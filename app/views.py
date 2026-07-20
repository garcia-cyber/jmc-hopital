from django.shortcuts import render , redirect , get_object_or_404
from .forms import *
from .models import *
from django.contrib.auth import authenticate , login as auth_login , logout ,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm ,UserChangeForm , PasswordChangeForm
from django.contrib import messages
from django.db.models import Q , Sum ,Prefetch , Count , ExpressionWrapper , OuterRef, Subquery , F , Value ,DecimalField, FloatField ,IntegerField ,Exists
from decimal import Decimal , ROUND_HALF_UP , InvalidOperation
import pytz
from datetime import timedelta , date  , datetime
from django.db import transaction
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models.functions import Coalesce , Length ,TruncDay, TruncWeek, TruncMonth
import json
from django.http import JsonResponse , HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.exceptions import PermissionDenied
from django.contrib.admin.views.decorators import staff_member_required


# Create your views here.


# 1
# ======================================================================================
# PAGE D'ACCUEIL
# ======================================================================================
def home(request):
    return render(request , "front-end/index.html") 

# 2
# =====================================================================
# CONNEXION DANS LE SYSTEME
# =====================================================================
def login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    msg = None
    now = timezone.now()

    lock_until = request.session.get('lock_until')
    if lock_until:
        lock_until_dt = parse_datetime(lock_until)
        if lock_until_dt and now < lock_until_dt:
            form = LoginForm()
            msg = "Trop de tentatives. Réessayez dans 2 minutes."
            return render(request, 'back-end/login.html', {'form': form, 'msg': msg})
        else:
            request.session.pop('lock_until', None)
            request.session.pop('login_attempts', None)

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            user = authenticate(request, username=username, password=password)

            if user is not None:
                if user.is_active:
                    request.session.pop('login_attempts', None)
                    request.session.pop('lock_until', None)
                    auth_login(request, user)
                    return redirect('dashboard')
                else:
                    msg = "Votre compte est désactivé."
            else:
                attempts = request.session.get('login_attempts', 0) + 1
                request.session['login_attempts'] = attempts

                if attempts >= 3:
                    request.session['lock_until'] = (now + timedelta(minutes=2)).isoformat()
                    msg = "Trop de tentatives. Le formulaire est bloqué pendant 2 minutes."
                else:
                    msg = "Identifiants invalides. Veuillez réessayer. 🤞"
    else:
        form = LoginForm()

    return render(request, 'back-end/login.html', {'form': form, 'msg': msg})
# 3
# ==========================================================================
# DECONNEXION
# ==========================================================================
def deco(request):
    logout(request)
    return redirect('home')

# 4
# ==========================================================================
# DASHBOARD
# ==========================================================================
@login_required
def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else 'visiteur'
    user_hopital = role.hopital if role else None
    aujourdhui = timezone.now().date()

    paiements_qs = Paiement.objects.all()
    depenses_qs = Depense.objects.all()
    consultations_qs = Consultation.objects.all()
    hospitalisations_qs = Hospitalisation.objects.all()
    blocs_qs = BlocOperatoire.objects.all()
    accouchements_qs = CompteRenduAccouchement.objects.all()
    produits_qs = ProduitPharmacie.objects.all()
    entreprises_qs = Entreprise.objects.all()
    patients_qs = Patient.objects.all()

    if fonctionKey != 'admin' and user_hopital:
        paiements_qs = paiements_qs.filter(hopital=user_hopital)
        depenses_qs = depenses_qs.filter(hopital=user_hopital)
        consultations_qs = consultations_qs.filter(hopital=user_hopital)
        hospitalisations_qs = hospitalisations_qs.filter(hopital=user_hopital)
        blocs_qs = blocs_qs.filter(hopital=user_hopital)
        accouchements_qs = accouchements_qs.filter(hopital=user_hopital)
        produits_qs = produits_qs.filter(hopital=user_hopital)
        entreprises_qs = entreprises_qs.filter(hopital=user_hopital)
        patients_qs = patients_qs.filter(hopital=user_hopital)
        total_utilisateurs = User.objects.filter(user_fonction__hopital=user_hopital).distinct().count()
    else:
        total_utilisateurs = User.objects.count()

    recettes_jour = paiements_qs.filter(date_paiement__date=aujourdhui).aggregate(
        usd=Sum('montant_verse', filter=Q(devise='USD')),
        cdf=Sum('montant_verse', filter=Q(devise='CDF'))
    )

    depenses_jour = depenses_qs.filter(date_depense__date=aujourdhui).aggregate(
        usd=Sum('montant', filter=Q(devise='USD')),
        cdf=Sum('montant', filter=Q(devise='CDF'))
    )

    context = {
        'fonctionKey': fonctionKey,
        'hopital_user': user_hopital,
        'total_utilisateurs': total_utilisateurs,
        'total_entreprises': entreprises_qs.count(),
        'total_patients': patients_qs.count(),
        'recettes_jour': recettes_jour,
        'depenses_jour': depenses_jour,
        'consultations_jour': consultations_qs.filter(date_creation__date=aujourdhui).count(),
        'hospitalisations_en_cours': hospitalisations_qs.filter(statut='EN_COURS').count(),
        'bloc_en_cours': blocs_qs.filter(statut='EN_COURS').count(),
        'accouchements_jour': accouchements_qs.filter(date_creation__date=aujourdhui).count(),
        'alerte_rupture_stock': produits_qs.filter(stock_initial__lt=5).count(),
    }

    return render(request, 'back-end/index.html', context)# 5
# ===========================================================================
# AJOUTER UTILISATEURS
# ===========================================================================
@login_required
def employeAdd(request):
    msg = None
    
    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES) # Ajout de request.FILES si le formulaire contient des images/fichiers
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            
            # Message de succès
            msg = "Employé enregistré avec succès !"
            
            # Optionnel mais recommandé : Rediriger ou réinitialiser le formulaire pour éviter les doubles soumissions si on rafraîchit la page
            form = EmployeForm() 
    else:
        # Le formulaire vide n'est créé QUE si la méthode est GET
        form = EmployeForm()

    # Vérification de la fonction de l'utilisateur connecté
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'fonctionKey': fonctionKey, 
        'form': form, 
        'msg': msg
    }
    return render(request, 'back-end/employeAdd.html', context)

# 6
# ============================================================================
# LISTE DES UTILISATEURS ENREGISTRE
# ============================================================================
@login_required
def employeRead(request):

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    # listes des utilisateurs
    lst_user = User.objects.all()
    context = {
        'fonctionKey' : fonctionKey ,
        'lst_user'    : lst_user ,
    }
    return render(request , 'back-end/employeRead.html' , context)

# 7 
# ============================================================================
# ATTRIBUE POSTE OU ROLE
# ============================================================================
@login_required
def attribuer_fonction(request, user_id):
    employe = get_object_or_404(User, id=user_id)
    msg = None

    if request.method == 'POST':
        form = FonctionForm(request.POST)
        if form.is_valid():
            fonction_instance = form.save(commit=False) # Changé le nom pour éviter les confusions
            fonction_instance.userKey = employe 
            fonction_instance.save()
            return redirect('employeRead') 
    else:
        form = FonctionForm()

    # Vérification de la fonction de l'utilisateur connecté
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'form': form,
        'employe': employe,
        'msg': msg, 
        'fonctionKey': fonctionKey # On passe la clé de fonction pour ton sidebar/droits
    }
    # J'ai retiré 'fonction': fonction qui causait l'erreur
    return render(request, 'back-end/employePoste.html', context)
# 8
# =================================================================================
#
# =================================================================================
@login_required
def liste_employe_poste(request):
    # Pour ton menu (récupère le rôle de l'utilisateur connecté)
    role_user = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_user.fonctionKey.roleName if role_user else None

    # On récupère la liste de tous les employés ayant une fonction
    # select_related permet d'éviter les requêtes répétitives en base de données
    liste_postes = Fonction.objects.all().select_related('userKey', 'fonctionKey')

    context = {
        'liste_postes': liste_postes,
        'fonctionKey': fonctionKey,
    }
    return render(request, 'back-end/liste_fonctions.html', context)


# 9
# =================================================================================
# SUPPRIMER POSTE
# =================================================================================
@login_required
def supprimer_poste(request, fonction_id):
    # Supprime l'attribution du poste
    poste = get_object_or_404(Fonction, id=fonction_id)
    poste.delete()
    return redirect('liste_employe_poste')

# 10
# =================================================================================
# CHANGEMENT DU MOT DE PASSE SANS CONNAITRE LE MOT DE PASSE  
# =================================================================================
@login_required
def force_reinitialiser_pass(request, user_id):
    # On récupère l'utilisateur cible (soit soi-même, soit un employé par un admin)
    u = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # On passe l'utilisateur au formulaire
        form = SetPasswordForm(user=u, data=request.POST)
        if form.is_valid():
            user = form.save()
            # Important : évite de déconnecter l'utilisateur si c'est son propre compte
            update_session_auth_hash(request, user)
            messages.success(request, f"Le mot de passe de {u.username} a été mis à jour.")
            return redirect('employeRead')
    else:
        form = SetPasswordForm(user=u)

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/reinitialiser_pass.html', {
        'form': form,
        'u': u ,
        'fonctionKey' : fonctionKey
    })
# 11
# ==================================================================================================
# MODIFICATION USER 
# ==================================================================================================
@login_required
def modifier_utilisateur(request, user_id):
    u = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # On lie le formulaire à l'utilisateur existant (instance=u)
        form = ModifierUserForm(request.POST, instance=u)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour avec succès !")
            return redirect('employeRead')
    else:
        # Affiche le formulaire pré-rempli avec username et email uniquement
        form = ModifierUserForm(instance=u)

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/modifier_user.html', {
        'form': form,
        'u': u ,
        'fonctionKey': fonctionKey
    }) 

# 12
# ==================================================================================================
# PRESTATION ET LISTE DES PRESTATIONS 
# ==================================================================================================
@login_required
def gestion_prestations(request):
    # 1. Gestion de la recherche (Query)
    query = request.GET.get('q')
    if query:
        prestations_list = Prestation.objects.filter(
            Q(libelle__icontains=query) | Q(categorie__icontains=query)
        ).order_by('libelle')
    else:
        prestations_list = Prestation.objects.all().order_by('libelle')

    # 2. Récupération du taux de change (Correction du type ici)
    config = ConfigurationHopital.objects.first()
    taux_valeur = config.taux_usd_en_cdf if config else 2500.00
    taux = Decimal(str(taux_valeur)) # Conversion sécurisée pour le calcul financier

    # 3. Pagination (10 éléments par page)
    paginator = Paginator(prestations_list, 10)
    page_number = request.GET.get('page')
    prestations_obj = paginator.get_page(page_number)

    # 4. Calcul du prix en CDF pour les éléments de la page actuelle
    for item in prestations_obj:
        item.prix_cdf = item.prix * taux

    # 5. Gestion de l'ajout (POST)
    if request.method == 'POST':
        form = PrestationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "La prestation a été ajoutée avec succès.")
            return redirect('gestion_prestations')
    else:
        form = PrestationForm()

    # 6. Gestion du rôle utilisateur (Vérification rétablie)
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 7. Préparation des catégories pour le modal de modification
    categories_list = Prestation._meta.get_field('categorie').choices

    # 8. Contexte complet
    context = {
        'prestations': prestations_obj,
        'form': form,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'categories_list': categories_list,
    }
    
    return render(request, 'back-end/prestation/list_prestation.html', context)
# 13
# ==================================================================================================
#  VUE CONFIGURATION TAUX (Modification unique) ---
# ==================================================================================================
@login_required
def modifier_taux(request):
    # On récupère le premier (et unique) objet, ou on en crée un s'il n'existe pas
    config, created = ConfigurationHopital.objects.get_or_create(id=1)
    
    if request.method == 'POST':
        form = ConfigurationHopitalForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, f"Le taux de change a été mis à jour : 1 USD = {config.taux_usd_en_cdf} CDF")
            return redirect('modifier_taux')
    else:
        form = ConfigurationHopitalForm(instance=config)

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/prestation/config_taux.html', {'form': form, 'config': config ,'fonctionKey':fonctionKey})

# 14
# ==================================================================================================
#  MODIFICATION PRESTATION
# ==================================================================================================
@login_required
def modifier_prestation(request, pk):
    prestation = get_object_or_404(Prestation, pk=pk)

    if request.method == 'POST':
        form = PrestationForm(request.POST, instance=prestation)
        if form.is_valid():
            form.save()
            messages.success(request, f"La prestation '{prestation.libelle}' a été mise à jour.")
            return redirect('gestion_prestations')
        else:
            messages.error(request, "Erreur lors de la mise à jour. Vérifiez les données.")
    else:
        form = PrestationForm(instance=prestation)

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/prestation/modifier_prestation.html', {
        'form': form,
        'prestation': prestation ,
        'fonctionKey': fonctionKey
    })

# 15
# ==================================================================================================
#  ENREGISTREMENT DES SERVICES
# ==================================================================================================
@login_required
def gestion_services(request):
    """Affiche la liste et gère l'ajout de nouveaux services"""
    services = Service.objects.all().order_by('-date_creation')
    
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Service '{form.cleaned_data['nom']}' ajouté avec succès.")
            return redirect('gestion_services')
    else:
        form = ServiceForm()

    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/service/gestion_services.html', {
        'services': services,
        'form': form ,
        'fonctionKey': fonctionKey
    })

# 16
# ==================================================================================================
#  MODIFICATION DES SERVICES
# ==================================================================================================

@login_required
def modifier_service(request, pk):
    """Modifie un service existant"""
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, "Service mis à jour avec succès.")
            return redirect('gestion_services')
    else:
        form = ServiceForm(instance=service)
    
    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/service/modifier_service.html', {
        'form': form,
        'service': service ,
        'fonctionKey' : fonctionKey
    })


# 17
# ==================================================================================================
#  ENREGISTREMENT DES PATIENT(E)S 
# ==================================================================================================
@login_required
def enregistrement_patient(request):
    user_fonction = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = user_fonction.hopital if user_fonction else None
    fonctionKey = user_fonction.fonctionKey.roleName if (user_fonction and user_fonction.fonctionKey) else "Invité"

    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            try:
                patient = form.save(commit=False)
                patient.created_by = request.user

                if not hopital_user:
                    messages.error(request, "Impossible d'enregistrer : votre compte n'est rattaché à aucun hôpital.")
                    return redirect('enregistrement_patient')

                patient.hopital = hopital_user

                if patient.entreprise and patient.entreprise.hopital_id != hopital_user.id:
                    messages.error(request, "Cette entreprise n'appartient pas à votre hôpital.")
                    return redirect('enregistrement_patient')

                if patient.entreprise:
                    patient.type_patient = 'CONVENTIONNE'

                patient.save()
                messages.success(request, f"Patient {patient.noms} enregistré avec succès.")
                return redirect('enregistrement_patient')
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.capitalize()}: {error}")
    else:
        form = PatientForm()

    patients = Patient.objects.select_related('entreprise', 'created_by', 'hopital').order_by('-date_creation')

    entreprises = Entreprise.objects.filter(hopital=hopital_user).order_by('nom') if hopital_user else Entreprise.objects.none()

    return render(request, 'back-end/patient/enregistrement_patient.html', {
        'patients': patients,
        'form': form,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
        'entreprises': entreprises,
    })

# 18
# ==================================================================================================
#  LISTE DES PATIENT(E)S 
# ==================================================================================================
@login_required
def liste_patients(request):
    query = request.GET.get('search')
    
    # On récupère tous les patients et on pré-charge les données de l'entreprise
    # pour éviter le problème "N+1" dans le tableau
    patients = Patient.objects.select_related('entreprise').order_by('-date_creation')
    
    if query:
        patients = patients.filter(
            Q(noms__icontains=query) | 
            Q(code_patient__icontains=query) |
            Q(entreprise__nom__icontains=query) # Permet de chercher par entreprise !
        )
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if (role and role.fonctionKey) else None

    return render(request, 'back-end/patient/liste_patients.html', {
        'patients': patients,
        'fonctionKey': fonctionKey
    })

# 19
# ==================================================================================================
#  MODIFICATION DES PATIENT(E)S 
# ==================================================================================================
@login_required
def modifier_patient(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    
    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, f"La fiche de {patient.noms} a été mise à jour.")
            return redirect('enregistrement_patient')
    else:
        form = PatientForm(instance=patient)
    
    # verification de la fonction
    role = Fonction.objects.filter(userKey = request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/patient/modifier_patient.html', {
        'form': form,
        'patient': patient ,
        'fonctionKey' : fonctionKey
    })

# 20
# ==================================================================================================
# PAIEMENT DE LA FICHE
# ==================================================================================================
@login_required
def payer_fiche(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')

    role = Fonction.objects.filter(userKey=request.user).select_related('hopital', 'fonctionKey').first()
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if patient.hopital != hopital_user:
        messages.error(request, "Ce patient appartient à un autre hôpital. Vous ne pouvez pas encaisser sa fiche.")
        return redirect('enregistrement_patient')

    prestation_fiche = Prestation.objects.filter(
        categorie='ADM',
        libelle__icontains="Fiche",
        hopital=hopital_user
    ).first()

    if not prestation_fiche:
        messages.error(request, f"La prestation 'Fiche' n'est pas configurée pour votre hôpital ({hopital_user.nom}).")
        return redirect('enregistrement_patient')

    prix_fiche_usd = Decimal(str(prestation_fiche.prix))

    paiements_existants = Paiement.objects.filter(patient=patient, service='FICHE')
    total_deja_paye_usd = Decimal('0.00')

    for p in paiements_existants:
        if p.devise == 'CDF':
            total_deja_paye_usd += p.montant_verse / taux
        else:
            total_deja_paye_usd += p.montant_verse

    reste_a_payer_usd = prix_fiche_usd - total_deja_paye_usd

    if request.method == 'POST':
        montant_saisi = Decimal(request.POST.get('montant', 0))
        devise = request.POST.get('devise')

        montant_test_usd = montant_saisi
        if devise == 'CDF':
            montant_test_usd = montant_saisi / taux

        if montant_test_usd > (reste_a_payer_usd + Decimal('0.01')):
            messages.error(request, f"Le montant dépasse le reste à payer ({reste_a_payer_usd:.2f} USD).")
        elif montant_saisi > 0:
            Paiement.objects.create(
                patient=patient,
                service='FICHE',
                montant_verse=montant_saisi,
                devise=devise,
                caissier=request.user,
                hopital=hopital_user
            )

            nouveau_total_usd = total_deja_paye_usd + montant_test_usd

            if nouveau_total_usd >= (prix_fiche_usd - Decimal('0.01')):
                patient.fiche_payee = True
                patient.save()
                messages.success(request, f"Paiement terminé. La fiche de {patient.noms} est validée.")
            else:
                messages.success(request, f"Paiement enregistré. Reste à payer : {(prix_fiche_usd - nouveau_total_usd):.2f} USD")

            return redirect('enregistrement_patient')

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'patient': patient,
        'reste_a_payer': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_usd * taux,
        'taux': taux,
        'prix_fiche': prix_fiche_usd,
        'libelle_prestation': prestation_fiche.libelle,
        'fonctionKey': fonctionKey,
        'deja_paye': patient.fiche_payee,
    }
    return render(request, 'back-end/finance/payer_fiche.html', context)
# 21
# ==================================================================================================
# HISTORIQUE DE PAIEMENT
# ==================================================================================================
@login_required
def historique_paiements(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Récupération du taux de change (assurez-vous d'avoir une méthode pour cela)
    taux = Decimal(str(getattr(ConfigurationHopital.objects.first(), 'taux_change', 1660)))

    # 1. CALCULS DES COÛTS (Sécurisation des objets)
    # Prix de la fiche
    cout_fiche = Decimal(str(getattr(patient.service, 'prix', 0))) if patient.service else Decimal('0.00')
    
    # Prix des examens
    cout_examens = Prestation.objects.filter(
        demandeexamen__consultation__triage__patient=patient
    ).aggregate(total=Sum('prix'))['total'] or Decimal('0.00')
    
    # Prix du Bloc (Sécurisation pour éviter l'erreur NoneType)
    bloc = BlocOperatoire.objects.filter(consultation__triage__patient=patient).first()
    cout_bloc = bloc.prestation.prix if (bloc and hasattr(bloc, 'prestation') and bloc.prestation) else Decimal('0.00')
    
    total_cout_usd = cout_fiche + cout_examens + cout_bloc
    
    # 2. CALCULS PAIEMENTS RÉELS
    paiements = Paiement.objects.filter(patient=patient)
    recettes = paiements.aggregate(
        usd=Sum('montant_verse', filter=Q(devise='USD')),
        cdf=Sum('montant_verse', filter=Q(devise='CDF'))
    )
    
    total_paye_usd = recettes['usd'] or Decimal('0.00')
    total_paye_cdf = recettes['cdf'] or Decimal('0.00')
    
    # Conversion du payé en CDF vers USD pour calculer la dette totale
    total_paye_en_usd = total_paye_usd + (total_paye_cdf / taux)
    
    # 3. RÉSULTATS ET DETTES
    reste_a_payer_usd = max(Decimal('0.00'), total_cout_usd - total_paye_en_usd)
    reste_a_payer_cdf = reste_a_payer_usd * taux
    
    # Objets pour les boutons d'encaissement
    consultation = Consultation.objects.filter(triage__patient=patient).order_by('-date_creation').first()
    
    context = {
        'patient': patient,
        'paiements_liste': paiements.order_by('-date_paiement'),
        'cout_total_usd': total_cout_usd,
        'total_paye_usd': total_paye_usd,
        'total_paye_cdf': total_paye_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'est_debiteur': reste_a_payer_usd > 0.01, # Si > 0.01$ de dette
        'derniere_consultation': consultation,
        'bloc_id': bloc.id if bloc else None,
        'fonctionKey': Fonction.objects.filter(userKey=request.user).first().fonctionKey.roleName 
                       if Fonction.objects.filter(userKey=request.user).first() else None
    }
    return render(request, 'back-end/finance/historique.html', context)


# 22
# ==================================================================================================
# IMPRIMER FACTURE
# ==================================================================================================
@login_required
def imprimer_recu_direct(request, paiement_id):
    paiement = get_object_or_404(Paiement, id=paiement_id)

    date_reelle = paiement.date_paiement

    examens_associes = []
    nom_prestation = None

    if paiement.consultation and paiement.service in ['LABO', 'RADIO', 'ECHOGRAPHIE', 'EXAMENS']:
        examens_payes = paiement.consultation.examens.filter(
            statut__in=['EN_COURS', 'TERMINE']
        ).select_related('prestation')

        for exam in examens_payes:
            if exam.prestation:
                examens_associes.append({
                    'libelle': exam.prestation.libelle,
                    'prix': exam.prestation.prix
                })

        if paiement.service == 'EXAMENS' and examens_associes:
            nom_prestation = examens_associes[0]['libelle']
        elif examens_payes.exists() and examens_payes.first().prestation:
            nom_prestation = examens_payes.first().prestation.libelle

    context = {
        'paiement': paiement,
        'patient': paiement.patient,
        'date_paiement_fix': date_reelle,
        'examens_ticket': examens_associes,
        'nom_prestation': nom_prestation,
    }
    return render(request, 'back-end/finance/ticket_paiement.html', context)
# 23
# ==================================================================================================
# PATIENT LISTE D'ATTENTE TRIAGE
# ==================================================================================================
@login_required
def liste_attente_triage(request):
    taux = ConfigurationHopital.get_taux()

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    prestation_fiche = Prestation.objects.filter(
        categorie='ADM',
        libelle__icontains='Fiche',
        hopital=hopital_user
    ).first()

    prix_fiche_usd = prestation_fiche.prix if prestation_fiche else Decimal('6.00')

    patients_liste = Patient.objects.filter(hopital=hopital_user).order_by('-date_creation')

    for patient in patients_liste:
        if patient.type_patient != 'SIMPLE':
            patient.a_solde_fiche = True
            patient.total_fiche_usd = Decimal('0.00')
            patient.doit_payer_fiche = False
        else:
            patient.doit_payer_fiche = True
            paiements = Paiement.objects.filter(patient=patient, service='FICHE', hopital=hopital_user)
            total_paye_usd = sum([
                p.montant_verse if p.devise == 'USD' else (p.montant_verse / taux)
                for p in paiements
            ], Decimal('0.00'))

            patient.total_fiche_usd = total_paye_usd
            patient.a_solde_fiche = total_paye_usd >= prix_fiche_usd

        patient.a_signes_vitaux_deja_pris = SigneVital.objects.filter(patient=patient).exists()

    fonctionKey = role.fonctionKey.roleName if (role and role.fonctionKey) else None

    return render(request, 'back-end/infirmerie/liste_attente.html', {
        'patients': patients_liste,
        'taux': taux,
        'prix_fiche': prix_fiche_usd,
        'fonctionKey': fonctionKey
    })



# 24
# ==================================================================================================
# PATIENT SIGNE VITAUX
# ==================================================================================================
@login_required
def saisir_signes(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    today = timezone.now().date()
    
    # On vérifie si un prélèvement non consulté existe déjà pour aujourd'hui
    triage_existant = SigneVital.objects.filter(
        patient=patient,
        date_prelevement__date=today,  
        est_consulte=False
    ).first()

    if request.method == 'POST':
        try:
            if triage_existant:
                # [MODE MISE À JOUR] : Le patient existe déjà, on écrase les anciennes valeurs
                triage_existant.temperature = request.POST.get('temp')
                triage_existant.poids = request.POST.get('poids')
                triage_existant.tension_arterielle = request.POST.get('tension')
                triage_existant.frequence_cardiaque = request.POST.get('pouls')
                triage_existant.frequence_respiratoire = request.POST.get('f_resp')
                triage_existant.saturation_oxygene = request.POST.get('spo2')
                triage_existant.infirmier = request.user  # L'infirmier qui fait la modification
                triage_existant.date_prelevement = timezone.now()  # On actualise l'heure du prélèvement
                triage_existant.save()
                
                messages.success(request, f"Les signes vitaux de {patient.noms} ont été actualisés avec succès.")
            else:
                # [MODE CRÉATION] : Premier prélèvement de la journée pour ce patient
                SigneVital.objects.create(
                    patient=patient,
                    temperature=request.POST.get('temp'),
                    poids=request.POST.get('poids'),
                    tension_arterielle=request.POST.get('tension'),
                    frequence_cardiaque=request.POST.get('pouls'),
                    frequence_respiratoire=request.POST.get('f_resp'),
                    saturation_oxygene=request.POST.get('spo2'),
                    infirmier=request.user,
                    est_consulte=False 
                )
                messages.success(request, f"Signes vitaux de {patient.noms} enregistrés avec succès.")
                
            return redirect('liste_attente_triage')
            
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de l'enregistrement : {str(e)}")

    else:
        # En mode GET : Si le patient a déjà des constantes saisies aujourd'hui
        if triage_existant:
            messages.info(
                request, 
                f"Note : Ce patient a déjà été prélevé aujourd'hui à {triage_existant.date_prelevement.strftime('%H:%M')}. "
                "Modifier les valeurs ci-dessous mettra à jour sa fiche en attente."
            )

    # Gestion des rôles pour l'interface
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/infirmerie/form_triage.html', {
        'patient': patient, 
        'fonctionKey': fonctionKey,
        'triage_existant': triage_existant  # Passe ceci au HTML pour injecter les `value="{{ triage_existant.temperature }}"` dans les inputs
    })
# 25
# ==================================================================================================
# PATIENT LISTE GLOBALE SIGNE VITAUX 
# ==================================================================================================
@login_required
def liste_globale_triage(request):
    # On récupère tous les signes vitaux, mais on ne garde qu'un seul exemplaire par patient
    # On trie par date pour avoir les derniers prélèvements en haut
    historique_global = SigneVital.objects.select_related('patient', 'infirmier').all().order_by('-date_prelevement')

    # Gestion du rôle pour le sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'fonctionKey': fonctionKey,
        'historique': historique_global,
    }
    return render(request, 'back-end/infirmerie/liste_globale_triage.html', context)

# 26
# ==================================================================================================
# PATIENT SIGNE VITAUX  HISTORIQUE
# ==================================================================================================
@login_required
def historique_signes_vitaux(request, patient_id):
    # On récupère le patient spécifique ou erreur 404
    patient = get_object_or_404(Patient, id=patient_id)
    
    # On récupère tout l'historique des prélèvements pour ce patient
    # trié du plus récent au plus ancien
    historique = SigneVital.objects.filter(patient=patient).order_by('-date_prelevement')
    
    # Récupération du rôle pour le sidebar (ton système habituel)
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'patient': patient,
        'historique': historique,
        'fonctionKey': fonctionKey,
    }
    return render(request, 'back-end/infirmerie/historique_signes.html', context)


