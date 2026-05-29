from django.urls import path 
from .views import * 
from . import views


urlpatterns = [
    path('', home , name = 'home') ,
    path('login/' , login , name='login') , 
    path('deco/' , deco , name = 'deco') ,
    path('dashboard/' , dashboard , name = 'dashboard') ,

    # employe CRUD
     #
     path('employeAdd/', employeAdd , name = 'employeAdd'),
     path('employeRead/', employeRead , name = 'employeRead') ,
     path('ajouter-fonction/<int:user_id>/', views.attribuer_fonction, name='ajouter_fonction'),
     path('employe-poste/', views.liste_employe_poste, name='liste_employe_poste'),
     path('supprimer-poste/<int:fonction_id>/', views.supprimer_poste, name='supprimer_poste'),
     path('modifier-utilisateur/<int:user_id>/', views.modifier_utilisateur, name='modifier_user'),
     path('reinitialiser-password/<int:user_id>/', views.force_reinitialiser_pass, name='force_pass'),


     # ===================================
     # PATIENT
     path('patients/enregistrement/', views.enregistrement_patient, name='enregistrement_patient'),
     path('patients/modifier/<int:pk>/', views.modifier_patient, name='modifier_patient'),
     path('patients/liste/', views.liste_patients, name='liste_patients'),

     
     
     # ================================
     # PRESTATION 
     path('prestations/', views.gestion_prestations, name='gestion_prestations'),
     path('config/taux/', views.modifier_taux, name='modifier_taux'),
     path('prestations/modifier/<int:pk>/', views.modifier_prestation, name='modifier_prestation'),

     # =================================
     # SERVICE
     path('services/', views.gestion_services, name='gestion_services'),
     path('services/modifier/<int:pk>/', views.modifier_service, name='modifier_service'),

     # =================================
     # SIGNE VITAUX


    path('signes-vitaux/<int:patient_id>/', views.ajouter_signes_vitaux, name='ajouter_signes_vitaux'),
    path('signes-vitaux/liste/', views.liste_signes_vitaux, name='liste_signes_vitaux'),


    # ==================================
    # PAIEMENT DE LA FICHE
    path('payer-fiche/<int:patient_id>/', views.payer_fiche_partiel, name='payer_fiche_partiel'),
    
]
