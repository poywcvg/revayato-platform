import os
import sys
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
    'apps.assistant',
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
DB_CONN_MAX_AGE = int(os.environ.get('DB_CONN_MAX_AGE', '60'))


def _db_pool_options():
    """Per-process psycopg pool for the ASGI web services (DB_POOL_MAX_SIZE > 0).

    Under ASGI Django runs every request in a fresh thread, so a persistent
    connection (CONN_MAX_AGE > 0) is orphaned when that thread ends: the
    stream gateway alone was holding 120+ idle connections and pushing
    Postgres into "too many clients" 500s on search/home. A pool is the
    ASGI-safe way to reuse connections; it requires CONN_MAX_AGE = 0, which
    returns each request's connection to the pool instead of leaking it.
    """
    max_size = int(os.environ.get('DB_POOL_MAX_SIZE', '0') or 0)
    if max_size <= 0 or DB_ENGINE != 'django.db.backends.postgresql':
        return None
    try:
        import psycopg_pool  # noqa: F401
    except ImportError:
        # Image built without the pool extra: still stop the leak (no reuse).
        return False
    return {
        'min_size': max(0, min(max_size, int(os.environ.get('DB_POOL_MIN_SIZE', '1') or 0))),
        'max_size': max_size,
        'timeout': float(os.environ.get('DB_POOL_TIMEOUT', '10') or 10),
        'max_idle': float(os.environ.get('DB_POOL_MAX_IDLE', '300') or 300),
    }


_db_pool = _db_pool_options()
if _db_pool is not None:
    DB_CONN_MAX_AGE = 0
    if _db_pool:
        _postgres_options['pool'] = _db_pool
DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.environ.get('DB_NAME', str(BASE_DIR / 'db.sqlite3') if DEBUG else 'revayato'),
        'USER': os.environ.get('DB_USER', 'revayato'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'change-me-in-production'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': DB_CONN_MAX_AGE,
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

# Film2Media — default public download crawler (no VIP login). The host is a
# moving target (myf2m.info -> myf2ms.top in 2026); nothing else in the codebase
# may pin it, or a domain move silently returns zero results instead of failing.
MYF2M_BASE_URL = os.environ.get('MYF2M_BASE_URL', 'https://www.myf2ms.top').strip().rstrip('/')
MYF2M_TIMEOUT_SECONDS = int(os.environ.get('MYF2M_TIMEOUT_SECONDS', '30'))
MYF2M_RATE_LIMIT_PER_MINUTE = int(os.environ.get('MYF2M_RATE_LIMIT_PER_MINUTE', '30'))
MYF2M_VERIFY_SSL = env_bool('MYF2M_VERIFY_SSL', True)
MYF2M_USER_AGENT = os.environ.get(
    'MYF2M_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
).strip() or 'RevayatoCatalogCrawler/1.0'
MYF2M_MAX_RESULTS_PER_LOOKUP = max(1, min(50, int(os.environ.get('MYF2M_MAX_RESULTS_PER_LOOKUP', '20'))))
MYF2M_AUTO_CRAWL_ON_PUBLISH = env_bool('MYF2M_AUTO_CRAWL_ON_PUBLISH', True)
# Film2Media discovery is listing-driven (``/movies/``, ``/series/``), so a tick
# is bounded by pages walked as well as by titles kept.
MYF2M_IMPORT_ENABLED = env_bool('MYF2M_IMPORT_ENABLED', True)
MYF2M_IMPORT_MOVIES_PER_TICK = max(1, min(40, int(os.environ.get('MYF2M_IMPORT_MOVIES_PER_TICK', '12'))))
MYF2M_IMPORT_SERIES_PER_TICK = max(1, min(20, int(os.environ.get('MYF2M_IMPORT_SERIES_PER_TICK', '6'))))
MYF2M_IMPORT_MAX_PAGES_PER_TICK = max(1, min(60, int(os.environ.get('MYF2M_IMPORT_MAX_PAGES_PER_TICK', '12'))))
# ``0`` keeps the clock-based default (next calendar year) so the walk does not
# need a code change every January.
MYF2M_IMPORT_YEAR_START = max(0, min(2100, int(os.environ.get('MYF2M_IMPORT_YEAR_START', '0'))))
MYF2M_IMPORT_YEAR_END = max(1900, min(2100, int(os.environ.get('MYF2M_IMPORT_YEAR_END', '1970'))))
MYF2M_IMPORT_CHECKPOINT = os.environ.get(
    'MYF2M_IMPORT_CHECKPOINT', '/app/media/myf2m_import_checkpoint.json',
).strip() or '/app/media/myf2m_import_checkpoint.json'

# Dornatv (dornatv.com) — WordPress BartarTheme catalog + public CDN download boxes.
DORNATV_BASE_URL = os.environ.get('DORNATV_BASE_URL', 'https://dornatv.com').strip().rstrip('/')
DORNATV_TIMEOUT_SECONDS = int(os.environ.get('DORNATV_TIMEOUT_SECONDS', '30'))
DORNATV_RATE_LIMIT_PER_MINUTE = int(os.environ.get('DORNATV_RATE_LIMIT_PER_MINUTE', '30'))
DORNATV_VERIFY_SSL = env_bool('DORNATV_VERIFY_SSL', True)
DORNATV_USER_AGENT = os.environ.get(
    'DORNATV_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
).strip() or 'RevayatoCatalogCrawler/1.0'
DORNATV_MAX_RESULTS_PER_LOOKUP = max(1, min(50, int(os.environ.get('DORNATV_MAX_RESULTS_PER_LOOKUP', '20'))))
DORNATV_REST_PER_PAGE = max(1, min(100, int(os.environ.get('DORNATV_REST_PER_PAGE', '100'))))
DORNATV_IMPORT_MOVIES_PER_TICK = max(1, min(40, int(os.environ.get('DORNATV_IMPORT_MOVIES_PER_TICK', '16'))))
DORNATV_IMPORT_SERIES_PER_TICK = max(1, min(20, int(os.environ.get('DORNATV_IMPORT_SERIES_PER_TICK', '8'))))
DORNATV_IMPORT_ENABLED = env_bool('DORNATV_IMPORT_ENABLED', True)
# Wall-clock budget for one discovery tick, per provider. Both tasks carry
# ``soft_time_limit=12*60``; before this existed the dornatv walk simply ran until
# Celery killed it, every single tick, so it never returned a result and never
# logged its stats — the work was real and checkpointed, but nothing downstream
# could tell a working importer from a dead one. The walks are resumable, so
# stopping early is free. Kept well under the soft limit because the budget is only
# checked between items and a single title can take tens of seconds to import.
DORNATV_IMPORT_BUDGET_SECONDS = max(0, int(os.environ.get('DORNATV_IMPORT_BUDGET_SECONDS', '540')))
MYF2M_IMPORT_BUDGET_SECONDS = max(0, int(os.environ.get('MYF2M_IMPORT_BUDGET_SECONDS', '540')))
# ``0`` keeps the clock-based default (next calendar year) instead of pinning the
# walk to a year that goes stale.
DORNATV_IMPORT_YEAR_START = max(0, min(2100, int(os.environ.get('DORNATV_IMPORT_YEAR_START', '0'))))
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
# A refresh that fails (page removed, identity changed) leaves the row stalest;
# it sits out this long so it cannot hold every refresh slot of every tick.
DORNATV_REFRESH_FAIL_COOLDOWN_SECONDS = max(600, int(os.environ.get('DORNATV_REFRESH_FAIL_COOLDOWN_SECONDS', str(24 * 60 * 60))))
DORNATV_REFRESH_SCAN_WINDOW = max(50, int(os.environ.get('DORNATV_REFRESH_SCAN_WINDOW', '1000')))
# Checkpointed detail pages kept, most recent last (see dornatv_import._DonePaths).
DORNATV_IMPORT_DONE_PATHS_CAP = max(1000, int(os.environ.get('DORNATV_IMPORT_DONE_PATHS_CAP', '50000')))
# Pages of titles the catalog already has from another provider whose links are
# merged in per tick (each costs one detail-page fetch plus the dead-link screen).
DORNATV_IMPORT_MERGE_PER_TICK = max(0, int(os.environ.get('DORNATV_IMPORT_MERGE_PER_TICK', '8')))


# Kargadan Movie (kargadanmovie.com). Discovery is the public wp-sitemap; download
# links are shown only to a signed-in account and the sign-in form has a CAPTCHA,
# so the crawler never signs in by itself. An operator signs in with a browser and
# pastes that session's ``Cookie`` header into KARGADAN_SESSION_COOKIE (keep the
# browser's User-Agent in KARGADAN_USER_AGENT if the site binds sessions to it).
# Without it the lane still runs, keeps the inventory fresh and logs
# ``provider_import.kargadan_session_missing``.
KARGADAN_BASE_URL = os.environ.get('KARGADAN_BASE_URL', 'https://kargadanmovie.com').strip().rstrip('/')
KARGADAN_TIMEOUT_SECONDS = int(os.environ.get('KARGADAN_TIMEOUT_SECONDS', '30'))
KARGADAN_RATE_LIMIT_PER_MINUTE = max(1, min(60, int(os.environ.get('KARGADAN_RATE_LIMIT_PER_MINUTE', '20'))))
KARGADAN_VERIFY_SSL = env_bool('KARGADAN_VERIFY_SSL', True)
KARGADAN_USER_AGENT = os.environ.get(
    'KARGADAN_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
).strip() or 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)'
KARGADAN_SESSION_COOKIE = os.environ.get('KARGADAN_SESSION_COOKIE', '').strip()
KARGADAN_SESSION_RECHECK_MINUTES = max(5, int(os.environ.get('KARGADAN_SESSION_RECHECK_MINUTES', '30')))
KARGADAN_IMPORT_ENABLED = env_bool('KARGADAN_IMPORT_ENABLED', True)
KARGADAN_IMPORT_MOVIES_PER_TICK = max(0, min(40, int(os.environ.get('KARGADAN_IMPORT_MOVIES_PER_TICK', '10'))))
KARGADAN_IMPORT_SERIES_PER_TICK = max(0, min(20, int(os.environ.get('KARGADAN_IMPORT_SERIES_PER_TICK', '5'))))
KARGADAN_IMPORT_REFRESH_PER_TICK = max(0, min(60, int(os.environ.get('KARGADAN_IMPORT_REFRESH_PER_TICK', '16'))))
KARGADAN_IMPORT_RETRY_HOURS = max(1, int(os.environ.get('KARGADAN_IMPORT_RETRY_HOURS', '24')))
KARGADAN_IMPORT_BUDGET_SECONDS = max(0, int(os.environ.get('KARGADAN_IMPORT_BUDGET_SECONDS', '540')))
KARGADAN_IMPORT_CHECKPOINT = os.environ.get(
    'KARGADAN_IMPORT_CHECKPOINT', '/app/media/kargadan_import_checkpoint.json',
).strip() or '/app/media/kargadan_import_checkpoint.json'

