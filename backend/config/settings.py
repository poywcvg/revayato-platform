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
DB_STATEMENT_TIMEOUT_MS = max(0, int(os.environ.get('DB_STATEMENT_TIMEOUT_MS', '0') or 0))
_postgres_options = {
    'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
}
if DB_STATEMENT_TIMEOUT_MS:
    _postgres_options['options'] = f'-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}'
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
        **({'OPTIONS': _postgres_options} if DB_ENGINE == 'django.db.backends.postgresql' else {}),
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

# Private original-file archive (ArvanCloud / S3-compatible). Separate from the
# optional public AWS_* media bucket used for posters and avatars.
ARCHIVE_S3_ENDPOINT_URL = os.environ.get('ARCHIVE_S3_ENDPOINT_URL', '').strip()
ARCHIVE_S3_ACCESS_KEY_ID = os.environ.get('ARCHIVE_S3_ACCESS_KEY_ID', '')
ARCHIVE_S3_SECRET_ACCESS_KEY = os.environ.get('ARCHIVE_S3_SECRET_ACCESS_KEY', '')
ARCHIVE_S3_BUCKET_NAME = os.environ.get('ARCHIVE_S3_BUCKET_NAME', '').strip()
ARCHIVE_S3_REGION = os.environ.get('ARCHIVE_S3_REGION', '').strip() or 'us-east-1'
ARCHIVE_S3_SIGNATURE_VERSION = os.environ.get('ARCHIVE_S3_SIGNATURE_VERSION', 's3v4').strip() or 's3v4'
ARCHIVE_S3_ADDRESSING_STYLE = os.environ.get('ARCHIVE_S3_ADDRESSING_STYLE', 'path').strip() or 'path'
ARCHIVE_S3_PRIVATE = env_bool('ARCHIVE_S3_PRIVATE', True)
ARCHIVE_PRESIGNED_URL_EXPIRES = int(os.environ.get('ARCHIVE_PRESIGNED_URL_EXPIRES', '900'))
ARCHIVE_DOWNLOAD_URL_EXPIRES = int(os.environ.get('ARCHIVE_DOWNLOAD_URL_EXPIRES', '600'))
ARCHIVE_MULTIPART_CHUNK_SIZE_MB = int(os.environ.get('ARCHIVE_MULTIPART_CHUNK_SIZE_MB', '64'))
ARCHIVE_MULTIPART_URL_BATCH_SIZE = int(os.environ.get('ARCHIVE_MULTIPART_URL_BATCH_SIZE', '20'))
ARCHIVE_UPLOAD_CONCURRENCY = int(os.environ.get('ARCHIVE_UPLOAD_CONCURRENCY', '3'))
ARCHIVE_MAX_UPLOAD_SIZE_GB = int(os.environ.get('ARCHIVE_MAX_UPLOAD_SIZE_GB', '100'))
ARCHIVE_ALLOWED_EXTENSIONS = tuple(
    ext.strip().lower().lstrip('.')
    for ext in os.environ.get('ARCHIVE_ALLOWED_EXTENSIONS', 'mkv,mp4').split(',')
    if ext.strip()
) or ('mkv', 'mp4')
ARCHIVE_VERIFY_WITH_FFPROBE = env_bool('ARCHIVE_VERIFY_WITH_FFPROBE', False)
ARCHIVE_S3_CONNECT_TIMEOUT = int(os.environ.get('ARCHIVE_S3_CONNECT_TIMEOUT', '10'))
ARCHIVE_S3_READ_TIMEOUT = int(os.environ.get('ARCHIVE_S3_READ_TIMEOUT', '60'))
ARCHIVE_S3_MAX_ATTEMPTS = int(os.environ.get('ARCHIVE_S3_MAX_ATTEMPTS', '3'))

