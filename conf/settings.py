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
    "django_csp",  # ← AJOUTÉ : django-csp
    "app",
    "crispy_forms",
    "crispy_bootstrap4",
    "channels",
    "video",
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"
ASGI_APPLICATION = "conf.asgi.application"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",  # ← AJOUTÉ : CSP Middleware (après SecurityMiddleware)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

# =============================================================================
# CONFIGURATION CSP (Content Security Policy)
# =============================================================================

CSP_REPORT_ONLY = False  # Mettre à True pour tester sans bloquer

CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",  # Nécessaire pour certains scripts inline (à éviter si possible)
    "'unsafe-eval'",    # Nécessaire pour certains libs JS
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    "https://code.jquery.com",
    "https://stackpath.bootstrapcdn.com",
    "https://cdn.jsdelivr.net/npm/bootstrap@5",
)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",  # Nécessaire pour les styles inline
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    "https://stackpath.bootstrapcdn.com",
    "https://fonts.googleapis.com",
)
CSP_IMG_SRC = (
    "'self'",
    "data:",  # Permet les images en base64
    "blob:",
    "https:",
)
CSP_FONT_SRC = (
    "'self'",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    "https://fonts.gstatic.com",
    "https://stackpath.bootstrapcdn.com",
)
CSP_CONNECT_SRC = (
    "'self'",
    "https:",
)
CSP_FRAME_SRC = ("'self'",)
CSP_OBJECT_SRC = ("'none'",)
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)

# =============================================================================
# CONFIGURATION SÉCURITÉ PRODUCTION
# =============================================================================

if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    
    # Cookies sécurisés
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    
    # SSL/TLS
    SECURE_SSL_REDIRECT = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    
    # HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 31536000  # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Headers supplémentaires
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    
    # Trusted origins
    CSRF_TRUSTED_ORIGINS = [
        "https://jmc-hopital.onrender.com",
        "https://www.jmc-hopital.onrender.com",
    ]
    
    # Proxy SSL header (pour Render/Heroku)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# =============================================================================
# LOGGING (optionnel mais recommandé)
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}