# Probe concurrency for the import/crawl lanes (media_probe.probe_many and
# media_verification.screen_links). I/O-bound CDN ranged GETs from background
# workers only — never the public request path — so raising this shortens a
# title's verification time without touching site latency or DB pools.
CATALOG_PROBE_WORKERS = max(1, min(8, int(os.environ.get('CATALOG_PROBE_WORKERS', '6'))))
CATALOG_SCREEN_PROBE_WORKERS = max(1, min(6, int(os.environ.get('CATALOG_SCREEN_PROBE_WORKERS', '4'))))

# SubtitleStar — public Persian sidecar subtitle fallback for movie playback.
# Matching is IMDb-strict and requests are throttled/cached to avoid hammering
# the provider. SUBTITLESTAR_COOKIE is optional for an authorized session only;
# the crawler never attempts to solve browser challenges or CAPTCHAs.
SUBTITLESTAR_ENABLED = env_bool('SUBTITLESTAR_ENABLED', True)
# Online SoftSub: embedded Soft CDN ffmpeg → SubtitleStar → Subzone.ir.
SOFTSUB_ALLOW_FFMPEG = env_bool('SOFTSUB_ALLOW_FFMPEG', False)
# Open-player sync lane: seconds spent attempting an embedded demux of the
# playing file itself before sidecar providers. 0 disables file-first.
PLAYBACK_SYNC_EMBEDDED_SECONDS = max(
    0, int(os.environ.get('PLAYBACK_SYNC_EMBEDDED_SECONDS', '4')))
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
# SubDL official API (exact IMDb/TMDb lookup). Off until SUBDL_API_KEY is set;
# the key is a free subdl.com account key and is never logged.
SUBDL_API_KEY = os.environ.get('SUBDL_API_KEY', '').strip()
SUBDL_ENABLED = env_bool('SUBDL_ENABLED', True)
SUBDL_TIMEOUT_SECONDS = int(os.environ.get('SUBDL_TIMEOUT_SECONDS', '12'))

