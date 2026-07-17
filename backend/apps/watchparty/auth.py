from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication


SUBPROTOCOL_PREFIX = 'watchparty.jwt.'


@database_sync_to_async
def _user_from_token(raw_token):
    authentication = JWTAuthentication()
    try:
        validated_token = authentication.get_validated_token(raw_token)
        return authentication.get_user(validated_token)
    except Exception:
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    """Authenticate browser sockets without leaking JWTs in URLs or access logs."""

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        protocols = scope.get('subprotocols', [])
        protocol = next((item for item in protocols if item.startswith(SUBPROTOCOL_PREFIX)), None)
        if protocol:
            scope['user'] = await _user_from_token(protocol[len(SUBPROTOCOL_PREFIX):])
            scope['watchparty_subprotocol'] = protocol
        return await super().__call__(scope, receive, send)
