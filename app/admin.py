from django.contrib import admin
from django.utils import timezone
from .models import *

# 1. CONFIGURATION ET ADMINISTRATION ====================================
@admin.register(ConfigurationHopital)
class ConfigurationHopitalAdmin(admin.ModelAdmin):
    list_display = ('taux_usd_en_cdf', 'derniere_mise_a_jour')

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('roleName',)

@admin.register(Fonction)
class FonctionAdmin(admin.ModelAdmin):
    list_display = ('userKey', 'fonctionKey', 'autorisation')

# 2. GESTION DES PATIENTS ET SERVICES ==================================
@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('code_patient', 'noms', 'sexe', 'type_patient', 'est_en_regle_display')
    list_filter = ('type_patient', 'sexe', 'service')
    search_fields = ('noms', 'code_patient')

    # On crée une méthode spécifique pour l'affichage dans l'admin
    @admin.display(description="En règle", boolean=True)
    def est_en_regle_display(self, obj):
        # Appelle la méthode définie dans votre models.py
        return obj.est_en_regle()

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'date_creation')

@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    list_display = ('nom', 'contact_responsable')

# 3. CONSULTATIONS ET SOINS ============================================
@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'medecin', 'consultation_payee')
    list_filter = ('consultation_payee', 'date_creation')

@admin.register(SigneVital)
class SigneVitalAdmin(admin.ModelAdmin):
    list_display = ('patient', 'temperature', 'tension_arterielle', 'date_prelevement')

@admin.register(DemandeExamen)
class DemandeExamenAdmin(admin.ModelAdmin):
    list_display = ('prestation', 'consultation', 'statut', 'date_demande')
    list_filter = ('statut', 'prestation__categorie')

@admin.register(Orientation)
class OrientationAdmin(admin.ModelAdmin):
    list_display = (
        'get_patient_noms', 
        'destination', 
        'medecin_orientateur', 
        'date_orientation', 
        'est_admis'
    )
    list_filter = ('destination', 'est_admis', 'date_orientation')
    search_fields = ('consultation__triage__patient__noms',)
    
    def get_patient_noms(self, obj):
        return obj.consultation.triage.patient.noms
    get_patient_noms.short_description = 'Patient'

admin.site.register(Medicament)
admin.site.register(LigneMedicament)

# 4. FINANCES ET FACTURATION ===========================================
@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'service', 'montant_verse', 'devise', 'caissier', 'date_paiement')
    list_filter = ('service', 'devise', 'date_paiement')
    search_fields = ('patient__noms',)

@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('numero_facture', 'paiement', 'date_emission')

@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ('motif', 'montant', 'devise', 'auteur', 'date_depense')
    list_filter = ('motif', 'devise')

# 5. HOSPITALISATION ET MATERNITÉ ======================================
@admin.register(Hospitalisation)
class HospitalisationAdmin(admin.ModelAdmin):
    list_display = ('patient', 'lit', 'statut', 'cout_total')
    list_filter = ('statut',)

@admin.register(SuiviQuotidien)
class SuiviQuotidienAdmin(admin.ModelAdmin):
    list_display = ('hospitalisation', 'date_suivi', 'infirmier')

admin.site.register([TypeChambre, Chambre, Lit])
admin.site.register(Maternite)
admin.site.register(ConsultationMaternite)

# 6. PHARMACIE ET AUTRES ===============================================


@admin.register(ProduitPharmacie)
class ProduitPharmacieAdmin(admin.ModelAdmin):
    list_display = (
        'nom',
        'forme',
        'dosage',
        'categorie',
        'prix_achat_unitaire',
        'prix_vente_unitaire',
        'devise',
        'date_enregistrement'
    )
    list_filter = ('categorie', 'devise')
    search_fields = ('nom', 'forme', 'dosage')
    ordering = ('nom',)




@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = (
        'lot',
        'type_mouvement',
        'quantite_unites',
        'effectue_par',
        'date_mouvement'
    )
    list_filter = (
        'type_mouvement',
        'date_mouvement'
    )
    search_fields = (
        'lot__produit__nom',
        'lot__numero_lot'
    )
    ordering = ('-date_mouvement',)


