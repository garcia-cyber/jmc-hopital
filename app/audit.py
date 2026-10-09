"""
AUDIT DU PROJET
===============
A enregistrer dans le MEME dossier que models.py, sous le nom : audit.py

Ce fichier fait deux choses :

1. Le middleware retient quel utilisateur (et quelle adresse IP) fait la
   requête en cours. Sans lui, un signal Django ne sait pas "qui" agit.

2. Les signaux enregistrent automatiquement dans AuditLog :
   - chaque CREATION, MODIFICATION et SUPPRESSION des modèles listés
     dans MODELES_AUDITES (avec les valeurs avant / après)
   - chaque CONNEXION, DECONNEXION et ECHEC de connexion

Aucune vue existante n'a besoin d'être modifiée.
"""

import contextvars
import ipaddress
import logging

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ==============================================================
# 1) MODELES SURVEILLES (ajoute ou retire des noms librement)
# ==============================================================
MODELES_AUDITES = [
    # Finance
    "Paiement",
    "Facture",
    "Depense",
    "ConfigurationHopital",   # le taux USD/CDF
    "Prestation",             # les prix
    "Entreprise",
    # Patients et soins
    "Patient",
    "ClientExterne",
    "ActeMedical",
    "Consultation",
    "Ordonnance",
    "Hospitalisation",
    "SessionSoins",
    "Maternite",
    "Deces",
    "BlocOperatoire",
    "DemandeExamenExterne",
    # Pharmacie
    "ProduitPharmacie",
    "LotPharmacie",
    "SortiePharmacie",
    # Administration
    "Hopital",
    "Service",
    "Fonction",               # qui a quel rôle dans quel hôpital
]

# Champs jamais enregistrés dans le journal
CHAMPS_IGNORES = {
    "password",
    "last_login",
    "date_modification",
    "derniere_mise_a_jour",
}


# ==============================================================
# 2) MIDDLEWARE : retient la requête en cours
# ==============================================================
_requete_courante = contextvars.ContextVar("audit_requete", default=None)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jeton = _requete_courante.set(request)
        try:
            return self.get_response(request)
        finally:
            _requete_courante.reset(jeton)


