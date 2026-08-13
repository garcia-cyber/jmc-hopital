import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-temporary-key")
# Utiliser True par défaut pour le développement local
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"


ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "jmc-hopital.onrender.com",
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app",
    "crispy_forms",
    "crispy_bootstrap4",
    "channels",
    "video",
    "csp",
    'axes',
    'honeypot',
]


# Backend d'authentification pour django-axes
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',  # <-- doit être en premier
    'django.contrib.auth.backends.ModelBackend',
]


CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"
ASGI_APPLICATION = "conf.asgi.application"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'honeypot.middleware.HoneypotMiddleware',
    'axes.middleware.AxesMiddleware',  # <-- DOIT ÊTRE EN DERNIER
]


# bloquage des ip apres plusieurs tentatives
AXES_FAILURE_LIMIT = 5  # 5 tentatives max
AXES_COOLOFF_TIME = 1  # 1 heure de blocage
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True
AXES_RESET_ON_SUCCESS = True


ROOT_URLCONF = "conf.urls"
WSGI_APPLICATION = "conf.wsgi.application"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# --- CONFIGURATION BASE DE DONNÉES ---
DATABASE_URL = os.environ.get("DATABASE_URL")


if DATABASE_URL:
    # Production (Render + Neon)
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,  # Neon nécessite SSL
        )
    }
else:
    # Développement (SQLite local)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = []


LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Kinshasa"
USE_I18N = True
USE_TZ = False


STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==========================================
# CONTENT SECURITY POLICY (CSP) - django-csp
# ==========================================

# Mode report-only (décommente pour tester sans bloquer)
# CSP_REPORT_ONLY = True
# CSP_REPORT_URI = "/csp-report/"  # optionnel

# Politique CSP pour production
if not DEBUG:
    CSP_DEFAULT_SRC = ("'self'",)
    
    CSP_STYLE_SRC = (
        "'self'",
        "'unsafe-inline'",  # nécessaire pour Bootstrap/crispy-forms
        "https://cdn.jsdelivr.net",
        "https://cdn.datatables.net",
        "https://stackpath.bootstrapcdn.com",
        "https://maxcdn.bootstrapcdn.com",
    )
    
    CSP_SCRIPT_SRC = (
        "'self'",
        "'unsafe-inline'",  # nécessaire pour certains scripts inline
        "'unsafe-eval'",    # nécessaire pour DataTables/jQuery
        "https://cdn.jsdelivr.net",
        "https://cdn.datatables.net",
        "https://code.jquery.com",
        "https://stackpath.bootstrapcdn.com",
        "https://maxcdn.bootstrapcdn.com",
        "https://kit.fontawesome.com",
    )
    
    CSP_IMG_SRC = (
        "'self'",
        "data:",
        "https:",
    )
    
    CSP_FONT_SRC = (
        "'self'",
        "https:",
        "data:",
    )
    
    CSP_FRAME_SRC = ("'self'",)
    
    CSP_OBJECT_SRC = ("'none'",)
    
    CSP_BASE_URI = ("'self'",)
    
    CSP_FORM_ACTION = ("'self'",)
    
    CSP_CONNECT_SRC = (
        "'self'",
        "https://jmc-hopital.onrender.com",
    )


# Configuration sécurité
if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    CSRF_TRUSTED_ORIGINS = ["https://jmc-hopital.onrender.com"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")