@admin.register(SortiePharmacie)
class SortiePharmacieAdmin(admin.ModelAdmin):
    list_display = (
        'paiement',
        'lot',
        'quantite_vendue',
        'vendu_par',
        'date_sortie'
    )
    list_filter = ('date_sortie',)
    search_fields = (
        'lot__produit__nom',
        'lot__numero_lot'
    )
    ordering = ('-date_sortie',)

@admin.register(LotPharmacie)
class LotPharmacieAdmin(admin.ModelAdmin):
    # 'quantite_actuelle' est affiché ici pour voir si le stock est bien à 16
    list_display = ('produit', 'numero_lot', 'quantite_initiale', 'quantite_actuelle', 'date_peremption')
    list_filter = ('produit',)
    readonly_fields = ('quantite_actuelle',)

admin.site.register(Prestation)
admin.site.register(Deces)
admin.site.register(SoinOccasionnel)

@admin.register(BlocOperatoire)
class BlocOperatoireAdmin(admin.ModelAdmin):
    # Colonnes affichées dans la liste
    list_display = (
        'get_patient_noms', 
        'prestation', 
        'chirurgien', 
        'statut', 
        'date_programmee', 
        'date_fin'
    )
    
    # Filtres latéraux pour trier rapidement
    list_filter = ('statut', 'date_programmee', 'prestation__categorie')
    
    # Barre de recherche (utilise les relations pour chercher par nom de patient)
    search_fields = ('consultation__triage__patient__noms', 'chirurgien__username')
    
    # Rendre les champs en lecture seule pour éviter des erreurs après la saisie
    readonly_fields = ('date_fin',)
    
    # Organiser les champs en groupes pour une meilleure lisibilité
    fieldsets = (
        ('Informations Patient', {
            'fields': ('consultation', 'constantes_pre_op')
        }),
        ('Détails Opératoires', {
            'fields': ('prestation', 'acte_realise', 'chirurgien')
        }),
        ('Suivi', {
            'fields': ('statut', 'date_programmee', 'date_fin')
        }),
    )

    # Méthode pour afficher le nom du patient dans la liste
    def get_patient_noms(self, obj):
        return obj.consultation.triage.patient.noms
    get_patient_noms.short_description = 'Patient'
    get_patient_noms.admin_order_field = 'consultation__triage__patient__noms'


# =========================================================================================================

@admin.register(CompteRenduAccouchement)
class CompteRenduAccouchementAdmin(admin.ModelAdmin):
    # Configuration de l'affichage dans la liste
    list_display = (
        'get_patient_name', 
        'type_accouchement', 
        'prestation', 
        'auteur', 
        'date_creation'
    )
    
    # Ajout de filtres pour faciliter la recherche
    list_filter = ('type_accouchement', 'date_creation', 'auteur')
    
    # Barre de recherche par nom de patient ou détails
    search_fields = ('consultation__triage__patient__noms', 'details_acte')
    
    # Organisation du formulaire de modification
    readonly_fields = ('date_creation',)
    fields = (
        'consultation', 
        'prestation', 
        'type_accouchement', 
        'details_acte', 
        'auteur', 
        'date_creation'
    )

    # Méthode pour afficher le nom du patient dans la liste (accès via la relation consultation)
    def get_patient_name(self, obj):
        return obj.consultation.triage.patient.noms
    get_patient_name.short_description = 'Patient'

    # Optimisation des requêtes pour éviter de trop nombreuses requêtes SQL
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'consultation__triage__patient', 
            'prestation', 
            'auteur'
        )




# 1. Inline pour ajouter les prestations directement dans la Session de Soins
class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 1  # Nombre de lignes vides affichées par défaut
    readonly_fields = ('prix_facture',) # Le prix est calculé automatiquement

@admin.register(SessionSoins)
class SessionSoinsAdmin(admin.ModelAdmin):
    list_display = ('patient', 'date_creation', 'total_a_payer', 'est_payee')
    list_filter = ('est_payee', 'date_creation')
    search_fields = ('patient__noms',)
    inlines = [LigneFactureInline]  # Permet de gérer les prestations dans la page Session

@admin.register(LigneFacture)
class LigneFactureAdmin(admin.ModelAdmin):
    list_display = ('session', 'prestation', 'quantite', 'prix_facture')
    readonly_fields = ('prix_facture',)

