"""
Django settings for conf project.
Configured for Local Development and Render Deployment using SQLite.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# 🛠️ DÉTECTION DE L'ENVIRONNEMENT RENDER
# Si la variable 'RENDER' existe, on est en production sur internet. Sinon, on est en local.
IS_IN_PRODUCTION = os.environ.get('RENDER') is not None

# SECURITY WARNING: keep the secret key used in production secret!
# En local, utilise la clé par défaut. Sur Render, charge une clé secrète depuis l'environnement.
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-kag&&9kcessqfg^fe5la5rwbuq5v_3jd+7zpb)@vw=*=2k42$$')

# SECURITY WARNING: don't run with debug turned on in production!
# True en local, False automatiquement sur Render.
DEBUG = not IS_IN_PRODUCTION

# Autoriser localhost en local, et votre sous-domaine Render sur internet
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # ⚡ AJOUTÉ POUR LES STYLES (CSS/JS) SUR RENDER
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

if IS_IN_PRODUCTION:
    # 📁 Configuration Render avec un disque persistant pour ne JAMAIS perdre vos données SQLite
    # Remarque : Vous devez lier un "Persistent Disk" monté sur `/data` sur votre service Render.
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': '/data/db.sqlite3',
        }
    }
else:
    # 💻 Configuration Classique en Local
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# Passé en Français pour correspondre aux besoins de votre ERP
LANGUAGE_CODE = 'fr-fr'

TIME_ZONE = 'Africa/Kinshasa' # Fuseau horaire adapté pour la RDC

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

# Dossier où vous mettez vos fichiers statiques pendant le développement
STATICFILES_DIRS = [
    BASE_DIR / 'static'
]

# Dossier où Django va rassembler tous les fichiers statiques lors du déploiement
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Optimisation du stockage pour WhiteNoise en production
if IS_IN_PRODUCTION:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'