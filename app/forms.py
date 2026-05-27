from django import forms 
from django.contrib.auth.models import User
from .models import *
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory


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

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        # On exclut les champs générés automatiquement ou en lecture seule
        exclude = ['code_patient', 'created_by', 'date_creation', 'date_modification']
        
        widgets = {
            'noms': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Nom complet du patient'
            }),
            'service': forms.Select(attrs={
                'class': 'form-control'
            }),
            'sexe': forms.Select(attrs={
                'class': 'form-control'
            }),
            'age': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ex: 25 ans'
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Adresse complète'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '+243 XXX XXX XXX'
            }),
            'fiche_payee': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        
        labels = {
            'noms': 'Nom et Prénom',
            'service': 'Service d\'accueil',
            'sexe': 'Sexe',
            'age': 'Âge',
            'adresse': 'Adresse',
            'telephone': 'Téléphone',
            'fiche_payee': 'Fiche de consultation payée',
        }

# ==============================================================================================


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