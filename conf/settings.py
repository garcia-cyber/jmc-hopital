import os
from pathlib import Path

# --- CHEMINS ---
# BASE_DIR pointe vers la racine de ton projet (là où se trouve manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# --- SÉCURITÉ ---
# Sur Render, ajoute une variable d'environnement SECRET_KEY
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-temporary-key')

# DEBUG est False sur Render pour la sécurité
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# Autorise ton site Render et le local
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '.onrender.com']

# --- APPLICATIONS ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app',  # Ton application Medical-Moyanoli
    'crispy_forms',
    'crispy_bootstrap4',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"

# --- MIDDLEWARE ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Pour gérer les fichiers statiques sur Render
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'conf.urls'

# --- TEMPLATES ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'conf.wsgi.application'

# --- BASE DE DONNÉES (À LA RACINE) ---
# Le fichier db.sqlite3 sera créé directement à côté de manage.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# --- VALIDATION DES MOTS DE PASSE ---
AUTH_PASSWORD_VALIDATORS = [
    # {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    # {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    # {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    # {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNATIONALISATION ---
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Kinshasa'  # <--- Très important pour avoir l'heure de Kinshasa
USE_I18N = True
USE_L10N = True
USE_TZ = False

# Ajoutez-le juste ici
DATE_INPUT_FORMATS = [
    '%d/%m/%Y', # Format jour/mois/année (ex: 15/05/2026)
    '%Y-%m-%d', # Format standard base de données
]

# --- FICHIERS STATIQUES (CSS, JS) ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Whitenoise pour la compression en production
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --- FICHIERS MÉDIAS (Photos, Uploads) ---
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'


# MEDIA_URL = '/media/'
# MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# --- AUTHENTIFICATION --- 
LOGIN_REDIRECT_URL = '/dashboard/'
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/home/'

# --- SÉCURITÉ PROD ---
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = True
    X_FRAME_OPTIONS = 'DENY'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
