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
    code_patient = models.CharField(max_length=20, unique=True, editable=False)
    noms = models.CharField(max_length=100)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='patients', null=True)
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Féminin')])
    age = models.CharField(max_length=30)
    adresse = models.TextField()
    telephone = models.CharField(max_length=20)
    fiche_payee = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='patients_crees')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.code_patient:
            # Remplacement de datetime.now() par timezone.now() pour la cohérence des fuseaux horaires
            annee = timezone.now().year
            prefixe = f"MLY-{annee}-"
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


