from django.db import models
from django.contrib.auth.models import User
import uuid
from decimal import Decimal  # Ajout crucial pour la sécurité des calculs financiers
from django.utils import timezone 
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.conf import settings 
from django.db import transaction 
from django.core.exceptions import ObjectDoesNotExist

# 0 Plusieurs Hopitaux
class Hopital(models.Model):
    nomH = models.CharField(max_length=30)
    

    def __str__(self):
        return self.nomH



# 1. CONFIGURATION ET BASE =============================================

class ConfigurationHopital(models.Model):
    taux_usd_en_cdf = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('2500.00'))
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration du Taux"

    # AJOUTEZ CE BLOC ICI
    @classmethod
    def get_taux(cls):
        """Récupère le taux actuel ou renvoie 2500 par défaut si aucune config n'existe."""
        config = cls.objects.first()
        if config:
            return config.taux_usd_en_cdf
        return Decimal('2500.00')

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
    hopital = models.ForeignKey(Hopital , on_delete=models.SET_NULL, null = True , related_name= 'hopital_fonction') 

    def __str__(self):
        if self.userKey and self.fonctionKey:
            return f"{self.userKey.username} - {self.fonctionKey.roleName}"
        return f"Autorisation: {self.autorisation}"

# 4. PRESTATIONS ===================================================
class Prestation(models.Model):
    CATEGORIES = [
        ('ADM', 'Administratif'), 
        ('CONS', 'Consultation'),
        ('LABO', 'Laboratoire'), 
        ('SOIN', 'Soins'), 
        ('ECHO', 'Échographie'), 
        ('RADIO', 'Radiologie'),
        ('SCAN', 'Scanner'),
        ('IRM', 'IRM'),
        ('CARDIO', 'Cardiographie'),
        ('GYNECO', 'Gynécographie'),
        ('ONCO', 'Oncologie'),
        ('ORTHO', 'Orthopédie'),
        ('DERMA', 'Dermatologie'),
        ('OPHTA', 'Ophtalmologie'),
        ('PSY', 'Psychiatrie'),
        ('KINE', 'Rééducation / Kinésithérapie'),
        ('MED', 'Acte Médical'),      
        ('CHIR', 'Acte Chirurgical'),
        ('CONS_MAT', 'Consultation Maternité'), 
        ('MAT', 'Forfait Maternité / Accouchement'), 
    ]
    
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    categorie = models.CharField(max_length=10, choices=CATEGORIES, verbose_name="Catégorie")
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Prix (USD)")
    hopital =  models.ForeignKey(Hopital, on_delete= models.SET_NULL , null = True , related_name = 'hopital_prestation') 
    valeur_normale = models.CharField(
        max_length=150, blank=True, null=True, 
        verbose_name="Valeur Normale / Référence (Labo uniquement)",
        help_text="Ex: 70-110 mg/dl, Négatif, etc."
    )

    def clean(self):
        # Nettoyage : Si ce n'est pas du Laboratoire, on vide la valeur normale
        if self.categorie != 'LABO':
            self.valeur_normale = None
            
    def __str__(self):
        return f"{self.libelle} ({self.get_categorie_display()}) - {self.prix} USD"

    class Meta:
        verbose_name = "Prestation"
        verbose_name_plural = "Prestations"


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
    # 1. Choix pour le type de patient
    TYPE_CHOICES = [
        ('SIMPLE', 'Patient Simple'),
        ('FIDELE', 'Patient Fidèle'),
        ('CONVENTIONNE', 'Patient Conventionné'),
    ]

    code_patient = models.CharField(max_length=20, unique=True, editable=False)
    noms = models.CharField(max_length=100)
    service = models.ForeignKey('Service', on_delete=models.PROTECT, related_name='patients', null=True)
    sexe = models.CharField(max_length=1, choices=[('M', 'Masculin'), ('F', 'Féminin')])
    age = models.CharField(max_length=30)
    adresse = models.TextField()
    telephone = models.CharField(max_length=20)
    hopital = models.ForeignKey(Hopital , on_delete=models.SET_NULL , related_name= 'patient_hopital', null = True) 
    
    # 2. Gestion financière
    type_patient = models.CharField(max_length=15, choices=TYPE_CHOICES, default='SIMPLE')
    a_carte_fidelite = models.BooleanField(default=False, verbose_name="Possède carte de fidélité")
    
    # Relation avec l'entreprise
    entreprise = models.ForeignKey(
        'Entreprise', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='patients', 
        verbose_name="Entreprise (si conventionné)"
    )
    
    fiche_payee = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='patients_crees')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    # --- MÉTHODES ---
    def save(self, *args, **kwargs):
        if not self.code_patient:
            annee = timezone.now().year
            prefixe = f"MLY-{annee}-"
            last_patient = Patient.objects.filter(code_patient__startswith=prefixe).order_by('id').last()
            new_id = int(last_patient.code_patient.split('-')[-1]) + 1 if last_patient else 1
            self.code_patient = f"{prefixe}{new_id:04d}"
        super().save(*args, **kwargs)

    def a_deja_ete_consulte(self):
        return Consultation.objects.filter(triage__patient=self).exists()

    def a_une_consultation_en_attente(self):
        return Consultation.objects.filter(triage__patient=self, consultation_payee=False).exists()

    def est_en_regle(self):
        if not self.fiche_payee:
            return False
        if self.a_deja_ete_consulte() and self.a_une_consultation_en_attente():
            return False
        return True

    def __str__(self):
        return f"{self.noms} ({self.code_patient}) - {self.get_type_patient_display()}"

