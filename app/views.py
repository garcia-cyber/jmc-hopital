from django.shortcuts import render , redirect , get_object_or_404
from .forms import *
from .models import *
from django.contrib.auth import authenticate , login as auth_login , logout ,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm ,UserChangeForm
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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.dateparse import parse_datetime


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
        # L'instance permet de mettre à jour l'objet existant au lieu d'en créer un nouveau
        form = PrestationForm(request.POST, instance=prestation)
        if form.is_valid():
            form.save()
            messages.success(request, f"La prestation '{prestation.libelle}' a été mise à jour.")
        else:
            messages.error(request, "Erreur lors de la mise à jour. Vérifiez les données.")
            
    return redirect('gestion_prestations')

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

    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            try:
                patient = form.save(commit=False)
                patient.created_by = request.user

                if hopital_user:
                    patient.hopital = hopital_user
                else:
                    messages.error(request, "Impossible d'enregistrer : votre compte n'est rattaché à aucun hôpital.")
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

    patients = Patient.objects.all().select_related(
        'entreprise', 'created_by', 'hopital'
    ).order_by('-date_creation')

    fonctionKey = user_fonction.fonctionKey.roleName if (user_fonction and user_fonction.fonctionKey) else "Invité"

    return render(request, 'back-end/patient/enregistrement_patient.html', {
        'patients': patients,
        'form': form,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
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
    
    # 🛠️ CORRECTION 1 : Suppression des 11 heures de décalage artificiel
    # Django gère déjà le fuseau horaire via les filtres de template ou l'heure locale
    date_reelle = paiement.date_paiement 

    # 🛠️ CORRECTION 2 : Traçabilité des examens spécifiques à ce paiement
    examens_associes = []
    if paiement.consultation and paiement.service in ['LABO', 'RADIO', 'ECHOGRAPHIE']:
        # On extrait les examens payés (statut libéré) liés à cette consultation précise
        examens_payes = paiement.consultation.examens.filter(
            statut__in=['EN_COURS', 'TERMINE']
        ).select_related('prestation')
        
        for exam in examens_payes:
            examens_associes.append({
                'libelle': exam.prestation.libelle,
                'prix': exam.prestation.prix
            })

    context = {
        'paiement': paiement,
        'patient': paiement.patient,
        'date_paiement_fix': date_reelle,
        'examens_ticket': examens_associes,  # Envoyé au template du ticket
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
                    consultation_obj.save()

                    DemandeExamen.objects.filter(consultation=consultation_obj, statut='EN_ATTENTE').delete()
                    for e_id in examens_ids:
                        prestation = get_object_or_404(Prestation, id=e_id, hopital=hopital_user)
                        qty_value = request.POST.get(f'qty_{e_id}', 1)

                        DemandeExamen.objects.create(
                            consultation=consultation_obj,
                            prestation=prestation,
                            quantite=qty_value,
                            statut='EN_ATTENTE'
                        )

                    if any(n.strip() for n in noms_medocs if n):
                        ordonnance, _ = Ordonnance.objects.get_or_create(
                            consultation=consultation_obj,
                            type_ordonnance='URGENCE'
                        )
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
                                    statut='EN_COURS'
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

    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else None

    context = {
        'triage': triage,
        'form': form,
        'examens_disponibles': examens_disponibles,
        'consultation': consultation,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/consultation_medecin.html', context)





# 30
# ==================================================================================================
# MEDECIN  LISTE DES EXAMENS CONSULTER
# ==================================================================================================
@login_required
def liste_consultations_terminees(request):
    # Optimisation de la requête avec le bon nom de relation : 'examens'
    consultations = Consultation.objects.select_related(
        'triage__patient',      
        'medecin'               
    ).prefetch_related(
        'examens__prestation'  # Utilise 'examens' car related_name='examens'
    ).order_by('-date_creation')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None
    
    context = {
        'consultations': consultations,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/medecin/liste_consultations.html', context)

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
    if not role_user or not role_user.fonctionKey:
        return redirect('dashboard')

    hopital_user = role_user.hopital
    nom_role = role_user.fonctionKey.roleName.lower()
    fonctionKey = role_user.fonctionKey.roleName

    consultations_payees = Consultation.objects.filter(
        examens__isnull=False,
        triage__patient__hopital=hopital_user
    ).distinct().select_related('triage__patient', 'medecin').prefetch_related('examens__prestation')

    historique_technique = []

    for cons in consultations_payees:
        patient = cons.triage.patient
        examens_query = cons.examens.all()
        examens_filtrés = []

        for exam in examens_query:
            cat = str(exam.prestation.categorie).upper()

            if patient.type_patient == 'SIMPLE':
                paiement_examen = Paiement.objects.filter(
                    patient=patient,
                    consultation=cons,
                    service__in=['LABO', 'ECHO', 'RADIO', 'EXAMENS'],
                    montant_verse__gt=0,
                    hopital=hopital_user
                ).exists()
                if not paiement_examen:
                    continue

            if ('labo' in nom_role and cat == 'LABO') or \
               (('echo' in nom_role or 'echographe' in nom_role) and cat == 'ECHO') or \
               (('radio' in nom_role or 'radiologue' in nom_role) and cat == 'RADIO'):

                examens_filtrés.append({
                    'id_examen': exam.id,
                    'libelle': exam.prestation.libelle,
                    'est_deja_fait': (exam.statut == 'TERMINE')
                })

        if examens_filtrés:
            a_des_examens_en_attente = any(not ex['est_deja_fait'] for ex in examens_filtrés)

            info_pat = {
                'nom': patient.noms,
                'code': patient.code_patient,
                'type': patient.get_type_patient_display(),
                'genre': patient.get_sexe_display(),
                'age': patient.age,
                'info_financiere': None
            }

            if patient.type_patient == 'CONVENTIONNE' and patient.entreprise:
                info_pat['info_financiere'] = f"Entreprise: {patient.entreprise.nom}"
            elif patient.type_patient == 'FIDELE':
                info_pat['info_financiere'] = "Patient Fidèle"
            elif patient.type_patient == 'SIMPLE':
                info_pat['info_financiere'] = "Examen affiché car paiement partiel effectué"

            historique_technique.append({
                'consultation_id': cons.id,
                'patient': info_pat,
                'examens': examens_filtrés,
                'medecin': cons.medecin.username if cons.medecin else "Généraliste",
                'tout_traite': not a_des_examens_en_attente
            })

    context = {
        'historique_technique': historique_technique,
        'examens_presents': len(historique_technique) > 0,
        'titre_page': "Examens à réaliser",
        'fonctionKey': fonctionKey
    }

    return render(request, 'back-end/technique/liste_examens_payes.html', context)



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
    # --- GESTION DES DATES --- 
    maintenant = timezone.now()
    
    # Aujourd'hui à minuit (00:00:00)
    debut_aujourdhui = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Début de la semaine (7 jours glissants)
    debut_semaine = debut_aujourdhui - timedelta(days=7)
    
    # Début du mois (Le 1er du mois en cours à 00:00:00)
    debut_mois = debut_aujourdhui.replace(day=1)

    # --- 1. CALCUL DES ENTRÉES GLOBALES (PAIEMENTS - TOUT HISTORIQUE) ---
    total_usd = Paiement.objects.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0.00
    total_cdf = Paiement.objects.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0.00

    # --- 2. CALCUL DES SORTIES GLOBALES (DÉPENSES - TOUT HISTORIQUE) ---
    depense_totale_usd = Depense.objects.filter(devise='USD').aggregate(total=Sum('montant'))['total'] or 0.00
    depense_totale_cdf = Depense.objects.filter(devise='CDF').aggregate(total=Sum('montant'))['total'] or 0.00

    # --- 3. CALCUL DU SOLDE RESTANT REEL EN CAISSE ---
    restant_usd = float(total_usd) - float(depense_totale_usd)
    restant_cdf = float(total_cdf) - float(depense_totale_cdf)

    # --- 4. STATISTIQUES DES ENTRÉES PAR PÉRIODES (USD et CDF) ---
    # Aujourd'hui
    recette_aujourdhui_usd = Paiement.objects.filter(date_paiement__gte=debut_aujourdhui, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0.00
    recette_aujourdhui_cdf = Paiement.objects.filter(date_paiement__gte=debut_aujourdhui, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0.00

    # Cette Semaine
    recette_semaine_usd = Paiement.objects.filter(date_paiement__gte=debut_semaine, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0.00
    recette_semaine_cdf = Paiement.objects.filter(date_paiement__gte=debut_semaine, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0.00

    # Ce Mois
    recette_mois_usd = Paiement.objects.filter(date_paiement__gte=debut_mois, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0.00
    recette_mois_cdf = Paiement.objects.filter(date_paiement__gte=debut_mois, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0.00

    # --- 5. CALCUL DES ENTRÉES PAR SERVICE ET PAR DEVISE (TOUT HISTORIQUE) ---
    services_stats = []
    for code, nom_service in Paiement.SERVICES:
        usd_service = Paiement.objects.filter(service=code, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0.00
        cdf_service = Paiement.objects.filter(service=code, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0.00
        
        services_stats.append({
            'nom': nom_service,
            'usd': usd_service,
            'cdf': cdf_service
        })

    # --- 6. LISTE DES PAIEMENTS COMPLETS ---
    tous_les_paiements = Paiement.objects.select_related('patient', 'caissier').order_by('-date_paiement')

    # Extraction du rôle pour la sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    # --- 7. ENVOI AU TEMPLATE ---
    context = {
        # Entrées globales (Historique total des paiements reçus)
        'total_usd': total_usd,
        'total_cdf': total_cdf,
        
        # Sorties globales (Historique total des dépenses effectuées)
        'depense_totale_usd': depense_totale_usd,
        'depense_totale_cdf': depense_totale_cdf,
        
        # Net physique restant dans le coffre (Entrées - Sorties)
        'restant_usd': restant_usd,
        'restant_cdf': restant_cdf,
        
        # Stats temporelles des entrées : USD
        'aujourdhui_usd': recette_aujourdhui_usd,
        'semaine_usd': recette_semaine_usd,
        'mois_usd': recette_mois_usd,
        
        # Stats temporelles des entrées : CDF
        'aujourdhui_cdf': recette_aujourdhui_cdf,
        'semaine_cdf': recette_semaine_cdf,
        'mois_cdf': recette_mois_cdf,
        
        # Tables et meta
        'services_stats': services_stats,
        'paiements': tous_les_paiements,
        'fonctionKey': fonctionKey,
        'titre_page': "Journal de Caisse & Finances - Moyanoli"
    }
    return render(request, 'back-end/finance/dashboard_finance.html', context)

# ==================================================================================================
# #41 : FINANCE GESTION DE DETTE 
# ==================================================================================================
@login_required
def creer_depense(request):
    # Extraction du rôle pour la sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    if request.method == 'POST':
        form = DepenseForm(request.POST)
        if form.is_valid():
            # 1. On crée l'objet en mémoire sans le sauvegarder immédiatement en BDD
            depense = form.save(commit=False)
            # 2. On lui attribue automatiquement l'utilisateur connecté comme auteur
            depense.auteur = request.user
            
            # --- VÉRIFICATION STRICTE DU SOLDE DISPONIBLE ---
            devise_saisie = depense.devise  # USD ou CDF
            
            # On force tout en float pour sécuriser les calculs mathématiques
            montant_demande_float = float(depense.montant)

            # Calcule toutes les entrées (Paiements) pour cette devise
            res_entrees = Paiement.objects.filter(devise=devise_saisie).aggregate(
                total=Coalesce(Sum('montant_verse'), 0, output_field=DecimalField())
            )['total']
            
            # Calcule toutes les sorties (Dépenses) déjà validées pour cette devise
            res_sorties = Depense.objects.filter(devise=devise_saisie).aggregate(
                total=Coalesce(Sum('montant'), 0, output_field=DecimalField())
            )['total']

            # Conversion mathématique brute et sécurisée en float
            total_entrees_float = float(res_entrees) if res_entrees else 0.0
            total_sorties_float = float(res_sorties) if res_sorties else 0.0

            # Calcul du solde en float (Plus aucun risque de conflit)
            solde_disponible_float = total_entrees_float - total_sorties_float

            # Blocage manuel si la somme demandée est supérieure à la caisse
            if montant_demande_float > solde_disponible_float:
                form.add_error(None, f"Opération refusée. Solde de caisse insuffisant en {devise_saisie}. Disponible : {solde_disponible_float:.2f} {devise_saisie}. Montant demandé : {montant_demande_float:.2f} {devise_saisie}.")
            else:
                try:
                    # 3. On force l'exécution du clean() du modèle au cas où d'autres validations existent
                    depense.full_clean()
                    depense.save()
                    
                    # Message de succès et redirection vers la bonne vue de journal
                    messages.success(request, "La dépense a été enregistrée avec succès !")
                    return redirect('dashboard_finance_depense')
                    
                except ValidationError as e:
                    # 4. Si une autre validation du modèle échoue, on récupère l'erreur pour l'afficher
                    if hasattr(e, 'message_dict'):
                        for field, errors in e.message_dict.items():
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
    # 1. Gestion du rôle pour la sidebar Moyanoli
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    # 2. Filtrage temporel (Aujourd'hui, Cette semaine, Ce mois)
    maintenant = timezone.now()
    debut_aujourdhui = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    debut_semaine = debut_aujourdhui - timezone.timedelta(days=maintenant.weekday())
    debut_mois = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- ENTRÉES (PAIEMENTS) ---
    paiements_tous = Paiement.objects.all().order_by('-date_paiement')

    # Utilisation de Decimal('0.00') et output_field pour éviter le mélange de types
    zero_decimal = Decimal('0.00')

    # Statistiques temporelles des entrées
    recettes_stats = Paiement.objects.aggregate(
        auj_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='USD')), zero_decimal, output_field=DecimalField()),
        auj_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='CDF')), zero_decimal, output_field=DecimalField()),
        sem_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='USD')), zero_decimal, output_field=DecimalField()),
        sem_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='CDF')), zero_decimal, output_field=DecimalField()),
        mois_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='USD')), zero_decimal, output_field=DecimalField()),
        mois_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='CDF')), zero_decimal, output_field=DecimalField()),
    )

    # Totaux globaux des entrées
    total_entrees = Paiement.objects.aggregate(
        usd=Coalesce(Sum('montant_verse', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant_verse', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    # --- SORTIES (DÉPENSES) ---
    total_depenses = Depense.objects.aggregate(
        usd=Coalesce(Sum('montant', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    # --- CALCUL DU SOLDE NET EN COFFRE ---
    restant_usd = total_entrees['usd'] - total_depenses['usd']
    restant_cdf = total_entrees['cdf'] - total_depenses['cdf']

    # --- VENTILATION PAR SERVICE ---
    services_liste = ['FICHE', 'LABO', 'ECHOGRAPHIE', 'RADIO']
    services_stats = []
    for s in services_liste:
        s_usd = Paiement.objects.filter(service=s, devise='USD').aggregate(t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField()))['t']
        s_cdf = Paiement.objects.filter(service=s, devise='CDF').aggregate(t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField()))['t']
        services_stats.append({'nom': s, 'usd': s_usd, 'cdf': s_cdf})

    context = {
        'titre_page': "Journal Général de Caisse",
        'fonctionKey': fonctionKey,
        'paiements': paiements_tous,
        
        # Variables Recettes Temporelles
        'aujourdhui_usd': recettes_stats['auj_usd'],
        'aujourdhui_cdf': recettes_stats['auj_cdf'],
        'semaine_usd': recettes_stats['sem_usd'],
        'semaine_cdf': recettes_stats['sem_cdf'],
        'mois_usd': recettes_stats['mois_usd'],
        'mois_cdf': recettes_stats['mois_cdf'],
        
        # Variables Bilan Coffre-Fort
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
    # 1. Traitement du formulaire (POST)
    if request.method == 'POST' and request.POST.get('action') == 'enregistrer_ordonnance':
        consultation_id = request.POST.get('consultation_id')
        diagnostic = request.POST.get('diagnostic_final')
        type_ord = request.POST.get('type_ordonnance')
        
        # Données orientation
        destination = request.POST.get('destination')
        observation_orient = request.POST.get('observation_orientation')
        
        # Données médicaments
        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')
        
        # Récupération de la consultation
        consultation = Consultation.objects.filter(id=consultation_id).first()
        
        if consultation:
            try:
                with transaction.atomic():
                    # A. Mise à jour diagnostic
                    consultation.diagnostic_final = diagnostic
                    consultation.save()
                    
                    # B. Création ordonnance
                    ordonnance = Ordonnance.objects.create(
                        consultation=consultation,
                        type_ordonnance=type_ord
                    )
                    
                    # C. Création médicaments
                    for nom, pos, dur in zip(noms, posologies, durees):
                        if nom.strip():
                            Medicament.objects.create(
                                ordonnance=ordonnance,
                                nom=nom,
                                posologie=pos,
                                duree=dur
                            )
                    
                    # D. Logique d'orientation et Hospitalisation
                    if destination:
                        # Gestion spécifique si hospitalisation
                        if destination == 'Hospitalisation':
                            lit_id = request.POST.get('lit_id')
                            date_entree = request.POST.get('date_entree')
                            motif_admission = request.POST.get('motif_admission')
                            
                            if lit_id:
                                Hospitalisation.objects.create(
                                    patient=consultation.patient,
                                    lit_id=lit_id,
                                    date_entree=date_entree if date_entree else timezone.now(),
                                    motif_admission=motif_admission if motif_admission else diagnostic,
                                    statut='EN_COURS'
                                )
                        
                        # Enregistrement de l'objet Orientation pour l'historique
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

    # 2. Affichage de la liste (GET)
    # Filtre sur examens terminés et optimisation des requêtes
    consultations_en_attente = Consultation.objects.filter(
        examens__statut='TERMINE'
    ).prefetch_related('examens', 'ordonnance_set').distinct()

    # Récupération des lits disponibles
    lits_disponibles = Lit.objects.filter(est_occupe=False)

    # Récupération de la fonctionKey pour le contrôle d'accès/menu
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None 
    
    # Rendu final avec tout le contexte nécessaire
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
    if request.method == 'POST':
        form = TypeChambreForm(request.POST)
        if form.is_valid():
            type_chambre = form.save()
            messages.success(request, f"Le type de chambre '{type_chambre.libelle}' a été enregistré.")
            # Redirection logique et fluide vers l'étape 2 (Ajout d'une pièce physique)
            return redirect('ajouter_chambre') 
    else:
        form = TypeChambreForm()
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/hospitalisation/type_chambre_form.html', {'form': form , 'fonctionKey':fonctionKey})


# --------------------------------------------------------------------------------------------------
# VUE : Deuxième étape de la configuration de l'infrastructure de soins.
# FONCTION : Gère l'enregistrement des chambres physiques et de leurs prix par nuitée. Elle bloque
#            l'accès et réoriente l'utilisateur vers l'étape 1 si aucune catégorie n'existe en base.
# --------------------------------------------------------------------------------------------------
@login_required
def ajouter_chambre(request):
    """ Étape 2 : Enregistrer une chambre physique """
    # Sécurité métier : Empêche l'enregistrement d'une chambre orpheline sans type associé.
    if not TypeChambre.objects.exists():
        messages.warning(request, "Vous devez d'abord créer un Type de chambre avant d'ajouter une chambre.")
        return redirect('ajouter_type_chambre')

    if request.method == 'POST':
        form = ChambreForm(request.POST)
        if form.is_valid():
            chambre = form.save()
            messages.success(request, f"La chambre {chambre.nom} a été enregistrée.")
            # Redirection logique et fluide vers l'étape 3 (Ajout du mobilier / des lits)
            return redirect('ajouter_lit')
    else:
        form = ChambreForm()
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role else None

    return render(request, 'back-end/hospitalisation/chambre_form.html', {'form': form, 'fonctionKey':fonctionKey})


# --------------------------------------------------------------------------------------------------
# VUE : Troisième et dernière étape de la configuration de l'infrastructure.
# FONCTION : Ajoute les unités d'accueil individuelles (Lits) dans les chambres. Gère la double 
#            possibilité de valider la saisie ou d'enchaîner sur un enregistrement en série.
# --------------------------------------------------------------------------------------------------
@login_required
def ajouter_lit(request):
    """ Étape 3 : Enregistrer un lit dans une chambre """
    # Sécurité métier : Interdit de créer un lit s'il n'y a aucun local physique pour le recevoir.
    if not Chambre.objects.exists():
        messages.warning(request, "Vous devez d'abord créer une chambre avant d'y ajouter des lits.")
        return redirect('ajouter_chambre')

    if request.method == 'POST':
        form = LitForm(request.POST)
        if form.is_valid():
            lit = form.save()
            # CORRECTION : Remplacé .nom_ou_code par .nom_lit
            messages.success(request, f"Le lit '{lit.nom_lit}' a bien été ajouté à la {lit.chambre}.")
            
            # Optimisation UX
            if 'ajouter_autre' in request.POST:
                return redirect('ajouter_lit')
            return redirect('dashboard_chambres')
    else:
        form = LitForm()
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/hospitalisation/lit_form.html', {'form': form , 'fonctionKey':fonctionKey})


# --------------------------------------------------------------------------------------------------
# VUE : Point d'entrée d'action unitaire et asynchrone (ou par redirection directe).
# FONCTION : Permet aux infirmiers ou gestionnaires d'annuler une occupation ou de bloquer temporairement
#            un lit à la volée depuis l'interface visuelle sans passer par un formulaire d'édition complet.
# --------------------------------------------------------------------------------------------------
@login_required
def toggle_statut_lit(request, lit_id):
    """ Action rapide pour occuper/libérer un lit depuis le dashboard """
    lit = get_object_or_404(Lit, id=lit_id)
    # Bascule booléenne de l'état d'occupation du lit
    lit.est_occupe = not lit.est_occupe
    lit.save()
    messages.info(request, f"Le statut du lit {lit.nom_ou_code} a été modifié.")
    return redirect('dashboard_chambres')


# =====================================================================================================
# REDIGE ORDONNANCE
# =====================================================================================================
@login_required
def enregistrer_ordonnance_view(request, triage_id):
    triage = get_object_or_404(SigneVital, id=triage_id)
    consultation = get_object_or_404(Consultation, triage=triage)
    
    
    # Récupération des examens liés à cette consultation
    examens_termines = DemandeExamen.objects.filter(consultation=consultation, statut='TERMINE')

    if request.method == 'POST':
        form = OrdonnanceForm(request.POST)
        
        # Récupération des listes du formulaire
        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        if form.is_valid():
            try:
                with transaction.atomic():
                    ordonnance = form.save(commit=False)
                    ordonnance.consultation = consultation
                    ordonnance.save()
                    
                    # Enregistrement des lignes médicaments
                    for n, p, d in zip(noms, posologies, durees):
                        if n.strip():
                            LigneMedicament.objects.create(
                                ordonnance=ordonnance,
                                nom_medicament=n,
                                posologie=p,
                                duree=d
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
        'examens_termines': examens_termines, # C'est ici que l'info arrive dans le HTML
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
    
    # --- GESTION DES ACTIONS (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Action pour stopper TOUTE l'ordonnance ou un médicament
        if action == 'stopper_medicament':
            ligne_id = request.POST.get('ligne_id')
            motif = request.POST.get('motif_arret', 'Arrêté par le médecin')
            
            if ligne_id and ligne_id.isdigit():
                ligne = LigneMedicament.objects.filter(id=int(ligne_id)).first()
                if ligne:
                    ligne.statut = 'STOPPE'
                    ligne.motif_arret = motif
                    ligne.date_modification = timezone.now()
                    ligne.save()
                    messages.warning(request, f"Le médicament '{ligne.nom_medicament}' a été stoppé.")
            return redirect(request.path_info)

    # --- REQUÊTE GET : AFFICHAGE DEPUIS LE MODÈLE ORDONNANCE ---
    # On récupère toutes les ordonnances avec le patient lié, et on pré-charge ses médicaments
    ordonnances_medecin = Ordonnance.objects.select_related(
        'consultation__triage__patient'
    ).prefetch_related(
        'medicaments'
    ).order_by('-date_prescrite')

    # Gestion du rôle utilisateur pour la sidebar
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

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
    # Récupération du rôle pour le contexte (optimisation : on évite la requête si user n'est pas authentifié)
    fonctionKey = None
    if request.user.is_authenticated:
        role = Fonction.objects.filter(userKey=request.user).first()
        if role and role.fonctionKey:
            fonctionKey = role.fonctionKey.roleName

    if request.method == 'POST':
        form = HospitalisationForm(request.POST)
        if form.is_valid():
            patient = form.cleaned_data.get('patient')
            
            # Vérification de sécurité : le patient a-t-il payé sa fiche ?
            if not patient.fiche_payee:
                messages.error(request, "Impossible d'admettre ce patient : fiche non payée.")
                return render(request, 'back-end/hospitalisation/admettre.html', {
                    'form': form, 
                    'fonctionKey': fonctionKey
                })

            # Sauvegarde
            try:
                hospitalisation = form.save()
                messages.success(request, "Admission réussie et lit réservé.")
                return redirect('liste_hospitalisations')
            except Exception as e:
                messages.error(request, f"Une erreur est survenue lors de l'enregistrement : {str(e)}")
        else:
            messages.error(request, "Erreur lors de l'admission. Veuillez vérifier les champs du formulaire.")
    else:
        form = HospitalisationForm()

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
    # 1. Requête optimisée (avec prefetch_related pour charger les paiements en une seule fois)
    # Cela permet d'accéder à hosp.get_reste_a_payer() sans ralentir la page.
    hospitalisations = Hospitalisation.objects.select_related(
        'patient', 
        'lit__chambre__type_chambre'
    ).prefetch_related('paiements').order_by('-date_entree')

    # 2. Gestion de vos rôles (votre logique d'origine)
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 3. Rendu avec toutes les informations nécessaires
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
    hosp = get_object_or_404(Hospitalisation, id=hosp_id)
    
    # Vérification : Le patient est-il déjà sorti ?
    if hosp.statut != 'EN_COURS':
        messages.warning(request, "Cette hospitalisation est déjà clôturée ou annulée.")
        return redirect('liste_hospitalisations')

    if request.method == 'POST':
        try:
            # 1. Récupération et conversion sécurisée des données
            try:
                montant_brut = Decimal(request.POST.get('montant_verse', '0'))
                reduction = Decimal(request.POST.get('montant_reduction', '0'))
            except (InvalidOperation, ValueError):
                messages.error(request, "Veuillez saisir des montants valides.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            # Vérification : Paiement inutile
            if montant_brut < 0 or reduction < 0:
                messages.error(request, "Les montants ne peuvent pas être négatifs.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)
            
            if montant_brut == 0 and reduction == 0:
                messages.error(request, "Veuillez saisir un montant ou une réduction.")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            devise = request.POST.get('devise', 'USD')
            
            # 2. Conversion en USD
            montant_verse_usd = montant_brut
            reduction_usd = reduction
            if devise == 'CDF':
                taux = ConfigurationHopital.get_taux() 
                if not taux or taux <= 0:
                    raise ValueError("Taux de change non configuré ou invalide.")
                montant_verse_usd = montant_brut / Decimal(str(taux))
                reduction_usd = reduction / Decimal(str(taux))
            
            # 3. Vérification du solde
            reste_actuel = hosp.get_reste_a_payer()
            total_paye_ce_coup_ci = montant_verse_usd + reduction_usd
            
            if total_paye_ce_coup_ci > (reste_actuel + Decimal('0.01')):
                messages.error(request, f"Le montant saisi dépasse le solde restant ({reste_actuel:.2f} USD).")
                return redirect('payer_hospitalisation', hosp_id=hosp.id)
            
            # 4. Enregistrement
            Paiement.objects.create(
                hospitalisation=hosp,
                patient=hosp.patient,
                service='HOSPITALISATION',
                montant_verse=montant_verse_usd,
                montant_reduction=reduction_usd,
                devise=devise,
                caissier=request.user
            )
            
            # 5. Logique de libération (Automatisation)
            nouveau_reste = hosp.get_reste_a_payer()
            if nouveau_reste <= 0:
                hosp.statut = 'TERMINE'
                hosp.date_sortie = timezone.now()
                hosp.est_payee = True
                hosp.save() # Le save() déclenche la libération du lit via le modèle
                messages.success(request, "Paiement complet : Patient libéré, lit disponible.")
            else:
                messages.success(request, "Paiement partiel enregistré avec succès.")

            return redirect('liste_hospitalisations')
            
        except Exception as e:
            messages.error(request, f"Erreur critique lors du paiement : {str(e)}")
            return redirect('payer_hospitalisation', hosp_id=hosp.id)

    # 6. Récupération des informations pour le template (GET)
    role = Fonction.objects.filter(userKey=request.user).first()
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
    patient = get_object_or_404(Patient, id=patient_id)
    
    if not patient.fiche_payee:
        messages.error(request, "Accès refusé.")
        return redirect('liste_patients')
    
    # Consultations
    historique_consultations = Consultation.objects.filter(
        triage__patient=patient
    ).order_by('-date_creation').prefetch_related(
        'examens__prestation', 
        'ordonnance_set__medicaments'
    ).select_related('triage', 'medecin')
    
    # Hospitalisations (on retire le prefetch qui causait l'erreur)
    hospitalisations = Hospitalisation.objects.filter(patient=patient).order_by('-date_entree')
    
    # Signes vitaux (on s'assure que 'infirmier' existe ou on le retire)
    signes_vitaux = SigneVital.objects.filter(patient=patient).order_by('-date_prelevement')
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'patient': patient,
        'consultations': historique_consultations,
        'hospitalisations': hospitalisations,
        'signes_vitaux': signes_vitaux,
        'fonctionKey':fonctionKey
    }
    
    return render(request, 'back-end/patient/dossier_medical.html', context)


#
# ===========================================================================================
# DETAIL HOSPITALIERE
# ============================================================================================
@login_required
def detail_hospitalisation(request, pk):
    # 1. Récupération de l'hospitalisation avec relations optimisées
    hosp = get_object_or_404(
        Hospitalisation.objects.select_related('patient', 'lit__chambre__type_chambre'), 
        pk=pk
    )

    # --- LOGIQUE DE CALENDRIER ---
    # On commence à la date d'entrée et on va jusqu'à DEMAIN
    date_debut = hosp.date_entree.date()
    demain = timezone.now().date() + timedelta(days=1)
    
    jours = []
    curr = date_debut
    while curr <= demain:
        jours.append(curr)
        curr += timedelta(days=1)
    # -----------------------------

    # 2. Récupération des ordonnances
    ordonnances = Ordonnance.objects.filter(
        consultation__triage__patient=hosp.patient
    ).prefetch_related('medicaments').order_by('-date_prescrite')
    
    # 3. Préparation du Kardex
    kardex_items = Kardex.objects.filter(hospitalisation=hosp).prefetch_related('administrations').order_by('-id')
    
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
    
    # 4. Gestion des suivis journaliers avec pagination
    suivis_list = hosp.suivis_journaliers.all().order_by('-date_suivi')
    paginator = Paginator(suivis_list, 5) 
    page_number = request.GET.get('page')
    suivis = paginator.get_page(page_number)
    
    # 5. Gestion des rôles
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 6. Rendu final
    return render(request, 'back-end/hospitalisation/detail.html', {
        'hosp': hosp,
        'ordonnances': ordonnances,
        'kardex_data': kardex_data,
        'suivis': suivis, 
        'fonctionKey': fonctionKey,
        'jours': jours,
    })


# ===========================================================================================

def changer_statut_kardex(request, kardex_id):
    if request.method == 'POST':
        item = get_object_or_404(Kardex, id=kardex_id)
        # Bascule entre True et False
        item.est_actif = not item.est_actif 
        item.save()
        # Redirection vers la même page de détail
        return redirect('detail_hospitalisation', pk=item.hospitalisation.id)
    return redirect('liste_hospitalisations')

#
# ===========================================================================================
# ADD SUIVI PAR L'INFIRMIER  
# ============================================================================================
@login_required
def ajouter_suivi(request, pk):
    # 1. Vérification des droits d'accès
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    # Redirection immédiate si non autorisé
    if fonctionKey not in ['infirmier', 'medecin', 'admin']:
        messages.error(request, "Accès refusé : vous n'êtes pas autorisé à modifier le suivi.")
        return redirect('detail_hospitalisation', pk=pk)

    if request.method == 'POST':
        # 2. Récupération de l'hospitalisation
        hosp = get_object_or_404(Hospitalisation, pk=pk)
        
        # 3. Récupération des données du formulaire
        ta_val = request.POST.get('ta')
        pouls_val = request.POST.get('pouls')
        temp_val = request.POST.get('temp')
        etat = request.POST.get('etat_general')
        soins = request.POST.get('soins_effectues', '')
        
        # 4. Validation des champs obligatoires
        if all([ta_val, pouls_val, temp_val, etat]):
            try:
                # Création d'une synthèse textuelle
                synthese = f"TA: {ta_val} | Pouls: {pouls_val} | Temp: {temp_val}°C"
                
                # 5. Enregistrement dans les champs dédiés
                SuiviQuotidien.objects.create(
                    hospitalisation=hosp,
                    infirmier=request.user,
                    ta=ta_val,
                    pouls=pouls_val,
                    temp=temp_val,
                    etat_general=etat,
                    constantes_du_jour=synthese,
                    soins_effectues=soins
                )
                
                messages.success(request, "Le suivi quotidien a été enregistré avec succès.")
                
            except Exception as e:
                messages.error(request, f"Une erreur technique est survenue : {e}")
        else:
            messages.error(request, "Erreur : Veuillez remplir tous les champs obligatoires (TA, Pouls, Temp, État).")
            
        # Redirection finale après traitement du POST
        return redirect('detail_hospitalisation', pk=pk)
    
    # Redirection si la méthode n'est pas POST
    return redirect('detail_hospitalisation', pk=pk)

#
# ============================================================================================
# KARDEX (FICHE DE TRAITEMENT)
# ============================================================================================
@login_required
def ajouter_kardex(request, hosp_id):
    hosp = get_object_or_404(Hospitalisation, id=hosp_id)
    
    if not hosp.est_actif:
        messages.error(request, "Impossible d'ajouter un traitement : hospitalisation terminée.")
        return redirect('detail_hospitalisation', pk=hosp.id)
    
    if request.method == 'POST':
        medicament = request.POST.get('medicament')
        posologie = request.POST.get('posologie')
        voie = request.POST.get('voie')
        
        if medicament and posologie:
            with transaction.atomic(): # Assure que tout est créé ou rien
                nouveau_kardex = Kardex.objects.create(
                    hospitalisation=hosp,
                    medicament=medicament,
                    posologie=posologie,
                    voie_administration=voie,
                    est_actif=True
                )
                
                # Création de l'administration initiale
                AdministrationKardex.objects.create(
                    kardex=nouveau_kardex,
                    date_admin=timezone.now().date(),
                    matin=False, midi=False, soir=False # Initialisé à False
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
    if request.method == 'POST':
        # 1. Récupérer le médicament concerné
        kardex_item = get_object_or_404(Kardex, id=kardex_id)
        
        # 2. Récupérer la date envoyée par le formulaire (depuis le champ hidden)
        date_str = request.POST.get('date_cible')
        try:
            date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return redirect('detail_hospitalisation', pk=kardex_item.hospitalisation.id)

        # 3. Créer ou récupérer l'enregistrement pour ce jour précis
        # get_or_create s'occupe de créer une nouvelle ligne s'il n'en trouve pas
        admin, created = AdministrationKardex.objects.get_or_create(
            kardex=kardex_item,
            date_admin=date_cible
        )
        
        # 4. Mettre à jour les cases (True si coché, False sinon)
        admin.matin = 'matin' in request.POST
        admin.midi = 'midi' in request.POST
        admin.soir = 'soir' in request.POST
        admin.save()
        
        # 5. Rediriger vers la page du patient
        return redirect('detail_hospitalisation', pk=kardex_item.hospitalisation.id)
    
    return redirect('liste_hospitalisations')


# 
# ===========================================================================================
#   GESTION DES RENDEZ-VOUS
# ===========================================================================================
@login_required
def creer_rendez_vous(request, hosp_id):
    hosp = get_object_or_404(Hospitalisation, id=hosp_id)
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    if fonctionKey not in ['medecin', 'admin']:
        messages.error(request, "Accès refusé.")
        return redirect('detail_hospitalisation', pk=hosp.id)
    
    if request.method == 'POST':
        date_rdv = request.POST.get('date_rdv')
        motif = request.POST.get('motif')
        note = request.POST.get('note')
        
        if date_rdv and motif:
            # VÉRIFICATION : Le rendez-vous existe-t-il déjà pour cette hospitalisation ?
            if RendezVous.objects.filter(hospitalisation=hosp).exists():
                messages.warning(request, "Un rendez-vous est déjà planifié pour cette hospitalisation.")
                return redirect('creer_ordonnance_sortie', hosp_id=hosp.id)
            
            # Création si aucun rendez-vous n'existe
            RendezVous.objects.create(
                hospitalisation=hosp,
                date_rdv=date_rdv,
                motif=motif,
                note=note,
                enregistre_par=request.user
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
    hosp = get_object_or_404(Hospitalisation, id=hosp_id)
    if request.method == 'POST':
        # Logique pour sauvegarder l'ordonnance
        ordonnance = Ordonnance.objects.create(
            hospitalisation=hosp,
            type_ordonnance='SORTIE',
            contenu=request.POST.get('contenu')
        )
        return redirect('dossier_patient', hosp_id=hosp.id)

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/hospitalisation/creer_ordonnance.html', {'hosp': hosp, 'fonctionKey':fonctionKey})


#
# ===========================================================================================
# LISTE DE RENDEZ-VOUS
# ===========================================================================================
@login_required
def liste_rendez_vous(request):
    # Récupérer tous les rendez-vous futurs ou récents
    rendez_vous = RendezVous.objects.all().order_by('date_rdv')
    
    # On transmet la date actuelle pour comparer dans le template
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/hospitalisation/liste_rdv.html', {
        'rendez_vous': rendez_vous,
        'maintenant': timezone.now() ,
        'fonctionKey' : fonctionKey
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
    item = get_object_or_404(Kardex, id=kardex_id)
    
    if request.method == 'POST':
        # Si c'est le bouton STOP qui est cliqué
        if 'stop_traitement' in request.POST:
            item.est_actif = False
            item.save()
        # Sinon, c'est la mise à jour des cases à cocher
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
    if request.method == 'POST':
        hosp = get_object_or_404(Hospitalisation, id=hosp_id)
        
        # On désactive l'hospitalisation
        hosp.est_actif = False
        # Si tu as un champ date_fin dans ton modèle Hospitalisation
        hosp.date_fin = timezone.now() 
        hosp.save()
        
    return redirect('detail_hospitalisation', pk=hosp_id)

#
# ============================================================================================
# IMPRIMER ORDONNANCE 
# ============================================================================================
@login_required
def imprimer_ordonnance(request, ordonnance_id):
    # Récupération de l'ordonnance avec ses relations pré-chargées
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__triage__patient', 
            'consultation__medecin'
        ).prefetch_related(
            'medicaments' # Utilisation du related_name
        ), 
        id=ordonnance_id
    )
    
    context = {'ord': ordonnance}
    return render(request, 'back-end/imprimer/print_ordonnance.html', context)


#
# ===========================================================================================
# CREE UN ORDONNANCE
# ============================================================================================
@login_required
def creer_ordonnance_view(request, consultation_id):
    # 1. Récupération sécurisée de la consultation
    consultation = get_object_or_404(Consultation, id=consultation_id)

    # 2. Traitement du formulaire POST
    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic_final')
        contenu = request.POST.get('contenu_ordonnance')
        type_ord = request.POST.get('type_ordonnance')
        
        # Listes dynamiques des médicaments
        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')

        try:
            with transaction.atomic():
                # Mise à jour du diagnostic
                consultation.diagnostic_final = diagnostic
                consultation.save()
                
                # Création de l'ordonnance
                ordonnance = Ordonnance.objects.create(
                    consultation=consultation,
                    observation=contenu,
                    type_ordonnance=type_ord
                )
                
                # Enregistrement des médicaments
                for nom, pos, dur in zip(noms, posologies, durees):
                    if nom.strip(): # On n'enregistre que si le nom est présent
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom,
                            posologie=pos,
                            duree=dur
                        )
            
            messages.success(request, f"Ordonnance créée pour {consultation.triage.patient.noms}.")
            return redirect('liste_attente_medecin') # Remplacez par votre vrai nom d'URL
            
        except Exception as e:
            messages.error(request, f"Une erreur est survenue : {str(e)}")

    # 3. Affichage du formulaire (GET)

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/creer_ordonnance.html', {'c': consultation, 'fonctionKey': fonctionKey}) 



#
# ======================================================================================
# ENREGISTREMENT DE L'ENTREPRISE
# ======================================================================================
@login_required
def enregistrer_entreprise_view(request):
    if request.method == 'POST':
        form = EntrepriseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "L'entreprise a été enregistrée avec succès.")
            return redirect('liste_entreprises') # Remplacez par votre URL de redirection
    else:
        form = EntrepriseForm()
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/entreprise/enregistrer_entreprise.html', {'form': form , 'fonctionKey':fonctionKey})

#
# ======================================================================================
# LISTE DES ENTREPRISES
# ======================================================================================
@login_required
def liste_entreprises_view(request):
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    entreprises = Entreprise.objects.all().order_by('-date_enregistrement')
    return render(request, 'back-end/entreprise/liste_entreprises.html', {'entreprises': entreprises, 'fonctionKey':fonctionKey})




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
    
    # 0. Récupérer le taux de change
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2800.00')

    # 1. Récupérer la prestation "Carte de Fidélité"
    # On cherche une prestation qui contient "Carte" dans le libellé et est administrative
    try:
        prestation_carte = Prestation.objects.get(categorie='ADM', libelle__icontains="Carte")
    except (Prestation.DoesNotExist, Prestation.MultipleObjectsReturned):
        prestation_carte = Prestation.objects.filter(categorie='ADM', libelle__icontains="Carte").first()
        
    if not prestation_carte:
        messages.error(request, "La prestation 'Carte de Fidélité' n'est pas configurée.")
        return redirect('enregistrement_patient')
    
    prix_carte_usd = Decimal(str(prestation_carte.prix))

    # 2. Calcul du cumul des paiements déjà effectués pour la Carte
    # On filtre sur le service 'CARTE' (Assurez-vous d'utiliser ce mot clé dans Paiement)
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

        # Vérification si le montant dépasse le reste à payer
        if montant_test_usd > (reste_a_payer_usd + Decimal('0.01')):
            messages.error(request, f"Le montant dépasse le prix de la carte ({reste_a_payer_usd:.2f} USD restants).")
        elif montant_saisi > 0:
            # Enregistrement du paiement
            Paiement.objects.create(
                patient=patient,
                service='CARTE', # Important pour le filtrage du cumul
                montant_verse=montant_saisi,
                devise=devise,
                caissier=request.user
            )
            
            nouveau_total_usd = total_deja_paye_usd + montant_test_usd
            
            # Vérification si la carte est totalement réglée
            if nouveau_total_usd >= (prix_carte_usd - Decimal('0.01')):
                patient.a_carte_fidelite = True # Assurez-vous que ce champ existe dans Patient
                patient.save()
                messages.success(request, f"Paiement terminé. La carte de {patient.noms} est activée.")
            else:
                messages.success(request, f"Paiement de {montant_saisi} {devise} enregistré. Reste : {(prix_carte_usd - nouveau_total_usd):.2f} USD")
            
            return redirect('enregistrement_patient')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

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
    
    # Récupération des données pour le formulaire
    prestation_mat = Prestation.objects.filter(categorie='MAT').first()
    prix_referentiel = prestation_mat.prix if prestation_mat else Decimal('150.00')
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')
    
    if request.method == 'POST':
        # On récupère les valeurs
        montant_raw = request.POST.get('montant', '0')
        reste_raw = request.POST.get('reste_a_payer', '0')
        devise = request.POST.get('devise', 'USD')
        
        try:
            # Conversion sécurisée en Decimal
            montant = Decimal(montant_raw)
            reste = Decimal(reste_raw)
            
            # Conversion du montant versé en USD pour comparaison
            montant_en_usd = montant if devise == 'USD' else (montant / taux)
            
            # Vérification de sécurité
            if montant_en_usd > prix_referentiel:
                messages.error(request, f"Erreur : Le montant versé dépasse le forfait Maternité de {prix_referentiel} USD.")
                return redirect('payer_dossier_maternite', dossier_id=dossier.id)
            
            # Création du paiement
            Paiement.objects.create(
                patient=dossier.patient,
                dossier_maternite=dossier,
                service='MATERNITE',
                montant_verse=montant,
                devise=devise,
                reste_a_payer=reste,
                caissier=request.user
            )
            
            messages.success(request, f"Paiement de {montant} {devise} enregistré avec succès.")
            return redirect('liste_admissions_maternite')
            
        except (InvalidOperation, ValueError, TypeError):
            # En cas de valeur non numérique, on renvoie une erreur
            messages.error(request, "Erreur : Format de montant invalide.")
            return redirect('payer_dossier_maternite', dossier_id=dossier.id)
    
    # Affichage de la page en GET
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/maternite/payer.html', {
        'dossier': dossier, 
        'prix_max': prix_referentiel,
        'taux': taux ,
        'fonctionKey' : fonctionKey
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
    
    # 1. VÉRIFICATION DU DOUBLON : Est-ce qu'un paiement existe déjà pour ce décès ?
    if deces.paiements.exists():
        messages.warning(request, "Attention : Ce décès a déjà été réglé.")
        return redirect('liste_deces')

    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')
    
    prestation = Prestation.objects.filter(libelle__icontains="acte de deces").first()
    prix_usd = prestation.prix if prestation else Decimal('0.00')
    prix_cdf = (prix_usd * taux).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    if request.method == 'POST':
        devise = request.POST.get('devise')
        try:
            montant_verse = Decimal(request.POST.get('montant_verse', '0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except:
            montant_verse = Decimal('0')
            
        prix_requis = (prix_usd if devise == 'USD' else prix_cdf).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # 2. VÉRIFICATION DU MONTANT
        if abs(montant_verse - prix_requis) > Decimal('0.05'): 
            messages.error(request, f"Paiement refusé : Le montant doit être de {prix_requis:.2f} {devise}.")
            return render(request, 'back-end/deces/payer.html', {
                'deces': deces, 'prix_usd': prix_usd, 'prix_cdf': prix_cdf, 'taux': taux
            })

        # 3. CRÉATION DU PAIEMENT (Double sécurité au cas où deux clics simultanés arrivent)
        if not deces.paiements.exists():
            Paiement.objects.create(
                patient=deces.patient if deces.patient else None,
                deces=deces,
                service='DECES',
                montant_verse=montant_verse,
                devise=devise,
                caissier=request.user
            )
            messages.success(request, "Paiement enregistré avec succès.")
        else:
            messages.error(request, "Erreur : Un paiement a été enregistré simultanément.")
            
        return redirect('liste_deces')

    # Affichage normal
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/deces/payer.html', {
        'deces': deces, 'prix_usd': prix_usd, 'prix_cdf': prix_cdf, 
        'taux': taux, 'fonctionKey': fonctionKey
    })



#
# =========================================================================================
# LISTE DES PATIENTS CARTE DE FIDELITE 
# =========================================================================================
@login_required
def liste_patients_avec_carte(request):
    # On filtre uniquement les patients dont a_carte_fidelite est True
    patients_fideles = Patient.objects.filter(a_carte_fidelite=True).order_by('-date_creation')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    context = {
        'patients': patients_fideles,
        'title': "Patients avec Carte de Fidélité" ,
        'fonctionKey' : fonctionKey
    }
    return render(request, 'back-end/patient/liste_patients_carte.html', context)

#
# ==========================================================================================
# MODIFIER TYPE DE PATIENT
# ==========================================================================================
@login_required
def modifier_type_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    
    # RÈGLE : Bloquer l'accès si le type est déjà 'FIDELE'
    if patient.type_patient == 'FIDELE':
        messages.error(request, "Le statut 'Patient Fidèle' est définitif et ne peut plus être modifié.")
        return redirect('liste_patients_avec_carte')
    
    if request.method == 'POST':
        nouveau_type = request.POST.get('type_patient')
        patient.type_patient = nouveau_type
        patient.save()
        messages.success(request, f"Statut mis à jour.")
        return redirect('liste_patients_avec_carte')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    return render(request, 'back-end/patient/modifier_type.html', {'patient': patient , 'fonctionKey': fonctionKey})

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
                        effectue_par=request.user
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
    # On filtre les soins créés aujourd'hui
    aujourd_hui = timezone.now().date()
    soins = SoinOccasionnel.objects.filter(date_soin__date=aujourd_hui).order_by('-date_soin')
    

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/soins/liste_soins_traitement.html', {
        'soins': soins , 
        'fonctionKey' : fonctionKey
    })

#
# ============================================================================================
# MARQUE TRAITEMENT FAIT 
# ============================================================================================
@login_required
def marquer_fait(request, soin_id):
    soin = get_object_or_404(SoinOccasionnel, id=soin_id)
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
    if request.method == 'POST':
        form = ProduitPharmacieForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Le produit a été enregistré avec succès.")
            # Redirige vers la liste des produits ou la gestion de stock
            return redirect('gestion_pharmacie') 
        else:
            messages.error(request, "Erreur lors de l'enregistrement. Vérifie les données.")
    else:
        form = ProduitPharmacieForm()

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    return render(request, 'back-end/pharmacie/ajouter_produit.html', {'form': form ,'fonctionKey':fonctionKey})


# 
# ====================================================================================
# LISTE DES MEDICAMENTS 
# ====================================================================================
@login_required
def gestion_pharmacie(request):
    # 1. Annotation : Calcul des entrées et des sorties séparément
    # On utilise 'les_lots__quantite_initiale' et 'les_lots__sorties__quantite_vendue'
    # pour traverser les relations correctement.
    produits = ProduitPharmacie.objects.annotate(
        total_entrees=Sum('les_lots__quantite_initiale'),
        total_sorties=Sum('les_lots__sorties__quantite_vendue')
    ).annotate(
        # 2. Calcul du stock réel : (Entrées - Sorties)
        # Coalesce transforme les valeurs NULL en 0
        stock_reel=ExpressionWrapper(
            Coalesce('total_entrees', 0) - Coalesce('total_sorties', 0),
            output_field=IntegerField()
        )
    ).order_by('nom')
    
    # Calcul de la valeur totale pour chaque produit avant de passer au template
    for p in produits:
        p.valeur_totale = p.stock_reel * p.prix_vente_unitaire
    
    # Gestion des rôles
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    # Récupération du taux de change
    taux_change = ConfigurationHopital.get_taux()

    context = {
        'produits': produits, 
        'fonctionKey': fonctionKey,
        'taux': taux_change
    }
    
    return render(request, 'back-end/pharmacie/gestion_stock.html', context)

#
# ====================================================================================
# GESTION DES STOCKS
# ====================================================================================
@login_required
def ajouter_lot(request):
    if request.method == 'POST':
        form = LotPharmacieForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Lot ajouté avec succès, stock mis à jour.")
            return redirect('gestion_pharmacie')
    else:
        form = LotPharmacieForm()
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/pharmacie/ajouter_lot.html', {'form': form , 'fonctionKey':fonctionKey}) 

#
# =====================================================================================
# VENTE DE PRODUIT 
# =====================================================================================
@login_required
def enregistrer_vente(request):
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

            # Utilisation de la transaction pour garantir la cohérence
            with transaction.atomic():
                montant_total = Decimal('0.00')
                items_a_vendre = [] 
                
                # 1. Validation du stock et calcul du total
                for item in panier:
                    # select_for_update() verrouille le lot pour éviter les ventes simultanées
                    lot = LotPharmacie.objects.select_for_update().filter(
                        produit_id=item['id'], 
                        quantite_actuelle__gte=int(item['qte'])
                    ).first()
                    
                    if not lot:
                        produit = ProduitPharmacie.objects.get(id=item['id'])
                        return JsonResponse({'status': 'error', 'message': f'Stock insuffisant pour {produit.nom}'})

                    prix_u = Decimal(str(lot.produit.prix_vente_unitaire))
                    if devise == 'CDF':
                        prix_u *= taux
                    
                    montant_total += (prix_u * int(item['qte']))
                    items_a_vendre.append({'lot': lot, 'qte': int(item['qte'])})

                # 2. Validation financière
                if montant_verse > montant_total:
                    return JsonResponse({'status': 'error', 'message': 'Le montant versé dépasse le total.'})

                # 3. Création du paiement
                reste_a_payer = montant_total - montant_verse
                paiement = Paiement.objects.create(
                    montant_verse=montant_verse,
                    devise=devise,
                    service='PHARMACIE',
                    caissier=request.user,
                    reste_a_payer=reste_a_payer
                )

                # 4. Enregistrement des sorties
                # IMPORTANT : Le save() de SortiePharmacie décrémente le stock une seule fois.
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

    # GET : Liste des produits
    from django.db.models import Sum
    produits = ProduitPharmacie.objects.annotate(
        stock_reel=Sum('les_lots__quantite_actuelle')
    ).order_by('nom')
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

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
    # 1. Gestion du filtre de période
    periode = request.GET.get('periode', 'jour')
    periodes_map = {
        'jour': TruncDay('date_paiement'),
        'semaine': TruncWeek('date_paiement'),
        'mois': TruncMonth('date_paiement'),
    }
    trunc_func = periodes_map.get(periode, TruncDay('date_paiement'))

    # 2. Total Général ventilé par devise
    # Assure-toi que 'devise' est bien un champ dans ton modèle Paiement
    total_general = Paiement.objects.values('devise') \
        .annotate(grand_total=Sum('montant_verse'))

    # 3. Ventes par Utilisateur (Traçabilité)
    ventes_par_utilisateur = Paiement.objects.values('les_sorties__vendu_par__username', 'devise') \
        .annotate(total_vendu=Sum('montant_verse')) \
        .order_by('-total_vendu')

    # 4. Stats des ventes regroupées par période et devise
    stats_ventes = Paiement.objects.annotate(date_groupee=trunc_func) \
        .values('date_groupee', 'devise') \
        .annotate(total_periode=Sum('montant_verse')) \
        .order_by('-date_groupee', 'devise')

    # 5. Top 5 Produits par Bénéfice
    top_benefices = SortiePharmacie.objects.values('lot__produit__nom') \
        .annotate(
            benefice_total=Sum(
                (F('lot__produit__prix_vente_unitaire') - F('lot__produit__prix_achat_unitaire')) 
                * F('quantite_vendue'),
                output_field=DecimalField()
            )
        ).order_by('-benefice_total')[:5]

    # 6. Dettes en cours
    dettes_en_cours = Paiement.objects.filter(reste_a_payer__gt=0) \
        .prefetch_related('les_sorties__vendu_par')

    # 7. Stocks critiques
    produits_critiques = LotPharmacie.objects.filter(quantite_actuelle__lt=5) \
        .select_related('produit')

    # 8. KPIs du jour
    aujourdhui = timezone.now().date()
    nombre_ventes = Paiement.objects.filter(date_paiement__date=aujourdhui).count()

    # 9. Rôle
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    context = {
        'stats_ventes': stats_ventes,
        'total_general': total_general,
        'ventes_par_utilisateur': ventes_par_utilisateur,
        'top_benefices': top_benefices,
        'dettes_en_cours': dettes_en_cours,
        'produits_critiques': produits_critiques,
        'nb_ventes': nombre_ventes,
        'periode_actuelle': periode,
        'fonctionKey': fonctionKey
    }
    return render(request, 'back-end/pharmacie/dashboard.html', context)

# 
# ==================================================================================================
# LISTE DES VENTES
# ==================================================================================================
@login_required
def liste_ventes(request):
    # Correction ici : le chemin correct est les_sorties -> lot -> produit
    ventes = Paiement.objects.filter(service='PHARMACIE') \
                             .prefetch_related('les_sorties__lot__produit') \
                             .order_by('-date_paiement')

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/pharmacie/liste_ventes.html', {
        'ventes': ventes,
        'fonctionKey': fonctionKey 
    })

#
# ===================================================================================================
# FACTURATION DES VENTES PRODUITS
# ===================================================================================================
@login_required
def details_facture(request, vente_id):
    facture = get_object_or_404(Paiement, id=vente_id)
    details = facture.les_sorties.select_related('lot__produit').all()
    
    for item in details:
        # Données du médicament
        produit = item.lot.produit
        item.nom_medicament = produit.nom
        item.forme_medicament = produit.forme
        item.dosage_medicament = produit.dosage
        
        # Calculs financiers
        item.prix_unitaire = produit.prix_vente_unitaire 
        item.total_ligne = item.prix_unitaire * item.quantite_vendue
        
    context = {
        'facture': facture,
        'details': details,
    }
    return render(request, 'back-end/pharmacie/facture_print.html', context)

#
# ===============================================================================================
# VALIDER VENTE PHARMACIE
# ===============================================================================================
@csrf_exempt
def valider_vente(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            panier = data.get('panier')
            devise = data.get('devise')

            # 1. Créer le paiement
            paiement = Paiement.objects.create(devise=devise)

            # 2. Enregistrer les sorties en utilisant le lot
            for item in panier:
                SortiePharmacie.objects.create(
                    paiement=paiement,
                    # ICI : utilise 'lot_id' au lieu de 'produit_id'
                    lot_id=item['lot_id'], 
                    quantite_vendue=item['quantite']
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
    # 1. GESTION DE LA VALIDATION (Marquer comme traité)
    if request.method == 'POST' and request.POST.get('orientation_id'):
        orientation = get_object_or_404(Orientation, id=request.POST.get('orientation_id'))
        orientation.est_admis = True
        orientation.save()
        return redirect('service_liste_attente')

    # 2. IDENTIFICATION DU RÔLE
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_nom = role_obj.fonctionKey.roleName.strip().lower() if (role_obj and role_obj.fonctionKey) else ""

    # 3. LOGIQUE DE FILTRAGE DES SERVICES
    # Liste des services nécessitant une saisie de compte rendu
    services_avec_compte_rendu = ['bloc', 'accouchement']
    doit_saisir_compte_rendu = any(s in fonction_nom for s in services_avec_compte_rendu)

    # Définition des destinations autorisées par rôle
    if 'pharmacien' in fonction_nom:
        destinations_autorisees = ['PHARMACIE']
    elif 'infirmier' in fonction_nom or 'medecin' in fonction_nom:
        destinations_autorisees = ['SALLE_SOINS', 'BLOC_OPERATOIRE', 'ACCOUCHEMENT']
    elif 'hospitalisation' in fonction_nom:
        destinations_autorisees = ['HOSPITALISATION']
    else:
        destinations_autorisees = []

    # 4. RÉCUPÉRATION DES ORIENTATIONS
    orientations = Orientation.objects.filter(
        destination__in=destinations_autorisees,
        est_admis=False
    ).select_related(
        'consultation__triage__patient',
        'consultation__medecin'
    ).prefetch_related(
        'consultation__ordonnance_set__medicaments'
    )

    # 5. RENDU DU TEMPLATE
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
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_nom = role_obj.fonctionKey.roleName.strip().lower() if (role_obj and role_obj.fonctionKey) else ""
    fonctionKey = role_obj.fonctionKey.roleName if role_obj else "Invité"

    # 1. DÉFINITION DES DESTINATIONS AUTORISÉES SELON LE RÔLE
    if 'infirmier' in fonction_nom:
        # Ajout de 'ACCOUCHEMENT' ici
        destinations_autorisees = ['SALLE_SOINS', 'BLOC_OPERATOIRE', 'ACCOUCHEMENT']
    elif 'pharmacien' in fonction_nom:
        destinations_autorisees = ['PHARMACIE']
    elif 'hospitalisation' in fonction_nom:
        destinations_autorisees = ['HOSPITALISATION']
    else:
        destinations_autorisees = ['BLOC_OPERATOIRE'] if 'bloc' in fonction_nom else []

    # 2. RÉCUPÉRATION DES ADMIS (HISTORIQUE)
    orientations = Orientation.objects.filter(
        destination__in=destinations_autorisees,
        est_admis=True
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
    consultation = get_object_or_404(Consultation, id=consultation_id)
    
    # 1. Récupération ou création
    bloc, created = BlocOperatoire.objects.get_or_create(
        consultation=consultation,
        defaults={
            'constantes_pre_op': f"TA: {consultation.triage.tension_arterielle} | Pouls: {consultation.triage.frequence_cardiaque} | Temp: {consultation.triage.temperature}"
        }
    )
    
    # 2. Récupération des prestations de type Chirurgie pour le menu
    prestations_chir = Prestation.objects.filter(categorie='CHIR')

    if request.method == 'POST':
        # Mise à jour des informations
        bloc.acte_realise = request.POST.get('acte_realise')
        bloc.statut = request.POST.get('statut', 'TERMINE')
        bloc.chirurgien = request.user
        
        # Sauvegarde de la prestation choisie
        prestation_id = request.POST.get('prestation_id')
        if prestation_id:
            bloc.prestation_id = prestation_id
            
        if bloc.statut == 'TERMINE':
            bloc.date_fin = timezone.now()
        
        bloc.save()
        
        # Suggestion : Facturation automatique ici si nécessaire
        messages.success(request, "Informations de bloc mises à jour avec succès.")
        return redirect('service_liste_attente')

    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    context = {
        'consultation': consultation,
        'bloc': bloc,
        'patient': consultation.triage.patient,
        'fonctionKey': fonctionKey,
        'prestations_chir': prestations_chir, # Ajouté pour le template
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
    # 1. Vérification de l'existence de l'objet
    bloc = get_object_or_404(BlocOperatoire, id=bloc_id)
    consultation = bloc.consultation
    
    # 2. Récupération de la configuration (Taux)
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500')
    
    # 3. Calcul du reste à payer (Calcul basé sur l'historique des paiements de ce bloc)
    prix_chirurgie = bloc.prestation.prix if bloc.prestation else Decimal('0.00')
    paiements_bloc = Paiement.objects.filter(bloc_op=bloc)
    
    total_verse = paiements_bloc.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_reductions = paiements_bloc.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')
    
    reste_a_payer = max(Decimal('0.00'), prix_chirurgie - (total_verse + total_reductions))

    # 4. Traitement du formulaire
    if request.method == 'POST':
        # Vérification si le bloc est déjà totalement payé (sécurité supplémentaire)
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
        
        # Conversion du montant versé en USD
        montant_verse_usd = montant_recu / taux if devise == 'CDF' else montant_recu
        total_a_deduire = montant_verse_usd + reduction_usd
        
        # VÉRIFICATION : Le paiement ne doit pas dépasser le reste à payer
        if total_a_deduire > (reste_a_payer + Decimal('0.01')):
            messages.error(request, f"Erreur : Le montant total ({total_a_deduire:.2f} USD) dépasse le reste à payer ({reste_a_payer:.2f} USD).")
            return redirect('encaisser_bloc', bloc_id=bloc.id)
        
        # Création du paiement
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

    # 5. Gestion des rôles (pour le template)
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

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
    bloc = get_object_or_404(BlocOperatoire, id=bloc_id)
    
    if request.method == 'POST':
        # Enregistrement du rapport et finalisation
        bloc.acte_realise = request.POST.get('acte_realise')
        bloc.statut = 'TERMINE' # On passe l'opération à terminé
        bloc.date_fin = timezone.now() # On horodate la fin
        bloc.save()
        return redirect('service_historique') 
        
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

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
    # Récupère l'objet bloc
    bloc = get_object_or_404(BlocOperatoire, id=bloc_id)
    
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/bloc/voir_rapport.html', {
        'bloc': bloc ,
        'fonctionKey' : fonctionKey
    })

#
# =======================================================================================
# PRESTATION ACCOUCHEMENT  (saisir fiche accouchement apres acouchement)
# =======================================================================================
@login_required
def saisir_fiche_accouchement_view(request, consultation_id):
    consultation = get_object_or_404(Consultation, id=consultation_id)
    # Récupère uniquement les prestations de type MAT (forfait maternité)
    prestations = Prestation.objects.filter(categorie='MAT')

    if request.method == 'POST':
        prestation_id = request.POST.get('prestation_id')
        type_acc = request.POST.get('type_accouchement')
        sexe_bebe = request.POST.get('sexe_bebe')
        poids_bebe = request.POST.get('poids_bebe')
        score_apgar = request.POST.get('score_apgar')
        notes = request.POST.get('notes')

        # Vérification des champs obligatoires
        if not prestation_id or not type_acc or not poids_bebe:
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            return redirect('saisir_fiche_accouchement', consultation_id=consultation.id)

        try:
            prestation = Prestation.objects.get(id=prestation_id)

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

        except Prestation.DoesNotExist:
            messages.error(request, "La prestation sélectionnée est invalide.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement : {e}")

    # Récupération du rôle de l'utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

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
    consultation = get_object_or_404(Consultation, id=consultation_id)
    # On récupère les prestations de la catégorie MAT (Forfait Maternité)
    prestations = Prestation.objects.filter(categorie='MAT')
    
    if request.method == 'POST':
        prestation_id = request.POST.get('prestation_id')
        type_acc = request.POST.get('type_accouchement')
        details = request.POST.get('details_acte')
        
        if not prestation_id:
            messages.error(request, "Veuillez sélectionner un forfait de maternité.")
            return redirect('saisir_cr_accouchement', consultation_id=consultation.id)

        try:
            with transaction.atomic():
                # 1. Enregistrement du Compte-rendu
                CompteRenduAccouchement.objects.create(
                    consultation=consultation,
                    prestation=Prestation.objects.get(id=prestation_id),
                    type_accouchement=type_acc,
                    details_acte=details,
                    auteur=request.user
                )
                
                # 2. Marquer l'orientation comme traitée
                # On cherche l'orientation liée à cette consultation
                orientation = consultation.orientation
                if orientation:
                    orientation.est_admis = True
                    orientation.save()
            
            messages.success(request, "Compte-rendu d'accouchement enregistré avec succès.")
            return redirect('service_liste_attente')
            
        except Exception as e:
            messages.error(request, f"Erreur critique : {str(e)}")
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/accouchement/saisir_cr.html', {
        'consultation': consultation,
        'prestations': prestations ,
        'fonctionKey' : fonctionKey
    })

#
# ====================================================================================================
# LISTE DES FICHES ACCOUCHEMENT 
# =====================================================================================================
@login_required
def liste_fiches_accouchement_view(request):
    query = request.GET.get('q', '')
    fiches = FicheAccouchement.objects.all().order_by('-date_creation')

    # Recherche par patient ou notes
    if query:
        fiches = fiches.filter(
            Q(consultation__triage__patient__noms__icontains=query) |
            Q(notes__icontains=query)
        )

    # Pagination : 10 fiches par page
    paginator = Paginator(fiches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Récupération du rôle de l'utilisateur
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

    return render(request, 'back-end/accouchement/liste_fiches.html', {
        'page_obj': page_obj,
        'query': query , 
        'fonctionKey' : fonctionKey
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
    cr = get_object_or_404(CompteRenduAccouchement, id=cr_id)
    taux = ConfigurationHopital.get_taux()
    
    # 1. Calculer le reste à payer actuel pour ce compte-rendu
    # Prix total du forfait
    total_forfait = cr.prestation.prix
    # Somme des paiements déjà effectués
    paiements_precedents = Paiement.objects.filter(compte_rendu=cr)
    total_deja_paye = paiements_precedents.aggregate(Sum('montant_verse'))['montant_verse__sum'] or Decimal('0.00')
    
    # Reste à payer en USD
    reste_a_payer_usd = total_forfait - total_deja_paye

    if request.method == 'POST':
        montant_saisi = Decimal(request.POST.get('montant_verse', 0))
        montant_reduction = Decimal(request.POST.get('montant_reduction', 0))
        devise = request.POST.get('devise', 'USD')
        
        # 2. Conversion du montant saisi en USD pour comparaison
        montant_en_usd = montant_saisi
        if devise == 'CDF':
            montant_en_usd = montant_saisi / taux
            
        # 3. Vérification : le total (paiement + réduction) ne doit pas dépasser le reste
        if (montant_en_usd + montant_reduction) > reste_a_payer_usd:
            messages.error(request, f"Le montant saisi dépasse la dette restante ({reste_a_payer_usd:.2f} USD).")
        else:
            try:
                Paiement.objects.create(
                    patient=cr.consultation.triage.patient,
                    compte_rendu=cr,
                    service='MATERNITE',
                    montant_verse=montant_en_usd, # On enregistre en USD
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

    # Récupération du rôle pour le template
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

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
    # Récupère le compte-rendu associé à la consultation
    cr = get_object_or_404(CompteRenduAccouchement, consultation__id=consultation_id)
    
    # Récupération du rôle pour le template (si nécessaire)
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role_obj.fonctionKey.roleName if (role_obj and role_obj.fonctionKey) else "Invité"

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
    patient = get_object_or_404(Patient, id=patient_id)
    
    # 1. Vérification du rôle utilisateur
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    
    if fonctionKey not in ['receptionniste', 'caissier', 'admin']:
        messages.error(request, "Accès refusé : droits insuffisants.")
        return redirect('liste_patients')
    
    # 2. Vérification : Fiche payée obligatoire
    if not getattr(patient, 'fiche_payee', False):
        messages.error(request, "Le patient doit d'abord payer sa fiche d'ouverture.")
        return redirect('enregistrement_patient')

    # 3. Traitement du formulaire
    if request.method == 'POST':
        # --- PROTECTION ANTI-DOUBLON ---
        # Empêche la création d'une session identique dans les 10 dernières secondes
        seuil = timezone.now() - timedelta(seconds=10)
        doublon = SessionSoins.objects.filter(patient=patient, date_creation__gte=seuil).exists()
        if doublon:
            messages.warning(request, "Une session a déjà été créée très récemment pour ce patient.")
            return redirect('liste_sessions')

        prestation_ids = request.POST.getlist('prestations')
        if not prestation_ids:
            messages.error(request, "Veuillez sélectionner au moins une prestation.")
            return redirect('creer_session_soins', patient_id=patient.id)

        # Vérification des droits sur les prestations (Sexe)
        autorisees_qs = Prestation.objects.filter(categorie='CONS')
        if patient.sexe == 'F':
            autorisees_qs = autorisees_qs | Prestation.objects.filter(categorie='CONS_MAT')
        
        autorisees_ids = autorisees_qs.values_list('id', flat=True)
        
        for p_id in prestation_ids:
            if int(p_id) not in autorisees_ids:
                messages.error(request, "Erreur : Une prestation sélectionnée est invalide.")
                return redirect('creer_session_soins', patient_id=patient.id)

        # Création sécurisée
        try:
            with transaction.atomic():
                session = SessionSoins.objects.create(patient=patient)
                prestations = Prestation.objects.filter(id__in=prestation_ids)
                
                lignes = [
                    LigneFacture(session=session, prestation=p, prix_facture=p.prix) 
                    for p in prestations
                ]
                LigneFacture.objects.bulk_create(lignes)
                
                messages.success(request, "Session créée avec succès.")
                return redirect('paiement_session', session_id=session.id)
        except Exception as e:
            messages.error(request, f"Erreur critique lors de la création : {str(e)}")

    # 4. Chargement des prestations autorisées pour l'affichage
    if patient.sexe == 'M':
        prestations = Prestation.objects.filter(categorie='CONS')
    else:
        prestations = Prestation.objects.filter(categorie__in=['CONS', 'CONS_MAT'])
    
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
    # Récupération des sessions avec les relations nécessaires
    sessions = SessionSoins.objects.prefetch_related('items__prestation', 'paiements').all().order_by('-date_creation')
    
    # Calcul dynamique des totaux pour chaque session
    for session in sessions:
        # On récupère tous les paiements liés à la session
        paiements = session.paiements.all()
        
        total_paye = paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        total_red = paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
        
        # Attributs calculés pour l'affichage
        session.total_verse = total_paye
        session.total_reductions = total_red
        session.actuel_reste = max(0, session.total_a_payer - total_paye - total_red)

    # 3. Gestion des droits d'accès (ton système de rôle)
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

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
    """
    Vue permettant d'encaisser un paiement pour une session de soins donnée.
    """
    # 1. Récupération de la session
    session = get_object_or_404(SessionSoins, pk=session_id)
    
    # 2. Récupération du taux de change actuel
    taux = ConfigurationHopital.get_taux()

    # 3. Vérification si déjà soldé
    if session.est_payee:
        messages.warning(request, "Cette session est déjà soldée.")
        return redirect('liste_sessions')

    # 4. Traitement du paiement (POST)
    if request.method == 'POST':
        try:
            montant_saisi = Decimal(request.POST.get('montant', 0))
            reduction = Decimal(request.POST.get('reduction', 0))
            devise = request.POST.get('devise', 'USD')

            # Conversion si CDF vers USD (base de données en USD)
            montant_verse = montant_saisi / taux if devise == 'CDF' else montant_saisi

            # Création de l'objet Paiement 
            # La logique métier (calcul du reste, mise à jour de la session) 
            # est gérée automatiquement dans Paiement.save()
            Paiement.objects.create(
                session=session,
                patient=session.patient,
                service='SOIN',
                montant_verse=montant_verse,
                montant_reduction=reduction,
                devise='USD',
                caissier=request.user
            )
            
            messages.success(request, "Paiement et remise enregistrés avec succès.")
            return redirect('liste_sessions')
        except Exception as e:
            messages.error(request, f"Erreur lors du paiement : {str(e)}")

    # 5. Calculs pour l'affichage (GET)
    # Somme des versements et réductions déjà effectués
    total_deja_paye = session.paiements.aggregate(models.Sum('montant_verse'))['montant_verse__sum'] or 0
    total_reductions = session.paiements.aggregate(models.Sum('montant_reduction'))['montant_reduction__sum'] or 0
    reste_a_payer = max(0, session.total_a_payer - total_deja_paye - total_reductions)
    
    # Calcul du reste en CDF pour l'affichage direct dans le template
    reste_a_payer_cdf = float(reste_a_payer) * float(taux)

    # 6. Vérification du rôle utilisateur
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 7. Rendu de la page
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
    session = get_object_or_404(SessionSoins, id=session_id)
    # On récupère tous les signes vitaux du patient lié à cette session
    historique_signes = SigneVital.objects.filter(patient=session.patient).order_by('-date_prelevement')


    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/consultation/details.html', {
        'session': session,
        'historique_signes': historique_signes ,
        'fonctionKey' : fonctionKey
    })

#
# ===========================================================================================
# LISTE DES SESSIONS POUR INFIRMIER 
# ===========================================================================================
@login_required
def liste_sessions_infirmier(request):
    # On filtre uniquement les sessions qui ont au moins un paiement
    # On précharge 'items__prestation' pour que le template puisse accéder aux noms
    sessions = SessionSoins.objects.annotate(
        a_un_paiement=Exists(Paiement.objects.filter(session=OuterRef('pk')))
    ).filter(a_un_paiement=True).prefetch_related('items__prestation').order_by('-date_creation')

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

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
    session = get_object_or_404(SessionSoins, id=session_id) 
    
    if request.method == 'POST':
        form = SigneVitalForm(request.POST)
        if form.is_valid():
            signes = form.save(commit=False)
            signes.session = session
            signes.patient = session.patient
            signes.infirmier = request.user
            signes.save()
            return redirect('liste_sessions_infirmier')
    else:
        form = SigneVitalForm()
    
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/consultation/saisie_signes.html', {
        'form': form, 'session': session ,
        'fonctionKey' : fonctionKey
    })



#
# ===============================================================================================
# PAIEMENT DES DETTES COTE VENTE MEDICAMENT 
# ===============================================================================================
@login_required
def ajouter_paiement_dette(request, paiement_id):
    paiement = get_object_or_404(Paiement, id=paiement_id)
    
    # On récupère le taux actuel (depuis ton modèle de configuration)
    taux = Decimal(str(ConfigurationHopital.get_taux()))

    if request.method == 'POST':
        montant_saisi = Decimal(str(request.POST.get('montant')))
        devise_paiement = request.POST.get('devise_paiement') # USD ou CDF

        # 1. Conversion du montant saisi en USD (la devise de la vente)
        montant_en_usd = montant_saisi
        if devise_paiement == 'CDF':
            montant_en_usd = montant_saisi / taux

        # 2. Vérification
        if montant_en_usd > paiement.reste_a_payer:
            messages.error(request, f"Le montant saisi ({montant_saisi} {devise_paiement}) dépasse la dette restante en USD.")
            return redirect('liste_ventes')

        # 3. Sauvegarde
        with transaction.atomic():
            paiement.reste_a_payer -= montant_en_usd
            paiement.montant_verse += montant_en_usd
            paiement.save()
            
            messages.success(request, "Dette mise à jour avec succès.")
            
        return redirect('liste_ventes')


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
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    if not role_obj or not role_obj.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    # On récupère le nom de sa fonction (ex: "Laborantin", "Radiologue")
    role_name = role_obj.fonctionKey.roleName.upper()
    
    # On définit la catégorie à filtrer selon le rôle
    # Vérifie bien que ces codes correspondent à tes choix dans Prestation.CATEGORIES
    cat_cible = None
    if 'LABO' in role_name: cat_cible = 'LABO'
    elif 'RADIO' in role_name: cat_cible = 'RADIO'
    elif 'ECHO' in role_name: cat_cible = 'ECHO'

    # Récupération des demandes qui contiennent au moins une prestation de cette catégorie
    demandes = DemandeExamenExterne.objects.filter(
        prestations__categorie=cat_cible
    ).distinct().order_by('-date_demande')

    historique_technique = []

    for dem in demandes:
        # On ne garde que les examens de la catégorie du technicien
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
    # 1. Vérification du rôle
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    if not role_obj or not role_obj.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})

    role_name = role_obj.fonctionKey.roleName.upper()
    
    # Déterminer si l'utilisateur est un médecin ou un technicien
    is_medecin = 'MEDECIN' in role_name or 'DOCTEUR' in role_name
    
    # Définir la catégorie cible pour le technicien
    cat_cible = None
    if 'LABO' in role_name: cat_cible = 'LABO'
    elif 'RADIO' in role_name: cat_cible = 'RADIO'
    elif 'ECHO' in role_name: cat_cible = 'ECHO'

    # 2. Récupération des demandes
    if is_medecin:
        demandes = DemandeExamenExterne.objects.all().order_by('-date_demande')
    elif cat_cible:
        demandes = DemandeExamenExterne.objects.filter(
            prestations__categorie=cat_cible
        ).distinct().order_by('-date_demande')
    else:
        # Si ce n'est ni médecin ni technicien reconnu
        return render(request, 'back-end/error.html', {'message': "Accès non autorisé pour ce profil."})

    historique_technique = []

    for dem in demandes:
        # On récupère tous les examens de la demande
        tous_les_examens = dem.prestations.all() 
        
        details_examens = []
        for p in tous_les_examens:
            # Recherche du résultat
            res = ExamenExterneResultat.objects.filter(demande=dem, prestation=p).first()
            
            details_examens.append({
                'prestation': p,
                'statut': res.statut if res else 'EN_ATTENTE',
                'id_resultat': res.id if res else None,
                'rapport': res.rapport if res else None,
                # Autorisation d'édition/visualisation : le médecin voit tout, le technicien seulement sa catégorie
                'est_ma_categorie': is_medecin or (p.categorie == cat_cible)
            })

        # Reconstruction de l'objet historique complet
        historique_technique.append({
            'id': dem.id,
            'client': dem.client, # Informations complètes du client (objet)
            'patient': dem.client.noms, # Gardé pour compatibilité
            'date': dem.date_demande,
            'details': details_examens,
            'medecin_demandeur': dem.medecin_demandeur if hasattr(dem, 'medecin_demandeur') else "Non spécifié",
            'type_urgence': getattr(dem, 'urgence', 'Standard') # Exemple d'info supplémentaire
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
    mois = timezone.now().month
    annee = timezone.now().year

    consultations = Consultation.objects.filter(
        triage__patient__type_patient='CONVENTIONNE',
        date_creation__year=annee,
        date_creation__month=mois
    ).select_related('triage__patient__entreprise').prefetch_related('examens__prestation')

    entreprises_data = {}

    for cons in consultations:
        patient = cons.triage.patient
        entreprise = patient.entreprise if patient.entreprise else None
        entreprise_nom = entreprise.nom if entreprise else "Sans entreprise"

        montant_total = sum(
            ex.prestation.prix * ex.quantite
            for ex in cons.examens.all()
            if ex.prestation and ex.prestation.prix
        )

        if entreprise_nom not in entreprises_data:
            entreprises_data[entreprise_nom] = {
                'patients': [],
                'somme': 0,
                'entreprise_obj': entreprise
            }

        entreprises_data[entreprise_nom]['patients'].append(patient)
        entreprises_data[entreprise_nom]['somme'] += montant_total

    # ✅ Mise à jour de la dette mensuelle dans Entreprise
    for data in entreprises_data.values():
        if data['entreprise_obj']:
            data['entreprise_obj'].dette_mensuelle = data['somme']
            data['entreprise_obj'].save()

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/entreprise/liste_conventionnes.html', {
        'entreprises_data': entreprises_data,
        'mois': mois,
        'annee': annee,
        'fonctionKey': fonctionKey
    })