# ======================================================================================
# 
#
# INFORMATION DU CLIENT EXTERNE 

@admin.register(ClientExterne)
class ClientExterneAdmin(admin.ModelAdmin):
    list_display = ('noms', 'sexe','poids','age','telephone', 'date_enregistrement')
    search_fields = ('noms', 'telephone')
    list_filter = ('date_enregistrement',)
    ordering = ('-date_enregistrement',)

@admin.register(DemandeExamenExterne)
class DemandeExamenExterneAdmin(admin.ModelAdmin):
    list_display = ('client', 'get_prestations', 'total_a_payer', 'statut', 'date_demande')
    list_filter = ('statut', 'date_demande')
    search_fields = ('client__noms', 'client__telephone')
    
    # Permet de voir facilement les prestations sélectionnées
    filter_horizontal = ('prestations',) 
    
    # Méthode pour afficher la liste des prestations dans la table admin
    def get_prestations(self, obj):
        return ", ".join([p.libelle for p in obj.prestations.all()])
    get_prestations.short_description = 'Examens demandés'

    # Optionnel : Calculer le total automatiquement si tu veux qu'il s'affiche
    readonly_fields = ('total_a_payer',)

# ====================================================================================
#
#
class ExamenExterneResultatInline(admin.TabularInline):
    model = ExamenExterneResultat
    extra = 0  # Ne pas ajouter de lignes vides inutiles
    readonly_fields = ('date_resultat',)


@admin.register(ExamenExterneResultat)
class ExamenExterneResultatAdmin(admin.ModelAdmin):
    list_display = ('demande', 'prestation', 'statut', 'date_resultat')
    list_filter = ('statut', 'prestation__categorie')
    search_fields = ('demande__client__noms', 'prestation__libelle')