# 6. PATIENT =======================================================
class Paiement(models.Model):
    CURRENCY = [('USD', 'USD'), ('CDF', 'CDF')]
    SERVICES = [
        ('FICHE', 'Fiche'), ('CONSULTATION', 'Consultation'), ('LABO', 'Labo'),
        ('ECHOGRAPHIE', 'Échographie'), ('RADIO', 'Radiographie'), ('SOIN', 'Soins'),
        ('MATERNITE', 'Maternité'), ('DECES', 'Actes de décès'), ('EXAMENS', 'Examens'),
        ('CHIRURGIE', 'Chirurgie'), ('CARTE_FIDELITE', 'Achat Carte de Fidélité'), 
        ('PHARMACIE', 'Pharmacie'), ('EXAMEN_EXTERNE', 'Examen Externe'),
        ('ENTREPRISE', 'Paiement Entreprise'), ('HOSPITALISATION', 'Hospitalisation')
    ]
    
    # Relations
    bloc_op = models.ForeignKey('BlocOperatoire', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, null=True, blank=True)
    demande_examen_externe = models.ForeignKey('DemandeExamenExterne', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    consultation = models.ForeignKey('Consultation', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    dossier_maternite = models.ForeignKey('Maternite', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    deces = models.ForeignKey('Deces', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    session = models.ForeignKey('SessionSoins', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    entreprise = models.ForeignKey('Entreprise', on_delete=models.CASCADE, null=True, blank=True, related_name='paiements')
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements')
    compte_rendu = models.OneToOneField('CompteRenduAccouchement', on_delete=models.SET_NULL, null=True, blank=True, related_name='paiement')

    # Champs de paiement
    service = models.CharField(max_length=20, choices=SERVICES)
    montant_verse = models.DecimalField(max_digits=15, decimal_places=2)
    montant_reduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    devise = models.CharField(max_length=3, choices=CURRENCY, default='USD')
    date_paiement = models.DateTimeField(default=timezone.now)
    caissier = models.ForeignKey(User, on_delete=models.PROTECT)
    reste_a_payer = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name="Dette / Reste à payer")

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # --- LOGIQUE SERVICES STANDARDS ---
        if self.service == 'FICHE' and self.patient:
            self.patient.fiche_payee = True
            self.patient.save()
        elif self.service == 'CONSULTATION' and self.consultation:
            self.consultation.consultation_payee = True
            self.consultation.save()
        elif self.service == 'CARTE_FIDELITE' and self.patient:
            self.patient.a_carte_fidelite = True
            self.patient.type_patient = 'FIDELE'
            self.patient.save()

        # --- LOGIQUE HOSPITALISATION ---
        if self.hospitalisation:
            total_due = Decimal(str(self.hospitalisation.cout_total))
            paiements_existants = self.hospitalisation.paiements.exclude(pk=self.pk)
            total_deja_verse = paiements_existants.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            total_deja_reduit = paiements_existants.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
            
            self.reste_a_payer = max(0, total_due - (total_deja_reduit + self.montant_reduction) - (total_deja_verse + self.montant_verse))
            self.hospitalisation.est_payee = (self.reste_a_payer <= 0)
            self.hospitalisation.save()

        # --- LOGIQUE SESSIONS SOINS ---
        if self.session:
            tous_paiements = self.session.paiements.exclude(pk=self.pk)
            total_deja_verse = tous_paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            total_deja_reduit = tous_paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
            self.reste_a_payer = max(0, self.session.total_a_payer - (total_deja_reduit + self.montant_reduction) - (total_deja_verse + self.montant_verse))
            self.session.est_payee = (self.reste_a_payer <= 0)
            self.session.save()

        # --- LOGIQUE EXAMEN EXTERNE ---
        if self.demande_examen_externe:
            total_due = self.demande_examen_externe.total_a_payer
            paiements_existants = self.demande_examen_externe.paiements.exclude(pk=self.pk)
            total_deja_verse = paiements_existants.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
            self.reste_a_payer = max(0, total_due - (total_deja_verse + self.montant_verse))
            if self.reste_a_payer <= 0:
                self.demande_examen_externe.statut = 'PAYE'
                self.demande_examen_externe.save()

        # --- LOGIQUE MATERNITE ---
        if self.service == 'MATERNITE' and self.dossier_maternite:
            if self.reste_a_payer <= 0:
                self.dossier_maternite.est_paye = True
                self.dossier_maternite.save()

        # --- LOGIQUE ENTREPRISE ---
        if self.service == 'ENTREPRISE' and self.entreprise:
            montant_usd = self.montant_verse
            if self.devise == 'CDF':
                from .models import ConfigurationHopital
                taux = ConfigurationHopital.get_taux()
                montant_usd = self.montant_verse / taux
            total_a_deduire = montant_usd + self.montant_reduction
            self.entreprise.dette_mensuelle = max(Decimal('0.00'), self.entreprise.dette_mensuelle - total_a_deduire)
            self.entreprise.save()

        super().save(*args, **kwargs)

        if is_new:
            from .models import Facture
            Facture.objects.create(
                paiement=self,
                numero_facture=f"FAC-{timezone.now().strftime('%y%m%d')}-{self.id}"
            )




# 8. FACTURE =======================================================
class Facture(models.Model):
    paiement = models.OneToOneField(Paiement, on_delete=models.CASCADE, related_name='facture_liee')
    numero_facture = models.CharField(max_length=50, unique=True)
    date_emission = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Facture {self.numero_facture} ({self.paiement.get_service_display()})"



# =================================================================================================================
class SessionSoins(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    date_creation = models.DateTimeField(auto_now_add=True)
    est_payee = models.BooleanField(default=False)
    
    @property
    def total_a_payer(self):
        return sum(item.prix_facture for item in self.items.all())

    def __str__(self):
        return f"Session de {self.patient.noms} du {self.date_creation.strftime('%d/%m/%Y')}"

class LigneFacture(models.Model):
    session = models.ForeignKey(SessionSoins, related_name="items", on_delete=models.CASCADE)
    prestation = models.ForeignKey(Prestation, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField(default=1)
    prix_facture = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self.prix_facture:
            self.prix_facture = self.prestation.prix * self.quantite
        super().save(*args, **kwargs)
        
# 9. SIGNES VITAUX ==================================================
class SigneVital(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    temperature = models.DecimalField(max_digits=4, decimal_places=1) 
    poids = models.DecimalField(max_digits=5, decimal_places=2) 
    tension_arterielle = models.CharField(max_length=10) 
    frequence_cardiaque = models.IntegerField()
    frequence_respiratoire = models.IntegerField(null=True, blank=True)
    saturation_oxygene = models.IntegerField(null=True, blank=True) 
    date_prelevement = models.DateTimeField(default=timezone.now)
    infirmier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    est_consulte = models.BooleanField(default=False)
    session = models.ForeignKey(SessionSoins, on_delete=models.CASCADE, related_name='signes_vitaux', null=True)

    def __str__(self):
        return f"Signes vitaux de {self.patient.noms} le {self.date_prelevement}"



# 10. CONSULTATION ==================================================
class Consultation(models.Model):
    # Propriété pour accéder facilement au patient
    @property
    def patient(self):
        return self.triage.patient

    triage = models.OneToOneField(SigneVital, db_index=True, on_delete=models.CASCADE)
    medecin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    motif_consultation = models.TextField(verbose_name="Motif")
    antecedent = models.CharField(max_length  = 30 , null = True , blank = True)
    histoire_maladie = models.TextField(verbose_name="Histoire de la maladie")
    examen_physique = models.TextField(verbose_name="Examen physique")
    complement_d_anamnese = models.CharField(max_length=200, null=True)
    hypothese_diagnostique = models.TextField(verbose_name="Hypothèse diagnostique")
    date_creation = models.DateTimeField(default=timezone.now)
    
    consultation_payee = models.BooleanField(default=False, verbose_name="Consultation payée")

    session = models.OneToOneField(SessionSoins, on_delete=models.CASCADE, null=True)
    

    @property
    def est_accessible(self):
        return self.session.est_payee if self.session else False

    def __str__(self):
        return f"Consultation de {self.triage.patient.noms} le {self.date_creation.strftime('%d/%m/%Y')}"

    @property
    def total_examens_a_payer(self):
        examens_lies = self.examens.all()
        return sum((ex.prestation.prix * ex.quantite) for ex in examens_lies if ex.prestation and ex.prestation.prix)

    @property
    def est_accessible(self):
        return self.consultation_payee

# ====================================================================
class ClientExterne(models.Model):
    # Juste le nécessaire pour identifier la personne de passage
    noms = models.CharField(max_length=150, verbose_name="Nom complet")
    TYPESEXE = [
        ('M', 'Masculin') , 
        ('F' , 'Feminin')
    ]
    sexe = models.CharField(max_length = 20 , choices = TYPESEXE , blank=True, null=True)
    poids = models.CharField(max_length = 15 , blank=True, null=True)
    age = models.CharField(max_length = 15 , blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.noms} (Externe)"
    
# 11. DEMANDE EXAMEN ===============================================
class DemandeExamen(models.Model):
    STATUT = [
        ('EN_ATTENTE', 'En attente'),
        ('TERMINE', 'Terminé'),
        ('ANNULE', 'Annulé'),
    ]
    
    consultation = models.ForeignKey('Consultation', related_name='examens', on_delete=models.CASCADE)
    prestation = models.ForeignKey('Prestation', on_delete=models.PROTECT)
    indication = models.TextField(blank=True, help_text="Note du médecin pour le technicien")
    resultat = models.TextField(blank=True, null=True)
    image_resultat = models.ImageField(upload_to='resultats_examens/', blank=True, null=True)
    technicien = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name='examens_realises', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    statut = models.CharField(max_length=20, choices=STATUT, default='EN_ATTENTE')
    date_demande = models.DateTimeField(default=timezone.now)
    date_realisation = models.DateTimeField(null=True, blank=True)
    quantite = models.PositiveIntegerField(default=1)

    def __str__(self):
        try:
            nom_patient = self.consultation.patient.noms  # ⚠️ adapte selon ton modèle Consultation
        except (AttributeError, ObjectDoesNotExist):
            nom_patient = "Patient inconnu"
        return f"{self.prestation.libelle} pour {nom_patient}"
    
    
class Ordonnance(models.Model):
    TYPE_CHOICES = [('URGENCE', 'Ordonnance d’Urgence'), ('DEFINITIVE', 'Ordonnance Définitive')]
    
    consultation = models.ForeignKey('Consultation', on_delete=models.CASCADE)
    date_prescrite = models.DateTimeField(default=timezone.now)
    type_ordonnance = models.CharField(max_length=20, choices=TYPE_CHOICES, default='URGENCE')
    diagnostic = models.CharField(max_length=255, blank=True)
    observation = models.TextField(blank=True)

    def __str__(self):
        # Utilisation d'une structure sécurisée pour éviter les erreurs de type DoesNotExist
        try:
            nom_patient = self.consultation.triage.patient.noms
        except (AttributeError, ObjectDoesNotExist):
            nom_patient = "Patient non identifié"
            
        return f"Ordonnance {self.get_type_ordonnance_display()} - {nom_patient}"

class Medicament(models.Model):
    # Utilisation des guillemets pour éviter l'erreur de référence circulaire
    ordonnance = models.ForeignKey('Ordonnance', on_delete=models.CASCADE, related_name='medicaments')
    nom = models.CharField(max_length=255)
    posologie = models.CharField(max_length=255)
    duree = models.CharField(max_length=100)
    
    STATUT_CHOICES = [('EN_COURS', 'En cours'), ('STOPPE', 'Stoppé')]
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_COURS')

    def __str__(self):
        return f"{self.nom} ({self.statut})"





# 13. LIGNE MEDICAMENT =============================================
class LigneMedicament(models.Model):
    STATUT_MEDOC = [
        ('EN_COURS', 'En cours'),
        ('STOPPE', 'Stoppé / Changé'),
    ]
    
    # Utilisez un related_name unique pour éviter les conflits
    ordonnance = models.ForeignKey(
        'Ordonnance', 
        related_name='lignes_medicaments', 
        on_delete=models.CASCADE
    )
    
    nom_medicament = models.CharField(max_length=200)
    posologie = models.CharField(max_length=200, help_text="ex: 1 tab 3 fois par jour")
    duree = models.CharField(max_length=100, help_text="ex: 5 jours")
    statut = models.CharField(max_length=20, choices=STATUT_MEDOC, default='EN_COURS')
    motif_arret = models.TextField(blank=True, null=True, help_text="Pourquoi le médecin a changé ce médicament")
    date_modification = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.nom_medicament} - {self.statut}"

# 14. DEPENSE ======================================================
class Depense(models.Model):
    CURRENCY = [('USD', 'USD'), ('CDF', 'CDF')]
    CATEGORIES = [
        ('LABO_REACTIF', 'Réactifs & Matériel Labo'),
        ('PHARMA_STOCK', 'Achat Stock Pharmacie'),
        ('CARBURANT', 'Carburant Générateur'),
        ('MAINTENANCE', 'Maintenance & Réparations'),
        ('ADMIN', 'Frais Administratifs & Bureau'),
        ('SALAIRE', 'Avances & Salaires Personnel'),
        ('AUTRE', 'Autre dépense'),
    ]

    motif = models.CharField(max_length=50, choices=CATEGORIES, verbose_name="Motif")
    description = models.TextField(blank=True, null=True)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    devise = models.CharField(max_length=3, choices=CURRENCY, default='USD')
    date_depense = models.DateTimeField(default=timezone.now)
    auteur = models.ForeignKey('auth.User', on_delete=models.PROTECT, verbose_name="Enregistré par")
    beneficiaire = models.CharField(max_length=150, blank=True, null=True, verbose_name="Bénéficiaire")

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"

    def clean(self):
        # Correction 1 : Retrait de l'import circulaire de Paiement (on l'appelle directement)
        # Correction 2 : Utilisation d'un entier 0 à la place du float 0.0 pour éviter le TypeError avec Decimal
        total_entrees = Paiement.objects.filter(devise=self.devise).aggregate(
            total=Sum('montant_verse')
        )['total'] or 0

        toutes_les_depenses = Depense.objects.filter(devise=self.devise)
        if self.pk:
            toutes_les_depenses = toutes_les_depenses.exclude(pk=self.pk)
            
        total_sorties = toutes_les_depenses.aggregate(total=Sum('montant'))['total'] or 0

        solde_disponible = total_entrees - total_sorties

        if self.montant > solde_disponible:
            raise ValidationError(
                f"Opération refusée. Solde de caisse insuffisant en {self.devise}. "
                f"Disponible : {solde_disponible:.2f} {self.devise}. "
                f"Montant demandé : {self.montant:.2f} {self.devise}."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Dépense {self.id} - {self.montant} {self.devise} ({self.get_motif_display()})"

# 15. HOSPITALISATION ET CHAMBRES ==================================
class TypeChambre(models.Model):
    libelle = models.CharField(max_length=100)
    # Utilisation de DecimalField pour la précision monétaire
    prix_nuitée = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return self.libelle

class Chambre(models.Model):
    # En ajoutant default="", Django ne vous posera plus la question
    nom = models.CharField(max_length=50, default="Sans nom") 
    type_chambre = models.ForeignKey(TypeChambre, on_delete=models.CASCADE)
    est_active = models.BooleanField(default=True)

    def __str__(self):
        return self.nom

class Lit(models.Model):
    chambre = models.ForeignKey(Chambre, related_name='lits', on_delete=models.CASCADE)
    nom_lit = models.CharField(max_length=50)
    est_occupe = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)


    def __str__(self) :
        return self.nom_lit

# =====================================================================
# hospitalisation 


class Hospitalisation(models.Model):
    # Statuts de l'hospitalisation
    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
        ('ANNULE', 'Annulé'),
    ]

    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='sejours')
    lit = models.ForeignKey('Lit', on_delete=models.PROTECT, related_name='occupations')
    date_entree = models.DateTimeField(default=timezone.now)
    date_sortie = models.DateTimeField(null=True, blank=True)
    motif_admission = models.TextField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_COURS')
    observations = models.TextField(blank=True, null=True)
    est_actif = models.BooleanField(default=True)
    
    # Champ pour suivre l'état de paiement en base
    est_payee = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        """
        Logique automatique : met à jour l'état du lit lors de l'enregistrement.
        """
        if self.statut == 'EN_COURS':
            self.lit.est_occupe = True
        elif self.statut == 'TERMINE' or self.statut == 'ANNULE':
            self.lit.est_occupe = False
            
        self.lit.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Hosp. {self.patient.noms} - Lit {self.lit.nom_lit}"

    @property
    def prix_par_jour(self):
        # Accède au prix défini dans le TypeChambre via la chambre du lit
        return self.lit.chambre.type_chambre.prix_nuitée

    @property
    def nombre_jours(self):
        """Calcule la durée de l'hospitalisation."""
        date_fin = self.date_sortie.date() if self.date_sortie else timezone.now().date()
        date_deb = self.date_entree.date()
        delta = date_fin - date_deb
        return max(1, delta.days)

    @property
    def cout_total(self):
        """Calcule le coût total basé sur le nombre de jours."""
        return Decimal(str(self.nombre_jours)) * Decimal(str(self.prix_par_jour))

    def get_reste_a_payer(self):
        """
        Calcule le reste à payer en tenant compte des paiements et réductions.
        L'utilisation de quantize(Decimal('0.01')) garantit une précision monétaire.
        """
        total_paye = self.paiements.aggregate(Sum('montant_verse'))['montant_verse__sum'] or 0
        total_reduit = self.paiements.aggregate(Sum('montant_reduction'))['montant_reduction__sum'] or 0
        
        reste = self.cout_total - (Decimal(str(total_paye)) + Decimal(str(total_reduit)))
        
        # On retourne max 0.00 et on arrondit à 2 décimales
        return max(Decimal('0.00'), reste.quantize(Decimal('0.01')))

    class Meta:
        verbose_name = "Hospitalisation"
        verbose_name_plural = "Hospitalisations"


# ==============================================================================================
# 
class SuiviQuotidien(models.Model):
    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE, related_name='suivis_journaliers')
    infirmier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    # Évolution quotidienne
    date_suivi = models.DateTimeField(auto_now_add=True)
    etat_general = models.TextField(verbose_name="État général du patient")
    constantes_du_jour = models.TextField(verbose_name="Constantes (TA, Pouls, Temp...)")
    soins_effectues = models.TextField(verbose_name="Soins et médicaments administrés")
    ta = models.CharField(max_length=20, verbose_name="TA", default="N/A")
    pouls = models.CharField(max_length=20, verbose_name="Pouls", default="N/A")
    temp = models.CharField(max_length=20, verbose_name="Temp (°C)", default="N/A")
    class Meta:
        verbose_name = "Suivi Quotidien"
        verbose_name_plural = "Suivis Quotidiens"
        ordering = ['-date_suivi']

    def __str__(self):
        return f"Suivi de {self.hospitalisation.patient.noms} le {self.date_suivi.strftime('%d/%m/%Y')}"


# =============================================================================================
#
class Kardex(models.Model):
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE, related_name='kardex_items')
    medicament = models.CharField(max_length=200 , null = True)
    posologie = models.CharField(max_length=100 , null = True)
    voie_administration = models.CharField(max_length=50 , null = True)
    date_prescription = models.DateTimeField(auto_now_add=True , null = True)
    est_actif = models.BooleanField(default=True , null = True)

    def __str__(self):
        return f"{self.medicament} - {self.hospitalisation.patient.noms}"

    def get_admin_pour_jour(self, date):
        return self.administrations.filter(date_admin=date).first()

class AdministrationKardex(models.Model):
    """Ce modèle enregistre si le médicament a été administré pour une date donnée"""
    kardex = models.ForeignKey(Kardex, on_delete=models.CASCADE, related_name='administrations')
    date_admin = models.DateField() # Exemple : 23/06/2026
    
    matin = models.BooleanField(default=False)
    midi = models.BooleanField(default=False)
    soir = models.BooleanField(default=False)

    class Meta:
        # Empêche d'avoir deux fois la même date pour le même médicament
        unique_together = ('kardex', 'date_admin')

# =======================================================================================
#
class RendezVous(models.Model):
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE)
    date_rdv = models.DateTimeField()
    motif = models.CharField(max_length=200)
    note = models.TextField(blank=True, null=True)
    
    # Nouveau champ pour enregistrer l'utilisateur
    enregistre_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    def est_urgent(self):
        # On calcule la différence entre la date du RDV et maintenant
        delta = self.date_rdv - timezone.now()
        # Alerte si le rendez-vous est dans moins de 24h (86400 secondes) 
        # et qu'il n'est pas encore passé
        return 0 < delta.total_seconds() < 86400

    def __str__(self):
        return f"RDV pour {self.hospitalisation.patient.noms} le {self.date_rdv}"

# =======================================================================================
# Entreprise
# =======================================================================================
class Entreprise(models.Model):
    nom = models.CharField(max_length=255, verbose_name="Nom de l'entreprise")
    contact_responsable = models.CharField(max_length=100, verbose_name="Numéro du responsable")
    date_enregistrement = models.DateTimeField(default=timezone.now, verbose_name="Date d'enregistrement")
    dette_mensuelle = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Dette mensuelle", 
        null = True , 
        blank = True
    )

    def __str__(self):
        return self.nom