# IndexNow: tells Bing/Yandex about new title pages within minutes instead of
# the next sitemap crawl. The key is public by design (served at
# /indexnow-key.txt); it only proves the URLs belong to this host.
INDEXNOW_ENABLED = env_bool('INDEXNOW_ENABLED', True)
INDEXNOW_KEY = os.environ.get('INDEXNOW_KEY', '173d5706686eafd33f00b2414e781440').strip()
INDEXNOW_RESUBMIT_SECONDS = int(os.environ.get('INDEXNOW_RESUBMIT_SECONDS', str(30 * 24 * 60 * 60)))
SUBDL_REQUEST_INTERVAL_SECONDS = float(os.environ.get('SUBDL_REQUEST_INTERVAL_SECONDS', '0.5'))
# The SubDL key's quota is shared by every lane. Bulk backfill gets a paced,
# hourly-capped share and pauses for an hour on a 429; an open player (live lane)
# is never budgeted and is back after a few minutes.
SUBDL_BULK_INTERVAL_SECONDS = float(os.environ.get('SUBDL_BULK_INTERVAL_SECONDS', '3'))
SUBDL_BULK_HOURLY_BUDGET = int(os.environ.get('SUBDL_BULK_HOURLY_BUDGET', '90'))
SUBDL_BULK_BACKOFF_SECONDS = int(os.environ.get('SUBDL_BULK_BACKOFF_SECONDS', str(60 * 60)))
SUBDL_LIVE_BACKOFF_SECONDS = int(os.environ.get('SUBDL_LIVE_BACKOFF_SECONDS', '180'))
SUBDL_NEGATIVE_CACHE_SECONDS = int(os.environ.get('SUBDL_NEGATIVE_CACHE_SECONDS', str(6 * 60 * 60)))
SUBDL_MAX_ZIP_BYTES = int(os.environ.get('SUBDL_MAX_ZIP_BYTES', str(8 * 1024 * 1024)))
SUBZONE_VERIFY_SSL = env_bool('SUBZONE_VERIFY_SSL', True)

# Online playback auto-subtitle report pipeline (report → extract → bind).
# The player's sync window is deliberately short: quick provider sidecars only,
# so the POST never blocks video start; everything else runs on the worker.
PLAYBACK_SUBTITLE_SYNC_MAX_SECONDS = max(
    3, int(os.environ.get('PLAYBACK_SUBTITLE_SYNC_MAX_SECONDS', '9')),
)
# Redis micro-cache TTL for the lightweight status endpoint read by player polls.
# After a full worker pass finds no Persian subtitle anywhere (file, providers)
# the gap is "exhausted": ensure/status answer that at once instead of letting
# every viewer re-queue the same empty hunt and poll it for minutes.
PLAYBACK_SUBTITLE_EXHAUSTED_COOLDOWN_SECONDS = max(
    300, int(os.environ.get('PLAYBACK_SUBTITLE_EXHAUSTED_COOLDOWN_SECONDS', str(6 * 60 * 60))),
)
PLAYBACK_SUBTITLE_STATUS_CACHE_SECONDS = max(
    1, int(os.environ.get('PLAYBACK_SUBTITLE_STATUS_CACHE_SECONDS', '3')),
)
# Stale-open playback gap retry safety nets (beat + management command).
PLAYBACK_GAP_DRAIN_MIN_AGE_SECONDS = max(
    30, int(os.environ.get('PLAYBACK_GAP_DRAIN_MIN_AGE_SECONDS', '120')),
)
PLAYBACK_GAP_DRAIN_MAX_PER_BATCH = max(
    1, int(os.environ.get('PLAYBACK_GAP_DRAIN_MAX_PER_BATCH', '20')),
)
PLAYBACK_GAP_DRAIN_MAX_ATTEMPTS = max(
    1, int(os.environ.get('PLAYBACK_GAP_DRAIN_MAX_ATTEMPTS', '3')),
)
# Upper bound (seconds) for the in-request provider sidecar attach. The heavy
# embedded-demux + full provider crawl lives on the Celery worker; the open
# player request only runs a short best-effort lookup so the HTTP call stays fast.
PLAYBACK_SYNC_ATTACH_SECONDS = max(
    1, int(os.environ.get('PLAYBACK_SYNC_ATTACH_SECONDS', '4')),
)
# Recurring re-crawl of published titles whose download/playback links expired
# (Dornatv CDN signatures self-expire ~13 h). The Celery beat task processes a
# bounded batch per run so signatures are refreshed before the player goes dark.
PLAYBACK_REFRESH_BATCH_SIZE = max(1, int(os.environ.get('PLAYBACK_REFRESH_BATCH_SIZE', '120')))
PLAYBACK_REFRESH_INTERVAL_SECONDS = max(
    300, int(os.environ.get('PLAYBACK_REFRESH_INTERVAL_SECONDS', '1800')),
)
PLAYBACK_REFRESH_DELETE = str(
    os.environ.get('PLAYBACK_REFRESH_DELETE', '0'),
).strip().lower() in {'1', 'true', 'yes', 'on'}
PLAYBACK_REFRESH_DELAY_SECONDS = max(
    0.0, float(os.environ.get('PLAYBACK_REFRESH_DELAY_SECONDS', '0.3')),
)

# Playback gateway. Last-resort path for sources a browser genuinely cannot
# open: ffmpeg rewraps the file into fragmented-MP4 HLS on demand, copying the
# video stream whenever it is already H.264 so the cost is I/O, not CPU.
# Sessions are live processes with live segment directories, so both limits
# below are really *disk* limits — see stream_gateway for the sizing.
STREAM_SESSION_ROOT = os.environ.get('STREAM_SESSION_ROOT', '/var/tmp/revayato-stream')
STREAM_MAX_CONCURRENT_REMUX = max(
    1, int(os.environ.get('STREAM_MAX_CONCURRENT_REMUX', '6')),
)
# Re-encoding is the one branch that burns a whole core; only ~0.1% of the
# catalog (9 titles) is HEVC/AV1, so a tiny cap is enough.
STREAM_MAX_CONCURRENT_TRANSCODE = max(
    0, int(os.environ.get('STREAM_MAX_CONCURRENT_TRANSCODE', '2')),
)
STREAM_ALLOW_TRANSCODE = env_bool('STREAM_ALLOW_TRANSCODE', True)
# Hard ceiling on what all live sessions may hold together. The concurrency
# caps bound how many sessions exist, not how large they grow, and this volume
# lives on a disk the whole site shares — so past this the gateway reports
# «busy» rather than taking everything else down with it.
STREAM_DISK_BUDGET_MB = max(
    256, int(os.environ.get('STREAM_DISK_BUDGET_MB', '2048')),
)
# The background sweep only belongs in the gateway container: it reads /proc to
# tell a live ffmpeg from a stale pid, and no other container shares that pid
# namespace. Left off everywhere else.
STREAM_GATEWAY_REAPER = env_bool('STREAM_GATEWAY_REAPER', False)
STREAM_REAPER_SECONDS = max(
    15, int(os.environ.get('STREAM_REAPER_SECONDS', '60')),
)
# CDNs that serve files only to Iranian IPs and send no CORS headers (myf2m's
# abrtech.top → mehracdn.com). Anything outside Iran — this server, the
# gateway, a viewer on a VPN — gets a «turn your VPN off» page instead of the
# file, and the browser remuxer cannot read them at all. Links on these hosts
# are flagged ``iran_only`` so the player plays them natively, never sends them
# to the gateway, and offers an external player / download instead.
GEO_LOCKED_CDN_HOSTS = [
    part.strip().lower().lstrip('.')
    for part in os.environ.get('GEO_LOCKED_CDN_HOSTS', 'abrtech.top,mehracdn.com').replace(';', ',').split(',')
    if part.strip()
]