# ==============================================================
# 3) OUTILS
# ==============================================================
def _utilisateur_courant():
    requete = _requete_courante.get()
    user = getattr(requete, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return None


def _adresse_ip(requete):
    if requete is None:
        return None

    brut = requete.META.get("HTTP_X_FORWARDED_FOR")
    if brut:
        brut = brut.split(",")[0].strip()
    else:
        brut = requete.META.get("REMOTE_ADDR")

    try:
        return str(ipaddress.ip_address(brut))
    except (ValueError, TypeError):
        return None


def _hopital_id_de(user, requete):
    """Hôpital actif de l'utilisateur (mis en cache pour la requête)."""
    if user is None:
        return None

    if requete is not None and hasattr(requete, "_audit_hopital_id"):
        return requete._audit_hopital_id

    from .models import Fonction

    fonction = Fonction.objects.filter(
        userKey=user,
        autorisation="oui",
    ).first()
    valeur = fonction.hopital_id if fonction else None

    if requete is not None:
        requete._audit_hopital_id = valeur

    return valeur


def _valeur(v):
    """Convertit une valeur en texte/nombre simple pour le stockage JSON."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return str(v)[:200]


def _instantane(instance):
    """Photo des valeurs d'un objet : {nom_du_champ: valeur}."""
    donnees = {}
    for champ in instance._meta.concrete_fields:
        if champ.name in CHAMPS_IGNORES:
            continue
        donnees[champ.name] = _valeur(champ.value_from_object(instance))
    return donnees


def _representation(instance):
    try:
        return str(instance)[:200]
    except Exception:
        return f"{instance.__class__.__name__} #{instance.pk}"


def _enregistrer(**donnees):
    """Ecrit une ligne dans le journal sans jamais bloquer l'opération."""
    from .models import AuditLog

    try:
        with transaction.atomic():
            AuditLog.objects.create(**donnees)
    except Exception:
        logger.exception("Audit : impossible d'enregistrer la ligne du journal")


# ==============================================================
# 4) SIGNAUX SUR LES MODELES (création / modification / suppression)
# ==============================================================
def _avant_sauvegarde(sender, instance, raw=False, **kwargs):
    # On garde l'état d'avant pour pouvoir comparer après
    instance._audit_avant = None

    if raw or instance.pk is None:
        return

    ancien = sender._base_manager.filter(pk=instance.pk).first()
    if ancien is not None:
        instance._audit_avant = _instantane(ancien)


def _apres_sauvegarde(sender, instance, created, raw=False, **kwargs):
    if raw:  # chargement de fixtures : on ne journalise pas
        return

    apres = _instantane(instance)
    avant = getattr(instance, "_audit_avant", None)
    instance._audit_avant = None

    if created or avant is None:
        action = "CREATION"
        changements = {
            nom: [None, val]
            for nom, val in apres.items()
            if val not in (None, "")
        }
    else:
        action = "MODIFICATION"
        changements = {
            nom: [avant.get(nom), val]
            for nom, val in apres.items()
            if avant.get(nom) != val
        }
        if not changements:  # rien n'a changé : pas de ligne inutile
            return

    _ecrire_objet(action, instance, changements)


def _apres_suppression(sender, instance, **kwargs):
    changements = {
        nom: [val, None]
        for nom, val in _instantane(instance).items()
        if val not in (None, "")
    }
    _ecrire_objet("SUPPRESSION", instance, changements)


def _ecrire_objet(action, instance, changements):
    requete = _requete_courante.get()
    user = _utilisateur_courant()

    if instance.__class__.__name__ == "Hopital":
        hopital_id = instance.pk
    else:
        hopital_id = getattr(instance, "hopital_id", None) or _hopital_id_de(
            user, requete
        )

    _enregistrer(
        utilisateur=user,
        nom_utilisateur=user.username if user else "Système",
        hopital_id=hopital_id,
        action=action,
        modele=instance.__class__.__name__,
        objet_id=str(instance.pk),
        objet_repr=_representation(instance),
        changements=changements,
        adresse_ip=_adresse_ip(requete),
        chemin=(requete.path[:255] if requete is not None else ""),
    )


def connecter_audit(espace_models):
    """
    Branche les signaux sur les modèles de MODELES_AUDITES.
    Appelée une seule fois, à la fin de models.py :
        connecter_audit(globals())
    """
    for nom in MODELES_AUDITES:
        modele = espace_models.get(nom)
        if modele is None:
            logger.warning("Audit : le modèle %s n'existe pas, ignoré.", nom)
            continue

        pre_save.connect(
            _avant_sauvegarde, sender=modele,
            dispatch_uid=f"audit_pre_{nom}", weak=False,
        )
        post_save.connect(
            _apres_sauvegarde, sender=modele,
            dispatch_uid=f"audit_post_{nom}", weak=False,
        )
        post_delete.connect(
            _apres_suppression, sender=modele,
            dispatch_uid=f"audit_del_{nom}", weak=False,
        )


# ==============================================================
# 5) SIGNAUX DE CONNEXION
# ==============================================================
@receiver(user_logged_in)
def _audit_connexion(sender, request, user, **kwargs):
    _enregistrer(
        utilisateur=user,
        nom_utilisateur=user.username,
        hopital_id=_hopital_id_de(user, request),
        action="CONNEXION",
        objet_repr="Connexion réussie",
        adresse_ip=_adresse_ip(request),
        chemin=(request.path[:255] if request is not None else ""),
    )


@receiver(user_logged_out)
def _audit_deconnexion(sender, request, user, **kwargs):
    if user is None:
        return
    _enregistrer(
        utilisateur=user,
        nom_utilisateur=user.username,
        hopital_id=_hopital_id_de(user, request),
        action="DECONNEXION",
        objet_repr="Déconnexion",
        adresse_ip=_adresse_ip(request),
        chemin=(request.path[:255] if request is not None else ""),
    )


@receiver(user_login_failed)
def _audit_echec_connexion(sender, credentials, **kwargs):
    request = kwargs.get("request")
    # On garde seulement l'identifiant saisi, JAMAIS le mot de passe
    identifiant = str((credentials or {}).get("username", ""))[:150]
    _enregistrer(
        utilisateur=None,
        nom_utilisateur=identifiant,
        action="ECHEC_CONNEXION",
        objet_repr=f"Identifiant saisi : {identifiant}",
        adresse_ip=_adresse_ip(request),
        chemin=(request.path[:255] if request is not None else ""),
    )