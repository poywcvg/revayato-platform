import os
from pathlib import Path
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# Public origins are deliberately environment-only.  An empty value keeps
# local development same-origin/relative while production can use separate
# site, API, media CDN, and download CDN domains.
SITE_BASE_URL = os.environ.get('SITE_BASE_URL', '').strip().rstrip('/')
API_BASE_URL = os.environ.get('API_BASE_URL', '').strip().rstrip('/')
MEDIA_CDN_BASE_URL = os.environ.get('MEDIA_CDN_BASE_URL', '').strip().rstrip('/')
DOWNLOAD_CDN_BASE_URL = os.environ.get('DOWNLOAD_CDN_BASE_URL', '').strip().rstrip('/')


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('true', '1', 'yes', 'on')


DEBUG = env_bool('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is False.')
    SECRET_KEY = get_random_secret_key()
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',

    # Third-party
    'channels',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',

    # Domain apps — legacy (kept for migration compatibility)
    'core',
    'content',
    'users',
    'activity',

    # Domain apps — new structure
    'apps.catalog',
    'apps.engagement',
    'apps.accounts',
    'apps.recommendations',
    'apps.watchparty',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = os.environ.get(
    'DB_ENGINE',
    'django.db.backends.sqlite3' if DEBUG else 'django.db.backends.postgresql',
)
DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.environ.get('DB_NAME', str(BASE_DIR / 'db.sqlite3') if DEBUG else 'revayato'),
        'USER': os.environ.get('DB_USER', 'revayato'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'change-me-in-production'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
        **({'OPTIONS': {
            'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
        }} if DB_ENGINE == 'django.db.backends.postgresql' else {}),
    }
}

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = f'{MEDIA_CDN_BASE_URL}/' if MEDIA_CDN_BASE_URL else '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

# Optional S3-compatible object storage (Cloudflare R2, Bunny Storage, S3, ...)
# for uploaded posters and avatars. Static assets stay local and are served by Caddy.
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', '') or None
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'auto')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '') or None
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = os.environ.get('AWS_S3_ADDRESSING_STYLE', 'virtual')
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = env_bool('AWS_QUERYSTRING_AUTH', False)
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'public, max-age=2592000, immutable'}
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    if AWS_S3_CUSTOM_DOMAIN and not MEDIA_CDN_BASE_URL:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN.rstrip("/")}/'

# CORS
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'DJANGO_CORS_ALLOWED_ORIGINS',
        SITE_BASE_URL,
    ).split(',')
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

# REST Framework
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'config.exceptions.user_friendly_exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'watch_party_create': '10/hour',
        'watch_party_join': '60/hour',
    },
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# SimpleJWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

FRONTEND_URL = os.environ.get('FRONTEND_URL', SITE_BASE_URL)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'روایتو <no-reply@example.invalid>')
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    X_FRAME_OPTIONS = 'DENY'

# Cache (Redis)
CACHE_URL = os.environ.get('CACHE_URL', '')
if CACHE_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': CACHE_URL,
            'TIMEOUT': 300,
            'KEY_PREFIX': 'revayato',
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'revayato-cache',
        },
    }

# Realtime watch parties. Redis is mandatory outside tests; an in-memory
# backend can be selected explicitly for isolated test runs only.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CHANNEL_LAYER_BACKEND = os.environ.get(
    'CHANNEL_LAYER_BACKEND', 'channels_redis.core.RedisChannelLayer',
)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': CHANNEL_LAYER_BACKEND,
        **({} if CHANNEL_LAYER_BACKEND == 'channels.layers.InMemoryChannelLayer' else {
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': int(os.environ.get('CHANNEL_CAPACITY', '1000')),
                'expiry': int(os.environ.get('CHANNEL_EXPIRY_SECONDS', '10')),
            },
        }),
    },
}

WATCH_PARTY_MAX_MEMBERS = int(os.environ.get('WATCH_PARTY_MAX_MEMBERS', '20'))
WATCH_PARTY_DEFAULT_EXPIRY_MINUTES = int(
    os.environ.get('WATCH_PARTY_DEFAULT_EXPIRY_MINUTES', '240'),
)
WATCH_PARTY_CHAT_MAX_LENGTH = int(os.environ.get('WATCH_PARTY_CHAT_MAX_LENGTH', '1000'))

# Automated catalog ingestion. Metadata sync is draft-first; publication also
# requires rights verification and a licensed HLS key in the media manifest.
TMDB_API_TOKEN = os.environ.get('TMDB_API_TOKEN', '')
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
TMDB_API_BASE_URL = os.environ.get('TMDB_API_BASE_URL', '').rstrip('/')
TMDB_LANGUAGE = os.environ.get('TMDB_LANGUAGE', 'fa-IR')
TMDB_REGION = os.environ.get('TMDB_REGION', '')
CATALOG_MEDIA_MANIFEST = os.environ.get('CATALOG_MEDIA_MANIFEST', '')
CATALOG_SYNC_LOOKBACK_DAYS = int(os.environ.get('CATALOG_SYNC_LOOKBACK_DAYS', '14'))
CATALOG_SYNC_LOOKAHEAD_DAYS = int(os.environ.get('CATALOG_SYNC_LOOKAHEAD_DAYS', '7'))
CATALOG_SYNC_MAX_PAGES = int(os.environ.get('CATALOG_SYNC_MAX_PAGES', '2'))
CATALOG_SYNC_ENABLED = env_bool('CATALOG_SYNC_ENABLED', False)
CATALOG_AUTO_PUBLISH = env_bool('CATALOG_AUTO_PUBLISH', False)
CATALOG_SYNC_INTERVAL_HOURS = int(os.environ.get('CATALOG_SYNC_INTERVAL_HOURS', '6'))
CATALOG_PUBLISH_INTERVAL_SECONDS = int(os.environ.get('CATALOG_PUBLISH_INTERVAL_SECONDS', '300'))

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {}
if CATALOG_SYNC_ENABLED:
    CELERY_BEAT_SCHEDULE['catalog-metadata-sync'] = {
        'task': 'apps.catalog.tasks.sync_catalog_task',
        'schedule': max(3600, CATALOG_SYNC_INTERVAL_HOURS * 3600),
    }
if CATALOG_AUTO_PUBLISH:
    CELERY_BEAT_SCHEDULE['catalog-publish-ready'] = {
        'task': 'apps.catalog.tasks.publish_ready_catalog_task',
        'schedule': max(60, CATALOG_PUBLISH_INTERVAL_SECONDS),
    }

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
    },
}