## ==================================================================================
# model maternite 
class Maternite(models.Model):
    # Liste des groupes sanguins autorisés
    GROUPE_SANGUIN_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dossiers_maternite')
    date_admission = models.DateTimeField(auto_now_add=True)
    terme_prevu = models.DateField()
    
    # Utilisation des 'choices' ici
    groupe_sanguin = models.CharField(
        max_length=3, 
        choices=GROUPE_SANGUIN_CHOICES,
        default='O+'
    )
    
    enregistre_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    est_paye = models.BooleanField(default=False, verbose_name="Frais d'ouverture réglés")

    def __str__(self):
        return f"Maternité de {self.patient.noms} - {self.date_admission.strftime('%d/%m/%Y')}"


# =======================================================================================
#
# model ConsultationMaternite 
class ConsultationMaternite(models.Model):
    # Lien vers le dossier de maternité spécifique
    dossier_maternite = models.ForeignKey(Maternite, on_delete=models.CASCADE, related_name='consultations')
    
    date_consultation = models.DateTimeField(auto_now_add=True)
    poids = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Poids (kg)")
    tension_arterielle = models.CharField(max_length=10, verbose_name="Tension artérielle")
    hauteur_uterine = models.IntegerField(verbose_name="Hauteur utérine (cm)")
    bruits_cardiaques_foetaux = models.CharField(max_length=20, verbose_name="BCF")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes médicales")
    
    # Médecin/Infirmier ayant fait la consultation
    effectue_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Consultation du {self.date_consultation.strftime('%d/%m/%Y')} pour {self.dossier_maternite.patient.noms}"

    # Pour facturer automatiquement la consultation lors de sa saisie
    prestation = models.ForeignKey(
        Prestation, 
        on_delete=models.SET_NULL, 
        null=True, 
        limit_choices_to={'categorie': 'CONS_MAT'}
    )



