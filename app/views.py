from django.shortcuts import render , redirect , get_object_or_404
from .forms import *
from .models import *
from django.contrib.auth import authenticate , login as auth_login , logout ,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm ,UserChangeForm , PasswordChangeForm
from django.contrib import messages
from django.db.models import Q , Sum ,Prefetch , Count , ExpressionWrapper , OuterRef, Subquery , F , Value ,DecimalField, FloatField ,IntegerField ,Exists , Case, When
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
from django.db.models import ProtectedError


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

    # On récupère la liste de tous les employés ayant une fonction avec l'hôpital
    liste_postes = Fonction.objects.all().select_related('userKey', 'fonctionKey', 'hopital')

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

    # 2. Récupération du taux de change
    config = ConfigurationHopital.objects.first()
    taux_valeur = config.taux_usd_en_cdf if config else 2500.00
    taux = Decimal(str(taux_valeur))  # 1 USD = taux CDF

    # 3. Pagination (10 éléments par page)
    paginator = Paginator(prestations_list, 10)
    page_number = request.GET.get('page')
    prestations_obj = paginator.get_page(page_number)

    # 4. Calcul du prix en USD pour les éléments de la page actuelle
    #    prix est maintenant en CDF → on calcule USD = CDF / taux
    for item in prestations_obj:
        item.prix_usd = item.prix / taux if taux else Decimal('0')
        # item.prix reste le prix en CDF (stocké en base)

    # 5. Gestion de l'ajout (POST)
    if request.method == 'POST':
        form = PrestationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "La prestation a été ajoutée avec succès.")
            return redirect('gestion_prestations')
    else:
        form = PrestationForm()

    # 6. Gestion du rôle utilisateur
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

#
# ==================================================================================================
# SUPPRESSION PRESTATION
# ==================================================================================================
@login_required
def supprimer_prestation(request, pk):
    prestation = get_object_or_404(Prestation, pk=pk)

    if request.method == "POST":
        prestation.delete()
        messages.success(request, "La prestation a été supprimée avec succès.")
        return redirect("gestion_prestations")

    return redirect("gestion_prestations")


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


    # Récupérer les paramètres de filtre
    hopital_filter = request.GET.get('hopital', '')
    date_filter = request.GET.get('date', '')
    heure_filter = request.GET.get('heure', '')


    # Base queryset - ordre décroissant par date_creation (les plus récents en premier)
    patients = Patient.objects.select_related('entreprise', 'created_by', 'hopital').order_by('-date_creation')


    # Filtre par hôpital
    if hopital_filter:
        # Si un filtre est spécifié, l'appliquer
        if fonctionKey == 'admin':
            # Admin peut choisir n'importe quel hôpital
            patients = patients.filter(hopital_id=hopital_filter)
        else:
            # Autres utilisateurs : peuvent voir leur hôpital OU les hôpitaux sans restriction
            patients = patients.filter(hopital_id=hopital_filter)
    elif hopital_user:
        # Si aucun filtre sélectionné, afficher par défaut l'hôpital de l'utilisateur
        patients = patients.filter(hopital=hopital_user)


    # Filtre par date
    if date_filter:
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
            patients = patients.filter(date_creation__date=date_obj)
        except ValueError:
            pass


    # Filtre par heure (heure de début)
    if heure_filter:
        try:
            from datetime import datetime
            time_obj = datetime.strptime(heure_filter, '%H:%M').time()
            patients = patients.filter(
                date_creation__hour__gte=time_obj.hour,
                date_creation__minute__gte=time_obj.minute
            )
        except ValueError:
            pass


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


                if patient.entreprise:
                    return redirect('liste_attente_triage')


                return redirect('payer_fiche', patient_id=patient.id)


            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.capitalize()}: {error}")
    else:
        form = PatientForm()


    # Entreprises pour le formulaire
    entreprises = Entreprise.objects.filter(hopital=hopital_user).order_by('nom') if hopital_user else Entreprise.objects.none()


    # Liste des hôpitaux pour le filtre (TOUS les utilisateurs peuvent voir tous les hôpitaux)
    hopitaux = Hopital.objects.all().order_by('nomH')  # ← CORRIGÉ ICI


    return render(request, 'back-end/patient/enregistrement_patient.html', {
        'patients': patients,
        'form': form,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
        'entreprises': entreprises,
        'hopitaux': hopitaux,
        'hopital_filter': hopital_filter,
        'date_filter': date_filter,
        'heure_filter': heure_filter,
    })

#
# ==================================================================================================
# SUPPRIMER PATIENT PAR ADMIN 
# ==================================================================================================
@login_required
def supprimer_patient(request, patient_id):
    # 1. Rôle et hôpital de l’utilisateur
    user_fonction = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = user_fonction.hopital if user_fonction else None
    fonctionKey = user_fonction.fonctionKey.roleName if (user_fonction and user_fonction.fonctionKey) else "Invité"

    if not hopital_user and fonctionKey != 'admin':
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    # 2. Récupération du patient
    # - admin : peut supprimer n'importe quel patient
    # - autres : seulement les patients de leur hôpital
    if fonctionKey == 'admin':
        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            messages.error(request, "Le patient demandé n'existe pas.")
            return redirect('enregistrement_patient')
    else:
        try:
            patient = Patient.objects.get(id=patient_id, hopital=hopital_user)
        except Patient.DoesNotExist:
            messages.error(
                request,
                "Le patient demandé n'existe pas ou n'appartient pas à votre hôpital."
            )
            return redirect('enregistrement_patient')

    # 3. Permissions (ici on autorise admin + éventuellement d'autres rôles)
    # Adapte selon tes règles exactes
    if fonctionKey not in ['admin']:
        messages.error(request, "Vous n'avez pas la permission de supprimer un patient.")
        return redirect('enregistrement_patient')

    # 4. Suppression
    try:
        patient_noms = patient.noms
        patient.delete()
        messages.success(request, f"Le patient {patient_noms} a été supprimé avec succès.")
    except Exception as e:
        messages.error(request, f"Erreur lors de la suppression : {str(e)}")

    return redirect('enregistrement_patient')
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
    # Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None


    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')


    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user)


    # Taux de change
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')  # 1 USD = taux CDF
    if not taux or taux == 0:
        taux = Decimal('2300.00')


    # Heure locale pour info (jour/nuit)
    now = timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())
    now_local = timezone.localtime(now)
    heure_actuelle = now_local.hour
    est_nuit = heure_actuelle >= 16 or heure_actuelle < 7
    libelle_periode = "nuit" if est_nuit else "jour"


    # Récupérer TOUTES les prestations ADM pour cet hôpital
    prestations_adm = (
        Prestation.objects
        .filter(
            categorie='ADM',
            hopital=hopital_user
        )
        .order_by('categorie', 'libelle')
    )


    if not prestations_adm.exists():
        messages.error(
            request,
            f"Aucune prestation administrative (ADM) n'est configurée pour "
            f"l'hôpital {hopital_user.nomH}."
        )
        return redirect('enregistrement_patient')


    # --- Calcul des paiements existants pour ce patient (service FICHE) ---
    paiements_existants = Paiement.objects.filter(
        patient=patient,
        service='FICHE',
        hopital=hopital_user
    )


    total_deja_paye_cdf = Decimal('0')
    total_deja_reduction_cdf = Decimal('0')
    
    for p in paiements_existants:
        if p.devise == 'CDF':
            total_deja_paye_cdf += p.montant_verse or Decimal('0')
            total_deja_reduction_cdf += p.montant_reduction or Decimal('0')
        else:  # USD
            total_deja_paye_cdf += (p.montant_verse or Decimal('0')) * taux
            total_deja_reduction_cdf += (p.montant_reduction or Decimal('0')) * taux


    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None


    # --- Traitement du formulaire de paiement ---
    if request.method == 'POST':
        # Liste des IDs de prestations cochées
        prestation_ids = request.POST.getlist('prestation_ids')
        montant_saisi = Decimal(request.POST.get('montant', '0') or '0')
        montant_reduction = Decimal(request.POST.get('montant_reduction', '0') or '0')
        devise = request.POST.get('devise', 'CDF')


        if not prestation_ids:
            messages.error(
                request,
                "Vous devez sélectionner au moins une fiche (prestation administrative)."
            )
            return redirect('payer_fiche', patient_id=patient.id)


        # Récupérer les prestations sélectionnées
        prestations_selectionnees = (
            Prestation.objects
            .filter(
                id__in=prestation_ids,
                categorie='ADM',
                hopital=hopital_user
            )
        )


        if len(prestations_selectionnees) != len(prestation_ids):
            messages.error(request, "Une ou plusieurs prestations sélectionnées sont invalides.")
            return redirect('payer_fiche', patient_id=patient.id)


        # Calcul du coût total des prestations sélectionnées (en CDF)
        total_a_payer_cdf = sum(
            (p.prix or Decimal('0')) for p in prestations_selectionnees
        )


        # Convertir le montant saisi en CDF
        if devise == 'CDF':
            montant_saisi_cdf = montant_saisi
            montant_reduction_cdf = montant_reduction
        else:  # USD
            montant_saisi_cdf = montant_saisi * taux
            montant_reduction_cdf = montant_reduction * taux


        # Vérifier si le montant dépasse le total (avec tolérance)
        tolerance_cdf = Decimal('1')
        total_verse_plus_reduction = montant_saisi_cdf + montant_reduction_cdf
        
        if total_verse_plus_reduction > (total_a_payer_cdf - total_deja_paye_cdf - total_deja_reduction_cdf + tolerance_cdf):
            messages.error(
                request,
                f"Le montant dépasse le reste à payer "
                f"({total_a_payer_cdf - total_deja_paye_cdf - total_deja_reduction_cdf:.0f} CDF / "
                f"{(total_a_payer_cdf - total_deja_paye_cdf - total_deja_reduction_cdf) / taux:.2f} USD)."
            )
            return redirect('payer_fiche', patient_id=patient.id)


        if montant_saisi_cdf > 0 or montant_reduction_cdf > 0:
            # Créer le paiement avec réduction
            Paiement.objects.create(
                patient=patient,
                service='FICHE',
                montant_verse=montant_saisi,
                montant_reduction=montant_reduction,
                devise=devise,
                caissier=request.user,
                hopital=hopital_user,
            )


            nouveau_total_cdf = total_deja_paye_cdf + montant_saisi_cdf
            nouveau_total_reduction_cdf = total_deja_reduction_cdf + montant_reduction_cdf


            if nouveau_total_cdf + nouveau_total_reduction_cdf >= (total_a_payer_cdf - Decimal('1')):  # tolérance 1 CDF
                patient.fiche_payee = True
                patient.save()
                
                # TOUTES les prestations ADM redirigent vers les signes vitaux
                messages.success(
                    request,
                    f"Paiement terminé. Veuillez procéder au prélèvement des signes vitaux de {patient.noms}."
                )
                # Rediriger vers la vue de saisie des signes vitaux
                return redirect('saisir_signes', patient_id=patient.id)
            else:
                nouveau_reste_cdf = total_a_payer_cdf - nouveau_total_cdf - nouveau_total_reduction_cdf
                nouveau_reste_usd = nouveau_reste_cdf / taux
                messages.success(
                    request,
                    f"Paiement enregistré. Reste à payer : {nouveau_reste_cdf:.0f} CDF "
                    f"(~ {nouveau_reste_usd:.2f} USD)."
                )
                return redirect('payer_fiche', patient_id=patient.id)


    # Pour l'affichage initial
    total_prestations_adm_cdf = sum((p.prix or Decimal('0')) for p in prestations_adm)
    reste_a_payer_cdf = max(Decimal('0'), total_prestations_adm_cdf - total_deja_paye_cdf - total_deja_reduction_cdf)
    reste_a_payer_usd = reste_a_payer_cdf / taux


    return render(request, 'back-end/finance/payer_fiche.html', {
        'patient': patient,
        'prestations_adm': prestations_adm,
        'reste_a_payer': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'deja_paye': patient.fiche_payee,
        'est_nuit': est_nuit,
        'heure_actuelle': heure_actuelle,
        'libelle_periode': libelle_periode,
        'total_prestations_adm_cdf': total_prestations_adm_cdf,
        'total_prestations_adm_usd': total_prestations_adm_cdf / taux,
        'ResteDejaPayeCDF': total_deja_paye_cdf,
        'ResteDejaPayeUSD': total_deja_paye_cdf / taux,
    })
