import os

from django.core.wsgi import get_wsgi_application

# On définit le module de réglages par défaut
# Remplace 'conf' par le nom de ton projet si nécessaire
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conf.settings')

application = get_wsgi_application()

# Pour Render, Gunicorn utilisera cet objet 'application' pour lancer le projet