# Avasarami licensed provider (server-side only). Prefer API token / authorized
# cookie / feed. Username/password is blocked when CAPTCHA is present.
AVASARAMI_BASE_URL = os.environ.get('AVASARAMI_BASE_URL', 'https://avasarami.top').strip().rstrip('/')
AVASARAMI_LOGIN_URL = os.environ.get('AVASARAMI_LOGIN_URL', 'https://avasarami.top/sign-in/').strip()
AVASARAMI_MOVIES_URL = os.environ.get('AVASARAMI_MOVIES_URL', 'https://avasarami.top/movies/').strip()
AVASARAMI_SERIES_URL = os.environ.get('AVASARAMI_SERIES_URL', 'https://avasarami.top/series/').strip()
AVASARAMI_AUTH_TYPE = os.environ.get('AVASARAMI_AUTH_TYPE', '').strip().lower()
AVASARAMI_USERNAME = os.environ.get('AVASARAMI_USERNAME', '')
AVASARAMI_PASSWORD = os.environ.get('AVASARAMI_PASSWORD', '')
AVASARAMI_API_TOKEN = os.environ.get('AVASARAMI_API_TOKEN', '')
AVASARAMI_COOKIE = os.environ.get('AVASARAMI_COOKIE', '')
AVASARAMI_TIMEOUT_SECONDS = int(os.environ.get('AVASARAMI_TIMEOUT_SECONDS', '30'))
AVASARAMI_RATE_LIMIT_PER_MINUTE = int(os.environ.get('AVASARAMI_RATE_LIMIT_PER_MINUTE', '30'))
AVASARAMI_VERIFY_SSL = env_bool('AVASARAMI_VERIFY_SSL', True)

# Film2Media / myf2m.info — default public download crawler (no VIP login).
MYF2M_BASE_URL = os.environ.get('MYF2M_BASE_URL', 'https://www.myf2m.info').strip().rstrip('/')
MYF2M_TIMEOUT_SECONDS = int(os.environ.get('MYF2M_TIMEOUT_SECONDS', '30'))
MYF2M_RATE_LIMIT_PER_MINUTE = int(os.environ.get('MYF2M_RATE_LIMIT_PER_MINUTE', '30'))
MYF2M_VERIFY_SSL = env_bool('MYF2M_VERIFY_SSL', True)
MYF2M_USER_AGENT = os.environ.get(
    'MYF2M_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
).strip() or 'RevayatoCatalogCrawler/1.0'
MYF2M_MAX_RESULTS_PER_LOOKUP = max(1, min(50, int(os.environ.get('MYF2M_MAX_RESULTS_PER_LOOKUP', '20'))))
MYF2M_AUTO_CRAWL_ON_PUBLISH = env_bool('MYF2M_AUTO_CRAWL_ON_PUBLISH', True)

# Dornatv (dornatv.com) — WordPress BartarTheme catalog + public CDN download boxes.
DORNATV_BASE_URL = os.environ.get('DORNATV_BASE_URL', 'https://dornatv.com').strip().rstrip('/')
DORNATV_TIMEOUT_SECONDS = int(os.environ.get('DORNATV_TIMEOUT_SECONDS', '30'))
DORNATV_RATE_LIMIT_PER_MINUTE = int(os.environ.get('DORNATV_RATE_LIMIT_PER_MINUTE', '30'))
DORNATV_VERIFY_SSL = env_bool('DORNATV_VERIFY_SSL', True)
DORNATV_USER_AGENT = os.environ.get(
    'DORNATV_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
).strip() or 'RevayatoCatalogCrawler/1.0'
DORNATV_MAX_RESULTS_PER_LOOKUP = max(1, min(50, int(os.environ.get('DORNATV_MAX_RESULTS_PER_LOOKUP', '20'))))
DORNATV_REST_PER_PAGE = max(1, min(100, int(os.environ.get('DORNATV_REST_PER_PAGE', '50'))))
DORNATV_IMPORT_MOVIES_PER_TICK = max(1, min(40, int(os.environ.get('DORNATV_IMPORT_MOVIES_PER_TICK', '12'))))
DORNATV_IMPORT_SERIES_PER_TICK = max(1, min(20, int(os.environ.get('DORNATV_IMPORT_SERIES_PER_TICK', '6'))))
DORNATV_IMPORT_ENABLED = env_bool('DORNATV_IMPORT_ENABLED', True)
DORNATV_IMPORT_YEAR_START = max(1900, min(2100, int(os.environ.get('DORNATV_IMPORT_YEAR_START', '2026'))))
DORNATV_IMPORT_YEAR_END = max(1900, min(2100, int(os.environ.get('DORNATV_IMPORT_YEAR_END', '1970'))))
DORNATV_IMPORT_CHECKPOINT = os.environ.get(
    'DORNATV_IMPORT_CHECKPOINT', '/app/media/dornatv_import_checkpoint.json',
).strip() or '/app/media/dornatv_import_checkpoint.json'

