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

# Only the public web service opts in (the stream gateway shares this module).
if os.environ.get('SEARCH_SUGGEST_PREWARM', '').strip() in {'1', 'true', 'yes'}:
    from apps.catalog.search_suggest import prewarm_in_background

    prewarm_in_background()

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