#
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
    # 1. Traitement du paiement (POST)
    if request.method == 'POST':
        try:
            consultation_id = request.POST.get('consultation_id')
            montant_verse = Decimal(request.POST.get('montant', 0))
            reduction = Decimal(request.POST.get('reduction', 0))
            devise = request.POST.get('devise', 'USD')
            
            cons = Consultation.objects.get(id=consultation_id)
            
            # Conversion en USD si le paiement est en CDF
            montant_en_usd = montant_verse
            if devise == 'CDF':
                taux = ConfigurationHopital.get_taux()
                montant_en_usd = montant_verse / taux

            # Création du paiement lié à CETTE consultation
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

    # 2. Préparation des données pour l'affichage
    mois = timezone.now().month
    annee = timezone.now().year

    consultations = Consultation.objects.filter(
        triage__patient__type_patient='FIDELE',
        date_creation__year=annee,
        date_creation__month=mois
    ).prefetch_related('paiements', 'examens__prestation') 

    patients_data = []
    for cons in consultations:
        patient = cons.triage.patient
        # Calcul du coût total des prestations pour cette consultation
        montant_total = sum(
            ex.prestation.prix * ex.quantite 
            for ex in cons.examens.all() 
            if ex.prestation
        )
        
        # Calcul du total payé + remise via related_name 'paiements'
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

    # 3. Vérification des droits
    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 4. Rendu avec TOUTES les variables nécessaires
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
    """
    Vue dédiée à la prescription pour les clients externes.
    Utilise le suffixe _externe pour éviter tout conflit avec les patients internes.
    """
    # Récupération du client externe
    client = get_object_or_404(ClientExterne, id=client_id)
    
    if request.method == 'POST':
        try:
            # 1. Création de l'en-tête de l'ordonnance
            ordonnance = OrdonnanceExterne.objects.create(
                client=client,
                medecin=request.user,
                note_globale=request.POST.get('note_globale', '').strip()
            )
            
            # 2. Récupération des données du formulaire dynamique
            designations = request.POST.getlist('designation[]')
            posologies = request.POST.getlist('posologie[]')
            quantites = request.POST.getlist('quantite[]')
            
            # 3. Enregistrement des items (médicaments/examens)
            # On boucle sur la longueur de la liste la plus longue (designations)
            for i in range(len(designations)):
                designation = designations[i].strip()
                if designation: # On n'enregistre que si le nom n'est pas vide
                    OrdonnanceItem.objects.create(
                        ordonnance=ordonnance,
                        designation=designation,
                        posologie=posologies[i].strip() if i < len(posologies) else "",
                        quantite=quantites[i].strip() if i < len(quantites) else ""
                    )
            
            messages.success(request, f"Ordonnance enregistrée pour {client.noms}.")
            # Redirection vers la fiche du client externe (ajuste le nom selon ton projet)
            return redirect('detail_client_externe', client_id=client.id)
            
        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors de l'enregistrement : {e}")
            return render(request, 'back-end/client/prescrire.html', {'client': client})

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Si GET, on affiche simplement la page de prescription
    return render(request, 'back-end/client/prescrire_ordonnance_client_externe.html', {'client': client , 'fonctionKey' : fonctionKey})

#
# ==========================================================================================================
# DETAIL CLIENT EXTERNE
# ===========================================================================================================
@login_required
def detail_client_externe(request, client_id):
    # 1. Récupération du client
    client = get_object_or_404(ClientExterne, id=client_id)
    
    # 2. Récupération du rôle de l'utilisateur pour la sidebar/header
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
    # 3. Récupération optionnelle des ordonnances liées à ce client
    # Cela te permettra d'afficher la liste des ordonnances sur la page de détail
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
    # Récupère toutes les ordonnances, de la plus récente à la plus ancienne
    ordonnances = OrdonnanceExterne.objects.all().order_by('-date_creation')
    
    # Récupération du rôle pour le menu
    role_obj = Fonction.objects.filter(userKey=request.user).first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    
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