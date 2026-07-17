"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

django_asgi_application = get_asgi_application()

from apps.watchparty.auth import JwtAuthMiddleware
from apps.watchparty.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': django_asgi_application,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
        ),
    ),
})
