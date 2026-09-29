from django import forms
from django.contrib.auth.models import User
from .models import *
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from datetime import date
from django.utils import timezone

# creation du formulaire d'authentification
# ==========================================
# ==========================================
class LoginForm(forms.Form):
    username = forms.CharField(max_length = 30 , widget = forms.TextInput(attrs={'class':'form-control'}))
    password = forms.CharField(max_length = 200 , widget = forms.PasswordInput(attrs={'class':'form-control'}))

# creation du formulaire Utilisateurs
# ===================================
# ===================================
class EmployeForm(forms.ModelForm):
    password = forms.CharField(
        max_length=200,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Mot de passe utilisateur'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username': 'Nom utilisateur',
            'email': 'Email utilisateur',
        }

    # Vérification de l'username (doublon)
    def clean_username(self):
        username = self.cleaned_data.get('username')
        exists = User.objects.filter(username=username)

        if self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)

        if exists.exists():
            raise ValidationError("Ce nom d'utilisateur est déjà utilisé dans le système.")
        return username

    # Vérification de l'email (doublon)
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email: # On vérifie seulement si l'email est rempli
            exists = User.objects.filter(email=email)

            if self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)

            if exists.exists():
                raise ValidationError("Cette adresse email est déjà enregistrée.")
        return email

    # Pour hacher le mot de passe avant la sauvegarde
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"]) # Hachage sécurisé
        if commit:
            user.save()
        return user


# formulaire pour attribue role 
class FonctionForm(forms.ModelForm):
    class Meta:
        model = Fonction
        fields = ['fonctionKey','hopital']
        labels = {
            'fonctionKey': 'Rôle / Poste',
                    }
        widgets = {
            'fonctionKey': forms.Select(attrs={'class': 'form-control'}),
            'hopital': forms.Select(attrs={'class': 'form-control'}),
            
        }

class ModifierUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']  # On ne garde QUE ce dont tu as besoin
        
    def __init__(self, *args, **kwargs):
        super(ModifierUserForm, self).__init__(*args, **kwargs)
        # On ajoute les classes Bootstrap pour garder ton beau design
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})



class PrestationForm(forms.ModelForm):
    class Meta:
        model = Prestation
        fields = ['libelle', 'categorie', 'prix', 'valeur_normale', 'hopital']
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Goutte Épaisse'}),
            'categorie': forms.Select(attrs={'class': 'form-control', 'id': 'id_categorie'}),
            'hopital': forms.Select(attrs={'class': 'form-control'}),
            'prix': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'valeur_normale': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 70-110 mg/dl ou Négatif',
                'id': 'id_valeur_normale'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        categorie = cleaned_data.get('categorie')
        valeur_normale = cleaned_data.get('valeur_normale')

        if categorie != 'LABO' and valeur_normale:
            cleaned_data['valeur_normale'] = None

        return cleaned_data

class ConfigurationHopitalForm(forms.ModelForm):
    class Meta:
        model = ConfigurationHopital
        fields = ['taux_usd_en_cdf']
        widgets = {
            'taux_usd_en_cdf': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ex: 2850.00'
            }),
        }

    def clean_taux_usd_en_cdf(self):
        taux = self.cleaned_data.get('taux_usd_en_cdf')
        if taux <= 0:
            raise forms.ValidationError("Le taux de change doit être supérieur à zéro.")
        return taux



class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['nom']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Gynécologie, Radiographie...'
            }),
        }

    def clean_nom(self):
        nom = self.cleaned_data.get('nom')
        # On vérifie si un service avec ce nom existe déjà (en ignorant la casse si tu veux)
        if Service.objects.filter(nom__iexact=nom).exists():
            raise forms.ValidationError("Ce service existe déjà dans le système.")
        return nom

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['noms', 'sexe', 'age', 'adresse', 'telephone', 'service', 'entreprise','statut_p']
        widgets = {
            'noms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom, Post-nom et Prénom'}),
            'sexe': forms.Select(attrs={'class': 'form-select'}),
            'age': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 25 ans ou 8 mois'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: +243...'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Adresse de résidence'}),
            'service': forms.Select(attrs={'class': 'form-select'}),
            'entreprise': forms.Select(attrs={'class': 'form-select'}),
            'statut_p': forms.Select(attrs={'class':'form-select'}) 
        }

    def clean_noms(self):
        noms = self.cleaned_data.get('noms')
        if len(noms) < 3:
            raise forms.ValidationError("Le nom complet est trop court.")
        return noms.upper()