# =======================================================================================================
#
class Deces(models.Model):
    # Gestion de l'identité du défunt
    patient = models.ForeignKey('Patient', on_delete=models.SET_NULL, null=True, blank=True)
    nom_patient_externe = models.CharField(max_length=255, null=True, blank=True)
    
    # Informations biographiques (du certificat)
    date_naissance = models.DateField(verbose_name="Date de naissance")
    lieu_naissance = models.CharField(max_length=100, verbose_name="Lieu de naissance")
    
    # Adresse du défunt
    adresse_avenue = models.CharField(max_length=100, verbose_name="Avenue")
    adresse_numero = models.CharField(max_length=20, verbose_name="Numéro")
    adresse_quartier = models.CharField(max_length=100, verbose_name="Quartier")
    adresse_commune = models.CharField(max_length=100, verbose_name="Commune")
    
    # Informations sur le décès
    date_deces = models.DateTimeField(verbose_name="Date et heure du décès")
    cause_deces = models.TextField(verbose_name="Cause du décès")
    
    # Informations médicales et certification
    etablissement = models.CharField(max_length=255, default="Hôpital Paradis Center")
    certifie_par = models.CharField(max_length=255, verbose_name="Nom du médecin")
    numero_cnom = models.CharField(max_length=50, verbose_name="Numéro CNOM du médecin")
    
    # Métadonnées
    notes = models.TextField(blank=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        nom = self.patient.nom if self.patient else self.nom_patient_externe
        return f"Décès : {nom} - {self.date_deces.strftime('%d/%m/%Y')}"

    class Meta:
        verbose_name = "Certificat de décès"
        verbose_name_plural = "Certificats de décès"



# ====================================================================
# ORIENTATION 
class Orientation(models.Model):
    DESTINATIONS = (
        ('PHARMACIE', 'Pharmacie'),
        ('HOSPITALISATION', 'Hospitalisation'),
        ('SALLE_SOINS', 'Salle de Soins'),
        ('BLOC_OPERATOIRE', 'Bloc Opératoire'),
        ('ACCOUCHEMENT', 'Accouchement'),  # Ajout de l'option ici
        ('SORTIE', 'Sortie/Retour à domicile'),
    )

    consultation = models.OneToOneField(
        Consultation, 
        on_delete=models.CASCADE, 
        related_name='orientation'
    )
    # QUI oriente ?
    medecin_orientateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='orientations_effectuees'
    )
    destination = models.CharField(max_length=50, choices=DESTINATIONS)
    observation = models.TextField(blank=True, null=True)
    date_orientation = models.DateTimeField(auto_now_add=True)
    est_admis = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.consultation.triage.patient.noms} orienté vers {self.get_destination_display()} par Dr. {self.medecin_orientateur.username}"