# Dornatv crawl performance knobs.
# Detail-page HTML is cached so repeated beat ticks (and the modified-order
# sweep) do not re-download 200-400 KB pages. CDN download signatures self-expire
# in ~13 h, so a short page TTL keeps listings fresh without hammering the site.
DORNATV_PAGE_CACHE_TTL_SECONDS = max(30, int(os.environ.get('DORNATV_PAGE_CACHE_TTL_SECONDS', '1500')))
DORNATV_PAGE_CACHE_MAX_BYTES = max(64 * 1024, int(os.environ.get('DORNATV_PAGE_CACHE_MAX_BYTES', str(512 * 1024))))
# Per-tick cap on recently-modified listing pages walked before the year-walk.
DORNATV_MODIFIED_PAGES_PER_TICK = max(1, min(20, int(os.environ.get('DORNATV_MODIFIED_PAGES_PER_TICK', '3'))))
# Per-tick budget for re-crawling already-imported titles whose signed CDN links
# have gone stale (see DORNATV_REFRESH_LINK_MAX_AGE_SECONDS).
DORNATV_REFRESH_PER_TICK = max(0, min(40, int(os.environ.get('DORNATV_REFRESH_PER_TICK', '4'))))
DORNATV_REFRESH_LINK_MAX_AGE_SECONDS = max(300, int(os.environ.get('DORNATV_REFRESH_LINK_MAX_AGE_SECONDS', str(6 * 60 * 60))))

# SubtitleStar — public Persian sidecar subtitle fallback for movie playback.
# Matching is IMDb-strict and requests are throttled/cached to avoid hammering
# the provider. SUBTITLESTAR_COOKIE is optional for an authorized session only;
# the crawler never attempts to solve browser challenges or CAPTCHAs.
SUBTITLESTAR_ENABLED = env_bool('SUBTITLESTAR_ENABLED', True)
# Online SoftSub: embedded Soft CDN ffmpeg → SubtitleStar → Subzone.ir.
SOFTSUB_ALLOW_FFMPEG = env_bool('SOFTSUB_ALLOW_FFMPEG', False)
SUBTITLESTAR_BASE_URL = os.environ.get('SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com').strip().rstrip('/')
SUBTITLESTAR_TIMEOUT_SECONDS = int(os.environ.get('SUBTITLESTAR_TIMEOUT_SECONDS', '20'))
SUBTITLESTAR_REQUEST_INTERVAL_SECONDS = float(os.environ.get('SUBTITLESTAR_REQUEST_INTERVAL_SECONDS', '4'))
SUBTITLESTAR_NEGATIVE_CACHE_SECONDS = int(os.environ.get('SUBTITLESTAR_NEGATIVE_CACHE_SECONDS', str(24 * 60 * 60)))
SUBTITLESTAR_BLOCKED_COOLDOWN_SECONDS = int(
    os.environ.get('SUBTITLESTAR_BLOCKED_COOLDOWN_SECONDS', str(20 * 60)),
)
SUBTITLESTAR_MAX_RESULTS_PER_LOOKUP = max(
    1,
    min(5, int(os.environ.get('SUBTITLESTAR_MAX_RESULTS_PER_LOOKUP', '3'))),
)
SUBTITLESTAR_MAX_HTML_BYTES = int(os.environ.get('SUBTITLESTAR_MAX_HTML_BYTES', str(2 * 1024 * 1024)))
SUBTITLESTAR_MAX_ARCHIVE_BYTES = int(os.environ.get('SUBTITLESTAR_MAX_ARCHIVE_BYTES', str(16 * 1024 * 1024)))
SUBTITLESTAR_MAX_MEMBER_BYTES = int(os.environ.get('SUBTITLESTAR_MAX_MEMBER_BYTES', str(5 * 1024 * 1024)))
SUBTITLESTAR_MAX_EXTRACTED_BYTES = int(
    os.environ.get('SUBTITLESTAR_MAX_EXTRACTED_BYTES', str(20 * 1024 * 1024)),
)
SUBTITLESTAR_MAX_ARCHIVE_MEMBERS = int(os.environ.get('SUBTITLESTAR_MAX_ARCHIVE_MEMBERS', '60'))
SUBTITLESTAR_ALLOWED_DOWNLOAD_HOSTS = tuple(
    host.strip().lower()
    for host in os.environ.get(
        'SUBTITLESTAR_ALLOWED_DOWNLOAD_HOSTS',
        'subtitlestar.com,file-share.io',
    ).split(',')
    if host.strip()
)
SUBTITLESTAR_USER_AGENT = os.environ.get(
    'SUBTITLESTAR_USER_AGENT',
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
).strip()
SUBTITLESTAR_COOKIE = os.environ.get('SUBTITLESTAR_COOKIE', '').strip()
SUBTITLESTAR_VERIFY_SSL = env_bool('SUBTITLESTAR_VERIFY_SSL', True)