# Season/episode metadata completion from TMDB. Episodes are created from
# provider download links, so without this pass they keep the stub «قسمت N»
# label and carry no overview, air date, runtime or still image.
EPISODE_METADATA_INTERVAL_SECONDS = max(
    300, int(os.environ.get('EPISODE_METADATA_INTERVAL_SECONDS', '3600')),
)
# Series processed per beat tick. Each series costs one TMDB call per season.
EPISODE_METADATA_SERIES_PER_TICK = max(
    1, int(os.environ.get('EPISODE_METADATA_SERIES_PER_TICK', '25')),
)
# Downloading a still per episode is the expensive part (54k episodes), so the
# recurring pass fills text metadata only unless this is switched on.
EPISODE_METADATA_STILLS = env_bool('EPISODE_METADATA_STILLS', False)
EPISODE_METADATA_DELAY_SECONDS = max(
    0.0, float(os.environ.get('EPISODE_METADATA_DELAY_SECONDS', '0.15')),
)
# A series whose episodes stayed blank after a pass is usually missing the data
# upstream, so it is not re-asked for this many days.
EPISODE_METADATA_RECHECK_DAYS = max(
    0, int(os.environ.get('EPISODE_METADATA_RECHECK_DAYS', '14')),
)

# Primary + secondary link providers for publish auto-crawl and catalog import.
# Always crawl Film2Media, Dornatv and Kargadan and merge qualities.
CATALOG_LINK_PROVIDER = os.environ.get('CATALOG_LINK_PROVIDER', 'myf2m').strip().lower() or 'myf2m'
CATALOG_LINK_PROVIDERS = [
    part.strip().lower()
    for part in os.environ.get('CATALOG_LINK_PROVIDERS', 'myf2m,dornatv,kargadan').replace(';', ',').split(',')
    if part.strip()
] or ['myf2m', 'dornatv', 'kargadan']
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
    if KARGADAN_BASE_URL and not KARGADAN_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('KARGADAN_BASE_URL must use HTTPS when DJANGO_DEBUG is False.')
    if not KARGADAN_VERIFY_SSL:
        raise ImproperlyConfigured('KARGADAN_VERIFY_SSL must remain True when DJANGO_DEBUG is False.')
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
# Native app (Android/TV) requests carry no Origin header; React-Native fetch sees
# our API as cross-origin without a browser-context Origin. Allow-All keeps those
# calls unblocked while credentialed browser traffic still honors the allowlist.
# Defaults to True; set DJANGO_CORS_ALLOW_ALL_ORIGINS=False to restrict strictly.
CORS_ALLOW_ALL_ORIGINS = env_bool('DJANGO_CORS_ALLOW_ALL_ORIGINS', True)
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

# Countries the playback CDNs actually serve. The video files sit on Iranian
# hosts that drop foreign connections silently, so a viewer outside this set
# gets a player that never starts and no reason why; the region endpoint uses
# this list to give them one. Widen it here if a mirror opens elsewhere.
SITE_PLAYBACK_REGIONS = os.environ.get('SITE_PLAYBACK_REGIONS', 'IR').strip()

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
        # Staff admin desk/list/edit calls and TMDB lookups, each in its own
        # bucket (never the site-wide 'user' one). See admin_api.StaffAdminThrottle.
        'staff_admin': os.environ.get('STAFF_ADMIN_THROTTLE_RATE', '600/minute'),
        'staff_tmdb': os.environ.get('STAFF_TMDB_THROTTLE_RATE', '60/minute'),
        'playback_subtitle_ensure': os.environ.get('PLAYBACK_SUBTITLE_ENSURE_THROTTLE_RATE', '30/minute'),
        'playback_subtitle_status': os.environ.get('PLAYBACK_SUBTITLE_STATUS_THROTTLE_RATE', '60/minute'),
        'subtitle_sync_report': os.environ.get('SUBTITLE_SYNC_REPORT_THROTTLE_RATE', '20/minute'),
        'content_issue_report': os.environ.get('CONTENT_ISSUE_REPORT_THROTTLE_RATE', '20/minute'),
        'content_issue_status': os.environ.get('CONTENT_ISSUE_STATUS_THROTTLE_RATE', '60/minute'),
        'playback_failure': os.environ.get('PLAYBACK_FAILURE_THROTTLE_RATE', '30/minute'),
        'watch_party_create': '10/hour',
        'watch_party_join': '60/hour',
        # Playback gateway: opening a session spawns ffmpeg, so it is rare and
        # expensive; segment reads are one every few seconds per viewer and a
        # whole household behind one NAT address must not throttle itself out.
        'stream_open': os.environ.get('STREAM_OPEN_THROTTLE_RATE', '30/minute'),
        # One call per play, and only the lapsed ones cost a crawl — but a
        # whole household behind one NAT is still one anonymous client.
        'playback_resolve': os.environ.get('PLAYBACK_RESOLVE_THROTTLE_RATE', '60/minute'),
        'stream_segment': os.environ.get('STREAM_SEGMENT_THROTTLE_RATE', '600/minute'),
        # The Android launch check. One call per app start, but a household
        # — or a whole mobile carrier NAT — shares a single address, so this
        # cannot sit in the 100/hour anonymous bucket.
        'app_version': os.environ.get('APP_VERSION_THROTTLE_RATE', '120/minute'),
    },
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# SimpleJWT — optional dedicated signing key; falls back to Django SECRET_KEY.
_JWT_SECRET = os.environ.get('JWT_SECRET', '').strip()
JWT_REFRESH_TOKEN_DAYS = max(1, int(os.environ.get('JWT_REFRESH_TOKEN_DAYS', '400')))
# Short-lived access token: it lives in a JS-readable cookie, so a small window
# limits replay. The session itself never depends on it — the client silently
# rotates a new one from the long-lived refresh token before it expires.
JWT_ACCESS_TOKEN_MINUTES = max(5, int(os.environ.get('JWT_ACCESS_TOKEN_MINUTES', '60')))
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=JWT_ACCESS_TOKEN_MINUTES),
    # Rotation renews this browser-compatible 400-day window on active use, so a
    # user who keeps visiting stays signed in until they log out themselves.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    **({'SIGNING_KEY': _JWT_SECRET} if _JWT_SECRET else {}),
}