# 27
# ==================================================================================================
# MEDECIN LISTE CONSULTATION VOIR SIGNE VITAUX
# ==================================================================================================
@login_required
def liste_consultation_medecin(request):
    """
    Vue pour la liste de consultation du médecin.
    Récupère les signes vitaux non consultés,
    avec possibilité de filtrer selon la présence d'une session.
    """

    filtre = request.GET.get('filtre', 'tous')

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    patients_prets = SigneVital.objects.filter(
        est_consulte=False,
        patient__hopital=hopital_user
    ).select_related(
        'patient',
        'infirmier',
        'session'
    ).prefetch_related(
        'session__items__prestation'
    ).order_by('date_prelevement')

    if filtre == 'avec_session':
        patients_prets = patients_prets.filter(session__isnull=False)
    elif filtre == 'sans_session':
        patients_prets = patients_prets.filter(session__isnull=True)

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'fonctionKey': fonctionKey,
        'patients_prets': patients_prets,
        'filtre': filtre,
    }

    return render(request, 'back-end/medecin/liste_consultation.html', context)
# 28
# ==================================================================================================
# MEDECIN MARQUER CONSULTER POUR N'EST PLUS VOIR DANS LA LISTE
# ==================================================================================================
@login_required
def marquer_consulte(request, sv_id):
    # 1. On récupère le prélèvement spécifique
    signe = get_object_or_404(SigneVital, id=sv_id)
    
    # 2. On marque comme consulté pour qu'il disparaisse DIRECTEMENT de la liste d'attente
    signe.est_consulte = True
    signe.save()
    
    # 3. Redirection vers l'espace de travail du médecin
    return redirect('consultation_medicale', triage_id=sv_id)

# 30
# ==================================================================================================
# MEDECIN   CONSULTATION PATIENT
# ==================================================================================================

@login_required
def consultation_medicale(request, triage_id):
    triage = get_object_or_404(SigneVital, id=triage_id)

    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if triage.patient.hopital != hopital_user:
        messages.error(request, "Ce patient appartient à un autre hôpital.")
        return redirect('liste_consultation_medecin')

    consultation = Consultation.objects.filter(triage=triage).first()

    if triage.est_consulte and consultation is not None:
        messages.warning(request, f"Le dossier de consultation pour {triage.patient.noms} a déjà été clôturé.")
        return redirect('liste_consultation_medecin')

    if request.method == 'POST':
        if consultation is not None:
            messages.error(request, "Erreur : Cette consultation a déjà été enregistrée par un autre utilisateur.")
            return redirect('liste_consultation_medecin')

        form = ConsultationForm(request.POST, instance=consultation)

        examens_ids = request.POST.getlist('examens_ids')
        noms_medocs = request.POST.getlist('nom_medicament')
        posologies = request.POST.getlist('posologie')
        durees = request.POST.getlist('duree')

        if form.is_valid():
            try:
                with transaction.atomic():
                    if Consultation.objects.filter(triage=triage).exists():
                        raise Exception("Ce patient a déjà été pris en charge entre-temps.")

                    consultation_obj = form.save(commit=False)
                    consultation_obj.triage = triage
                    consultation_obj.medecin = request.user
                    consultation_obj.hopital = hopital_user
                    consultation_obj.save()

                    DemandeExamen.objects.filter(consultation=consultation_obj, statut='EN_ATTENTE').delete()

                    for e_id in examens_ids:
                        prestation = get_object_or_404(Prestation, id=e_id, hopital=hopital_user)
                        qty_value = request.POST.get(f'qty_{e_id}', 1)

                        DemandeExamen.objects.create(
                            consultation=consultation_obj,
                            prestation=prestation,
                            quantite=qty_value,
                            statut='EN_ATTENTE',
                            hopital=hopital_user
                        )

                    if any(n.strip() for n in noms_medocs if n):
                        ordonnance, _ = Ordonnance.objects.get_or_create(
                            consultation=consultation_obj,
                            type_ordonnance='URGENCE',
                            defaults={'hopital': hopital_user}
                        )
                        if not ordonnance.hopital:
                            ordonnance.hopital = hopital_user
                            ordonnance.save()

                        LigneMedicament.objects.filter(ordonnance=ordonnance).delete()

                        for i, nom in enumerate(noms_medocs):
                            if nom and nom.strip():
                                poso = posologies[i] if i < len(posologies) else ""
                                dur = durees[i] if i < len(durees) else ""

                                LigneMedicament.objects.create(
                                    ordonnance=ordonnance,
                                    nom_medicament=nom,
                                    posologie=poso,
                                    duree=dur,
                                    statut='EN_COURS',
                                    hopital=hopital_user
                                )

                    triage.est_consulte = True
                    triage.save()

                messages.success(request, f"Consultation de {triage.patient.noms} enregistrée et clôturée avec succès !")
                return redirect('liste_consultation_medecin')

            except Exception as e:
                messages.error(request, f"Une erreur technique est survenue : {str(e)}")
        else:
            messages.error(request, "Veuillez vérifier les erreurs dans le formulaire clinique.")

    else:
        form = ConsultationForm(instance=consultation)

    examens_disponibles = Prestation.objects.filter(
        categorie__in=['LABO', 'ECHO', 'RADIO'],
        hopital=hopital_user
    ).order_by('categorie', 'libelle')

    return render(request, 'back-end/medecin/consultation_medecin.html', {
        'triage': triage,
        'form': form,
        'examens_disponibles': examens_disponibles,
        'consultation': consultation,
        'fonctionKey': fonctionKey
    })




# 30
# ==================================================================================================
# MEDECIN  LISTE DES EXAMENS CONSULTER
# ==================================================================================================
@login_required
def liste_consultations_terminees(request):
    consultations = Consultation.objects.select_related(
        'triage__patient',
        'medecin'
    ).prefetch_related(
        'examens__prestation'
    ).order_by('-date_creation')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'consultations': consultations,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/liste_consultations.html', context)
#
# ==============================================================================================
# MODIFICATION DE LA CONSULTATION PAR LE MEDECIN 
# ==============================================================================================
@login_required
@login_required
def modifier_consultation(request, triage_id):
    triage = get_object_or_404(SigneVital, id=triage_id)

    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if triage.patient.hopital != hopital_user:
        messages.error(request, "Ce patient appartient à un autre hôpital.")
        return redirect('liste_consultation_medecin')

    consultation = Consultation.objects.filter(triage=triage).first()

    if consultation is None:
        messages.error(request, "Aucune consultation trouvée pour ce patient.")
        return redirect('liste_consultation_medecin')

    examens_disponibles = Prestation.objects.filter(
        hopital=hopital_user,
        categorie__in=['LABO', 'RADIO', 'ECHO']
    ).order_by('categorie', 'libelle')

    examens_existant = DemandeExamen.objects.filter(
        consultation=consultation,
        hopital=hopital_user
    ).select_related('prestation').order_by('date_demande')

    if request.method == 'POST':
        form = ConsultationForm(request.POST, instance=consultation)

        if form.is_valid():
            try:
                with transaction.atomic():
                    consultation_obj = form.save(commit=False)
                    consultation_obj.medecin = request.user
                    consultation_obj.hopital = hopital_user
                    consultation_obj.triage = triage
                    consultation_obj.save()

                    for exam in examens_existant:
                        prestation_id = request.POST.get(f'exam_{exam.id}_prestation')
                        quantite = request.POST.get(f'exam_{exam.id}_quantite')
                        statut = request.POST.get(f'exam_{exam.id}_statut')
                        indication = request.POST.get(f'exam_{exam.id}_indication')
                        resultat = request.POST.get(f'exam_{exam.id}_resultat')
                        date_realisation = request.POST.get(f'exam_{exam.id}_date_realisation')

                        if prestation_id:
                            prestation = get_object_or_404(
                                Prestation,
                                id=prestation_id,
                                hopital=hopital_user,
                                categorie__in=['LABO', 'RADIO', 'ECHO']
                            )
                            exam.prestation = prestation

                        if quantite:
                            exam.quantite = quantite
                        if statut:
                            exam.statut = statut
                        if indication is not None:
                            exam.indication = indication
                        if resultat is not None:
                            exam.resultat = resultat
                        if date_realisation:
                            exam.date_realisation = date_realisation

                        exam.hopital = hopital_user
                        exam.save()

                    prestation_ids = request.POST.getlist('examens_ids')
                    for prestation_id in prestation_ids:
                        prestation = get_object_or_404(
                            Prestation,
                            id=prestation_id,
                            hopital=hopital_user,
                            categorie__in=['LABO', 'RADIO', 'ECHO']
                        )

                        DemandeExamen.objects.create(
                            consultation=consultation_obj,
                            prestation=prestation,
                            quantite=request.POST.get(f'qty_{prestation_id}', 1),
                            statut=request.POST.get(f'statut_{prestation_id}', 'EN_ATTENTE'),
                            indication=request.POST.get(f'indication_{prestation_id}', ''),
                            resultat=request.POST.get(f'resultat_{prestation_id}', ''),
                            hopital=hopital_user,
                            date_realisation=request.POST.get(f'date_realisation_{prestation_id}') or None
                        )

                messages.success(request, f"Consultation de {triage.patient.noms} modifiée avec succès !")
                return redirect('liste_consultation_medecin')

            except Exception as e:
                messages.error(request, f"Une erreur technique est survenue : {str(e)}")
        else:
            messages.error(request, "Veuillez vérifier les erreurs du formulaire clinique.")
    else:
        form = ConsultationForm(instance=consultation)

    return render(request, 'back-end/medecin/modifier_consultation.html', {
        'triage': triage,
        'form': form,
        'consultation': consultation,
        'examens_disponibles': examens_disponibles,
        'examens_existant': examens_existant,
        'fonctionKey': fonctionKey
    })
# 31
# ==================================================================================================
# MEDECIN  DETAILS CONSULTATION 
# ==================================================================================================
@login_required
def detail_consultation_view(request, pk):
    # On récupère la consultation avec ses relations pour optimiser les requêtes
    consultation = get_object_or_404(
        Consultation.objects.select_related('triage__patient', 'medecin').prefetch_related('examens__prestation'),
        pk=pk
    )

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/medecin/detail_consultation.html', {'c': consultation, 'fonctionKey':fonctionKey})


# 32
# ==================================================================================================
# MEDECIN  VOIR LES ORDONNANCES D'URGENCE
# ==================================================================================================
@login_required
def liste_ordonnances_urgence(request):
    query = request.GET.get('q')
    
    # 1. Filtre strict sur le type 'URGENCE' et correction du tri avec 'date_prescrite'
    ordonnances_list = Ordonnance.objects.filter(
        type_ordonnance='URGENCE'
    ).select_related(
        'consultation__triage__patient',
        'consultation__medecin'
    ).prefetch_related(
        'medicaments'
    ).order_by('-date_prescrite')

    # 2. Recherche par nom de patient ou code patient
    if query:
        ordonnances_list = ordonnances_list.filter(
            Q(consultation__triage__patient__noms__icontains=query) |
            Q(consultation__triage__patient__code_patient__icontains=query)
        )

    # 3. Pagination à 10 éléments par page
    paginator = Paginator(ordonnances_list, 10)
    page = request.GET.get('page')
    
    try:
        ordonnances = paginator.page(page)
    except PageNotAnInteger:
        ordonnances = paginator.page(1)
    except EmptyPage:
        ordonnances = paginator.page(paginator.num_pages)

    # 4. Rôle de l'utilisateur pour la sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None
    
    context = {
        'ordonnances': ordonnances,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/liste_ordonnances_urgence.html', context)


# 33
# ==================================================================================================
# MEDECIN  ORDONNANCE D'URGENCE
# ==================================================================================================
@login_required
def prescrire_ordonnance_urgence_rapide(request, consultation_id):
    if request.method == 'POST':
        consultation = get_object_or_404(Consultation, id=consultation_id)
        observation = request.POST.get('observation')
        medicaments_text = request.POST.get('medicaments_text') # Contenu texte libre ou liste
        
        # 1. Création de l'ordonnance d'urgence
        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            type_ordonnance='URGENCE',
            observation=f"{observation} | Produits prescrits : {medicaments_text}" if medicaments_text else observation
        )
        
        messages.success(request, f"Ordonnance d'urgence #{ordonnance.id} créée avec succès pour {consultation.triage.patient.noms} !")
        
    # Redirige vers la page d'où vient l'utilisateur
    return redirect(request.META.get('HTTP_REFERER', 'liste_consultations_terminees'))

# 34
# ==================================================================================================
# RECEPTIONNISTE PAIEMENT DES EXAM
# ==================================================================================================
@login_required
def encaisser_examens_prescrits(request, consultation_id):
    # Récupération de l'objet consultation
    consultation = get_object_or_404(Consultation, id=consultation_id)
    examens = consultation.examens.all()
    
    # 1. Récupération de la configuration pour le taux (Logique conservée)
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500')
    
    # 2. Calculs financiers (Logique conservée)
    total_prescrit = examens.aggregate(total=Sum('prestation__prix'))['total'] or Decimal('0.00')
    total_verse = Paiement.objects.filter(consultation=consultation).aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_reductions = Paiement.objects.filter(consultation=consultation).aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')
    
    reste_a_payer_usd = total_prescrit - (total_verse + total_reductions)

    if request.method == 'POST':
        try:
            devise = request.POST.get('devise', 'USD')
            montant_recu = Decimal(request.POST.get('montant_verse', 0))
            reduction_usd = Decimal(request.POST.get('montant_reduction', 0))
            
            # Validation : montants négatifs
            if montant_recu < 0 or reduction_usd < 0:
                messages.error(request, "Les montants ne peuvent pas être négatifs.")
                return redirect('encaisser_examens', consultation_id=consultation.id)

            # Conversion du montant reçu en USD
            montant_verse_usd = montant_recu / taux if devise == 'CDF' else montant_recu
            total_encaisse = montant_verse_usd + reduction_usd

            # Validation : Vérification du solde avant encaissement
            if total_encaisse > reste_a_payer_usd:
                messages.error(request, f"Erreur : Le montant total ({total_encaisse:.2f} USD) dépasse le reste à payer ({reste_a_payer_usd:.2f} USD).")
                return redirect('encaisser_examens', consultation_id=consultation.id)

            # 3. Création du paiement (Logique forcée conservée)
            nouveau_reste = reste_a_payer_usd - total_encaisse
            
            Paiement.objects.create(
                patient=consultation.triage.patient,
                consultation=consultation,
                service='EXAMENS',
                montant_verse=montant_verse_usd,
                montant_reduction=reduction_usd,
                reste_a_payer=max(Decimal('0.00'), nouveau_reste),
                devise=devise,
                caissier=request.user,
                date_paiement=timezone.now()
            )

            messages.success(request, "Paiement enregistré avec succès.")
            return redirect('historique_paiements', patient_id=consultation.triage.patient.id)

        except Exception as e:
            messages.error(request, f"Une erreur technique est survenue : {str(e)}")
            return redirect('encaisser_examens', consultation_id=consultation.id)

    # Récupération des informations sur l'utilisateur pour le template (Logique conservée)
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    # Context complet avec toutes vos variables d'origine
    context = {
        'consultation': consultation,
        'reste_a_payer_usd': reste_a_payer_usd,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'examens': examens, # Ajouté : nécessaire pour afficher la liste des examens
        'total_prescrit': total_prescrit
    }
    return render(request, 'back-end/caisse/encaisser_examens.html', context)

# 35
# ==================================================================================================
# RECEPTIONNISTE PAIEMENT DES EXAM
# ==================================================================================================
@login_required
def liste_attente_caisse(request):
    taux = ConfigurationHopital.get_taux()

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    consultations_a_payer = Consultation.objects.filter(
        examens__isnull=False,
        triage__patient__hopital=hopital_user
    ).distinct().order_by('-date_creation')

    consultations_a_payer = consultations_a_payer.annotate(
        total_a_payer=Coalesce(
            Sum(F('examens__prestation__prix') * F('examens__quantite')),
            Value(0.00, output_field=DecimalField())
        ),
        total_deja_paye=Coalesce(
            Sum('paiements__montant_verse') + Sum('paiements__montant_reduction'),
            Value(0.00, output_field=DecimalField())
        )
    )

    consultations_a_payer = consultations_a_payer.annotate(
        reste_a_payer=F('total_a_payer') - F('total_deja_paye')
    )

    consultations_a_payer = consultations_a_payer.filter(reste_a_payer__gt=0)

    query = request.GET.get('q')
    if query:
        consultations_a_payer = consultations_a_payer.filter(
            Q(triage__patient__noms__icontains=query) |
            Q(triage__patient__code_patient__icontains=query)
        )

    fonctionKey = role.fonctionKey.roleName if (role and role.fonctionKey) else None

    context = {
        'consultations': consultations_a_payer,
        'fonctionKey': fonctionKey,
        'query': query
    }

    return render(request, 'back-end/caisse/liste_attente.html', context)

# 36
# ==================================================================================================
# LISTE DES EXAMENS A FAIRE 
# ==================================================================================================
@login_required
def liste_examens_techniques(request):
    role_user = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    if not role_user or not role_user.fonctionKey or not role_user.hopital:
        return redirect('dashboard')

    hopital_user = role_user.hopital
    nom_role = (role_user.fonctionKey.roleName or "").lower()
    fonctionKey = role_user.fonctionKey.roleName

    consultations = Consultation.objects.select_related(
        'triage__patient',
        'medecin'
    ).prefetch_related(
        'examens__prestation'
    ).filter(
        examens__isnull=False
    ).distinct().order_by('-date_creation')

    historique_technique = []

    for cons in consultations:
        patient = cons.triage.patient
        examens_filtrés = []

        for exam in cons.examens.all():
            if exam.hopital_id and exam.hopital_id != hopital_user.id:
                continue

            if exam.prestation and exam.prestation.hopital_id and exam.prestation.hopital_id != hopital_user.id:
                continue

            cat = str(exam.prestation.categorie).upper() if exam.prestation else ""

            if patient.type_patient == 'SIMPLE':
                paiement_examen = Paiement.objects.filter(
                    patient=patient,
                    consultation=cons,
                    service__in=['LABO', 'ECHO', 'RADIO', 'EXAMENS'],
                    montant_verse__gt=0
                ).exists()
                if not paiement_examen:
                    continue

            if ('labo' in nom_role and cat == 'LABO') or \
               (('echo' in nom_role or 'echographe' in nom_role) and cat == 'ECHO') or \
               (('radio' in nom_role or 'radiologue' in nom_role) and cat == 'RADIO') or \
               ('technicien' in nom_role):
                examens_filtrés.append({
                    'id_examen': exam.id,
                    'libelle': exam.prestation.libelle if exam.prestation else 'Examen',
                    'est_deja_fait': exam.statut == 'TERMINE'
                })

        if examens_filtrés:
            historique_technique.append({
                'consultation_id': cons.id,
                'patient': {
                    'nom': patient.noms,
                    'code': patient.code_patient,
                    'type': patient.get_type_patient_display(),
                    'genre': patient.get_sexe_display(),
                    'age': patient.age,
                    'info_financiere': (
                        "Patient simple" if patient.type_patient == "SIMPLE" else
                        "Patient fidèle" if patient.type_patient == "FIDELE" else
                        "Patient conventionné"
                    ),
                },
                'examens': examens_filtrés,
                'medecin': cons.medecin.username if cons.medecin else "Généraliste",
                'tout_traite': not any(not ex['est_deja_fait'] for ex in examens_filtrés)
            })

    return render(request, 'back-end/technique/liste_examens_payes.html', {
        'historique_technique': historique_technique,
        'examens_presents': len(historique_technique) > 0,
        'titre_page': "Examens à réaliser",
        'fonctionKey': fonctionKey
    })