# 21
# ==================================================================================================
# HISTORIQUE DE PAIEMENT
# ==================================================================================================
@login_required
def historique_paiements(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    taux = ConfigurationHopital.get_taux()  # 1 USD = taux CDF

    # ---- Paiements du patient ----
    paiements = Paiement.objects.filter(patient=patient)
    if hopital_user:
        paiements = paiements.filter(hopital=hopital_user)

    # Sommes brutes par devise
    recettes = paiements.aggregate(
        usd=Sum('montant_verse', filter=Q(devise='USD')),
        cdf=Sum('montant_verse', filter=Q(devise='CDF'))
    )

    total_paye_usd_brut = recettes['usd'] or Decimal('0.00')
    total_paye_cdf_brut = recettes['cdf'] or Decimal('0.00')

    # Total payé en CDF (tout converti en CDF)
    total_paye_cdf = total_paye_cdf_brut + (total_paye_usd_brut * taux)
    # Total payé en USD (pour affichage)
    total_paye_en_usd = total_paye_cdf / taux if taux else Decimal('0')

    # ---- Fiche ----
    # On pourrait aussi déterminer jour/nuit ici si nécessaire
    prestation_fiche = None
    if hopital_user:
        prestation_fiche = Prestation.objects.filter(
            categorie='ADM',
            libelle__icontains='Fiche',
            hopital=hopital_user
        ).first()

    # Prix de la fiche en CDF (stocké en base)
    cout_fiche_cdf = Decimal(str(prestation_fiche.prix)) if prestation_fiche else Decimal('0.00')
    cout_fiche_usd = cout_fiche_cdf / taux if taux else Decimal('0')

    # ---- Examens ----
    examens_qs = Prestation.objects.filter(
        demandeexamen__consultation__triage__patient=patient
    )
    if hopital_user:
        examens_qs = examens_qs.filter(hopital=hopital_user)

    # Prix des examens en CDF
    cout_examens_cdf = examens_qs.aggregate(total=Sum('prix'))['total'] or Decimal('0.00')
    cout_examens_usd = cout_examens_cdf / taux if taux else Decimal('0')

    # ---- Bloc ----
    bloc_qs = BlocOperatoire.objects.filter(consultation__triage__patient=patient)
    if hopital_user:
        bloc_qs = bloc_qs.filter(consultation__triage__patient__hopital=hopital_user)
    bloc = bloc_qs.first()

    cout_bloc_cdf = Decimal('0.00')
    if bloc:
        if hasattr(bloc, 'prestation') and bloc.prestation:
            cout_bloc_cdf = Decimal(str(bloc.prestation.prix))
        elif hasattr(bloc, 'cout_total') and bloc.cout_total:
            cout_bloc_cdf = Decimal(str(bloc.cout_total))

    cout_bloc_usd = cout_bloc_cdf / taux if taux else Decimal('0')

    # ---- Total des coûts ----
    total_cout_cdf = cout_fiche_cdf + cout_examens_cdf + cout_bloc_cdf
    total_cout_usd = total_cout_cdf / taux if taux else Decimal('0')

    # ---- Reste à payer ----
    reste_a_payer_cdf = max(Decimal('0'), total_cout_cdf - total_paye_cdf)
    reste_a_payer_usd = reste_a_payer_cdf / taux if taux else Decimal('0')

    # ---- Dernière consultation ----
    consultation_qs = Consultation.objects.filter(triage__patient=patient)
    if hopital_user:
        consultation_qs = consultation_qs.filter(triage__patient__hopital=hopital_user)
    consultation = consultation_qs.order_by('-date_creation').first()

    peut_imprimer_facture = total_cout_cdf > 0
    facture_reglee = reste_a_payer_cdf <= Decimal('1')  # 1 CDF de tolérance

    context = {
        'patient': patient,
        'paiements_liste': paiements.order_by('-date_paiement'),
        'cout_total_cdf': total_cout_cdf,
        'cout_total_usd': total_cout_usd,
        'total_paye_cdf': total_paye_cdf,
        'total_paye_usd': total_paye_en_usd,  # même valeur, nom plus clair pour le template
        'total_paye_en_usd': total_paye_en_usd,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'est_debiteur': reste_a_payer_cdf > Decimal('1'),
        'facture_reglee': facture_reglee,
        'peut_imprimer_facture': peut_imprimer_facture,
        'derniere_consultation': consultation,
        'bloc_id': bloc.id if bloc else None,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
        'taux': taux,
    }
    return render(request, 'back-end/finance/historique.html', context)
#
# ================================================================================================
# IMPRIMER HISTORIQUE PAIEMENT 
# ===============================================================================================
@login_required
def imprimer_facture(request, patient_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user)
    taux = ConfigurationHopital.get_taux()

    paiements = Paiement.objects.filter(patient=patient, hopital=hopital_user)

    recettes = paiements.aggregate(
        usd=Sum('montant_verse', filter=Q(devise='USD')),
        cdf=Sum('montant_verse', filter=Q(devise='CDF'))
    )

    total_paye_usd = recettes['usd'] or Decimal('0.00')
    total_paye_cdf = recettes['cdf'] or Decimal('0.00')
    total_paye_en_usd = total_paye_usd + (total_paye_cdf / taux)

    prestation_fiche = Prestation.objects.filter(
        categorie='ADM',
        libelle__icontains='Fiche',
        hopital=hopital_user
    ).first()

    cout_fiche = Decimal(str(prestation_fiche.prix)) if prestation_fiche else Decimal('0.00')

    total_cout_usd = cout_fiche
    reste_a_payer_usd = max(Decimal('0.00'), total_cout_usd - total_paye_en_usd)
    reste_a_payer_cdf = reste_a_payer_usd * taux

    context = {
        'patient': patient,
        'paiements_liste': paiements.order_by('-date_paiement'),
        'taux': taux,
        'cout_total_usd': total_cout_usd,
        'cout_total_cdf': total_cout_usd * taux,
        'total_paye_usd': total_paye_usd,
        'total_paye_cdf': total_paye_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'facture_reglee': reste_a_payer_usd <= Decimal('0.01'),
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
    }
    return render(request, 'back-end/finance/imprimer_facture.html', context)

# 22
# ==================================================================================================
# IMPRIMER FACTURE
# ==================================================================================================
@login_required
def imprimer_recu_direct(request, paiement_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        return redirect('enregistrement_patient')

    paiement = get_object_or_404(
        Paiement.objects.select_related(
            'patient', 'caissier', 'consultation', 'bloc_op', 'entreprise'
        ),
        id=paiement_id,
        hopital=hopital_user
    )

    patient = paiement.patient
    taux = ConfigurationHopital.get_taux()
    date_reelle = paiement.date_paiement

    nom_prestation = paiement.get_service_display()
    details_ticket = []

    # Cas consultation / examens
    if paiement.consultation:
        examens_qs = getattr(paiement.consultation, 'examens', None)
        if examens_qs is not None:
            examens_associes = examens_qs.select_related('prestation').all()
            for exam in examens_associes:
                if getattr(exam, 'prestation', None):
                    details_ticket.append({
                        'libelle': exam.prestation.libelle,
                        'prix': exam.prestation.prix,
                    })

            if details_ticket:
                nom_prestation = details_ticket[0]['libelle']

    # Cas bloc opératoire
    if paiement.bloc_op and hasattr(paiement.bloc_op, 'prestation') and paiement.bloc_op.prestation:
        nom_prestation = paiement.bloc_op.prestation.libelle
        details_ticket.append({
            'libelle': paiement.bloc_op.prestation.libelle,
            'prix': paiement.bloc_op.prestation.prix,
        })

    # Cas paiement entreprise
    if paiement.service == 'ENTREPRISE' and paiement.entreprise:
        nom_prestation = f"Paiement Entreprise : {paiement.entreprise.nom}"

    # Montant converti si besoin
    montant_usd = paiement.montant_verse
    if paiement.devise == 'CDF':
        montant_usd = paiement.montant_verse / taux

    context = {
        'paiement': paiement,
        'patient': patient,
        'hopital_user': hopital_user,
        'fonctionKey': fonctionKey,
        'date_paiement_fix': date_reelle,
        'nom_prestation': nom_prestation,
        'details_ticket': details_ticket,
        'taux': taux,
        'montant_usd': montant_usd,
    }
    return render(request, 'back-end/finance/ticket_paiement.html', context)
# 23
# ==================================================================================================
# PATIENT LISTE D'ATTENTE TRIAGE
# ==================================================================================================
@login_required
def liste_attente_triage(request):
    taux = ConfigurationHopital.get_taux()  # 1 USD = taux CDF

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    # --- Détermination jour / nuit (16h–7h = nuit) ---
    now = timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())
    now_local = timezone.localtime(now)
    heure_actuelle = now_local.hour

    est_nuit = heure_actuelle >= 16 or heure_actuelle < 7
    libelle_cible = "Fiche nuit" if est_nuit else "Fiche jour"

    # --- Récupération de la prestation (prix en CDF) ---
    prestation_fiche = Prestation.objects.filter(
        categorie='ADM',
        libelle__icontains=libelle_cible,
        hopital=hopital_user
    ).first()

    if not prestation_fiche:
        # Fallback si aucune prestation trouvée
        messages.error(
            request,
            f"La prestation '{libelle_cible}' n'est pas configurée pour votre hôpital."
        )
        # Tu peux choisir de rediriger ou continuer avec un prix par défaut
        # return redirect('enregistrement_patient')
        prix_fiche_cdf = Decimal('0')
    else:
        prix_fiche_cdf = prestation_fiche.prix or Decimal('0')

    # Prix en USD juste pour affichage (si besoin dans le template)
    prix_fiche_usd = prix_fiche_cdf / taux if taux else Decimal('0')

    patients_liste = Patient.objects.filter(hopital=hopital_user).order_by('-date_creation')

    for patient in patients_liste:
        # Patients non SIMPLE : on considère qu'ils n'ont pas à payer la fiche
        if patient.type_patient != 'SIMPLE':
            patient.a_solde_fiche = True
            patient.total_fiche_cdf = Decimal('0')  # ou total_fiche_usd si tu veux garder ce champ
            patient.doit_payer_fiche = False
        else:
            patient.doit_payer_fiche = True

            # Tous les paiements FICHE pour ce patient
            paiements = Paiement.objects.filter(
                patient=patient,
                service='FICHE',
                hopital=hopital_user
            )

            # Calcul du total payé en CDF (en convertissant les USD en CDF)
            total_paye_cdf = Decimal('0')
            for p in paiements:
                if p.devise == 'CDF':
                    total_paye_cdf += p.montant_verse
                else:  # USD
                    total_paye_cdf += p.montant_verse * taux

            # On stocke le total payé (en CDF) dans le patient (adapte le nom du champ selon ton modèle)
            patient.total_fiche_cdf = total_paye_cdf

            # Le patient a soldé si le total payé >= prix de la fiche (en CDF)
            patient.a_solde_fiche = total_paye_cdf >= prix_fiche_cdf

        # Signes vitaux
        patient.a_signes_vitaux_deja_pris = SigneVital.objects.filter(patient=patient).exists()

    fonctionKey = role.fonctionKey.roleName if (role and role.fonctionKey) else None

    return render(request, 'back-end/infirmerie/liste_attente.html', {
        'patients': patients_liste,
        'taux': taux,
        'prix_fiche': prix_fiche_usd,      # pour affichage en USD si tu veux
        'prix_fiche_cdf': prix_fiche_cdf,  # pour affichage en CDF
        'fonctionKey': fonctionKey,
        'libelle_cible': libelle_cible,
        'est_nuit': est_nuit,
        'heure_actuelle': heure_actuelle,
    })


# 24
# ==================================================================================================
# PATIENT SIGNE VITAUX
# ==================================================================================================
@login_required
def saisir_signes(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    today = timezone.now().date()
    
    # Récupérer l'hôpital de l'utilisateur
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    
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
                triage_existant.hopital = hopital_user  # ← AJOUTÉ : Assigner l'hôpital
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
                    hopital=hopital_user,  # ← AJOUTÉ : Assigner l'hôpital
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
    # Récupérer les informations de l'utilisateur
    user_fonction = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = user_fonction.hopital if user_fonction else None
    fonctionKey = user_fonction.fonctionKey.roleName if (user_fonction and user_fonction.fonctionKey) else "Invité"
    
    # Récupérer tous les signes vitaux
    historique_global = SigneVital.objects.select_related('patient', 'infirmier', 'hopital').order_by('-date_prelevement')
    
    # DEBUG: Afficher la requête SQL
    print("=== REQUÊTE SQL ===")
    print(str(historique_global.query))
    print("==================")
    
    # DEBUG: Afficher les IDs
    print("=== IDs des signes vitaux ===")
    for s in historique_global:
        print(f"ID: {s.id}, Patient: {s.patient.noms}, Hopital: {s.hopital}")
    print("============================")
    
    # Filtrer par hôpital seulement si l'utilisateur a un hôpital
    if hopital_user and fonctionKey != 'admin':
        historique_global = historique_global.filter(
            models.Q(hopital=hopital_user) | models.Q(hopital__isnull=True)
        )
    
    context = {
        'fonctionKey': fonctionKey,
        'historique': historique_global,
        'hopital_user': hopital_user,
    }
    return render(request, 'back-end/infirmerie/liste_globale_triage.html', context)
#
#
# ********************************************************************************************************************************
# ********************************************************************************************************************************
#
#
# ************************************************************* Mise en jour 
@login_required
def modifier_signes_vitaux(request, signe_id):
    print(f"=== MODIFICATION SIGNE VITAL ID: {signe_id} ===")
    
    # Récupérer le signe vital à modifier
    try:
        signe = SigneVital.objects.select_related('patient', 'infirmier', 'hopital', 'session').get(id=signe_id)
        print(f"Signe trouvé: {signe.patient.noms}")
    except SigneVital.DoesNotExist:
        print(f"Signe ID {signe_id} NON TROUVÉ!")
        messages.error(request, "Ce prélèvement n'existe pas.")
        return redirect('liste_globale_triage')
    
    # Vérifier les permissions
    user_fonction = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = user_fonction.hopital if user_fonction else None
    fonctionKey = user_fonction.fonctionKey.roleName if (user_fonction and user_fonction.fonctionKey) else "Invité"
    
    print(f"Votre rôle: {fonctionKey}")
    print(f"Votre hôpital: {hopital_user}")
    print(f"Hôpital du signe: {signe.hopital}")
    
    # Seulement admin, infirmier, médecin et receptionniste peuvent modifier
    if fonctionKey not in ['admin', 'infirmier', 'medecin', 'receptionniste']:
        print(f"PERMISSION REFUSÉE: {fonctionKey} n'est pas dans ['admin', 'infirmier', 'medecin', 'receptionniste']")
        messages.error(request, "Vous n'avez pas la permission de modifier ce prélèvement.")
        return redirect('liste_globale_triage')
    
    # Vérifier que le signe vital appartient à l'hôpital de l'utilisateur (ou pas d'hôpital)
    if hopital_user and fonctionKey != 'admin':
        if signe.hopital and signe.hopital.id != hopital_user.id:
            messages.error(request, "Vous ne pouvez modifier que les signes vitaux de votre hôpital.")
            return redirect('liste_globale_triage')
    
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            temperature = request.POST.get('temperature')
            tension_arterielle = request.POST.get('tension_arterielle')
            frequence_cardiaque = request.POST.get('frequence_cardiaque')
            frequence_respiratoire = request.POST.get('frequence_respiratoire')
            poids = request.POST.get('poids')
            saturation_oxygene = request.POST.get('saturation_oxygene')
            
            # Validation et conversion des données
            if temperature:
                temperature = float(temperature)
                if temperature < 30 or temperature > 45:
                    messages.error(request, "La température doit être entre 30°C et 45°C.")
                    return redirect('modifier_signes_vitaux', signe_id=signe_id)
            else:
                messages.error(request, "La température est obligatoire.")
                return redirect('modifier_signes_vitaux', signe_id=signe_id)
            
            if poids:
                poids = float(poids)
                if poids < 1 or poids > 300:
                    messages.error(request, "Le poids doit être entre 1 kg et 300 kg.")
                    return redirect('modifier_signes_vitaux', signe_id=signe_id)
            else:
                messages.error(request, "Le poids est obligatoire.")
                return redirect('modifier_signes_vitaux', signe_id=signe_id)
            
            if frequence_cardiaque:
                frequence_cardiaque = int(frequence_cardiaque)
                if frequence_cardiaque < 30 or frequence_cardiaque > 250:
                    messages.error(request, "La fréquence cardiaque doit être entre 30 et 250 bpm.")
                    return redirect('modifier_signes_vitaux', signe_id=signe_id)
            else:
                messages.error(request, "La fréquence cardiaque est obligatoire.")
                return redirect('modifier_signes_vitaux', signe_id=signe_id)
            
            if frequence_respiratoire:
                frequence_respiratoire = int(frequence_respiratoire)
                if frequence_respiratoire < 5 or frequence_respiratoire > 60:
                    messages.error(request, "La fréquence respiratoire doit être entre 5 et 60 cycles/min.")
                    return redirect('modifier_signes_vitaux', signe_id=signe_id)
            
            if saturation_oxygene:
                saturation_oxygene = int(saturation_oxygene)
                if saturation_oxygene < 50 or saturation_oxygene > 100:
                    messages.error(request, "La saturation en oxygène doit être entre 50% et 100%.")
                    return redirect('modifier_signes_vitaux', signe_id=signe_id)
            
            # Mettre à jour les valeurs
            signe.temperature = temperature
            signe.poids = poids
            signe.tension_arterielle = tension_arterielle if tension_arterielle else signe.tension_arterielle
            signe.frequence_cardiaque = frequence_cardiaque
            signe.frequence_respiratoire = frequence_respiratoire if frequence_respiratoire else signe.frequence_respiratoire
            signe.saturation_oxygene = saturation_oxygene if saturation_oxygene else signe.saturation_oxygene
            
            # Sauvegarder
            signe.save()
            
            messages.success(request, f"Signes vitaux de {signe.patient.noms} modifiés avec succès.")
            return redirect('liste_globale_triage')
            
        except ValueError as e:
            messages.error(request, f"Erreur de format : Veuillez vérifier les valeurs saisies.")
            return redirect('modifier_signes_vitaux', signe_id=signe_id)
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification : {str(e)}")
            return redirect('modifier_signes_vitaux', signe_id=signe_id)
    
    # Afficher le formulaire de modification
    context = {
        'signe': signe,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
    }
    
    print(f"Rendu du template avec signe.id={signe.id}")
    return render(request, 'back-end/infirmerie/modifier_signes_vitaux.html', context)
# ***********************************************************************************************************************************

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
    Liste de consultations côté médecin.
    - Montre TOUTES les prises de signes vitaux de l'hôpital de l'utilisateur
    - Les NON consultées en premier, puis les consultées
    - Option de filtre: tous | avec_session | sans_session
    """
    filtre = request.GET.get('filtre', 'tous')

    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    # Base: toutes les prises pour l'hôpital de l'utilisateur
    patients_prets = (
        SigneVital.objects
        .filter(patient__hopital=hopital_user)
        .select_related('patient', 'infirmier', 'session')
        .prefetch_related('session__items__prestation')
        .annotate(
            priorite=Case(
                When(est_consulte=False, then=Value(0)),
                default=Value(1),
                output_field=IntegerField()
            )
        )
    )

    # Filtres selon la présence de session
    if filtre == 'avec_session':
        patients_prets = patients_prets.filter(session__isnull=False)
    elif filtre == 'sans_session':
        patients_prets = patients_prets.filter(session__isnull=True)

    # Tri: d'abord par priorité (non consultés), puis par date (les plus récents en haut)
    patients_prets = patients_prets.order_by('priorite', '-date_prelevement')

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    context = {
        'fonctionKey': fonctionKey,
        'patients_prets': patients_prets,
        'filtre': filtre,
    }
    return render(request, 'back-end/medecin/liste_consultation.html', context)
#
# ===========================================================================================================
# MARQUE CONSULTE
# ============================================================================================================
@login_required
def marquer_consulte(request, sv_id):
    """
    Marque une prise de signes vitaux comme consultée
    (elle RESTE visible dans la liste, mais descend sous les non consultées).
    """
    signe = get_object_or_404(SigneVital, id=sv_id)

    if not signe.est_consulte:
        signe.est_consulte = True
        signe.save(update_fields=['est_consulte'])

    # Redirige vers l'espace de consultation (première consultation)
    return redirect('consultation_medicale', triage_id=signe.id)

#
# ==================================================================================================
# MEDECIN RECONSULTATION
# ==================================================================================================
@login_required
def reconsulter(request, sv_id):
    """
    Reconsultation d'un patient déjà consulté.
    - Si une consultation existe : on la modifie.
    - Si aucune consultation n'existe : on en crée une nouvelle automatiquement.
    """
    triage = get_object_or_404(SigneVital.objects.select_related('patient'), id=sv_id)

    role_obj = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if triage.patient.hopital != hopital_user:
        messages.error(request, "Ce patient appartient à un autre hôpital.")
        return redirect('liste_consultation_medecin')

    # Consultation précédente (optionnelle maintenant)
    consultation = Consultation.objects.filter(triage=triage).first()

    if not consultation:
        # Créer automatiquement une nouvelle consultation vide
        consultation = Consultation.objects.create(
            triage=triage,
            medecin=request.user,
            hopital=hopital_user,
            # PAS de patient=... car 'patient' est une property
        )
        messages.info(
            request,
            f"Aucune consultation précédente trouvée. Une nouvelle consultation a été créée pour {triage.patient.noms}."
        )

    # Chargement des examens et médicaments précédents (s'il y a une consultation)
    examens_precedents = DemandeExamen.objects.filter(
        consultation=consultation
    ).select_related('prestation')

    ordonnance = Ordonnance.objects.filter(consultation=consultation).first()
    medicaments_precedents = (
        LigneMedicament.objects.filter(ordonnance=ordonnance)
        if ordonnance else []
    )

    if request.method == 'POST':
        # On modifie la consultation existante
        form = ConsultationForm(request.POST, instance=consultation)

        examens_ids = request.POST.getlist('examens_ids')
        noms_medocs = request.POST.getlist('nom_medicament')
        posologies = request.POST.getlist('posologie')
        durees = request.POST.getlist('duree')
        quantites = request.POST.getlist('quantite')  # ← nouveau

        if form.is_valid():
            try:
                with transaction.atomic():
                    consultation_obj = form.save(commit=False)
                    consultation_obj.triage = triage
                    consultation_obj.medecin = request.user
                    consultation_obj.hopital = hopital_user
                    consultation_obj.save()

                    # Mettre à jour les examens
                    DemandeExamen.objects.filter(
                        consultation=consultation_obj,
                        statut='EN_ATTENTE'
                    ).delete()

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

                    # Mettre à jour les médicaments
                    if any(n.strip() for n in noms_medocs if n):
                        ordonnance_obj, _ = Ordonnance.objects.get_or_create(
                            consultation=consultation_obj,
                            type_ordonnance='URGENCE',
                            defaults={'hopital': hopital_user}
                        )
                        if not ordonnance_obj.hopital:
                            ordonnance_obj.hopital = hopital_user
                            ordonnance_obj.save()

                        LigneMedicament.objects.filter(ordonnance=ordonnance_obj).delete()

                        for i, nom in enumerate(noms_medocs):
                            if nom and nom.strip():
                                poso = posologies[i] if i < len(posologies) else ""
                                dur = durees[i] if i < len(durees) else ""
                                qty = quantites[i] if i < len(quantites) and quantites[i] else 1

                                # Nettoyer et convertir quantite
                                try:
                                    qty_int = int(qty)
                                except (ValueError, TypeError):
                                    qty_int = 1

                                LigneMedicament.objects.create(
                                    ordonnance=ordonnance_obj,
                                    nom_medicament=nom,
                                    posologie=poso,
                                    duree=dur,
                                    statut='EN_COURS',
                                    hopital=hopital_user,
                                    quantite=qty_int
                                )

                    triage.est_consulte = True
                    triage.save()

                messages.success(
                    request,
                    f"Reconsultation de {triage.patient.noms} enregistrée avec succès !"
                )
                return redirect('liste_consultation_medecin')

            except Exception as e:
                messages.error(request, f"Une erreur technique est survenue : {str(e)}")
        else:
            messages.error(request, "Veuillez vérifier les erreurs dans le formulaire clinique.")

    else:
        # GET : pré-remplir le formulaire avec l'ancienne consultation (ou nouvelle si créée)
        form = ConsultationForm(instance=consultation)

    examens_disponibles = Prestation.objects.filter(
        categorie__in=['LABO', 'ECHO', 'RADIO'],
        hopital=hopital_user
    ).order_by('categorie', 'libelle')

    context = {
        'triage': triage,
        'form': form,
        'examens_disponibles': examens_disponibles,
        'consultation': consultation,
        'fonctionKey': fonctionKey,
        'examens_precedents': examens_precedents,
        'medicaments_precedents': medicaments_precedents,
        'mode': 'reconsultation',
    }
    return render(request, 'back-end/medecin/consultation_medecin.html', context)


# 30
# ==================================================================================================
# MEDECIN   CONSULTATION PATIENT
# ==================================================================================================
@login_required
def consultation_medicale(request, triage_id):
    """
    Première consultation d'un patient (ou tentative).
    Si une consultation existe déjà, on bloque et on redirige.
    """
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

    # Si déjà consulté et consultation existe → on bloque
    if triage.est_consulte and consultation is not None:
        messages.warning(
            request,
            f"Le dossier de consultation pour {triage.patient.noms} a déjà été clôturé."
        )
        return redirect('liste_consultation_medecin')

    if request.method == 'POST':
        if consultation is not None:
            messages.error(
                request,
                "Erreur : Cette consultation a déjà été enregistrée par un autre utilisateur."
            )
            return redirect('liste_consultation_medecin')

        form = ConsultationForm(request.POST, instance=consultation)

        examens_ids = request.POST.getlist('examens_ids')
        noms_medocs = request.POST.getlist('nom_medicament')
        posologies = request.POST.getlist('posologie')
        durees = request.POST.getlist('duree')

        # --- DEBUG ---
        print("=== DEBUG CONSULTATION ===")
        print("nom_medicament:", noms_medocs)
        print("posologie:", posologies)
        print("duree:", durees)
        print("any med?:", any(n.strip() for n in noms_medocs if n))
        # ------------

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

                    # Examens
                    DemandeExamen.objects.filter(
                        consultation=consultation_obj,
                        statut='EN_ATTENTE'
                    ).delete()

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

                    # Médicaments
                    print("=== AVANT BLOC MEDICAMENTS ===")
                    if any(n.strip() for n in noms_medocs if n):
                        print("ON ENTRE DANS LE BLOC MEDICAMENTS")
                        ordonnance, _ = Ordonnance.objects.get_or_create(
                            consultation=consultation_obj,
                            type_ordonnance='URGENCE',
                            defaults={'hopital': hopital_user}
                        )
                        print("Ordonnance:", ordonnance.id, ordonnance.type_ordonnance)

                        if not ordonnance.hopital:
                            ordonnance.hopital = hopital_user
                            ordonnance.save()

                        LigneMedicament.objects.filter(ordonnance=ordonnance).delete()

                        for i, nom in enumerate(noms_medocs):
                            if nom and nom.strip():
                                poso = posologies[i] if i < len(posologies) else ""
                                dur = durees[i] if i < len(durees) else ""

                                print("Création ligne:", nom, poso, dur)
                                LigneMedicament.objects.create(
                                    ordonnance=ordonnance,
                                    nom_medicament=nom,
                                    posologie=poso,
                                    duree=dur,
                                    statut='EN_COURS',
                                    hopital=hopital_user
                                )

                        print("=== FIN BLOC MEDICAMENTS ===")
                    else:
                        print("AUCUN MÉDICAMENT → on ne crée pas d'ordonnance")

                    triage.est_consulte = True
                    triage.save()

                messages.success(
                    request,
                    f"Consultation de {triage.patient.noms} enregistrée et clôturée avec succès !"
                )
                return redirect('liste_consultation_medecin')

            except Exception as e:
                print("=== EXCEPTION ===")
                print(e)
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
        'fonctionKey': fonctionKey,
        # pas de mode → le template affiche "Nouvelle consultation"
    })

# 30
# ==================================================================================================
# MEDECIN  LISTE DES EXAMENS CONSULTER
# ==================================================================================================
@login_required
def liste_consultations_terminees(request):
    # Rôle / hôpital
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    consultations = Consultation.objects.none()

    if hopital_user:
        consultations = (
            Consultation.objects.select_related(
                'triage__patient',
                'medecin'
            )
            .prefetch_related('examens__prestation')
            .filter(triage__patient__hopital=hopital_user)
        )

        # Filtre de recherche
        q = request.GET.get('q', '').strip()
        if q:
            consultations = consultations.filter(
                Q(triage__patient__noms__icontains=q) |
                Q(triage__patient__code_patient__icontains=q) |
                Q(medecin__username__icontains=q) |
                Q(medecin__first_name__icontains=q) |
                Q(medecin__last_name__icontains=q)
            )

        # Tri : ID le plus élevé en premier (décroissant)
        consultations = consultations.order_by('-id')  # <-- LE '-' EST IMPORTANT

    context = {
        'consultations': consultations,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
    }
    return render(request, 'back-end/medecin/liste_consultations.html', context)
#
# ==============================================================================================
# MODIFICATION DE LA CONSULTATION PAR LE MEDECIN 
# ==============================================================================================
@login_required
def modifier_consultation(request, consultation_id):
    # Récupérer la consultation
    consultation = get_object_or_404(
        Consultation.objects.select_related('triage__patient', 'medecin'),
        id=consultation_id
    )

    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('liste_consultations')

    # Sécurité : le patient doit appartenir au même hôpital
    if consultation.triage.patient.hopital != hopital_user:
        messages.error(request, "Ce patient appartient à un autre hôpital.")
        return redirect('liste_consultations')

    triage = consultation.triage

    # EXAMENS EXISTANTS : uniquement ceux de l'hôpital du user
    examens_existant = DemandeExamen.objects.filter(
        consultation=consultation,
        hopital=hopital_user
    ).select_related('prestation').order_by('date_demande')

    # PRESTATIONS DISPONIBLES : uniquement celles de l'hôpital du user
    examens_disponibles = Prestation.objects.filter(
        hopital=hopital_user,
        categorie__in=['LABO', 'RADIO', 'ECHO']
    ).order_by('categorie', 'libelle')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                prestation_ids = request.POST.getlist('examens_ids')

                for prestation_id in prestation_ids:
                    # On vérifie aussi l'hôpital ici
                    prestation = get_object_or_404(
                        Prestation,
                        id=prestation_id,
                        hopital=hopital_user,
                        categorie__in=['LABO', 'RADIO', 'ECHO']
                    )

                    quantite = request.POST.get(f'qty_{prestation_id}', 1)
                    statut = request.POST.get(f'statut_{prestation_id}', 'EN_ATTENTE')
                    indication = request.POST.get(f'indication_{prestation_id}', '')
                    resultat = request.POST.get(f'resultat_{prestation_id}', '')
                    date_realisation = request.POST.get(f'date_realisation_{prestation_id}') or None

                    # Création / mise à jour de l'examen
                    exam, created = DemandeExamen.objects.get_or_create(
                        consultation=consultation,
                        prestation=prestation,
                        hopital=hopital_user,  # <== important
                        defaults={
                            'quantite': quantite,
                            'statut': statut,
                            'indication': indication,
                            'resultat': resultat,
                            'date_realisation': date_realisation,
                        }
                    )

                    if not created:
                        exam.quantite = quantite
                        exam.statut = statut
                        exam.indication = indication
                        exam.resultat = resultat
                        exam.date_realisation = date_realisation
                        exam.save()

            messages.success(request, f"Examens ajoutés pour {triage.patient.noms} avec succès !")
            return redirect('liste_consultations')

        except Exception as e:
            messages.error(request, f"Une erreur technique est survenue : {str(e)}")

    return render(request, 'back-end/medecin/modifier_consultation.html', {
        'triage': triage,
        'consultation': consultation,
        'examens_disponibles': examens_disponibles,
        'examens_existant': examens_existant,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
    })# 31
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

    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role else None

    # Requête de base : toutes les ordonnances d'urgence, triées par date décroissante
    ordonnances_list = (
        Ordonnance.objects
        .filter(type_ordonnance='URGENCE')
        .select_related(
            'consultation__triage__patient',
            'consultation__medecin'
        )
        .prefetch_related('lignes_medicaments')
        .order_by('-date_prescrite')  # les plus récentes en premier
    )

    # Filtre par hôpital sauf pour ADMIN
    if fonctionKey != 'ADMIN':
        if hopital_user:
            ordonnances_list = ordonnances_list.filter(
                consultation__triage__patient__hopital=hopital_user
            )
        else:
            ordonnances_list = ordonnances_list.none()

    # Recherche par patient (nom ou code)
    if query:
        ordonnances_list = ordonnances_list.filter(
            Q(consultation__triage__patient__noms__icontains=query) |
            Q(consultation__triage__patient__code_patient__icontains=query)
        )

    # Pagination
    paginator = Paginator(ordonnances_list, 10)
    page = request.GET.get('page')

    try:
        ordonnances = paginator.page(page)
    except PageNotAnInteger:
        ordonnances = paginator.page(1)
    except EmptyPage:
        ordonnances = paginator.page(paginator.num_pages)

    context = {
        'ordonnances': ordonnances,
        'fonctionKey': fonctionKey,
        'query': query,
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
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    consultation = get_object_or_404(
        Consultation.objects.select_related('triage__patient', 'medecin', 'hopital')
        .prefetch_related('examens__prestation', 'paiements'),
        id=consultation_id,
        triage__patient__hopital=hopital_user
    )

    examens = consultation.examens.all()
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500.00')  # 1 USD = taux CDF

    # ---- Total des examens prescrits (en CDF) ----
    total_prescrit_cdf = examens.aggregate(
        total=Coalesce(
            Sum(F('prestation__prix') * F('quantite')),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=15, decimal_places=2))
        )
    )['total'] or Decimal('0.00')

    # ---- Paiements déjà faits pour les examens (en CDF) ----
    paiements_examens = consultation.paiements.filter(service='EXAMENS')

    total_verse_cdf = Decimal('0.00')
    total_reductions_cdf = Decimal('0.00')

    for p in paiements_examens:
        # montant_verse est dans la devise du paiement
        if p.devise == 'CDF':
            total_verse_cdf += p.montant_verse
        else:  # USD
            total_verse_cdf += p.montant_verse * taux

        # idem pour les réductions (si stockées en USD ou CDF selon ta logique)
        if p.devise == 'CDF':
            total_reductions_cdf += p.montant_reduction
        else:
            total_reductions_cdf += p.montant_reduction * taux

    # Reste à payer en CDF
    reste_a_payer_cdf = total_prescrit_cdf - (total_verse_cdf + total_reductions_cdf)
    if reste_a_payer_cdf < 0:
        reste_a_payer_cdf = Decimal('0.00')

    # Conversion en USD (pour affichage)
    reste_a_payer_usd = reste_a_payer_cdf / taux if taux else Decimal('0')

    # ---- Traitement du formulaire de paiement ----
    if request.method == 'POST':
        try:
            devise = request.POST.get('devise', 'CDF')  # par défaut CDF
            montant_recu = Decimal(request.POST.get('montant_verse', '0') or '0')
            reduction = Decimal(request.POST.get('montant_reduction', '0') or '0')

            if montant_recu < 0 or reduction < 0:
                messages.error(request, "Les montants ne peuvent pas être négatifs.")
                return redirect('encaisser_examens_prescrits', consultation_id=consultation.id)

            # Conversion du montant et de la réduction en CDF
            if devise == 'CDF':
                montant_verse_cdf = montant_recu
                reduction_cdf = reduction
            else:  # USD
                montant_verse_cdf = montant_recu * taux
                reduction_cdf = reduction * taux

            total_encaisse_cdf = montant_verse_cdf + reduction_cdf

            # Vérifier si on ne dépasse pas le reste à payer (en CDF)
            tolerance_cdf = Decimal('1')  # 1 CDF de tolérance
            if total_encaisse_cdf > (reste_a_payer_cdf + tolerance_cdf):
                messages.error(
                    request,
                    f"Erreur : le montant total ({total_encaisse_cdf:.0f} CDF / "
                    f"{total_encaisse_cdf / taux:.2f} USD) dépasse le reste à payer "
                    f"({reste_a_payer_cdf:.0f} CDF / {reste_a_payer_usd:.2f} USD)."
                )
                return redirect('encaisser_examens_prescrits', consultation_id=consultation.id)

            # Nouveau reste en CDF
            nouveau_reste_cdf = reste_a_payer_cdf - total_encaisse_cdf
            if nouveau_reste_cdf < 0:
                nouveau_reste_cdf = Decimal('0')

            # Création du paiement
            # Ici, on stocke montant_verse et montant_reduction dans la devise choisie
            paiement = Paiement.objects.create(
                patient=consultation.triage.patient,
                consultation=consultation,
                service='EXAMENS',
                montant_verse=montant_recu,          # dans la devise choisie
                montant_reduction=reduction,         # dans la devise choisie
                reste_a_payer=nouveau_reste_cdf,     # on garde le reste en CDF en base (ou adapte selon ton modèle)
                devise=devise,
                caissier=request.user,
                date_paiement=timezone.now(),
                hopital=hopital_user
            )

            if nouveau_reste_cdf <= Decimal('1'):  # 1 CDF de tolérance
                consultation.consultation_payee = True
                consultation.save(update_fields=['consultation_payee'])

            messages.success(request, "Paiement enregistré avec succès.")
            return redirect('historique_paiements', patient_id=consultation.triage.patient.id)

        except Exception as e:
            messages.error(request, f"Une erreur technique est survenue : {str(e)}")
            return redirect('encaisser_examens_prescrits', consultation_id=consultation.id)

    context = {
        'consultation': consultation,
        'examens': examens,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'total_prescrit_cdf': total_prescrit_cdf,
        'total_prescrit_usd': total_prescrit_cdf / taux if taux else Decimal('0'),
        'total_verse_cdf': total_verse_cdf,
        'total_reductions_cdf': total_reductions_cdf,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
    }
    return render(request, 'back-end/caisse/encaisser_examens.html', context)# 35
# ==================================================================================================
# RECEPTIONNISTE PAIEMENT DES EXAM
# ==================================================================================================
@login_required
def liste_attente_caisse(request):
    taux = ConfigurationHopital.get_taux()  # 1 USD = taux CDF

    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    # Requête de base : consultations qui ont au moins un examen, pour l'hôpital de l'utilisateur
    # On exclut les patients CONVENTIONNE et FIDELE
    consultations_qs = (
        Consultation.objects
        .filter(
            examens__isnull=False,
            triage__patient__hopital=hopital_user,
        )
        .exclude(
            triage__patient__type_patient__in=['CONVENTIONNE', 'FIDELE']
        )
        .select_related('triage__patient', 'medecin')
        .prefetch_related('examens__prestation', 'paiements')
        .distinct()  # important pour éviter les doublons
        .order_by('-id')
    )

    # Filtre recherche
    query = request.GET.get('q', '').strip()
    if query:
        consultations_qs = consultations_qs.filter(
            Q(triage__patient__noms__icontains=query) |
            Q(triage__patient__code_patient__icontains=query)
        )

    consultations = []
    for c in consultations_qs:
        # ---- Total des examens en CDF ----
        total_a_payer_cdf = c.examens.aggregate(
            total=Coalesce(
                Sum(F('prestation__prix') * F('quantite')),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=15, decimal_places=2))
            )
        )['total'] or Decimal('0.00')

        # ---- Paiements déjà faits pour les examens (en CDF) ----
        paiements_examens = c.paiements.filter(service='EXAMENS')

        total_deja_paye_cdf = Decimal('0.00')
        for p in paiements_examens:
            if p.devise == 'CDF':
                total_deja_paye_cdf += p.montant_verse
            else:  # USD
                total_deja_paye_cdf += p.montant_verse * taux

        # ---- Reste à payer ----
        reste_a_payer_cdf = total_a_payer_cdf - total_deja_paye_cdf
        if reste_a_payer_cdf <= 0:
            continue  # déjà payée, on ne l'affiche pas

        # Conversion en USD pour affichage
        total_a_payer_usd = total_a_payer_cdf / taux if taux else Decimal('0')
        total_deja_paye_usd = total_deja_paye_cdf / taux if taux else Decimal('0')
        reste_a_payer_usd = reste_a_payer_cdf / taux if taux else Decimal('0')

        # On attache les infos à la consultation
        c.total_a_payer_cdf = total_a_payer_cdf
        c.total_deja_paye_cdf = total_deja_paye_cdf
        c.reste_a_payer_cdf = reste_a_payer_cdf

        c.total_a_payer_usd = total_a_payer_usd
        c.total_deja_paye_usd = total_deja_paye_usd
        c.reste_a_payer_usd = reste_a_payer_usd

        consultations.append(c)

    # Tri explicite décroissant par id (déjà fait en DB, mais on garde pour sécurité)
    consultations.sort(key=lambda x: x.id, reverse=True)

    return render(request, 'back-end/caisse/liste_attente.html', {
        'consultations': consultations,
        'fonctionKey': role.fonctionKey.roleName if (role and role.fonctionKey) else None,
        'query': query,
        'taux': taux,
    })

    
# 36
# ==================================================================================================
# LISTE DES EXAMENS A FAIRE 
# ==================================================================================================
@login_required
def liste_examens_techniques(request):
    role_user = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    
    # Vérification de base
    if not role_user or not role_user.fonctionKey or not role_user.hopital:
        return redirect('dashboard')

    hopital_user = role_user.hopital
    nom_role = (role_user.fonctionKey.roleName or "").lower()
    fonctionKey = role_user.fonctionKey.roleName

    # Récupérer le taux
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500.00')

    # Filtrer les consultations par hôpital du user connecté
    # Le gestionnaire et le technicien voient les mêmes consultations de leur hôpital
    consultations = (
        Consultation.objects.select_related('triage__patient', 'medecin')
        .prefetch_related('examens__prestation', 'paiements')
        .filter(
            hopital=hopital_user,  # Filtrer directement par hopital de la consultation
            examens__isnull=False
        )
        .distinct()
        .order_by('-date_creation')
    )

    historique_technique = []

    for cons in consultations:
        patient = cons.triage.patient
        examens_filtres = []

        # ---- Calcul financier pour cette consultation ----
        # Total des examens prescrits (en CDF) - filtrés par hôpital
        total_prescrit_cdf = cons.examens.filter(
            hopital=hopital_user
        ).aggregate(
            total=Coalesce(
                Sum(F('prestation__prix') * F('quantite')),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=15, decimal_places=2))
            )
        )['total'] or Decimal('0.00')

        # Paiements déjà faits pour les examens
        paiements_examens = cons.paiements.filter(
            patient=patient,
            consultation=cons,
            service__in=['LABO', 'ECHO', 'RADIO', 'EXAMENS']
        )

        total_verse_cdf = Decimal('0.00')
        total_reduction_cdf = Decimal('0.00')

        for p in paiements_examens:
            if p.devise == 'CDF':
                total_verse_cdf += p.montant_verse or Decimal('0')
                total_reduction_cdf += p.montant_reduction or Decimal('0')
            else:  # USD
                total_verse_cdf += (p.montant_verse or Decimal('0')) * taux
                total_reduction_cdf += (p.montant_reduction or Decimal('0')) * taux

        reste_a_payer_cdf = total_prescrit_cdf - (total_verse_cdf + total_reduction_cdf)
        if reste_a_payer_cdf < 0:
            reste_a_payer_cdf = Decimal('0.00')

        reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_prescrit_usd = (total_prescrit_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # --------------------------------------------------

        for exam in cons.examens.filter(hopital=hopital_user).all():
            # Vérification supplémentaire de l'hôpital
            if exam.hopital_id and exam.hopital_id != hopital_user.id:
                continue

            if exam.prestation and exam.prestation.hopital_id and exam.prestation.hopital_id != hopital_user.id:
                continue

            cat = str(exam.prestation.categorie).upper() if exam.prestation else ""

            # Filtrer par type de patient (pour les patients SIMPLE uniquement)
            if patient.type_patient == 'SIMPLE':
                paiement_examen = Paiement.objects.filter(
                    patient=patient,
                    consultation=cons,
                    service__in=['LABO', 'ECHO', 'RADIO', 'EXAMENS'],
                    montant_verse__gt=0
                ).exists()
                if not paiement_examen:
                    continue

            # Filtrer par rôle du technicien OU gestionnaire (admin)
            # Le gestionnaire (admin) voit tout, le technicien voit selon sa spécialité
            est_gestionnaire = 'gestionnaire' in nom_role or 'admin' in nom_role
            
            if est_gestionnaire or \
               ('labo' in nom_role and cat == 'LABO') or \
               (('echo' in nom_role or 'echographiste' in nom_role) and cat == 'ECHO') or \
               (('radio' in nom_role or 'radiologue' in nom_role) and cat == 'RADIO') or \
               ('technicien' in nom_role):

                examens_filtres.append({
                    'id_examen': exam.id,
                    'libelle': exam.prestation.libelle if exam.prestation else 'Examen',
                    'est_deja_fait': exam.statut == 'TERMINE'
                })

        if examens_filtres:
            examens_filtres.sort(key=lambda x: x['est_deja_fait'])

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
                'examens': examens_filtres,
                'medecin': cons.medecin.username if cons.medecin else "Généraliste",
                'tout_traite': not any(not ex['est_deja_fait'] for ex in examens_filtres),

                # Infos financières pour le technicien/gestionnaire
                'total_prescrit_cdf': total_prescrit_cdf,
                'total_prescrit_usd': total_prescrit_usd,
                'total_paye_cdf': total_verse_cdf + total_reduction_cdf,
                'reste_a_payer_cdf': reste_a_payer_cdf,
                'reste_a_payer_usd': reste_a_payer_usd,
            })

    # Trier pour afficher d'abord les patients avec examens non traités
    historique_technique.sort(key=lambda x: (x['tout_traite'], -x['consultation_id']))

    return render(request, 'back-end/technique/liste_examens_payes.html', {
        'historique_technique': historique_technique,
        'examens_presents': len(historique_technique) > 0,
        'titre_page': "Examens à réaliser",
        'fonctionKey': fonctionKey,
        'taux': taux,
        'hopital_user': hopital_user,
    })


# 37
# ==================================================================================================
# 
# ==================================================================================================
@login_required
def saisir_resultats_examens(request, consultation_id):
    # 1. Vérification du rôle du technicien/gestionnaire
    role_user = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    if not role_user or not role_user.fonctionKey or not role_user.hopital:
        messages.error(request, "Accès refusé.")
        return redirect('dashboard')

    hopital_user = role_user.hopital
    nom_role = role_user.fonctionKey.roleName.lower()
    fonctionKey = role_user.fonctionKey.roleName

    # 2. Récupération de la consultation avec vérification de l'hôpital
    consultation = get_object_or_404(
        Consultation.objects.filter(hopital=hopital_user),  # Filtrer par hôpital
        id=consultation_id
    )
    
    # 3. Extraction et filtrage des examens 'EN_ATTENTE' pour ce rôle précis
    examens_en_attente = consultation.examens.filter(
        statut='EN_ATTENTE',
        hopital=hopital_user  # Filtrer par hôpital
    ).select_related('prestation')
    
    examens_a_saisir = []
    
    # Vérifier si c'est un gestionnaire ou admin (peut tout voir)
    est_gestionnaire = 'gestionnaire' in nom_role or 'admin' in nom_role
    
    for exam in examens_en_attente:
        cat = exam.prestation.categorie if exam.prestation else ""
        
        # Le gestionnaire/admin voit TOUS les examens
        if est_gestionnaire:
            examens_a_saisir.append(exam)
        # Le technicien voit selon sa spécialité
        elif ('labo' in nom_role or 'laborantin' in nom_role) and cat == 'LABO':
            examens_a_saisir.append(exam)
        elif ('echo' in nom_role or 'echographiste' in nom_role) and cat == 'ECHO':
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
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,  # Ajout pour le template
    }
    return render(request, 'back-end/technique/saisir_resultats.html', context)

#
# ==================================================================================================
# MODIFICATION D'EXAMENT PAR LES TECHNICIENS
# ==================================================================================================
@login_required
def modifier_resultats_examens(request, consultation_id):
    role_user = Fonction.objects.filter(userKey=request.user).first()
    if not role_user or not role_user.fonctionKey:
        messages.error(request, "Accès refusé.")
        return redirect('dashboard')

    nom_role = role_user.fonctionKey.roleName.lower()
    fonctionKey = role_user.fonctionKey.roleName

    consultation = get_object_or_404(Consultation.objects.select_related('triage__patient'), id=consultation_id)

    examens_termines = consultation.examens.filter(statut='TERMINE').select_related('prestation')

    examens_a_modifier = []
    for exam in examens_termines:
        cat = exam.prestation.categorie if exam.prestation else ''
        if ('labo' in nom_role or 'laborantin' in nom_role) and cat == 'LABO':
            examens_a_modifier.append(exam)
        elif ('echo' in nom_role or 'echographiste' in nom_role) and cat == 'ECHO':
            examens_a_modifier.append(exam)
        elif ('radio' in nom_role or 'radiologue' in nom_role) and cat == 'RADIO':
            examens_a_modifier.append(exam)

    if not examens_a_modifier:
        messages.error(request, "Aucun examen terminé à modifier pour votre spécialité.")
        return redirect('liste_examens_techniques')

    if request.method == 'POST':
        examens_modifies = 0
        for exam in examens_a_modifier:
            cle_resultat = f"resultat_{exam.id}"
            texte_resultat = request.POST.get(cle_resultat, "").strip()
            if texte_resultat:
                exam.resultat = texte_resultat
                exam.technicien = request.user
                exam.date_realisation = timezone.now()
                exam.save(update_fields=['resultat', 'technicien', 'date_realisation'])
                examens_modifies += 1

        if examens_modifies > 0:
            messages.success(request, f"Les résultats de ({examens_modifies}) examen(s) pour {consultation.triage.patient.noms} ont été modifiés.")
        else:
            messages.warning(request, "Aucune modification n'a été enregistrée.")

        return redirect('liste_examens_techniques')

    context = {
        'consultation': consultation,
        'patient': consultation.triage.patient,
        'examens_a_modifier': examens_a_modifier,
        'fonctionKey': fonctionKey,
    }
    return render(request, 'back-end/technique/modifier_resultats.html', context)

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
    debut_mois = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    debut_annee = maintenant.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)  # NOUVEAU


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


    total_usd = paiements_qs.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_cdf = paiements_qs.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')


    depense_totale_usd = depenses_qs.filter(devise='USD').aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
    depense_totale_cdf = depenses_qs.filter(devise='CDF').aggregate(total=Sum('montant'))['total'] or Decimal('0.00')


    restant_usd = total_usd - depense_totale_usd
    restant_cdf = total_cdf - depense_totale_cdf


    aujourdhui_usd = paiements_qs.filter(date_paiement__gte=debut_aujourdhui, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    aujourdhui_cdf = paiements_qs.filter(date_paiement__gte=debut_aujourdhui, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')


    semaine_usd = paiements_qs.filter(date_paiement__gte=debut_semaine, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    semaine_cdf = paiements_qs.filter(date_paiement__gte=debut_semaine, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')


    mois_usd = paiements_qs.filter(date_paiement__gte=debut_mois, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    mois_cdf = paiements_qs.filter(date_paiement__gte=debut_mois, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    
    
    # NOUVEAU : Stats par année
    annee_usd = paiements_qs.filter(date_paiement__gte=debut_annee, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    annee_cdf = paiements_qs.filter(date_paiement__gte=debut_annee, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')


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
        usd_service = paiements_qs.filter(service=code, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
        cdf_service = paiements_qs.filter(service=code, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
        services_stats.append({
            'code': code,
            'nom': nom_service,
            'usd': usd_service,
            'cdf': cdf_service,
        })


    # NOUVEAU : Stats par mois (année en cours)
    paiements_annee = paiements_qs.filter(date_paiement__gte=debut_annee)
    
    mois_stats = []
    for m in range(1, 13):
        debut_mois_courant = maintenant.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        if m == 12:
            fin_mois_courant = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            fin_mois_courant = maintenant.replace(month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

        m_usd = paiements_annee.filter(
            date_paiement__range=(debut_mois_courant, fin_mois_courant),
            devise='USD'
        ).aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')

        m_cdf = paiements_annee.filter(
            date_paiement__range=(debut_mois_courant, fin_mois_courant),
            devise='CDF'
        ).aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')

        nom_mois = debut_mois_courant.strftime('%B').capitalize()

        mois_stats.append({
            'nom': nom_mois,
            'mois_num': m,
            'usd': m_usd,
            'cdf': m_cdf,
        })
    
    
    # NOUVEAU : Dépenses par mois
    depenses_annee = depenses_qs.filter(date_depense__gte=debut_annee)
    
    depenses_mois_stats = []
    for m in range(1, 13):
        debut_mois_courant = maintenant.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        if m == 12:
            fin_mois_courant = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            fin_mois_courant = maintenant.replace(month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

        d_usd = depenses_annee.filter(
            date_depense__range=(debut_mois_courant, fin_mois_courant),
            devise='USD'
        ).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

        d_cdf = depenses_annee.filter(
            date_depense__range=(debut_mois_courant, fin_mois_courant),
            devise='CDF'
        ).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')

        nom_mois = debut_mois_courant.strftime('%B').capitalize()

        depenses_mois_stats.append({
            'nom': nom_mois,
            'mois_num': m,
            'usd': d_usd,
            'cdf': d_cdf,
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
        'annee_usd': annee_usd,  # NOUVEAU
        'annee_cdf': annee_cdf,  # NOUVEAU
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
        'mois_stats': mois_stats,  # NOUVEAU
        'depenses_mois_stats': depenses_mois_stats,  # NOUVEAU
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
                return redirect('historique_depenses')

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
# HISTORIQUE DES DEPENSES
# ==================================================================================================
@login_required
def historique_depenses(request):
    # Rôle / hôpital de l'utilisateur
    role = Fonction.objects.select_related('fonctionKey', 'hopital').filter(userKey=request.user).first()
    
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    hopital_user = role.hopital if role and role.hopital else None
    hopital_user_id = role.hopital_id if role and role.hopital_id else None
    
    # Vérifier si admin
    is_admin = fonctionKey and fonctionKey.lower() in ['admin', 'administrateur', 'superadmin']
    
    # Filtrer les dépenses selon le rôle
    if is_admin:
        # Admin voit toutes les dépenses de tous les hôpitaux
        depenses = Depense.objects.select_related('hopital', 'auteur').all()
    else:
        # Les autres ne voient que les dépenses de leur hôpital
        if hopital_user_id:
            depenses = Depense.objects.select_related('hopital', 'auteur').filter(
                hopital_id=hopital_user_id
            )
        else:
            depenses = Depense.objects.none()
    
    # Filtres de recherche
    q = request.GET.get('q', '').strip()
    if q:
        depenses = depenses.filter(
            Q(description__icontains=q) |
            Q(auteur__username__icontains=q) |
            Q(auteur__first_name__icontains=q) |
            Q(auteur__last_name__icontains=q) |
            Q(motif__icontains=q) |
            Q(beneficiaire__icontains=q)
        )
    
    # Filtre par devise
    devise_filter = request.GET.get('devise', '').strip()
    if devise_filter:
        depenses = depenses.filter(devise=devise_filter)
    
    # Filtre par hôpital (seulement pour admin)
    hopital_filter = request.GET.get('hopital_id', '').strip()
    if is_admin and hopital_filter:
        depenses = depenses.filter(hopital_id=hopital_filter)
    
    # Filtre par date_depense
    date_debut = request.GET.get('date_debut', '').strip()
    date_fin = request.GET.get('date_fin', '').strip()
    
    if date_debut:
        depenses = depenses.filter(date_depense__gte=date_debut)
    if date_fin:
        depenses = depenses.filter(date_depense__lte=date_fin)
    
    # Tri : plus récent en premier
    depenses = depenses.order_by('-date_depense', '-id')
    
    # Pagination
    paginator = Paginator(depenses, 25)
    page_number = request.GET.get('page', 1)
    depenses_page = paginator.get_page(page_number)
    
    # Calcul des totaux par devise
    def total_par_devise(devise):
        qs = depenses.filter(devise=devise)
        total = qs.aggregate(
            total=Coalesce(Sum('montant'), Decimal('0.00'), output_field=DecimalField())
        )['total']
        return total or Decimal('0.00')
    
    total_usd = total_par_devise('USD')
    total_cdf = total_par_devise('CDF')
    
    # Liste des hôpitaux (pour le filtre admin)
    hopitaux = None
    if is_admin:
        hopitaux = Hopital.objects.all()
    
    context = {
        'depenses': depenses_page,
        'titre_page': "Historique des Dépenses",
        'fonctionKey': fonctionKey,
        'is_admin': is_admin,
        'hopital_user': hopital_user,
        'hopitaux': hopitaux,
        'total_usd': total_usd,
        'total_cdf': total_cdf,
        'q': q,
        'devise_filter': devise_filter,
        'hopital_filter': hopital_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }
    
    return render(request, 'back-end/finance/historique_depenses.html', context)

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

    # Périodes de temps
    debut_aujourdhui = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    debut_semaine = debut_aujourdhui - timedelta(days=maintenant.weekday())
    debut_mois = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    debut_annee = maintenant.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    zero_decimal = Decimal('0.00')

    # QuerySets de base (NON filtrés pour les stats)
    paiements_tous = Paiement.objects.all().order_by('-date_paiement')
    depenses_toutes = Depense.objects.all().order_by('-date_depense')

    # QuerySets pour stats (avant filtrage)
    paiements_stats = paiements_tous
    depenses_stats = depenses_toutes

    # Application du filtre par hôpital
    if fonctionKey != 'admin':
        if hopital_user:
            paiements_tous = paiements_tous.filter(hopital=hopital_user)
            depenses_toutes = depenses_toutes.filter(hopital=hopital_user)
            paiements_stats = paiements_stats.filter(hopital=hopital_user)
            depenses_stats = depenses_stats.filter(hopital=hopital_user)
        else:
            paiements_tous = paiements_tous.none()
            depenses_toutes = depenses_toutes.none()
            paiements_stats = paiements_stats.none()
            depenses_stats = depenses_stats.none()

    # --- Statistiques temporelles (recettes) ---
    recettes_stats = paiements_stats.aggregate(
        auj_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='USD')), zero_decimal, output_field=DecimalField()),
        auj_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_aujourdhui, devise='CDF')), zero_decimal, output_field=DecimalField()),
        sem_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='USD')), zero_decimal, output_field=DecimalField()),
        sem_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_semaine, devise='CDF')), zero_decimal, output_field=DecimalField()),
        mois_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='USD')), zero_decimal, output_field=DecimalField()),
        mois_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_mois, devise='CDF')), zero_decimal, output_field=DecimalField()),
        annee_usd=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_annee, devise='USD')), zero_decimal, output_field=DecimalField()),
        annee_cdf=Coalesce(Sum('montant_verse', filter=Q(date_paiement__gte=debut_annee, devise='CDF')), zero_decimal, output_field=DecimalField()),
    )

    # --- Totaux globaux ---
    total_entrees = paiements_stats.aggregate(
        usd=Coalesce(Sum('montant_verse', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant_verse', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    total_depenses = depenses_stats.aggregate(
        usd=Coalesce(Sum('montant', filter=Q(devise='USD')), zero_decimal, output_field=DecimalField()),
        cdf=Coalesce(Sum('montant', filter=Q(devise='CDF')), zero_decimal, output_field=DecimalField())
    )

    restant_usd = total_entrees['usd'] - total_depenses['usd']
    restant_cdf = total_entrees['cdf'] - total_depenses['cdf']

    # --- Stats par service (TOP 5) ---
    services_liste = ['FICHE', 'LABO', 'ECHOGRAPHIE', 'RADIO']
    services_stats = []
    for s in services_liste:
        s_usd = paiements_stats.filter(service=s, devise='USD').aggregate(
            t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField())
        )['t']
        s_cdf = paiements_stats.filter(service=s, devise='CDF').aggregate(
            t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField())
        )['t']
        services_stats.append({'nom': s, 'usd': s_usd, 'cdf': s_cdf})
    
    services_stats = services_stats[:5]

    # --- Stats par mois (recettes) ---
    paiements_annee = paiements_stats.filter(date_paiement__gte=debut_annee)

    mois_stats = []
    for m in range(1, 13):
        debut_mois_courant = maintenant.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        if m == 12:
            fin_mois_courant = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            fin_mois_courant = maintenant.replace(month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

        m_usd = paiements_annee.filter(
            date_paiement__range=(debut_mois_courant, fin_mois_courant),
            devise='USD'
        ).aggregate(t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField()))['t']

        m_cdf = paiements_annee.filter(
            date_paiement__range=(debut_mois_courant, fin_mois_courant),
            devise='CDF'
        ).aggregate(t=Coalesce(Sum('montant_verse'), zero_decimal, output_field=DecimalField()))['t']

        nom_mois = debut_mois_courant.strftime('%B').capitalize()

        mois_stats.append({
            'nom': nom_mois,
            'mois_num': m,
            'usd': m_usd,
            'cdf': m_cdf,
        })

    # --- Dépenses par mois ---
    depenses_annee = depenses_stats.filter(date_depense__gte=debut_annee)

    depenses_mois_stats = []
    for m in range(1, 13):
        debut_mois_courant = maintenant.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
        if m == 12:
            fin_mois_courant = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            fin_mois_courant = maintenant.replace(month=m + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)

        d_usd = depenses_annee.filter(
            date_depense__range=(debut_mois_courant, fin_mois_courant),
            devise='USD'
        ).aggregate(t=Coalesce(Sum('montant'), zero_decimal, output_field=DecimalField()))['t']

        d_cdf = depenses_annee.filter(
            date_depense__range=(debut_mois_courant, fin_mois_courant),
            devise='CDF'
        ).aggregate(t=Coalesce(Sum('montant'), zero_decimal, output_field=DecimalField()))['t']

        nom_mois = debut_mois_courant.strftime('%B').capitalize()

        depenses_mois_stats.append({
            'nom': nom_mois,
            'mois_num': m,
            'usd': d_usd,
            'cdf': d_cdf,
        })

    # --- PAGINATION des paiements (10 par page) ---
    paginator = Paginator(paiements_tous, 10)  # 10 paiements par page
    page_number = request.GET.get('page')
    paiements_page = paginator.get_page(page_number)

    context = {
        'titre_page': "Journal Général de Caisse",
        'fonctionKey': fonctionKey,

        # Paiements PAGINÉS
        'paiements': paiements_page,

        'depenses': depenses_toutes,

        # Stats temporelles
        'aujourdhui_usd': recettes_stats['auj_usd'],
        'aujourdhui_cdf': recettes_stats['auj_cdf'],
        'semaine_usd': recettes_stats['sem_usd'],
        'semaine_cdf': recettes_stats['sem_cdf'],
        'mois_usd': recettes_stats['mois_usd'],
        'mois_cdf': recettes_stats['mois_cdf'],
        'annee_usd': recettes_stats['annee_usd'],
        'annee_cdf': recettes_stats['annee_cdf'],

        # Totaux
        'total_usd': total_entrees['usd'],
        'total_cdf': total_entrees['cdf'],
        'depense_totale_usd': total_depenses['usd'],
        'depense_totale_cdf': total_depenses['cdf'],
        'restant_usd': restant_usd,
        'restant_cdf': restant_cdf,

        # Stats par service (limité à 5)
        'services_stats': services_stats,

        # Stats par mois
        'mois_stats': mois_stats,
        'depenses_mois_stats': depenses_mois_stats,
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

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if request.method == 'POST' and request.POST.get('action') == 'enregistrer_ordonnance':
        consultation_id = request.POST.get('consultation_id')
        diagnostic = request.POST.get('diagnostic_final')
        type_ord = request.POST.get('type_ordonnance')
        destination = request.POST.get('destination', '').upper()
        observation_orient = request.POST.get('observation_orientation')

        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')
        quantites = request.POST.getlist('quantite[]')

        consultation = Consultation.objects.filter(
            id=consultation_id,
            triage__patient__hopital=hopital_user
        ).first()

        if not consultation:
            messages.error(request, "Consultation introuvable.")
            return redirect('liste_attente_medecin')

        try:
            with transaction.atomic():
                if hasattr(consultation, 'diagnostic_final'):
                    consultation.diagnostic_final = diagnostic
                    consultation.save(update_fields=['diagnostic_final'])

                # Au lieu de verrouiller, on peut soit créer une nouvelle ordonnance,
                # soit récupérer et modifier l'existante. Ici, on récupère la dernière :
                ordonnance = consultation.ordonnance_set.order_by('-id').first()
                if ordonnance is None:
                    ordonnance = Ordonnance.objects.create(
                        consultation=consultation,
                        type_ordonnance=type_ord,
                        diagnostic=diagnostic,
                        hopital=hopital_user
                    )
                else:
                    ordonnance.type_ordonnance = type_ord
                    ordonnance.diagnostic = diagnostic
                    ordonnance.hopital = hopital_user
                    ordonnance.save()

                    # On efface l’ancien traitement pour le remplacer
                    ordonnance.medicaments.all().delete()

                for nom, pos, dur, qty in zip(noms, posologies, durees, quantites):
                    if nom and nom.strip():
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom.strip(),
                            posologie=pos.strip() if pos else '',
                            duree=dur.strip() if dur else '',
                            quantite=int(qty) if qty and qty.isdigit() else 1,
                            hopital=hopital_user
                        )

                if destination:
                    orientation = Orientation.objects.create(
                        consultation=consultation,
                        medecin_orientateur=request.user,
                        destination=destination,
                        observation=observation_orient,
                        est_admis=False,
                        hopital=hopital_user
                    )

                    if destination == 'HOSPITALISATION':
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

                            lit = Lit.objects.filter(id=lit_id, hopital=hopital_user).first()
                            if lit:
                                lit.est_occupe = True
                                lit.save(update_fields=['est_occupe'])

            messages.success(request, "Traitement (ordonnance) enregistré / mis à jour avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur critique : {str(e)}")

        return redirect('liste_attente_medecin')

    consultations_en_attente = Consultation.objects.filter(
        examens__statut='TERMINE',
        triage__patient__hopital=hopital_user
    ).prefetch_related(
        'examens__prestation',
        'ordonnance_set'
    ).distinct().order_by('-date_creation')

    for c in consultations_en_attente:
        c.ordonnance_existante = c.ordonnance_set.exists()
        c.examens_termines = c.examens.filter(statut='TERMINE')

    lits_disponibles = Lit.objects.filter(
        est_occupe=False,
        hopital=hopital_user
    ).select_related('chambre').order_by('nom_lit')

    return render(request, 'back-end/medecin/liste_attente.html', {
        'consultations_en_attente': consultations_en_attente,
        'lits_disponibles': lits_disponibles,
        'fonctionKey': fonctionKey,
        'now': timezone.now(),
    })

# ==================================================================================================
# MODIFICATION EXAMEN PRESCRITE 
# =================================================================================================
@login_required
def modifier_ordonnance_view_med(request, consultation_id):
    # 1. Rôle et hôpital
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    # 2. Consultation + ordonnance existante
    consultation = get_object_or_404(
        Consultation.objects.select_related('triage__patient').prefetch_related('examens__prestation'),
        id=consultation_id,
        triage__patient__hopital=hopital_user
    )

    ordonnance = consultation.ordonnance_set.order_by('-id').first()

    if ordonnance is None:
        messages.error(request, "Aucune ordonnance existante pour cette consultation.")
        return redirect('liste_attente_medecin')

    medicaments = ordonnance.medicaments.all().order_by('id')
    examens_termines = consultation.examens.filter(statut='TERMINE').select_related('prestation')

    # Lits disponibles pour cet hôpital
    lits_disponibles = Lit.objects.filter(
        est_occupe=False,
        hopital=hopital_user
    ).select_related('chambre').order_by('nom_lit')

    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic_final') or ordonnance.diagnostic
        type_ord = request.POST.get('type_ordonnance') or ordonnance.type_ordonnance

        destination = request.POST.get('destination', '').upper()
        observation_orient = request.POST.get('observation_orientation')

        noms = request.POST.getlist('nom_medicament[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')
        quantites = request.POST.getlist('quantite[]')

        try:
            with transaction.atomic():
                # Mise à jour diagnostic consultation si champ présent
                if hasattr(consultation, 'diagnostic_final'):
                    consultation.diagnostic_final = diagnostic
                    consultation.save(update_fields=['diagnostic_final'])

                # 3. Mise à jour ordonnance
                ordonnance.type_ordonnance = type_ord
                ordonnance.diagnostic = diagnostic
                ordonnance.hopital = hopital_user
                ordonnance.save()

                # 4. Remplacer les médicaments
                ordonnance.medicaments.all().delete()

                for nom, pos, dur, qty in zip(noms, posologies, durees, quantites):
                    if nom and nom.strip():
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom.strip(),
                            posologie=pos.strip() if pos else '',
                            duree=dur.strip() if dur else '',
                            quantite=int(qty) if qty and qty.isdigit() else 1,
                            hopital=hopital_user
                        )

                # 5. Orientation (optionnelle)
                if destination:
                    orientation = Orientation.objects.create(
                        consultation=consultation,
                        medecin_orientateur=request.user,
                        destination=destination,
                        observation=observation_orient,
                        est_admis=False,
                        hopital=hopital_user
                    )

                    if destination == 'HOSPITALISATION':
                        lit_id = request.POST.get('lit_id')
                        date_entree = request.POST.get('date_entree')
                        motif_admission = request.POST.get('motif_admission') or diagnostic

                        if lit_id:
                            # Vérifier que le lit appartient bien à l'hôpital et est libre
                            lit = Lit.objects.filter(
                                id=lit_id,
                                hopital=hopital_user,
                                est_occupe=False
                            ).select_related('chambre').first()

                            if not lit:
                                raise ValueError("Le lit sélectionné n'est pas disponible ou n'appartient pas à votre hôpital.")

                            Hospitalisation.objects.create(
                                patient=consultation.triage.patient,
                                lit=lit,  # attention: champ 'lit', pas 'lit_id' si FK
                                hopital=hopital_user,
                                date_entree=date_entree if date_entree else timezone.now(),
                                motif_admission=motif_admission,
                                statut='EN_COURS'
                            )

                            lit.est_occupe = True
                            lit.save(update_fields=['est_occupe'])

            messages.success(request, "Ordonnance modifiée avec succès.")
            return redirect('liste_attente_medecin')

        except Exception as e:
            messages.error(request, f"Erreur lors de la modification : {str(e)}")

    # GET : afficher les infos existantes
    context = {
        'consultation': consultation,
        'ordonnance': ordonnance,
        'medicaments': medicaments,
        'examens_termines': examens_termines,
        'fonctionKey': fonctionKey,
        'lits_disponibles': lits_disponibles,  # <- ajouté
        'now': timezone.now(),
    }
    return render(request, 'back-end/medecin/modifier_ordonnance_med.html', context)

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
    """
    Affichage global de la situation des chambres, prix et lits,
    avec logique multi-hôpitaux similaire à liste_hospitalisations.
    """

    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Peut voir tous les hôpitaux ?
    peut_voir_tous_hopitaux = (
        request.user.is_superuser
        or (role and role.fonctionKey and role.fonctionKey.roleName in ['Admin', 'Directeur'])
    )

    # Paramètre URL : ?tous_hopitaux=1
    afficher_tous = request.GET.get('tous_hopitaux') == '1'

    if not hopital_user and not afficher_tous:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')  # ou autre vue par défaut

    if afficher_tous and not peut_voir_tous_hopitaux:
        afficher_tous = False
        messages.warning(
            request,
            "Vous n'avez pas l'autorisation de voir tous les hôpitaux."
        )

    # 2. Taux de change (par défaut en CDF)
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')
    if not taux or taux == 0:
        taux = Decimal('2500.00')

    # 3. Récupérer les hôpitaux pour le filtre (admin / tous hopitaux)
    hopitaux_qs = Hopital.objects.all().order_by('nomH')

    # 4. Récupération des chambres avec jointures optimisées
    chambres_qs = (
        Chambre.objects
        .select_related('type_chambre', 'hopital')
        .prefetch_related('lits')
        .order_by('nom')  # ou autre champ pertinent
    )

    # Filtre par hôpital "par défaut" si on n'affiche pas tous
    if not afficher_tous:
        chambres_qs = chambres_qs.filter(hopital=hopital_user)

    # Filtre par hôpital via ?hopital=ID (uniquement si l'utilisateur peut voir tous)
    hopital_selectionne_id = request.GET.get('hopital')
    hopital_selectionne = None

    if peut_voir_tous_hopitaux and afficher_tous and hopital_selectionne_id:
        try:
            hopital_selectionne = Hopital.objects.get(pk=hopital_selectionne_id)
            chambres_qs = chambres_qs.filter(hopital=hopital_selectionne)
        except (ValueError, Hopital.DoesNotExist):
            hopital_selectionne = None

    # 5. Statistiques globales (sur le queryset filtré)
    # On se base sur les lits liés aux chambres filtrées
    lits_qs = Lit.objects.filter(
        chambre__in=chambres_qs
    )

    stats = lits_qs.aggregate(
        total_lits=Count('id', filter=Q(est_actif=True)),
        lits_occupes=Count('id', filter=Q(est_occupe=True, est_actif=True)),
        lits_disponibles=Count('id', filter=Q(est_occupe=False, est_actif=True)),
    )

    # Calculs supplémentaires par chambre (prix, occupation, etc.)
    chambres = []
    now = timezone.now()

    for chambre in chambres_qs:
        lits_chambre = chambre.lits.all()
        total_lits_chambre = lits_chambre.filter(est_actif=True).count()
        lits_occupes_chambre = lits_chambre.filter(est_actif=True, est_occupe=True).count()
        lits_dispos_chambre = total_lits_chambre - lits_occupes_chambre

        # Prix par nuit (en CDF)
        prix_lit_cdf = Decimal('0')
        if hasattr(chambre, 'type_chambre') and chambre.type_chambre:
            prix_lit_cdf = chambre.type_chambre.prix_nuitée or Decimal('0')
        if prix_lit_cdf <= 0:
            prix_lit_cdf = Decimal('50000')  # valeur par défaut

        chambres.append({
            'chambre': chambre,
            'total_lits': total_lits_chambre,
            'lits_occupes': lits_occupes_chambre,
            'lits_disponibles': lits_dispos_chambre,
            'prix_lit_cdf': prix_lit_cdf,
        })

    # 6. Construire l'historique des hospitalisations
    hospitalisations_qs = (
        Hospitalisation.objects
        .select_related(
            'patient',
            'lit__chambre',
            'hopital'
        )
        .order_by('-date_entree')
    )

    # Même logique de filtrage que pour les chambres
    if not afficher_tous:
        hospitalisations_qs = hospitalisations_qs.filter(hopital=hopital_user)

    if peut_voir_tous_hopitaux and afficher_tous and hopital_selectionne:
        hospitalisations_qs = hospitalisations_qs.filter(hopital=hopital_selectionne)

    historique = []

    for hosp in hospitalisations_qs:
        date_entree = hosp.date_entree or now

        # Nombre de jours
        if hosp.statut == 'EN_COURS':
            nombre_jours = (now - date_entree).days + 1
            date_sortie = None
        else:
            date_sortie = getattr(hosp, 'date_sortie', None)
            nombre_jours = getattr(hosp, 'nombre_jours', None)

            if nombre_jours is None or nombre_jours <= 0:
                if date_sortie:
                    nombre_jours = (date_sortie - date_entree).days + 1
                else:
                    nombre_jours = (now - date_entree).days + 1

        historique.append({
            'hospitalisation': hosp,
            'nombre_jours': nombre_jours,
            'date_sortie': date_sortie,
        })

    context = {
        'fonctionKey': fonctionKey,
        'taux': taux,
        'afficher_tous': afficher_tous,
        'peut_voir_tous_hopitaux': peut_voir_tous_hopitaux,
        'hopitaux': hopitaux_qs if peut_voir_tous_hopitaux else [],
        'hopital_selectionne': hopital_selectionne,

        'chambres': chambres,
        'total_chambres': len(chambres),
        'total_lits': stats['total_lits'],
        'lits_occupes': stats['lits_occupes'],
        'lits_disponibles': stats['lits_disponibles'],

        'historique': historique,
    }

    return render(
        request,
        'back-end/hospitalisation/dashboard_chambres.html',
        context
    )

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

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('ajouter_type_chambre')  # ou vers un dashboard

    if request.method == 'POST':
        form = TypeChambreForm(request.POST)
        if form.is_valid():
            type_chambre = form.save(commit=False)
            type_chambre.hopital = hopital_user

            # Le prix est saisi en CDF par défaut dans le formulaire
            # Si ton formulaire a un champ 'prix_cdf', tu peux faire :
            # type_chambre.prix = form.cleaned_data['prix_cdf']

            type_chambre.save()

            messages.success(request, f"Le type de chambre '{type_chambre.libelle}' a été enregistré.")
            return redirect('ajouter_chambre')  # ou une autre vue de liste
    else:
        form = TypeChambreForm()

    # Optionnel : récupérer le taux pour affichage (ex. dans le template)
    
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500.00')

    return render(request, 'back-end/hospitalisation/type_chambre_form.html', {
        'form': form,
        'fonctionKey': fonctionKey,
        'taux': taux,
        'hopital_user': hopital_user,
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
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    ordonnances = Ordonnance.objects.none()

    if hopital_user:
        ordonnances = (
            Ordonnance.objects.filter(
                type_ordonnance='DEFINITIVE',
                consultation__triage__patient__hopital=hopital_user
            )
            .select_related(
                'consultation__triage__patient',
                'consultation__medecin'
            )
            .prefetch_related(
                'medicaments',
                'consultation__examens__prestation',
                'consultation__examens__technicien'
            )
            .order_by('-id')
        )

    context = {
        'ordonnances': ordonnances,
        'fonctionKey': fonctionKey,
        'hopital_user': hopital_user,
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
    from decimal import Decimal
    from django.db.models import DecimalField
    from django.db.models.functions import Coalesce
    from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
    from django.utils import timezone
    from decimal import ROUND_HALF_UP

    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Vérifier si l'utilisateur peut voir tous les hôpitaux
    peut_voir_tous_hopitaux = (
        request.user.is_superuser
        or (role and role.fonctionKey and role.fonctionKey.roleName in ['Admin', 'Directeur'])
    )

    # Paramètre URL : ?tous_hopitaux=1
    afficher_tous = request.GET.get('tous_hopitaux') == '1'

    if not hopital_user and not afficher_tous:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    if afficher_tous and not peut_voir_tous_hopitaux:
        afficher_tous = False
        messages.warning(request, "Vous n'avez pas l'autorisation de voir toutes les hospitalisations.")

    # 2. Taux de change
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')
    if not taux or taux == 0:
        taux = Decimal('2500.00')

    # 3. Récupérer les hôpitaux pour le filtre (admin / tous hopitaux)
    hopitaux_qs = Hopital.objects.all().order_by('nomH')

    # 4. Récupérer les hospitalisations
    hospitalisations_qs = Hospitalisation.objects.select_related(
        'patient',
        'lit__chambre__type_chambre',
        'hopital'
    ).prefetch_related(
        'paiements'
    ).order_by('-date_entree')

    # Filtre par hôpital "par défaut" si on n'affiche pas tous
    if not afficher_tous:
        hospitalisations_qs = hospitalisations_qs.filter(hopital=hopital_user)

    # Filtre par hôpital via ?hopital=ID (uniquement si l'utilisateur peut voir tous)
    hopital_selectionne_id = request.GET.get('hopital')
    hopital_selectionne = None

    if peut_voir_tous_hopitaux and afficher_tous and hopital_selectionne_id:
        try:
            hopital_selectionne = Hopital.objects.get(pk=hopital_selectionne_id)
            hospitalisations_qs = hospitalisations_qs.filter(hopital=hopital_selectionne)
        except (ValueError, Hopital.DoesNotExist):
            hopital_selectionne = None

    # 5. Calcul pour chaque hospitalisation
    hospitalisations = []
    now = timezone.now()

    for hosp in hospitalisations_qs:
        date_entree = hosp.date_entree
        if not date_entree:
            # Sécurité : pas de date_entree → on saute ou on met 0 jour
            nombre_jours = 0
            prix_lit_cdf = Decimal('0')
            cout_total_cdf = Decimal('0')
            cout_total_usd = Decimal('0')
            total_deja_paye_cdf = Decimal('0')
            reste_a_payer_cdf = Decimal('0')
            reste_a_payer_usd = Decimal('0')

            hospitalisations.append({
                'hosp': hosp,
                'cout_total_usd': cout_total_usd,
                'cout_total_cdf': cout_total_cdf,
                'reste_a_payer_usd': reste_a_payer_usd,
                'reste_a_payer_cdf': reste_a_payer_cdf,
                'nombre_jours': nombre_jours,
                'prix_lit_cdf': prix_lit_cdf,
            })
            continue

        # --- Nombre de jours ---
        statut = (hosp.statut or '').upper()

        if statut == 'EN_COURS':
            # Comptage en cours jusqu'à maintenant
            delta = now - date_entree
            nombre_jours = max(1, delta.days + 1)
        else:
            # Hospitalisation terminée / annulée / autre : on utilise date_sortie
            date_sortie = hosp.date_sortie
            if not date_sortie:
                # Si pas de date_sortie mais statut != EN_COURS, on essaie d'utiliser la propriété du modèle
                date_sortie = getattr(hosp, 'date_sortie', None)

            if date_sortie and date_sortie >= date_entree:
                delta = date_sortie - date_entree
                nombre_jours = max(1, delta.days + 1)
            else:
                # Cas de secours : on utilise hosp.nombre_jours si défini
                nombre_jours = getattr(hosp, 'nombre_jours', 1)
                if nombre_jours <= 0:
                    nombre_jours = 1

        # --- Prix du lit par nuit (en CDF) ---
        prix_lit_cdf = Decimal('0')

        if hasattr(hosp.lit.chambre, 'type_chambre') and hosp.lit.chambre.type_chambre:
            prix_lit_cdf = hosp.lit.chambre.type_chambre.prix_nuitée or Decimal('0')

        if prix_lit_cdf <= 0:
            prix_lit_cdf = Decimal('50000')

        # --- Coût total en CDF ---
        cout_total_cdf = (prix_lit_cdf * nombre_jours).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        cout_total_usd = (cout_total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # --- Total déjà payé en CDF ---
        total_deja_paye_cdf = Decimal('0')
        for p in hosp.paiements.all():
            montant = p.montant_verse or Decimal('0')
            if p.devise == 'CDF':
                total_deja_paye_cdf += montant
            else:  # USD
                total_deja_paye_cdf += montant * taux

        # --- Reste à payer (en CDF + USD) ---
        reste_a_payer_cdf = max(Decimal('0'), cout_total_cdf - total_deja_paye_cdf)
        reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        hospitalisations.append({
            'hosp': hosp,
            'cout_total_usd': cout_total_usd,
            'cout_total_cdf': cout_total_cdf,
            'reste_a_payer_usd': reste_a_payer_usd,
            'reste_a_payer_cdf': reste_a_payer_cdf,
            'nombre_jours': nombre_jours,
            'prix_lit_cdf': prix_lit_cdf,
        })

    return render(request, 'back-end/hospitalisation/liste_hospitalisations.html', {
        'hospitalisations': hospitalisations,
        'fonctionKey': fonctionKey,
        'taux': taux,
        'afficher_tous': afficher_tous,
        'peut_voir_tous_hopitaux': peut_voir_tous_hopitaux,
        'hopitaux': hopitaux_qs if peut_voir_tous_hopitaux else [],
        'hopital_selectionne': hopital_selectionne,
    })

# ******************************************************************************************************
# ******************************************************************************************************
@login_required
def liste_dettes_examens_labo(request):
    # Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Filtre de base : examens de type LABO, statut terminé (ou aussi EN_ATTENTE si tu veux)
    examens_qs = DemandeExamen.objects.filter(
        prestation__categorie='LABO',          # ou un autre critère selon ton modèle
        hopital=hopital_user
    ).select_related(
        'consultation__triage__patient',
        'prestation',
        'hopital'
    )

    # Si tu veux ne prendre que les examens déjà réalisés (terminés)
    # examens_qs = examens_qs.filter(statut='TERMINE')

    # Pour chaque examen, on veut connaître le prix unitaire
    # Supposons que Prestation a un champ 'prix' ou 'tarif' en CDF
    # adapte le nom du champ selon ton modèle (prix, tarif, etc.)
    # Ici on suppose : prestation.prix (en CDF)

    # Agrégation par patient
    dettes = (
        examens_qs
        .values(
            'consultation__triage__patient',
            'consultation__triage__patient__noms',
            'consultation__triage__patient__code_patient',
            'hopital__nomH',
        )
        .annotate(
            patient_id=F('consultation__triage__patient'),
            patient_noms=F('consultation__triage__patient__noms'),
            patient_code=F('consultation__triage__patient__code_patient'),
            hopital_nom=F('hopital__nomH'),
            total_du=Sum(
                F('prestation__prix') * F('quantite'),
                output_field=DecimalField(max_digits=15, decimal_places=2)
            ),
        )
        .order_by('patient_noms')
    )

    # Pour chaque patient, on calcule le total déjà payé via les paiements liés aux examens
    # On suppose que tu as un related_name 'examens' sur consultation
    # et que les paiements sont liés à la consultation ou directement à la demande d'examen.
    # Deux cas possibles :

    # CAS 1 : Paiement lié à la consultation (service='LABO' ou 'EXAMENS')
    # et tu veux sommer tous les paiements LABO de cette consultation.
    # CAS 2 : Tu as un lien direct DemandeExamen <-> Paiement (moins courant).

    # Ici, on va faire simple : pour chaque ligne de dettes, on va chercher
    # les paiements de la consultation avec service LABO/EXAMENS.

    dettes_list = []
    for row in dettes:
        patient_id = row['patient_id']

        # Total déjà payé pour les examens LABO de ce patient
        # On passe par les consultations du patient
        total_paye = (
            Paiement.objects.filter(
                Q(service='LABO') | Q(service='EXAMENS'),
                consultation__triage__patient_id=patient_id,
                hopital=hopital_user
            )
            .aggregate(
                total=Coalesce(Sum('montant_verse'), Decimal('0'), output_field=DecimalField(max_digits=15, decimal_places=2))
            )['total']
        )

        total_du = row['total_du'] or Decimal('0')
        reste = max(Decimal('0'), total_du - total_paye)

        if reste > 0:
            dettes_list.append({
                'patient_id': patient_id,
                'patient_noms': row['patient_noms'],
                'patient_code': row['patient_code'],
                'hopital_nom': row['hopital_nom'],
                'total_du': total_du,
                'total_paye': total_paye,
                'reste_a_payer': reste,
            })

    context = {
        'dettes': dettes_list,
        'fonctionKey': fonctionKey,
    }
    return render(request, 'back-end/labo/liste_dettes_examens_labo.html', context)
#
# =====================================================================================================
# PAIEMENT DE L'HOSPITALISATION
# =====================================================================================================
@login_required
def enregistrer_paiement_hospitalisation(request, hosp_id):
    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 2. Récupérer l'hospitalisation
    hosp = get_object_or_404(Hospitalisation, id=hosp_id, hopital=hopital_user)

    if hosp.statut != 'EN_COURS':
        messages.warning(request, "Cette hospitalisation est déjà clôturée ou annulée.")
        return redirect('liste_hospitalisations')

    # 3. Taux de change (même logique que liste_hospitalisations)
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')  # 1 USD = taux CDF
    if not taux or taux == 0:
        taux = Decimal('2500.00')

    # 4. Calcul du coût total en CDF (comme dans liste_hospitalisations)
    now = timezone.now()
    date_entree = hosp.date_entree or now

    if hosp.statut == 'EN_COURS':
        nombre_jours = (now - date_entree).days + 1
    else:
        nombre_jours = getattr(hosp, 'nombre_jours', 1)
        if nombre_jours <= 0:
            nombre_jours = 1

    prix_lit_cdf = Decimal('0')
    if hasattr(hosp.lit.chambre, 'type_chambre') and hosp.lit.chambre.type_chambre:
        prix_lit_cdf = hosp.lit.chambre.type_chambre.prix_nuitée or Decimal('0')

    if prix_lit_cdf <= 0:
        prix_lit_cdf = Decimal('50000')

    cout_total_cdf = (prix_lit_cdf * nombre_jours).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    # 5. Calcul du total déjà payé en CDF
    total_deja_paye_cdf = Decimal('0')
    for p in hosp.paiements.all():
        montant = p.montant_verse or Decimal('0')
        if p.devise == 'CDF':
            total_deja_paye_cdf += montant
        else:  # USD
            total_deja_paye_cdf += montant * taux

    reste_a_payer_cdf = max(Decimal('0'), cout_total_cdf - total_deja_paye_cdf)
    reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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

            # On stocke le montant TEL QUEL dans Paiement.montant_verse
            # (20 000 si CDF, 10 si USD, etc.)
            montant_verse = montant_brut
            reduction_stockee = reduction

            # Pour la vérification et le calcul du reste, on convertit tout en CDF
            if devise == 'CDF':
                montant_verse_cdf = montant_brut
                reduction_cdf = reduction
            else:  # USD
                montant_verse_cdf = montant_brut * taux
                reduction_cdf = reduction * taux

            total_paye_ce_coup_ci_cdf = montant_verse_cdf + reduction_cdf

            # Vérification : ne pas payer plus que le reste en CDF
            if total_paye_ce_coup_ci_cdf > (reste_a_payer_cdf + Decimal('1')):
                messages.error(
                    request,
                    "Le montant saisi dépasse le solde restant ({} CDF / {} USD).".format(
                        int(round(reste_a_payer_cdf)),
                        float(reste_a_payer_usd)
                    )
                )
                return redirect('payer_hospitalisation', hosp_id=hosp.id)

            # Création du paiement
            # montant_verse et reduction_stockee sont dans la devise choisie
            Paiement.objects.create(
                hospitalisation=hosp,
                patient=hosp.patient,
                service='HOSPITALISATION',
                montant_verse=montant_verse,          # 20000 si CDF, 10 si USD, etc.
                montant_reduction=reduction_stockee,  # idem
                devise=devise,                        # 'CDF' ou 'USD'
                caissier=request.user,
                hopital=hopital_user
            )

            # Recalculer le nouveau reste après ce paiement
            nouveau_total_deja_paye_cdf = total_deja_paye_cdf + total_paye_ce_coup_ci_cdf
            nouveau_reste_cdf = max(Decimal('0'), cout_total_cdf - nouveau_total_deja_paye_cdf)

            if nouveau_reste_cdf <= 0:
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

    # Contexte pour le template
    return render(request, 'back-end/hospitalisation/paiement_hosp.html', {
        'hosp': hosp,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'cout_total_cdf': cout_total_cdf,
        'cout_total_usd': (cout_total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'fonctionKey': fonctionKey,
        'taux': taux,
        'nombre_jours': nombre_jours,
        'prix_lit_cdf': prix_lit_cdf,
    })

# 
# ============================================================================================
# IMPRIMER FACTURE HOPITAL
# ============================================================================================
@login_required
def imprimer_facture_hospitalisation(request, hosp_id):
    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Utilisateur autorisé : même hôpital OU admin/superuser
    peut_voir_tous_hopitaux = (
        request.user.is_superuser
        or (role and role.fonctionKey and role.fonctionKey.roleName in ['Admin', 'Directeur'])
    )

    # 2. Récupérer l'hospitalisation
    hosp = get_object_or_404(Hospitalisation, id=hosp_id)

    # Vérification des droits
    if not peut_voir_tous_hopitaux and hosp.hopital != hopital_user:
        messages.error(request, "Vous n'avez pas accès à cette hospitalisation.")
        return redirect('liste_hospitalisations')

    # 3. Taux de change
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2500.00')
    if not taux or taux == 0:
        taux = Decimal('2500.00')

    # 4. Calcul du coût total en CDF
    now = timezone.now()
    date_entree = hosp.date_entree or now

    if hosp.statut == 'EN_COURS':
        nombre_jours = (now - date_entree).days + 1
    else:
        nombre_jours = getattr(hosp, 'nombre_jours', 1)
        if nombre_jours <= 0:
            nombre_jours = 1

    prix_lit_cdf = Decimal('0')
    if hasattr(hosp.lit.chambre, 'type_chambre') and hosp.lit.chambre.type_chambre:
        prix_lit_cdf = hosp.lit.chambre.type_chambre.prix_nuitée or Decimal('0')

    if prix_lit_cdf <= 0:
        prix_lit_cdf = Decimal('50000')

    cout_total_cdf = (prix_lit_cdf * nombre_jours).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    cout_total_usd = (cout_total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 5. Calcul du total déjà payé en CDF
    total_deja_paye_cdf = Decimal('0')
    for p in hosp.paiements.all():
        montant = p.montant_verse or Decimal('0')
        if p.devise == 'CDF':
            total_deja_paye_cdf += montant
        else:  # USD
            total_deja_paye_cdf += montant * taux

    reste_a_payer_cdf = max(Decimal('0'), cout_total_cdf - total_deja_paye_cdf)
    reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    context = {
        'hosp': hosp,
        'patient': hosp.patient,
        'nombre_jours': nombre_jours,
        'prix_lit_cdf': prix_lit_cdf,
        'cout_total_cdf': cout_total_cdf,
        'cout_total_usd': cout_total_usd,
        'total_deja_paye_cdf': total_deja_paye_cdf,
        'total_deja_paye_usd': (total_deja_paye_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'taux': taux,
        'paiements': hosp.paiements.all().order_by('-date_paiement'),
        'fonctionKey': fonctionKey,
        'date_impression': timezone.now(),
    }

    return render(request, 'back-end/hospitalisation/facture_hospitalisation.html', context)

#
# ===========================================================================================
# DOSSIER MEDICALE
# ============================================================================================
@login_required
def dossier_medical_complet(request, patient_id):
    """Dossier médical complet - Affiche TOUT l'historique du patient + avis médecins"""

    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    patient = get_object_or_404(Patient, id=patient_id, hopital=hopital_user)

    if not patient.fiche_payee:
        messages.error(request, "Accès refusé. Fiche patient non payée.")
        return redirect('liste_patients')

    # ------------------------------
    # FILTRE PAR DATE
    # ------------------------------
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    # ------------------------------
    # GESTION DU FORMULAIRE (POST) - AJOUT AVIS MÉDECIN
    # ------------------------------
    if request.method == 'POST' and request.POST.get('action') == 'avis_medecin':
        if fonctionKey in ('medecin', 'admin'):
            type_avis = request.POST.get('type_avis', 'COMMENTAIRE')
            titre = request.POST.get('titre', '').strip() or None
            contenu = request.POST.get('contenu', '').strip()

            consultation_id = request.POST.get('consultation')
            hospitalisation_id = request.POST.get('hospitalisation')

            consultation = None
            hospitalisation = None

            if consultation_id:
                consultation = get_object_or_404(
                    Consultation,
                    id=consultation_id,
                    triage__patient=patient,
                    hopital=hopital_user
                )

            if hospitalisation_id:
                hospitalisation = get_object_or_404(
                    Hospitalisation,
                    id=hospitalisation_id,
                    patient=patient,
                    hopital=hopital_user
                )

            if not contenu:
                messages.error(request, "Le contenu de l'avis est obligatoire.")
            else:
                AvisMedecin.objects.create(
                    patient=patient,
                    medecin=request.user,
                    hopital=hopital_user,
                    type_avis=type_avis,
                    titre=titre,
                    contenu=contenu,
                    consultation=consultation,
                    hospitalisation=hospitalisation,
                )
                messages.success(request, "Avis médecin enregistré avec succès.")

        return redirect('dossier_medical_complet', patient_id=patient.id)
    # ------------------------------

    # --- CONSULTATIONS ---
    consultations_qs = Consultation.objects.filter(
        triage__patient=patient,
        hopital=hopital_user
    ).order_by('-date_creation').select_related(
        'triage', 'medecin', 'session'
    ).prefetch_related(
        'examens__prestation',
        'ordonnance_set__medicaments',
        'ordonnance_set__lignes_medicaments'
    )

    # Filtre par date
    if date_debut:
        try:
            d_debut = datetime.strptime(date_debut, '%Y-%m-%d')
            consultations_qs = consultations_qs.filter(date_creation__date__gte=d_debut.date())
        except ValueError:
            pass

    if date_fin:
        try:
            d_fin = datetime.strptime(date_fin, '%Y-%m-%d')
            consultations_qs = consultations_qs.filter(date_creation__date__lte=d_fin.date())
        except ValueError:
            pass

    consultations = consultations_qs

    # --- HOSPITALISATIONS ---
    hospitalisations = Hospitalisation.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_entree').prefetch_related(
        'kardex_items__administrations',
        'suivis_journaliers',
        'ordonnance_sortie',
        'rendezvous_set',
        'lit__chambre__type_chambre'
    )

    # --- SIGNES VITAUX ---
    signes_vitaux = SigneVital.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_prelevement').select_related('infirmier', 'session')

    # --- MATERNITÉ ---
    maternites = Maternite.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_admission').prefetch_related(
        'consultations__effectue_par'
    )

    # --- SESSIONS DE SOINS ---
    sessions = SessionSoins.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_creation').prefetch_related(
        'items__prestation',
        'signes_vitaux'
    )

    # --- AVIS MÉDECIN ---
    avis_medecin = AvisMedecin.objects.filter(
        patient=patient,
        hopital=hopital_user
    ).order_by('-date_avis').select_related('medecin', 'consultation', 'hospitalisation')

    # --- STATS ---
    total_consultations = consultations.count()
    total_hospitalisations = hospitalisations.count()
    total_examens = DemandeExamen.objects.filter(
        consultation__in=consultations
    ).count()
    total_ordonnances = Ordonnance.objects.filter(
        consultation__in=consultations
    ).count()
    total_avis = avis_medecin.count()

    context = {
        'patient': patient,
        'consultations': consultations,
        'hospitalisations': hospitalisations,
        'signes_vitaux': signes_vitaux,
        'maternites': maternites,
        'sessions': sessions,
        'avis_medecin': avis_medecin,
        'fonctionKey': fonctionKey,
        'total_consultations': total_consultations,
        'total_hospitalisations': total_hospitalisations,
        'total_examens': total_examens,
        'total_ordonnances': total_ordonnances,
        'total_avis': total_avis,
        'date_debut': date_debut or '',
        'date_fin': date_fin or '',
    }

    return render(request, 'back-end/patient/dossier_medical.html', context)