# 1. Formulaire principal de la Consultation
class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ['motif_consultation','antecedent', 'histoire_maladie', 'complement_d_anamnese','examen_physique', 'hypothese_diagnostique']
        widgets = {
            # On ajoute 'required': 'required' dans les attributs HTML
            'motif_consultation': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2, 
                'placeholder': 'Pourquoi le patient consulte ?',
                'required': 'required'
            }),
            'histoire_maladie': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'required': 'required'
            }),
            'complement_d_anamnese': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'required': 'required'
            }),


            'examen_physique': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'required': 'required'
            }),
            'hypothese_diagnostique': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2, 
                'placeholder': 'Votre diagnostic provisoire',
                'required': 'required'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On s'assure que TOUS les champs du formulaire sont obligatoires au niveau de Django
        for field_name in self.fields:
            self.fields[field_name].required = True


# ==================================================================================================
class DepenseForm(forms.ModelForm):
    class Meta:
        model = Depense
        # On ne met pas 'auteur' et 'date_depense' car ils sont gérés automatiquement
        fields = ['motif', 'description', 'montant', 'devise', 'beneficiaire']
        
        # Injection des classes Bootstrap pour le design
        widgets = {
            'motif': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Détails de la dépense...'}),
            'montant': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 150'}),
            'devise': forms.Select(attrs={'class': 'form-control'}),
            'beneficiaire': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Fournisseur Mazout ou Nom de l\'agent'}),
        }


# ==================================================================================================
class TypeChambreForm(forms.ModelForm):
    class Meta:
        model = TypeChambre
        fields = ['libelle', 'prix_nuitée']
        widgets = {
            'libelle': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: VIP, Commune, Spéciale, etc.'
            }),
            'prix_nuitée': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '100',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['libelle'].label = "Libellé du type de chambre"
        self.fields['prix_nuitée'].label = "Prix de la nuitée (FC)"
        self.fields['prix_nuitée'].help_text = "Indiquez le prix en Francs Congolais (FC)."
        self.fields['prix_nuitée'].required = True

class ChambreForm(forms.ModelForm):
    class Meta:
        model = Chambre
        # On utilise uniquement les champs définis dans le modèle Chambre
        fields = ['nom', 'type_chambre', 'est_active']
        
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Chambre 101'}),
            'type_chambre': forms.Select(attrs={'class': 'form-control'}),
            'est_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nom': 'Nom ou Numéro de la chambre',
            'type_chambre': 'Type de chambre',
            'est_active': 'Disponible pour hospitalisation',
        }

# apps/forms.py

class LitForm(forms.ModelForm):
    class Meta:
        model = Lit
        fields = ['chambre', 'nom_lit', 'est_occupe', 'est_actif']
        widgets = {
            'chambre': forms.Select(attrs={'class': 'form-control'}),
            'nom_lit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Lit A, Lit 01...'}),
            'est_occupe': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'chambre': 'Chambre associée',
            'nom_lit': 'Nom ou Numéro du Lit',
            'est_occupe': 'Déjà occupé ?',
            'est_actif': 'Opérationnel / Actif',
        }

    def clean(self):
        cleaned_data = super().clean()
        chambre = cleaned_data.get('chambre')
        nom_lit = cleaned_data.get('nom_lit')

        # Vérifier si un lit avec ce nom existe déjà dans CETTE chambre
        if chambre and nom_lit:
            # On cherche un lit avec le même nom dans la même chambre
            # On exclut le lit actuel (self.instance) pour permettre la modification sans erreur
            exists = Lit.objects.filter(chambre=chambre, nom_lit__iexact=nom_lit).exclude(pk=self.instance.pk)
            
            if exists.exists():
                raise ValidationError({
                    'nom_lit': f"Le '{nom_lit}' existe déjà dans la chambre {chambre}."
                })
        
        return cleaned_data




class OrdonnanceForm(forms.ModelForm):
    class Meta:
        model = Ordonnance
        fields = ['type_ordonnance', 'diagnostic', 'observation']

class MedicamentForm(forms.ModelForm):
    class Meta:
        model = Medicament
        # Assurez-vous que ces champs existent dans votre classe Medicament :
        fields = ['nom', 'posologie', 'duree']

# ===============================================================================
#
# 


