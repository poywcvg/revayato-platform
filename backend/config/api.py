from rest_framework.decorators import api_view
from django.conf import settings
from django.db import connection
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.decorators import throttle_classes
from rest_framework.response import Response

# One pooled client for the whole worker: the previous version built, opened
# and closed a brand-new TCP connection on every single health probe (compose
# hits this every 20s per service plus the edge). redis-py pools are
# thread-safe, so sharing is both faster and cheaper under load.
_health_redis_client: Redis | None = None


def _shared_redis() -> Redis:
    global _health_redis_client
    client = _health_redis_client
    if client is None:
        client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
        _health_redis_client = client
    return client


@api_view(['GET'])
@throttle_classes([])
def health_check(request):
    services = {'database': False, 'redis': False}

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            services['database'] = cursor.fetchone()[0] == 1
    except Exception:
        pass

    in_memory_channels = settings.CHANNEL_LAYER_BACKEND == 'channels.layers.InMemoryChannelLayer'
    if in_memory_channels:
        services['redis'] = True
    else:
        try:
            services['redis'] = bool(_shared_redis().ping())
        except RedisError:
            pass

    healthy = all(services.values())
    return Response(
        {
            'status': 'ok' if healthy else 'degraded',
            'service': 'revayato-api',
            'services': services,
        },
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
