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