# ============================================================================================
#
#
class SoinOccasionnel(models.Model):
    paiement = models.ForeignKey(
        'Paiement', 
        on_delete=models.CASCADE, 
        related_name="soins_lies" # Permet de faire paiement.soins_lies.all()
    )
    nom_patient = models.CharField(max_length=200)
    prestation = models.ForeignKey('Prestation', on_delete=models.CASCADE)
    date_soin = models.DateTimeField(auto_now_add=True)
    effectue_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    est_effectue = models.BooleanField(default=False)

    def __str__(self):
        return f"Soin: {self.nom_patient} - {self.prestation.libelle}"


# =======================================================================================================================
#
# GESTION DE PHARMACIE 
#
# =======================================================================================================================

class ProduitPharmacie(models.Model):
    DEVISE_CHOICES = [('USD', 'USD'), ('CDF', 'CDF')]
    
    nom = models.CharField(max_length=200, verbose_name="Nom commercial / DCI")
    forme = models.CharField(max_length=100)
    dosage = models.CharField(max_length=50)
    categorie = models.CharField(max_length=100)
    unites_par_carton = models.PositiveIntegerField(default=1)
    devise = models.CharField(max_length=3, choices=DEVISE_CHOICES, default='USD')
    prix_achat_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    prix_vente_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    enregistre_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)
    stock_initial = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('nom', 'forme', 'dosage')

    def __str__(self):
        return f"{self.nom} - {self.dosage}"

    @property
    def prix_vente_cdf(self):
        return self.prix_vente_unitaire * ConfigurationHopital.get_taux()

