"""
Django settings for conf project.
Configured for Absolute Security in Production and Smooth Local Development using SQLite.
"""

import os
from pathlib import Path

# BASE_DIR pointe vers la racine du projet (là où se trouve manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# 🛠️ DÉTECTION DE L'ENVIRONNEMENT RENDER
IS_IN_PRODUCTION = os.environ.get('RENDER') is not None


# ==============================================================================
# SÉCURITÉ ET CLÉS
# ==============================================================================

# Si on est sur internet, on charge la clé secrète depuis Render.
# Si la variable n'existe pas, Django refuse de démarrer par sécurité.
if IS_IN_PRODUCTION:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("ERREUR DE SÉCURITÉ : La variable d'environnement 'SECRET_KEY' est manquante sur Render !")
else:
    # Clé de secours uniquement pour le développement sur ton PC
    SECRET_KEY = 'django-insecure-kag&&9kcessqfg^fe5la5rwbuq5v_3jd+7zpb)@vw=*=2k42$$'

# DEBUG est True sur ton PC, mais passe à False AUTOMATIQUEMENT sur internet.
# ⚠️ Ne jamais mettre True en production sous peine de divulguer ton code et tes mots de passe.
DEBUG = not IS_IN_PRODUCTION


# ==============================================================================
# HÔTES AUTORISÉS (ALLOWED HOSTS)
# ==============================================================================

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)


# ==============================================================================
# CONFIGURATIONS DE SÉCURITÉ ABSOLUE (PROD)
# ==============================================================================

if IS_IN_PRODUCTION:
    # 1. Forcer la redirection de tout le trafic HTTP vers HTTPS
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # 2. Protection contre le vol de session et de cookies (Attaques XSS/MitM)
    SESSION_COOKIE_SECURE = True       # Le cookie de session ne voyage qu'en HTTPS
    CSRF_COOKIE_SECURE = True          # Le cookie CSRF ne voyage qu'en HTTPS
    SESSION_COOKIE_HTTPONLY = True     # Interdit au JavaScript d'accéder au cookie de session
    CSRF_COOKIE_HTTPONLY = True        # Interdit au JavaScript d'accéder au cookie CSRF
    
    # 3. Politique SameSite pour bloquer les attaques CSRF (Cross-Site Request Forgery)
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

    # 4. En-têtes de sécurité stricts pour les navigateurs (HSTS)
    # Demande aux navigateurs de ne visiter ton site QU'EN HTTPS pendant 1 an
    SECURE_HSTS_SECONDS = 31536000  
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # 5. Protection du navigateur contre le reniflage de contenu (MIME Sniffing)
    SECURE_CONTENT_TYPE_NOSNIFF = True


# ==============================================================================
# APPLICATION & MIDDLEWARE
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app',  # Ton application principale
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ⚡ Gère et compresse tes fichiers CSS/JS en prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # Protection contre le détournement de clics
]

ROOT_URLCONF = 'conf.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'conf.wsgi.application'


# ==============================================================================
# BASE DE DONNÉES (SQLite locale demandée, sans dossier /data)
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ==============================================================================
# VALIDATION DES MOTS DE PASSE (Sécurité des comptes)
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==============================================================================
# INTERNATIONALISATION (Configuré pour la RDC / Kinshasa)
# ==============================================================================

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Kinshasa'
USE_I18N = True
USE_TZ = True


# ==============================================================================
# FICHIERS STATIQUES (CSS, JS, IMAGES)
# ==============================================================================

STATIC_URL = 'static/'

# Dossier de développement
STATICFILES_DIRS = [
    BASE_DIR / 'static'
]

# Dossier de production où WhiteNoise va puiser
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Optimisation et compression WhiteNoise pour la production
if IS_IN_PRODUCTION:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- AUTHENTIFICATION --- 
LOGIN_REDIRECT_URL = '/dashboard/'
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/home/'