#
# ===========================================================================================
# DETAIL HOSPITALIERE
# ============================================================================================
@login_required
def detail_hospitalisation(request, pk):
    # Rôle de l'utilisateur
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Hospitalisation concernée
    hosp = get_object_or_404(
        Hospitalisation.objects.select_related(
            'patient',
            'lit__chambre__type_chambre'
        ),
        pk=pk,
        hopital=hopital_user
    )

    # ------------------------------
    # 1) GESTION DU FORMULAIRE (POST)
    # ------------------------------
    if request.method == 'POST':
        action = request.POST.get('action')

        # --- Suivi médecin ---
        if action == 'suivi_medecin':
            if fonctionKey in ('medecin', 'admin'):
                diagnostic = request.POST.get('diagnostic_du_jour', '')
                evolution = request.POST.get('evolution', '')
                consignes = request.POST.get('consignes', '')

                SuiviMedecin.objects.create(
                    hospitalisation=hosp,
                    medecin=request.user,
                    diagnostic_du_jour=diagnostic,
                    evolution=evolution,
                    consignes=consignes,
                    hopital=hopital_user
                )
                messages.success(request, "Suivi médecin enregistré avec succès.")

            return redirect('detail_hospitalisation', pk=pk)

        # Tu pourras ajouter d'autres actions ici (ex: action == 'suivi_infirmier', etc.)

    # ------------------------------
    # 2) PRÉPARATION DES DONNÉES (GET ou après POST)
    # ------------------------------
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
            'voie': item.voie_administration,
            'est_actif': item.est_actif,
            'cellules': [
                {'date': jour, 'admin': admins.get(jour)}
                for jour in jours
            ]
        }
        kardex_data.append(row)

    # Suivis infirmier
    suivis_list = hosp.suivis_journaliers.all().order_by('-date_suivi')
    paginator = Paginator(suivis_list, 5)
    page_number = request.GET.get('page')
    suivis = paginator.get_page(page_number)

    # Suivis médecin
    suivis_medecin = hosp.suivis_medecin.all().order_by('-date_suivi')

    # ------------------------------
    # 3) RENDU DU TEMPLATE
    # ------------------------------
    return render(request, 'back-end/hospitalisation/detail.html', {
        'hosp': hosp,
        'ordonnances': ordonnances,
        'kardex_data': kardex_data,
        'suivis': suivis,
        'suivis_medecin': suivis_medecin,
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
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None

    # Filtrer par hôpital (sauf ADMIN) mais accepter URGENCE et DEFINITIVE
    queryset = Ordonnance.objects.filter(
        id=ordonnance_id
    ).select_related(
        'consultation__triage__patient',
        'consultation__medecin'
    ).prefetch_related(
        'lignes_medicaments'
    )

    if hopital_user:
        queryset = queryset.filter(
            consultation__triage__patient__hopital=hopital_user
        )
    else:
        # Si pas d'hôpital, on ne restreint pas (ou tu peux bloquer selon ta logique)
        pass

    # Accepter URGENCE et DEFINITIVE
    ordonnance = get_object_or_404(
        queryset,
        type_ordonnance__in=['URGENCE', 'DEFINITIVE']
    )

    return render(request, 'back-end/medecin/imprimer_ordonnance.html', {
        'ordonnance': ordonnance
    })


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
    # Vérifier que c'est un staff / admin
    if not request.user.is_staff:
        messages.error(request, "Vous n'êtes pas autorisé à enregistrer une entreprise.")
        return redirect('liste_entreprises')

    # Récupérer la fonction de l'utilisateur connecté
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        form = EntrepriseForm(request.POST)
        if form.is_valid():
            entreprise = form.save(commit=False)
            # L'admin choisit l'hôpital via le formulaire, donc on ne le force pas ici
            # Si tu veux forcer l'hôpital de l'utilisateur, utilise :
            # entreprise.hopital = user_hopital
            entreprise.created_by = request.user
            entreprise.save()
            messages.success(request, "L'entreprise a été enregistrée avec succès.")
            return redirect('liste_entreprises')
    else:
        form = EntrepriseForm()

    return render(request, 'back-end/entreprise/enregistrer_entreprise.html', {
        'form': form,
        'fonctionKey': fonctionKey,
    })

#
# ======================================================================================
# LISTE DES ENTREPRISES
# ======================================================================================
@login_required
def liste_entreprises_view(request):
    # Optionnel : réserver aux admins
    if not request.user.is_staff:
        messages.error(request, "Accès non autorisé.")
        return redirect('accueil')

    # Récupérer la fonction de l'utilisateur connecté
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # Requête de base
    qs = Entreprise.objects.select_related('hopital').order_by('-date_enregistrement')

    # --- Recherche ---
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(nom__icontains=query) |
            Q(contact_responsable__icontains=query) |
            Q(hopital__nomH__icontains=query)
        )

    # --- Pagination ---
    paginator = Paginator(qs, 10)  # 10 entreprises par page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'back-end/entreprise/liste_entreprises.html', {
        'entreprises': page_obj.object_list,  # liste des objets pour la boucle
        'page_obj': page_obj,                 # objet de pagination pour le template
        'fonctionKey': fonctionKey,           # pour ton header / sidebar / logs, etc.
        'user_hopital': user_hopital,         # optionnel, si tu veux l’utiliser dans le template
    })

