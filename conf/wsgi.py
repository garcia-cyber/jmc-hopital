import os
from django.core.wsgi import get_wsgi_application

# On indique à Django où trouver les settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conf.settings')

# L'application WSGI utilisée par Django
application = get_wsgi_application()