# --- Android in-app update channel -------------------------------------------
# The APK is sideloaded from /downloads/, not installed from Google Play, so the
# app asks us what the newest build is. `downloads/` is mounted read-only into
# the backend container; the manifest lives beside the APKs it describes so a
# release is a file copy, not an image rebuild. See config/app_release.py.
APP_RELEASE_DIR = os.environ.get('APP_RELEASE_DIR', '/srv/downloads').strip()
APP_RELEASE_MANIFEST = os.environ.get('APP_RELEASE_MANIFEST', '').strip()
APP_DOWNLOAD_BASE_URL = os.environ.get(
    'APP_DOWNLOAD_BASE_URL', f'{SITE_BASE_URL}/downloads' if SITE_BASE_URL else '',
).strip().rstrip('/')

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
# Persian titles from Wikidata / Persian Wikipedia (by IMDb/TMDB id), tried after
# TMDB's own Persian translation and before machine translation. Off under
# `manage.py test` so the suite never depends on a live third-party site.
CATALOG_WIKIDATA_TITLES_ENABLED = (
    os.environ.get('CATALOG_WIKIDATA_TITLES_ENABLED', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
    and 'test' not in sys.argv[1:2]
)
CATALOG_WIKIDATA_TIMEOUT_SECONDS = int(os.environ.get('CATALOG_WIKIDATA_TIMEOUT_SECONDS', '8'))
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
# Download-link sizes (apps/catalog/link_sizes.py). Every save that brings new
# links queues a per-title run on the ``link-sizes`` lane; the beat sweep works
# through the backlog (hot chart → Top 250 → popularity) on the same lane.
CATALOG_LINK_SIZE_ON_IMPORT = env_bool('CATALOG_LINK_SIZE_ON_IMPORT', True)
CATALOG_LINK_SIZE_TITLE_BUDGET_SECONDS = float(os.environ.get('CATALOG_LINK_SIZE_TITLE_BUDGET_SECONDS', '240'))
CATALOG_LINK_SIZE_TITLES_PER_TICK = int(os.environ.get('CATALOG_LINK_SIZE_TITLES_PER_TICK', '150'))
CATALOG_LINK_SIZE_BUDGET_SECONDS = float(os.environ.get('CATALOG_LINK_SIZE_BUDGET_SECONDS', '270'))
CATALOG_LINK_SIZE_WORKERS = int(os.environ.get('CATALOG_LINK_SIZE_WORKERS', '6'))
CATALOG_LINK_SIZE_LINKS_PER_TITLE = int(os.environ.get('CATALOG_LINK_SIZE_LINKS_PER_TITLE', '200'))
# Source fill (apps/catalog/provider_import/source_fill.py): per tick, how many
# titles missing a provider get asked, and the wall-clock budget for the tick.
# Every title costs a search + page fetch per missing provider, plus the dead-link
# screen of whatever it finds, so keep it well under the discovery lanes' share.
CATALOG_SOURCE_FILL_ENABLED = env_bool('CATALOG_SOURCE_FILL_ENABLED', True)
CATALOG_SOURCE_FILL_TITLES_PER_TICK = int(os.environ.get('CATALOG_SOURCE_FILL_TITLES_PER_TICK', '35'))
CATALOG_SOURCE_FILL_BUDGET_SECONDS = float(os.environ.get('CATALOG_SOURCE_FILL_BUDGET_SECONDS', '300'))
CATALOG_SOURCE_FILL_SCAN_WINDOW = int(os.environ.get('CATALOG_SOURCE_FILL_SCAN_WINDOW', '400'))
# Draft source hunt: how often to look for download links for unpublished titles,
# how many to enrol per run, and how many to actually crawl providers for. The fix
# limit is the only one that costs provider requests — keep it well under the
# per-minute budget the live catalog crawler needs.
# Pre-publish media verification (apps/catalog/media_verification.py): nothing
# goes live until its sources answer a real ranged request. Turning this off
# returns the importer to publishing on link *presence*, which is what produced
# the «پخش نمی‌شود» reports in the first place.
CATALOG_VERIFY_MEDIA_BEFORE_PUBLISH = env_bool('CATALOG_VERIFY_MEDIA_BEFORE_PUBLISH', True)
# Screen provider links as they are imported and drop the ones the host reports
# gone (404/410/soft-404), before they are ever stored.
CATALOG_SCREEN_PROVIDER_LINKS = env_bool('CATALOG_SCREEN_PROVIDER_LINKS', True)
# Several mirror CDNs serve valid media behind expired or mismatched certificates.
# The probe only reads the first two kilobytes to decide "does this file exist",
# never credentials, so a chain error must not be reported as a dead file.
CATALOG_PROBE_VERIFY_TLS = env_bool('CATALOG_PROBE_VERIFY_TLS', False)
# Read the container header with ffprobe before calling a source browser-playable
# (apps/catalog/media_tech.py), instead of trusting the codec tokens in its
# filename. Catches HEVC behind a .mp4 name, Matroska behind any name, and DTS
# audio that plays as a silent picture. Off ⇒ back to filename guessing.
CATALOG_VERIFY_CODEC_BEFORE_PUBLISH = env_bool('CATALOG_VERIFY_CODEC_BEFORE_PUBLISH', True)
# Test the link a viewer is handed for *online playback* before handing it over
# (apps/catalog/playback_gate.py): reachable, seekable, and a container/codec a
# browser really decodes. Off ⇒ the playback link goes back to being whichever
# file name scored highest, which is how 74% of movies came to serve an MKV.
CATALOG_VERIFY_PLAYBACK_LINK = env_bool('CATALOG_VERIFY_PLAYBACK_LINK', True)
# Episodes whose playback link is tested *inline*, per series, during an import.
# A movie is one title and gets gated whole; a series is a season pack of up to
# several hundred files, and every test is a ranged GET plus up to two ffprobes,
# so gating all of them inline would turn one crawl into an hour of network
# waits. The episodes this budget covers are published tested; the rest are
# published explicitly untested (unverified, null check cursor), which puts them
# at the head of the playback sweep's queue rather than claiming they work.
CATALOG_EPISODE_GATE_PER_IMPORT = int(os.environ.get('CATALOG_EPISODE_GATE_PER_IMPORT', '6'))
# Validate the subtitle file itself before it is published (apps/catalog/
# subtitle_verify.py): parses, is Persian, is not an advert dump, and its last
# cue actually fits the film's measured runtime.
CATALOG_VERIFY_SUBTITLES_BEFORE_PUBLISH = env_bool('CATALOG_VERIFY_SUBTITLES_BEFORE_PUBLISH', True)
# Titles re-verified per sweep (signed provider URLs expire in ~13 h).
CATALOG_MEDIA_RECHECK_BATCH = int(os.environ.get('CATALOG_MEDIA_RECHECK_BATCH', '40'))
CATALOG_SYNC_INTERVAL_HOURS = int(os.environ.get('CATALOG_SYNC_INTERVAL_HOURS', '6'))
CATALOG_SYNC_STAGE_BATCH_SIZE = int(os.environ.get('CATALOG_SYNC_STAGE_BATCH_SIZE', '2000'))
CATALOG_SYNC_PROCESS_BATCH_SIZE = int(os.environ.get('CATALOG_SYNC_PROCESS_BATCH_SIZE', '20'))
CATALOG_SYNC_ITEM_MAX_ATTEMPTS = int(os.environ.get('CATALOG_SYNC_ITEM_MAX_ATTEMPTS', '3'))
CATALOG_SYNC_ITEMS_PER_SECOND = float(os.environ.get('CATALOG_SYNC_ITEMS_PER_SECOND', '6'))
CATALOG_TMDB_REFRESH_AFTER_DAYS = int(os.environ.get('CATALOG_TMDB_REFRESH_AFTER_DAYS', '150'))
CATALOG_SYNC_STALE_REFRESH_LIMIT = int(os.environ.get('CATALOG_SYNC_STALE_REFRESH_LIMIT', '50000'))
CATALOG_SYNC_STALE_HEARTBEAT_MINUTES = int(os.environ.get('CATALOG_SYNC_STALE_HEARTBEAT_MINUTES', '15'))
CATALOG_PUBLISH_INTERVAL_SECONDS = int(os.environ.get('CATALOG_PUBLISH_INTERVAL_SECONDS', '300'))
CATALOG_PUBLISH_BATCH_SIZE = max(1, int(os.environ.get('CATALOG_PUBLISH_BATCH_SIZE', '50')))

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# ``queue_order_strategy: priority`` makes the Redis transport drain the queues
# in exactly the order a worker lists them with ``-Q`` instead of round-robin.
# That is what keeps a 50k-deep bulk SoftSub backlog on ``softsub`` from starving
# the small maintenance/beat tasks on ``celery`` inside the same worker.
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 2 * 60 * 60,
    'queue_order_strategy': 'priority',
}
# Ceiling for the bulk SoftSub lane (see ``apps.catalog.tasks.softsub_queue_saturated``).
# Routing alone does not bound a queue: the per-title enqueue lock expires after two
# hours, so a lane consuming slower than it is fed re-admits the same titles forever.
# Production hit 154,481 queued tasks for 23,477 titles that way. Above this mark the
# producers stop admitting background work; the live-player ``softsub-urgent`` lane is
# never gated. 0 disables the ceiling.
CATALOG_SOFTSUB_QUEUE_MAX_DEPTH = int(os.environ.get('CATALOG_SOFTSUB_QUEUE_MAX_DEPTH', '5000') or 0)
# Minutes without progress after which an import job is presumed abandoned and
# failed, so its provider stops answering 409 ``job_active`` forever. A running
# job touches ``updated_at`` on every item, so this only catches dead workers.
CATALOG_IMPORT_JOB_STALE_MINUTES = int(os.environ.get('CATALOG_IMPORT_JOB_STALE_MINUTES', '60') or 60)
# How long a provider discovery lane may go without *finishing* a run before
# ``import_watchdog_task`` clears its lock and starts it again. Must stay above
# the slowest schedule (myf2m, 10 min) plus one full run (hard limit 15 min), so
# a healthy-but-slow lane is never restarted underneath itself.
CATALOG_IMPORT_SILENCE_MINUTES = int(os.environ.get('CATALOG_IMPORT_SILENCE_MINUTES', '45') or 45)
# IMDb Top 250 completion lane (``complete_top250_task``). Budget is the wall-clock
# time one tick may spend; it must stay under the task's 28-minute soft limit.
CATALOG_TOP250_ENABLED = env_bool('CATALOG_TOP250_ENABLED', True)
CATALOG_TOP250_LIMIT = int(os.environ.get('CATALOG_TOP250_LIMIT', '40') or 40)
CATALOG_TOP250_RETRY_HOURS = float(os.environ.get('CATALOG_TOP250_RETRY_HOURS', '24') or 24)
CATALOG_TOP250_DELAY_SECONDS = float(os.environ.get('CATALOG_TOP250_DELAY_SECONDS', '0.5') or 0)
CATALOG_TOP250_BUDGET_SECONDS = int(os.environ.get('CATALOG_TOP250_BUDGET_SECONDS', '1200') or 1200)
# Hot titles lane: TMDB trending/now-playing/new releases, completed hottest first
# (see apps.catalog.hot_titles). The same chart orders every other queue.
CATALOG_HOT_ENABLED = env_bool('CATALOG_HOT_ENABLED', True)
CATALOG_HOT_LIMIT = int(os.environ.get('CATALOG_HOT_LIMIT', '30') or 30)
CATALOG_HOT_RETRY_HOURS = float(os.environ.get('CATALOG_HOT_RETRY_HOURS', '6') or 6)
CATALOG_HOT_DELAY_SECONDS = float(os.environ.get('CATALOG_HOT_DELAY_SECONDS', '0.5') or 0)
CATALOG_HOT_BUDGET_SECONDS = int(os.environ.get('CATALOG_HOT_BUDGET_SECONDS', '540') or 540)
CATALOG_HOT_CHART_SIZE = int(os.environ.get('CATALOG_HOT_CHART_SIZE', '80') or 80)
CATALOG_HOT_CHART_MAX_AGE_HOURS = float(os.environ.get('CATALOG_HOT_CHART_MAX_AGE_HOURS', '2') or 2)
CATALOG_HOT_TMDB_PAGES = int(os.environ.get('CATALOG_HOT_TMDB_PAGES', '2') or 2)
# Lanes:
#   celery         — short maintenance + beat ticks (highest priority)
#   imports        — long admin catalog import jobs (hours, network bound)
#   softsub        — bulk subtitle extraction backlog (tens of thousands of rows)
#   softsub-urgent — live player subtitle requests, must never queue behind bulk
#   softsub-drain  — re-runs of old viewer reports; same worker, read only when
#                    softsub-urgent is empty, hunts on the bulk provider lane
# Without these routes every task landed on ``celery`` behind the bulk backlog,
# so beat ticks piled up unprocessed and the crawler effectively never ran.
CELERY_TASK_ROUTES = {
    # User-facing support lane. Answering a ticket or fixing a viewer's report must
    # never wait behind the ~25-minute playback-refresh crawl that occupies the
    # default ``celery`` worker (it used to expire ~87% of support ticks unrun).
    'apps.engagement.tasks.resolve_support_tickets_task': {'queue': 'support'},
    'apps.engagement.tasks.process_support_ticket_task': {'queue': 'support'},
    'apps.catalog.tasks.handle_content_report_task': {'queue': 'support'},
    'apps.catalog.tasks.drain_content_reports_task': {'queue': 'support'},
    # Admin desk «تکمیل کامل» runs on its own worker (catalog-worker-admin);
    # bulk selections pass queue='imports' explicitly.
    'apps.catalog.tasks.complete_title_task': {'queue': 'admin-ops'},
    'apps.catalog.tasks.extract_movie_softsub_task': {'queue': 'softsub'},
    'apps.catalog.tasks.extract_series_softsub_task': {'queue': 'softsub'},
    'apps.catalog.provider_import.tasks.run_catalog_import_task': {'queue': 'imports'},
    'apps.catalog.provider_import.tasks.run_catalog_year_import_task': {'queue': 'imports'},
    'apps.catalog.provider_import.tasks.complete_episode_metadata_task': {'queue': 'imports'},
    'apps.catalog.provider_import.tasks.auto_crawl_myf2m_movie_downloads_task': {'queue': 'imports'},
    'apps.catalog.provider_import.tasks.auto_crawl_myf2m_series_downloads_task': {'queue': 'imports'},
    # Provider discovery beat ticks are long-running crawls. Left on the default
    # lane they queue behind (and behind) every maintenance task, which is how the
    # default queue grew tens of thousands of stale messages.
    #
    # They then have to be split off ``imports`` as well, for the same reason one
    # step down: ``imports`` carries the per-title ``auto_crawl_*`` retries, which
    # run ~790 deep and take minutes to clear. Discovery is the only producer of
    # *new* titles, so parking it behind that backlog stops the archive growing
    # while every container still looks healthy. Its own lane is consumed first by
    # the imports worker, so a deep retry backlog can no longer starve it.
    'apps.catalog.provider_import.tasks.import_missing_dornatv_task': {'queue': 'imports-discovery'},
    'apps.catalog.provider_import.tasks.import_missing_myf2m_task': {'queue': 'imports-discovery'},
    'apps.catalog.provider_import.tasks.import_missing_kargadan_task': {'queue': 'imports-discovery'},
    'apps.catalog.provider_import.tasks.fill_missing_sources_task': {'queue': 'imports-discovery'},
    # Top 250 gets a lane of its own, listed first on the imports worker: it is
    # the shelf users see first, and it must not wait behind either of the above.
    'apps.catalog.provider_import.tasks.complete_top250_task': {'queue': 'imports-top250'},
    'apps.catalog.provider_import.tasks.complete_hot_titles_task': {'queue': 'imports-hot'},
    # جدول پخش: new episodes are the hottest titles there are, so the date sync
    # and the release hunter ride the hot lane. See apps/catalog/airing.py.
    'apps.catalog.tasks.sync_airing_schedule_task': {'queue': 'imports-hot'},
    'apps.catalog.tasks.hunt_airing_releases_task': {'queue': 'imports-hot'},
    'apps.catalog.tasks.fill_link_sizes_task': {'queue': 'link-sizes'},
    'apps.catalog.tasks.size_title_links_task': {'queue': 'link-sizes'},
    'apps.catalog.provider_import.tasks.import_watchdog_task': {'queue': 'support'},
    'apps.catalog.provider_import.tasks.reap_stale_import_jobs_task': {'queue': 'support'},
}
# Every beat tick expires well before the next one is due. A worker that falls
# behind therefore discards stale duplicates instead of accumulating them
# forever (the production queue had grown to 5k copies of a single 5-minute
# tick, which is why maintenance work never reached the head of the queue).
CELERY_BEAT_SCHEDULE = {
    # Answer & remediate the support inbox (درخواست‌ها) automatically. Runs every
    # few minutes: phase 1 gives every OPEN ticket a real first response (status-
    # based, so a human glancing at the inbox can't make it abandon a ticket);
    # phase 2 re-checks parked in_progress tickets (crawl-free) and auto-resolves
    # them once the dedicated crawlers land a browser-safe source / the import
    # finishes — closing the loop with the user. Idempotent by design.
    'engagement-resolve-support-tickets': {
        'task': 'apps.engagement.tasks.resolve_support_tickets_task',
        'schedule': 180,
        'options': {'expires': 170},
    },
    # Long-tail worker for viewer «گزارش خطا» reports: crawl-free sweep of reports
    # whose title now plays + a small re-crawl batch on a widening backoff, then
    # notifies the owners of whatever got fixed. Event-driven intake
    # (handle_content_report_task) does the fast path; this is the safety net.
    'catalog-drain-content-reports': {
        'task': 'apps.catalog.tasks.drain_content_reports_task',
        'schedule': 300,
        'options': {'expires': 290},
    },
    # Published titles decay on their own: signed provider URLs expire in ~13 h
    # and mirrors get purged. Re-test the stale ones and repair them before a
    # viewer has to report it. See media_verification.sweep_published_media.
    'catalog-verify-media': {
        'task': 'apps.catalog.tasks.verify_catalog_media_task',
        'schedule': 1800,
        'options': {'expires': 1700, 'queue': 'support'},
    },
    # Sizes on every download link («1080p · 2.30 GB»): the backlog sweep. New
    # links are sized at import by their own per-title run on the same lane —
    # it used to share the two support slots with viewers' tickets.
    'catalog-fill-link-sizes': {
        'task': 'apps.catalog.tasks.fill_link_sizes_task',
        'schedule': 5 * 60,
        'options': {'expires': 4 * 60, 'queue': 'link-sizes'},
    },
    'catalog-sync-watchdog': {
        'task': 'apps.catalog.tasks.catalog_sync_watchdog_task',
        'schedule': 300,
        'options': {'expires': 280},
    },
    'catalog-metadata-sync': {
        'task': 'apps.catalog.tasks.sync_catalog_task',
        'schedule': 15 * 60,
        'options': {'expires': 14 * 60},
    },
    # Nothing else moves an import job out of RUNNING, so a worker that dies
    # mid-job locks its provider behind a permanent 409 ``job_active``.
    'catalog-reap-stale-import-jobs': {
        'task': 'apps.catalog.provider_import.tasks.reap_stale_import_jobs_task',
        'schedule': 10 * 60,
        'options': {'queue': 'support', 'expires': 9 * 60},
    },
    'catalog-softsub-backfill': {
        'task': 'apps.catalog.tasks.backfill_softsub_tracks_task',
        'schedule': 60 * 60,
        'options': {'expires': 55 * 60},
    },
    'catalog-playback-gap-drain': {
        'task': 'apps.catalog.tasks.drain_playback_subtitle_gaps_task',
        'schedule': 300,
        'options': {'expires': 280},
    },
    # Bake the crowd-sourced subtitle timing consensus into the served VTT files.
    # Runs infrequently and does bounded work per tick so it never competes with
    # playback or the crawlers for the box.
    'catalog-subtitle-sync-verify': {
        'task': 'apps.catalog.tasks.verify_subtitle_sync_task',
        'schedule': 30 * 60,
        'options': {'expires': 28 * 60},
    },
    'catalog-refresh-expired-playback': {
        'task': 'apps.catalog.tasks.refresh_expired_playback_task',
        'schedule': PLAYBACK_REFRESH_INTERVAL_SECONDS,
        'options': {'expires': max(120, PLAYBACK_REFRESH_INTERVAL_SECONDS - 60)},
    },
    # ``expires`` shorter than the schedule is right for a tick with no other
    # de-duplication, but it is fatal for these two. They already refuse to overlap
    # (the 14-minute ``*-import-missing-lock`` returns ``already_running``), so the
    # tight expiry bought nothing and cost everything: once the lane backed up past
    # ~5 minutes, every tick aged out while queued and the worker logged
    # ``Discarding revoked task``. Production imported nothing for hours that way,
    # with no error line anywhere. The window is now several schedules wide — long
    # enough to survive a backlog, still short enough that an outage cannot leave
    # an unbounded pile of ticks behind.
    'catalog-dornatv-import-missing': {
        'task': 'apps.catalog.provider_import.tasks.import_missing_dornatv_task',
        'schedule': 300,
        'options': {'queue': 'imports-discovery', 'expires': 3 * 300},
    },
    # Film2Media is the primary provider, so it is walked at least as often as
    # Dornatv. A tick finishes its listing pages in well under a minute (the
    # 14-minute lock still stops two ticks overlapping), so the old 600s cadence
    # left the lane idle most of the time while the deep walk crawled along.
    'catalog-myf2m-import-missing': {
        'task': 'apps.catalog.provider_import.tasks.import_missing_myf2m_task',
        'schedule': 300,
        'options': {'queue': 'imports-discovery', 'expires': 3 * 300},
    },
    # Kargadan: sitemap diff, so a tick with nothing new costs ~10 requests.
    'catalog-kargadan-import-missing': {
        'task': 'apps.catalog.provider_import.tasks.import_missing_kargadan_task',
        'schedule': 600,
        'options': {'queue': 'imports-discovery', 'expires': 3 * 600},
    },
    # Every published title should carry links from every provider that has it.
    # Asks only the providers a title has no links from, hot chart first; each
    # (title, provider) answer is remembered for a week. See source_fill.py.
    'catalog-source-fill': {
        'task': 'apps.catalog.provider_import.tasks.fill_missing_sources_task',
        'schedule': 600,
        'options': {'queue': 'imports-discovery', 'expires': 3 * 600},
    },
    # Newly published titles -> Bing/Yandex in one IndexNow batch. See indexnow.py.
    'catalog-indexnow-flush': {
        'task': 'apps.catalog.tasks.indexnow_flush_task',
        'schedule': 600,
        'options': {'queue': 'celery', 'expires': 600},
    },
    # IMDb Top 250 completion. A tick that finds nothing left to do returns in
    # seconds, so a short cadence costs nothing once the shelf is complete.
    'catalog-top250-complete': {
        'task': 'apps.catalog.provider_import.tasks.complete_top250_task',
        'schedule': 600,
        'options': {'queue': 'imports-top250', 'expires': 3 * 600},
    },
    # This week's trending/newest titles, hottest first. A tick with nothing
    # missing returns in seconds; the chart itself is rebuilt every ~2 hours.
    'catalog-hot-titles-complete': {
        'task': 'apps.catalog.provider_import.tasks.complete_hot_titles_task',
        'schedule': 600,
        'options': {'queue': 'imports-hot', 'expires': 3 * 600},
    },
    # جدول پخش. Sync: TMDB episode air dates / digital release dates of every
    # airing title (each re-read every 6–12 h; a tick with nothing due is a few
    # queries). Hunt: from the morning a release is due (Tehran), crawl the
    # providers for it every 2 h → 6 h → daily until it is on the site.
    'catalog-airing-sync': {
        'task': 'apps.catalog.tasks.sync_airing_schedule_task',
        'schedule': 30 * 60,
        'options': {'queue': 'imports-hot', 'expires': 25 * 60},
    },
    'catalog-airing-hunt': {
        'task': 'apps.catalog.tasks.hunt_airing_releases_task',
        'schedule': 10 * 60,
        'options': {'queue': 'imports-hot', 'expires': 3 * 600},
    },
    # Last line of defence: restarts discovery whenever it stops finishing runs,
    # whatever the cause. See ``import_watchdog_task``.
    'catalog-import-watchdog': {
        'task': 'apps.catalog.provider_import.tasks.import_watchdog_task',
        'schedule': 5 * 60,
        'options': {'queue': 'support', 'expires': 4 * 60},
    },
    'catalog-episode-metadata': {
        'task': 'apps.catalog.provider_import.tasks.complete_episode_metadata_task',
        'schedule': EPISODE_METADATA_INTERVAL_SECONDS,
        'options': {'expires': max(120, EPISODE_METADATA_INTERVAL_SECONDS - 60)},
    },
    # NOTE: IMDb rating sync (``sync_imdb_ratings_task``) and archive completion
    # (``hunt_draft_sources_task``) are deliberately NOT scheduled here. Both are
    # long provider/network jobs and the only lane that fits them, ``imports``,
    # runs at concurrency 1 and was measured ~900 messages deep — a beat tick
    # placed there expires unrun. They run instead as lanes of the permanent
    # ``catalog-crawler`` container (backend/scripts/run_myf2m_catalog_loop.py),
    # which is always on and shares its budget with nothing. Both tasks remain
    # callable by hand for a one-off run.
    # Rotating refresh tokens for 400 days means the blacklist tables only grow.
    # Expired rows can no longer authorise anything, so sweep them daily to keep
    # the refresh endpoint — the thing that keeps sessions alive — fast.
    'accounts-flush-expired-tokens': {
        'task': 'apps.accounts.tasks.flush_expired_tokens_task',
        'schedule': 24 * 60 * 60,
        'options': {'expires': 12 * 60 * 60},
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