class HospitalisationForm(forms.ModelForm):
    class Meta:
        model = Hospitalisation
        fields = ['patient', 'lit', 'date_entree', 'motif_admission']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-control select2'}), # 'select2' pour la recherche JS
            'lit': forms.Select(attrs={'class': 'form-control'}),
            'date_entree': forms.DateTimeInput(attrs={
                'class': 'form-control', 
                'type': 'datetime-local'
            }),
            'motif_admission': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 1. Filtrage Patient : Seulement ceux dont la fiche est payée
        # Assurez-vous que votre modèle Patient possède un champ 'fiche_payee'
        self.fields['patient'].queryset = Patient.objects.filter(fiche_payee=True)
        
        # 2. Filtrage Lit : Uniquement les lits libres et actifs
        self.fields['lit'].queryset = Lit.objects.filter(est_occupe=False, est_actif=True)
        
        # 3. Initialisation de la date par défaut
        self.fields['date_entree'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')

    def clean_patient(self):
        patient = self.cleaned_data.get('patient')
        # Sécurité supplémentaire : vérifier si le patient est déjà en cours d'hospitalisation
        if Hospitalisation.objects.filter(patient=patient, statut='EN_COURS').exists():
            raise forms.ValidationError(f"Le patient {patient.noms} est déjà hospitalisé actuellement.")
        return patient

    def clean_lit(self):
        lit = self.cleaned_data.get('lit')
        
        # Vérification en base pour éviter les accès concurrents
        qs = Hospitalisation.objects.filter(lit=lit, statut='EN_COURS')
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
            
        if qs.exists():
            raise forms.ValidationError(f"Le lit {lit.nom_lit} vient d'être réservé par un autre patient.")
        return lit


# =======================================================================
# formulaire entreprise add 
# =======================================================================

class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ['nom', 'contact_responsable', 'hopital']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "Nom de l'entreprise"
            }),
            'contact_responsable': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Numéro de téléphone'
            }),
            'hopital': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def clean_nom(self):
        nom = self.cleaned_data.get('nom')
        instance = getattr(self, 'instance', None)

        # En création : on vérifie sur toutes les entreprises
        # En modification : on exclut l'entreprise en cours d'édition
        qs = Entreprise.objects.filter(nom__iexact=nom)
        if instance and instance.pk:
            qs = qs.exclude(pk=instance.pk)

        if qs.exists():
            raise forms.ValidationError(f"L'entreprise '{nom}' est déjà enregistrée dans le système.")
        return nom



# =============================================================================
# formulaire maternite 
class MaterniteForm(forms.ModelForm):
    class Meta:
        model = Maternite
        fields = ['terme_prevu', 'groupe_sanguin']
        widgets = {
            'terme_prevu': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'groupe_sanguin': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_terme_prevu(self):
        terme = self.cleaned_data.get('terme_prevu')
        # Optionnel : Empêcher une date passée
        if terme and terme < date.today():
            raise ValidationError("La date du terme ne peut pas être dans le passé.")
        return terme

    def clean(self):
        # Cette vérification nécessite de passer le 'patient' au formulaire
        # On le fera via le constructeur __init__
        cleaned_data = super().clean()
        patient = self.instance.patient if self.instance else None
        
        # Exemple : On bloque l'enregistrement si un dossier existe déjà 
        # pour la même date de terme (évite les saisies en double)
        if patient and Maternite.objects.filter(patient=patient, terme_prevu=cleaned_data.get('terme_prevu')).exists():
            raise ValidationError("Cette patiente possède déjà un dossier de maternité avec cette date de terme.")
        
        return cleaned_data



# ===============================================================================
#
#  

class ConsultationMaterniteForm(forms.ModelForm):
    class Meta:
        model = ConsultationMaternite
        exclude = ['dossier_maternite', 'effectue_par', 'date_consultation']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }



# ===============================================================================
#
#
class ProduitPharmacieForm(forms.ModelForm):
    class Meta:
        model = ProduitPharmacie
        fields = [
            'nom', 'forme', 'dosage', 'categorie', 
            'unites_par_carton', 'prix_achat_unitaire', 'prix_vente_unitaire'
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Amoxicilline'}),
            'forme': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Comprimé'}),
            'dosage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 500mg'}),
            'categorie': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Antibiotique'}),
            'unites_par_carton': forms.NumberInput(attrs={'class': 'form-control'}),
            'prix_achat_unitaire': forms.NumberInput(attrs={'class': 'form-control'}),
            'prix_vente_unitaire': forms.NumberInput(attrs={'class': 'form-control'}),
        }




