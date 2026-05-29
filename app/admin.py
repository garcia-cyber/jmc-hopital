from django.contrib import admin
from .models import *

# --- Enregistrement unique de chaque modèle ---

@admin.register(ConfigurationHopital)
class ConfigurationHopitalAdmin(admin.ModelAdmin):
    list_display = ('taux_usd_en_cdf', 'derniere_mise_a_jour')
    def has_add_permission(self, request):
        return not ConfigurationHopital.objects.exists()

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
    list_editable = ('prix',)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'date_creation')
    search_fields = ('nom',)

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('code_patient', 'noms', 'sexe', 'service', 'fiche_payee', 'date_creation')
    list_filter = ('service', 'sexe', 'fiche_payee')
    search_fields = ('code_patient', 'noms', 'telephone')
    readonly_fields = ('code_patient', 'date_creation', 'date_modification')

@admin.register(SigneVital)
class SigneVitalAdmin(admin.ModelAdmin):
    list_display = ('patient_noms', 'tension_sys', 'tension_dia', 'temperature', 'poids', 'date_enregistrement')
    def patient_noms(self, obj):
        return obj.patient.noms

class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 1

@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'montant_total', 'est_payee', 'date_creation')
    filter_horizontal = ('prestations',)
    inlines = [PaiementInline]

@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('facture', 'montant_paye', 'methode_paiement', 'date_paiement')