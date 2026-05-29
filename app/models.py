from django.db import models
from django.contrib.auth.models import User
import uuid
from decimal import Decimal  # Ajout crucial pour la sécurité des calculs financiers
from django.utils import timezone 
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.conf import settings

# 1. CONFIGURATION ET BASE =============================================

class ConfigurationHopital(models.Model):
    # Utilisation d'une chaîne pour le default pour éviter les dérives de float
    taux_usd_en_cdf = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('2500.00'))
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration du Taux"

    def __str__(self):
        return f"1 USD = {self.taux_usd_en_cdf} CDF"


# 2. ROLE =======================================================
class Role(models.Model):
    roleName = models.CharField(max_length=30)
 
    def __str__(self):
        return self.roleName

# 3. FONCTION ======================================================
class Fonction(models.Model):
    fonctionKey = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)
    userKey = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='user_fonction')
    autorisation = models.CharField(max_length=30, default='oui')

    def __str__(self):
        if self.userKey and self.fonctionKey:
            return f"{self.userKey.username} - {self.fonctionKey.roleName}"
        return f"Autorisation: {self.autorisation}"


# 4. PRESTATIONS ===================================================
class Prestation(models.Model):
    CATEGORIES = [
        ('ADM', 'Administratif'), 
        ('LABO', 'Laboratoire'), 
        ('SOIN', 'Soins'), 
        ('ECHO', 'Échographie'), 
        ('RADIO', 'Radiologie'), 
    ]
    
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    categorie = models.CharField(max_length=10, choices=CATEGORIES, verbose_name="Catégorie")
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix (USD)")
    valeur_normale = models.CharField(
        max_length=150, blank=True, null=True, 
        verbose_name="Valeur Normale / Référence (Labo uniquement)",
        help_text="Ex: 70-110 mg/dl, Négatif, etc. Utilisé uniquement pour le Laboratoire."
    )

    def __str__(self):
        return f"{self.libelle} - {self.prix} USD"

    class Meta:
        verbose_name = "Prestation"
        verbose_name_plural = "Prestations"

    def clean(self):
        if self.categorie != 'LABO' and self.valeur_normale:
            self.valeur_normale = None

# 5. SERVICE =======================================================
class Service(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"

# 6. PATIENT =======================================================
class Patient(models.Model):
    # Champ unique pour l'identification
    code_patient = models.CharField(max_length=20, unique=True, editable=False)
    
    # Informations personnelles
    noms = models.CharField(max_length=100)
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Féminin')])
    age = models.CharField(max_length=30)
    adresse = models.TextField()
    telephone = models.CharField(max_length=20)
    
    # Statut du paiement de la fiche
    fiche_payee = models.BooleanField(default=False)
    
    # Relation avec Service (en utilisant le nom du modèle entre guillemets pour éviter les erreurs)
    service = models.ForeignKey('Service', on_delete=models.PROTECT, related_name='patients', null=True)
    
    # Audit et traçabilité
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='patients_crees')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Génération automatique du matricule patient à la création."""
        if not self.code_patient:
            annee = timezone.now().year
            prefixe = f"MLY-{annee}-"
            # On récupère le dernier patient créé avec ce préfixe
            last_patient = Patient.objects.filter(code_patient__startswith=prefixe).order_by('id').last()
            
            if last_patient:
                last_id = int(last_patient.code_patient.split('-')[-1])
                new_id = last_id + 1
            else:
                new_id = 1
            self.code_patient = f"{prefixe}{new_id:04d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.noms} ({self.code_patient})"

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"


# ============================================================================
#
#
class SigneVital(models.Model):
    # Lien vers le patient pour l'historique
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    
    # Les mesures médicales
    tension_sys = models.IntegerField()
    tension_dia = models.IntegerField()
    temperature = models.DecimalField(max_digits=4, decimal_places=1)
    poids = models.DecimalField(max_digits=5, decimal_places=2)
    frequence_cardiaque = models.IntegerField()
    
    # Date automatique pour créer la chronologie du carnet médical
    date_enregistrement = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Attention : utilisez self.patient.noms (avec un 's') 
        # au lieu de self.patient.nom
        return f"Signes vitaux de {self.patient.noms} - {self.date_enregistrement.strftime('%d/%m/%Y %H:%M')}"




# --- Nouveaux modèles ---

class Facture(models.Model):
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='factures')
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Lier les prestations à la facture
    prestations = models.ManyToManyField(Prestation, related_name='factures')
    est_payee = models.BooleanField(default=False)


    @property
    def reste_a_payer(self):
        total_paye = sum(p.montant_paye for p in self.paiements.all())
        return self.montant_total - total_paye
        
    def __str__(self):
        return f"Facture #{self.id} - {self.patient.noms}"

class Paiement(models.Model):
    METHODES = [
        ('CASH', 'Espèces'),
        ('BANK', 'Virement/Banque'),
        ('MOBILE', 'Mobile Money'),
    ]
    
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='paiements')
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    methode_paiement = models.CharField(max_length=10, choices=METHODES)
    date_paiement = models.DateTimeField(default=timezone.now)
    
    # Pour les statistiques : on lie la prestation au paiement si nécessaire,
    # mais il est plus simple de filtrer par la facture.
    
    def __str__(self):
        return f"Paiement {self.montant_paye} USD - Facture #{self.facture.id}"