# ------------------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------

class LotPharmacieForm(forms.ModelForm):
    class Meta:
        model = LotPharmacie
        fields = [
            'produit',
            'numero_lot',
            'quantite_initiale',
            'date_peremption',
        ]

        widgets = {
            'produit': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'numero_lot': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Exemple : LOT-001'
                }
            ),
            'quantite_initiale': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '1'
                }
            ),
            'date_peremption': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        hopital = kwargs.pop('hopital', None)

        super().__init__(*args, **kwargs)

        if hopital:
            # Important :
            # seul ce qui appartient à cet hôpital ET est encore actif
            # apparaît dans la liste déroulante.
            self.fields['produit'].queryset = (
                ProduitPharmacie.objects.filter(
                    hopital=hopital,
                    actif=True
                ).order_by('nom', 'dosage')
            )
        else:
            # Sans hôpital, aucun médicament ne doit être affiché.
            self.fields['produit'].queryset = (
                ProduitPharmacie.objects.none()
            )


# ==========================================================================================
#
# 
class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['noms', 'sexe', 'age', 'adresse', 'telephone', 'entreprise', 'service','statut_p']
        widgets = {
            'noms': forms.TextInput(attrs={'class': 'form-control'}),
            'sexe': forms.Select(attrs={'class': 'form-control'}),
            'age': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'entreprise': forms.Select(attrs={'class': 'form-control'}),
            'service': forms.Select(attrs={'class': 'form-control'}), # Liste déroulante des services
            'statut_p' : forms.Select(attrs={'class': 'form-control'}),
        }



# ===================================================================
#
#
class ClientExterneForm(forms.ModelForm):
    class Meta:
        model = ClientExterne
        fields = ['noms', 'sexe', 'poids', 'age', 'telephone']
        widgets = {
            'noms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet du client'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numéro de téléphone'}),
            'age': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Age du client'}),
            'sexe': forms.Select(attrs={'class': 'form-control'}),
            'poids': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Poids (kg)'}), 
        }


class DemandeExamenExterneForm(forms.ModelForm):
    class Meta:
        model = DemandeExamenExterne
        fields = ['medecin_demandeur', 'clinique', 'but', 'prestations']
        widgets = {
            'medecin_demandeur': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Nom du médecin demandeur'
            }),
            'clinique': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Informations cliniques...'
            }),
            'but': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2, 
                'placeholder': 'But de la demande...'
            }),
            'prestations': forms.SelectMultiple(attrs={
                'class': 'form-control', 
                'size': '10',
                'multiple': 'multiple'
            }),
        }
        labels = {
            'medecin_demandeur': 'Médecin demandeur',
            'clinique': 'Informations cliniques',
            'but': 'But de la demande',
            'prestations': 'Examens à réaliser',
        }


# =================================================================
#
#
class DemandeExamenForm(forms.ModelForm):
    class Meta:
        model = DemandeExamenExterne
        fields = ['prestations']
        widgets = {
            # Utilisation de 'selectmultiple' pour permettre de choisir plusieurs examens
            'prestations': forms.SelectMultiple(attrs={'class': 'form-control select2'}),
        }


# ============================================================
#
#