# --- 3. LOT ---
class LotPharmacie(models.Model):
    produit = models.ForeignKey('ProduitPharmacie', related_name='les_lots', on_delete=models.CASCADE)
    numero_lot = models.CharField(max_length=100)
    quantite_initiale = models.PositiveIntegerField(default=0)
    quantite_actuelle = models.PositiveIntegerField(default=0)
    date_peremption = models.DateField()
    date_entree = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.quantite_actuelle = self.quantite_initiale
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['date_peremption']

    def __str__(self):
        return f"{self.produit.nom} | Lot: {self.numero_lot} | Stock: {self.quantite_actuelle}"


# --- 4. MOUVEMENT DE STOCK ---
class MouvementStock(models.Model):
    TYPE_MOUVEMENT = (('ENTREE', 'Entrée'), ('SORTIE', 'Sortie'), ('AJUSTEMENT', 'Ajustement'))
    
    lot = models.ForeignKey(LotPharmacie, on_delete=models.PROTECT, related_name='mouvements')
    type_mouvement = models.CharField(max_length=20, choices=TYPE_MOUVEMENT)
    quantite_unites = models.IntegerField()
    effectue_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    date_mouvement = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # CORRECTION : On ne modifie plus le stock ici.
        # Le mouvement est juste un historique.
        super().save(*args, **kwargs)

