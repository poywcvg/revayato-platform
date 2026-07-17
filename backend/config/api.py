from rest_framework.decorators import api_view
from django.conf import settings
from django.db import connection
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.response import Response


@api_view(['GET'])
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
        client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            services['redis'] = bool(client.ping())
        except RedisError:
            pass
        finally:
            client.close()

    healthy = all(services.values())
    return Response(
        {
            'status': 'ok' if healthy else 'degraded',
            'service': 'revayato-api',
            'services': services,
        },
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
