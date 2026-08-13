import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-temporary-key")
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


AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
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
    'axes.middleware.AxesMiddleware',
]


AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = 2
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]


HONEYPOT_FIELD_NAME = 'email'
HONEYPOT_VALUE = ''


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


DATABASE_URL = os.environ.get("DATABASE_URL")


if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
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
# CONTENT SECURITY POLICY (CSP) - django-csp 4.0
# ==========================================

if not DEBUG:
    CONTENT_SECURITY_POLICY = {
        'DIRECTIVES': {
            'default-src': ("'self'",),
            
            'style-src': (
                "'self'",
                "'unsafe-inline'",
                "'unsafe-eval'",
                "https://cdn.jsdelivr.net",
                "https://cdn.datatables.net",
                "https://stackpath.bootstrapcdn.com",
                "https://maxcdn.bootstrapcdn.com",
                "https://cdnjs.cloudflare.com",
                "https://fonts.googleapis.com",
            ),
            
            'script-src': (
                "'self'",
                "'unsafe-inline'",
                "'unsafe-eval'",
                "https://cdn.jsdelivr.net",
                "https://cdn.datatables.net",
                "https://code.jquery.com",
                "https://stackpath.bootstrapcdn.com",
                "https://maxcdn.bootstrapcdn.com",
                "https://kit.fontawesome.com",
                "https://cdnjs.cloudflare.com",
            ),
            
            'img-src': (
                "'self'",
                "data:",
                "https:",
                "blob:",
            ),
            
            'font-src': (
                "'self'",
                "https:",
                "data:",
                "https://fonts.gstatic.com",
            ),
            
            'frame-src': ("'self'", "https:"),
            
            'object-src': ("'none'",),
            
            'base-uri': ("'self'",),
            
            'form-action': ("'self'",),
            
            'connect-src': (
                "'self'",
                "https://jmc-hopital.onrender.com",
                "https:",
            ),
        }
    }


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