# --- 5. SORTIE PHARMACIE ---
class SortiePharmacie(models.Model):
    paiement = models.ForeignKey('Paiement', on_delete=models.CASCADE, related_name='les_sorties')
    lot = models.ForeignKey('LotPharmacie', on_delete=models.PROTECT, related_name='sorties')
    quantite_vendue = models.PositiveIntegerField()
    date_sortie = models.DateTimeField(auto_now_add=True)
    vendu_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def save(self, *args, **kwargs):
        # Utilisation de transaction pour éviter les erreurs de concurrence
        with transaction.atomic():
            # On récupère le lot à jour avec verrouillage (select_for_update)
            lot_verrouille = LotPharmacie.objects.select_for_update().get(pk=self.lot.pk)
            
            # Vérification de sécurité
            if lot_verrouille.quantite_actuelle < self.quantite_vendue:
                raise ValueError(f"Stock insuffisant pour le lot {self.lot.numero_lot}.")

            # Décrémentation unique
            lot_verrouille.quantite_actuelle -= self.quantite_vendue
            lot_verrouille.save(update_fields=['quantite_actuelle'])

            # Sauvegarde de la sortie
            super().save(*args, **kwargs)

            # Création du mouvement d'historique
            MouvementStock.objects.create(
                lot=self.lot, 
                type_mouvement='SORTIE', 
                quantite_unites=-self.quantite_vendue, 
                effectue_par=self.vendu_par
            )


# ******************************************************************************************************************** 
# 
# FIN DE LA PARTIE PHARMACIE 
#
# *********************************************************************************************************************


class BlocOperatoire(models.Model):
    STATUT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('EN_COURS', 'En cours'),
        ('TERMINE', 'Terminé'),
        ('ANNULE', 'Annulé'),
    ]

    # Relation avec la consultation pour garder l'historique médical
    consultation = models.OneToOneField('Consultation', on_delete=models.CASCADE, related_name='bloc_op')
    
    # Informations pré-opératoires
    constantes_pre_op = models.TextField(verbose_name="Constantes pré-opératoires")
    date_programmee = models.DateTimeField(default=timezone.now)
    
    # Informations opératoires (remplies après l'acte)
    acte_realise = models.TextField(blank=True, null=True, verbose_name="Compte-rendu opératoire")
    chirurgien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='chirurgies_realisees')
    
    # Suivi
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_ATTENTE')
    date_fin = models.DateTimeField(null=True, blank=True)

    prestation = models.ForeignKey(
        'Prestation', 
        on_delete=models.SET_NULL, 
        null=True, 
        limit_choices_to={'categorie': 'CHIR'},
        verbose_name="Type d'intervention"
    )

    def __str__(self):
        return f"Bloc: {self.consultation.triage.patient.noms} - {self.statut}"

# ===============================================================================
# ACCOUCHEMENT 


class CompteRenduAccouchement(models.Model):
    consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name='cr_accouchement')
    
    # Liaison avec la prestation (Forfait Maternité)
    prestation = models.ForeignKey(
        Prestation, 
        on_delete=models.SET_NULL, 
        null=True, 
        limit_choices_to={'categorie': 'MAT'},
        verbose_name="Forfait / Prestation Maternité"
    )
    
    type_accouchement = models.CharField(
        max_length=20, 
        choices=[('NATUREL', 'Accouchement Simple (Voie basse)'), ('CESARIENNE', 'Accouchement par Césarienne')]
    )
    details_acte = models.TextField(verbose_name="Détails de l'intervention / Rapport")
    date_creation = models.DateTimeField(auto_now_add=True)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"CR Accouchement - {self.consultation.triage.patient.noms}"
# ===================================================================================================

class FicheAccouchement(models.Model):
    consultation = models.ForeignKey(
        'Consultation',
        on_delete=models.CASCADE,
        related_name='fiches_accouchement'
    )
    prestation = models.ForeignKey(
        'Prestation',
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'categorie': 'MAT'},
        verbose_name="Forfait Maternité"
    )
    type_accouchement = models.CharField(
        max_length=20,
        choices=[('NATUREL', 'Accouchement Naturel'), ('CESARIENNE', 'Césarienne')],
        verbose_name="Type d'accouchement"
    )
    sexe_bebe = models.CharField(
        max_length=1,
        choices=[('M', 'Masculin'), ('F', 'Féminin')],
        verbose_name="Sexe du bébé"
    )
    poids_bebe = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Poids du bébé (kg)"
    )
    score_apgar = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Score Apgar"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes / Complications"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Auteur de la fiche"
    )

    def __str__(self):
        return f"Fiche Accouchement - {self.consultation.triage.patient.noms}"