# 37
# ==================================================================================================
# 
# ==================================================================================================
@login_required
def saisir_resultats_examens(request, consultation_id):
    # 1. Vérification du rôle du technicien
    role_user = Fonction.objects.filter(userKey=request.user).first()
    if not role_user or not role_user.fonctionKey:
        messages.error(request, "Accès refusé.")
        return redirect('dashboard')

    nom_role = role_user.fonctionKey.roleName.lower()
    fonctionKey = role_user.fonctionKey.roleName

    # 2. Récupération de la consultation
    consultation = get_object_or_404(Consultation, id=consultation_id)
    
    # 3. Extraction et filtrage des examens 'EN_ATTENTE' pour ce rôle précis
    examens_en_attente = consultation.examens.filter(statut='EN_ATTENTE').select_related('prestation')
    
    examens_a_saisir = []
    for exam in examens_en_attente:
        cat = exam.prestation.categorie
        # Logique de spécialisation retrouvée
        if ('labo' in nom_role or 'laborantin' in nom_role) and cat == 'LABO':
            examens_a_saisir.append(exam)
        elif ('echo' in nom_role or 'echographe' in nom_role) and cat == 'ECHO':
            examens_a_saisir.append(exam)
        elif ('radio' in nom_role or 'radiologue' in nom_role) and cat == 'RADIO':
            examens_a_saisir.append(exam)

    # Sécurité : Si accès forcé alors que rien n'est à saisir pour ce rôle
    if not examens_a_saisir:
        messages.error(request, "Aucun examen en attente de saisie pour votre spécialité.")
        return redirect('liste_examens_techniques')

    # 4. Traitement de la soumission du formulaire (POST)
    if request.method == 'POST':
        examens_traites_count = 0
        
        for exam in examens_a_saisir:
            cle_resultat = f"resultat_{exam.id}"
            texte_resultat = request.POST.get(cle_resultat, "").strip()
            
            if texte_resultat:
                exam.resultat = texte_resultat
                exam.statut = 'TERMINE'
                exam.technicien = request.user
                exam.date_realisation = timezone.now()
                exam.save()
                examens_traites_count += 1
                
        if examens_traites_count > 0:
            messages.success(request, f"Les résultats de ({examens_traites_count}) examen(s) pour {consultation.triage.patient.noms} ont été enregistrés.")
        else:
            messages.warning(request, "Aucun résultat n'a été saisi.")
            
        return redirect('liste_examens_techniques')

    context = {
        'consultation': consultation,
        'patient': consultation.triage.patient,
        'examens_a_saisir': examens_a_saisir,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/technique/saisir_resultats.html', context)

# 38
# ==================================================================================================
# DOSSIER RESULTAT PATIENT
# ==================================================================================================
@login_required
def dossier_resultats_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    # 1. Récupération de toutes les consultations du patient (de la plus récente à la plus ancienne)
    consultations = Consultation.objects.filter(triage__patient=patient).select_related('medecin').order_by('-date_creation')
    
    historique_consultations_examens = []
    
    for condultation in consultations:
        # 2. Récupération de TOUS les examens liés à CETTE consultation spécifique
        tous_les_examens = condultation.examens.select_related('prestation').all()
        
        # On sépare les examens par catégorie pour un affichage structuré dans le template
        examens_labo = []
        examens_radio = []
        examens_echo = []
        
        for exam in tous_les_examens:
            cat = exam.prestation.categorie
            if cat == 'LABO':
                examens_labo.append(exam)
            elif cat == 'RADIO':
                examens_radio.append(exam)
            elif cat == 'ECHO':
                examens_echo.append(exam)
        
        # On calcule le niveau d'avancement des examens pour cette consultation
        total_examens = tous_les_examens.count()
        examens_termines = tous_les_examens.filter(statut='TERMINE').count()
        
        # Statut global de la fiche d'examen pour le médecin
        if total_examens == 0:
            statut_global = "Aucun examen prescrit"
            classe_badge = "badge-secondary"
        elif examens_termines == total_examens:
            statut_global = "Complet (Tous les résultats sont disponibles)"
            classe_badge = "badge-success"
        elif examens_termines > 0:
            statut_global = f"Incomplet ({examens_termines}/{total_examens} disponible(s))"
            classe_badge = "badge-warning"
        else:
            statut_global = "En attente de réalisation / de paiement"
            classe_badge = "badge-danger"

        # On rassemble les informations de la consultation et ses examens cloisonnés
        historique_consultations_examens.append({
            'consultation': condultation,
            'statut_global': statut_global,
            'classe_badge': classe_badge,
            'labo': examens_labo,
            'radio': examens_radio,
            'echo': examens_echo,
            'a_des_examens': total_examens > 0
        })

    # Récupération du rôle pour la sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'patient': patient,
        'historique': historique_consultations_examens,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/dossier_resultats.html', context)


# 39
# ==================================================================================================
# 
# ==================================================================================================

@login_required
def uniquement_resultats_examens(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Récupérer toutes les consultations du patient
    consultations = Consultation.objects.filter(triage__patient=patient).order_by('-date_creation')
    
    historique_resultats = []
    
    for consult in consultations:
        # On prend UNIQUEMENT les examens terminés (avec un résultat saisi)
        examens_termines = consult.examens.filter(statut='TERMINE').select_related('prestation')
        
        if examens_termines.exists():
            historique_resultats.append({
                'consultation': consult,
                'examens': examens_termines
            })
            
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'patient': patient,
        'historique_resultats': historique_resultats,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/resultats_bruts.html', context)

# 40
# ==================================================================================================
#  FINANCE DASHBOARD
# ==================================================================================================
@login_required
def dashboard_finance(request):
    if not request.user.is_authenticated:
        return redirect('login')

    role = Fonction.objects.select_related('fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if fonctionKey != 'admin':
        messages.error(request, "Accès refusé : réservée à l'administration.")
        return redirect('home')

    maintenant = timezone.now()
    debut_aujourdhui = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    debut_semaine = debut_aujourdhui - timedelta(days=7)
    debut_mois = debut_aujourdhui.replace(day=1)

    hopital_id = request.GET.get('hopital')
    devise = request.GET.get('devise')
    service = request.GET.get('service')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    paiements_qs = Paiement.objects.select_related('patient', 'caissier', 'hopital')
    depenses_qs = Depense.objects.select_related('auteur', 'hopital')

    if hopital_id:
        paiements_qs = paiements_qs.filter(hopital_id=hopital_id)
        depenses_qs = depenses_qs.filter(hopital_id=hopital_id)

    if devise:
        paiements_qs = paiements_qs.filter(devise=devise)
        depenses_qs = depenses_qs.filter(devise=devise)

    if service:
        paiements_qs = paiements_qs.filter(service=service)

    if date_debut:
        paiements_qs = paiements_qs.filter(date_paiement__date__gte=date_debut)

    if date_fin:
        paiements_qs = paiements_qs.filter(date_paiement__date__lte=date_fin)

    total_usd = paiements_qs.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
    total_cdf = paiements_qs.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0

    depense_totale_usd = depenses_qs.filter(devise='USD').aggregate(total=Sum('montant'))['total'] or 0
    depense_totale_cdf = depenses_qs.filter(devise='CDF').aggregate(total=Sum('montant'))['total'] or 0

    restant_usd = float(total_usd) - float(depense_totale_usd)
    restant_cdf = float(total_cdf) - float(depense_totale_cdf)

    aujourdhui_usd = paiements_qs.filter(date_paiement__gte=debut_aujourdhui, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
    aujourdhui_cdf = paiements_qs.filter(date_paiement__gte=debut_aujourdhui, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0

    semaine_usd = paiements_qs.filter(date_paiement__gte=debut_semaine, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
    semaine_cdf = paiements_qs.filter(date_paiement__gte=debut_semaine, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0

    mois_usd = paiements_qs.filter(date_paiement__gte=debut_mois, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
    mois_cdf = paiements_qs.filter(date_paiement__gte=debut_mois, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0

    recettes_par_hopital = paiements_qs.values(
        'hopital__id',
        'hopital__nomH'
    ).annotate(
        total_usd=Sum('montant_verse', filter=Q(devise='USD')),
        total_cdf=Sum('montant_verse', filter=Q(devise='CDF')),
    ).order_by('hopital__nomH')

    recettes_par_hopital_par_jour = paiements_qs.annotate(
        jour=TruncDay('date_paiement')
    ).values(
        'jour',
        'hopital__id',
        'hopital__nomH'
    ).annotate(
        total_usd=Sum('montant_verse', filter=Q(devise='USD')),
        total_cdf=Sum('montant_verse', filter=Q(devise='CDF')),
    ).order_by('jour', 'hopital__nomH')

    depenses_par_hopital = depenses_qs.values(
        'hopital__id',
        'hopital__nomH'
    ).annotate(
        depenses_usd=Sum('montant', filter=Q(devise='USD')),
        depenses_cdf=Sum('montant', filter=Q(devise='CDF')),
    ).order_by('hopital__nomH')

    services_stats = []
    for code, nom_service in Paiement.SERVICES:
        usd_service = paiements_qs.filter(service=code, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
        cdf_service = paiements_qs.filter(service=code, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0
        services_stats.append({
            'code': code,
            'nom': nom_service,
            'usd': usd_service,
            'cdf': cdf_service,
        })

    tous_les_paiements = paiements_qs.order_by('-date_paiement')

    hopitaux = Paiement.objects.values('hopital__id', 'hopital__nomH').distinct().order_by('hopital__nomH')

    context = {
        'aujourdhui_usd': aujourdhui_usd,
        'aujourdhui_cdf': aujourdhui_cdf,
        'semaine_usd': semaine_usd,
        'semaine_cdf': semaine_cdf,
        'mois_usd': mois_usd,
        'mois_cdf': mois_cdf,
        'total_usd': total_usd,
        'total_cdf': total_cdf,
        'depense_totale_usd': depense_totale_usd,
        'depense_totale_cdf': depense_totale_cdf,
        'restant_usd': restant_usd,
        'restant_cdf': restant_cdf,
        'services_stats': services_stats,
        'paiements': tous_les_paiements,
        'recettes_par_hopital': recettes_par_hopital,
        'recettes_par_hopital_par_jour': recettes_par_hopital_par_jour,
        'depenses_par_hopital': depenses_par_hopital,
        'hopitaux': hopitaux,
        'fonctionKey': fonctionKey,
        'titre_page': "Journal de Caisse & Finances - JMC",
        'filtres': {
            'hopital': hopital_id or '',
            'devise': devise or '',
            'service': service or '',
            'date_debut': date_debut or '',
            'date_fin': date_fin or '',
        }
    }
    return render(request, 'back-end/finance/dashboard_finance.html', context)
# ==================================================================================================
# #41 : FINANCE GESTION DE DETTE 
# ==================================================================================================
@login_required
def creer_depense(request):
    role = Fonction.objects.select_related('fonctionKey', 'hopital').filter(userKey=request.user).first()

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user_id = role.hopital_id if role and role.hopital_id else None

    is_admin = fonctionKey in ['admin', 'Admin', 'ADMIN', 'Administrateur']

    def qs_hopital(model_qs, devise):
        qs = model_qs.filter(devise=devise)
        if not is_admin:
            if hopital_user_id:
                qs = qs.filter(hopital_id=hopital_user_id)
            else:
                qs = qs.none()
        return qs

    def solde_par_devise(devise):
        total_entrees = qs_hopital(Paiement.objects.all(), devise).aggregate(
            total=Coalesce(Sum('montant_verse'), Decimal('0.00'), output_field=DecimalField())
        )['total']

        total_sorties = qs_hopital(Depense.objects.all(), devise).aggregate(
            total=Coalesce(Sum('montant'), Decimal('0.00'), output_field=DecimalField())
        )['total']

        return total_entrees - total_sorties

    solde_disponible_usd = solde_par_devise('USD')
    solde_disponible_cdf = solde_par_devise('CDF')

    if request.method == 'POST':
        form = DepenseForm(request.POST)
        if form.is_valid():
            depense = form.save(commit=False)
            depense.auteur = request.user

            if not is_admin:
                if not hopital_user_id:
                    form.add_error(None, "Impossible de déterminer l'hôpital du gestionnaire.")
                    context = {
                        'form': form,
                        'titre_page': "Enregistrer une Sortie de Caisse",
                        'fonctionKey': fonctionKey,
                        'solde_disponible_usd': solde_disponible_usd,
                        'solde_disponible_cdf': solde_disponible_cdf,
                    }
                    return render(request, 'back-end/finance/creer_depense.html', context)
                depense.hopital_id = hopital_user_id

            try:
                depense.full_clean()
                depense.save()
                messages.success(request, "La dépense a été enregistrée avec succès !")
                return redirect('dashboard_finance_depense')

            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    for _, errors in e.message_dict.items():
                        for error in errors:
                            form.add_error(None, error)
                else:
                    for error in e.messages:
                        form.add_error(None, error)
    else:
        form = DepenseForm()

    context = {
        'form': form,
        'titre_page': "Enregistrer une Sortie de Caisse",
        'fonctionKey': fonctionKey,
        'solde_disponible_usd': solde_disponible_usd,
        'solde_disponible_cdf': solde_disponible_cdf,
    }
    return render(request, 'back-end/finance/creer_depense.html', context)

# ==================================================================================================
# 42 : FINANCE GESTION DE DETTE  JOURNAL
# ==================================================================================================
@login_required
def dashboard_finance_depense(request):
    """
    Tableau de bord financier : Journal des entrées,
    statistiques temporelles et bilan global du coffre (USD / CDF).
    """
    role = Fonction.objects.select_related('fonctionKey', 'hopital').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role and hasattr(role, 'hopital') else None

    maintenant = timezone.now()
    debut_aujourdhui = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    debut_semaine = debut_aujourdhui - timezone.timedelta(days=maintenant.weekday())
    debut_mois = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    zero_decimal = Decimal('0.00')

    paiements_qs = Paiement.objects.all().order_by('-date_paiement')
    depenses_qs = Depense.objects.all()

    if fonctionKey != 'admin':
        if hopital_user:
            paiements_qs = paiements_qs.filter(hopital=hopital_user)
            depenses_qs = depenses_qs.filter(hopital=hopital_user)
        else:
            paiements_qs = paiements_qs.none()
            depenses_qs = depenses_qs.none()

    recettes_stats = paiements_qs.aggregate(
        auj_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='USD')), zero_decimal, output_field=DecimalField()),
        auj_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='CDF')), zero_decimal, output_field=DecimalField()),
        sem_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='USD')), zero_decimal, output_field=DecimalField()),
        sem_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='CDF')), zero_decimal, output_field=DecimalField()),
        mois_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='USD')), zero_decimal, output_field=DecimalField()),
        mois_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='CDF')), zero_decimal, output_field=DecimalField()),
    )

    total_entrees = paiements_qs.aggregate(
        usd=Coalesce(Sum('montant_verse', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant_verse', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    total_depenses = depenses_qs.aggregate(
        usd=Coalesce(Sum('montant', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    restant_usd = total_entrees['usd'] - total_depenses['usd']
    restant_cdf = total_entrees['cdf'] - total_depenses['cdf']

    services_liste = ['FICHE', 'LABO', 'ECHOGRAPHIE', 'RADIO']
    services_stats = []
    for s in services_liste:
        s_usd = paiements_qs.filter(service=s, devise='USD').aggregate(
            t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField())
        )['t']
        s_cdf = paiements_qs.filter(service=s, devise='CDF').aggregate(
            t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField())
        )['t']
        services_stats.append({'nom': s, 'usd': s_usd, 'cdf': s_cdf})

    context = {
        'titre_page': "Journal Général de Caisse",
        'fonctionKey': fonctionKey,
        'paiements': paiements_qs,
        'aujourdhui_usd': recettes_stats['auj_usd'],
        'aujourdhui_cdf': recettes_stats['auj_cdf'],
        'semaine_usd': recettes_stats['sem_usd'],
        'semaine_cdf': recettes_stats['sem_cdf'],
        'mois_usd': recettes_stats['mois_usd'],
        'mois_cdf': recettes_stats['mois_cdf'],
        'total_usd': total_entrees['usd'],
        'total_cdf': total_entrees['cdf'],
        'depense_totale_usd': total_depenses['usd'],
        'depense_totale_cdf': total_depenses['cdf'],
        'restant_usd': restant_usd,
        'restant_cdf': restant_cdf,
        'services_stats': services_stats,
    }
    return render(request, 'back-end/finance/journal_caisse.html', context)
# ==================================================================================================
# 43 : RESULTAT DU LABO RADIO ET ECHO PAR LE MEDECIN
# ==================================================================================================
@login_required
def liste_attente_ordonnance_view(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if request.method == 'POST' and request.POST.get('action') == 'enregistrer_ordonnance':
        consultation_id = request.POST.get('consultation_id')
        diagnostic = request.POST.get('diagnostic_final')
        type_ord = request.POST.get('type_ordonnance')

        destination = request.POST.get('destination')
        observation_orient = request.POST.get('observation_orientation')

        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        consultation = Consultation.objects.filter(
            id=consultation_id,
            triage__patient__hopital=hopital_user
        ).first()

        if consultation:
            try:
                with transaction.atomic():
                    consultation.diagnostic_final = diagnostic
                    consultation.save()

                    ordonnance = Ordonnance.objects.create(
                        consultation=consultation,
                        type_ordonnance=type_ord
                    )

                    for nom, pos, dur in zip(noms, posologies, durees):
                        if nom.strip():
                            Medicament.objects.create(
                                ordonnance=ordonnance,
                                nom=nom,
                                posologie=pos,
                                duree=dur
                            )

                    if destination:
                        if destination == 'Hospitalisation':
                            lit_id = request.POST.get('lit_id')
                            date_entree = request.POST.get('date_entree')
                            motif_admission = request.POST.get('motif_admission')

                            if lit_id:
                                Hospitalisation.objects.create(
                                    patient=consultation.triage.patient,
                                    lit_id=lit_id,
                                    hopital=hopital_user,
                                    date_entree=date_entree if date_entree else timezone.now(),
                                    motif_admission=motif_admission if motif_admission else diagnostic,
                                    statut='EN_COURS'
                                )

                        Orientation.objects.create(
                            consultation=consultation,
                            medecin_orientateur=request.user,
                            destination=destination,
                            observation=observation_orient,
                            est_admis=False
                        )

                    messages.success(request, "Traitement complet effectué avec succès.")
            except Exception as e:
                messages.error(request, f"Erreur critique : {str(e)}")

        return redirect('liste_attente_medecin')

    consultations_en_attente = Consultation.objects.filter(
        examens__statut='TERMINE',
        triage__patient__hopital=hopital_user
    ).prefetch_related('examens', 'ordonnance_set').distinct()

    lits_disponibles = Lit.objects.filter(
        est_occupe=False,
        hopital=hopital_user
    )

    return render(request, 'back-end/medecin/liste_attente.html', {
        'consultations_en_attente': consultations_en_attente,
        'lits_disponibles': lits_disponibles,
        'fonctionKey': fonctionKey,
        'now': timezone.now()
    })
 
# ==================================================================================================
# 44 : RESULTAT HISTORIQUE SOIT LABO , RADIO OU ECHO
# ==================================================================================================
@login_required
def historique_examens_view(request):
    """
    Vue pour afficher l'historique de tous les examens terminés dans Moyanoli avec pagination.
    """
    # 1. Récupération et optimisation du QuerySet de base
    examens_liste = DemandeExamen.objects.filter(
        statut='TERMINE'
    ).select_related(
        'consultation__triage__patient',  # Accès direct aux infos du patient
        'prestation',                     # Accès au prix et libellé de l'examen
        'technicien'                      # Accès à l'utilisateur qui a fait l'examen
    ).prefetch_related(
        'technicien__user_fonction__fonctionKey'  # Récupère la fonction et le rôle associé
    ).order_by('-date_realisation')

    # 2. Configuration de la pagination (ex: 10 examens par page)
    elements_par_page = 10
    paginator = Paginator(examens_liste, elements_par_page)
    
    # 3. Récupération du numéro de la page actuelle depuis l'URL (?page=...)
    page_number = request.GET.get('page')
    
    try:
        historique_examens = paginator.get_page(page_number)
    except PageNotAnInteger:
        # Si le paramètre page n'est pas un entier, on renvoie la première page
        historique_examens = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, on renvoie la dernière page de résultats
        historique_examens = paginator.page(paginator.num_pages)

    # 4. Gestion des rôles utilisateur
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    context = {
        'historique_examens': historique_examens,  # Cet objet contient maintenant les méthodes de pagination (.has_next, etc.)
        'fonctionKey': fonctionKey
    }
    
    return render(request, 'back-end/examens/historique.html', context)

# ==================================================================================================
# 45 : GESTION HOPITALISATION
# ==================================================================================================

# --------------------------------------------------------------------------------------------------
# VUE : Vue principale agissant comme tableau de bord pour piloter les infrastructures physiques.
# FONCTION : Récupère toutes les chambres (avec jointures optimisées), calcule les statistiques 
#            d'occupation globales en temps réel et génère l'affichage du plan des salles.
# --------------------------------------------------------------------------------------------------
@login_required
def dashboard_chambres(request):
    """ Affichage global de la situation des chambres, prix et lits """
    
    # 1. Récupération des chambres avec jointures optimisées
    chambres = Chambre.objects.all().select_related('type_chambre').prefetch_related('lits')

    # 2. Gestion des rôles utilisateur
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey').first()
    fonctionKey = role.fonctionKey.roleName if role else None

    # 3. Statistiques globales en UNE SEULE requête SQL (Agrégation)
    # Cela évite de solliciter la base de données plusieurs fois inutilement.
    stats = Lit.objects.aggregate(
        total_lits=Count('id', filter=Q(est_actif=True)),
        lits_occupes=Count('id', filter=Q(est_occupe=True, est_actif=True)),
        lits_disponibles=Count('id', filter=Q(est_occupe=False, est_actif=True))
    )

    context = {
        'fonctionKey': fonctionKey,
        'chambres': chambres,
        'total_chambres': chambres.filter(est_active=True).count(),
        'total_lits': stats['total_lits'],
        'lits_occupes': stats['lits_occupes'],
        'lits_disponibles': stats['lits_disponibles'],
    }
    
    return render(request, 'back-end/hospitalisation/dashboard_chambres.html', context)


# --------------------------------------------------------------------------------------------------
# VUE : Première étape de la configuration de l'infrastructure de soins.
# FONCTION : Permet d'enregistrer une nouvelle catégorie de tarification ou de destination médicale 
#            (ex: VIP, Soins Intensifs, Pédiatrie) avant de pouvoir y affecter des locaux.
# --------------------------------------------------------------------------------------------------
@login_required
def ajouter_type_chambre(request):
    """ Étape 1 : Enregistrer une catégorie (VIP, Commune, etc.) """
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        form = TypeChambreForm(request.POST)
        if form.is_valid():
            type_chambre = form.save(commit=False)
            type_chambre.hopital = hopital_user
            type_chambre.save()
            messages.success(request, f"Le type de chambre '{type_chambre.libelle}' a été enregistré.")
            return redirect('ajouter_chambre')
    else:
        form = TypeChambreForm()

    return render(request, 'back-end/hospitalisation/type_chambre_form.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })

# --------------------------------------------------------------------------------------------------
# VUE : Deuxième étape de la configuration de l'infrastructure de soins.
# FONCTION : Gère l'enregistrement des chambres physiques et de leurs prix par nuitée. Elle bloque
#            l'accès et réoriente l'utilisateur vers l'étape 1 si aucune catégorie n'existe en base.
# --------------------------------------------------------------------------------------------------
@login_required
def ajouter_chambre(request):
    """ Étape 2 : Enregistrer une chambre physique """
    if not TypeChambre.objects.exists():
        messages.warning(request, "Vous devez d'abord créer un Type de chambre avant d'ajouter une chambre.")
        return redirect('ajouter_type_chambre')

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        form = ChambreForm(request.POST)
        if form.is_valid():
            chambre = form.save(commit=False)
            chambre.hopital = hopital_user
            chambre.save()
            messages.success(request, f"La chambre {chambre.nom} a été enregistrée.")
            return redirect('ajouter_lit')
    else:
        form = ChambreForm()

    return render(request, 'back-end/hospitalisation/chambre_form.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })


# --------------------------------------------------------------------------------------------------
# VUE : Troisième et dernière étape de la configuration de l'infrastructure.
# FONCTION : Ajoute les unités d'accueil individuelles (Lits) dans les chambres. Gère la double 
#            possibilité de valider la saisie ou d'enchaîner sur un enregistrement en série.
# --------------------------------------------------------------------------------------------------
@login_required
def ajouter_lit(request):
    """ Étape 3 : Enregistrer un lit dans une chambre """
    if not Chambre.objects.exists():
        messages.warning(request, "Vous devez d'abord créer une chambre avant d'y ajouter des lits.")
        return redirect('ajouter_chambre')

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        form = LitForm(request.POST)
        form.fields['chambre'].queryset = Chambre.objects.filter(hopital=hopital_user)

        if form.is_valid():
            lit = form.save(commit=False)
            lit.hopital = hopital_user
            lit.save()

            messages.success(request, f"Le lit '{lit.nom_lit}' a bien été ajouté à la {lit.chambre}.")
            if 'ajouter_autre' in request.POST:
                return redirect('ajouter_lit')
            return redirect('dashboard_chambres')
    else:
        form = LitForm()
        form.fields['chambre'].queryset = Chambre.objects.filter(hopital=hopital_user)

    return render(request, 'back-end/hospitalisation/lit_form.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })

# --------------------------------------------------------------------------------------------------
# VUE : Point d'entrée d'action unitaire et asynchrone (ou par redirection directe).
# FONCTION : Permet aux infirmiers ou gestionnaires d'annuler une occupation ou de bloquer temporairement
#            un lit à la volée depuis l'interface visuelle sans passer par un formulaire d'édition complet.
# --------------------------------------------------------------------------------------------------
@login_required
def toggle_statut_lit(request, lit_id):
    """ Action rapide pour occuper/libérer un lit depuis le dashboard """
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    lit = get_object_or_404(Lit, id=lit_id, hopital=hopital_user)

    lit.est_occupe = not lit.est_occupe
    lit.save()

    messages.info(request, f"Le statut du lit {lit.nom_lit} a été modifié.")
    return redirect('dashboard_chambres')


# =====================================================================================================
# REDIGE ORDONNANCE
# =====================================================================================================
@login_required
def enregistrer_ordonnance_view(request, triage_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    triage = get_object_or_404(SigneVital, id=triage_id, patient__hopital=hopital_user)
    consultation = get_object_or_404(Consultation, triage=triage, hopital=hopital_user)

    examens_termines = DemandeExamen.objects.filter(
        consultation=consultation,
        statut='TERMINE',
        hopital=hopital_user
    ).select_related('prestation')

    if request.method == 'POST':
        form = OrdonnanceForm(request.POST)
        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        if form.is_valid():
            try:
                with transaction.atomic():
                    ordonnance = form.save(commit=False)
                    ordonnance.consultation = consultation
                    ordonnance.hopital = hopital_user
                    ordonnance.save()

                    for n, p, d in zip(noms, posologies, durees):
                        if n.strip():
                            LigneMedicament.objects.create(
                                ordonnance=ordonnance,
                                nom_medicament=n,
                                posologie=p,
                                duree=d,
                                hopital=hopital_user
                            )

                    triage.est_consulte = True
                    triage.save()

                    messages.success(request, "Ordonnance enregistrée avec succès !")
                    return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"Erreur base de données : {e}")
        else:
            messages.error(request, "Formulaire invalide.")

    return render(request, 'back-end/medecin/enregistrer_ordonnance.html', {
        'consultation': consultation,
        'examens_termines': examens_termines,
        'form': OrdonnanceForm()
    })
#
# ===========================================================================================
# LISTE ORDONNANCE COTE MEDECIN
# ============================================================================================
@login_required
def liste_ordonnances_delivrees_view(request):
    """
    Affiche la liste des ordonnances (Modèle Ordonnance) prescrites par le médecin.
    Permet également de stopper un médicament spécifique.
    """

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'stopper_medicament':
            ligne_id = request.POST.get('ligne_id')
            motif = request.POST.get('motif_arret', 'Arrêté par le médecin')

            if ligne_id and ligne_id.isdigit():
                ligne = LigneMedicament.objects.filter(id=int(ligne_id), hopital=hopital_user).first()
                if ligne:
                    ligne.statut = 'STOPPE'
                    ligne.motif_arret = motif
                    ligne.date_modification = timezone.now()
                    ligne.save()
                    messages.warning(request, f"Le médicament '{ligne.nom_medicament}' a été stoppé.")
            return redirect(request.path_info)

    ordonnances_medecin = Ordonnance.objects.select_related(
        'consultation__triage__patient'
    ).prefetch_related(
        'medicaments'
    ).filter(
        hopital=hopital_user
    ).order_by('-date_prescrite')

    context = {
        'ordonnances_medecin': ordonnances_medecin,
        'fonctionKey': fonctionKey
    }

    return render(request, 'back-end/medecin/liste_ordonnances_delivrees.html', context)
#
# ===========================================================================================
# LISTE ORDONNANCE COTE MEDECIN
# ============================================================================================
@login_required
def liste_ordonnances_prescrites_view(request):
    # Récupération optimisée avec le bon related_name 'medicaments'
    ordonnances = Ordonnance.objects.filter(type_ordonnance='DEFINITIVE').select_related(
        'consultation__triage__patient', 
        'consultation__medecin' 
    ).prefetch_related(
        'medicaments', # <--- CORRIGÉ ICI
        'consultation__examens__prestation',
        'consultation__examens__technicien'
    ).order_by('-id')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'ordonnances': ordonnances, 
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/liste_ordonnances.html', context)

#
# ===========================================================================================
# HOSPITALISE PATIENT 
# ============================================================================================
@login_required
def admettre_patient(request):
    fonctionKey = None
    role = None
    hopital_user = None

    if request.user.is_authenticated:
        role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
        if role and role.fonctionKey:
            fonctionKey = role.fonctionKey.roleName
        if role:
            hopital_user = role.hopital

    if request.method == 'POST':
        form = HospitalisationForm(request.POST)
        form.fields['patient'].queryset = Patient.objects.filter(hopital=hopital_user)
        form.fields['lit'].queryset = Lit.objects.filter(hopital=hopital_user, est_occupe=False)

        if form.is_valid():
            patient = form.cleaned_data.get('patient')

            if not patient.fiche_payee:
                messages.error(request, "Impossible d'admettre ce patient : fiche non payée.")
                return render(request, 'back-end/hospitalisation/admettre.html', {
                    'form': form,
                    'fonctionKey': fonctionKey
                })

            try:
                hospitalisation = form.save(commit=False)
                hospitalisation.hopital = hopital_user
                hospitalisation.save()
                messages.success(request, "Admission réussie et lit réservé.")
                return redirect('liste_hospitalisations')
            except Exception as e:
                messages.error(request, f"Une erreur est survenue lors de l'enregistrement : {str(e)}")
        else:
            messages.error(request, "Erreur lors de l'admission. Veuillez vérifier les champs du formulaire.")
    else:
        form = HospitalisationForm()
        form.fields['patient'].queryset = Patient.objects.filter(hopital=hopital_user)
        form.fields['lit'].queryset = Lit.objects.filter(hopital=hopital_user, est_occupe=False)

    return render(request, 'back-end/hospitalisation/admettre.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })
#
# ===========================================================================================
# LISTE DES PATIENT HOSPITALISE
# ============================================================================================
@login_required
def liste_hospitalisations(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    hospitalisations = Hospitalisation.objects.select_related(
        'patient',
        'lit__chambre__type_chambre'
    ).prefetch_related(
        'paiements'
    ).filter(
        hopital=hopital_user
    ).order_by('-date_entree')

    return render(request, 'back-end/hospitalisation/liste_hospitalisations.html', {
        'hospitalisations': hospitalisations,
        'fonctionKey': fonctionKey
    })
#
# =====================================================================================================
# PAIEMENT DE L'HOSPITALISATION
# =====================================================================================================
@login_required
def enregistrer_paiement_hospitalisation(request, hosp_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

    if hosp.statut != 'EN_COURS':
        messages.warning(request, "Cette hospitalisation est déjà clôturée ou annulée.")
        return redirect('liste_hospitalisations')

    if request.method == 'POST':
        try:
            try:
                montant_brut = Decimal(request.POST.get('montant_verse', '0'))
                reduction = Decimal(request.POST.get('montant_reduction', '0'))
            except (InvalidOperation, ValueError):
                messages.error(request, "Veuillez saisir des montants valides.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            if montant_brut < 0 or reduction < 0:
                messages.error(request, "Les montants ne peuvent pas être négatifs.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            if montant_brut == 0 and reduction == 0:
                messages.error(request, "Veuillez saisir un montant ou une réduction.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            devise = request.POST.get('devise', 'USD')

            montant_verse_usd = montant_brut
            reduction_usd = reduction
            if devise == 'CDF':
                taux = ConfigurationHopital.get_taux()
                if not taux or taux <= 0:
                    raise ValueError("Taux de change non configuré ou invalide.")
                montant_verse_usd = montant_brut / Decimal(str(taux))
                reduction_usd = reduction / Decimal(str(taux))

            reste_actuel = hosp.get_reste_a_payer()
            total_paye_ce_coup_ci = montant_verse_usd + reduction_usd

            if total_paye_ce_coup_ci > (reste_actuel + Decimal('0.01')):
                messages.error(request, f"Le montant saisi dépasse le solde restant ({reste_actuel:.2f} USD).")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            Paiement.objects.create(
                hospitalisation=hosp,
                patient=hosp.patient,
                service='HOSPITALISATION',
                montant_verse=montant_verse_usd,
                montant_reduction=reduction_usd,
                devise=devise,
                caissier=request.user,
                hopital=hopital_user
            )

            nouveau_reste = hosp.get_reste_a_payer()
            if nouveau_reste <= 0:
                hosp.statut = 'TERMINE'
                hosp.date_sortie = timezone.now()
                hosp.est_payee = True
                hosp.save()
                messages.success(request, "Paiement complet : Patient libéré, lit disponible.")
            else:
                messages.success(request, "Paiement partiel enregistré avec succès.")

            return redirect('liste_hospitalisations')

        except Exception as e:
            messages.error(request, f"Erreur critique lors du paiement : {str(e)}")
            return redirect('payer_hospitalisation', hosp_id=hosp.id)

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/hospitalisation/paiement_hosp.html', {
        'hosp': hosp,
        'reste_a_payer': hosp.get_reste_a_payer(),
        'fonctionKey': fonctionKey
    })




#
# ===========================================================================================
# DOSSIER MEDICALE
# ============================================================================================
@login_required
def dossier_medical_complet(request, patient_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user)

    if not patient.fiche_payee:
        messages.error(request, "Accès refusé.")
        return redirect('liste_patients')

    historique_consultations = Consultation.objects.filter(
        triage__patient=patient,
        hopital=hopital_user
    ).order_by('-date_creation').prefetch_related(
        'examens__prestation',
        'ordonnance_set__medicaments'
    ).select_related('triage', 'medecin')

    hospitalisations = Hospitalisation.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_entree')

    signes_vitaux = SigneVital.objects.filter(
        patient=patient
    ).order_by('-date_prelevement')

    context = {
        'patient': patient,
        'consultations': historique_consultations,
        'hospitalisations': hospitalisations,
        'signes_vitaux': signes_vitaux,
        'fonctionKey': fonctionKey
    }

    return render(request, 'back-end/patient/dossier_medical.html', context)

#
# ===========================================================================================
# DETAIL HOSPITALIERE
# ============================================================================================
@login_required
def detail_hospitalisation(request, pk):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    hosp = get_object_or_404(
        Hospitalisation.objects.select_related(
            'patient',
            'lit__chambre__type_chambre'
        ),
        pk=pk,
        hopital=hopital_user
    )

    date_debut = hosp.date_entree.date()
    demain = timezone.now().date() + timedelta(days=1)

    jours = []
    curr = date_debut
    while curr <= demain:
        jours.append(curr)
        curr += timedelta(days=1)

    ordonnances = Ordonnance.objects.filter(
        consultation__triage__patient=hosp.patient,
        hopital=hopital_user
    ).prefetch_related('medicaments').order_by('-date_prescrite')

    kardex_items = Kardex.objects.filter(
        hospitalisation=hosp,
        hopital=hopital_user
    ).prefetch_related('administrations').order_by('-id')

    kardex_data = []
    for item in kardex_items:
        admins = {a.date_admin: a for a in item.administrations.all()}
        row = {
            'id': item.id,
            'medicament': item.medicament,
            'posologie': item.posologie,
            'est_actif': item.est_actif,
            'cellules': [{'date': jour, 'admin': admins.get(jour)} for jour in jours]
        }
        kardex_data.append(row)

    suivis_list = hosp.suivis_journaliers.all().order_by('-date_suivi')
    paginator = Paginator(suivis_list, 5)
    page_number = request.GET.get('page')
    suivis = paginator.get_page(page_number)

    return render(request, 'back-end/hospitalisation/detail.html', {
        'hosp': hosp,
        'ordonnances': ordonnances,
        'kardex_data': kardex_data,
        'suivis': suivis,
        'fonctionKey': fonctionKey,
        'jours': jours,
    })

# ===========================================================================================
@login_required
def changer_statut_kardex(request, kardex_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        item = get_object_or_404(
            Kardex.objects.select_related('hospitalisation'),
            id=kardex_id,
            hopital=hopital_user
        )

        item.est_actif = not item.est_actif
        item.save()

        return redirect('detail_hospitalisation', pk=item.hospitalisation.id)

    return redirect('liste_hospitalisations')

#
# ===========================================================================================
# ADD SUIVI PAR L'INFIRMIER  
# ============================================================================================
@login_required
def ajouter_suivi(request, pk):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if fonctionKey not in ['infirmier', 'medecin', 'admin']:
        messages.error(request, "Accès refusé : vous n'êtes pas autorisé à modifier le suivi.")
        return redirect('detail_hospitalisation', pk=pk)

    if request.method == 'POST':
        hosp = get_object_or_404(Hospitalisation, pk=pk, hopital=hopital_user)

        ta_val = request.POST.get('ta')
        pouls_val = request.POST.get('pouls')
        temp_val = request.POST.get('temp')
        etat = request.POST.get('etat_general')
        soins = request.POST.get('soins_effectues', '')

        if all([ta_val, pouls_val, temp_val, etat]):
            try:
                synthese = f"TA: {ta_val} | Pouls: {pouls_val} | Temp: {temp_val}°C"

                SuiviQuotidien.objects.create(
                    hospitalisation=hosp,
                    infirmier=request.user,
                    ta=ta_val,
                    pouls=pouls_val,
                    temp=temp_val,
                    etat_general=etat,
                    constantes_du_jour=synthese,
                    soins_effectues=soins,
                    hopital=hopital_user
                )

                messages.success(request, "Le suivi quotidien a été enregistré avec succès.")
            except Exception as e:
                messages.error(request, f"Une erreur technique est survenue : {e}")
        else:
            messages.error(request, "Erreur : Veuillez remplir tous les champs obligatoires (TA, Pouls, Temp, État).")

        return redirect('detail_hospitalisation', pk=pk)

    return redirect('detail_hospitalisation', pk=pk)
#
# ============================================================================================
# KARDEX (FICHE DE TRAITEMENT)
# ============================================================================================
@login_required
def ajouter_kardex(request, hosp_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

    if not hosp.est_actif:
        messages.error(request, "Impossible d'ajouter un traitement : hospitalisation terminée.")
        return redirect('detail_hospitalisation', pk=hosp.id)

    if request.method == 'POST':
        medicament = request.POST.get('medicament')
        posologie = request.POST.get('posologie')
        voie = request.POST.get('voie')

        if medicament and posologie:
            with transaction.atomic():
                nouveau_kardex = Kardex.objects.create(
                    hospitalisation=hosp,
                    medicament=medicament,
                    posologie=posologie,
                    voie_administration=voie,
                    est_actif=True,
                    hopital=hopital_user
                )

                AdministrationKardex.objects.create(
                    kardex=nouveau_kardex,
                    date_admin=timezone.now().date(),
                    matin=False,
                    midi=False,
                    soir=False,
                    hopital=hopital_user
                )

            messages.success(request, "Médicament ajouté au Kardex.")
        else:
            messages.warning(request, "Champs manquants.")

    return redirect('detail_hospitalisation', pk=hosp.id)
#
# ========================================================================================
# ADMINISTRE LE KARDEX
# ========================================================================================
@login_required
def marquer_administration(request, kardex_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        kardex_item = get_object_or_404(
            Kardex,
            id=kardex_id,
            hopital=hopital_user
        )

        date_str = request.POST.get('date_cible')
        try:
            date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return redirect('detail_hospitalisation', pk=kardex_item.hospitalisation.id)

        admin, created = AdministrationKardex.objects.get_or_create(
            kardex=kardex_item,
            date_admin=date_cible,
            defaults={'hopital': hopital_user}
        )

        admin.matin = 'matin' in request.POST
        admin.midi = 'midi' in request.POST
        admin.soir = 'soir' in request.POST
        if hasattr(admin, 'hopital') and admin.hopital is None:
            admin.hopital = hopital_user
        admin.save()

        return redirect('detail_hospitalisation', pk=kardex_item.hospitalisation.id)

    return redirect('liste_hospitalisations')
# 
# ===========================================================================================
#   GESTION DES RENDEZ-VOUS
# ===========================================================================================
@login_required
def creer_rendez_vous(request, hosp_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

    if fonctionKey not in ['medecin', 'admin']:
        messages.error(request, "Accès refusé.")
        return redirect('detail_hospitalisation', pk=hosp.id)

    if request.method == 'POST':
        date_rdv = request.POST.get('date_rdv')
        motif = request.POST.get('motif')
        note = request.POST.get('note')

        if date_rdv and motif:
            if RendezVous.objects.filter(hospitalisation=hosp).exists():
                messages.warning(request, "Un rendez-vous est déjà planifié pour cette hospitalisation.")
                return redirect('creer_ordonnance_sortie', hosp_id=hosp.id)

            RendezVous.objects.create(
                hospitalisation=hosp,
                date_rdv=date_rdv,
                motif=motif,
                note=note,
                enregistre_par=request.user,
                hopital=hopital_user
            )
            messages.success(request, "Rendez-vous enregistré avec succès.")
            return redirect('creer_ordonnance_sortie', hosp_id=hosp.id)
        else:
            messages.error(request, "Veuillez remplir la date et le motif.")

    return render(request, 'back-end/hospitalisation/creer_rdv.html', {
        'hosp': hosp,
        'fonctionKey': fonctionKey
    }) 
#
# ===============================================================================================
# ORDONNANCE DE SORTIE 
# ===============================================================================================
@login_required
def creer_ordonnance_sortie(request, hosp_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

    if request.method == 'POST':
        ordonnance = Ordonnance.objects.create(
            hospitalisation=hosp,
            type_ordonnance='SORTIE',
            contenu=request.POST.get('contenu'),
            hopital=hopital_user
        )
        return redirect('dossier_patient', hosp_id=hosp.id)

    return render(request, 'back-end/hospitalisation/creer_ordonnance.html', {
        'hosp': hosp,
        'fonctionKey': fonctionKey
    })

#
# ===========================================================================================
# LISTE DE RENDEZ-VOUS
# ===========================================================================================
@login_required
def liste_rendez_vous(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    rendez_vous = RendezVous.objects.filter(
        hopital=hopital_user
    ).order_by('date_rdv')

    return render(request, 'back-end/hospitalisation/liste_rdv.html', {
        'rendez_vous': rendez_vous,
        'maintenant': timezone.now(),
        'fonctionKey': fonctionKey
    })

#
# ============================================================================================
# LISTE ORDONNANCE DE SORTIE 
# ============================================================================================
@login_required
def liste_ordonnances_sortie(request):
    # Récupère toutes les ordonnances, en pré-chargeant l'hospitalisation pour optimiser la base
    ordonnances = OrdonnanceSortie.objects.select_related('hospitalisation__patient').all().order_by('-date_creation')
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/hospitalisation/liste_ordonnances_sortie.html', {
        'ordonnances': ordonnances , 
        'fonctionKey' : fonctionKey
    })

#
# ============================================================================================
# MODIFIER KARDEX
# ============================================================================================
@login_required
def update_kardex(request, kardex_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    item = get_object_or_404(
        Kardex,
        id=kardex_id,
        hospitalisation__hopital=hopital_user
    )

    if request.method == 'POST':
        if 'stop_traitement' in request.POST:
            item.est_actif = False
            item.save()
        else:
            item.matin = 'matin' in request.POST
            item.midi = 'midi' in request.POST
            item.soir = 'soir' in request.POST
            item.save()

    return redirect('detail_hospitalisation', pk=item.hospitalisation.id)
#
# ============================================================================================
# METTRE FIN AU TRAITEMENT
# ============================================================================================
@login_required
def finir_hospitalisation(request, hosp_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

        hosp.est_actif = False
        hosp.date_fin = timezone.now()
        hosp.save()

    return redirect('detail_hospitalisation', pk=hosp_id)

#
# ============================================================================================
# IMPRIMER ORDONNANCE 
# ============================================================================================
@login_required
def imprimer_ordonnance(request, ordonnance_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__triage__patient',
            'consultation__medecin'
        ).prefetch_related(
            'medicaments'
        ),
        id=ordonnance_id,
        hopital=hopital_user
    )

    context = {'ord': ordonnance}
    return render(request, 'back-end/imprimer/print_ordonnance.html', context)


#
# ===========================================================================================
# CREE UN ORDONNANCE
# ============================================================================================
@login_required
def creer_ordonnance_view(request, consultation_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    consultation = get_object_or_404(Consultation, id=consultation_id, hopital=hopital_user)

    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic_final')
        contenu = request.POST.get('contenu_ordonnance')
        type_ord = request.POST.get('type_ordonnance')

        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        try:
            with transaction.atomic():
                consultation.diagnostic_final = diagnostic
                consultation.save()

                ordonnance = Ordonnance.objects.create(
                    consultation=consultation,
                    observation=contenu,
                    type_ordonnance=type_ord,
                    hopital=hopital_user
                )

                for nom, pos, dur in zip(noms, posologies, durees):
                    if nom.strip():
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom,
                            posologie=pos,
                            duree=dur,
                            hopital=hopital_user
                        )

            messages.success(request, f"Ordonnance créée pour {consultation.triage.patient.noms}.")
            return redirect('liste_attente_medecin')

        except Exception as e:
            messages.error(request, f"Une erreur est survenue : {str(e)}")

    return render(request, 'back-end/medecin/creer_ordonnance.html', {
        'c': consultation,
        'fonctionKey': fonctionKey
    }) 



#
# ======================================================================================
# ENREGISTREMENT DE L'ENTREPRISE
# ======================================================================================
@login_required
def enregistrer_entreprise_view(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        form = EntrepriseForm(request.POST)
        if form.is_valid():
            entreprise = form.save(commit=False)
            entreprise.hopital = user_hopital
            entreprise.save()
            messages.success(request, "L'entreprise a été enregistrée avec succès.")
            return redirect('liste_entreprises')
    else:
        form = EntrepriseForm()

    return render(request, 'back-end/entreprise/enregistrer_entreprise.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })

#
# ======================================================================================
# LISTE DES ENTREPRISES
# ======================================================================================
@login_required
def liste_entreprises_view(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    entreprises = Entreprise.objects.all()

    if fonctionKey != 'admin' and user_hopital:
        entreprises = entreprises.filter(hopital=user_hopital)

    entreprises = entreprises.order_by('-date_enregistrement')

    return render(request, 'back-end/entreprise/liste_entreprises.html', {
        'entreprises': entreprises,
        'fonctionKey': fonctionKey
    })




#
# ======================================================================================
# MEDECIN ORDONNANCE D'URGENCES
# ======================================================================================
@login_required
def enregistrer_ordonnance_urgence(request, consultation_id):
    # On récupère la consultation par son ID
    consultation = get_object_or_404(Consultation, pk=consultation_id)
    patient = consultation.patient  # grâce à la propriété définie dans ton modèle

    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic')
        observation = request.POST.get('observation')

        noms = request.POST.getlist('nom')
        posologies = request.POST.getlist('posologie')
        durees = request.POST.getlist('duree')

        with transaction.atomic():
            # Création de l’ordonnance liée à la consultation existante
            ordonnance = Ordonnance.objects.create(
                consultation=consultation,
                type_ordonnance='URGENCE',
                diagnostic=diagnostic,
                observation=observation
            )

            # Ajout des médicaments
            for i in range(len(noms)):
                if noms[i]:
                    Medicament.objects.create(
                        ordonnance=ordonnance,
                        nom=noms[i],
                        posologie=posologies[i],
                        duree=durees[i]
                    )

        # Redirection vers la fiche patient après enregistrement
        #return redirect('detail_patient', pk=patient.pk)

    # Récupération du rôle utilisateur pour l’affichage
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/creer_ordonnance_urgence.html', {
        'patient': patient,
        'consultation': consultation,
        'fonctionKey': fonctionKey
    })



#
# ======================================================================================
#  PATIENT PAR LE MEDECIN POUR ORDONNANCE D'URGENCE
# ======================================================================================
@login_required
def liste_patients_urgence(request):
    # 1. On filtre pour ne garder QUE les patients dont fiche_payee est True
    patients = Patient.objects.filter(fiche_payee=True).order_by('-id')
    
    # 2. Récupération du rôle
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 3. Enrichissement
    for p in patients:
        # Consultation la plus récente
        p.consultation_active = Consultation.objects.filter(
            triage__patient=p
        ).order_by('-date_creation').first()
        
        # Hospitalisation en cours
        p.hosp_en_cours = Hospitalisation.objects.filter(
            patient=p, 
            statut='EN_COURS'
        ).first()

    return render(request, 'back-end/medecin/liste_patients.html', {
        'patients': patients, 
        'fonctionKey': fonctionKey
    })




# 
# ===========================================================================================
# IMPRIMER LES RESULTAT DU TECHNICIEN 
# ===========================================================================================
@login_required
def imprimer_resultat(request, examen_id):
    # On récupère directement l'examen par son ID
    examen = get_object_or_404(DemandeExamen.objects.select_related('consultation__triage__patient', 'prestation', 'technicien'), id=examen_id)
    
    # Comme vous avez besoin de la consultation pour le template, on l'extrait de l'examen
    consultation = examen.consultation
    
    # On met l'examen dans une liste pour conserver la compatibilité avec votre template (qui fait un {% for exam in examens %})
    examens = [examen]
    
    return render(request, 'back-end/medecin/imprimer_resultat.html', {
        'consultation': consultation,
        'examens': examens
    })
# 
# ===========================================================================================
# IMPRIMER LES RESULTAT DU TECHNICIEN TOUT 
# ===========================================================================================
@login_required
def imprimer_consultation(request, consultation_id):
    # On ne récupère que la consultation et ses examens
    consultation = get_object_or_404(
        Consultation.objects.prefetch_related('examens'), 
        id=consultation_id
    )
    
    # On filtre uniquement les examens terminés pour l'affichage
    examens_termines = consultation.examens.filter(statut='TERMINE')
    
    return render(request, 'back-end/medecin/imprimer_consultation.html', {
        'consultation': consultation,
        'examens': examens_termines
    })

# 
# ============================================================================================
# MODIFICATION DES L'ORDONNANCE
# ============================================================================================
@login_required
def modifier_ordonnance_view(request, ordonnance_id):
    # Récupération de l'ordonnance avec ses relations
    ordonnance = get_object_or_404(Ordonnance.objects.select_related('consultation'), id=ordonnance_id)

    if request.method == 'POST':
        # 1. Mise à jour des informations de base
        ordonnance.type_ordonnance = request.POST.get('type_ordonnance')
        ordonnance.observation = request.POST.get('observation')
        ordonnance.save()

        # 2. Mise à jour des médicaments : on supprime les anciens et on recrée
        ordonnance.medicaments.all().delete()
        
        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        for i in range(len(noms)):
            if noms[i]: # On vérifie que le nom n'est pas vide
                Medicament.objects.create(
                    ordonnance=ordonnance,
                    nom=noms[i],
                    posologie=posologies[i],
                    duree=durees[i]
                )
        
        messages.success(request, "Ordonnance mise à jour avec succès.")
        return redirect('liste_ordonnances') 
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/modifier_ordonnance.html', {'ord': ordonnance, 'fonctionKey':fonctionKey})


#
# ====================================================================================================
#  ADMETTRE UNE PATIENTE A LA MATERNITE 
# ====================================================================================================
@login_required
def admettre_maternite(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    # SÉCURITÉ 1 : Vérification stricte du paiement de la fiche générale
    if not patient.fiche_payee:
        messages.error(request, "Erreur : La fiche du patient doit être réglée avant toute admission.")
        return redirect('enregistrement_patient')

    # SÉCURITÉ 2 : Vérification stricte du sexe
    if patient.sexe not in ['Feminin', 'F']:
        messages.error(request, "Erreur : Impossible d'admettre un homme en maternité.")
        return redirect('enregistrement_patient')

    maternite_instance = Maternite(patient=patient)
    
    if request.method == 'POST':
        form = MaterniteForm(request.POST, instance=maternite_instance)
        if form.is_valid():
            dossier = form.save(commit=False)
            dossier.enregistre_par = request.user
            
            # MISE À JOUR : Le paiement n'est plus requis pour l'ouverture du dossier
            dossier.save()
            
            messages.success(request, f"Patiente {patient.noms} admise avec succès. L'ouverture du dossier est gratuite.")
            return redirect('liste_admissions_maternite')
    else:
        form = MaterniteForm(instance=maternite_instance)
    
    # Récupération du rôle
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/maternite/admettre.html', {
        'form': form, 
        'patient': patient,
        'fonctionKey': fonctionKey
    })



# 
# ========================================================================================
#  LISTE DE PATIENTES A LA MATERNITES 
# ========================================================================================
@login_required
def liste_admissions_maternite(request):
    # Récupère tous les dossiers, ordonnés du plus récent au plus ancien
    admissions = Maternite.objects.all().order_by('-date_admission')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'admissions': admissions,
        'segment': 'liste_maternite' ,
        'fonctionKey' : fonctionKey
    }
    return render(request, 'back-end/maternite/liste_maternite.html', context)

#
# ====================================================================================
# AJOUTE CONSULTATION
# ====================================================================================
@login_required
def ajouter_consultation(request, dossier_id):
    dossier = get_object_or_404(Maternite, id=dossier_id)
    
    if request.method == 'POST':
        form = ConsultationMaterniteForm(request.POST)
        if form.is_valid():
            consultation = form.save(commit=False)
            consultation.dossier_maternite = dossier
            consultation.effectue_par = request.user
            consultation.save()
            
            messages.success(request, f"Consultation enregistrée pour {dossier.patient.noms}.") 
            return redirect('liste_admissions_maternite')
    else:
        form = ConsultationMaterniteForm()

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/maternite/ajouter_consultation.html', {
        'form': form,
        'dossier': dossier , 
        'fonctionKey' : fonctionKey
    })


# 
# ===================================================================================================
#  PAIEMENT DE LA CARTE DE FIDELITE
# ===================================================================================================
@login_required
def vue_paiement_carte_fidelite(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if hopital_user and patient.hopital_id != hopital_user.id and fonctionKey != 'admin':
        messages.error(request, "Accès refusé : patient hors de votre hôpital.")
        return redirect('enregistrement_patient')

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2800.00')

    try:
        prestation_carte = Prestation.objects.get(
            categorie='ADM',
            libelle__icontains="Carte",
            hopital=patient.hopital
        )
    except (Prestation.DoesNotExist, Prestation.MultipleObjectsReturned):
        prestation_carte = Prestation.objects.filter(
            categorie='ADM',
            libelle__icontains="Carte",
            hopital=patient.hopital
        ).first()

    if not prestation_carte:
        messages.error(request, "La prestation 'Carte de Fidélité' n'est pas configurée pour cet hôpital.")
        return redirect('enregistrement_patient')

    prix_carte_usd = Decimal(str(prestation_carte.prix))

    paiements_existants = Paiement.objects.filter(patient=patient, service='CARTE')
    total_deja_paye_usd = Decimal('0.00')

    for p in paiements_existants:
        if p.devise == 'CDF':
            total_deja_paye_usd += p.montant_verse / taux
        else:
            total_deja_paye_usd += p.montant_verse

    reste_a_payer_usd = prix_carte_usd - total_deja_paye_usd

    if request.method == 'POST':
        montant_saisi = Decimal(request.POST.get('montant', 0))
        devise = request.POST.get('devise')

        montant_test_usd = montant_saisi
        if devise == 'CDF':
            montant_test_usd = montant_saisi / taux

        if montant_test_usd > (reste_a_payer_usd + Decimal('0.01')):
            messages.error(request, f"Le montant dépasse le prix de la carte ({reste_a_payer_usd:.2f} USD restants).")
        elif montant_saisi > 0:
            Paiement.objects.create(
                patient=patient,
                service='CARTE',
                montant_verse=montant_saisi,
                devise=devise,
                caissier=request.user,
                hopital=patient.hopital
            )

            nouveau_total_usd = total_deja_paye_usd + montant_test_usd

            if nouveau_total_usd >= (prix_carte_usd - Decimal('0.01')):
                patient.a_carte_fidelite = True
                patient.save()
                messages.success(request, f"Paiement terminé. La carte de {patient.noms} est activée.")
            else:
                messages.success(request, f"Paiement de {montant_saisi} {devise} enregistré. Reste : {(prix_carte_usd - nouveau_total_usd):.2f} USD")

            return redirect('enregistrement_patient')

    context = {
        'patient': patient,
        'reste_a_payer': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_usd * taux,
        'taux': taux,
        'prix_carte': prix_carte_usd,
        'libelle_prestation': prestation_carte.libelle,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/patient/paiement_prestation.html', context)

# 
# ========================================================================================
# PAYER DOSSIER MATERNITE
# ========================================================================================
@login_required
def payer_dossier_maternite(request, dossier_id):
    dossier = get_object_or_404(Maternite, id=dossier_id)
    hopital_dossier = dossier.patient.hopital if dossier.patient else None

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if hopital_user and hopital_dossier and hopital_user.id != hopital_dossier.id and fonctionKey != 'admin':
        messages.error(request, "Accès refusé : ce dossier ne dépend pas de votre hôpital.")
        return redirect('liste_admissions_maternite')

    prestation_mat = Prestation.objects.filter(
        categorie='MAT',
        hopital=hopital_dossier
    ).first()

    prix_referentiel = prestation_mat.prix if prestation_mat else Decimal('150.00')

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')

    if request.method == 'POST':
        montant_raw = request.POST.get('montant', '0')
        reste_raw = request.POST.get('reste_a_payer', '0')
        devise = request.POST.get('devise', 'USD')

        try:
            montant = Decimal(montant_raw)
            reste = Decimal(reste_raw)

            montant_en_usd = montant if devise == 'USD' else (montant / taux)

            if montant_en_usd > prix_referentiel:
                messages.error(request, f"Erreur : Le montant versé dépasse le forfait Maternité de {prix_referentiel} USD.")
                return redirect('payer_dossier_maternite', dossier_id=dossier.id)

            Paiement.objects.create(
                patient=dossier.patient,
                dossier_maternite=dossier,
                service='MATERNITE',
                montant_verse=montant,
                devise=devise,
                reste_a_payer=reste,
                caissier=request.user,
                hopital=hopital_dossier
            )

            messages.success(request, f"Paiement de {montant} {devise} enregistré avec succès.")
            return redirect('liste_admissions_maternite')

        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, "Erreur : Format de montant invalide.")
            return redirect('payer_dossier_maternite', dossier_id=dossier.id)

    return render(request, 'back-end/maternite/payer.html', {
        'dossier': dossier,
        'prix_max': prix_referentiel,
        'taux': taux,
        'fonctionKey': fonctionKey
    })
    
    #  
# =================================================================================================
# ENREGISTREMENT DE L'ACTE DE DECES 
# =================================================================================================
@login_required
def enregistrer_deces(request):
    patients = Patient.objects.all().order_by('noms')

    if request.method == 'POST':
        try:
            # Récupération de l'identité
            patient_id = request.POST.get('patient_id')
            nom_externe = request.POST.get('nom_patient_externe')
            
            # Récupération des infos biographiques et adresse
            date_naissance = request.POST.get('date_naissance')
            lieu_naissance = request.POST.get('lieu_naissance')
            adresse_avenue = request.POST.get('adresse_avenue')
            adresse_numero = request.POST.get('adresse_numero')
            adresse_quartier = request.POST.get('adresse_quartier')
            adresse_commune = request.POST.get('adresse_commune')
            
            # Infos décès
            date_deces = request.POST.get('date_deces')
            cause = request.POST.get('cause_deces')
            
            # Certification
            etablissement = request.POST.get('etablissement', "Hôpital Paradis Center")
            certifie = request.POST.get('certifie_par')
            numero_cnom = request.POST.get('numero_cnom')
            notes = request.POST.get('notes', '')

            # Validation (vérifie au moins les champs essentiels)
            if not date_deces or not cause or not certifie:
                messages.error(request, "Veuillez remplir tous les champs obligatoires (Date décès, Cause, Médecin).")
                return redirect('enregistrer_deces')

            # Création de l'objet avec tous les nouveaux champs
            Deces.objects.create(
                patient_id=patient_id if patient_id else None,
                nom_patient_externe=nom_externe if not patient_id else None,
                date_naissance=date_naissance,
                lieu_naissance=lieu_naissance,
                adresse_avenue=adresse_avenue,
                adresse_numero=adresse_numero,
                adresse_quartier=adresse_quartier,
                adresse_commune=adresse_commune,
                date_deces=date_deces,
                cause_deces=cause,
                etablissement=etablissement,
                certifie_par=certifie,
                numero_cnom=numero_cnom,
                notes=notes
            )

            messages.success(request, "Certificat de décès enregistré avec succès.")
            return redirect('liste_deces')

        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
            return redirect('enregistrer_deces')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/deces/enregistre.html', {'patients': patients, 'fonctionKey': fonctionKey})

#
# =========================================================================
# LISTE DES DECES 
# ========================================================================
@login_required
def liste_deces(request):
    # On récupère tous les décès, triés par date (du plus récent au plus ancien)
    deces_list = Deces.objects.all().order_by('-date_deces')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    return render(request, 'back-end/deces/liste.html', {'deces_list': deces_list, 'fonctionKey': fonctionKey})

#
# ==============================================================================
# IMPRIMER DECES 
# =============================================================================
@login_required
def imprimer_deces(request, deces_id):
    deces = get_object_or_404(Deces, id=deces_id)
    return render(request, 'back-end/deces/imprimer.html', {'deces': deces})


#
# =============================================================================
# PAYER DECES ACTE
# =============================================================================
@login_required
def enregistrer_paiement_deces(request, deces_id):
    deces = get_object_or_404(Deces, id=deces_id)
    hopital_deces = deces.patient.hopital if deces.patient else None

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    if hopital_user and hopital_deces and hopital_user.id != hopital_deces.id and fonctionKey != 'admin':
        messages.error(request, "Accès refusé : ce décès ne dépend pas de votre hôpital.")
        return redirect('liste_deces')

    if deces.paiements.exists():
        messages.warning(request, "Attention : Ce décès a déjà été réglé.")
        return redirect('liste_deces')

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')

    prestation = Prestation.objects.filter(
        libelle__icontains="acte de deces",
        hopital=hopital_deces
    ).first()

    prix_usd = prestation.prix if prestation else Decimal('0.00')
    prix_cdf = (prix_usd * taux).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    if request.method == 'POST':
        devise = request.POST.get('devise')
        try:
            montant_verse = Decimal(request.POST.get('montant_verse', '0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except:
            montant_verse = Decimal('0')

        prix_requis = (prix_usd if devise == 'USD' else prix_cdf).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if abs(montant_verse - prix_requis) > Decimal('0.05'):
            messages.error(request, f"Paiement refusé : Le montant doit être de {prix_requis:.2f} {devise}.")
            return render(request, 'back-end/deces/payer.html', {
                'deces': deces,
                'prix_usd': prix_usd,
                'prix_cdf': prix_cdf,
                'taux': taux
            })

        if not deces.paiements.exists():
            Paiement.objects.create(
                patient=deces.patient if deces.patient else None,
                deces=deces,
                service='DECES',
                montant_verse=montant_verse,
                devise=devise,
                caissier=request.user,
                hopital=hopital_deces
            )
            messages.success(request, "Paiement enregistré avec succès.")
        else:
            messages.error(request, "Erreur : Un paiement a été enregistré simultanément.")

        return redirect('liste_deces')

    return render(request, 'back-end/deces/payer.html', {
        'deces': deces,
        'prix_usd': prix_usd,
        'prix_cdf': prix_cdf,
        'taux': taux,
        'fonctionKey': fonctionKey
    })

#
# =========================================================================================
# LISTE DES PATIENTS CARTE DE FIDELITE 
# =========================================================================================
@login_required
def liste_patients_avec_carte(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    patients_fideles = Patient.objects.filter(
        a_carte_fidelite=True,
        hopital=hopital_user
    ).order_by('-date_creation') if hopital_user else Patient.objects.none()

    context = {
        'patients': patients_fideles,
        'title': "Patients avec Carte de Fidélité",
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/patient/liste_patients_carte.html', context)

#
# ==========================================================================================
# MODIFIER TYPE DE PATIENT
# ==========================================================================================
@login_required
def modifier_type_patient(request, patient_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user) if hopital_user else None
    if not patient:
        messages.error(request, "Patient introuvable.")
        return redirect('liste_patients_avec_carte')

    if patient.type_patient == 'FIDELE':
        messages.error(request, "Le statut 'Patient Fidèle' est définitif et ne peut plus être modifié.")
        return redirect('liste_patients_avec_carte')

    if request.method == 'POST':
        nouveau_type = request.POST.get('type_patient')

        if nouveau_type not in ['SIMPLE', 'FIDELE', 'CONVENTIONNE']:
            messages.error(request, "Type de patient invalide.")
            return redirect('modifier_type_patient', patient_id=patient.id)

        patient.type_patient = nouveau_type
        patient.save()
        messages.success(request, "Statut mis à jour.")
        return redirect('liste_patients_avec_carte')

    return render(request, 'back-end/patient/modifier_type.html', {
        'patient': patient,
        'fonctionKey': fonctionKey
    })

#
# ==================================================================================================
#   SOIN RAPIDE HORS FICHE
# ==================================================================================================
@login_required
def enregistrer_soin_rapide(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        nom_patient = request.POST.get('nom_patient')
        ids_prestations = request.POST.getlist('prestation_ids')
        reduction = Decimal(request.POST.get('reduction', '0.00'))
        devise_paiement = request.POST.get('devise')

        prestations = Prestation.objects.filter(
            id__in=ids_prestations,
            hopital=user_hopital,
            categorie='SOIN'
        )

        total_brut = sum(p.prix for p in prestations)
        net_usd = total_brut - reduction

        if devise_paiement == 'CDF':
            taux = ConfigurationHopital.get_taux()
            montant_verse = net_usd * taux
        else:
            montant_verse = net_usd

        try:
            with transaction.atomic():
                paiement = Paiement.objects.create(
                    service='SOIN',
                    montant_verse=montant_verse,
                    montant_reduction=reduction,
                    devise=devise_paiement,
                    caissier=request.user,
                    reste_a_payer=Decimal('0.00'),
                    hopital=user_hopital
                )

                for p in prestations:
                    SoinOccasionnel.objects.create(
                        paiement=paiement,
                        nom_patient=nom_patient,
                        prestation=p,
                        effectue_par=request.user,
                        hopital=user_hopital
                    )

            messages.success(request, "Paiement enregistré !")
            return redirect('soin_rapide')

        except Exception as e:
            messages.error(request, f"Erreur : {e}")
            return redirect('soin_rapide')

    return render(request, 'back-end/soins/soin_rapide.html', {
        'prestations': Prestation.objects.filter(categorie='SOIN', hopital=user_hopital),
        'taux': ConfigurationHopital.get_taux(),
        'fonctionKey': fonctionKey,
    })
#
# =========================================================================================
# IMPRIMER FACTURE PATIENT OCCASIONNEL
# =========================================================================================
@login_required
def facture_print(request, paiement_id):
    # On récupère le paiement spécifique
    paiement = get_object_or_404(Paiement, id=paiement_id)
    
    # On récupère les soins liés à ce paiement via le related_name 'soins_lies'
    soins = paiement.soins_lies.all()
    
    # On affiche le template de la facture (que tu as déjà sûrement créé)
    return render(request, 'back-end/soins/facture_print.html', {
        'paiement': paiement,
        'soins': soins
    })

#
# =========================================================================================
# LISTE SOINS PATIENT OCCASIONNEL
# =========================================================================================
@login_required
def liste_soins_traitement(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    aujourd_hui = timezone.now().date()

    soins = SoinOccasionnel.objects.filter(
        hopital=hopital_user,
        est_effectue=False,
        date_soin__date=aujourd_hui
    ).select_related(
        'paiement',
        'prestation',
        'effectue_par',
        'hopital'
    ).order_by('-date_soin')

    return render(request, 'back-end/soins/liste_soins_traitement.html', {
        'soins': soins,
        'fonctionKey': fonctionKey
    })

#
# ============================================================================================
# MARQUE TRAITEMENT FAIT 
# ============================================================================================
@login_required
def marquer_fait(request, soin_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    soin = get_object_or_404(SoinOccasionnel, id=soin_id, hopital=hopital_user)
    soin.est_effectue = True
    soin.save()
    return redirect('liste_soins_traitement')

#
# ============================================================================================
# HISTORIQUE DES SOINS RAPIDE  
# =============================================================================================
@login_required
def historique_soins(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    paiements = Paiement.objects.filter(soins_lies__isnull=False)

    if fonctionKey != 'admin' and user_hopital:
        paiements = paiements.filter(hopital=user_hopital)

    paiements = paiements.distinct().order_by('-date_paiement')

    return render(request, 'back-end/soins/historique_soins.html', {
        'paiements': paiements,
        'fonctionKey': fonctionKey
    })


#
# ==============================================================================================
# ENREGISTREMENT DES PRODUITS PHARMACEUTIQUES
# ==============================================================================================
@login_required
def ajouter_produit(request):
    """Vue pour enregistrer une nouvelle référence de médicament en stock"""
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if request.method == 'POST':
        form = ProduitPharmacieForm(request.POST)
        if form.is_valid():
            produit = form.save(commit=False)
            produit.hopital = hopital_user
            produit.save()
            messages.success(request, "Le produit a été enregistré avec succès.") 
            return redirect('gestion_pharmacie')
        else:
            messages.error(request, "Erreur lors de l'enregistrement. Vérifie les données.")
    else:
        form = ProduitPharmacieForm()

    return render(request, 'back-end/pharmacie/ajouter_produit.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })


# 
# ====================================================================================
# LISTE DES MEDICAMENTS 
# ====================================================================================

@login_required
def gestion_pharmacie(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        produits = ProduitPharmacie.objects.none()
    else:
        entrees_subquery = LotPharmacie.objects.filter(
            produit_id=OuterRef('pk'),
            hopital=hopital_user
        ).values('produit_id').annotate(
            total_entrees=Coalesce(Sum('quantite_initiale'), 0)
        ).values('total_entrees')[:1]

        sorties_subquery = SortiePharmacie.objects.filter(
            lot__produit_id=OuterRef('pk'),
            lot__hopital=hopital_user
        ).values('lot__produit_id').annotate(
            total_sorties=Coalesce(Sum('quantite_vendue'), 0)
        ).values('total_sorties')[:1]

        produits = ProduitPharmacie.objects.filter(
            hopital=hopital_user
        ).annotate(
            total_entrees=Coalesce(Subquery(entrees_subquery, output_field=IntegerField()), 0),
            total_sorties=Coalesce(Subquery(sorties_subquery, output_field=IntegerField()), 0),
        ).annotate(
            stock_reel=ExpressionWrapper(
                F('total_entrees') - F('total_sorties'),
                output_field=IntegerField()
            )
        ).order_by('nom')

        for p in produits:
            p.valeur_totale = p.stock_reel * p.prix_vente_unitaire

    taux_change = ConfigurationHopital.get_taux()

    context = {
        'produits': produits,
        'fonctionKey': fonctionKey,
        'taux': taux_change
    }

    return render(request, 'back-end/pharmacie/gestion_stock.html', context)

#
# ====================================================================================
# MODIFIER MEDICAMENT
# ====================================================================================
@login_required
def modifier_produit_pharmacie(request, produit_id):
    """Vue pour modifier un produit de pharmacie"""
    # Vérification des permissions
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role.hopital if role else None
    
    if not hopital_user:
        messages.error(request, "Accès non autorisé.")
        return redirect('gestion_pharmacie')
    
    # Récupération du produit
    produit = get_object_or_404(ProduitPharmacie, pk=produit_id, hopital=hopital_user)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Récupération des champs texte
                produit.nom = request.POST.get('nom', '').strip()
                produit.forme = request.POST.get('forme', '').strip()
                produit.dosage = request.POST.get('dosage', '').strip()
                produit.categorie = request.POST.get('categorie', '').strip()
                produit.devise = request.POST.get('devise', 'USD')
                produit.unites_par_carton = int(request.POST.get('unites_par_carton', 1) or 1)
                
                # Conversion des prix en Decimal
                produit.prix_achat_unitaire = Decimal(request.POST.get('prix_achat_unitaire', 0) or 0)
                produit.prix_vente_unitaire = Decimal(request.POST.get('prix_vente_unitaire', 0) or 0)
                
                # Validation des champs obligatoires
                if not produit.nom or not produit.forme or not produit.dosage:
                    raise ValueError("Les champs nom, forme et dosage sont obligatoires.")
                
                if produit.prix_achat_unitaire < 0 or produit.prix_vente_unitaire < 0:
                    raise ValueError("Les prix ne peuvent pas être négatifs.")
                
                if produit.unites_par_carton < 1:
                    raise ValueError("L'unité par carton doit être au moins 1.")
                
                produit.save()
                
            messages.success(request, f"✅ Produit '{produit.nom}' modifié avec succès.")
            return redirect('gestion_pharmacie')
            
        except ValueError as e:
            messages.error(request, f"❌ Erreur: {str(e)}")
            return redirect('modifier_produit', produit_id=produit_id)
        except Exception as e:
            messages.error(request, f"❌ Erreur inattendue: {str(e)}")
            return redirect('modifier_produit', produit_id=produit_id)
    
    # Calcul du stock réel pour affichage
    with transaction.atomic():
        entrees = LotPharmacie.objects.filter(
            produit=produit,
            hopital=hopital_user
        ).aggregate(total=Coalesce(Sum('quantite_initiale'), 0))['total'] or 0
        
        sorties = SortiePharmacie.objects.filter(
            lot__produit=produit,
            lot__hopital=hopital_user
        ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
    
    stock_reel = entrees - sorties
    valeur_totale = float(produit.prix_vente_unitaire) * stock_reel if produit.prix_vente_unitaire else 0
    
    context = {
        'produit': produit,
        'stock_reel': stock_reel,
        'valeur_totale': round(valeur_totale, 2),
        'fonctionKey': role.fonctionKey.roleName if role and role.fonctionKey else None,
        'taux': ConfigurationHopital.get_taux()
    }
    
    return render(request, 'back-end/pharmacie/modifier_produit.html', context)
#
# ====================================================================================
# SUPPRIMER MEDICAMENT
# ====================================================================================
@login_required
def supprimer_produit_pharmacie(request, produit_id):
    """Vue pour supprimer un produit de pharmacie"""
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role.hopital if role else None
    
    if not hopital_user:
        messages.error(request, "Accès non autorisé.")
        return redirect('gestion_pharmacie')
    
    produit = get_object_or_404(ProduitPharmacie, pk=produit_id, hopital=hopital_user)
    
    if request.method == 'POST':
        try:
            produit.delete()
            messages.success(request, "Produit supprimé avec succès.")
            return redirect('gestion_pharmacie')
        except Exception as e:
            messages.error(request, f"Erreur lors de la suppression: {str(e)}")
    
    context = {'produit': produit}
    return render(request, 'back-end/pharmacie/confirmer_suppression.html', context)

#
# ====================================================================================
# GESTION DES STOCKS
# ====================================================================================
@login_required
def ajouter_lot(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if request.method == 'POST':
        form = LotPharmacieForm(request.POST, hopital=hopital_user)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.hopital = hopital_user
            lot.save()
            messages.success(request, "Lot ajouté avec succès, stock mis à jour.")
            return redirect('gestion_pharmacie')
    else:
        form = LotPharmacieForm(hopital=hopital_user)

    lots = LotPharmacie.objects.filter(hopital=hopital_user).select_related('produit').order_by('-id')

    return render(request, 'back-end/pharmacie/ajouter_lot.html', {
        'form': form,
        'fonctionKey': fonctionKey,
        'lots': lots
    })
#
# =====================================================================================
# VENTE DE PRODUIT 
# =====================================================================================
@login_required
def enregistrer_vente(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            panier = data.get('panier_data', [])
            devise = data.get('devise', 'USD')
            montant_verse = Decimal(str(data.get('montant_verse', 0)))

            if not panier:
                return JsonResponse({'status': 'error', 'message': 'Le panier est vide.'})
            if montant_verse < 0:
                return JsonResponse({'status': 'error', 'message': 'Montant versé invalide.'})

            taux = Decimal(str(ConfigurationHopital.get_taux()))

            with transaction.atomic():
                montant_total = Decimal('0.00')
                items_a_vendre = []

                for item in panier:
                    lot = LotPharmacie.objects.select_for_update().filter(
                        produit_id=item['id'],
                        hopital=hopital_user,
                        quantite_actuelle__gte=int(item['qte'])
                    ).first()

                    if not lot:
                        produit = ProduitPharmacie.objects.filter(id=item['id'], hopital=hopital_user).first()
                        nom_produit = produit.nom if produit else "Produit"
                        return JsonResponse({'status': 'error', 'message': f'Stock insuffisant pour {nom_produit}'})

                    prix_u = Decimal(str(lot.produit.prix_vente_unitaire))
                    if devise == 'CDF':
                        prix_u *= taux

                    montant_total += (prix_u * int(item['qte']))
                    items_a_vendre.append({'lot': lot, 'qte': int(item['qte'])})

                if montant_verse > montant_total:
                    return JsonResponse({'status': 'error', 'message': 'Le montant versé dépasse le total.'})

                reste_a_payer = montant_total - montant_verse

                paiement = Paiement.objects.create(
                    montant_verse=montant_verse,
                    devise=devise,
                    service='PHARMACIE',
                    caissier=request.user,
                    hopital=hopital_user,
                    reste_a_payer=reste_a_payer
                )

                for item in items_a_vendre:
                    SortiePharmacie.objects.create(
                        paiement=paiement,
                        lot=item['lot'],
                        quantite_vendue=item['qte'],
                        vendu_par=request.user
                    )

            return JsonResponse({
                'status': 'success',
                'message': 'Vente validée avec succès.',
                'dette': str(reste_a_payer)
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    produits = ProduitPharmacie.objects.filter(
        hopital=hopital_user
    ).annotate(
        stock_reel=Sum('les_lots__quantite_actuelle')
    ).order_by('nom')

    return render(request, 'back-end/pharmacie/enregistrer_vente.html', {
        'produits': produits,
        'taux_actuel': float(ConfigurationHopital.get_taux()),
        'fonctionKey': fonctionKey
    })
#
# =============================================================================================================================
# DASHBOARD COTE PHARMACIE 
# =============================================================================================================================
@login_required
def dashboard_ventes(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Invité"

    periode = request.GET.get('periode', 'jour')
    hopital_id = request.GET.get('hopital_id')
    est_admin = request.user.is_superuser or request.user.is_staff

    if est_admin:
        hopital_actif = None
        if hopital_id:
            hopital_actif = Hopital.objects.filter(id=hopital_id).first()

        paiements_base = Paiement.objects.all()
        sorties_base = SortiePharmacie.objects.all()
        lots_base = LotPharmacie.objects.all()
        hopitaux = Hopital.objects.all().order_by('nomH')
    else:
        hopital_actif = hopital_user
        paiements_base = Paiement.objects.filter(hopital=hopital_user) if hopital_user else Paiement.objects.none()
        sorties_base = SortiePharmacie.objects.filter(hopital=hopital_user) if hopital_user else SortiePharmacie.objects.none()
        lots_base = LotPharmacie.objects.filter(hopital=hopital_user) if hopital_user else LotPharmacie.objects.none()
        hopitaux = Hopital.objects.filter(id=hopital_user.id) if hopital_user else Hopital.objects.none()

    if est_admin and hopital_actif:
        paiements_base = paiements_base.filter(hopital=hopital_actif)
        sorties_base = sorties_base.filter(hopital=hopital_actif)
        lots_base = lots_base.filter(hopital=hopital_actif)

    periodes_map = {
        'jour': TruncDay('date_paiement'),
        'semaine': TruncWeek('date_paiement'),
        'mois': TruncMonth('date_paiement'),
    }
    trunc_func = periodes_map.get(periode, TruncDay('date_paiement'))

    total_general = paiements_base.values('devise').annotate(
        grand_total=Sum('montant_verse')
    ).order_by('devise')

    ventes_par_utilisateur = paiements_base.values(
        'les_sorties__vendu_par__username', 'devise'
    ).annotate(
        total_vendu=Sum('montant_verse')
    ).order_by('-total_vendu')

    stats_ventes = paiements_base.annotate(date_groupee=trunc_func).values(
        'date_groupee', 'devise'
    ).annotate(
        total_periode=Sum('montant_verse')
    ).order_by('-date_groupee', 'devise')

    benefice_expr = ExpressionWrapper(
        (F('lot__produit__prix_vente_unitaire') - F('lot__produit__prix_achat_unitaire')) * F('quantite_vendue'),
        output_field=DecimalField(max_digits=14, decimal_places=2)
    )

    top_benefices = sorties_base.values('lot__produit__nom').annotate(
        benefice_total=Sum(benefice_expr)
    ).order_by('-benefice_total')[:5]

    dettes_en_cours = paiements_base.filter(reste_a_payer__gt=0).prefetch_related('les_sorties__vendu_par')
    produits_critiques = lots_base.filter(quantite_actuelle__lt=5).select_related('produit')

    aujourdhui = timezone.now().date()
    ventes_du_jour = paiements_base.filter(date_paiement__date=aujourdhui)

    chiffre_affaires_jour = ventes_du_jour.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    nombre_ventes_jour = ventes_du_jour.count()

    repartition_jour = ventes_du_jour.values('devise').annotate(
        total=Sum('montant_verse'),
        nombre=Count('id')
    ).order_by('devise')

    repartition_globale = paiements_base.values('devise').annotate(
        total=Sum('montant_verse'),
        nombre=Count('id')
    ).order_by('devise')

    context = {
        'stats_ventes': stats_ventes,
        'total_general': total_general,
        'ventes_par_utilisateur': ventes_par_utilisateur,
        'top_benefices': top_benefices,
        'dettes_en_cours': dettes_en_cours,
        'produits_critiques': produits_critiques,
        'nb_ventes': ventes_du_jour.count(),
        'periode_actuelle': periode,
        'fonctionKey': fonctionKey,
        'est_admin': est_admin,
        'hopitaux': hopitaux,
        'hopital_actif': hopital_actif,
        'chiffre_affaires_jour': chiffre_affaires_jour,
        'nombre_ventes_jour': nombre_ventes_jour,
        'repartition_jour': repartition_jour,
        'repartition_globale': repartition_globale,
    }
    return render(request, 'back-end/pharmacie/dashboard.html', context)
# ==================================================================================================
# LISTE DES VENTES
# ==================================================================================================
@login_required
def liste_ventes(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Invité"

    ventes = Paiement.objects.filter(service='PHARMACIE', hopital=hopital_user).order_by('-date_paiement')

    q = request.GET.get('q', '').strip()
    devise = request.GET.get('devise', '').strip()
    date_debut = request.GET.get('date_debut', '').strip()
    date_fin = request.GET.get('date_fin', '').strip()

    if q:
        ventes = ventes.filter(
            Q(service__icontains=q) |
            Q(devise__icontains=q) |
            Q(montant_verse__icontains=q) |
            Q(reste_a_payer__icontains=q)
        )

    if devise in ['USD', 'CDF']:
        ventes = ventes.filter(devise=devise)

    if date_debut:
        ventes = ventes.filter(date_paiement__date__gte=date_debut)

    if date_fin:
        ventes = ventes.filter(date_paiement__date__lte=date_fin)

    usd_ventes = ventes.filter(devise='USD')
    cdf_ventes = ventes.filter(devise='CDF')

    total_verse_usd = usd_ventes.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_verse_cdf = cdf_ventes.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')

    total_reste_usd = usd_ventes.aggregate(total=Sum('reste_a_payer'))['total'] or Decimal('0.00')
    total_reste_cdf = cdf_ventes.aggregate(total=Sum('reste_a_payer'))['total'] or Decimal('0.00')

    total_reduction_usd = usd_ventes.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')
    total_reduction_cdf = cdf_ventes.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')

    return render(request, 'back-end/pharmacie/liste_ventes.html', {
        'ventes': ventes,
        'fonctionKey': fonctionKey,
        'total_verse_usd': total_verse_usd,
        'total_verse_cdf': total_verse_cdf,
        'total_reste_usd': total_reste_usd,
        'total_reste_cdf': total_reste_cdf,
        'total_reduction_usd': total_reduction_usd,
        'total_reduction_cdf': total_reduction_cdf,
        'nb_ventes': ventes.count(),
        'q': q,
        'devise': devise,
        'date_debut': date_debut,
        'date_fin': date_fin,
    })
#
# ===================================================================================================
# FACTURATION DES VENTES PRODUITS
# ===================================================================================================
@login_required
def details_facture(request, vente_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    facture = get_object_or_404(Paiement, id=vente_id, hopital=hopital_user)
    details = facture.les_sorties.select_related('lot__produit').all()

    taux = Decimal(str(ConfigurationHopital.get_taux()))
    devise_facture = facture.devise
    total_vente = Decimal('0.00')

    for item in details:
        produit = item.lot.produit
        item.nom_medicament = produit.nom
        item.forme_medicament = produit.forme
        item.dosage_medicament = produit.dosage

        prix_source = Decimal(str(produit.prix_vente_unitaire))
        devise_source = produit.devise if hasattr(produit, 'devise') and produit.devise else devise_facture

        if devise_source != devise_facture:
            if devise_source == 'USD' and devise_facture == 'CDF':
                prix_affiche = prix_source * taux
            elif devise_source == 'CDF' and devise_facture == 'USD':
                prix_affiche = prix_source / taux
            else:
                prix_affiche = prix_source
        else:
            prix_affiche = prix_source

        item.prix_unitaire = prix_affiche.quantize(Decimal('0.01'))
        item.total_ligne = (item.prix_unitaire * item.quantite_vendue).quantize(Decimal('0.01'))
        total_vente += item.total_ligne

    total_vente = total_vente.quantize(Decimal('0.01'))
    montant_verse = Decimal(str(facture.montant_verse)).quantize(Decimal('0.01'))
    reste_a_payer = (total_vente - montant_verse).quantize(Decimal('0.01'))

    context = {
        'facture': facture,
        'details': details,
        'total_vente': total_vente,
        'montant_verse': montant_verse,
        'reste_a_payer': reste_a_payer,
        'taux': taux,
    }
    return render(request, 'back-end/pharmacie/facture_print.html', context)
#
# ===============================================================================================
# VALIDER VENTE PHARMACIE
# ===============================================================================================
@csrf_exempt
def valider_vente(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            panier = data.get('panier', [])
            devise = data.get('devise')

            if not panier:
                return JsonResponse({'success': False, 'message': 'Panier vide.'})

            with transaction.atomic():
                paiement = Paiement.objects.create(
                    devise=devise,
                    hopital=hopital_user,
                    caissier=request.user
                )

                for item in panier:
                    lot = get_object_or_404(
                        LotPharmacie,
                        id=item['lot_id'],
                        hopital=hopital_user
                    )

                    SortiePharmacie.objects.create(
                        paiement=paiement,
                        lot=lot,
                        quantite_vendue=item['quantite'],
                        vendu_par=request.user
                    )

            return JsonResponse({'success': True})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})
#
# ===============================================================================================
# ORIENTATIONS
# ===============================================================================================
@login_required
def service_destinataire_view(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonction_nom = role_obj.fonctionKey.roleName.strip().lower() if (role_obj and role_obj.fonctionKey) else ""

    if request.method == 'POST' and request.POST.get('orientation_id'):
        orientation = get_object_or_404(
            Orientation,
            id=request.POST.get('orientation_id'),
            hopital=hopital_user
        )
        orientation.est_admis = True
        orientation.save()
        return redirect('service_liste_attente')

    services_avec_compte_rendu = ['bloc', 'accouchement']
    doit_saisir_compte_rendu = any(s in fonction_nom for s in services_avec_compte_rendu)

    if 'pharmacien' in fonction_nom:
        destinations_autorisees = ['PHARMACIE']
    elif 'infirmier' in fonction_nom or 'medecin' in fonction_nom:
        destinations_autorisees = ['SALLE_SOINS', 'BLOC_OPERATOIRE', 'ACCOUCHEMENT']
    elif 'hospitalisation' in fonction_nom:
        destinations_autorisees = ['HOSPITALISATION']
    else:
        destinations_autorisees = []

    orientations = Orientation.objects.filter(
        destination__in=destinations_autorisees,
        est_admis=False,
        hopital=hopital_user
    ).select_related(
        'consultation__triage__patient',
        'consultation__medecin'
    ).prefetch_related(
        'consultation__ordonnance_set__medicaments'
    )

    return render(request, 'back-end/orientation/liste_attente.html', {
        'orientations': orientations,
        'fonctionKey': role_obj.fonctionKey.roleName if role_obj else "Invité",
        'doit_saisir_compte_rendu': doit_saisir_compte_rendu
    })


#
# ================================================================================================
# HISTORIQUE DES DOSSIER ORIENTE ET TRAITE
# ===============================================================================================
@login_required
def service_historique_view(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonction_nom = role_obj.fonctionKey.roleName.strip().lower() if (role_obj and role_obj.fonctionKey) else ""
    fonctionKey = role_obj.fonctionKey.roleName if role_obj else "Invité"

    if 'infirmier' in fonction_nom:
        destinations_autorisees = ['SALLE_SOINS', 'BLOC_OPERATOIRE', 'ACCOUCHEMENT']
    elif 'pharmacien' in fonction_nom:
        destinations_autorisees = ['PHARMACIE']
    elif 'hospitalisation' in fonction_nom:
        destinations_autorisees = ['HOSPITALISATION']
    else:
        destinations_autorisees = ['BLOC_OPERATOIRE'] if 'bloc' in fonction_nom else []

    orientations = Orientation.objects.filter(
        destination__in=destinations_autorisees,
        est_admis=True,
        hopital=hopital_user
    ).order_by('-date_orientation')

    return render(request, 'back-end/orientation/historique.html', {
        'orientations': orientations,
        'fonctionKey': fonctionKey
    })

# 
# ===================================================================================================
# BLOC OPERATOIRE
# ===================================================================================================
@login_required
def gerer_bloc_operatoire(request, consultation_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        hopital=hopital_user
    )

    bloc, created = BlocOperatoire.objects.get_or_create(
        consultation=consultation,
        defaults={
            'constantes_pre_op': f"TA: {consultation.triage.tension_arterielle} | Pouls: {consultation.triage.frequence_cardiaque} | Temp: {consultation.triage.temperature}"
        }
    )

    prestations_chir = Prestation.objects.filter(categorie='CHIR')

    if request.method == 'POST':
        bloc.acte_realise = request.POST.get('acte_realise')
        bloc.statut = request.POST.get('statut', 'TERMINE')
        bloc.chirurgien = request.user

        prestation_id = request.POST.get('prestation_id')
        if prestation_id:
            bloc.prestation_id = prestation_id

        if bloc.statut == 'TERMINE':
            bloc.date_fin = timezone.now()

        bloc.save()
        messages.success(request, "Informations de bloc mises à jour avec succès.")
        return redirect('service_liste_attente')

    context = {
        'consultation': consultation,
        'bloc': bloc,
        'patient': consultation.triage.patient,
        'fonctionKey': fonctionKey,
        'prestations_chir': prestations_chir,
    }
    return render(request, 'back-end/bloc/saisir_compte_rendu.html', context)

#
# ==================================================================================================
# HISTORIQUE DU BLOC OPERATOIRE
# ==================================================================================================
@login_required
def historique_bloc_operatoire(request):
    # 1. Récupération de l'historique de base
    # On exclut les annulés et on optimise les accès aux relations (select_related)
    historique = BlocOperatoire.objects.exclude(statut='ANNULE').select_related(
        'consultation__triage__patient', 
        'chirurgien', 
        'prestation'
    ).order_by('-date_programmee')

    # 2. Recherche par nom de patient
    query = request.GET.get('q')
    if query:
        historique = historique.filter(consultation__triage__patient__noms__icontains=query)

    # 3. Calcul dynamique du reste à payer pour chaque opération
    # C'est ici que l'on vérifie combien a été payé pour chaque bloc individuellement
    for op in historique:
        prix_total = op.prestation.prix if op.prestation else Decimal('0.00')
        
        # Somme des paiements et des réductions pour ce bloc précis
        paiements_du_bloc = Paiement.objects.filter(bloc_op=op)
        total_verse = paiements_du_bloc.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
        total_reductions = paiements_du_bloc.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')
        
        # On injecte l'attribut calculé directement dans l'objet pour l'utiliser dans le template
        op.reste_a_payer = max(Decimal('0.00'), prix_total - (total_verse + total_reductions))

    # 4. Gestion des rôles utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    # 5. Préparation du contexte
    context = {
        'historique': historique,
        'query': query,
        'fonctionKey': fonctionKey
    }
    
    return render(request, 'back-end/bloc/historique_operations.html', context)



#
# ===========================================================================================================
# CAISSE POUR PAYER L'OPERATION
# ===========================================================================================================
@login_required
def encaisser_bloc(request, bloc_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    bloc = get_object_or_404(
        BlocOperatoire.objects.select_related('consultation__triage__patient', 'prestation'),
        id=bloc_id,
        consultation__hopital=hopital_user
    )
    consultation = bloc.consultation

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500')

    prix_chirurgie = bloc.prestation.prix if bloc.prestation else Decimal('0.00')
    paiements_bloc = Paiement.objects.filter(bloc_op=bloc)

    total_verse = paiements_bloc.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_reductions = paiements_bloc.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')

    reste_a_payer = max(Decimal('0.00'), prix_chirurgie - (total_verse + total_reductions))

    if request.method == 'POST':
        if reste_a_payer <= 0:
            messages.warning(request, "Ce bloc est déjà soldé.")
            return redirect('historique_paiements', patient_id=consultation.triage.patient.id)

        devise = request.POST.get('devise', 'USD')
        try:
            montant_recu = Decimal(request.POST.get('montant_verse', 0))
            reduction_usd = Decimal(request.POST.get('montant_reduction', 0))
        except:
            messages.error(request, "Format de montant invalide.")
            return redirect('encaisser_bloc', bloc_id=bloc.id)

        montant_verse_usd = montant_recu / taux if devise == 'CDF' else montant_recu
        total_a_deduire = montant_verse_usd + reduction_usd

        if total_a_deduire > (reste_a_payer + Decimal('0.01')):
            messages.error(request, f"Erreur : Le montant total ({total_a_deduire:.2f} USD) dépasse le reste à payer ({reste_a_payer:.2f} USD).")
            return redirect('encaisser_bloc', bloc_id=bloc.id)

        nouveau_reste = reste_a_payer - total_a_deduire

        Paiement.objects.create(
            patient=consultation.triage.patient,
            consultation=consultation,
            bloc_op=bloc,
            service='CHIRURGIE',
            montant_verse=montant_verse_usd,
            montant_reduction=reduction_usd,
            reste_a_payer=max(Decimal('0.00'), nouveau_reste),
            devise=devise,
            caissier=request.user,
            date_paiement=timezone.now()
        )

        messages.success(request, "Paiement du bloc opératoire enregistré avec succès.")
        return redirect('historique_paiements', patient_id=consultation.triage.patient.id)

    context = {
        'bloc': bloc,
        'prix_chirurgie': prix_chirurgie,
        'reste_a_payer': reste_a_payer,
        'taux': taux,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/caisse/encaisser_bloc.html', context)
#
# ====================================================================================================
# REDIGER RAPPORT PAR LE MEDECIN
# =====================================================================================================
@login_required
def rediger_compte_rendu(request, bloc_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    bloc = get_object_or_404(
        BlocOperatoire.objects.select_related('consultation__triage__patient', 'prestation'),
        id=bloc_id,
        consultation__hopital=hopital_user
    )

    if request.method == 'POST':
        bloc.acte_realise = request.POST.get('acte_realise')
        bloc.statut = 'TERMINE'
        bloc.date_fin = timezone.now()
        bloc.save()
        return redirect('service_historique')

    return render(request, 'back-end/bloc/rediger_rapport.html', {
        'bloc': bloc,
        'fonctionKey': fonctionKey
    })
#
# ===================================================================================================
# VOIR LE RAPPORT REDIGER
# ====================================================================================================
@login_required
def voir_rapport(request, bloc_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    bloc = get_object_or_404(
        BlocOperatoire.objects.select_related('consultation__triage__patient', 'prestation'),
        id=bloc_id,
        consultation__hopital=hopital_user
    )

    return render(request, 'back-end/bloc/voir_rapport.html', {
        'bloc': bloc,
        'fonctionKey': fonctionKey
    })

#
# =======================================================================================
# PRESTATION ACCOUCHEMENT  (saisir fiche accouchement apres acouchement)
# =======================================================================================
@login_required
def saisir_fiche_accouchement_view(request, consultation_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        hopital=hopital_user
    )

    prestations = Prestation.objects.filter(categorie='MAT', hopital=hopital_user)

    if request.method == 'POST':
        prestation_id = request.POST.get('prestation_id')
        type_acc = request.POST.get('type_accouchement')
        sexe_bebe = request.POST.get('sexe_bebe')
        poids_bebe = request.POST.get('poids_bebe')
        score_apgar = request.POST.get('score_apgar')
        notes = request.POST.get('notes')

        if not prestation_id or not type_acc or not poids_bebe:
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            return redirect('saisir_fiche_accouchement', consultation_id=consultation.id)

        try:
            prestation = get_object_or_404(Prestation, id=prestation_id, hopital=hopital_user, categorie='MAT')

            FicheAccouchement.objects.create(
                consultation=consultation,
                prestation=prestation,
                type_accouchement=type_acc,
                sexe_bebe=sexe_bebe,
                poids_bebe=poids_bebe,
                score_apgar=score_apgar if score_apgar else None,
                notes=notes,
                auteur=request.user
            )
            messages.success(request, "Fiche d'accouchement enregistrée avec succès.")
            return redirect('service_liste_attente')

        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement : {e}")

    return render(request, 'back-end/accouchement/saisir_fiche.html', {
        'consultation': consultation,
        'prestations': prestations,
        'fonctionKey': fonctionKey
    })

#
# ======================================================================================================
#
# ======================================================================================================
@login_required
def saisir_cr_accouchement_view(request, consultation_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        hopital=hopital_user
    )

    prestations = Prestation.objects.filter(categorie='MAT', hopital=hopital_user)

    if request.method == 'POST':
        prestation_id = request.POST.get('prestation_id')
        type_acc = request.POST.get('type_accouchement')
        details = request.POST.get('details_acte')

        if not prestation_id:
            messages.error(request, "Veuillez sélectionner un forfait de maternité.")
            return redirect('saisir_cr_accouchement', consultation_id=consultation.id)

        try:
            with transaction.atomic():
                prestation = get_object_or_404(
                    Prestation,
                    id=prestation_id,
                    categorie='MAT',
                    hopital=hopital_user
                )

                CompteRenduAccouchement.objects.create(
                    consultation=consultation,
                    prestation=prestation,
                    type_accouchement=type_acc,
                    details_acte=details,
                    auteur=request.user
                )

                orientation = consultation.orientation
                if orientation:
                    orientation.est_admis = True
                    orientation.save()

            messages.success(request, "Compte-rendu d'accouchement enregistré avec succès.")
            return redirect('service_liste_attente')

        except Exception as e:
            messages.error(request, f"Erreur critique : {str(e)}")

    return render(request, 'back-end/accouchement/saisir_cr.html', {
        'consultation': consultation,
        'prestations': prestations,
        'fonctionKey': fonctionKey
    })
#
# ====================================================================================================
# LISTE DES FICHES ACCOUCHEMENT 
# =====================================================================================================
@login_required
def liste_fiches_accouchement_view(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    query = request.GET.get('q', '')
    fiches = FicheAccouchement.objects.filter(
        consultation__hopital=hopital_user
    ).order_by('-date_creation')

    if query:
        fiches = fiches.filter(
            Q(consultation__triage__patient__noms__icontains=query) |
            Q(notes__icontains=query)
        )

    paginator = Paginator(fiches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'back-end/accouchement/liste_fiches.html', {
        'page_obj': page_obj,
        'query': query,
        'fonctionKey': fonctionKey
    })
#
# =====================================================================================================
# DETAIL DE LA FICHE D'ACCOUCHEMENT
# ===================================================================================================== 
@login_required
def detail_fiche_accouchement_view(request, fiche_id):
    fiche = get_object_or_404(FicheAccouchement, id=fiche_id)

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/accouchement/detail_fiche.html', {
        'fiche': fiche , 
        'fonctionKey' : fonctionKey
    })


#
# ======================================================================================================
#
# ======================================================================================================
@login_required
def liste_cr_accouchement_view(request):
    # Ajout de 'prestation' dans le select_related
    liste_cr = CompteRenduAccouchement.objects.select_related(
        'consultation__triage__patient', 'auteur', 'prestation'
    ).order_by('-date_creation')
    
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/accouchement/liste_cr.html', {
        'liste_cr': liste_cr,
        'fonctionKey': fonctionKey
    })

#
# ====================================================================================================
# PAYER ACCOUCHEMENT
# ====================================================================================================
@login_required
def payer_accouchement_view(request, cr_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    cr = get_object_or_404(
        CompteRenduAccouchement.objects.select_related('consultation__triage__patient', 'prestation'),
        id=cr_id,
        consultation__hopital=hopital_user
    )

    taux = ConfigurationHopital.get_taux()

    total_forfait = cr.prestation.prix
    paiements_precedents = Paiement.objects.filter(compte_rendu=cr)
    total_deja_paye = paiements_precedents.aggregate(Sum('montant_verse'))['montant_verse__sum'] or Decimal('0.00')

    reste_a_payer_usd = total_forfait - total_deja_paye

    if request.method == 'POST':
        montant_saisi = Decimal(request.POST.get('montant_verse', 0))
        montant_reduction = Decimal(request.POST.get('montant_reduction', 0))
        devise = request.POST.get('devise', 'USD')

        montant_en_usd = montant_saisi
        if devise == 'CDF':
            montant_en_usd = montant_saisi / taux

        if (montant_en_usd + montant_reduction) > reste_a_payer_usd:
            messages.error(request, f"Le montant saisi dépasse la dette restante ({reste_a_payer_usd:.2f} USD).")
        else:
            try:
                Paiement.objects.create(
                    patient=cr.consultation.triage.patient,
                    compte_rendu=cr,
                    service='MATERNITE',
                    montant_verse=montant_en_usd,
                    montant_reduction=montant_reduction,
                    devise=devise,
                    caissier=request.user,
                    date_paiement=timezone.now(),
                    reste_a_payer=max(Decimal('0.00'), reste_a_payer_usd - (montant_en_usd + montant_reduction))
                )
                messages.success(request, "Paiement enregistré avec succès.")
                return redirect('liste_cr_accouchement')
            except Exception as e:
                messages.error(request, f"Erreur système : {e}")

    return render(request, 'back-end/accouchement/payer_cr.html', {
        'cr': cr,
        'reste_a_payer': reste_a_payer_usd,
        'taux': taux,
        'fonctionKey': fonctionKey
    })

#
# ====================================================================================================
# VOIR LE COMPTE RENDU 
# ====================================================================================================
@login_required
def voir_cr_accouchement_view(request, consultation_id):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    cr = get_object_or_404(
        CompteRenduAccouchement.objects.select_related(
            'consultation__triage__patient',
            'prestation'
        ),
        consultation__id=consultation_id,
        consultation__hopital=hopital_user
    )

    return render(request, 'back-end/accouchement/voir_cr.html', {
        'cr': cr,
        'fonctionKey': fonctionKey
    })

# 
# =====================================================================================================
# ENREGISTRE LES PATIENTS DES ENTREPRISES
# =====================================================================================================
@login_required
def enregistrer_patient_entreprise(request):
    if request.method == 'POST':
        # On utilise un formulaire lié au modèle Patient
        form = PatientForm(request.POST)
        if form.is_valid():
            # On crée l'instance sans la sauvegarder immédiatement en BDD
            patient = form.save(commit=False)
            # On force le type à CONVENTIONNE comme demandé
            patient.type_patient = 'CONVENTIONNE'
            patient.save()
            
            messages.success(request, f"Le patient {patient.noms} a été enregistré avec succès.")
            return redirect('enregistrement_patient') # Remplacez par votre URL
        else:
            messages.error(request, "Erreur lors de l'enregistrement. Vérifiez les champs.")
    else:
        form = PatientForm()

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/patient/creer_patient_entreprise.html', {
        'form': form,
        'titre': "Enregistrer un patient d'entreprise" ,
        'fonctionKey' : fonctionKey
    })


#
# =================================================================================================
# NOUVELLE CONSULTATION
# =================================================================================================
@login_required
def creer_session_soins(request, patient_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if fonctionKey not in ['receptionniste', 'caissier', 'admin']:
        messages.error(request, "Accès refusé : droits insuffisants.")
        return redirect('liste_patients')

    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user)

    if not getattr(patient, 'fiche_payee', False):
        messages.error(request, "Le patient doit d'abord payer sa fiche d'ouverture.")
        return redirect('enregistrement_patient')

    if request.method == 'POST':
        seuil = timezone.now() - timedelta(seconds=10)
        doublon = SessionSoins.objects.filter(patient=patient, date_creation__gte=seuil).exists()
        if doublon:
            messages.warning(request, "Une session a déjà été créée très récemment pour ce patient.")
            return redirect('liste_sessions')

        prestation_ids = request.POST.getlist('prestations')
        if not prestation_ids:
            messages.error(request, "Veuillez sélectionner au moins une prestation.")
            return redirect('creer_session_soins', patient_id=patient.id)

        autorisees_qs = Prestation.objects.filter(hopital=hopital_user, categorie='CONS')
        if patient.sexe == 'F':
            autorisees_qs = autorisees_qs | Prestation.objects.filter(hopital=hopital_user, categorie='CONS_MAT')

        autorisees_ids = set(autorisees_qs.values_list('id', flat=True))

        for p_id in prestation_ids:
            if int(p_id) not in autorisees_ids:
                messages.error(request, "Erreur : Une prestation sélectionnée est invalide.")
                return redirect('creer_session_soins', patient_id=patient.id)

        try:
            with transaction.atomic():
                session = SessionSoins.objects.create(patient=patient, hopital=hopital_user)
                prestations = Prestation.objects.filter(id__in=prestation_ids, hopital=hopital_user)

                lignes = [
                    LigneFacture(session=session, prestation=p, prix_facture=p.prix, hopital=hopital_user)
                    for p in prestations
                ]
                LigneFacture.objects.bulk_create(lignes)

                messages.success(request, "Session créée avec succès.")
                return redirect('paiement_session', session_id=session.id)
        except Exception as e:
            messages.error(request, f"Erreur critique lors de la création : {str(e)}")

    if patient.sexe == 'M':
        prestations = Prestation.objects.filter(hopital=hopital_user, categorie='CONS')
    else:
        prestations = Prestation.objects.filter(hopital=hopital_user, categorie__in=['CONS', 'CONS_MAT'])

    return render(request, 'back-end/consultation/creer_session.html', {
        'patient': patient,
        'prestations': prestations,
        'fonctionKey': fonctionKey
    })
#
# ===================================================================================================================
# LISTE DES SESSIONS
# ===================================================================================================================
@login_required
def liste_sessions(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    user_hopital = role_obj.hopital if role_obj else None

    sessions = SessionSoins.objects.prefetch_related('items__prestation', 'paiements').all()

    if fonction_key != "admin" and user_hopital:
        sessions = sessions.filter(hopital=user_hopital)

    sessions = sessions.order_by('-date_creation')

    for session in sessions:
        paiements = session.paiements.all()
        total_paye = paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        total_red = paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0

        session.total_verse = total_paye
        session.total_reductions = total_red
        session.actuel_reste = max(0, session.total_a_payer - total_paye - total_red)

    return render(request, 'back-end/consultation/liste_sessions.html', {
        'sessions': sessions,
        'fonctionKey': fonction_key
    })
#
# ====================================================================================================================
# PAIEMENT DESE SESSION(CONSULTATION)
# ====================================================================================================================
@login_required
def payer_session(request, session_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        pk=session_id,
        hopital=hopital_user
    )

    taux = ConfigurationHopital.get_taux()

    if session.estpayee:
        messages.warning(request, "Cette session est déjà soldée.")
        return redirect('liste_sessions')

    if request.method == 'POST':
        try:
            montant_saisi = Decimal(request.POST.get('montant', 0))
            reduction = Decimal(request.POST.get('reduction', 0))
            devise = request.POST.get('devise', 'USD')

            montant_verse = montant_saisi / taux if devise == 'CDF' else montant_saisi

            Paiement.objects.create(
                session=session,
                patient=session.patient,
                service='SOIN',
                montant_verse=montant_verse,
                montant_reduction=reduction,
                devise='USD',
                caissier=request.user,
                hopital=hopital_user
            )

            messages.success(request, "Paiement et remise enregistrés avec succès.")
            return redirect('liste_sessions')
        except Exception as e:
            messages.error(request, f"Erreur lors du paiement : {str(e)}")

    total_deja_paye = session.paiements.aggregate(models.Sum('montant_verse'))['montant_verse__sum'] or 0
    total_reductions = session.paiements.aggregate(models.Sum('montant_reduction'))['montant_reduction__sum'] or 0
    reste_a_payer = max(0, session.totalapayer - total_deja_paye - total_reductions)
    reste_a_payer_cdf = float(reste_a_payer) * float(taux)

    return render(request, 'back-end/consultation/payer_session.html', {
        'session': session,
        'reste_a_payer': reste_a_payer,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'taux': taux,
        'fonctionKey': fonctionKey
    })

#
# ==============================================================================================
# DETAILS DE CONSULTATION 
# ==============================================================================================
@login_required
def detail_consultation(request, session_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        id=session_id,
        hopital=hopital_user
    )

    historique_signes = SigneVital.objects.filter(
        patient=session.patient,
        hopital=hopital_user
    ).order_by('-dateprelevement')

    return render(request, 'back-end/consultation/details.html', {
        'session': session,
        'historique_signes': historique_signes,
        'fonctionKey': fonctionKey
    })

#
# ===========================================================================================
# LISTE DES SESSIONS POUR INFIRMIER 
# ===========================================================================================
@login_required
def liste_sessions_infirmier(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    sessions = SessionSoins.objects.filter(
        hopital=hopital_user
    ).annotate(
        a_un_paiement=Exists(
            Paiement.objects.filter(session=OuterRef('pk'))
        )
    ).filter(
        a_un_paiement=True
    ).prefetch_related('items__prestation').order_by('-date_creation')

    return render(request, 'back-end/consultation/liste_sessions_infirmier.html', {
        'sessions': sessions,
        'fonctionKey': fonctionKey
    })
#
# ===========================================================================================
# SIGNE VITAUX RELIE PAR UNE NOUVEL CONSULTATION
# ===========================================================================================
@login_required
def saisir_signes_vitaux(request, session_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        id=session_id,
        hopital=hopital_user
    )

    if request.method == 'POST':
        form = SigneVitalForm(request.POST)
        if form.is_valid():
            signes = form.save(commit=False)
            signes.session = session
            signes.patient = session.patient
            signes.infirmier = request.user
            signes.hopital = hopital_user
            signes.save()
            return redirect('liste_sessions_infirmier')
    else:
        form = SigneVitalForm()

    return render(request, 'back-end/consultation/saisie_signes.html', {
        'form': form,
        'session': session,
        'fonctionKey': fonctionKey
    })



#
# ===============================================================================================
# PAIEMENT DES DETTES COTE VENTE MEDICAMENT 
# ===============================================================================================
@login_required
def ajouter_paiement_dette(request, paiement_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    paiement = get_object_or_404(Paiement, id=paiement_id, hopital=hopital_user)
    taux = Decimal(str(ConfigurationHopital.get_taux()))

    if request.method == 'POST':
        montant_saisi = Decimal(str(request.POST.get('montant') or '0'))
        devise_paiement = request.POST.get('devise_paiement')
        devise_dette = paiement.devise

        montant_converti = montant_saisi

        if devise_paiement != devise_dette:
            if devise_paiement == 'USD' and devise_dette == 'CDF':
                montant_converti = montant_saisi * taux
            elif devise_paiement == 'CDF' and devise_dette == 'USD':
                montant_converti = montant_saisi / taux

        montant_converti = montant_converti.quantize(Decimal('0.01'))

        if montant_converti > paiement.reste_a_payer:
            messages.error(
                request,
                f"Le montant saisi ({montant_saisi} {devise_paiement}) dépasse la dette restante ({paiement.reste_a_payer} {devise_dette})."
            )
            return redirect('liste_ventes')

        with transaction.atomic():
            paiement.reste_a_payer -= montant_converti
            paiement.montant_verse += montant_converti
            paiement.save()

        messages.success(request, "Dette mise à jour avec succès.")
        return redirect('liste_ventes')

    return render(request, 'back-end/pharmacie/ajouter_paiement_dette.html', {
        'paiement': paiement,
        'taux': taux,
        'fonctionKey': fonctionKey
    })
# 
# ===========================================================================================================
# ENREGISTREMENT DU PATIENT EXTERNE POUR LES EXAMENS 
# =========================================================================================================== 
@login_required
def enregistrer_client_externe(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        form = ClientExterneForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            if fonctionKey != 'admin' and user_hopital:
                client.hopital = user_hopital
            client.save()
            return redirect('creer_demande_examen', client_id=client.id)
    else:
        form = ClientExterneForm()

    return render(request, 'back-end/client/enregistrer_client.html', {
        'form': form,
        'fonctionKey': fonctionKey
    })

# 
# ===========================================================================================================
# ENREGISTREMENT DEMANDE EXAMEN EXTERNE POUR LES EXAMENS 
# ===========================================================================================================     

@login_required
def creer_demande_examen(request, client_id):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if fonctionKey != 'admin' and user_hopital:
        client = get_object_or_404(ClientExterne, id=client_id, hopital=user_hopital)
        prestations_labo = Prestation.objects.filter(categorie='LABO', hopital=user_hopital)
        prestations_radio = Prestation.objects.filter(categorie='RADIO', hopital=user_hopital)
        prestations_echo = Prestation.objects.filter(categorie='ECHO', hopital=user_hopital)
    else:
        client = get_object_or_404(ClientExterne, id=client_id)
        prestations_labo = Prestation.objects.filter(categorie='LABO')
        prestations_radio = Prestation.objects.filter(categorie='RADIO')
        prestations_echo = Prestation.objects.filter(categorie='ECHO')

    if request.method == 'POST':
        ids_prestations = request.POST.getlist('prestations')

        if ids_prestations:
            if fonctionKey != 'admin' and user_hopital:
                prestations_selectionnees = Prestation.objects.filter(
                    id__in=ids_prestations,
                    hopital=user_hopital
                )
            else:
                prestations_selectionnees = Prestation.objects.filter(id__in=ids_prestations)

            with transaction.atomic():
                demande = DemandeExamenExterne.objects.create(
                    client=client,
                    hopital=user_hopital if fonctionKey != 'admin' else client.hopital
                )
                demande.prestations.set(prestations_selectionnees)
                demande.total_a_payer = demande.prestations.aggregate(total=Sum('prix'))['total'] or Decimal('0.00')
                demande.save()

            return redirect('liste_demandes_externes')

    return render(request, 'back-end/client/creer_demande.html', {
        'client': client,
        'fonctionKey': fonctionKey,
        'prestations_labo': prestations_labo,
        'prestations_radio': prestations_radio,
        'prestations_echo': prestations_echo,
    })

# 
# ===========================================================================================================
# LISTE DES PATIENTS EXTERNE POUR LES EXAMENS 
# =========================================================================================================== 

@login_required
def liste_demandes_externes(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if fonctionKey != 'admin' and user_hopital:
        demandes = DemandeExamenExterne.objects.filter(hopital=user_hopital).order_by('-date_demande')
    else:
        demandes = DemandeExamenExterne.objects.all().order_by('-date_demande')

    return render(request, 'back-end/client/liste_demandes.html', {
        'demandes': demandes,
        'fonctionKey': fonctionKey
    })


#
# ========================================================================================
# LISTE DE DEMANDE EXTERNE
# ========================================================================================
@login_required
def liste_examens_technicien(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    if not role_obj or not role_obj.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    role_name = role_obj.fonctionKey.roleName.upper()
    user_hopital = role_obj.hopital

    cat_cible = None
    if 'LABO' in role_name:
        cat_cible = 'LABO'
    elif 'RADIO' in role_name:
        cat_cible = 'RADIO'
    elif 'ECHO' in role_name:
        cat_cible = 'ECHO'

    if not cat_cible:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    demandes = DemandeExamenExterne.objects.filter(
        hopital=user_hopital,
        prestations__categorie=cat_cible
    ).distinct().order_by('-date_demande')

    historique_technique = []

    for dem in demandes:
        examens_filtres = dem.prestations.filter(categorie=cat_cible)

        if examens_filtres.exists():
            historique_technique.append({
                'id': dem.id,
                'patient': dem.client.noms,
                'date': dem.date_demande,
                'examens': examens_filtres,
                'statut': dem.statut
            })

    return render(request, 'back-end/client/liste_examens_technicien.html', {
        'historique_technique': historique_technique,
        'fonctionKey': role_obj.fonctionKey.roleName,
        'cat_cible': cat_cible
    })

#
# =========================================================================================================
# RESULTAT EXAMEN 
# =========================================================================================================
@login_required
def saisir_rapport(request, demande_id, prestation_id):
    # 1. On récupère la demande globale et la prestation spécifique
    demande = get_object_or_404(DemandeExamenExterne, id=demande_id)
    prestation = get_object_or_404(Prestation, id=prestation_id)
    
    # 2. On récupère ou on crée l'objet résultat associé à ce couple (demande + prestation)
    # Cela évite les erreurs si le résultat n'a pas encore été initialisé
    resultat, created = ExamenExterneResultat.objects.get_or_create(
        demande=demande,
        prestation=prestation,
        defaults={'rapport': '', 'statut': 'EN_ATTENTE'}
    )
    
    # 3. Traitement du formulaire
    if request.method == 'POST':
        rapport_texte = request.POST.get('rapport')
        
        # Enregistrement des données
        resultat.rapport = rapport_texte
        resultat.statut = 'TERMINE'  # On valide l'examen
        resultat.save()
        
        # Optionnel : Vérification globale pour passer la demande en TERMINE si tous les examens sont faits
        # Si tu veux que la demande passe en "TERMINE" globalement quand tous les examens le sont :
        # if not demande.resultats_examens.filter(statut='EN_ATTENTE').exists():
        #     demande.statut = 'TERMINE'
        #     demande.save()
            
        return redirect('liste_examens_technicien')
        
    # 4. Affichage de la page

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/client/saisir_rapport.html', {
        'demande': demande,
        'prestation': prestation,
        'resultat': resultat ,
        'fonctionKey' : fonctionKey
    })

#
# ========================================================================================================
# HISTORIQUE DES RESULTATS EXTERNE 
# ========================================================================================================
@login_required
def historique_examen_externe_technicien(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    if not role_obj or not role_obj.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    role_name = role_obj.fonctionKey.roleName.upper()
    user_hopital = role_obj.hopital

    is_medecin = 'MEDECIN' in role_name or 'DOCTEUR' in role_name

    cat_cible = None
    if 'LABO' in role_name:
        cat_cible = 'LABO'
    elif 'RADIO' in role_name:
        cat_cible = 'RADIO'
    elif 'ECHO' in role_name:
        cat_cible = 'ECHO'

    if is_medecin:
        demandes = DemandeExamenExterne.objects.filter(
            hopital=user_hopital
        ).order_by('-date_demande')
    elif cat_cible:
        demandes = DemandeExamenExterne.objects.filter(
            hopital=user_hopital,
            prestations__categorie=cat_cible
        ).distinct().order_by('-date_demande')
    else:
        return render(request, 'back-end/error.html', {'message': "Accès non autorisé pour ce profil."})

    historique_technique = []

    for dem in demandes:
        tous_les_examens = dem.prestations.all()

        details_examens = []
        for p in tous_les_examens:
            res = ExamenExterneResultat.objects.filter(demande=dem, prestation=p).first()

            details_examens.append({
                'prestation': p,
                'statut': res.statut if res else 'EN_ATTENTE',
                'id_resultat': res.id if res else None,
                'rapport': res.rapport if res else None,
                'est_ma_categorie': is_medecin or (p.categorie == cat_cible)
            })

        historique_technique.append({
            'id': dem.id,
            'client': dem.client,
            'patient': dem.client.noms,
            'date': dem.date_demande,
            'details': details_examens,
            'medecin_demandeur': dem.medecin_demandeur if hasattr(dem, 'medecin_demandeur') else "Non spécifié",
            'type_urgence': getattr(dem, 'urgence', 'Standard')
        })

    return render(request, 'back-end/client/historique_examen_externe_technicien.html', {
        'historique_technique': historique_technique,
        'fonctionKey': role_obj.fonctionKey.roleName,
        'is_medecin': is_medecin,
        'cat_cible': cat_cible
    })
# 
# ==================================================================================
# PAIEMENT DES L'EXAMEN EXTERNE
# ==================================================================================
@login_required
def encaisser_examen_externe(request, demande_id):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if fonctionKey != 'admin' and user_hopital:
        demande = get_object_or_404(DemandeExamenExterne, id=demande_id, hopital=user_hopital)
    else:
        demande = get_object_or_404(DemandeExamenExterne, id=demande_id)

    client = demande.client
    taux = Decimal(str(ConfigurationHopital.get_taux()))

    stats = demande.paiements.aggregate(
        total_verse=Sum('montant_verse'),
        total_reduit=Sum('montant_reduction')
    )
    total_verse = stats['total_verse'] or Decimal('0')
    total_reduit = stats['total_reduit'] or Decimal('0')
    reste_a_payer = demande.total_a_payer - (total_verse + total_reduit)

    if request.method == 'POST':
        devise = request.POST.get('devise')
        montant_saisi = Decimal(request.POST.get('montant_verse', '0'))
        reduction = Decimal(request.POST.get('montant_reduction', '0'))

        montant_verse_usd = (montant_saisi / taux) if devise == 'CDF' else montant_saisi

        if (montant_verse_usd + reduction) > (reste_a_payer + Decimal('0.01')):
            return render(request, 'back-end/client/encaisser_examen.html', {
                'demande': demande,
                'client': client,
                'reste_a_payer': reste_a_payer,
                'taux': taux,
                'fonctionKey': fonctionKey,
                'prestations': demande.prestations.all(),
                'error': f"Le total dépasse le reste à payer ({reste_a_payer:.2f} $)."
            })

        if client is None:
            return render(request, 'back-end/client/encaisser_examen.html', {
                'demande': demande,
                'client': client,
                'reste_a_payer': reste_a_payer,
                'taux': taux,
                'fonctionKey': fonctionKey,
                'prestations': demande.prestations.all(),
                'error': "Aucun patient n'est lié à cette demande."
            })

        Paiement.objects.create(
            demande_examen_externe=demande,
            clientEx=client,
            service='EXAMEN_EXTERNE',
            montant_verse=montant_verse_usd,
            montant_reduction=reduction,
            caissier=request.user,
            devise=devise,
            hopital=user_hopital if fonctionKey != 'admin' else demande.hopital
        )

        return redirect('liste_facturation')

    return render(request, 'back-end/client/encaisser_examen.html', {
        'demande': demande,
        'client': client,
        'reste_a_payer': reste_a_payer,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'prestations': demande.prestations.all()
    })
#
# ======================================================================================
# LISTE DE FACTURATION 
# ======================================================================================
@login_required
def liste_facturation(request):
    taux_val = ConfigurationHopital.get_taux()
    taux = float(taux_val) if taux_val else 1.0
    decimal_field = DecimalField(max_digits=12, decimal_places=2)

    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    demandes = DemandeExamenExterne.objects.all()

    if fonctionKey != 'admin' and user_hopital:
        demandes = demandes.filter(hopital=user_hopital)

    demandes = demandes.annotate(
        total_verse=Coalesce(
            Sum('paiements__montant_verse', output_field=decimal_field),
            Value(0, output_field=decimal_field)
        ),
        total_reduit=Coalesce(
            Sum('paiements__montant_reduction', output_field=decimal_field),
            Value(0, output_field=decimal_field)
        )
    ).annotate(
        reste_usd=ExpressionWrapper(
            F('total_a_payer') - (F('total_verse') + F('total_reduit')),
            output_field=decimal_field
        )
    ).prefetch_related('prestations').order_by('-date_demande')

    return render(request, 'back-end/client/liste_facturation.html', {
        'demandes': demandes,
        'taux': taux,
        'fonctionKey': fonctionKey
    })

#
# ===============================================================================================
# IMPRIMER RESULTAT
# ===============================================================================================
@login_required
def imprimer_rapport_complet(request, demande_id):
    demande = get_object_or_404(DemandeExamenExterne, id=demande_id)
    # Récupération des paiements et résultats liés à cette demande
    paiements = demande.paiements.all()
    resultats = demande.resultats_examens.all()
    
    return render(request, 'back-end/client/imprimer_rapport.html', {
        'demande': demande,
        'paiements': paiements,
        'resultats': resultats,
    })



#
# ==================================================================================================
# IMPRIMER ORDONNANCE 
# ==================================================================================================
@login_required
def imprimer_ordonnance_urgence(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related('consultation__triage__patient', 'consultation__medecin').prefetch_related('medicaments'),
        pk=pk
    )
    return render(request, 'back-end/medecin/imprimer_ordonnance.html', {'ord': ordonnance})

#
# ==============================================================================================
# MODIFICATION ORDONNACE D'URGENCE
# ==============================================================================================
@login_required
def modifier_ordonnance_urgence(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related('consultation__triage__patient', 'consultation__medecin'),
        pk=pk
    )

    if request.method == 'POST':
        form = OrdonnanceFormUrgence(request.POST, instance=ordonnance)
        if form.is_valid():
            form.save()
            return redirect('liste_ordonnances_urgence')
    else:
        form = OrdonnanceFormUrgence(instance=ordonnance)

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/modifier_ordonnance_urgence.html', {
        'form': form,
        'ordonnance': ordonnance,
        'fonctionKey': fonctionKey
    })

#
# ===================================================================================
# LISTE DES CONVENTIONNES PAR ENTREPRISE
# ===================================================================================
@login_required
def liste_conventionnes_par_entreprise(request):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    patients_conventionnes = Patient.objects.filter(
        type_patient='CONVENTIONNE',
        hopital=hopital_user
    ).select_related('entreprise', 'hopital').order_by('-date_creation') if hopital_user else Patient.objects.none()

    entreprises_data = {}

    for patient in patients_conventionnes:
        entreprise = patient.entreprise if patient.entreprise else None
        entreprise_nom = entreprise.nom if entreprise else "Sans entreprise"

        if entreprise_nom not in entreprises_data:
            entreprises_data[entreprise_nom] = {
                'patients': [],
                'entreprise_obj': entreprise
            }

        entreprises_data[entreprise_nom]['patients'].append(patient)

    return render(request, 'back-end/entreprise/liste_conventionnes.html', {
        'entreprises_data': entreprises_data,
        'fonctionKey': fonctionKey
    })#
# ==========================================================================================
# PAEIMENT PAR ENTREPRISE LA DETTE 
# ==========================================================================================
@login_required
def payer_dette_entreprise(request, entreprise_id):
    # 1. Récupération de l'objet
    entreprise = get_object_or_404(Entreprise, pk=entreprise_id)

    # 2. Traitement du formulaire POST
    if request.method == "POST":
        try:
            # On récupère les données brutes
            montant = Decimal(request.POST.get("montant", "0"))
            devise = request.POST.get("devise", "USD")
            reduction = Decimal(request.POST.get("reduction", "0"))

            # Création du paiement (le calcul de la dette est géré dans models.py)
            Paiement.objects.create(
                entreprise=entreprise,
                service="ENTREPRISE",
                montant_verse=montant,
                montant_reduction=reduction,
                devise=devise,
                caissier=request.user
            )

            messages.success(request, "Paiement enregistré avec succès.")
            return redirect('payer_dette_entreprise', entreprise_id=entreprise.id)

        except Exception as e:
            messages.error(request, f"Erreur lors du traitement : {str(e)}")
            return redirect('payer_dette_entreprise', entreprise_id=entreprise.id)

    # 3. Préparation du contexte (GET)
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # On rafraîchit l'objet depuis la base pour être certain d'avoir la dernière dette
    entreprise.refresh_from_db()

    return render(request, 'back-end/entreprise/payer_dette.html', {
        'entreprise': entreprise,
        'dette': entreprise.dette_mensuelle,
        'fonctionKey': fonctionKey
    })

#
# ======================================================================================
# HISTORIQUE DE CHAQUE INFORMATIONS PAR ENTREPRISE 
# ======================================================================================
@login_required
def historique_entreprise(request, entreprise_id):
    entreprise = get_object_or_404(Entreprise, pk=entreprise_id)
    
    # Récupérer toutes les consultations des patients appartenant à cette entreprise
    # On suppose que ton modèle Patient a un ForeignKey vers Entreprise
    consultations = entreprise.patients.all().prefetch_related('consultations__paiements')
    
    # Récupérer l'historique complet des paiements de dette
    historique_paiements = entreprise.paiements.all().order_by('-date_paiement')
    
    return render(request, 'back-end/entreprise/historique.html', {
        'entreprise': entreprise,
        'consultations': consultations,
        'historique_paiements': historique_paiements
    })

#
# ========================================================================================
# LISTE DE PATIENTS FIDELE POUR VOIR LES DETTES
# =========================================================================================
@login_required
def liste_patients_fideles(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        try:
            consultation_id = request.POST.get('consultation_id')
            montant_verse = Decimal(request.POST.get('montant', 0))
            reduction = Decimal(request.POST.get('reduction', 0))
            devise = request.POST.get('devise', 'USD')

            cons = Consultation.objects.get(id=consultation_id)

            if fonctionKey != 'admin' and user_hopital and cons.hopital != user_hopital:
                messages.error(request, "Accès refusé.")
                return redirect('liste_patients_fideles')

            montant_en_usd = montant_verse
            if devise == 'CDF':
                taux = ConfigurationHopital.get_taux()
                montant_en_usd = montant_verse / taux

            Paiement.objects.create(
                consultation=cons,
                patient=cons.triage.patient,
                service='CONSULTATION',
                montant_verse=montant_en_usd,
                montant_reduction=reduction,
                devise=devise,
                date_paiement=timezone.now(),
                caissier=request.user,
            )
            messages.success(request, f"Paiement de {montant_verse} {devise} enregistré pour {cons.triage.patient.noms}.")
            return redirect('liste_patients_fideles')
        except Exception as e:
            messages.error(request, f"Erreur lors du paiement : {e}")

    mois = timezone.now().month
    annee = timezone.now().year

    consultations = Consultation.objects.filter(
        triage__patient__type_patient='FIDELE',
        date_creation__year=annee,
        date_creation__month=mois
    ).prefetch_related('paiements', 'examens__prestation')

    if fonctionKey != 'admin' and user_hopital:
        consultations = consultations.filter(hopital=user_hopital)

    patients_data = []
    for cons in consultations:
        patient = cons.triage.patient
        montant_total = sum(
            ex.prestation.prix * ex.quantite
            for ex in cons.examens.all()
            if ex.prestation
        )

        totaux = cons.paiements.aggregate(
            paye=Sum('montant_verse'),
            remise=Sum('montant_reduction')
        )

        paye = totaux['paye'] or 0
        remise = totaux['remise'] or 0
        reste_a_payer = montant_total - (paye + remise)

        patients_data.append({
            'consultation_id': cons.id,
            'patient': patient,
            'montant_total': montant_total,
            'reste_a_payer': max(Decimal('0.00'), reste_a_payer)
        })

    return render(request, 'back-end/patient/liste_fideles.html', {
        'patients_data': patients_data,
        'mois': mois,
        'annee': annee,
        'fonctionKey': fonctionKey
    })

#
# ================================================================================================
# PRESCRIRE ORDONNANCE POUR LE CLIENT EXTERNE 
# ================================================================================================
@login_required
def prescrire_ordonnance_client_externe(request, client_id):
    # Récupération du rôle + hopital de l'utilisateur
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    if not role or not role.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})
    fonctionKey = role.fonctionKey.roleName
    user_hopital = role.hopital

    # Récupération du client externe (on peut aussi s'assurer qu'il appartient au même hôpital)
    client = get_object_or_404(ClientExterne, id=client_id)

    # Vérifier que le client appartient au même hôpital (si vous enregistrez l'hôpital sur ClientExterne)
    if user_hopital and hasattr(client, 'hopital') and client.hopital and client.hopital != user_hopital and fonctionKey != 'admin':
        return render(request, 'back-end/error.html', {'message': "Accès refusé : client hors de votre hôpital."})

    if request.method == 'POST':
        try:
            with transaction.atomic():
                ordonnance = OrdonnanceExterne.objects.create(
                    client=client,
                    medecin=request.user,
                    note_globale=request.POST.get('note_globale', '').strip()
                )

                designations = request.POST.getlist('designation[]')
                posologies = request.POST.getlist('posologie[]')
                quantites = request.POST.getlist('quantite[]')

                for i in range(len(designations)):
                    designation = designations[i].strip()
                    if not designation:
                        continue
                    OrdonnanceItem.objects.create(
                        ordonnance=ordonnance,
                        designation=designation,
                        posologie=posologies[i].strip() if i < len(posologies) else "",
                        quantite=quantites[i].strip() if i < len(quantites) else ""
                    )

            messages.success(request, f"Ordonnance enregistrée pour {client.noms}.")
            return redirect('detail_client_externe', client_id=client.id)

        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors de l'enregistrement : {e}")
            return render(request, 'back-end/client/prescrire.html', {'client': client, 'fonctionKey': fonctionKey})

    # GET : affichage
    return render(request, 'back-end/client/prescrire_ordonnance_client_externe.html', {
        'client': client,
        'fonctionKey': fonctionKey
    })

#
# ==========================================================================================================
# DETAIL CLIENT EXTERNE
# ===========================================================================================================
@login_required
def detail_client_externe(request, client_id):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    if not role_obj or not role_obj.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    fonction_key = role_obj.fonctionKey.roleName
    user_hopital = role_obj.hopital

    if fonction_key != "admin":
        client = get_object_or_404(ClientExterne, id=client_id, hopital=user_hopital)
    else:
        client = get_object_or_404(ClientExterne, id=client_id)

    ordonnances = client.ordonnances_externes.all()

    context = {
        'client': client,
        'fonctionKey': fonction_key,
        'ordonnances': ordonnances,
    }

    return render(request, 'back-end/client/detail_client.html', context)

#
# ==========================================================================================================
# 
# ===========================================================================================================
@login_required
def liste_ordonnances_externes_client(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    user_hopital = role_obj.hopital if role_obj else None

    ordonnances = OrdonnanceExterne.objects.all()

    if fonction_key != "admin" and user_hopital:
        ordonnances = ordonnances.filter(hopital=user_hopital)

    ordonnances = ordonnances.order_by('-date_creation')

    return render(request, 'back-end/client/liste_ordonnances_client.html', {
        'ordonnances': ordonnances,
        'fonctionKey': fonction_key
    })


#
# ===========================================================================================================
# CONSULTATION ORDONNANCE EXTERNE 
# ============================================================================================================
@login_required
def consulter_ordonnance_externe(request, ordonnance_id):
    # 1. Récupération de l'ordonnance
    ordonnance = get_object_or_404(OrdonnanceExterne, id=ordonnance_id)
    
    # 2. Récupération du rôle pour le menu
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    context = {
        'ordonnance': ordonnance,
        'fonctionKey': fonction_key,
    }
    
    # 3. Retourne le template de consultation
    return render(request, 'back-end/client/consulter_ordonnance.html', context)

#
# ============================================================================================================
# MODIFICATION DE L'HOSPITALISATION 
# ============================================================================================================
@login_required
def modifier_hospitalisation_view(request, hospitalisation_id):
    # 1. Récupérer l'hospitalisation
    hospitalisation = get_object_or_404(Hospitalisation, id=hospitalisation_id)
    
    if request.method == 'POST':
        try:
            # Récupération des données du formulaire
            nouveau_lit_id = request.POST.get('lit_id')
            nouveau_motif = request.POST.get('motif_admission')
            nouveau_statut = request.POST.get('statut')
            nouvelle_date = request.POST.get('date_entree')
            
            # Gestion des lits : Si le lit change
            if int(nouveau_lit_id) != hospitalisation.lit.id:
                # Libérer l'ancien lit
                ancien_lit = hospitalisation.lit
                ancien_lit.est_occupe = False
                ancien_lit.save()
                
                # Occuper le nouveau lit
                nouveau_lit = Lit.objects.get(id=nouveau_lit_id)
                nouveau_lit.est_occupe = True
                nouveau_lit.save()
                
                hospitalisation.lit = nouveau_lit
            
            # Mise à jour des autres champs
            hospitalisation.date_entree = nouvelle_date
            hospitalisation.motif_admission = nouveau_motif
            hospitalisation.statut = nouveau_statut
            hospitalisation.save()
            
            messages.success(request, "Hospitalisation mise à jour avec succès.")
            return redirect('liste_hospitalisations')
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification : {str(e)}")

    # 2. Récupération des lits pour le template
    # On prend tous les lits libres OU le lit actuel du patient
    lits = Lit.objects.filter(est_occupe=False) | Lit.objects.filter(id=hospitalisation.lit.id)

    # 3. Gestion des droits d'accès (ton système de rôle)
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, 'back-end/hospitalisation/modifier_hospitalisation.html', {
        'hosp': hospitalisation,
        'lits': lits,
        'fonctionKey': fonction_key
    })


# 
# =========================================================================================
# ENREGISTRE CATEGORIE
# =========================================================================================
@login_required
def ajouter_categorie(request):
    if request.method == 'POST':
        form = CategorieForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('liste_categories') # Remplace par l'URL de ta liste
    else:
        form = CategorieForm()

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    return render(request, 'back-end/materiel/ajouter_categorie.html', {'form': form, 'fonctionKey':fonction_key})

# 
# ==========================================================================================
# LISTE DE CATEGORIE
# ==========================================================================================
@login_required
def liste_categories(request):
    # Récupère toutes les catégories enregistrées dans la base de données
    categories = CategorieEquipement.objects.all()

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    context = {
        'categories': categories ,
        'fonctionKey' : fonction_key
    }
    return render(request, 'back-end/materiel/liste_categories.html', context)


#
# ==========================================================================================
# ENREGISTRE EQUIPEMENT
# ==========================================================================================
@login_required
def ajouter_equipement(request):
    if request.method == 'POST':
        form = EquipementForm(request.POST)
        if form.is_valid():
            form.save() # Enregistre l'équipement avec sa catégorie choisie
            return redirect('liste_equipements')
    else:
        form = EquipementForm()
    
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, 'back-end/materiel/ajouter_equipement.html', {'form': form , 'fonctionKey' : fonction_key})

#
# ===============================================================================================
# LISTE DES EQUIPEMENT 
# ================================================================================================
@login_required
def liste_equipements(request):
    # Récupération des équipements
    equipements = Equipement.objects.all().order_by('-id')
    
    # Gestion de la fonction/rôle utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    context = {
        'equipements': equipements,
        'fonctionKey': fonction_key
    }
    return render(request, 'back-end/materiel/liste_equipements.html', context)

# 
# =======================================================================================================================
# ENREGISTRE HOPITAL
# =======================================================================================================================
@login_required
def enregistrer_hopital(request):
    if request.method == 'POST':
        form = HopitalForm(request.POST) # request.FILES si vous avez des images/fichiers
        if form.is_valid():
            form.save()
            messages.success(request, "Enregistrement effectué avec succès.")
            form = HopitalForm()
            # j vais mettre le lien pour la liste des hopitaux
        else:
            messages.error(request, "Erreur lors de l'enregistrement. Vérifiez les champs.")
    else:
        form = HopitalForm()

    # Gestion de la fonction/rôle utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, 'back-end/parametres/hopital.html', {'form': form , 'fonctionKey':fonction_key}) 

#
# ===================================================================================================
# LISTE DES HOPITAUX
# ===================================================================================================
@login_required
def liste_hopitaux(request):
    hopitaux = Hopital.objects.all()
    # Gestion de la fonction/rôle utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, 'back-end/parametres/hopital_liste.html', {'hopitaux': hopitaux, 'fonctionKey': fonction_key}) 
#
# =======================================================================================================================
# Modifier HOPITAL 
# =======================================================================================================================
@login_required
def modifier_hopital(request, id):
    hopital = get_object_or_404(Hopital, id=id) 
    if request.method == 'POST':
        form = HopitalForm(request.POST, instance=hopital)
        if form.is_valid():
            form.save()
            messages.success(request, "Hôpital modifié avec succès.")
            return redirect('hopital_liste')
    else:
        form = HopitalForm(instance=hopital)

    # Gestion de la fonction/rôle utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, 'back-end/parametres/hopital_modifier.html', {'form': form , 'fonctionKey':fonction_key})
#
# =======================================================================================================================
# SUPPRIME HOPITAL
# =======================================================================================================================
def supprimer_hopital(request, id):
    hopital = get_object_or_404(Hopital, id=id)
    hopital.delete()
    messages.success(request, "Hôpital supprimé avec succès.")
    return redirect('hopital_liste')

#
# ===================================================================================================================
# APPEL VIDEO 
# ===================================================================================================================
@login_required
def video_call_room(request, room_name):
    # Utilisez 'room_name' pour récupérer la salle
    room = get_object_or_404(VideoRoom, name=room_name)
    
    # Vérification de sécurité : l'utilisateur a-t-il le droit d'être là ?
    # Si vous avez un champ ManyToMany 'allowed_users'
    if request.user != room.created_by and not room.allowed_users.filter(id=request.user.id).exists():
        return HttpResponseForbidden("Vous n'avez pas accès à cette salle.")
    # Gestion de la fonction/rôle utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, "back-end/video_call/room.html", {
        "room": room,
        "room_name": room.name,
        'fonctionKey': fonction_key
    })


#
# ===================================================================================================
# DIRIGE VERS LA SALLE 
# ===================================================================================================
@login_required
def create_video_room(request):
    room_name = "salle-generale"
    room, created = VideoRoom.objects.get_or_create(
        name=room_name,
        defaults={"created_by": request.user}
    )
    return redirect("video_call_room", room_name=room.name)

@login_required
def add_colleague_to_room(request, room_id):
    room = get_object_or_404(VideoRoom, id=room_id) # Utilisez 'id' (ou le nom de votre clé primaire)

    if request.user != room.created_by:
        return HttpResponseForbidden()

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        colleague = get_object_or_404(User, id=user_id)
        room.allowed_users.add(colleague)
        # Redirection corrigée : on utilise le 'name' pour correspondre à la vue 'video_call_room'
        return redirect("video_call_room", room_name=room.name)

    colleagues = User.objects.filter(is_active=True).exclude(id=request.user.id)
    return render(request, "back-end/video_call/add_colleague.html", {
        "room": room,
        "colleagues": colleagues,
    })

#
# ========================================================================================================================
# CHANGE MOT DE PASSE 
# ========================================================================================================================
@login_required
def change_password(request):
    if request.method == "POST":
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Mot de passe modifié avec succès.")
            return redirect("change_password")
        else:
            messages.error(request, "Corrige les erreurs ci-dessous.")
    else:
        form = CustomPasswordChangeForm(request.user)

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(request, "back-end/accounts/change_password.html", {
        "form": form,
        "fonctionKey": fonction_key
    })

#
# ===========================================================================================================================
# ENREGISTRE RAPPORT 
# ===========================================================================================================================
@login_required
def creer_rapport_journalier(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital", "fonctionKey").first()
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    if request.method == "POST":
        form = RapportJournalierPersonnelForm(request.POST)
        if form.is_valid():
            rapport = form.save(commit=False)
            rapport.auteur = request.user
            rapport.hopital = hopital_user
            rapport.save()
            return redirect("liste_rapports_journaliers")
    else:
        form = RapportJournalierPersonnelForm()

    return render(
        request,
        "back-end/rapport/creer_rapport.html",
        {
            "form": form,
            "fonctionKey": fonction_key,
        }
    )
# ===========================================================================================================================
#  LISTE DES RAPPORTS
# ===========================================================================================================================
@login_required
def liste_rapports_journaliers(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    hopital_user = role_obj.hopital if role_obj else None

    rapports = RapportJournalierPersonnel.objects.select_related(
        "auteur", "hopital", "service"
    )

    if not (request.user.is_superuser or request.user.is_staff):
        rapports = rapports.filter(hopital=hopital_user)

    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")
    type_rapport = request.GET.get("type_rapport")

    if date_debut:
        rapports = rapports.filter(date_rapport__gte=date_debut)
    if date_fin:
        rapports = rapports.filter(date_rapport__lte=date_fin)
    if type_rapport:
        rapports = rapports.filter(type_rapport=type_rapport)

    rapports = rapports.order_by("-date_rapport", "-date_creation")

    return render(
        request,
        "back-end/rapport/liste_rapports_journaliers.html",
        {
            "rapports": rapports,
            "fonctionKey": fonction_key,
        }
    )

#
# ==========================================================================================================================
# PHARMACIE FILTRAGE ADMIN
# ==========================================================================================================================
@login_required
@staff_member_required
def admin_pharmacie_dashboard(request):
    """Dashboard admin pour la gestion de la pharmacie"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    
    # Si l'utilisateur a un rôle spécifique, on limite à son hôpital
    if fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        # Pharmacien ne voit que son hôpital
        hopital_selectionne = hopital_user
    elif hopital_id:
        # Admin peut filtrer par hôpital
        hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
    else:
        # Par défaut, on prend l'hôpital de l'utilisateur
        hopital_selectionne = hopital_user
    
    # Base queryset - Filtrage par hôpital
    produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
    lots = LotPharmacie.objects.filter(hopital=hopital_selectionne)
    sorties = SortiePharmacie.objects.filter(hopital=hopital_selectionne)
    mouvements = MouvementStock.objects.filter(hopital=hopital_selectionne)
    
    # Filtres par date
    if date_debut:
        lots = lots.filter(date_entree__gte=date_debut)
        sorties = sorties.filter(date_sortie__gte=date_debut)
        mouvements = mouvements.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        lots = lots.filter(date_entree__lte=date_fin)
        sorties = sorties.filter(date_sortie__lte=date_fin)
        mouvements = mouvements.filter(date_mouvement__lte=date_fin)
    
    # Statistiques globales
    total_produits = produits.count()
    total_lots = lots.count()
    total_sorties = sorties.count()
    
    # Récupérer le taux de change depuis ConfigurationHopital
    try:
        from .models import ConfigurationHopital
        config = ConfigurationHopital.objects.filter(hopital=hopital_selectionne).first()
        taux_change = config.taux if config and hasattr(config, 'taux') else 2500
    except:
        taux_change = 2500  # Valeur par défaut
    
    # Calcul du stock et valeur totale - USD et CDF
    stock_total = 0
    valeur_stock_achat_usd = 0
    valeur_stock_vente_usd = 0
    valeur_stock_achat_cdf = 0
    valeur_stock_vente_cdf = 0
    
    for produit in produits:
        entrees = LotPharmacie.objects.filter(
            produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_initiale'), 0))['total'] or 0
        
        sorties_prod = SortiePharmacie.objects.filter(
            lot__produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
        
        stock = entrees - sorties_prod
        stock_total += stock
        
        # Récupérer les prix
        prix_achat = float(produit.prix_achat_unitaire) if produit.prix_achat_unitaire else 0
        prix_vente = float(produit.prix_vente_unitaire) if produit.prix_vente_unitaire else 0
        
        # Vérifier la devise du produit
        if produit.devise == 'CDF':
            valeur_stock_achat_cdf += stock * prix_achat
            valeur_stock_vente_cdf += stock * prix_vente
        else:
            valeur_stock_achat_usd += stock * prix_achat
            valeur_stock_vente_usd += stock * prix_vente
    
    benefice_potentiel_usd = valeur_stock_vente_usd - valeur_stock_achat_usd
    benefice_potentiel_cdf = valeur_stock_vente_cdf - valeur_stock_achat_cdf
    
    # Produits en rupture
    produits_rupture = []
    for produit in produits:
        entrees = LotPharmacie.objects.filter(
            produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_initiale'), 0))['total'] or 0
        
        sorties_prod = SortiePharmacie.objects.filter(
            lot__produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
        
        if entrees - sorties_prod <= 0:
            produits_rupture.append(produit)
    
    # Top 10 produits les plus vendus
    top_ventes = []
    for produit in produits:
        quantite_vendue = SortiePharmacie.objects.filter(
            lot__produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
        
        if quantite_vendue > 0:
            prix_vente = float(produit.prix_vente_unitaire) if produit.prix_vente_unitaire else 0
            chiffre = quantite_vendue * prix_vente
            
            top_ventes.append({
                'produit': produit,
                'quantite_vendue': quantite_vendue,
                'chiffre_affaire': round(chiffre, 2),
                'devise': produit.devise
            })
    
    top_ventes = sorted(top_ventes, key=lambda x: x['quantite_vendue'], reverse=True)[:10]
    
    # Bénéfice réalisé (ventes effectives) - USD et CDF
    benefice_realise_usd = 0
    benefice_realise_cdf = 0
    chiffre_affaire_total_usd = 0
    chiffre_affaire_total_cdf = 0
    
    for sortie in sorties:
        prix_achat = float(sortie.lot.produit.prix_achat_unitaire) if sortie.lot.produit.prix_achat_unitaire else 0
        prix_vente = float(sortie.lot.produit.prix_vente_unitaire) if sortie.lot.produit.prix_vente_unitaire else 0
        benefice = (prix_vente - prix_achat) * sortie.quantite_vendue
        chiffre = prix_vente * sortie.quantite_vendue
        
        # Vérifier la devise
        if sortie.lot.produit.devise == 'CDF':
            benefice_realise_cdf += benefice
            chiffre_affaire_total_cdf += chiffre
        else:
            benefice_realise_usd += benefice
            chiffre_affaire_total_usd += chiffre
    
    # Liste des hôpitaux pour le filtre
    hopitaux = Hopital.objects.all()
    
    # Si l'utilisateur n'est pas admin global, on limite la liste
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'total_produits': total_produits,
        'total_lots': total_lots,
        'total_sorties': total_sorties,
        'stock_total': stock_total,
        # USD
        'valeur_stock_achat_usd': round(valeur_stock_achat_usd, 2),
        'valeur_stock_vente_usd': round(valeur_stock_vente_usd, 2),
        'benefice_potentiel_usd': round(benefice_potentiel_usd, 2),
        'benefice_realise_usd': round(benefice_realise_usd, 2),
        'chiffre_affaire_total_usd': round(chiffre_affaire_total_usd, 2),
        # CDF
        'valeur_stock_achat_cdf': round(valeur_stock_achat_cdf, 2),
        'valeur_stock_vente_cdf': round(valeur_stock_vente_cdf, 2),
        'benefice_potentiel_cdf': round(benefice_potentiel_cdf, 2),
        'benefice_realise_cdf': round(benefice_realise_cdf, 2),
        'chiffre_affaire_total_cdf': round(chiffre_affaire_total_cdf, 2),
        'taux_change': taux_change,
        'produits_rupture': len(produits_rupture),
        'top_ventes': top_ventes,
    }
    
    return render(request, 'back-end/pharmacie/pharmacie_dashboard.html', context)
#
# ==========================================================================================================================
# HISTORIQUE PHARMACIE ADMIN
# ==========================================================================================================================
@login_required
@staff_member_required
def admin_historique_stock(request, produit_id=None):
    """Historique complet des mouvements de stock par produit"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    type_mouvement = request.GET.get('type_mouvement')
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    
    # Si l'utilisateur a un rôle spécifique, on limite à son hôpital
    if fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        # Pharmacien ne voit que son hôpital
        hopital_selectionne = hopital_user
    elif hopital_id:
        # Admin peut filtrer par hôpital
        hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
    else:
        # Par défaut, on prend l'hôpital de l'utilisateur
        hopital_selectionne = hopital_user
    
    # Produit spécifique ou tous - AVEC GESTION D'ERREUR
    produit = None
    if produit_id:
        try:
            produit = ProduitPharmacie.objects.get(pk=produit_id, hopital=hopital_selectionne)
            mouvements = MouvementStock.objects.filter(lot__produit=produit)
        except ProduitPharmacie.DoesNotExist:
            messages.error(request, "Le produit demandé n'existe pas ou n'appartient pas à cet hôpital.")
            return redirect('admin_historique_stock')
    else:
        mouvements = MouvementStock.objects.all()
    
    # Filtres
    if hopital_selectionne:
        mouvements = mouvements.filter(hopital=hopital_selectionne)
    
    if date_debut:
        mouvements = mouvements.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        mouvements = mouvements.filter(date_mouvement__lte=date_fin)
    
    if type_mouvement:
        mouvements = mouvements.filter(type_mouvement=type_mouvement)
    
    # Tri par date décroissante
    mouvements = mouvements.select_related(
        'lot', 
        'lot__produit', 
        'effectue_par'
    ).order_by('-date_mouvement')
    
    # Calcul des totaux par produit
    resume_par_produit = {}
    for mouvement in mouvements:
        produit_nom = mouvement.lot.produit.nom
        if produit_nom not in resume_par_produit:
            resume_par_produit[produit_nom] = {
                'produit': mouvement.lot.produit,
                'entrees': 0,
                'sorties': 0,
                'ajustements': 0,
                'total': 0
            }
        
        if mouvement.type_mouvement == 'ENTREE':
            resume_par_produit[produit_nom]['entrees'] += mouvement.quantite_unites
            resume_par_produit[produit_nom]['total'] += mouvement.quantite_unites
        elif mouvement.type_mouvement == 'SORTIE':
            resume_par_produit[produit_nom]['sorties'] += abs(mouvement.quantite_unites)
            resume_par_produit[produit_nom]['total'] += mouvement.quantite_unites
        elif mouvement.type_mouvement == 'AJUSTEMENT':
            resume_par_produit[produit_nom]['ajustements'] += mouvement.quantite_unites
            resume_par_produit[produit_nom]['total'] += mouvement.quantite_unites
    
    # Liste des hôpitaux pour le filtre
    hopitaux = Hopital.objects.all()
    
    # Si l'utilisateur n'est pas admin global, on limite la liste
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    context = {
        'produit': produit,
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'type_mouvement': type_mouvement,
        'mouvements': mouvements,
        'resume_par_produit': resume_par_produit.values(),
    }
    
    return render(request, 'back-end/pharmacie/pharmacie_historique.html', context)
#
# ====================================================================================================
# BENEFICE PHARMACIE
# =====================================================================================================
@login_required
@staff_member_required
def admin_benefices_pharmacie(request):
    """Analyse détaillée des bénéfices"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    mois = request.GET.get('mois')
    annee = request.GET.get('annee', timezone.now().year)
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    
    # Si l'utilisateur a un rôle spécifique, on limite à son hôpital
    if fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        # Pharmacien ne voit que son hôpital
        hopital_selectionne = hopital_user
    elif hopital_id:
        # Admin peut filtrer par hôpital
        hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
    else:
        # Par défaut, on prend l'hôpital de l'utilisateur
        hopital_selectionne = hopital_user
    
    # Toutes les sorties - Filtrage par hôpital
    sorties = SortiePharmacie.objects.filter(hopital=hopital_selectionne)
    
    # Filtre par période
    if mois:
        sorties = sorties.filter(date_sortie__month=mois, date_sortie__year=annee)
    else:
        sorties = sorties.filter(date_sortie__year=annee)
    
    # Tous les produits - Filtrage par hôpital
    produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
    
    # Calcul par produit - USD et CDF
    benefices_par_produit = []
    for produit in produits:
        sorties_produit = sorties.filter(lot__produit=produit)
        quantite_vendue = sorties_produit.aggregate(
            total=Coalesce(Sum('quantite_vendue'), 0)
        )['total'] or 0
        
        if quantite_vendue > 0:
            prix_achat = float(produit.prix_achat_unitaire) if produit.prix_achat_unitaire else 0
            prix_vente = float(produit.prix_vente_unitaire) if produit.prix_vente_unitaire else 0
            benefice_unitaire = prix_vente - prix_achat
            benefice_total = benefice_unitaire * quantite_vendue
            chiffre_affaire = prix_vente * quantite_vendue
            marge = (benefice_total / chiffre_affaire * 100) if chiffre_affaire > 0 else 0
            
            benefices_par_produit.append({
                'produit': produit,
                'quantite_vendue': quantite_vendue,
                'prix_achat': round(prix_achat, 2),
                'prix_vente': round(prix_vente, 2),
                'benefice_unitaire': round(benefice_unitaire, 2),
                'benefice_total': round(benefice_total, 2),
                'chiffre_affaire': round(chiffre_affaire, 2),
                'marge': round(marge, 2),
                'devise': produit.devise  # USD ou CDF
            })
    
    # Tri par bénéfice total
    benefices_par_produit = sorted(
        benefices_par_produit, 
        key=lambda x: x['benefice_total'], 
        reverse=True
    )
    
    # Séparer USD et CDF
    benefices_usd = [x for x in benefices_par_produit if x['devise'] == 'USD']
    benefices_cdf = [x for x in benefices_par_produit if x['devise'] == 'CDF']
    
    # Totaux USD
    benefice_total_global_usd = sum(x['benefice_total'] for x in benefices_usd)
    chiffre_affaire_global_usd = sum(x['chiffre_affaire'] for x in benefices_usd)
    marge_moyenne_usd = (benefice_total_global_usd / chiffre_affaire_global_usd * 100) if chiffre_affaire_global_usd > 0 else 0
    
    # Totaux CDF
    benefice_total_global_cdf = sum(x['benefice_total'] for x in benefices_cdf)
    chiffre_affaire_global_cdf = sum(x['chiffre_affaire'] for x in benefices_cdf)
    marge_moyenne_cdf = (benefice_total_global_cdf / chiffre_affaire_global_cdf * 100) if chiffre_affaire_global_cdf > 0 else 0
    
    # Liste des hôpitaux pour le filtre
    hopitaux = Hopital.objects.all()
    
    # Si l'utilisateur n'est pas admin global, on limite la liste
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'mois': mois,
        'annee': annee,
        'benefices_par_produit': benefices_par_produit,
        # USD
        'benefice_total_global_usd': round(benefice_total_global_usd, 2),
        'chiffre_affaire_global_usd': round(chiffre_affaire_global_usd, 2),
        'marge_moyenne_usd': round(marge_moyenne_usd, 2),
        # CDF
        'benefice_total_global_cdf': round(benefice_total_global_cdf, 2),
        'chiffre_affaire_global_cdf': round(chiffre_affaire_global_cdf, 2),
        'marge_moyenne_cdf': round(marge_moyenne_cdf, 2),
    }
    
    return render(request, 'back-end/pharmacie/pharmacie_benefices.html', context)
#
# ======================================================================================================
# ALERT STOCK PHARMACIE
# ======================================================================================================
@login_required
@staff_member_required
def admin_alertes_stock(request):
    """Gestion des alertes de stock (rupture et seuil critique)"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    
    # Si l'utilisateur a un rôle spécifique, on limite à son hôpital
    if fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        # Pharmacien ne voit que son hôpital
        hopital_selectionne = hopital_user
    elif hopital_id:
        # Admin peut filtrer par hôpital
        hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
    else:
        # Par défaut, on prend l'hôpital de l'utilisateur
        hopital_selectionne = hopital_user
    
    # Tous les produits - Filtrage par hôpital
    produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
    
    alertes = []
    for produit in produits:
        # Calcul du stock - Version améliorée avec LotPharmacie.quantite_actuelle
        lots = LotPharmacie.objects.filter(
            produit=produit,
            hopital=hopital_selectionne
        )
        stock = sum(lot.quantite_actuelle or 0 for lot in lots)
        
        # Lots proches de péremption
        lots_peremption = LotPharmacie.objects.filter(
            produit=produit,
            hopital=hopital_selectionne,
            quantite_actuelle__gt=0
        ).filter(
            date_peremption__lte=timezone.now().date() + timedelta(days=30)
        ).count()
        
        # Vérifier si le modèle a un seuil_alerte, sinon définir une valeur par défaut
        seuil_alerte = getattr(produit, 'seuil_alerte', 10)
        
        # Déterminer le statut
        if stock <= 0:
            statut = 'rupture'
        elif stock <= seuil_alerte:
            statut = 'faible'
        elif lots_peremption > 0:
            statut = 'peremption'
        else:
            continue  # Pas d'alerte
        
        alertes.append({
            'produit': produit,
            'stock': stock,
            'seuil_alerte': seuil_alerte,
            'statut': statut,
            'lots_peremption': lots_peremption,
            'devise': produit.devise  # USD ou CDF
        })
    
    # Trier par statut (rupture d'abord, puis faible, puis péremption)
    statut_order = {'rupture': 0, 'faible': 1, 'peremption': 2}
    alertes = sorted(alertes, key=lambda x: statut_order.get(x['statut'], 3))
    
    # Liste des hôpitaux pour le filtre
    hopitaux = Hopital.objects.all()
    
    # Si l'utilisateur n'est pas admin global, on limite la liste
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    # Compter les alertes par type
    alertes_rupture = len([a for a in alertes if a['statut'] == 'rupture'])
    alertes_fortible = len([a for a in alertes if a['statut'] == 'faible'])
    alertes_peremption = len([a for a in alertes if a['statut'] == 'peremption'])
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'alertes': alertes,
        'alertes_rupture': alertes_rupture,
        'alertes_faible': alertes_fortible,
        'alertes_peremption': alertes_peremption,
        'total_alertes': len(alertes),
    }
    
    return render(request, 'back-end/pharmacie/pharmacie_alertes.html', context)

#
# ================================================================================================================
# HISTORIQUE DE PRODUIT ADMIN 
# =================================================================================================================

@login_required
@staff_member_required
def admin_historique_produit(request, produit_id):
    """Historique détaillé d'un produit spécifique"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    type_mouvement = request.GET.get('type_mouvement')
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    
    # Si l'utilisateur a un rôle spécifique, on limite à son hôpital
    if fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        # Pharmacien ne voit que son hôpital
        hopital_selectionne = hopital_user
    elif hopital_id:
        # Admin peut filtrer par hôpital
        hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
    else:
        # Par défaut, on prend l'hôpital de l'utilisateur
        hopital_selectionne = hopital_user
    
    # Récupérer le produit - AVEC GESTION D'ERREUR
    try:
        produit = ProduitPharmacie.objects.get(pk=produit_id, hopital=hopital_selectionne)
    except ProduitPharmacie.DoesNotExist:
        messages.error(request, f"Le produit demandé n'existe pas ou n'appartient pas à cet hôpital.")
        return redirect('admin_historique_stock')
    
    # Récupérer les mouvements pour ce produit
    mouvements = MouvementStock.objects.filter(lot__produit=produit, hopital=hopital_selectionne)
    
    # Filtres
    if date_debut:
        mouvements = mouvements.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        mouvements = mouvements.filter(date_mouvement__lte=date_fin)
    
    if type_mouvement:
        mouvements = mouvements.filter(type_mouvement=type_mouvement)
    
    # Tri par date décroissante
    mouvements = mouvements.select_related(
        'lot', 
        'lot__produit', 
        'effectue_par'
    ).order_by('-date_mouvement')
    
    # Calcul des totaux
    entrees = mouvements.filter(type_mouvement='ENTREE').aggregate(
        total=Coalesce(Sum('quantite_unites'), 0)
    )['total'] or 0
    
    sorties = mouvements.filter(type_mouvement='SORTIE').aggregate(
        total=Coalesce(Sum('quantite_unites'), 0)
    )['total'] or 0
    
    ajustements = mouvements.filter(type_mouvement='AJUSTEMENT').aggregate(
        total=Coalesce(Sum('quantite_unites'), 0)
    )['total'] or 0
    
    stock_net = entrees - sorties + ajustements
    
    # Liste des hôpitaux pour le filtre
    hopitaux = Hopital.objects.all()
    
    # Si l'utilisateur n'est pas admin global, on limite la liste
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    context = {
        'produit': produit,
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'type_mouvement': type_mouvement,
        'mouvements': mouvements,
        'entrees': entrees,
        'sorties': sorties,
        'ajustements': ajustements,
        'stock_net': stock_net,
    }
    
    return render(request, 'back-end/pharmacie/pharmacie_historique_produit.html', context)


#
# =======================================================================================================
# PAIEMENT VUE PAR ADMIN
# =======================================================================================================
@login_required
@staff_member_required
def admin_paiements_list(request):
    """Liste des paiements avec filtres par patient et prestation"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé. Aucun hôpital associé.")
        return redirect('dashboard')
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    patient_id = request.GET.get('patient')
    prestation_id = request.GET.get('prestation')
    service = request.GET.get('service')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    devise = request.GET.get('devise')
    
    # Gestion du filtre par hôpital selon le rôle
    hopital_selectionne = None
    est_admin_global = False
    
    # Vérifier si admin global
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        est_admin_global = True
        # Admin peut voir tous les hôpitaux ou filtrer
        if hopital_id:
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
        # Si pas de filtre, on ne filtre pas par hôpital (tous)
    else:
        # Caissier, comptable ne voient que leur hôpital
        hopital_selectionne = hopital_user
    
    # Requête de base
    if hopital_selectionne:
        paiements = Paiement.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin global voit TOUS les paiements
        paiements = Paiement.objects.all()
    
    # Filtres
    if patient_id:
        paiements = paiements.filter(patient_id=patient_id)
    
    if prestation_id:
        # Filtrer par prestation spécifique (consultation, session soins, etc.)
        from .models import Consultation, SessionSoins, DemandExamenExterne
        if prestation_id == 'consultation':
            consultations = Consultation.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else Consultation.objects.all()
            paiements = paiements.filter(consultation__in=consultations)
        elif prestation_id == 'session':
            sessions = SessionSoins.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else SessionSoins.objects.all()
            paiements = paiements.filter(session__in=sessions)
        elif prestation_id == 'examen_externe':
            examens = DemandExamenExterne.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else DemandExamenExterne.objects.all()
            paiements = paiements.filter(demande_examen_externe__in=examens)
    
    if service:
        paiements = paiements.filter(service=service)
    
    if date_debut:
        paiements = paiements.filter(date_paiement__date__gte=date_debut)
    
    if date_fin:
        paiements = paiements.filter(date_paiement__date__lte=date_fin)
    
    if devise:
        paiements = paiements.filter(devise=devise)
    
    # Tri par date décroissante
    paiements = paiements.select_related(
        'patient', 
        'caissier', 
        'hopital',
        'consultation',
        'session',
        'hospitalisation',
        'dossier_maternite',
        'demande_examen_externe'
    ).order_by('-date_paiement')
    
    # Stats
    if hopital_selectionne:
        total_usd = paiements.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
        total_cdf = paiements.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0
    else:
        total_usd = Paiement.objects.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
        total_cdf = Paiement.objects.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0
    
    # Liste des hôpitaux pour le filtre (admin global voit TOUS)
    if est_admin_global:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk)
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'paiements': paiements,
        'total_usd': round(total_usd, 2),
        'total_cdf': round(total_cdf, 2),
        'patient_id': patient_id,
        'prestation_id': prestation_id,
        'service': service,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'devise': devise,
        'SERVICES': Paiement.SERVICES,
        'est_admin_global': est_admin_global,
    }
    
    return render(request, 'back-end/paiements/paiements_list.html', context)

#
# ===============================================================================================================
# SUPPRESSION DU PAIEMENT PAR L'ADMIN
# ===============================================================================================================
@login_required
@staff_member_required
def admin_paiement_delete(request, paiement_id):
    """Supprimer un paiement - Admin global uniquement"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé.")
        return redirect('dashboard')
    
    # Vérifier si admin ou caissier principal
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur', 'admin_caisse']:
        messages.error(request, "Vous n'avez pas la permission de supprimer des paiements.")
        return redirect('admin_global_paiements_list')
    
    # Récupérer le paiement
    try:
        paiement = Paiement.objects.get(pk=paiement_id)
    except Paiement.DoesNotExist:
        messages.error(request, "Paiement non trouvé.")
        return redirect('admin_global_paiements_list')
    
    # Sauvegarder les infos avant suppression
    service = paiement.service
    montant = paiement.montant_verse
    devise = paiement.devise
    hopital_paiement = paiement.hopital
    
    # --- ANNULER LES EFFETS DU PAIEMENT ---
    
    # Si Fiche patient
    if service == 'FICHE' and paiement.patient:
        paiement.patient.fiche_payee = False
        paiement.patient.save()
    
    # Si Consultation
    elif service == 'CONSULTATION' and paiement.consultation:
        paiement.consultation.consultation_payee = False
        paiement.consultation.save()
    
    # Si Carte de fidélité
    elif service == 'CARTE_FIDELITE' and paiement.patient:
        paiement.patient.a_carte_fidelite = False
        paiement.patient.save()
    
    # Si Hospitalisation
    elif paiement.hospitalisation:
        total_due = Decimal(str(paiement.hospitalisation.cout_total))
        autres_paiements = paiement.hospitalisation.paiements.exclude(pk=paiement_id)
        total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        total_deja_reduit = autres_paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
        nouveau_reste = max(0, total_due - total_deja_reduit - total_deja_verse)
        paiement.hospitalisation.reste_a_payer = nouveau_reste
        paiement.hospitalisation.est_payee = (nouveau_reste <= 0)
        paiement.hospitalisation.save()
    
    # Si Session Soins
    elif paiement.session:
        autres_paiements = paiement.session.paiements.exclude(pk=paiement_id)
        total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        total_deja_reduit = autres_paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
        nouveau_reste = max(0, paiement.session.total_a_payer - total_deja_reduit - total_deja_verse)
        paiement.session.reste_a_payer = nouveau_reste
        paiement.session.est_payee = (nouveau_reste <= 0)
        paiement.session.save()
    
    # Si Examen Externe
    elif paiement.demande_examen_externe:
        total_due = paiement.demande_examen_externe.total_a_payer
        autres_paiements = paiement.demande_examen_externe.paiements.exclude(pk=paiement_id)
        total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        nouveau_reste = max(0, total_due - total_deja_verse)
        if nouveau_reste > 0:
            paiement.demande_examen_externe.statut = 'EN_ATTENTE'
        paiement.demande_examen_externe.save()
    
    # Si Maternité
    elif service == 'MATERNITE' and paiement.dossier_maternite:
        autres_paiements = paiement.dossier_maternite.paiements.exclude(pk=paiement_id)
        if autres_paiements.exists():
            total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            if total_deja_verse < paiement.dossier_maternite.cout_total:
                paiement.dossier_maternite.est_paye = False
        else:
            paiement.dossier_maternite.est_paye = False
        paiement.dossier_maternite.save()
    
    # Si Entreprise
    elif service == 'ENTREPRISE' and paiement.entreprise:
        montant_usd = montant
        if devise == 'CDF':
            from .models import ConfigurationHopital
            taux = ConfigurationHopital.get_taux()
            montant_usd = montant / taux
        total_a_rembourser = montant_usd + paiement.montant_reduction
        paiement.entreprise.dette_mensuelle = paiement.entreprise.dette_mensuelle + total_a_rembourser
        paiement.entreprise.save()
    
    # Si Bloc Opératoire
    elif paiement.bloc_op:
        autres_paiements = paiement.bloc_op.paiements.exclude(pk=paiement_id)
        if autres_paiements.exists():
            total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            if total_deja_verse < paiement.bloc_op.cout_total:
                paiement.bloc_op.est_payee = False
        else:
            paiement.bloc_op.est_payee = False
        paiement.bloc_op.save()
    
    # Si Compte Rendu (Maternité)
    elif paiement.compte_rendu:
        autres_paiements = Paiement.objects.filter(compte_rendu=paiement.compte_rendu).exclude(pk=paiement_id)
        if autres_paiements.exists():
            total_deja_verse = autres_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            if total_deja_verse < paiement.compte_rendu.cout_total:
                paiement.compte_rendu.est_paye = False
        else:
            paiement.compte_rendu.est_paye = False
        paiement.compte_rendu.save()
    
    # Supprimer la facture associée
    try:
        facture = Facture.objects.get(paiement=paiement)
        facture.delete()
    except Facture.DoesNotExist:
        pass
    
    # Enregistrer le journal de suppression
    try:
        from .models import JournalAudit
        JournalAudit.objects.create(
            user=request.user,
            action='SUPPRESSION_PAIEMENT',
            details=f"Paiement supprimé: {service} - {montant} {devise} - Hôpital: {hopital_paiement.nomH if hopital_paiement else 'N/A'}",
            hopital=hopital_paiement
        )
    except:
        pass
    
    # --- SUPPRIMER LE PAIEMENT ---
    paiement.delete()
    
    messages.success(
        request, 
        f"Paiement supprimé avec succès ! {service} - {montant} {devise}"
    )
    
    return redirect('admin_global_paiements_list')
#
# =======================================================================================================
# DETAIL PAIEMENT ADMIN
# =======================================================================================================
@login_required
@staff_member_required
def admin_paiement_detail(request, paiement_id):
    """Détail d'un paiement spécifique"""
    
    # Récupération du rôle de l'utilisateur connecté
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    
    hopital_user = role_obj.hopital if role_obj else None
    fonction_key = role_obj.fonctionKey if role_obj else None
    fonction_key_name = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # Vérification des permissions
    if not hopital_user:
        messages.error(request, "Accès non autorisé.")
        return redirect('dashboard')
    
    # Vérifier si admin
    if fonction_key and fonction_key.roleName.lower() not in ['admin', 'super_admin', 'directeur', 'admin_caisse', 'comptable']:
        messages.error(request, "Vous n'avez pas la permission de voir ce paiement.")
        return redirect('admin_payments_list')
    
    # Récupérer le paiement
    try:
        paiement = Paiement.objects.select_related(
            'patient',
            'caissier',
            'hopital',
            'consultation',
            'session',
            'hospitalisation',
            'dossier_maternite',
            'demande_examen_externe',
            'bloc_op',
            'compte_rendu',
            'entreprise',
            'clientEx'
        ).get(pk=paiement_id)
    except Paiement.DoesNotExist:
        messages.error(request, "Paiement non trouvé.")
        return redirect('admin_payments_list')
    
    # Récupérer la facture associée
    facture = None
    try:
        facture = Facture.objects.get(paiement=paiement)
    except Facture.DoesNotExist:
        pass
    
    # Récupérer les autres paiements liés au même service
    autres_paiements = Paiement.objects.none()
    
    if paiement.patient:
        autres_paiements = Paiement.objects.filter(patient=paiement.patient).exclude(pk=paiement_id)
    elif paiement.hospitalisation:
        autres_paiements = Paiement.objects.filter(hospitalisation=paiement.hospitalisation).exclude(pk=paiement_id)
    elif paiement.session:
        autres_paiements = Paiement.objects.filter(session=paiement.session).exclude(pk=paiement_id)
    elif paiement.demande_examen_externe:
        autres_paiements = Paiement.objects.filter(demande_examen_externe=paiement.demande_examen_externe).exclude(pk=paiement_id)
    elif paiement.dossier_maternite:
        autres_paiements = Paiement.objects.filter(dossier_maternite=paiement.dossier_maternite).exclude(pk=paiement_id)
    
    context = {
        'paiement': paiement,
        'facture': facture,
        'autres_paiements': autres_paiements,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
    }
    
    return render(request, 'back-end/paiements/paiement_detail.html', context)

#
# ===========================================================================================================================
# ===========================================================================================================================
from django.views.decorators.http import require_http_methods
def detect_intent(question):
    q = question.lower()

    if any(x in q for x in [
        "combien de consultations",
        "nombre de consultations",
        "a été consulté",
        "consulté combien",
        "nombre fois consulté"
    ]):
        return "consultations_patient"

    if any(x in q for x in [
        "total payé",
        "paiement",
        "combien a payé",
        "montant payé"
    ]):
        return "paiements_patient"

    if any(x in q for x in [
        "reste à payer",
        "reste payer",
        "solde",
        "dette"
    ]):
        return "reste_a_payer"

    if any(x in q for x in [
        "examens",
        "examens en attente",
        "examens réalisés"
    ]):
        return "examens_patient"

    if any(x in q for x in [
        "historique complet",
        "tout l'historique",
        "résumé complet",
        "vue complète"
    ]):
        return "historique_complet"

    return "unknown"


@login_required
@require_http_methods(["GET", "POST"])
def assistant_questions_view(request):
    if request.method == "GET":
        patients = Patient.objects.all().order_by("noms")
        return render(request, "back-end/assistant/questions.html", {"patients": patients})

    question = request.POST.get("question", "").strip()
    patient_id = request.POST.get("patient_id", "").strip()

    if not question:
        return JsonResponse({
            "success": False,
            "intent": "empty",
            "message": "La question est vide."
        }, status=400)

    patient = None
    if patient_id:
        patient = get_object_or_404(Patient, pk=patient_id)

    intent = detect_intent(question)

    if intent == "unknown":
        return JsonResponse({
            "success": False,
            "intent": "unknown",
            "message": "Je n'ai pas compris la question. Essaie de demander les consultations, paiements, reste à payer ou historique complet."
        }, status=200)

    if not patient:
        return JsonResponse({
            "success": False,
            "intent": intent,
            "message": "Veuillez sélectionner un patient pour cette question."
        }, status=400)

    consultations_qs = Consultation.objects.filter(triage__patient=patient)
    paiements_qs = Paiement.objects.filter(patient=patient)
    examens_qs = DemandeExamen.objects.filter(consultation__triage__patient=patient)
    sessions_qs = SessionSoins.objects.filter(patient=patient)

    if intent == "consultations_patient":
        total = consultations_qs.count()
        last = consultations_qs.order_by("-datecreation").first()

        data = {
            "patient": patient.noms,
            "code_patient": patient.codepatient,
            "total_consultations": total,
            "derniere_consultation": last.datecreation.strftime("%d/%m/%Y %H:%M") if last else None,
            "dernier_medecin": last.medecin.username if last and last.medecin else None,
        }

        answer = f"Le patient {patient.noms} a été consulté {total} fois."
        if last:
            answer += f" La dernière consultation date du {last.datecreation.strftime('%d/%m/%Y à %H:%M')}."

        return JsonResponse({
            "success": True,
            "intent": intent,
            "message": answer,
            "answer": answer,
            "data": data
        })

    if intent == "paiements_patient":
        total_usd = paiements_qs.filter(devise="USD").aggregate(total=Sum("montantverse"))["total"] or Decimal("0")
        total_cdf = paiements_qs.filter(devise="CDF").aggregate(total=Sum("montantverse"))["total"] or Decimal("0")
        total_reste = paiements_qs.aggregate(total=Sum("resteapayer"))["total"] or Decimal("0")

        data = {
            "patient": patient.noms,
            "nombre_paiements": paiements_qs.count(),
            "total_usd": float(total_usd),
            "total_cdf": float(total_cdf),
            "reste_total": float(total_reste),
        }

        answer = (
            f"Le patient {patient.noms} a {paiements_qs.count()} paiements enregistrés. "
            f"Total payé: {total_usd} USD et {total_cdf} CDF."
        )

        return JsonResponse({
            "success": True,
            "intent": intent,
            "message": answer,
            "answer": answer,
            "data": data
        })

    if intent == "reste_a_payer":
        total_reste = paiements_qs.aggregate(total=Sum("resteapayer"))["total"] or Decimal("0")

        data = {
            "patient": patient.noms,
            "reste_total": float(total_reste),
        }

        answer = f"Le reste à payer pour {patient.noms} est de {total_reste}."

        return JsonResponse({
            "success": True,
            "intent": intent,
            "message": answer,
            "answer": answer,
            "data": data
        })

    if intent == "examens_patient":
        total_examens = examens_qs.count()
        en_attente = examens_qs.filter(statut="ENATTENTE").count()
        termines = examens_qs.filter(statut="TERMINE").count()

        data = {
            "patient": patient.noms,
            "total_examens": total_examens,
            "examens_en_attente": en_attente,
            "examens_termines": termines,
        }

        answer = (
            f"Le patient {patient.noms} a {total_examens} examens, "
            f"dont {en_attente} en attente et {termines} terminés."
        )

        return JsonResponse({
            "success": True,
            "intent": intent,
            "message": answer,
            "answer": answer,
            "data": data
        })

    if intent == "historique_complet":
        total_consultations = consultations_qs.count()
        total_paiements = paiements_qs.count()
        total_examens = examens_qs.count()
        total_sessions = sessions_qs.count()

        total_usd = paiements_qs.filter(devise="USD").aggregate(total=Sum("montantverse"))["total"] or Decimal("0")
        total_cdf = paiements_qs.filter(devise="CDF").aggregate(total=Sum("montantverse"))["total"] or Decimal("0")
        total_reste = paiements_qs.aggregate(total=Sum("resteapayer"))["total"] or Decimal("0")

        data = {
            "patient": patient.noms,
            "code_patient": patient.codepatient,
            "consultations": total_consultations,
            "paiements": total_paiements,
            "examens": total_examens,
            "sessions": total_sessions,
            "total_usd": float(total_usd),
            "total_cdf": float(total_cdf),
            "reste_total": float(total_reste),
        }

        answer = (
            f"Résumé de {patient.noms} : {total_consultations} consultations, "
            f"{total_paiements} paiements, {total_examens} examens et {total_sessions} sessions de soins."
        )

        return JsonResponse({
            "success": True,
            "intent": intent,
            "message": answer,
            "answer": answer,
            "data": data
        })

    return JsonResponse({
        "success": False,
        "intent": "unknown",
        "message": "Question non prise en charge."
    }, status=200)