from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Cette ligne permet d'écouter les connexions WebSocket pour une salle spécifique
    re_path(r'ws/video/(?P<room_name>\w+)/$', consumers.VideoConsumer.as_asgi()),
]