class DemandeExamenExterne(models.Model):
    STATUT_CHOICES = [('EN_ATTENTE', 'En attente'), ('PAYE', 'Payé'), ('TERMINE', 'Terminé')]
    
    # On lie à la personne de passage, pas au Patient du système
    client = models.ForeignKey(ClientExterne, on_delete=models.CASCADE, related_name='demandes')
    prestations = models.ManyToManyField('Prestation', verbose_name="Examens choisis")
    
    total_a_payer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(max_length=15, choices=STATUT_CHOICES, default='EN_ATTENTE')
    date_demande = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Demande pour {self.client.noms} - {self.statut}"
    




class ExamenExterneResultat(models.Model):
    # Lien vers la demande globale (le contenant principal)
    demande = models.ForeignKey(
        'DemandeExamenExterne', 
        on_delete=models.CASCADE, 
        related_name='resultats_examens'
    )
    # L'examen spécifique (ex: Hémogramme, Échographie abdominale)
    prestation = models.ForeignKey('Prestation', on_delete=models.CASCADE)
    
    # Détails du résultat
    statut = models.CharField(
        max_length=20, 
        default='EN_ATTENTE', 
        choices=[('EN_ATTENTE', 'En attente'), ('TERMINE', 'Terminé')]
    )
    rapport = models.TextField(verbose_name="Résultat / Rapport d'examen")
    date_resultat = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Résultat: {self.prestation.libelle} - {self.demande.client.noms}"

    class Meta:
        verbose_name = "Résultat d'examen externe"
        verbose_name_plural = "Résultats des examens externes"





class OrdonnanceExterne(models.Model):
    """Ordonnance destinée à un client externe"""
    # Liaison avec le client externe au lieu du patient interne
    client = models.ForeignKey(ClientExterne, on_delete=models.CASCADE, related_name='ordonnances_externes')
    medecin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    note_globale = models.TextField(blank=True, null=True, help_text="Instructions générales")
    
    class Meta:
        verbose_name = "Ordonnance Client Externe"
        ordering = ['-date_creation']

    def __str__(self):
        return f"Ordonnance #{self.id} - {self.client.noms}"

class OrdonnanceItem(models.Model):
    """Détails des médicaments ou examens"""
    ordonnance = models.ForeignKey(OrdonnanceExterne, on_delete=models.CASCADE, related_name='items')
    designation = models.CharField(max_length=255, verbose_name="Médicament ou Examen")
    posologie = models.TextField(verbose_name="Posologie / Instructions")
    quantite = models.CharField(max_length=50, blank=True, null=True, verbose_name="Quantité")

    def __str__(self):
        return f"{self.designation} pour {self.ordonnance.client.noms}"


# ========================================================================================
#
class OrdonnanceSortie(models.Model):
    hospitalisation = models.OneToOneField(
        Hospitalisation, 
        on_delete=models.CASCADE, 
        related_name='ordonnance_sortie'
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    
    # Contenu détaillé
    prescriptions = models.TextField(verbose_name="Médicaments prescrits")
    recommandations = models.TextField(verbose_name="Conseils et hygiène de vie")
    date_prochain_rdv = models.DateField(null=True, blank=True, verbose_name="Date de suivi")
    
    # Médecin émetteur (optionnel, selon votre gestion des utilisateurs)
    medecin_nom = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Sortie - {self.hospitalisation.patient.noms}"

    class Meta:
        verbose_name = "Ordonnance de Sortie"
        verbose_name_plural = "Ordonnances de Sortie"



# ==============================================================================
#
#
class CategorieEquipement(models.Model):
    """Ex: Lits, Respirateurs, Moniteurs"""
    nom = models.CharField(max_length=100)

    def __str__(self):
        return self.nom

class Equipement(models.Model):
    ETAT_CHOICES = [
        ('bon', 'En bon état'),
        ('panne', 'En panne'),
        ('maintenance', 'En maintenance'),
        ('reforme', 'À réformer'),
    ]

    nom = models.CharField(max_length=100)
    numero_serie = models.CharField(max_length=100, unique=True)
    categorie = models.ForeignKey(CategorieEquipement, on_delete=models.CASCADE)
    etat = models.CharField(max_length=20, choices=ETAT_CHOICES, default='bon')
    
    # Lien vers votre Service existant (en supposant qu'il soit importé)
    # Remplacez 'votre_app.Service' par le chemin réel de votre modèle
    service = models.ForeignKey('Service', on_delete=models.SET_NULL, null=True, blank=True)
    
    date_acquisition = models.DateField()
    date_derniere_maintenance = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.nom} - {self.numero_serie}"

    class Meta:
        verbose_name = "Équipement"
        verbose_name_plural = "Équipements"

class InterventionMaintenance(models.Model):
    """Historique des pannes et réparations"""
    equipement = models.ForeignKey(Equipement, on_delete=models.CASCADE, related_name='maintenances')
    description_panne = models.TextField()
    date_panne = models.DateTimeField(auto_now_add=True)
    date_reparation = models.DateTimeField(null=True, blank=True)
    repare = models.BooleanField(default=False)
    technicien = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Maintenance sur {self.equipement.nom} - {'Réparé' if self.repare else 'En cours'}"