# ==================================================================================
#
#
@admin.register(FicheAccouchement)
class FicheAccouchementAdmin(admin.ModelAdmin):
    list_display = (
        'consultation',
        'prestation',
        'type_accouchement',
        'sexe_bebe',
        'poids_bebe',
        'score_apgar',
        'date_creation',
        'auteur'
    )
    list_filter = (
        'type_accouchement',
        'sexe_bebe',
        'date_creation',
        'prestation'
    )
    search_fields = (
        'consultation__triage__patient__noms',
        'notes',
        'auteur__username'
    )
    ordering = ('-date_creation',)
    date_hierarchy = 'date_creation'
    readonly_fields = ('date_creation',)

    fieldsets = (
        ("Informations générales", {
            'fields': ('consultation', 'prestation', 'type_accouchement', 'auteur')
        }),
        ("Données bébé", {
            'fields': ('sexe_bebe', 'poids_bebe', 'score_apgar')
        }),
        ("Notes", {
            'fields': ('notes',)
        }),
        ("Métadonnées", {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )

# =============================================================
# 
#
#

class OrdonnanceItemInline(admin.TabularInline):
    model = OrdonnanceItem
    extra = 1  # Nombre de lignes vides affichées par défaut pour ajouter des items
    min_num = 1 # Oblige à avoir au moins un item pour valider

@admin.register(OrdonnanceExterne)
class OrdonnanceExterneAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'medecin', 'date_creation')
    list_filter = ('date_creation', 'medecin')
    search_fields = ('client__noms', 'medecin__username')
    readonly_fields = ('date_creation',)
    
    # Intégration de l'inline
    inlines = [OrdonnanceItemInline]

    fieldsets = (
        ('Informations Générales', {
            'fields': ('client', 'medecin', 'date_creation')
        }),
        ('Notes', {
            'fields': ('note_globale',)
        }),
    )

# Enregistrement optionnel si tu veux gérer les items individuellement hors de l'ordonnance
@admin.register(OrdonnanceItem)
class OrdonnanceItemAdmin(admin.ModelAdmin):
    list_display = ('designation', 'ordonnance', 'posologie', 'quantite')
    search_fields = ('designation', 'ordonnance__client__noms')


# ====================================================================
#

class AdministrationKardexInline(admin.TabularInline):
    """Permet de voir et modifier les administrations directement dans la fiche du médicament"""
    model = AdministrationKardex
    extra = 1  # Ajoute une ligne vide par défaut pour une nouvelle saisie
    fields = ('date_admin', 'matin', 'midi', 'soir')
    ordering = ('-date_admin',)

@admin.register(Kardex)
class KardexAdmin(admin.ModelAdmin):
    list_display = ('medicament', 'patient_nom', 'posologie', 'est_actif', 'date_prescription')
    list_filter = ('est_actif', 'date_prescription')
    search_fields = ('medicament', 'hospitalisation__patient__noms')
    inlines = [AdministrationKardexInline] # Lie les administrations au médicament

    def patient_nom(self, obj):
        return obj.hospitalisation.patient.noms
    patient_nom.short_description = 'Patient'

@admin.register(AdministrationKardex)
class AdministrationKardexAdmin(admin.ModelAdmin):
    list_display = ('kardex', 'date_admin', 'matin', 'midi', 'soir')
    list_filter = ('date_admin', 'matin', 'midi', 'soir')
    search_fields = ('kardex__medicament', 'kardex__hospitalisation__patient__noms')
    date_hierarchy = 'date_admin' # Ajoute une navigation par date en haut de page

# ====================================================================
#
@admin.register(RendezVous)
class RendezVousAdmin(admin.ModelAdmin):
    list_display = ('hospitalisation', 'date_rdv', 'enregistre_par')
    list_filter = ('date_rdv',)
    search_fields = ('hospitalisation__patient__noms', 'motif')
    readonly_fields = ('enregistre_par',)

    def save_model(self, request, obj, form, change):
        # Enregistre automatiquement l'utilisateur connecté comme auteur du RDV
        if not obj.enregistre_par:
            obj.enregistre_par = request.user
        super().save_model(request, obj, form, change)

# ====================================================================
#
@admin.register(OrdonnanceSortie)
class OrdonnanceSortieAdmin(admin.ModelAdmin):
    # Affiche les colonnes dans la liste des ordonnances
    list_display = ('hospitalisation', 'medecin_nom', 'date_creation', 'date_prochain_rdv')
    
    # Ajoute un filtre sur la droite pour retrouver rapidement les ordonnances
    list_filter = ('date_creation', 'date_prochain_rdv')
    
    # Barre de recherche pour trouver par nom de patient (via la relation hospitalisation)
    search_fields = ('hospitalisation__patient__noms', 'medecin_nom')
    
    # Organisation des champs lors de l'édition
    fieldsets = (
        ('Informations Générales', {
            'fields': ('hospitalisation', 'medecin_nom')
        }),
        ('Contenu Médical', {
            'fields': ('prescriptions', 'recommandations', 'date_prochain_rdv')
        }),
    )

    # Lecture seule pour les champs créés automatiquement
    readonly_fields = ('date_creation',)



# ============================================================================================
#
@admin.register(CategorieEquipement)
class CategorieEquipementAdmin(admin.ModelAdmin):
    list_display = ['nom']
    search_fields = ['nom']

class InterventionInline(admin.TabularInline):
    """Permet de voir l'historique des pannes directement dans la fiche équipement"""
    model = InterventionMaintenance
    extra = 0
    readonly_fields = ['date_panne']

@admin.register(Equipement)
class EquipementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'numero_serie', 'categorie', 'etat', 'service', 'date_derniere_maintenance']
    list_filter = ['etat', 'categorie', 'service']  # Filtres latéraux pour trier rapidement
    search_fields = ['nom', 'numero_serie']
    list_editable = ['etat']  # Permet de changer l'état directement depuis la liste
    inlines = [InterventionInline] # Intègre l'historique des pannes dans la page de l'équipement
    
    # Remplissage automatique des champs de date ou autre si besoin
    fieldsets = (
        ('Informations Générales', {
            'fields': ('nom', 'numero_serie', 'categorie', 'service', 'date_acquisition')
        }),
        ('État opérationnel', {
            'fields': ('etat', 'date_derniere_maintenance')
        }),
    )

@admin.register(InterventionMaintenance)
class InterventionMaintenanceAdmin(admin.ModelAdmin):
    list_display = ['equipement', 'date_panne', 'repare', 'technicien']
    list_filter = ['repare', 'date_panne']
    search_fields = ['equipement__nom', 'technicien']
    list_editable = ['repare']