class OrdonnanceFormUrgence(forms.ModelForm):
    class Meta:
        model = Ordonnance
        fields = ['diagnostic', 'observation']  # ⚠️ pas de medicaments ici
        widgets = {
            'diagnostic': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'observation': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# =================================================================
#
class CategorieForm(forms.ModelForm):
    class Meta:
        model = CategorieEquipement
        fields = ['nom']
        widgets = {
            'nom' : forms.TextInput(attrs={'class': 'form-control'})
        }

    def clean_nom(self):
        nom = self.cleaned_data.get('nom')
        # Vérification insensible à la casse (ex: "Lit" = "lit")
        if CategorieEquipement.objects.filter(nom__iexact=nom).exists():
            raise forms.ValidationError(f"La catégorie '{nom}' existe déjà.")
        return nom 


# ====================================================================
#
class EquipementForm(forms.ModelForm):
    class Meta:
        model = Equipement
        fields = ['nom', 'numero_serie', 'categorie', 'etat', 'service', 'date_acquisition']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_serie': forms.TextInput(attrs={'class': 'form-control'}),
            'categorie': forms.Select(attrs={'class': 'form-control'}), # Menu déroulant auto
            'etat': forms.Select(attrs={'class': 'form-control'}),
            'service': forms.Select(attrs={'class': 'form-control'}),
            'date_acquisition': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


# ========================================================================
#
class SigneVitalForm(forms.ModelForm):
    class Meta:
        model = SigneVital
        # On exclut les champs qui sont remplis automatiquement dans la vue
        exclude = ['patient', 'session', 'infirmier', 'date_prelevement', 'est_consulte']
        
        # Ajout de labels et de widgets pour le design
        widgets = {
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 37.5'}),
            'poids': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 70.0'}),
            'tension_arterielle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 120/80'}),
            'frequence_cardiaque': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'BPM'}),
            'frequence_respiratoire': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'RPM'}),
            'saturation_oxygene': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '%'}),
        }
        labels = {
            'temperature': 'Température (°C)',
            'poids': 'Poids (kg)',
            'tension_arterielle': 'Tension Artérielle (mmHg)',
            'frequence_cardiaque': 'Fréquence Cardiaque (BPM)',
            'frequence_respiratoire': 'Fréquence Respiratoire (RPM)',
            'saturation_oxygene': 'Saturation Oxygène (%)',
        }

# ==============================================================================
#
class HopitalForm(forms.ModelForm) :
    class Meta:
        model = Hopital

        fields = ['nomH']
        widgets = {
            'nomH' : forms.TextInput(attrs={'class':'form-control'}) 
        } 

    def clean_nomH(self):
        nomH = self.cleaned_data.get('nomH')

        if Hopital.objects.filter(nomH__iexact=nomH).exists():
            raise forms.ValidationError(f" {nomH}' existe déjà.") 
        return nomH 


# ============================================================================================
#
from django.contrib.auth.forms import PasswordChangeForm

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["old_password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Mot de passe actuel",
        })
        self.fields["new_password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nouveau mot de passe",
        })
        self.fields["new_password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirmer le nouveau mot de passe",
        })


# =================================================================================================
#
class RapportJournalierPersonnelForm(forms.ModelForm):
    class Meta:
        model = RapportJournalierPersonnel
        fields = [
            "type_rapport",
            "titre",
            "contenu",
            "service",
            "nombre_personnel_present",
            "nombre_personnel_absent",
            "incidents_signales",
            "recommandations",
        ]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 5, "class": "form-control"}),
            "recommandations": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "service": forms.Select(attrs={"class": "form-control"}),
            "type_rapport": forms.Select(attrs={"class": "form-control"}),
            "titre": forms.TextInput(attrs={"class": "form-control"}),
            "nombre_personnel_present": forms.NumberInput(attrs={"class": "form-control"}),
            "nombre_personnel_absent": forms.NumberInput(attrs={"class": "form-control"}),
            "incidents_signales": forms.NumberInput(attrs={"class": "form-control"}),
        }





class ChambreForm(forms.ModelForm):

  class Meta:
    model = Chambre
    fields = ['nom', 'type_chambre', 'est_active', 'hopital']


class LitForm(forms.ModelForm):

  class Meta:
    model = Lit
    fields = ['chambre', 'nom_lit', 'est_occupe', 'est_actif', 'hopital']

# -------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------
class LigneMedicamentForm(forms.ModelForm):
    class Meta:
        model = LigneMedicament
        fields = [
            'nom_medicament',
            'posologie',
            'duree',
            'quantite',
        ]

        widgets = {
            'nom_medicament': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex. Paracétamol 500 mg'
            }),
            'posologie': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex. 1 comprimé, 3 fois par jour'
            }),
            'duree': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex. 5 jours'
            }),
            'quantite': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1
            }),
        }


# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------
class DemandeExamenHospitalisationForm(forms.Form):
    CATEGORIES_EXAMENS = [
        ('', '--------- Choisir une catégorie ---------'),
        ('LABO', 'Laboratoire'),
        ('ECHO', 'Échographie'),
        ('RADIO', 'Radiologie'),
    ]

    categorie = forms.ChoiceField(
        choices=CATEGORIES_EXAMENS,
        label="Catégorie d'examen",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_categorie_examen',
            'required': True,
        })
    )

    prestation = forms.ModelChoiceField(
        queryset=Prestation.objects.none(),
        label="Examen demandé",
        empty_label="--------- Choisir d'abord une catégorie ---------",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_prestation_examen',
            'required': True,
        })
    )

    indication = forms.CharField(
        label="Indication clinique",
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': (
                'Exemple : Douleur abdominale persistante, '
                'fièvre, suspicion de paludisme...'
            ),
        })
    )

    quantite = forms.IntegerField(
        label="Quantité",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
        })
    )

    def __init__(self, *args, **kwargs):
        hopital = kwargs.pop('hopital', None)
        super().__init__(*args, **kwargs)

        categorie = None

        if self.is_bound:
            categorie = self.data.get('categorie')

        if categorie in ('LABO', 'ECHO', 'RADIO'):
            prestations = Prestation.objects.filter(
                hopital=hopital,
                categorie=categorie
            ).order_by('libelle')

            self.fields['prestation'].queryset = prestations

# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
# MISE EN JOUR 
#   - acte medical le 25/09/2026
#   - ici formulaire 
#
#
from django.contrib.auth import get_user_model
User = get_user_model()


class ActeMedicalForm(forms.ModelForm):
    # Ce champ sert uniquement à filtrer visuellement les prestations
    # dans le template avec JavaScript.
    # Il ne bloque plus la sélection de plusieurs catégories.
    categorie = forms.ChoiceField(
        required=False,
        label="Filtrer les prestations par catégorie",
        choices=[],
        widget=forms.Select(
            attrs={
                'class': 'form-select',
                'id': 'id_categorie',
            }
        )
    )

    prestations = forms.ModelMultipleChoiceField(
        queryset=Prestation.objects.none(),
        required=True,
        label="Prestations à réaliser",
        widget=forms.CheckboxSelectMultiple(
            attrs={
                'class': 'form-check-input prestation-checkbox',
            }
        )
    )

    class Meta:
        model = ActeMedical

        fields = [
            'prestations',
            'type_patient',
            'patient',
            'client_externe',
            'date_acte',
            'medecin',
            'statut',
            'observation',
        ]

        widgets = {
            'type_patient': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_type_patient',
                }
            ),

            'patient': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_patient',
                }
            ),

            'client_externe': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_client_externe',
                }
            ),

            'date_acte': forms.DateTimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local',
                },
                format='%Y-%m-%dT%H:%M',
            ),

            'medecin': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_medecin',
                }
            ),

            'statut': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'observation': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        hopital = kwargs.pop('hopital', None)
        user = kwargs.pop('user', None)
        fonction_key = kwargs.pop('fonction_key', None)

        super().__init__(*args, **kwargs)

        self.hopital = hopital

        self.fields['patient'].required = False
        self.fields['client_externe'].required = False
        self.fields['medecin'].required = False
        self.fields['observation'].required = False

        # Si aucun hôpital n'est disponible, on ne propose aucune donnée.
        if not hopital:
            self.fields['prestations'].queryset = Prestation.objects.none()
            self.fields['patient'].queryset = Patient.objects.none()
            self.fields['client_externe'].queryset = ClientExterne.objects.none()
            self.fields['medecin'].queryset = User.objects.none()
            return

        # Important :
        # Toutes les prestations de l'hôpital sont disponibles.
        # Elles peuvent appartenir à plusieurs catégories différentes.
        prestations_hopital = Prestation.objects.filter(
            hopital=hopital
        ).order_by(
            'categorie',
            'libelle'
        )

        self.fields['prestations'].queryset = prestations_hopital

        # Permet d'afficher les libellés : Consultation, Laboratoire, etc.
        # au lieu des codes : CONS, LABO, RADIO, etc.
        categories_dict = dict(Prestation.CATEGORIES)

        categories_existantes = (
            prestations_hopital
            .exclude(categorie__isnull=True)
            .exclude(categorie__exact='')
            .values_list('categorie', flat=True)
            .distinct()
            .order_by('categorie')
        )

        self.fields['categorie'].choices = [
            ('', '--------- Toutes les catégories ---------')
        ] + [
            (
                categorie,
                categories_dict.get(categorie, categorie)
            )
            for categorie in categories_existantes
        ]

        # Seuls les patients de l'hôpital connecté peuvent être choisis.
        self.fields['patient'].queryset = (
            Patient.objects
            .filter(hopital=hopital)
            .order_by('noms')
        )

        # Seuls les clients externes de l'hôpital connecté peuvent être choisis.
        self.fields['client_externe'].queryset = (
            ClientExterne.objects
            .filter(hopital=hopital)
            .order_by('noms')
        )

        # Recherche des utilisateurs ayant le rôle médecin dans l'hôpital.
        fonctions_medecins = (
            Fonction.objects
            .filter(
                hopital=hopital,
                fonctionKey__roleName__icontains='medecin',
            )
            .select_related('userKey')
        )

        medecins_users_ids = [
            fonction.userKey_id
            for fonction in fonctions_medecins
            if fonction.userKey_id
        ]

        # Si l'utilisateur connecté est médecin, il est automatiquement
        # sélectionné dans le champ médecin.
        est_medecin = (
            fonction_key
            and 'medecin' in fonction_key.lower()
            and user
        )

        if est_medecin:
            self.fields['medecin'].queryset = User.objects.filter(
                pk=user.pk
            )

            self.initial['medecin'] = user

        else:
            self.fields['medecin'].queryset = (
                User.objects
                .filter(pk__in=medecins_users_ids)
                .order_by('last_name', 'first_name')
            )

    def clean(self):
        cleaned_data = super().clean()

        prestations = cleaned_data.get('prestations')
        type_patient = cleaned_data.get('type_patient')
        patient = cleaned_data.get('patient')
        client_externe = cleaned_data.get('client_externe')

        # Au moins une prestation est obligatoire.
        if not prestations:
            self.add_error(
                'prestations',
                "Cochez au moins une prestation."
            )

        # Sécurité : les prestations envoyées doivent appartenir
        # à l'hôpital de l'utilisateur connecté.
        #
        # Elles peuvent cependant provenir de plusieurs catégories :
        # consultation + laboratoire + radiologie + soins, etc.
        if prestations and self.hopital:
            prestations_autre_hopital = prestations.exclude(
                hopital=self.hopital
            )

            if prestations_autre_hopital.exists():
                self.add_error(
                    'prestations',
                    "Une ou plusieurs prestations ne sont pas liées à votre hôpital."
                )

        # Cas du patient interne.
        if type_patient == 'INTERNE':
            if not patient:
                self.add_error(
                    'patient',
                    "Sélectionnez un patient interne."
                )

            if client_externe:
                self.add_error(
                    'client_externe',
                    "Ne sélectionnez pas de client externe pour un patient interne."
                )

        # Cas du client externe.
        elif type_patient == 'EXTERNE':
            if patient:
                self.add_error(
                    'patient',
                    "Ne sélectionnez pas de patient interne pour un client externe."
                )

        return cleaned_data


