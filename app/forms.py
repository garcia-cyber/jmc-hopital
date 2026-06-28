from django import forms
from django.contrib.auth.models import User
from .models import *
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from datetime import date

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
        fields = ['fonctionKey']
        labels = {
            'fonctionKey': 'Rôle / Poste',
                    }
        widgets = {
            'fonctionKey': forms.Select(attrs={'class': 'form-control'}),
            
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
        # 1. On ajoute 'valeur_normale' dans la liste des champs
        fields = ['libelle', 'categorie', 'prix', 'valeur_normale']
        
        # 2. On configure le widget Bootstrap pour le nouveau champ
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Goutte Épaisse'}),
            'categorie': forms.Select(attrs={'class': 'form-control', 'id': 'id_categorie'}),
            'prix': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'valeur_normale': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ex: 70-110 mg/dl ou Négatif',
                'id': 'id_valeur_normale'
            }),
        }

    def clean_libelle(self):
        """ Vérifie si une prestation avec ce libellé existe déjà (insensible à la casse) """
        libelle = self.cleaned_data.get('libelle')
        if Prestation.objects.filter(libelle__iexact=libelle).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cette prestation existe déjà dans votre catalogue.")
        return libelle

    # 3. Optionnel : Sécurité bonus au niveau du formulaire
    def clean(self):
        cleaned_data = super().clean()
        categorie = cleaned_data.get('categorie')
        valeur_normale = cleaned_data.get('valeur_normale')

        # Si l'utilisateur a écrit quelque chose mais que ce n'est pas du LABO, on nettoie la donnée
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
        # On exclut code_patient et created_by car ils sont gérés automatiquement dans le modèle
        fields = ['noms', 'sexe', 'age', 'adresse', 'telephone', 'service']
        
        widgets = {
            'noms': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom, Post-nom et Prénom'
            }),
            'sexe': forms.Select(attrs={
                'class': 'form-control'
            }),
            'age': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 25 ans ou 8 mois'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: +243...'
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Adresse de résidence'
            }),
            'service': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(PatientForm, self).__init__(*args, **kwargs)
        # Label par défaut pour la liste déroulante des services
        self.fields['service'].empty_label = "Sélectionner le service"

    def clean_telephone(self):
        telephone = self.cleaned_data.get('telephone')
        # Vérification si le téléphone existe déjà pour un autre patient
        # On exclut l'instance actuelle en cas de modification (self.instance.pk)
        if Patient.objects.filter(telephone=telephone).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà attribué à un autre patient.")
        return telephone

    def clean_noms(self):
        noms = self.cleaned_data.get('noms')
        if len(noms) < 3:
            raise forms.ValidationError("Le nom complet est trop court.")
        return noms.upper() # On force le nom en majuscule pour l'uniformité

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
            'motif': forms.Select(attrs={'class': 'form-control select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Détails de la dépense...'}),
            'montant': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 150'}),
            'devise': forms.Select(attrs={'class': 'form-control'}),
            'beneficiaire': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Fournisseur Mazout ou Nom de l\'agent'}),
        }


# ==================================================================================================
class TypeChambreForm(forms.ModelForm):
    class Meta:
        model = TypeChambre
        fields = ['libelle', 'prix_nuitée'] # Vérifiez que le nom correspond exactement au modèle
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
            'prix_nuitée': forms.NumberInput(attrs={'class': 'form-control'}),
        }

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
        fields = ['nom', 'contact_responsable']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de l\'entreprise'}),
            'contact_responsable': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numéro de téléphone'}),
        }

    def clean_nom(self):
        nom = self.cleaned_data.get('nom')
        # On vérifie si une entreprise avec ce nom existe déjà (insensible à la casse)
        if Entreprise.objects.filter(nom__iexact=nom).exists():
            raise ValidationError(f"L'entreprise '{nom}' est déjà enregistrée dans le système.")
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

class LotPharmacieForm(forms.ModelForm):
    class Meta:
        model = LotPharmacie
        # Remplace 'quantite' par les nouveaux noms de champs
        fields = ['produit', 'numero_lot', 'quantite_initiale', 'date_peremption']
        widgets = {
            'produit': forms.Select(attrs={'class': 'form-control'}),
            'numero_lot': forms.TextInput(attrs={'class': 'form-control'}),
            'quantite_initiale': forms.NumberInput(attrs={'class': 'form-control'}),
            'date_peremption': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


# ==========================================================================================
#
# 
class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['noms', 'sexe', 'age', 'adresse', 'telephone', 'entreprise', 'service']
        widgets = {
            'noms': forms.TextInput(attrs={'class': 'form-control'}),
            'sexe': forms.Select(attrs={'class': 'form-control'}),
            'age': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'entreprise': forms.Select(attrs={'class': 'form-control'}),
            'service': forms.Select(attrs={'class': 'form-control'}), # Liste déroulante des services
        }



# ===================================================================
#
#
class ClientExterneForm(forms.ModelForm):
    class Meta:
        model = ClientExterne
        fields = ['noms', 'sexe','poids','age','telephone']
        widgets = {
            'noms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom complet du client'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numéro de téléphone'}),
            'age': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Age du client'}),
            'sexe' : forms.Select(attrs={'class': 'form-control'}),
            'poids' : forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'poids'}), 
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