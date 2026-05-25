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