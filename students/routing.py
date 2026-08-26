from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Captura la URL ws://dominio/ws/chat/ID_DEL_CURSO/
    re_path(r'ws/chat/(?P<course_id>\d+)/$', consumers.AIChatConsumer.as_asgi()),
]