# Subzone.ir — Subf2m mirror; fast Persian sidecar fallback after SubtitleStar.
SUBZONE_ENABLED = env_bool('SUBZONE_ENABLED', True)
SUBZONE_BASE_URL = os.environ.get('SUBZONE_BASE_URL', 'https://subzone.ir').strip().rstrip('/')
SUBZONE_TIMEOUT_SECONDS = int(os.environ.get('SUBZONE_TIMEOUT_SECONDS', '12'))
SUBZONE_REQUEST_INTERVAL_SECONDS = float(os.environ.get('SUBZONE_REQUEST_INTERVAL_SECONDS', '0.8'))
SUBZONE_NEGATIVE_CACHE_SECONDS = int(os.environ.get('SUBZONE_NEGATIVE_CACHE_SECONDS', str(12 * 60 * 60)))
SUBZONE_BLOCKED_COOLDOWN_SECONDS = int(os.environ.get('SUBZONE_BLOCKED_COOLDOWN_SECONDS', str(15 * 60)))
SUBZONE_MAX_HTML_BYTES = int(os.environ.get('SUBZONE_MAX_HTML_BYTES', str(2 * 1024 * 1024)))
SUBZONE_MAX_ARCHIVE_BYTES = int(os.environ.get('SUBZONE_MAX_ARCHIVE_BYTES', str(16 * 1024 * 1024)))
SUBZONE_ALLOWED_DOWNLOAD_HOSTS = tuple(
    host.strip().lower()
    for host in os.environ.get(
        'SUBZONE_ALLOWED_DOWNLOAD_HOSTS',
        'subzone.ir,subf2m.co,sub-api.ir,media.sub-api.ir',
    ).split(',')
    if host.strip()
)
SUBZONE_USER_AGENT = os.environ.get(
    'SUBZONE_USER_AGENT',
    (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
).strip()
SUBZONE_VERIFY_SSL = env_bool('SUBZONE_VERIFY_SSL', True)

# Primary + secondary link providers for publish auto-crawl and catalog import.
# Always crawl both Film2Media and Dornatv and merge qualities.
CATALOG_LINK_PROVIDER = os.environ.get('CATALOG_LINK_PROVIDER', 'myf2m').strip().lower() or 'myf2m'
CATALOG_LINK_PROVIDERS = [
    part.strip().lower()
    for part in os.environ.get('CATALOG_LINK_PROVIDERS', 'myf2m,dornatv').replace(';', ',').split(',')
    if part.strip()
] or ['myf2m', 'dornatv']
# Hollywood-only catalog: never keep Iranian cinema/TV.
CATALOG_EXCLUDE_IRANIAN = env_bool('CATALOG_EXCLUDE_IRANIAN', True)
# When True, titles that cannot be resolved on the link provider are deleted.
CATALOG_DELETE_WHEN_PROVIDER_MISSING = env_bool('CATALOG_DELETE_WHEN_PROVIDER_MISSING', True)

if not DEBUG:
    if MYF2M_BASE_URL and not MYF2M_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('MYF2M_BASE_URL must use HTTPS when DJANGO_DEBUG is False.')
    if not MYF2M_VERIFY_SSL:
        raise ImproperlyConfigured('MYF2M_VERIFY_SSL must remain True when DJANGO_DEBUG is False.')
    if DORNATV_BASE_URL and not DORNATV_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('DORNATV_BASE_URL must use HTTPS when DJANGO_DEBUG is False.')
    if not DORNATV_VERIFY_SSL:
        raise ImproperlyConfigured('DORNATV_VERIFY_SSL must remain True when DJANGO_DEBUG is False.')
    if SUBTITLESTAR_BASE_URL and not SUBTITLESTAR_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('SUBTITLESTAR_BASE_URL must use HTTPS when DJANGO_DEBUG is False.')
    if not SUBTITLESTAR_VERIFY_SSL:
        raise ImproperlyConfigured('SUBTITLESTAR_VERIFY_SSL must remain True when DJANGO_DEBUG is False.')
    if SUBZONE_BASE_URL and not SUBZONE_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('SUBZONE_BASE_URL must use HTTPS when DJANGO_DEBUG is False.')
    if not SUBZONE_VERIFY_SSL:
        raise ImproperlyConfigured('SUBZONE_VERIFY_SSL must remain True when DJANGO_DEBUG is False.')

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

# Client-IP resolution (see config/client_ip.py).
# Cloudflare's published edge ranges; empty falls back to the built-in list.
SITE_CLOUDFLARE_IP_RANGES = os.environ.get('SITE_CLOUDFLARE_IP_RANGES', '').strip()
# Extra trusted reverse-proxy CIDRs (e.g. a CDN in front of Cloudflare).
SITE_CADDY_CLIENT_IPS = os.environ.get('SITE_CADDY_CLIENT_IPS', '').strip()
# When True, the immediate peer (Docker bridge / host healthcheck) is trusted
# without needing the Cloudflare list. False keeps public traffic strict.
SITE_CLOUD_ADMIN = env_bool('SITE_CLOUD_ADMIN', True)

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
        # SSR and the frontend healthcheck read the public catalog through the
        # backend container, so they need a dedicated bucket instead of sharing
        # the very small anonymous authentication/API bucket.
        'catalog': os.environ.get('CATALOG_THROTTLE_RATE', '600/minute'),
        'playback_subtitle_ensure': os.environ.get('PLAYBACK_SUBTITLE_ENSURE_THROTTLE_RATE', '30/minute'),
        'watch_party_create': '10/hour',
        'watch_party_join': '60/hour',
    },
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# SimpleJWT — optional dedicated signing key; falls back to Django SECRET_KEY.
_JWT_SECRET = os.environ.get('JWT_SECRET', '').strip()
JWT_REFRESH_TOKEN_DAYS = max(1, int(os.environ.get('JWT_REFRESH_TOKEN_DAYS', '400')))
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    # Rotation renews this browser-compatible 400-day window on active use.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    **({'SIGNING_KEY': _JWT_SECRET} if _JWT_SECRET else {}),
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
    # Prefer Redis for sessions so auth/admin traffic avoids Postgres round-trips.
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
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