# 
# =====================================================================================
# MODIFICATION ENTREPRISE
# =====================================================================================
@login_required
def modifier_entreprise_view(request, pk):
    # Vérifier que c'est un staff / admin
    if not request.user.is_staff:
        messages.error(request, "Vous n'êtes pas autorisé à modifier cette entreprise.")
        return redirect('liste_entreprises')

    # Récupérer la fonction de l'utilisateur connecté
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Récupérer l'entreprise à modifier
    entreprise = get_object_or_404(Entreprise, pk=pk)

    if request.method == 'POST':
        form = EntrepriseForm(request.POST, instance=entreprise)
        if form.is_valid():
            form.save()
            messages.success(request, "L'entreprise a été modifiée avec succès.")
            return redirect('liste_entreprises')
    else:
        form = EntrepriseForm(instance=entreprise)

    return render(request, 'back-end/entreprise/modifier_entreprise.html', {
        'form': form,
        'fonctionKey': fonctionKey,
        'entreprise': entreprise,
    })


#
# ======================================================================================
# SUPPRIMER ENTREPRISE 
# ======================================================================================
@login_required
def supprimer_entreprise_view(request, pk):
    # Réservé aux admins / staff
    if not request.user.is_staff:
        messages.error(request, "Accès non autorisé.")
        return redirect('liste_entreprises')

    # Récupérer la fonction de l'utilisateur connecté
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Récupérer l'entreprise
    entreprise = get_object_or_404(Entreprise, pk=pk)

    # Nombre de patients liés à cette entreprise
    nb_patients = entreprise.patients.count()

    if request.method == 'POST':
        nom = entreprise.nom
        entreprise.delete()  # on_delete=SET_NULL sur Patient.entreprise → patients conservés
        messages.success(request, f"L'entreprise « {nom} » a été supprimée avec succès.")
        return redirect('liste_entreprises')

    return render(request, 'back-end/entreprise/confirmer_suppression_entreprise.html', {
        'entreprise': entreprise,
        'fonctionKey': fonctionKey,
        'nb_patients': nb_patients,
    })


