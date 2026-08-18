# Revayato | روایتو

A Nuxt + Django streaming platform for the Revayato brand, with catalog, engagement, personalized recommendations, and private Watch Party rooms.

## Local development

Prerequisites: Python 3.11+, Node.js 20+, pnpm, and Docker (for Redis).

```powershell
docker compose up -d redis

cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
pnpm install
pnpm dev
```

In a third terminal — the Android app (mobile + TV, one codebase):

```powershell
pnpm app:start      # Metro bundle server
# then, in another terminal:
pnpm app:android    # install + launch on a running emulator / adb device
```

The app defaults to `http://10.0.2.2:8000/api` (emulator → host). Use
`$env:API_BASE_URL` for a physical device/TV, and JDK 17+/Android SDK per
[android-app/README.md](android-app/README.md).

The frontend runs at `http://127.0.0.1:3000`, Django/ASGI at `http://127.0.0.1:8000`, and Redis is bound to localhost on port `6379`.

## Watch Party

Authenticated users can create private movie or episode rooms, copy a secure invite link, chat in real time, and receive host-controlled playback synchronization. See [docs/WATCH_PARTY.md](docs/WATCH_PARTY.md) for the API/event contract, deployment settings, reverse-proxy requirements, and test commands.

Never commit `.env` files or production credentials. `.env.example` contains placeholders only.

## Production

The production stack is defined in `compose.production.yaml` and includes Nuxt, Django/ASGI, PostgreSQL, Redis, and Caddy with automatic HTTPS and WebSocket proxying. Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) before exposing the service publicly.

Automated metadata/media readiness is documented in [docs/CATALOG_INGESTION.md](docs/CATALOG_INGESTION.md). It is draft-first and requires licensed media keys before anything can be published automatically.

### Public URL domains

Catalog rows store only relative object keys such as `movies/123/hls/master.m3u8`. API serializers and playback payloads build the public URL at response time. To move a CDN or download host later, update `SITE_BASE_URL`, `API_BASE_URL`, `MEDIA_CDN_BASE_URL`, and `DOWNLOAD_CDN_BASE_URL` in the deployment environment (plus the matching Nuxt public runtime variables), then restart/rebuild the services. No database edit or media-row migration is required.

## Authentication and notifications

Authentication uses short-lived JWT access tokens, rotating refresh tokens, refresh-token blacklisting on logout, temporary login locking, and email-based password reset. Run `python manage.py migrate` after updating so the SimpleJWT blacklist tables are available.

For real password-reset delivery, replace the console email backend with your SMTP provider using the `EMAIL_*` values documented in `.env.example`. Keep `DJANGO_SECRET_KEY` private and stable in production. The header notification center and toast feedback are in-app and require no external notification service.