# Automated catalog ingestion. Metadata sync is draft-first; auto-publish only
# needs basic metadata (description, release date, poster). TMDB credentials
# remain backend-only. Bearer auth is preferred.
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
TMDB_READ_ACCESS_TOKEN = os.environ.get('TMDB_READ_ACCESS_TOKEN', '')
TMDB_BASE_URL = os.environ.get('TMDB_BASE_URL', 'https://api.themoviedb.org/3').rstrip('/')
TMDB_IMAGE_BASE_URL = os.environ.get('TMDB_IMAGE_BASE_URL', 'https://image.tmdb.org/t/p').rstrip('/')
TMDB_LANGUAGE = os.environ.get('TMDB_LANGUAGE', 'fa-IR')
TMDB_FALLBACK_LANGUAGE = os.environ.get('TMDB_FALLBACK_LANGUAGE', 'en-US')
TMDB_REGION = os.environ.get('TMDB_REGION', 'IR')
TMDB_TIMEOUT_SECONDS = int(os.environ.get('TMDB_TIMEOUT_SECONDS', '20'))
TMDB_MAX_RETRIES = int(os.environ.get('TMDB_MAX_RETRIES', '3'))
TMDB_PROXY_URL = os.environ.get('TMDB_PROXY_URL', '')
TMDB_HTTP_PROXY = os.environ.get('HTTP_PROXY', '')
TMDB_HTTPS_PROXY = os.environ.get('HTTPS_PROXY', '') or TMDB_HTTP_PROXY
OMDB_API_KEY = os.environ.get('OMDB_API_KEY', '')
OMDB_BASE_URL = os.environ.get('OMDB_BASE_URL', 'https://www.omdbapi.com/').rstrip('/') + '/'
OMDB_TIMEOUT_SECONDS = int(os.environ.get('OMDB_TIMEOUT_SECONDS', '12'))
OMDB_MAX_RETRIES = int(os.environ.get('OMDB_MAX_RETRIES', '2'))
TVDB_API_KEY = os.environ.get('TVDB_API_KEY', '')
TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID', '')
MEDIA_RATING_CACHE_TTL = int(os.environ.get('MEDIA_RATING_CACHE_TTL', str(6 * 60 * 60)))
CATALOG_MEDIA_MANIFEST = os.environ.get('CATALOG_MEDIA_MANIFEST', '')
CATALOG_SYNC_LOOKBACK_DAYS = int(os.environ.get('CATALOG_SYNC_LOOKBACK_DAYS', '14'))
CATALOG_SYNC_LOOKAHEAD_DAYS = int(os.environ.get('CATALOG_SYNC_LOOKAHEAD_DAYS', '7'))
CATALOG_SYNC_MAX_PAGES = int(os.environ.get('CATALOG_SYNC_MAX_PAGES', '2'))
CATALOG_SYNC_ENABLED = env_bool('CATALOG_SYNC_ENABLED', False)
CATALOG_AUTO_PUBLISH = env_bool('CATALOG_AUTO_PUBLISH', False)
CATALOG_SYNC_INTERVAL_HOURS = int(os.environ.get('CATALOG_SYNC_INTERVAL_HOURS', '6'))
CATALOG_SYNC_STAGE_BATCH_SIZE = int(os.environ.get('CATALOG_SYNC_STAGE_BATCH_SIZE', '2000'))
CATALOG_SYNC_PROCESS_BATCH_SIZE = int(os.environ.get('CATALOG_SYNC_PROCESS_BATCH_SIZE', '20'))
CATALOG_SYNC_ITEM_MAX_ATTEMPTS = int(os.environ.get('CATALOG_SYNC_ITEM_MAX_ATTEMPTS', '3'))
CATALOG_SYNC_ITEMS_PER_SECOND = float(os.environ.get('CATALOG_SYNC_ITEMS_PER_SECOND', '6'))
CATALOG_TMDB_REFRESH_AFTER_DAYS = int(os.environ.get('CATALOG_TMDB_REFRESH_AFTER_DAYS', '150'))
CATALOG_SYNC_STALE_REFRESH_LIMIT = int(os.environ.get('CATALOG_SYNC_STALE_REFRESH_LIMIT', '50000'))
CATALOG_SYNC_STALE_HEARTBEAT_MINUTES = int(os.environ.get('CATALOG_SYNC_STALE_HEARTBEAT_MINUTES', '15'))
CATALOG_PUBLISH_INTERVAL_SECONDS = int(os.environ.get('CATALOG_PUBLISH_INTERVAL_SECONDS', '300'))

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_TRANSPORT_OPTIONS = {'visibility_timeout': 2 * 60 * 60}
CELERY_BEAT_SCHEDULE = {
    'catalog-sync-watchdog': {
        'task': 'apps.catalog.tasks.catalog_sync_watchdog_task',
        'schedule': 300,
    },
    'catalog-metadata-sync': {
        'task': 'apps.catalog.tasks.sync_catalog_task',
        'schedule': 15 * 60,
    },
    'catalog-softsub-backfill': {
        'task': 'apps.catalog.tasks.backfill_softsub_tracks_task',
        'schedule': 60 * 60,
    },
    'catalog-dornatv-import-missing': {
        'task': 'apps.catalog.provider_import.tasks.import_missing_dornatv_task',
        'schedule': 300,
    },
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