#
# ======================================================================================
# MEDECIN ORDONNANCE D'URGENCES
# ======================================================================================
@login_required
def enregistrer_ordonnance_urgence(request, consultation_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    consultation = get_object_or_404(
        Consultation,
        pk=consultation_id,
        triage__patient__hopital=hopital_user
    )
    patient = consultation.patient

    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic')
        observation = request.POST.get('observation')

        noms = request.POST.getlist('nom')
        posologies = request.POST.getlist('posologie')
        durees = request.POST.getlist('duree')
        quantites = request.POST.getlist('quantite')

        try:
            with transaction.atomic():
                ordonnance = Ordonnance.objects.create(
                    consultation=consultation,
                    type_ordonnance='URGENCE',
                    diagnostic=diagnostic,
                    observation=observation,
                    hopital=hopital_user
                )

                for nom, posologie, duree, quantite in zip(noms, posologies, durees, quantites):
                    if nom and nom.strip():
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom.strip(),
                            posologie=posologie.strip() if posologie else '',
                            duree=duree.strip() if duree else '',
                            quantite=int(quantite) if quantite and str(quantite).isdigit() else 1,
                            hopital=hopital_user
                        )

            messages.success(request, "Ordonnance d'urgence enregistrée avec succès.")
            return redirect('detail_patient', pk=patient.pk)

        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")

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
    # 1. Rôle & hôpital de l'utilisateur
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(
        userKey=request.user
    ).first()
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # Si l'utilisateur n'a pas d'hôpital → message + redirection
    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('liste_patients')  # ou une autre vue selon ton besoin

    # 2. On filtre pour ne garder QUE :
    # - les patients dont fiche_payee est True
    # - ET qui appartiennent à l'hôpital de l'utilisateur
    patients = Patient.objects.filter(
        fiche_payee=True,
        hopital=hopital_user
    ).order_by('-id')
    
    # 3. Enrichissement
    for p in patients:
        # Consultation la plus récente
        p.consultation_active = Consultation.objects.filter(
            triage__patient=p,
            hopital=hopital_user
        ).order_by('-date_creation').first()
        
        # Hospitalisation en cours
        p.hosp_en_cours = Hospitalisation.objects.filter(
            patient=p, 
            statut='EN_COURS',
            hopital=hopital_user
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
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related('consultation'),
        id=ordonnance_id
    )

    if request.method == 'POST':
        try:
            with transaction.atomic():
                ordonnance.type_ordonnance = request.POST.get('type_ordonnance')
                ordonnance.observation = request.POST.get('observation')
                ordonnance.save()

                ordonnance.medicaments.all().delete()

                noms = request.POST.getlist('nom_medicament[]')
                posologies = request.POST.getlist('posologie[]')
                durees = request.POST.getlist('duree[]')
                quantites = request.POST.getlist('quantite[]')

                for nom, posologie, duree, quantite in zip(noms, posologies, durees, quantites):
                    if nom and nom.strip():
                        Medicament.objects.create(
                            ordonnance=ordonnance,
                            nom=nom.strip(),
                            posologie=posologie.strip() if posologie else '',
                            duree=duree.strip() if duree else '',
                            quantite=int(quantite) if quantite and str(quantite).isdigit() else 1
                        )

            messages.success(request, "Ordonnance mise à jour avec succès.")
            return redirect('liste_ordonnances')

        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour : {str(e)}")

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/modifier_ordonnance.html', {
        'ord': ordonnance,
        'fonctionKey': fonctionKey
    })

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
@login_required
def enregistrer_soin_rapide(request):
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    if request.method == 'POST':
        nom_patient = request.POST.get('nom_patient')
        ids_prestations = request.POST.getlist('prestation_ids')
        reduction = Decimal(request.POST.get('reduction', '0.00'))
        devise_paiement = request.POST.get('devise')  # 'CDF' ou 'USD'

        prestations = Prestation.objects.filter(
            id__in=ids_prestations,
            hopital=user_hopital,
            categorie='SOIN'
        )

        total_brut = sum((p.prix for p in prestations), Decimal('0.00'))
        net_cdf = total_brut - reduction

        taux = ConfigurationHopital.get_taux()

        if devise_paiement == 'USD':
            montant_verse = (net_cdf / taux) if taux else Decimal('0.00')
            devise_enregistree = 'USD'
        else:
            montant_verse = net_cdf
            devise_enregistree = 'CDF'

        try:
            with transaction.atomic():
                paiement = Paiement.objects.create(
                    service='SOIN',
                    montant_verse=montant_verse,
                    montant_reduction=reduction,
                    devise=devise_enregistree,
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
    })#
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
            try:
                with transaction.atomic():
                    produit = form.save(commit=False)
                    produit.hopital = hopital_user
                    produit.enregistre_par = request.user
                    produit.devise = 'CDF'  # Force CDF par défaut
                    
                    #-validation des prix (doivent être > 0)
                    if produit.prix_achat_unitaire <= 0 or produit.prix_vente_unitaire <= 0:
                        messages.error(request, "Les prix doivent être supérieurs à 0.")
                        return redirect('ajouter_produit')
                    
                    produit.save()
                    
                messages.success(request, "Le produit a été enregistré avec succès.")
                return redirect('gestion_pharmacie')
                
            except Exception as e:
                messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
        else:
            messages.error(request, "Erreur lors de l'enregistrement. Vérifie les données.")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ProduitPharmacieForm()

    return render(request, 'back-end/pharmacie/ajouter_produit.html', {
        'form': form,
        'fonctionKey': fonctionKey,
        'taux': ConfigurationHopital.get_taux(),
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
        # Sous-requête pour les entrées totales
        entrees_subquery = LotPharmacie.objects.filter(
            produit_id=OuterRef('pk'),
            hopital=hopital_user
        ).values('produit_id').annotate(
            total_entrees=Coalesce(Sum('quantite_initiale'), 0)
        ).values('total_entrees')[:1]

        # Sous-requête pour les sorties totales
        sorties_subquery = SortiePharmacie.objects.filter(
            lot__produit_id=OuterRef('pk'),
            lot__hopital=hopital_user
        ).values('lot__produit_id').annotate(
            total_sorties=Coalesce(Sum('quantite_vendue'), 0)
        ).values('total_sorties')[:1]

        # Requête principale
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

        # Calcul de la valeur totale du stock (en CDF)
        for p in produits:
            # prix_vente_unitaire est déjà en CDF
            p.valeur_totale = Decimal(p.stock_reel) * p.prix_vente_unitaire

    # Taux de change (optionnel, pour affichage USD si besoin)
    taux_change = ConfigurationHopital.get_taux()

    context = {
        'produits': produits,
        'fonctionKey': fonctionKey,
        'taux': taux_change,
    }

    return render(request, 'back-end/pharmacie/gestion_stock.html', context)
#
# ====================================================================================
# MODIFIER MEDICAMENT
# ====================================================================================
@login_required
def modifier_produit_pharmacie(request, produit_id):
    """Vue pour modifier un produit de pharmacie"""
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
            with transaction.atomic():
                produit.nom = request.POST.get('nom', '').strip()
                produit.forme = request.POST.get('forme', '').strip()
                produit.dosage = request.POST.get('dosage', '').strip()
                produit.categorie = request.POST.get('categorie', '').strip()
                produit.unites_par_carton = int(request.POST.get('unites_par_carton', 1) or 1)
                
                # Prix en CDF (conversion si nécessaire)
                produit.prix_achat_unitaire = Decimal(request.POST.get('prix_achat_unitaire', 0) or 0)
                produit.prix_vente_unitaire = Decimal(request.POST.get('prix_vente_unitaire', 0) or 0)
                
                # Force CDF comme devise
                produit.devise = 'CDF'
                
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
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('modifier_produit', produit_id=produit_id)
        except Exception as e:
            messages.error(request, f"❌ Erreur inattendue : {str(e)}")
            return redirect('modifier_produit', produit_id=produit_id)
    
    # Calcul du stock réel
    entrees = LotPharmacie.objects.filter(
        produit=produit,
        hopital=hopital_user
    ).aggregate(total=Coalesce(Sum('quantite_initiale'), 0))['total'] or 0
    
    sorties = SortiePharmacie.objects.filter(
        lot__produit=produit,
        lot__hopital=hopital_user
    ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
    
    stock_reel = entrees - sorties
    valeur_totale = Decimal(stock_reel) * produit.prix_vente_unitaire if produit.prix_vente_unitaire else Decimal('0.00')
    
    context = {
        'produit': produit,
        'stock_reel': stock_reel,
        'valeur_totale': valeur_totale,
        'fonctionKey': role.fonctionKey.roleName if role and role.fonctionKey else None,
        'taux': ConfigurationHopital.get_taux()
    }
    
    return render(request, 'back-end/pharmacie/modifier_produit.html', context)#
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
            devise = data.get('devise', 'CDF')  # CDF par défaut
            montant_verse = Decimal(str(data.get('montant_verse', 0)))

            if not panier:
                return JsonResponse({'status': 'error', 'message': 'Le panier est vide.'})
            if montant_verse < 0:
                return JsonResponse({'status': 'error', 'message': 'Montant versé invalide.'})

            # Taux de change (1 USD = taux CDF)
            taux = Decimal(str(ConfigurationHopital.get_taux()))
            if not taux or taux <= 0:
                taux = Decimal('2300.00')

            with transaction.atomic():
                montant_total_cdf = Decimal('0.00')
                items_a_vendre = []

                # Calcul du total en CDF
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

                    # prix_vente_unitaire est considéré en CDF
                    prix_u_cdf = Decimal(str(lot.produit.prix_vente_unitaire or 0))
                    montant_total_cdf += (prix_u_cdf * int(item['qte']))
                    items_a_vendre.append({'lot': lot, 'qte': int(item['qte'])})

                # Convertir le montant versé en CDF pour comparer
                if devise == 'CDF':
                    montant_verse_cdf = montant_verse
                else:  # USD
                    montant_verse_cdf = montant_verse * taux

                if montant_verse_cdf > montant_total_cdf + Decimal('1'):
                    return JsonResponse({'status': 'error', 'message': 'Le montant versé dépasse le total à payer.'})

                reste_a_payer_cdf = montant_total_cdf - montant_verse_cdf

                paiement = Paiement.objects.create(
                    montant_verse=montant_verse,      # montant dans la devise saisie
                    devise=devise,
                    service='PHARMACIE',
                    caissier=request.user,
                    hopital=hopital_user,
                    reste_a_payer=reste_a_payer_cdf   # reste en CDF
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
                'dette_cdf': str(reste_a_payer_cdf),
                'total_cdf': str(montant_total_cdf)
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
@login_required
def liste_ventes(request):
    role_obj = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role_obj.hopital if role_obj else None
    fonctionKey = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Invité"

    # Taux de change (1 USD = taux CDF)
    taux = Decimal(str(ConfigurationHopital.get_taux()))
    if not taux or taux <= 0:
        taux = Decimal('2300.00')

    # Base : toutes les ventes pharmacie de l’hôpital
    ventes = Paiement.objects.filter(service='PHARMACIE', hopital=hopital_user).order_by('-date_paiement')

    # Filtres
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

    # Séparation par devise
    usd_ventes = ventes.filter(devise='USD')
    cdf_ventes = ventes.filter(devise='CDF')

    # Totaux bruts (dans leur devise)
    total_verse_usd = usd_ventes.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')
    total_verse_cdf = cdf_ventes.aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')

    total_reste_usd = usd_ventes.aggregate(total=Sum('reste_a_payer'))['total'] or Decimal('0.00')
    total_reste_cdf = cdf_ventes.aggregate(total=Sum('reste_a_payer'))['total'] or Decimal('0.00')

    total_reduction_usd = usd_ventes.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')
    total_reduction_cdf = cdf_ventes.aggregate(total=Sum('montant_reduction'))['total'] or Decimal('0.00')

    # Conversion CDF <-> USD pour l’affichage
    # On considère que les totaux "principaux" sont en CDF
    total_verse_cdf_total = total_verse_cdf + (total_verse_usd * taux)
    total_verse_usd_total = total_verse_cdf_total / taux if taux else Decimal('0.00')

    total_reste_cdf_total = total_reste_cdf + (total_reste_usd * taux)
    total_reste_usd_total = total_reste_cdf_total / taux if taux else Decimal('0.00')

    total_reduction_cdf_total = total_reduction_cdf + (total_reduction_usd * taux)
    total_reduction_usd_total = total_reduction_cdf_total / taux if taux else Decimal('0.00')

    return render(request, 'back-end/pharmacie/liste_ventes.html', {
        'ventes': ventes,
        'fonctionKey': fonctionKey,

        # Totaux par devise (bruts)
        'total_verse_usd': total_verse_usd,
        'total_verse_cdf': total_verse_cdf,
        'total_reste_usd': total_reste_usd,
        'total_reste_cdf': total_reste_cdf,
        'total_reduction_usd': total_reduction_usd,
        'total_reduction_cdf': total_reduction_cdf,

        # Totaux globaux (CDF + USD convertis)
        'total_verse_cdf_total': total_verse_cdf_total,
        'total_verse_usd_total': total_verse_usd_total,
        'total_reste_cdf_total': total_reste_cdf_total,
        'total_reste_usd_total': total_reste_usd_total,
        'total_reduction_cdf_total': total_reduction_cdf_total,
        'total_reduction_usd_total': total_reduction_usd_total,

        'nb_ventes': ventes.count(),
        'q': q,
        'devise': devise,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'taux_actuel': float(taux),
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
        'fonctionKey': fonctionKey,
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

    taux = ConfigurationHopital.get_taux()

    for session in sessions:
        total_session = session.items.aggregate(Sum('prix_facture'))['prix_facture__sum'] or Decimal('0')

        total_paye_cdf = Decimal('0')
        total_red_cdf = Decimal('0')

        for p in session.paiements.all():
            if p.devise == 'USD':
                total_paye_cdf += (p.montant_verse or Decimal('0')) * taux
                total_red_cdf += (p.montant_reduction or Decimal('0')) * taux
            else:
                total_paye_cdf += (p.montant_verse or Decimal('0'))
                total_red_cdf += (p.montant_reduction or Decimal('0'))

        session.total_verse = total_paye_cdf
        session.total_reductions = total_red_cdf
        session.total_payer_calc = total_session
        session.actuel_reste = max(Decimal('0'), total_session - total_paye_cdf - total_red_cdf)

    return render(request, 'back-end/consultation/liste_sessions.html', {
        'sessions': sessions,
        'fonctionKey': fonction_key
    })

#
# ===================================================================================================================
# FACTURE IMPRIMER DE LA SESSION NOUVELLE
# ===================================================================================================================
@login_required
def facture_session(request, session_id):
    role = Fonction.objects.select_related('hopital', 'fonctionKey').filter(userKey=request.user).first()
    hopital_user = role.hopital if role else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient').prefetch_related('items__prestation', 'paiements'),
        pk=session_id,
        hopital=hopital_user
    )

    taux = ConfigurationHopital.get_taux()
    total_session = session.items.aggregate(Sum('prix_facture'))['prix_facture__sum'] or Decimal('0')
    total_paye = Decimal('0')
    total_red = Decimal('0')

    for p in session.paiements.all():
        if p.devise == 'USD':
            total_paye += (p.montant_verse or Decimal('0')) * taux
            total_red += (p.montant_reduction or Decimal('0')) * taux
        else:
            total_paye += (p.montant_verse or Decimal('0'))
            total_red += (p.montant_reduction or Decimal('0'))

    reste = max(Decimal('0'), total_session - total_paye - total_red)

    return render(request, 'back-end/consultation/facture_session.html', {
        'session': session,
        'total_session': total_session,
        'total_paye': total_paye,
        'total_red': total_red,
        'reste': reste,
        'taux': taux,
    })
#
# ====================================================================================================================
# PAIEMENT DESE SESSION(CONSULTATION)
# ====================================================================================================================
@login_required
def payer_session(request, session_id):
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        pk=session_id,
        hopital=hopital_user
    )

    taux = ConfigurationHopital.get_taux()

    total_session = session.items.aggregate(models.Sum('prix_facture'))['prix_facture__sum'] or Decimal('0')
    total_deja_paye = Decimal('0')
    total_reductions = Decimal('0')

    for p in session.paiements.all():
        if p.devise == 'USD':
            total_deja_paye += (p.montant_verse or Decimal('0')) * taux
            total_reductions += (p.montant_reduction or Decimal('0')) * taux
        else:
            total_deja_paye += (p.montant_verse or Decimal('0'))
            total_reductions += (p.montant_reduction or Decimal('0'))

    reste_a_payer = max(Decimal('0'), total_session - total_deja_paye - total_reductions)

    if request.method == 'POST':
        try:
            montant_saisi = Decimal(request.POST.get('montant', 0))
            reduction = Decimal(request.POST.get('reduction', 0))
            devise = request.POST.get('devise', 'CDF')

            if devise == 'USD':
                montant_cdf = montant_saisi * taux
                reduction_cdf = reduction * taux
            else:
                montant_cdf = montant_saisi
                reduction_cdf = reduction

            if montant_cdf + reduction_cdf > reste_a_payer:
                messages.error(request, f"Montant trop élevé. Reste à payer : {reste_a_payer:.0f} CDF.")
                return redirect('paiement_session', session_id=session.id)

            Paiement.objects.create(
                session=session,
                patient=session.patient,
                service='SOIN',
                montant_verse=montant_saisi,
                montant_reduction=reduction,
                devise=devise,
                caissier=request.user,
                hopital=hopital_user
            )

            # Après tout paiement réussi, on va à la page de choix
            return redirect('apres_paiement_session', session_id=session.id)

        except Exception as e:
            messages.error(request, f"Erreur lors du paiement : {str(e)}")
            return redirect('paiement_session', session_id=session.id)

    return render(request, 'back-end/consultation/payer_session.html', {
        'session': session,
        'total_session': total_session,
        'reste_a_payer': reste_a_payer,
        'taux': taux,
        'fonctionKey': fonctionKey
    })
#
# ====================================================================================================================
# APRES PAIEMENT DESE SESSION(CONSULTATION)
# ====================================================================================================================
@login_required
def apres_paiement_session(request, session_id):
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Accès non autorisé.")
        return redirect('liste_sessions')

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        pk=session_id,
        hopital=hopital_user
    )

    taux = ConfigurationHopital.get_taux()

    total_session = session.items.aggregate(models.Sum('prix_facture'))['prix_facture__sum'] or Decimal('0')
    total_deja_paye = Decimal('0')
    total_reductions = Decimal('0')

    for p in session.paiements.all():
        if p.devise == 'USD':
            total_deja_paye += (p.montant_verse or Decimal('0')) * taux
            total_reductions += (p.montant_reduction or Decimal('0')) * taux
        else:
            total_deja_paye += (p.montant_verse or Decimal('0'))
            total_reductions += (p.montant_reduction or Decimal('0'))

    reste_a_payer = max(Decimal('0'), total_session - total_deja_paye - total_reductions)

    session_soldee = (reste_a_payer == 0)

    return render(request, 'back-end/consultation/apres_paiement_session.html', {
        'session': session,
        'reste_a_payer': reste_a_payer,
        'session_soldee': session_soldee,
        'fonctionKey': role.fonctionKey.roleName if role and role.fonctionKey else None,
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

    # Debug temporaire
    print("role:", role)
    print("hopital_user:", hopital_user)

    if not hopital_user:
        # Pour l’instant, on bloque simplement
        return redirect('liste_sessions_infirmier')

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    session = get_object_or_404(
        SessionSoins.objects.select_related('patient'),
        id=session_id,
        hopital=hopital_user
    )

    if request.method == 'POST':
        form = SigneVitalForm(request.POST)
        if form.is_valid():
            print("Formulaire valide")
            signes = form.save(commit=False)
            signes.session = session
            signes.patient = session.patient
            signes.infirmier = request.user
            signes.hopital = hopital_user
            signes.save()
            print("Signes vitaux enregistrés")
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

    # Taux de change (1 USD = taux CDF)
    taux = Decimal(str(ConfigurationHopital.get_taux()))
    if not taux or taux <= 0:
        taux = Decimal('2300.00')

    if request.method == 'POST':
        montant_saisi = Decimal(str(request.POST.get('montant') or '0'))
        devise_paiement = request.POST.get('devise_paiement', 'CDF')

        if montant_saisi <= 0:
            messages.error(request, "Le montant saisi doit être supérieur à 0.")
            return redirect('liste_ventes')

        # Convertir le montant saisi en CDF
        if devise_paiement == 'CDF':
            montant_cdf = montant_saisi
        else:  # USD
            montant_cdf = montant_saisi * taux

        # Arrondir à 2 décimales
        montant_cdf = montant_cdf.quantize(Decimal('0.01'))

        # Vérifier qu’on ne paie pas plus que le reste (qui est en CDF)
        if montant_cdf > paiement.reste_a_payer:
            messages.error(
                request,
                f"Le montant saisi ({montant_saisi} {devise_paiement}) dépasse la dette restante "
                f"({paiement.reste_a_payer} CDF)."
            )
            return redirect('liste_ventes')

        with transaction.atomic():
            # On met à jour uniquement le reste et le montant versé (en CDF)
            paiement.reste_a_payer -= montant_cdf
            paiement.montant_verse += montant_cdf
            paiement.save()

        messages.success(request, "Dette mise à jour avec succès.")
        return redirect('liste_ventes')

    return render(request, 'back-end/pharmacie/ajouter_paiement_dette.html', {
        'paiement': paiement,
        'taux': float(taux),
        'fonctionKey': fonctionKey
    })
# 
# ===========================================================================================================
# ENREGISTREMENT DU PATIENT EXTERNE POUR LES EXAMENS 
# =========================================================================================================== 
@login_required
def enregistrer_client_externe(request):
    # Récupère le rôle et l'hôpital du user connecté
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    
    if not role or not role.fonctionKey:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})
    
    fonctionKey = role.fonctionKey.roleName
    user_hopital = role.hopital

    if request.method == 'POST':
        form = ClientExterneForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            
            # Associe le client à l'hôpital du user (sauf si admin)
            if fonctionKey != 'admin' and user_hopital:
                client.hopital = user_hopital
            
            client.save()
            
            messages.success(request, f"Client {client.noms} enregistré avec succès !")
            return redirect('creer_demande_examen', client_id=client.id)
    else:
        form = ClientExterneForm()

    return render(request, 'back-end/client/enregistrer_client.html', {
        'form': form,
        'fonctionKey': fonctionKey,
        'hopital_user': user_hopital,  # ← Ajoute ça pour afficher dans le template
    })

# 
# ===========================================================================================================
# ENREGISTREMENT DEMANDE EXAMEN EXTERNE POUR LES EXAMENS 
# ===========================================================================================================     

@login_required
def creer_demande_examen(request, client_id):
    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # 2. Taux de change depuis la configuration de l'hôpital
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # 3. Récupération du client et des prestations
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

    # 4. Traitement du formulaire POST
    if request.method == 'POST':
        form = DemandeExamenExterneForm(request.POST)
        
        if form.is_valid():
            # Étape 1 : Sauvegarder la demande SANS les prestations
            demande = form.save(commit=False)
            demande.client = client
            demande.hopital = user_hopital if fonctionKey != 'admin' else client.hopital
            demande.save()  # ← IMPORTANT : Sauvegarde d'abord pour avoir un ID
            
            # Étape 2 : Récupérer les IDs des prestations sélectionnées
            ids_prestations = request.POST.getlist('prestations')
            
            if fonctionKey != 'admin' and user_hopital:
                prestations_selectionnees = Prestation.objects.filter(
                    id__in=ids_prestations,
                    hopital=user_hopital
                )
            else:
                prestations_selectionnees = Prestation.objects.filter(id__in=ids_prestations)
            
            # Étape 3 : Ajouter les prestations à la demande
            demande.prestations.set(prestations_selectionnees)
            
            # Étape 4 : Calculer et sauvegarder les totaux
            total_cdf = prestations_selectionnees.aggregate(total=Sum('prix'))['total'] or Decimal('0')
            demande.total_cdf = total_cdf
            demande.total_a_payer = (total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            demande.save()
            
            messages.success(request, f"Demande créée avec succès ! Total : {demande.total_a_payer} USD")
            return redirect('liste_demandes_externes')
    else:
        form = DemandeExamenExterneForm()

    # 5. Contexte pour l'affichage (GET)
    return render(request, 'back-end/client/creer_demande.html', {
        'client': client,
        'form': form,
        'fonctionKey': fonctionKey,
        'prestations_labo': prestations_labo,
        'prestations_radio': prestations_radio,
        'prestations_echo': prestations_echo,
        'taux': taux,
        'user_hopital': user_hopital,
    })


# 
# ===========================================================================================================
# LISTE DES PATIENTS EXTERNE POUR LES EXAMENS 
# =========================================================================================================== 

@login_required
def liste_demandes_externes(request):
    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # 2. Taux de change depuis la configuration de l'hôpital
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # 3. Filtrage des demandes selon le rôle
    if fonctionKey != 'admin' and user_hopital:
        demandes_qs = DemandeExamenExterne.objects.filter(hopital=user_hopital).order_by('-date_demande')
    else:
        demandes_qs = DemandeExamenExterne.objects.all().order_by('-date_demande')

    # 4. Construction des données avec totaux, déjà payé et reste à payer
    demandes_data = []

    for demande in demandes_qs:
        # Total en CDF (déjà stocké dans le modèle)
        total_cdf = demande.total_cdf or Decimal('0')
        total_usd = (total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Paiements liés à cette demande
        paiements = demande.paiements.all()

        # Calcul du déjà payé en CDF (la somme est stockée en CDF dans Paiement)
        deja_paye_cdf = Decimal('0')
        
        # Totaux pour le médecin et l'hôpital (en CDF)
        total_medecin_cdf = Decimal('0')
        total_hopital_cdf = Decimal('0')
        
        # Liste des paiements détaillés
        paiements_details = []

        for p in paiements:
            # Le montant est déjà en CDF dans le modèle Paiement
            montant_cdf = p.montant_verse or Decimal('0')
            montant_usd = (montant_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            deja_paye_cdf += montant_cdf

            # Récupérer les montants médecin et hôpital (en CDF)
            montant_medecin = p.montant_medecin or Decimal('0')
            montant_hopital = p.montant_hopital or Decimal('0')
            pourcentage = p.pourcentage_medecin or Decimal('0')

            total_medecin_cdf += montant_medecin
            total_hopital_cdf += montant_hopital

            # Ajouter le détail du paiement
            paiements_details.append({
                'paiement': p,
                'montant_cdf': montant_cdf,
                'montant_usd': montant_usd,
                'pourcentage_medecin': pourcentage,
                'montant_medecin': montant_medecin,
                'montant_hopital': montant_hopital,
            })

        # Reste à payer en CDF
        reste_a_payer_cdf = max(Decimal('0'), total_cdf - deja_paye_cdf)
        reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Statut de paiement
        if reste_a_payer_cdf <= Decimal('1'):
            statut_paiement = 'PAYE'
        elif deja_paye_cdf > Decimal('0'):
            statut_paiement = 'PARTIEL'
        else:
            statut_paiement = 'NON_PAYE'

        demandes_data.append({
            'demande': demande,
            'total_cdf': total_cdf,
            'total_usd': total_usd,
            'deja_paye_cdf': deja_paye_cdf,
            'deja_paye_usd': (deja_paye_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'reste_a_payer_cdf': reste_a_payer_cdf,
            'reste_a_payer_usd': reste_a_payer_usd,
            'statut_paiement': statut_paiement,
            'total_medecin_cdf': total_medecin_cdf,
            'total_hopital_cdf': total_hopital_cdf,
            'total_medecin_usd': (total_medecin_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_hopital_usd': (total_hopital_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'paiements_details': paiements_details,
            'nombre_paiements': paiements.count(),
        })

    return render(request, 'back-end/client/liste_demandes.html', {
        'demandes_data': demandes_data,
        'taux': taux,
        'fonctionKey': fonctionKey
    })



#
# ========================================================================================
# LISTE DE DEMANDE EXTERNE
# ========================================================================================
@login_required
def liste_examens_technicien(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    if not role_obj or not role_obj.fonctionKey or not role_obj.hopital:
        messages.error(request, "Accès refusé.")
        return redirect('dashboard')

    role_name = role_obj.fonctionKey.roleName.upper()
    user_hopital = role_obj.hopital
    nom_role = role_obj.fonctionKey.roleName.lower()

    # Vérifier si c'est un gestionnaire ou admin (peut tout voir)
    est_gestionnaire = 'gestionnaire' in nom_role or 'admin' in nom_role

    cat_cible = None
    if 'LABO' in role_name:
        cat_cible = 'LABO'
    elif 'RADIO' in role_name:
        cat_cible = 'RADIO'
    elif 'ECHO' in role_name:
        cat_cible = 'ECHO'

    # Le gestionnaire/admin n'a pas de catégorie spécifique, il voit tout
    if not cat_cible and not est_gestionnaire:
        messages.error(request, "Accès refusé.")
        return redirect('dashboard')

    # Filtrer par hôpital
    demandes = DemandeExamenExterne.objects.filter(
        hopital=user_hopital
    ).distinct().order_by('-date_demande')

    historique_technique = []

    for dem in demandes:
        # Le gestionnaire voit toutes les catégories, le technicien voit sa catégorie
        if est_gestionnaire:
            examens_filtres = dem.prestations.filter(hopital=user_hopital)
        else:
            examens_filtres = dem.prestations.filter(
                hopital=user_hopital,
                categorie=cat_cible
            )

        if examens_filtres.exists():
            historique_technique.append({
                'id': dem.id,
                'patient': dem.client.noms,
                'date': dem.date_demande,
                'examens': examens_filtres,
                'statut': dem.statut,
                'hopital': dem.hopital.nomH if dem.hopital else 'N/A'
            })

    return render(request, 'back-end/client/liste_examens_technicien.html', {
        'historique_technique': historique_technique,
        'fonctionKey': role_obj.fonctionKey.roleName,
        'cat_cible': cat_cible,
        'est_gestionnaire': est_gestionnaire,
        'hopital_user': user_hopital,
    })
#
# =========================================================================================================
# RESULTAT EXAMEN 
# =========================================================================================================
@login_required
def saisir_rapport(request, demande_id, prestation_id):
    demande = get_object_or_404(DemandeExamenExterne, id=demande_id)
    prestation = get_object_or_404(Prestation, id=prestation_id)
    
    resultat, created = ExamenExterneResultat.objects.get_or_create(
        demande=demande,
        prestation=prestation,
        defaults={'rapport': '', 'statut': 'EN_ATTENTE'}
    )
    
    if request.method == 'POST':
        rapport_texte = request.POST.get('rapport')
        resultat.rapport = rapport_texte
        resultat.statut = 'TERMINE'
        resultat.save()
        return redirect('liste_examens_technicien')
    
    # Récupère le rôle et l'hôpital du user
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None  # ← Ajoute ça

    return render(request, 'back-end/client/saisir_rapport.html', {
        'demande': demande,
        'prestation': prestation,
        'resultat': resultat,
        'fonctionKey': fonctionKey,
        'user_hopital': user_hopital,  # ← Ajoute ça
    })

#
# ========================================================================================================
# HISTORIQUE DES RESULTATS EXTERNE 
# ========================================================================================================
@login_required
def historique_examen_externe_technicien(request):
    try:
        # Récupère le rôle de l'utilisateur
        role_obj = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
        
        if not role_obj or not role_obj.fonctionKey or not role_obj.hopital:
            messages.error(request, "Accès refusé.")
            return redirect('dashboard')

        role_name = role_obj.fonctionKey.roleName.upper()
        user_hopital = role_obj.hopital  # ← Hôpital du user connecté
        nom_role = role_obj.fonctionKey.roleName.lower()

        # Vérifier si c'est un gestionnaire ou admin (peut tout voir)
        est_gestionnaire = 'gestionnaire' in nom_role or 'admin' in nom_role

        is_medecin = 'MEDECIN' in role_name or 'DOCTEUR' in role_name

        cat_cible = None
        if 'LABO' in role_name:
            cat_cible = 'LABO'
        elif 'RADIO' in role_name:
            cat_cible = 'RADIO'
        elif 'ECHO' in role_name:
            cat_cible = 'ECHO'

        # Requête filtrée par l'hôpital du user connecté
        if is_medecin or est_gestionnaire:
            # Le médecin et le gestionnaire voient tout de leur hôpital
            demandes = DemandeExamenExterne.objects.filter(
                hopital=user_hopital  # ← Seulement l'hôpital du user
            ).select_related('client').order_by('-date_demande')
        elif cat_cible:
            demandes = DemandeExamenExterne.objects.filter(
                hopital=user_hopital,  # ← Seulement l'hôpital du user
                prestations__categorie=cat_cible
            ).select_related('client').distinct().order_by('-date_demande')
        else:
            messages.error(request, "Accès non autorisé pour ce profil.")
            return redirect('dashboard')

        historique_technique = []

        for dem in demandes:
            # Récupère les prestations
            tous_les_examens = dem.prestations.filter(hopital=user_hopital)

            # Récupère les résultats
            resultats = dem.resultats_examens.all()
            resultats_dict = {res.prestation_id: res for res in resultats}

            details_examens = []
            for p in tous_les_examens:
                res = resultats_dict.get(p.id)

                # Le gestionnaire voit tout, le technicien voit sa catégorie
                est_ma_categorie = est_gestionnaire or is_medecin or (p.categorie == cat_cible)

                details_examens.append({
                    'prestation': p,
                    'statut': res.statut if res else 'EN_ATTENTE',
                    'id_resultat': res.id if res else None,
                    'rapport': res.rapport if res else None,
                    'est_ma_categorie': est_ma_categorie
                })

            historique_technique.append({
                'id': dem.id,
                'client': dem.client,
                'patient': dem.client.noms if dem.client else "Inconnu",
                'date': dem.date_demande,
                'details': details_examens,
                'medecin_demandeur': dem.medecin_demandeur or "Non spécifié",
                'type_urgence': getattr(dem, 'urgence', 'Standard'),
                'hopital': dem.hopital.nomH if dem.hopital else 'N/A'
            })

        return render(request, 'back-end/client/historique_examen_externe_technicien.html', {
            'historique_technique': historique_technique,
            'fonctionKey': role_obj.fonctionKey.roleName,
            'is_medecin': is_medecin,
            'cat_cible': cat_cible,
            'hopital_user': user_hopital,  # ← Ajoute ça pour afficher dans le template
            'est_gestionnaire': est_gestionnaire,
        })
        
    except Exception as e:
        # En cas d'erreur, affiche un message
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('dashboard')
# 
# ==================================================================================
# PAIEMENT DES L'EXAMEN EXTERNE
# ==================================================================================
@login_required
def encaisser_examen_externe(request, demande_id):
    # 1. Rôle et hôpital de l'utilisateur
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # 2. Récupération de la demande
    if fonctionKey != 'admin' and user_hopital:
        demande = get_object_or_404(
            DemandeExamenExterne,
            id=demande_id,
            hopital=user_hopital
        )
    else:
        demande = get_object_or_404(DemandeExamenExterne, id=demande_id)

    client = demande.client

    # 3. Taux de change depuis la configuration de l'hôpital
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # 4. Calcul du reste à payer (en CDF)
    total_due_cdf = (demande.total_a_payer * taux).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

    # Paiements existants
    paiements = demande.paiements.all()
    total_deja_verse_cdf = Decimal('0')
    total_deja_reduit_cdf = Decimal('0')

    for p in paiements:
        if p.devise == 'CDF':
            total_deja_verse_cdf += p.montant_verse or Decimal('0')
            total_deja_reduit_cdf += p.montant_reduction or Decimal('0')
        else:  # USD
            total_deja_verse_cdf += (p.montant_verse or Decimal('0')) * taux
            total_deja_reduit_cdf += (p.montant_reduction or Decimal('0')) * taux

    reste_a_payer_cdf = max(
        Decimal('0'),
        total_due_cdf - (total_deja_verse_cdf + total_deja_reduit_cdf)
    )
    reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 5. Traitement du formulaire POST
    if request.method == 'POST':
        devise = request.POST.get('devise', 'CDF')
        montant_total_patient = Decimal(request.POST.get('montant_verse', '0') or '0')  # Montant TOTAL payé par le patient
        reduction = Decimal(request.POST.get('montant_reduction', '0') or '0')
        
        # NOUVEAU : Récupérer le pourcentage du médecin
        pourcentage_medecin = Decimal(request.POST.get('pourcentage_medecin', '0') or '0')

        # Validation du pourcentage (0-100%)
        if pourcentage_medecin < 0 or pourcentage_medecin > 100:
            messages.error(request, "Le pourcentage doit être entre 0 et 100.")
            return redirect('encaisser_examen_externe', demande_id=demande.id)

        # Vérification : montant > 0
        if montant_total_patient <= 0:
            messages.error(request, "Le montant à payer doit être supérieur à 0.")
            return redirect('encaisser_examen_externe', demande_id=demande.id)

        # Conversion du montant saisi en CDF
        if devise == 'CDF':
            montant_total_patient_cdf = montant_total_patient
        else:  # USD
            montant_total_patient_cdf = montant_total_patient * taux

        # Vérifier si le montant dépasse le reste à payer (avec tolérance)
        tolerance_cdf = Decimal('1')
        if montant_total_patient_cdf > (reste_a_payer_cdf + tolerance_cdf):
            messages.error(
                request,
                f"Le montant dépasse le reste à payer "
                f"({reste_a_payer_cdf:.0f} CDF / {reste_a_payer_usd:.2f} USD)."
            )
            return redirect('encaisser_examen_externe', demande_id=demande.id)

        # NOUVEAU : Calcul des montants médecin et hôpital
        montant_net = montant_total_patient - reduction  # Montant net après réduction
        
        # Calcul du pourcentage pour le médecin
        montant_pour_medecin = (montant_net * pourcentage_medecin / 100).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )
        
        # Montant pour l'hôpital (CAISSE) = montant net - part médecin
        montant_pour_hopital = (montant_net - montant_pour_medecin).quantize(
            Decimal('0.01'), 
            rounding=ROUND_HALF_UP
        )

        # IMPORTANT : montant_verse = montant pour la CAISSE (90 USD), pas le total (100 USD)
        Paiement.objects.create(
            demande_examen_externe=demande,
            clientEx=client,
            service='EXAMEN_EXTERNE',
            montant_verse=montant_pour_hopital,  # ← SEULEMENT ce qui va à la caisse (90 USD)
            montant_reduction=reduction,
            pourcentage_medecin=pourcentage_medecin,
            montant_medecin=montant_pour_medecin,  # ← Part du médecin (10 USD)
            montant_hopital=montant_pour_hopital,  # ← Part de la caisse (90 USD)
            caissier=request.user,
            devise=devise,
            hopital=user_hopital if fonctionKey != 'admin' else demande.hopital
        )

        # Nouveau reste à payer (pour message)
        # On soustrait le montant TOTAL (médecin + caisse) du reste à payer
        nouveau_reste_cdf = reste_a_payer_cdf - montant_total_patient_cdf
        if nouveau_reste_cdf <= Decimal('1'):
            messages.success(
                request,
                f"Paiement enregistré. La demande de {client.noms} est soldée. "
                f"Répartition : Médecin ({demande.medecin_demandeur}) = {montant_pour_medecin} {devise}, "
                f"Caisse = {montant_pour_hopital} {devise}"
            )
            return redirect('liste_demandes_externes')
        else:
            nouveau_reste_usd = (nouveau_reste_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            messages.success(
                request,
                f"Paiement enregistré. Reste à payer : {nouveau_reste_cdf:.0f} CDF "
                f"(~ {nouveau_reste_usd:.2f} USD)."
            )
            return redirect('encaisser_examen_externe', demande_id=demande.id)

    # 6. Contexte pour l'affichage (GET)
    return render(request, 'back-end/client/encaisser_examen.html', {
        'demande': demande,
        'client': client,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'prestations': demande.prestations.all(),
    })

# ==========================================================================================
# IMPRIMER FACTURE EXAMEN EXTERNE
# ===========================================================================================
@login_required
def imprimer_facture_examen_externe(request, demande_id):
    """Vue pour afficher la facture à imprimer"""
    demande = get_object_or_404(DemandeExamenExterne, id=demande_id)
    
    # Vérifier les permissions
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None
    
    if fonctionKey != 'admin' and user_hopital and demande.hopital != user_hopital:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})
    
    # Récupérer le taux
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')
    
    # Récupérer tous les paiements
    paiements = demande.paiements.all()
    
    # Calculer les totaux
    total_medecin_cdf = Decimal('0')
    total_hopital_cdf = Decimal('0')
    total_general_cdf = Decimal('0')
    
    paiements_details = []
    
    for p in paiements:
        montant_cdf = p.montant_verse or Decimal('0')
        montant_medecin = p.montant_medecin or Decimal('0')
        montant_hopital = p.montant_hopital or Decimal('0')
        pourcentage = p.pourcentage_medecin or Decimal('0')
        
        total_medecin_cdf += montant_medecin
        total_hopital_cdf += montant_hopital
        total_general_cdf += montant_cdf
        
        paiements_details.append({
            'paiement': p,
            'montant_cdf': montant_cdf,
            'montant_medecin': montant_medecin,
            'montant_hopital': montant_hopital,
            'pourcentage': pourcentage,
            'date': p.date_paiement,
            'caissier': p.caissier,
        })
    
    return render(request, 'back-end/client/imprimer_facture_examen.html', {
        'demande': demande,
        'taux': taux,
        'paiements': paiements_details,
        'total_medecin_cdf': total_medecin_cdf,
        'total_hopital_cdf': total_hopital_cdf,
        'total_general_cdf': total_general_cdf,
    })

#
# ======================================================================================
# LISTE DE FACTURATION 
# ======================================================================================
@login_required
def liste_facturation(request):
    # 1. Rôle et hôpital de l’utilisateur
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # 2. Taux de change depuis la configuration de l’hôpital
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')  # 1 USD = taux CDF
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # 3. Filtrage des demandes selon le rôle
    demandes_qs = DemandeExamenExterne.objects.all()

    if fonctionKey != 'admin' and user_hopital:
        demandes_qs = demandes_qs.filter(hopital=user_hopital)

    # 4. On prefetch les paiements pour calculer le déjà payé en Python (plus simple pour gérer CDF/USD)
    demandes_qs = demandes_qs.prefetch_related(
        'prestations',
        'paiements'
    ).order_by('-date_demande')

    demandes_data = []

    for demande in demandes_qs:
        # Total en CDF et USD
        total_cdf = demande.total_cdf or Decimal('0')
        total_usd = demande.total_a_payer or Decimal('0')

        # Calcul du déjà payé en CDF
        deja_paye_cdf = Decimal('0')
        for p in demande.paiements.all():
            if p.devise == 'CDF':
                deja_paye_cdf += p.montant_verse or Decimal('0')
            else:  # USD
                deja_paye_cdf += (p.montant_verse or Decimal('0')) * taux

        # Reste à payer en CDF
        reste_a_payer_cdf = max(Decimal('0'), total_cdf - deja_paye_cdf)
        reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        demandes_data.append({
            'demande': demande,
            'total_cdf': total_cdf,
            'total_usd': total_usd,
            'deja_paye_cdf': deja_paye_cdf,
            'deja_paye_usd': (deja_paye_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'reste_a_payer_cdf': reste_a_payer_cdf,
            'reste_a_payer_usd': reste_a_payer_usd,
        })

    return render(request, 'back-end/client/liste_facturation.html', {
        'demandes_data': demandes_data,
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

    # Taux de change
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')  # 1 USD = taux CDF
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # Paiements liés à cette demande
    paiements = demande.paiements.all()

    # Calcul du déjà payé en CDF
    deja_paye_cdf = Decimal('0')
    for p in paiements:
        if p.devise == 'CDF':
            deja_paye_cdf += p.montant_verse or Decimal('0')
        else:  # USD
            deja_paye_cdf += (p.montant_verse or Decimal('0')) * taux

    # Total et reste à payer
    total_cdf = demande.total_cdf or Decimal('0')
    reste_a_payer_cdf = max(Decimal('0'), total_cdf - deja_paye_cdf)
    reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Résultats (si tu as un related_name 'resultats_examens' sur DemandeExamenExterne)
    resultats = demande.resultats_examens.all() if hasattr(demande, 'resultats_examens') else []

    return render(request, 'back-end/client/imprimer_rapport.html', {
        'demande': demande,
        'paiements': paiements,
        'resultats': resultats,
        'total_cdf': total_cdf,
        'total_usd': demande.total_a_payer,
        'deja_paye_cdf': deja_paye_cdf,
        'deja_paye_usd': (deja_paye_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'reste_a_payer_usd': reste_a_payer_usd,
        'taux': taux,
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
        Ordonnance.objects.select_related('consultation'),
        id=pk
    )

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Mise à jour des champs de l'ordonnance
                type_val = request.POST.get('type_ordonnance')
                if type_val:
                    ordonnance.type_ordonnance = type_val

                ordonnance.observation = request.POST.get('observation', '')
                ordonnance.save()

                # Supprime les anciennes lignes de médicaments
                ordonnance.lignes_medicaments.all().delete()

                # Récupère les nouvelles lignes
                noms = request.POST.getlist('nom_medicament[]')
                posologies = request.POST.getlist('posologie[]')
                durees = request.POST.getlist('duree[]')
                quantites = request.POST.getlist('quantite[]')

                for i, nom in enumerate(noms):
                    if nom and nom.strip():
                        poso = posologies[i].strip() if i < len(posologies) and posologies[i] else ''
                        dur = durees[i].strip() if i < len(durees) and durees[i] else ''

                        # Gestion de la quantité (peut être vide)
                        qte = None
                        if i < len(quantites) and quantites[i]:
                            qte_val = quantites[i].strip()
                            if qte_val:
                                try:
                                    qte = int(qte_val)
                                except ValueError:
                                    qte = None

                        LigneMedicament.objects.create(
                            ordonnance=ordonnance,
                            nom_medicament=nom.strip(),
                            posologie=poso,
                            duree=dur,
                            quantite=qte,  # ← quantité ajoutée
                            statut='EN_COURS',
                            hopital=ordonnance.hopital
                        )

            messages.success(request, "Ordonnance mise à jour avec succès.")
            return redirect('liste_ordonnances_urgence')

        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour : {str(e)}")

    role = Fonction.objects.filter(userKey=request.user).first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    return render(request, 'back-end/medecin/modifier_ordonnance_urgence.html', {
        'ord': ordonnance,
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
    # 1. Rôle et hôpital de l’utilisateur
    role = (
        Fonction.objects
        .select_related('hopital', 'fonctionKey')
        .filter(userKey=request.user)
        .first()
    )
    hopital_user = role.hopital if role else None

    if not hopital_user:
        messages.error(request, "Votre compte n'est rattaché à aucun hôpital.")
        return redirect('enregistrement_patient')

    entreprise = get_object_or_404(Entreprise, id=entreprise_id, hopital=hopital_user)

    # 2. Taux de change
    taux = ConfigurationHopital.get_taux()  # 1 USD = taux CDF

    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None

    # 3. Paiements existants pour cette entreprise (service = ENTREPRISE)
    paiements_existants = Paiement.objects.filter(
        entreprise=entreprise,
        service='ENTREPRISE',
        hopital=hopital_user
    ).order_by('-date_paiement')

    total_deja_paye_cdf = Decimal('0')
    for p in paiements_existants:
        if p.devise == 'CDF':
            total_deja_paye_cdf += p.montant_verse or Decimal('0')
        else:  # USD
            total_deja_paye_cdf += (p.montant_verse or Decimal('0')) * taux

    # 4. Calcul de la dette totale de l’entreprise (en CDF)
    # Tous les patients conventionnés de cette entreprise, dans cet hôpital
    patients_conventionnes = Patient.objects.filter(
        entreprise=entreprise,
        type_patient='CONVENTIONNE',
        hopital=hopital_user
    )

    # Toutes les consultations de ces patients
    consultations_qs = Consultation.objects.filter(
        triage__patient__in=patients_conventionnes
    ).select_related('triage__patient').prefetch_related('examens__prestation')

    dette_cdf = Decimal('0')
    for c in consultations_qs:
        total_examens_cdf = c.examens.aggregate(
            total=Coalesce(
                Sum(F('prestation__prix') * F('quantite')),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=15, decimal_places=2))
            )
        )['total'] or Decimal('0')
        dette_cdf += total_examens_cdf

    dette_usd = (dette_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 5. Reste à payer
    reste_a_payer_cdf = max(Decimal('0'), dette_cdf - total_deja_paye_cdf)
    reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 6. Traitement du formulaire de paiement
    if request.method == 'POST':
        montant_saisi = Decimal(request.POST.get('montant', '0') or '0')
        devise = request.POST.get('devise', 'CDF')  # par défaut CDF
        reduction = Decimal(request.POST.get('reduction', '0') or '0')

        # Convertir le montant saisi en CDF
        if devise == 'CDF':
            montant_saisi_cdf = montant_saisi
        else:  # USD
            montant_saisi_cdf = montant_saisi * taux

        # Vérifier si le montant dépasse le reste à payer (avec tolérance)
        tolerance_cdf = Decimal('1')
        if montant_saisi_cdf > (reste_a_payer_cdf + tolerance_cdf):
            messages.error(
                request,
                f"Le montant dépasse le reste à payer "
                f"({reste_a_payer_cdf:.0f} CDF / {reste_a_payer_usd:.2f} USD)."
            )
            return redirect('payer_dette_entreprise', entreprise_id=entreprise.id)

        if montant_saisi_cdf > 0:
            # Créer le paiement
            Paiement.objects.create(
                entreprise=entreprise,
                service='ENTREPRISE',
                montant_verse=montant_saisi,
                montant_reduction=reduction,
                devise=devise,
                caissier=request.user,
                hopital=hopital_user,
            )

            nouveau_total_cdf = total_deja_paye_cdf + montant_saisi_cdf
            nouveau_reste_cdf = dette_cdf - nouveau_total_cdf

            if nouveau_reste_cdf <= Decimal('1'):  # tolérance 1 CDF
                messages.success(
                    request,
                    f"Paiement terminé. La dette de {entreprise.nom} est soldée."
                )
                return redirect('liste_entreprises')  # ou une autre vue adaptée
            else:
                nouveau_reste_usd = (nouveau_reste_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                messages.success(
                    request,
                    f"Paiement enregistré. Reste à payer : {nouveau_reste_cdf:.0f} CDF "
                    f"(~ {nouveau_reste_usd:.2f} USD)."
                )
                return redirect('payer_dette_entreprise', entreprise_id=entreprise.id)

    # 7. Contexte pour l’affichage (GET)
    return render(request, 'back-end/entreprise/payer_dette.html', {
        'entreprise': entreprise,
        'dette_usd': dette_usd,
        'dette_cdf': dette_cdf,
        'reste_a_payer': reste_a_payer_usd,
        'reste_a_payer_cdf': reste_a_payer_cdf,
        'total_deja_paye_cdf': total_deja_paye_cdf,
        'taux': taux,
        'fonctionKey': fonctionKey,
        'paiements': paiements_existants,
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
@login_required
def liste_patients_fideles(request):
    # 1. Rôle et hôpital de l’utilisateur
    role = (
        Fonction.objects
        .filter(userKey=request.user)
        .select_related('fonctionKey', 'hopital')
        .first()
    )
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None

    # 2. Taux de change depuis la configuration de l’hôpital
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config else Decimal('2300.00')  # 1 USD = taux CDF
    if not taux or taux == 0:
        taux = Decimal('2300.00')

    # 3. Traitement du formulaire POST (paiement)
    if request.method == 'POST':
        try:
            consultation_id = request.POST.get('consultation_id')
            montant_verse = Decimal(request.POST.get('montant', '0') or '0')
            reduction = Decimal(request.POST.get('reduction', '0') or '0')
            devise = request.POST.get('devise', 'CDF')

            cons = get_object_or_404(Consultation, id=consultation_id)

            # Vérification hôpital
            if fonctionKey != 'admin' and user_hopital and cons.hopital != user_hopital:
                messages.error(request, "Accès refusé.")
                return redirect('liste_patients_fideles')

            # Calcul du montant total des examens (en CDF, comme dans payer_fiche)
            montant_total_cdf = Decimal('0')
            for ex in cons.examens.all():
                if ex.prestation and ex.prestation.prix:
                    montant_total_cdf += ex.prestation.prix * (ex.quantite or 1)

            # Calcul des paiements existants (en CDF)
            totaux = cons.paiements.aggregate(
                paye=Sum('montant_verse'),
                remise=Sum('montant_reduction')
            )
            paye_usd = totaux['paye'] or Decimal('0')
            remise_usd = totaux['remise'] or Decimal('0')

            # On suppose que les paiements sont stockés en USD dans ta base
            # et on les convertit en CDF pour comparer
            paye_cdf = paye_usd * taux
            remise_cdf = remise_usd * taux  # si remise est aussi en USD

            reste_a_payer_cdf = max(Decimal('0'), montant_total_cdf - (paye_cdf + remise_cdf))

            # Conversion du montant saisi en CDF
            if devise == 'CDF':
                montant_saisi_cdf = montant_verse
            else:  # USD
                montant_saisi_cdf = montant_verse * taux

            # Vérification : montant > 0
            if montant_saisi_cdf <= 0:
                messages.error(request, "Le montant à payer doit être supérieur à 0.")
                return redirect('liste_patients_fideles')

            # Vérification : montant ne dépasse pas le reste (avec tolérance)
            tolerance_cdf = Decimal('1')
            if montant_saisi_cdf > (reste_a_payer_cdf + tolerance_cdf):
                messages.error(
                    request,
                    f"Le montant dépasse le reste à payer "
                    f"({reste_a_payer_cdf:.0f} CDF / {(reste_a_payer_cdf / taux):.2f} USD)."
                )
                return redirect('liste_patients_fideles')

            # Création du paiement (on stocke en USD comme avant)
            if devise == 'CDF':
                montant_en_usd = (montant_verse / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                montant_en_usd = montant_verse

            Paiement.objects.create(
                consultation=cons,
                patient=cons.triage.patient,
                service='CONSULTATION',
                montant_verse=montant_en_usd,
                montant_reduction=reduction,
                devise=devise,
                date_paiement=timezone.now(),
                caissier=request.user,
                hopital=user_hopital,
            )

            nouveau_reste_cdf = reste_a_payer_cdf - montant_saisi_cdf

            if nouveau_reste_cdf <= Decimal('1'):
                messages.success(
                    request,
                    f"Paiement terminé. La consultation de {cons.triage.patient.noms} est soldée."
                )
            else:
                nouveau_reste_usd = (nouveau_reste_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                messages.success(
                    request,
                    f"Paiement enregistré. Reste à payer : {nouveau_reste_cdf:.0f} CDF "
                    f"(~ {nouveau_reste_usd:.2f} USD)."
                )

            return redirect('liste_patients_fideles')

        except Exception as e:
            messages.error(request, f"Erreur lors du paiement : {e}")
            return redirect('liste_patients_fideles')

    # 4. Préparation des données pour l’affichage (GET)
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

        # Montant total des examens (en CDF)
        montant_total_cdf = Decimal('0')
        for ex in cons.examens.all():
            if ex.prestation and ex.prestation.prix:
                montant_total_cdf += ex.prestation.prix * (ex.quantite or 1)

        # Totaux paiements + remise (en USD, convertis en CDF)
        totaux = cons.paiements.aggregate(
            paye=Sum('montant_verse'),
            remise=Sum('montant_reduction')
        )
        paye_usd = totaux['paye'] or Decimal('0')
        remise_usd = totaux['remise'] or Decimal('0')

        paye_cdf = paye_usd * taux
        remise_cdf = remise_usd * taux

        reste_a_payer_cdf = max(Decimal('0'), montant_total_cdf - (paye_cdf + remise_cdf))
        reste_a_payer_usd = (reste_a_payer_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        patients_data.append({
            'consultation_id': cons.id,
            'patient': patient,
            'montant_total': montant_total_cdf,      # en CDF
            'montant_total_usd': (montant_total_cdf / taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'reste_a_payer': reste_a_payer_usd,      # en USD (pour affichage)
            'reste_a_payer_cdf': reste_a_payer_cdf,  # en CDF (pour affichage)
        })

    return render(request, 'back-end/patient/liste_fideles.html', {
        'patients_data': patients_data,
        'mois': mois,
        'annee': annee,
        'taux': taux,
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

    # Récupération du client externe
    client = get_object_or_404(ClientExterne, id=client_id)

    # Vérifier que le client appartient au même hôpital
    if user_hopital and hasattr(client, 'hopital') and client.hopital and client.hopital != user_hopital and fonctionKey != 'admin':
        return render(request, 'back-end/error.html', {'message': "Accès refusé : client hors de votre hôpital."})

    if request.method == 'POST':
        try:
            with transaction.atomic():
                ordonnance = OrdonnanceExterne.objects.create(
                    client=client,
                    medecin=request.user,
                    hopital=user_hopital if fonctionKey != 'admin' else client.hopital,  # ← IMPORTANT
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
                        quantite=quantites[i].strip() if i < len(quantites) else "",
                        hopital=user_hopital if fonctionKey != 'admin' else client.hopital  # ← Ajoute ça aussi
                    )

            messages.success(request, f"Ordonnance enregistrée pour {client.noms}.")
            return redirect('liste_ordonnances_externes_client')

        except Exception as e:
            messages.error(request, f"Une erreur est survenue lors de l'enregistrement : {e}")
            return render(request, 'back-end/client/prescrire_ordonnance_client_externe.html', {
                'client': client, 
                'fonctionKey': fonctionKey
            })

    # GET : affichage
    return render(request, 'back-end/client/prescrire_ordonnance_client_externe.html', {
        'client': client,
        'fonctionKey': fonctionKey,
        'user_hopital': user_hopital,
    })
# ==========================================================================================================
# imprimer ordonnance externe
# ==========================================================================================================
@login_required
def imprimer_ordonnance_externe(request, ordonnance_id):
    """Vue pour afficher l'ordonnance à imprimer"""
    ordonnance = get_object_or_404(OrdonnanceExterne, id=ordonnance_id)
    
    # Vérifier les permissions
    role = Fonction.objects.filter(userKey=request.user).select_related('fonctionKey', 'hopital').first()
    fonctionKey = role.fonctionKey.roleName if role and role.fonctionKey else None
    user_hopital = role.hopital if role else None
    
    if fonctionKey != 'admin' and user_hopital and ordonnance.hopital != user_hopital:
        return render(request, 'back-end/error.html', {'message': "Accès refusé."})
    
    return render(request, 'back-end/client/imprimer_ordonnance.html', {
        'ordonnance': ordonnance,
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

    # Calcul des statistiques
    today = datetime.now().date()
    total = ordonnances.count()
    actives = total
    aujourd_hui = ordonnances.filter(date_creation__date=today).count()

    return render(request, 'back-end/client/liste_ordonnances_client.html', {
        'ordonnances': ordonnances,
        'fonctionKey': fonction_key,
        'total': total,
        'actives': actives,
        'aujourd_hui': aujourd_hui,
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
    hopital_selectionne = None
    filtre_actif = False
    
    # 1. Admin global ou super_admin peut tout voir OU filtrer
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        if hopital_id:
            # Admin a choisi un hôpital spécifique
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
            filtre_actif = True
        else:
            # Admin n'a pas filtré → voit TOUS les hôpitaux (None = pas de filtre)
            hopital_selectionne = None
            filtre_actif = False
    
    # 2. Pharmacien, admin_pharmacie, responsable_stock → limité à son hôpital
    elif fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # 3. Autres utilisateurs → hôpital par défaut
    else:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # --- BASE QUERYSET ---
    if hopital_selectionne:
        produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
        lots = LotPharmacie.objects.filter(hopital=hopital_selectionne)
        sorties = SortiePharmacie.objects.filter(hopital=hopital_selectionne)
        mouvements = MouvementStock.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin voit TOUS les hôpitaux
        produits = ProduitPharmacie.objects.all()
        lots = LotPharmacie.objects.all()
        sorties = SortiePharmacie.objects.all()
        mouvements = MouvementStock.objects.all()
    
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
    
    # --- TAUX DE CHANGE PAR DÉFAUT : 2500 CDF = 1 USD ---
    # Si l'hôpital a une config, on prend son taux, sinon 2500 CDF
    taux_change = 2500  # Taux par défaut : 1 USD = 2500 CDF
    
    if hopital_selectionne:
        try:
            config = ConfigurationHopital.objects.filter(hopital=hopital_selectionne).first()
            if config and hasattr(config, 'taux'):
                taux_change = config.taux
        except:
            pass
    
    # --- CALCULS : TOUT EN CDF PAR DÉFAUT, PUIS CONVERSION USD ---
    stock_total = 0
    valeur_stock_achat_cdf = 0
    valeur_stock_vente_cdf = 0
    valeur_stock_achat_usd = 0
    valeur_stock_vente_usd = 0
    
    for produit in produits:
        entrees = LotPharmacie.objects.filter(
            produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_initiale'), 0))['total'] or 0
        
        sorties_prod = SortiePharmacie.objects.filter(
            lot__produit=produit
        ).aggregate(total=Coalesce(Sum('quantite_vendue'), 0))['total'] or 0
        
        stock = entrees - sorties_prod
        stock_total += stock
        
        # Prix du produit
        prix_achat = float(produit.prix_achat_unitaire) if produit.prix_achat_unitaire else 0
        prix_vente = float(produit.prix_vente_unitaire) if produit.prix_vente_unitaire else 0
        devise_produit = produit.devise if produit.devise else 'CDF'  # CDF par défaut
        
        # Si le produit est en CDF
        if devise_produit == 'CDF':
            valeur_stock_achat_cdf += stock * prix_achat
            valeur_stock_vente_cdf += stock * prix_vente
            
            # Conversion en USD pour affichage
            valeur_stock_achat_usd += (stock * prix_achat) / taux_change
            valeur_stock_vente_usd += (stock * prix_vente) / taux_change
        
        # Si le produit est en USD
        else:
            valeur_stock_achat_usd += stock * prix_achat
            valeur_stock_vente_usd += stock * prix_vente
            
            # Conversion en CDF pour affichage
            valeur_stock_achat_cdf += (stock * prix_achat) * taux_change
            valeur_stock_vente_cdf += (stock * prix_vente) * taux_change
    
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
            devise_produit = produit.devise if produit.devise else 'CDF'
            
            # Calcul du chiffre d'affaire dans la devise du produit
            if devise_produit == 'CDF':
                chiffre = quantite_vendue * prix_vente
                chiffre_usd = chiffre / taux_change
            else:
                chiffre_usd = quantite_vendue * prix_vente
                chiffre = chiffre_usd * taux_change
            
            top_ventes.append({
                'produit': produit,
                'quantite_vendue': quantite_vendue,
                'chiffre_affaire': round(chiffre, 2),
                'chiffre_affaire_usd': round(chiffre_usd, 2),
                'devise': devise_produit
            })
    
    top_ventes = sorted(top_ventes, key=lambda x: x['quantite_vendue'], reverse=True)[:10]
    
    # --- BÉNÉFICE RÉALISÉ (VENTES EFFECTIVES) ---
    benefice_realise_usd = 0
    benefice_realise_cdf = 0
    chiffre_affaire_total_usd = 0
    chiffre_affaire_total_cdf = 0
    
    for sortie in sorties:
        prix_achat = float(sortie.lot.produit.prix_achat_unitaire) if sortie.lot.produit.prix_achat_unitaire else 0
        prix_vente = float(sortie.lot.produit.prix_vente_unitaire) if sortie.lot.produit.prix_vente_unitaire else 0
        devise_produit = sortie.lot.produit.devise if sortie.lot.produit.devise else 'CDF'
        
        benefice = (prix_vente - prix_achat) * sortie.quantite_vendue
        chiffre = prix_vente * sortie.quantite_vendue
        
        if devise_produit == 'CDF':
            benefice_realise_cdf += benefice
            chiffre_affaire_total_cdf += chiffre
            
            # Conversion USD
            benefice_realise_usd += benefice / taux_change
            chiffre_affaire_total_usd += chiffre / taux_change
        else:
            benefice_realise_usd += benefice
            chiffre_affaire_total_usd += chiffre
            
            # Conversion CDF
            benefice_realise_cdf += benefice * taux_change
            chiffre_affaire_total_cdf += chiffre * taux_change
    
    # Liste des hôpitaux pour le filtre
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'filtre_actif': filtre_actif,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'total_produits': total_produits,
        'total_lots': total_lots,
        'total_sorties': total_sorties,
        'stock_total': stock_total,
        'taux_change': taux_change,  # Taux utilisé pour les conversions
        # Valeurs principales (devise du produit)
        'valeur_stock_achat_usd': round(valeur_stock_achat_usd, 2),
        'valeur_stock_vente_usd': round(valeur_stock_vente_usd, 2),
        'benefice_potentiel_usd': round(benefice_potentiel_usd, 2),
        'benefice_realise_usd': round(benefice_realise_usd, 2),
        'chiffre_affaire_total_usd': round(chiffre_affaire_total_usd, 2),
        'valeur_stock_achat_cdf': round(valeur_stock_achat_cdf, 2),
        'valeur_stock_vente_cdf': round(valeur_stock_vente_cdf, 2),
        'benefice_potentiel_cdf': round(benefice_potentiel_cdf, 2),
        'benefice_realise_cdf': round(benefice_realise_cdf, 2),
        'chiffre_affaire_total_cdf': round(chiffre_affaire_total_cdf, 2),
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    type_mouvement = request.GET.get('type_mouvement')
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
    hopital_selectionne = None
    filtre_actif = False
    
    # 1. Admin global ou super_admin peut tout voir OU filtrer
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        if hopital_id:
            # Admin a choisi un hôpital spécifique
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
            filtre_actif = True
        else:
            # Admin n'a pas filtré → voit TOUS les hôpitaux (None = pas de filtre)
            hopital_selectionne = None
            filtre_actif = False
    
    # 2. Pharmacien, admin_pharmacie, responsable_stock → limité à son hôpital
    elif fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # 3. Autres utilisateurs → hôpital par défaut
    else:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # --- PRODUIT SPÉCIFIQUE OU TOUS ---
    produit = None
    
    if produit_id:
        # Si un produit est demandé
        if hopital_selectionne:
            # Utilisateur non-admin ou admin avec filtre → produit de cet hôpital
            try:
                produit = ProduitPharmacie.objects.get(pk=produit_id, hopital=hopital_selectionne)
                mouvements = MouvementStock.objects.filter(lot__produit=produit)
            except ProduitPharmacie.DoesNotExist:
                messages.error(request, "Le produit demandé n'existe pas ou n'appartient pas à cet hôpital.")
                return redirect('admin_historique_stock')
        else:
            # Admin sans filtre → peut voir n'importe quel produit
            try:
                produit = ProduitPharmacie.objects.get(pk=produit_id)
                mouvements = MouvementStock.objects.filter(lot__produit=produit)
            except ProduitPharmacie.DoesNotExist:
                messages.error(request, "Le produit demandé n'existe pas.")
                return redirect('admin_historique_stock')
    else:
        # Tous les mouvements
        mouvements = MouvementStock.objects.all()
    
    # --- FILTRES ---
    if hopital_selectionne:
        mouvements = mouvements.filter(hopital=hopital_selectionne)
    
    if date_debut:
        mouvements = mouvements.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        mouvements = mouvements.filter(date_mouvement__lte=date_fin)
    
    if type_mouvement:
        mouvements = mouvements.filter(type_mouvement=type_mouvement)
    
    # --- TRI ET OPTIMISATION ---
    mouvements = mouvements.select_related(
        'lot', 
        'lot__produit', 
        'effectue_par',
        'lot__produit__hopital'
    ).order_by('-date_mouvement')
    
    # --- PAGINATION (10 par page) ---
    paginator = Paginator(mouvements, 10)
    page_number = request.GET.get('page')
    mouvements_page = paginator.get_page(page_number)
    
    # --- CALCUL DES TOTAUX PAR PRODUIT ---
    resume_par_produit = {}
    for mouvement in mouvements_page:  # Utiliser la page paginée
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
    
    # --- LISTE DES HÔPITAUX POUR LE FILTRE ---
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    context = {
        'produit': produit,
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'filtre_actif': filtre_actif,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'type_mouvement': type_mouvement,
        'mouvements': mouvements_page,  # Paginé
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    mois = request.GET.get('mois')
    annee = request.GET.get('annee', timezone.now().year)
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
    hopital_selectionne = None
    filtre_actif = False
    
    # 1. Admin global ou super_admin peut tout voir OU filtrer
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        if hopital_id:
            # Admin a choisi un hôpital spécifique
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
            filtre_actif = True
        else:
            # Admin n'a pas filtré → voit TOUS les hôpitaux (None = pas de filtre)
            hopital_selectionne = None
            filtre_actif = False
    
    # 2. Pharmacien, admin_pharmacie, responsable_stock → limité à son hôpital
    elif fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # 3. Autres utilisateurs → hôpital par défaut
    else:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # --- TAUX DE CHANGE PAR DÉFAUT : 2500 CDF = 1 USD ---
    taux_change = 2500  # Taux par défaut : 1 USD = 2500 CDF
    
    if hopital_selectionne:
        try:
            config = ConfigurationHopital.objects.filter(hopital=hopital_selectionne).first()
            if config and hasattr(config, 'taux'):
                taux_change = config.taux
        except:
            pass
    
    # --- TOUTES LES SORTIES ---
    if hopital_selectionne:
        sorties = SortiePharmacie.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin voit TOUTES les sorties de tous les hôpitaux
        sorties = SortiePharmacie.objects.all()
    
    # Filtre par période
    if mois:
        sorties = sorties.filter(date_sortie__month=mois, date_sortie__year=annee)
    else:
        sorties = sorties.filter(date_sortie__year=annee)
    
    # --- TOUS LES PRODUITS ---
    if hopital_selectionne:
        produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin voit TOUS les produits
        produits = ProduitPharmacie.objects.all()
    
    # --- CALCUL PAR PRODUIT - AVEC GESTION CDF/USD ---
    benefices_par_produit = []
    
    for produit in produits:
        sorties_produit = sorties.filter(lot__produit=produit)
        quantite_vendue = sorties_produit.aggregate(
            total=Coalesce(Sum('quantite_vendue'), 0)
        )['total'] or 0
        
        if quantite_vendue > 0:
            prix_achat = float(produit.prix_achat_unitaire) if produit.prix_achat_unitaire else 0
            prix_vente = float(produit.prix_vente_unitaire) if produit.prix_vente_unitaire else 0
            devise_produit = produit.devise if produit.devise else 'CDF'  # CDF par défaut
            
            # Calculs dans la devise du produit
            benefice_unitaire = prix_vente - prix_achat
            benefice_total = benefice_unitaire * quantite_vendue
            chiffre_affaire = prix_vente * quantite_vendue
            marge = (benefice_total / chiffre_affaire * 100) if chiffre_affaire > 0 else 0
            
            # Conversions pour affichage
            if devise_produit == 'CDF':
                benefice_total_usd = benefice_total / taux_change
                chiffre_affaire_usd = chiffre_affaire / taux_change
                benefice_total_cdf = benefice_total
                chiffre_affaire_cdf = chiffre_affaire
            else:
                benefice_total_usd = benefice_total
                chiffre_affaire_usd = chiffre_affaire
                benefice_total_cdf = benefice_total * taux_change
                chiffre_affaire_cdf = chiffre_affaire * taux_change
            
            benefices_par_produit.append({
                'produit': produit,
                'quantite_vendue': quantite_vendue,
                'prix_achat': round(prix_achat, 2),
                'prix_vente': round(prix_vente, 2),
                'benefice_unitaire': round(benefice_unitaire, 2),
                'benefice_total': round(benefice_total, 2),
                'benefice_total_usd': round(benefice_total_usd, 2),
                'benefice_total_cdf': round(benefice_total_cdf, 2),
                'chiffre_affaire': round(chiffre_affaire, 2),
                'chiffre_affaire_usd': round(chiffre_affaire_usd, 2),
                'chiffre_affaire_cdf': round(chiffre_affaire_cdf, 2),
                'marge': round(marge, 2),
                'devise': devise_produit,
                'taux_change': taux_change,
            })
    
    # Tri par bénéfice total
    benefices_par_produit = sorted(
        benefices_par_produit, 
        key=lambda x: x['benefice_total'], 
        reverse=True
    )
    
    # --- TOTAUX GLOBAUX (TOUS PRODUITS CONFONDUS) ---
    benefice_total_global_usd = 0
    benefice_total_global_cdf = 0
    chiffre_affaire_global_usd = 0
    chiffre_affaire_global_cdf = 0
    
    for item in benefices_par_produit:
        benefice_total_global_usd += item['benefice_total_usd']
        benefice_total_global_cdf += item['benefice_total_cdf']
        chiffre_affaire_global_usd += item['chiffre_affaire_usd']
        chiffre_affaire_global_cdf += item['chiffre_affaire_cdf']
    
    marge_moyenne_usd = (benefice_total_global_usd / chiffre_affaire_global_usd * 100) if chiffre_affaire_global_usd > 0 else 0
    marge_moyenne_cdf = (benefice_total_global_cdf / chiffre_affaire_global_cdf * 100) if chiffre_affaire_global_cdf > 0 else 0
    
    # --- LISTE DES HÔPITAUX POUR LE FILTRE ---
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'filtre_actif': filtre_actif,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'mois': mois,
        'annee': annee,
        'benefices_par_produit': benefices_par_produit,
        # Totaux USD
        'benefice_total_global_usd': round(benefice_total_global_usd, 2),
        'chiffre_affaire_global_usd': round(chiffre_affaire_global_usd, 2),
        'marge_moyenne_usd': round(marge_moyenne_usd, 2),
        # Totaux CDF
        'benefice_total_global_cdf': round(benefice_total_global_cdf, 2),
        'chiffre_affaire_global_cdf': round(chiffre_affaire_global_cdf, 2),
        'marge_moyenne_cdf': round(marge_moyenne_cdf, 2),
        'taux_change': taux_change,
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
    hopital_selectionne = None
    filtre_actif = False
    
    # 1. Admin global ou super_admin peut tout voir OU filtrer
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        if hopital_id:
            # Admin a choisi un hôpital spécifique
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
            filtre_actif = True
        else:
            # Admin n'a pas filtré → voit TOUS les hôpitaux (None = pas de filtre)
            hopital_selectionne = None
            filtre_actif = False
    
    # 2. Pharmacien, admin_pharmacie, responsable_stock → limité à son hôpital
    elif fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # 3. Autres utilisateurs → hôpital par défaut
    else:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # --- TOUS LES PRODUITS ---
    if hopital_selectionne:
        produits = ProduitPharmacie.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin voit TOUS les produits de tous les hôpitaux
        produits = ProduitPharmacie.objects.all()
    
    # --- CALCUL DES ALERTES ---
    alertes = []
    
    for produit in produits:
        # Déterminer l'hôpital du produit pour filtrer les lots
        produit_hopital = produit.hopital
        
        # Calcul du stock - Tous les lots de ce produit dans cet hôpital
        lots = LotPharmacie.objects.filter(
            produit=produit,
            hopital=produit_hopital
        )
        stock = sum(lot.quantite_actuelle or 0 for lot in lots)
        
        # Lots proches de péremption (30 jours)
        lots_peremption = LotPharmacie.objects.filter(
            produit=produit,
            hopital=produit_hopital,
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
            continue  # Pas d'alerte, on passe au produit suivant
        
        alertes.append({
            'produit': produit,
            'stock': stock,
            'seuil_alerte': seuil_alerte,
            'statut': statut,
            'lots_peremption': lots_peremption,
            'devise': produit.devise if produit.devise else 'CDF',
            'hopital': produit_hopital,
        })
    
    # Trier par statut (rupture d'abord, puis faible, puis péremption)
    statut_order = {'rupture': 0, 'faible': 1, 'peremption': 2}
    alertes = sorted(alertes, key=lambda x: statut_order.get(x['statut'], 3))
    
    # --- LISTE DES HÔPITAUX POUR LE FILTRE ---
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    # Compter les alertes par type
    alertes_rupture = len([a for a in alertes if a['statut'] == 'rupture'])
    alertes_faible = len([a for a in alertes if a['statut'] == 'faible'])
    alertes_peremption = len([a for a in alertes if a['statut'] == 'peremption'])
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'filtre_actif': filtre_actif,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'alertes': alertes,
        'alertes_rupture': alertes_rupture,
        'alertes_faible': alertes_faible,
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    type_mouvement = request.GET.get('type_mouvement')
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
    hopital_selectionne = None
    filtre_actif = False
    
    # 1. Admin global ou super_admin peut tout voir OU filtrer
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        if hopital_id:
            # Admin a choisi un hôpital spécifique
            hopital_selectionne = get_object_or_404(Hopital, pk=hopital_id)
            filtre_actif = True
        else:
            # Admin n'a pas filtré → voit TOUS les hôpitaux (None = pas de filtre)
            hopital_selectionne = None
            filtre_actif = False
    
    # 2. Pharmacien, admin_pharmacie, responsable_stock → limité à son hôpital
    elif fonction_key and fonction_key.roleName.lower() in ['pharmacien', 'admin_pharmacie', 'responsable_stock']:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # 3. Autres utilisateurs → hôpital par défaut
    else:
        hopital_selectionne = hopital_user
        filtre_actif = True
    
    # --- RÉCUPÉRER LE PRODUIT ---
    # Admin peut voir TOUS les produits, pas seulement ceux de son hôpital
    if hopital_selectionne:
        # Utilisateur normal ou admin avec filtre → limité à un hôpital
        try:
            produit = ProduitPharmacie.objects.get(pk=produit_id, hopital=hopital_selectionne)
        except ProduitPharmacie.DoesNotExist:
            messages.error(request, f"Le produit demandé n'existe pas ou n'appartient pas à cet hôpital.")
            return redirect('admin_historique_stock')
    else:
        # Admin sans filtre → peut voir n'importe quel produit
        try:
            produit = ProduitPharmacie.objects.get(pk=produit_id)
        except ProduitPharmacie.DoesNotExist:
            messages.error(request, f"Le produit demandé n'existe pas.")
            return redirect('admin_historique_stock')
    
    # --- RÉCUPÉRER LES MOUVEMENTS ---
    # Si admin sans filtre, on prend TOUS les mouvements de ce produit
    if hopital_selectionne:
        # Utilisateur normal ou admin avec filtre → limité à un hôpital
        mouvements = MouvementStock.objects.filter(lot__produit=produit, hopital=hopital_selectionne)
    else:
        # Admin sans filtre → TOUS les mouvements de ce produit dans tous les hôpitaux
        mouvements = MouvementStock.objects.filter(lot__produit=produit)
    
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
        'effectue_par',
        'hopital'
    ).order_by('-date_mouvement')
    
    # --- CALCUL DES TOTAUX ---
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
    
    # --- LISTE DES HÔPITAUX POUR LE FILTRE ---
    if fonction_key and fonction_key.roleName.lower() in ['admin', 'super_admin', 'directeur']:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    context = {
        'produit': produit,
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'filtre_actif': filtre_actif,
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
    
    # Filtres
    hopital_id = request.GET.get('hopital')
    patient_id = request.GET.get('patient')
    prestation_id = request.GET.get('prestation')
    service = request.GET.get('service')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    devise = request.GET.get('devise')
    query = request.GET.get('q', '')  # Recherche
    
    # --- GESTION DU FILTRE PAR HÔPITAL ---
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
    
    # --- REQUÊTE DE BASE ---
    if hopital_selectionne:
        paiements = Paiement.objects.filter(hopital=hopital_selectionne)
    else:
        # Admin global voit TOUS les paiements
        paiements = Paiement.objects.all()
    
    # --- FILTRES ---
    if patient_id:
        paiements = paiements.filter(patient_id=patient_id)
    
    if prestation_id:
        if prestation_id == 'consultation':
            consultations = Consultation.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else Consultation.objects.all()
            paiements = paiements.filter(consultation__in=consultations)
        elif prestation_id == 'session':
            sessions = SessionSoins.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else SessionSoins.objects.all()
            paiements = paiements.filter(session__in=sessions)
        elif prestation_id == 'examen_externe':
            examens = DemandeExamenExterne.objects.filter(hopital=hopital_selectionne) if hopital_selectionne else DemandeExamenExterne.objects.all()
            paiements = paiements.filter(demande_examen_externe__in=examens)
    
    if service:
        paiements = paiements.filter(service=service)
    
    if date_debut:
        paiements = paiements.filter(date_paiement__date__gte=date_debut)
    
    if date_fin:
        paiements = paiements.filter(date_paiement__date__lte=date_fin)
    
    if devise:
        paiements = paiements.filter(devise=devise)
    
    # Recherche par nom
    if query:
        paiements = paiements.filter(
            Q(patient__noms__icontains=query) |
            Q(clientEx__noms__icontains=query)
        )
    
    # --- SÉLECTION LIÉE (SELECT_RELATED) ---
    paiements = paiements.select_related(
        'patient', 
        'caissier', 
        'hopital',
        'consultation',
        'session',
        'hospitalisation',
        'dossier_maternite',
        'demande_examen_externe',
        'clientEx'
    ).order_by('-date_paiement')
    
    # --- CRÉER LA LISTE DES PAIEMENTS AVEC TOUTES LES INFOS ---
    paiements_data = []
    
    for paiement in paiements:
        # 1. NOM DU PATIENT / CLIENT
        nom_patient = ""
        
        if paiement.patient:
            # Patient interne
            nom_patient = f"{paiement.patient.noms.upper()}"
        elif paiement.clientEx:
            # Client externe (via Paiement.clientEx, PAS via DemandeExamenExterne)
            nom_patient = f"{paiement.clientEx.noms.upper()} (Externe)"
        elif paiement.entreprise:
            # Entreprise
            nom_patient = paiement.entreprise.nom or "Entreprise"
        else:
            nom_patient = "N/A"
        
        # 2. PRESTATION
        prestation = ""
        numero_dossier = ""
        
        if paiement.consultation:
            prestation = f"Consultation - {paiement.consultation.motif_consultation[:50] or 'N/A'}"
            numero_dossier = f"CONS-{paiement.consultation.id}"
        elif paiement.session:
            session = paiement.session
            prestation = f"Session Soins - {session.total_a_payer:.2f} {paiement.devise or 'CDF'}"
            numero_dossier = f"SESSION-{session.id}"
        elif paiement.hospitalisation:
            hosp = paiement.hospitalisation
            prestation = f"Hospitalisation - {hosp.motif_admission[:50] or 'N/A'}"
            numero_dossier = f"HOSP-{hosp.id}"
        elif paiement.dossier_maternite:
            maternite = paiement.dossier_maternite
            prestation = f"Maternité - Terme: {maternite.terme_prevu.strftime('%d/%m/%Y') if maternite.terme_prevu else 'N/A'}"
            numero_dossier = f"MAT-{maternite.id}"
        elif paiement.demande_examen_externe:
            examen = paiement.demande_examen_externe
            prestation = f"Examen Externe - Total: {examen.total_a_payer:.2f} USD"
            numero_dossier = f"EXAM-{examen.id}"
        elif paiement.bloc_op:
            bloc = paiement.bloc_op
            prestation = f"Bloc Opératoire"
            numero_dossier = f"BLOC-{bloc.id}"
        elif paiement.deces:
            deces = paiement.deces
            prestation = f"Décès"
            numero_dossier = f"DECES-{deces.id}"
        elif paiement.compte_rendu:
            cr = paiement.compte_rendu
            prestation = f"Accouchement"
            numero_dossier = f"CR-{cr.id}"
        else:
            prestation = f"Service: {paiement.service or 'N/A'}"
        
        # 3. MONTANT
        montant = float(paiement.montant_verse) if paiement.montant_verse else 0
        
        # 4. HÔPITAL
        nom_hopital = paiement.hopital.nomH if paiement.hopital else "N/A"
        
        # 5. CAISSIER
        if paiement.caissier:
            nom_caissier = f"{paiement.caissier.first_name or ''} {paiement.caissier.last_name or paiement.caissier.username}".strip()
        else:
            nom_caissier = "Système"
        
        # 6. RESTE À PAYER
        reste_a_payer = float(paiement.reste_a_payer) if paiement.reste_a_payer else 0
        
        # Ajouter à la liste
        paiements_data.append({
            'paiement': paiement,
            'id': paiement.id,
            'nom_patient': nom_patient,
            'prestation': prestation,
            'numero_dossier': numero_dossier,
            'montant': round(montant, 2),
            'devise': paiement.devise or 'CDF',
            'date_paiement': paiement.date_paiement,
            'hopital': nom_hopital,
            'caissier': nom_caissier,
            'service': paiement.service or 'N/A',
            'reste_a_payer': round(reste_a_payer, 2),
        })
    
    # --- STATS ---
    if hopital_selectionne:
        total_usd = Paiement.objects.filter(hopital=hopital_selectionne, devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
        total_cdf = Paiement.objects.filter(hopital=hopital_selectionne, devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0
    else:
        total_usd = Paiement.objects.filter(devise='USD').aggregate(total=Sum('montant_verse'))['total'] or 0
        total_cdf = Paiement.objects.filter(devise='CDF').aggregate(total=Sum('montant_verse'))['total'] or 0
    
    # --- LISTE DES HÔPITAUX POUR LE FILTRE ---
    if est_admin_global:
        hopitaux = Hopital.objects.all()
    else:
        hopitaux = Hopital.objects.filter(pk=hopital_user.pk) if hopital_user else Hopital.objects.none()
    
    context = {
        'hopitaux': hopitaux,
        'hopital_selectionne': hopital_selectionne,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'paiements': paiements_data,
        'total_usd': round(total_usd, 2),
        'total_cdf': round(total_cdf, 2),
        'patient_id': patient_id,
        'prestation_id': prestation_id,
        'service': service,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'devise': devise,
        'query': query,
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
    
    # --- LOGIQUE NOM DU PATIENT (MÊME QUE LA VUE LISTE) ---
    nom_patient = ""
    
    if paiement.patient:
        # Patient interne - Utiliser 'noms'
        nom_patient = f"{paiement.patient.noms.upper()}"
    elif paiement.clientEx:
        # Client externe - Utiliser 'clientEx.noms'
        nom_patient = f"{paiement.clientEx.noms.upper()} (Externe)"
    elif paiement.entreprise:
        # Entreprise
        nom_patient = paiement.entreprise.nom or "Entreprise"
    else:
        nom_patient = "N/A"
    
    # --- PRESTATION ---
    prestation = ""
    numero_dossier = ""
    
    if paiement.consultation:
        prestation = f"Consultation - {paiement.consultation.motif_consultation[:50] or 'N/A'}"
        numero_dossier = f"CONS-{paiement.consultation.id}"
    elif paiement.session:
        session = paiement.session
        prestation = f"Session Soins - {session.total_a_payer:.2f} {paiement.devise or 'CDF'}"
        numero_dossier = f"SESSION-{session.id}"
    elif paiement.hospitalisation:
        hosp = paiement.hospitalisation
        prestation = f"Hospitalisation - {hosp.motif_admission[:50] or 'N/A'}"
        numero_dossier = f"HOSP-{hosp.id}"
    elif paiement.dossier_maternite:
        maternite = paiement.dossier_maternite
        prestation = f"Maternité - Terme: {maternite.terme_prevu.strftime('%d/%m/%Y') if maternite.terme_prevu else 'N/A'}"
        numero_dossier = f"MAT-{maternite.id}"
    elif paiement.demande_examen_externe:
        examen = paiement.demande_examen_externe
        prestation = f"Examen Externe - Total: {examen.total_a_payer:.2f} USD"
        numero_dossier = f"EXAM-{examen.id}"
    elif paiement.bloc_op:
        bloc = paiement.bloc_op
        prestation = f"Bloc Opératoire"
        numero_dossier = f"BLOC-{bloc.id}"
    elif paiement.deces:
        deces = paiement.deces
        prestation = f"Décès"
        numero_dossier = f"DECES-{deces.id}"
    elif paiement.compte_rendu:
        cr = paiement.compte_rendu
        prestation = f"Accouchement"
        numero_dossier = f"CR-{cr.id}"
    else:
        prestation = f"Service: {paiement.service or 'N/A'}"
    
    context = {
        'paiement': paiement,
        'facture': facture,
        'autres_paiements': autres_paiements,
        'fonctionKey': fonction_key_name,
        'role_utilisateur': fonction_key,
        'nom_patient': nom_patient,  # ← Ajouté
        'prestation': prestation,     # ← Ajouté
        'numero_dossier': numero_dossier,  # ← Ajouté
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

#
# ======================================================================================================================
# ORIENTATION DES PATIENT LISTE 
# ======================================================================================================================
@login_required
def liste_patients_orientations_view(request):
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital", "fonctionKey").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"
    user_hopital = role_obj.hopital if role_obj else None

    q = request.GET.get("q", "").strip()
    selected_hopital_id = request.GET.get("hopital", "").strip()

    patients = Patient.objects.select_related("hopital", "service")
    if q:
        patients = patients.filter(
            Q(noms__icontains=q) |
            Q(code_patient__icontains=q)
        )

    if request.user.is_superuser:
        if selected_hopital_id:
            patients = patients.filter(hopital_id=selected_hopital_id)
    else:
        if user_hopital:
            patients = patients.filter(hopital=user_hopital)
        else:
            patients = patients.none()

    patients = patients.order_by("noms")

    orientations = Orientation.objects.select_related(
        "consultation",
        "medecin_orientateur",
        "consultation__triage__patient",
        "hopital",
    ).order_by("-date_orientation")

    if request.user.is_superuser:
        if selected_hopital_id:
            orientations = orientations.filter(hopital_id=selected_hopital_id)
    else:
        if user_hopital:
            orientations = orientations.filter(hopital=user_hopital)
        else:
            orientations = orientations.none()

    if q:
        orientations = orientations.filter(
            Q(consultation__triage__patient__noms__icontains=q) |
            Q(consultation__triage__patient__code_patient__icontains=q)
        )

    derniere_orientation_par_patient = {}
    for orientation in orientations:
        patient = orientation.consultation.triage.patient
        if patient.id not in derniere_orientation_par_patient:
            derniere_orientation_par_patient[patient.id] = orientation

    patients_data = []
    for patient in patients:
        orientation = derniere_orientation_par_patient.get(patient.id)
        patients_data.append({
            "patient": patient,
            "orientation": orientation,
        })

    paginator = Paginator(patients_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.user.is_superuser:
        hopitals = Patient.objects.exclude(hopital__isnull=True).values_list(
            "hopital__id", "hopital__nomH"
        ).distinct().order_by("hopital__nomH")
    else:
        hopitals = []

    return render(request, "back-end/patient/liste_patients_orientations.html", {
        "page_obj": page_obj,
        "patients_data": page_obj.object_list,
        "patients": patients,
        "orientations": orientations,
        "fonctionKey": fonction_key,
        "user_hopital": user_hopital,
        "hopitals": hopitals,
        "selected_hopital_id": selected_hopital_id,
        "q": q,
    })
#
# ===========================================================================================================================
# LISTE DE TYPE DE CHAMBRE COTE ADMIN
# ===========================================================================================================================
@login_required
def liste_types_chambre(request):
    # Récupérer le taux de conversion
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500.00')  # 1 USD = taux CDF

    # Tous les types de chambre
    types_chambre = TypeChambre.objects.all()

    # Ajouter les prix convertis pour chaque type
    for tc in types_chambre:
        # tc.prix_nuitée est stocké en CDF
        tc.prix_cdf = tc.prix_nuitée or Decimal('0')
        tc.prix_usd = tc.prix_cdf / taux if taux else Decimal('0')

    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(
        request,
        'back-end/patient/type_chambre_list.html',
        {
            'types_chambre': types_chambre,
            'fonctionKey': fonction_key,
            'taux': taux,
        },
    )

#
# ===========================================================================================================================
# LISTE DE CHAMBRE COTE ADMIN
# ===========================================================================================================================
@login_required
def liste_chambres(request):
  chambres = Chambre.objects.all()

  role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
  fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

  return render(request, 'back-end/patient/chambre_list.html', {'chambres': chambres,'fonctionKey':fonction_key})

#
# ===========================================================================================================================
# LISTE DES LITS
# ===========================================================================================================================
@login_required
def liste_lits(request):
  lits = Lit.objects.all()

  role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
  fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

  return render(request, 'back-end/patient/lit_list.html', {'lits': lits ,'fonctionKey':fonction_key})





#
# ===============================================================================================================
# MODIFICATION TYPE DE CHAMBRE 
# ===============================================================================================================
@login_required
def modifier_type_chambre(request, pk):
    type_chambre = get_object_or_404(TypeChambre, pk=pk)

    if request.method == 'POST':
        form = TypeChambreForm(request.POST, instance=type_chambre)
        if form.is_valid():
            # Le champ prix_nuitée est en CDF dans le formulaire
            form.save()
            return redirect('type_chambre_list')
    else:
        form = TypeChambreForm(instance=type_chambre)

    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    # Récupérer le taux pour affichage (équivalent USD)
    config = ConfigurationHopital.objects.first()
    taux = config.taux_usd_en_cdf if config and config.taux_usd_en_cdf else Decimal('2500.00')

    return render(
        request,
        'back-end/patient/type_chambre_form.html',  # ou 'back-end/hospitalisation/type_chambre_form.html'
        {
            'form': form,
            'objet': type_chambre,
            'fonctionKey': fonction_key,
            'taux': taux,
        },
    )
#
# =============================================================================================================
# MODIFICATION DE CHAMBRE
# =============================================================================================================
@login_required
def modifier_chambre(request, pk):
  chambre = get_object_or_404(Chambre, pk=pk)
  if request.method == 'POST':
    form = ChambreForm(request.POST, instance=chambre)
    if form.is_valid():
      form.save()
      return redirect('chambre_list')
  else:
    form = ChambreForm(instance=chambre)
  role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
  fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

  return render(
      request, 'back-end/patient/chambre_form.html', {'form': form, 'objet': chambre,'fonctionKey':fonction_key} 
  )

#
# =========================================================================================================================
# MODIFICATION DES LITS
# =========================================================================================================================
@login_required
def modifier_lit(request, pk):
  lit = get_object_or_404(Lit, pk=pk)
  if request.method == 'POST':
    form = LitForm(request.POST, instance=lit)
    if form.is_valid():
      form.save()
      return redirect('lit_list')
  else:
    form = LitForm(instance=lit)
    
  role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
  fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

  return render(request, 'back-end/patient/lit_form.html', {'form': form, 'objet': lit,'fonctionKey':fonction_key})
#
# ===========================================================================================================================
# SUPPRESSION DU TYPE DE CHAMBRE 
# ============================================================================================================================
@login_required
def supprimer_type_chambre(request, pk):
    type_chambre = get_object_or_404(TypeChambre, pk=pk)
    if request.method == 'POST':
        type_chambre.delete()
        return redirect('type_chambre_list')
    
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(
        request,
        'back-end/patient/type_chambre_confirm_delete.html',
        {'objet': type_chambre, 'fonctionKey': fonction_key}
    )

#
# ===========================================================================================================================
# SUPPRESSION DES CHAMBRES 
# ============================================================================================================================
@login_required
def supprimer_chambre(request, pk):
    chambre = get_object_or_404(Chambre, pk=pk)
    if request.method == 'POST':
        chambre.delete()
        return redirect('chambre_list')
    
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(
        request,
        'back-end/patient/chambre_confirm_delete.html',
        {'objet': chambre, 'fonctionKey': fonction_key}
    )

#
# ===========================================================================================================================
# SUPPRESSION DES LITS 
# ============================================================================================================================
@login_required
def supprimer_lit(request, pk):
    lit = get_object_or_404(Lit, pk=pk)
    if request.method == 'POST':
        try:
            lit.delete()
            messages.success(request, "Le lit a été supprimé avec succès.")
            return redirect('lit_list')
        except ProtectedError:
            messages.error(request, "Impossible de supprimer ce lit car il est rattaché à une ou plusieurs hospitalisations existantes.")
            return redirect('lit_list')
    
    role_obj = Fonction.objects.filter(userKey=request.user).select_related("hopital").first()
    fonction_key = role_obj.fonctionKey.roleName if role_obj and role_obj.fonctionKey else "Utilisateur"

    return render(
        request,
        'back-end/patient/lit_confirm_delete.html',
        {'objet': lit, 'fonctionKey': fonction_key}
    )

#
# =============================================================================================================================
# LISTE DES PRESTATIONS POUR LES RECPTIONNISTE
# =============================================================================================================================
@login_required
def liste_prestations_receptionniste(request):
    role = Fonction.objects.filter(userKey=request.user).select_related("hopital", "fonctionKey").first()
    user_hopital = role.hopital if role else None
    fonction_key = role.fonctionKey.roleName if role and role.fonctionKey else "Utilisateur"

    q = request.GET.get("q", "").strip()

    prestations = Prestation.objects.all().order_by("libelle")

    if not request.user.is_superuser:
        if user_hopital:
            prestations = prestations.filter(hopital=user_hopital)
        else:
            prestations = prestations.none()

    if q:
        prestations = prestations.filter(
            Q(libelle__icontains=q) |
            Q(categorie__icontains=q)
        )

    taux = ConfigurationHopital.get_taux()
    taux = Decimal(str(taux))  # 1 USD = taux CDF

    # Calcul des prix :
    # - item.prix est en CDF (stocké en base)
    # - on calcule USD = CDF / taux
    prestations_list = []
    for prestation in prestations:
        prix_cdf = prestation.prix or Decimal("0")
        prix_usd = prix_cdf / taux if taux else Decimal("0")
        prestations_list.append({
            "obj": prestation,
            "prix_usd": prix_usd,
            "prix_cdf": prix_cdf,
        })

    return render(request, "back-end/prestation/list_prestation_receptionniste.html", {
        "prestations": prestations,
        "prestations_list": prestations_list,
        "taux": taux,
        "fonctionKey": fonction_key,
        "user_hopital": user_hopital,
        "q": q,
    })