from django.urls import re_path

from .consumers import WatchPartyConsumer


websocket_urlpatterns = [
    re_path(
        r'^ws/watch-party/(?P<invite_code>[A-Za-z0-9_-]{20,32})/$',
        WatchPartyConsumer.as_asgi(),
    ),
]
