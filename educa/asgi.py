"""
ASGI config for educa project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""
# educa/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'educa.settings')

django_asgi_app = get_asgi_application()

# Importamos las rutas de WebSockets de ambas apps
import chat.routing
import students.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            # Combinamos las rutas sin ningún conflicto
            chat.routing.websocket_urlpatterns + students.routing.websocket_urlpatterns
        )
    ),
})