# ================================================================
# IMPORTANT :
# Cette classe doit être en dehors de ActeMedicalForm.
# Elle doit commencer totalement à gauche, sans espaces au début.
# ================================================================
class ClientExterneFormDeux(forms.ModelForm):
    class Meta:
        model = ClientExterne

        fields = [
            'noms',
            'sexe',
            'poids',
            'age',
            'telephone',
        ]

        widgets = {
            'noms': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nom complet du client externe',
                }
            ),

            'sexe': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),

            'poids': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex. 65 kg',
                }
            ),

            'age': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex. 32 ans',
                }
            ),

            'telephone': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ex. +243...',
                }
            ),
        }

# -----------------------------------------------------------------------------------
# 
#   - formulaire pour le paiement des actes medicaux
#   - le 29/09/2026
#
#
class PaiementActeForm(forms.Form):
  # ---- Montant que le client donne maintenant ----
  montant_verse = forms.DecimalField(
    label="Montant versé",
    min_value=0,
    max_digits=15,
    decimal_places=2,
    required=False,
    widget=forms.NumberInput(attrs={"class": "acte-input", "step": "0.01"}),
  )

  # ---- Réduction accordée (facultatif) ----
  montant_reduction = forms.DecimalField(
    label="Réduction",
    min_value=0,
    max_digits=10,
    decimal_places=2,
    required=False,
    widget=forms.NumberInput(attrs={"class": "acte-input", "step": "0.01"}),
  )

  # ---- Devise : CDF ou USD ----
  devise = forms.ChoiceField(
    label="Devise",
    choices=Paiement.CURRENCY,
    widget=forms.Select(attrs={"class": "acte-input"}),
  )

