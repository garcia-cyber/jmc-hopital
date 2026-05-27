from django.contrib import admin
from django.utils import timezone
from .models import *

# Register your models here.

# ==========================================
# 1. CONFIGURATION & FINANCE
# ==========================================
@admin.register(ConfigurationHopital)
class ConfigurationHopitalAdmin(admin.ModelAdmin):
    list_display = ('taux_usd_en_cdf', 'derniere_mise_a_jour')
    
    def has_add_permission(self, request):
        # Empêche de créer plusieurs configurations de taux
        return not ConfigurationHopital.objects.exists()

# ==========================================
# 2. UTILISATEURS & RÔLES
# ==========================================
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['roleName']

@admin.register(Fonction)
class FonctionAdmin(admin.ModelAdmin):
    list_display = ['fonctionKey', 'userKey', 'autorisation']


@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'categorie', 'prix', 'valeur_normale')
    list_filter = ('categorie',)
    search_fields = ('libelle',)
    # Permet de modifier le prix directement depuis la liste
    list_editable = ('prix',)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'date_creation')
    search_fields = ('nom',)

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    # 'code_patient' est en lecture seule car généré par la méthode save()
    list_display = ('code_patient', 'noms', 'sexe', 'service', 'fiche_payee', 'date_creation')
    list_filter = ('service', 'sexe', 'fiche_payee')
    search_fields = ('code_patient', 'noms', 'telephone')
    readonly_fields = ('code_patient', 'date_creation', 'date_modification')
    
    # Organise les informations en sections pour plus de lisibilité
    fieldsets = (
        ('Identité', {
            'fields': ('code_patient', 'noms', 'sexe', 'age', 'telephone', 'adresse')
        }),
        ('Informations Médicales/Services', {
            'fields': ('service', 'fiche_payee')
        }),
        ('Système', {
            'fields': ('created_by', 'date_creation', 'date_modification'),
            'classes': ('collapse',) # Masque ces champs par défaut
        }),
    )
