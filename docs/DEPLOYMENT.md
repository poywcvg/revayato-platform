# Revayato production deployment

This runbook deploys the public Revayato application on one Linux server. Video delivery must remain on a dedicated streaming provider/CDN; the application server only serves Nuxt, the API, WebSockets, database traffic, and small media assets.

## Server baseline

- Ubuntu 24.04 LTS or another maintained Linux distribution
- 4 vCPU, 8 GB RAM, 80 GB NVMe or better
- A public IPv4 address
- TCP ports 22, 80, and 443 allowed; UDP 443 is optional for HTTP/3
- Docker Engine with the Compose plugin

Only Caddy exposes public ports. PostgreSQL and Redis are isolated on Docker's internal `data` network.

## 1. DNS and environment

Create `A` records for `SITE_DOMAIN` and `www.SITE_DOMAIN` pointing to the server IP.
With the default same-origin layout, the site, API (`/api`), admin (`/admin`),
WebSockets (`/ws`), and local media (`/media`) all share `https://revayato.com`.
Caddy redirects `www` to the apex host permanently.

If a proxying DNS provider (for example Cloudflare orange-cloud) is used, keep
records **DNS-only** until Caddy has obtained the first TLS certificate, or
terminate TLS at the proxy in Full (strict) mode after Caddy has a valid cert.

On the server:

```sh
cp .env.production.example .env.production
chmod 600 .env.production
```

Fill every placeholder. Generate independent random values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`. The production file is ignored by Git and must never be committed.

Required before launch:

- `SITE_BASE_URL`, `API_BASE_URL`, `MEDIA_CDN_BASE_URL`, `DOWNLOAD_CDN_BASE_URL`, and `WS_BASE_URL`
- matching `SITE_DOMAIN`, `WWW_DOMAIN`, and `ACME_EMAIL`
- allowed hosts, CORS, CSRF, and `FRONTEND_URL` for the site origin
- `DJANGO_SECURE_SSL_REDIRECT=False` when Caddy terminates TLS (container healthchecks use HTTP)
- TMDB bearer credentials (`TMDB_READ_ACCESS_TOKEN`) for admin import — never expose them to Nuxt public runtime
- optional `TMDB_PROXY_URL`, `HTTPS_PROXY`, or `HTTP_PROXY` when the server cannot reach TMDB directly
- a working SMTP account so password-reset emails are delivered
- licensed production object keys from a streaming provider/CDN (do not paste full CDN URLs into catalog rows)
- optional S3-compatible media credentials for posters and avatars
- optional private `ARCHIVE_*` Object Storage credentials for staff original-file
  archive uploads (never reuse the public `AWS_*` media bucket; see
  [ENVIRONMENT.md](ENVIRONMENT.md))
- optional licensed provider credentials (`AVASARAMI_*`) for staff archive
  import via official API/token/cookie/feed only — never CAPTCHA bypass; see
  [PROVIDER_IMPORT.md](PROVIDER_IMPORT.md)
- optional Film2Media crawler settings (`MYF2M_*`) for public download link
  crawl — see [ENVIRONMENT.md](ENVIRONMENT.md)

Do not run `seed_catalog` in production; it intentionally uses public demo streams. Add licensed titles through Django Admin or an approved import process.

For draft-first automatic metadata ingestion and scheduled publication, see [docs/CATALOG_INGESTION.md](CATALOG_INGESTION.md). The deployment includes dedicated Celery worker/beat services; they require a configured metadata token and a private licensed-media manifest.

## 2. First deployment

```sh
chmod +x ops/deploy.sh ops/backup-db.sh
./ops/deploy.sh
```

The backend container applies database migrations and collects static assets before starting Daphne/ASGI. Caddy automatically provisions and renews HTTPS certificates and proxies WebSocket upgrades.

The `catalog-crawler` service is permanent but low priority. Each round imports
Film2Media titles missing from the catalog, re-crawls existing series for new
episodes and existing movies for new qualities, fills missing download sizes,
and then sleeps for `MYF2M_CRAWL_INTERVAL_SECONDS` (30 minutes in the current
production environment). Its default hard CPU limit is 0.15 core; tune the
interval/delay instead of raising that limit on a busy host. Check it with:

```sh
docker compose --env-file .env.production -f compose.production.yaml ps catalog-crawler
docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 catalog-crawler
```

Create the first administrator:

```sh
docker compose --env-file .env.production -f compose.production.yaml exec backend python manage.py createsuperuser
```

## 3. Smoke checks

```sh
curl -fsS "$API_BASE_URL/api/health/"
curl -fsSI "$SITE_BASE_URL/"
curl -fsSI "$SITE_BASE_URL/robots.txt"
curl -fsSI "$SITE_BASE_URL/sitemap.xml"
docker compose --env-file .env.production -f compose.production.yaml ps
```

Then verify in two separate authenticated browsers:

1. registration, login, logout, and password reset;
2. catalog API data instead of mock content;
3. movie and episode playback on mobile and desktop networks;
4. Watch Party join, chat, playback synchronization, and reconnect;
5. non-staff access to `/admin/movies` and `/api/admin/` is denied;
6. staff TMDB search, preview, dry-run import, draft import, and safe sync;
7. admin poster/backdrop upload and draft/published validation;
8. staff provider-import validate on `/admin/provider-import` (CAPTCHA warning
   when interactive login is the only option; no secret values in responses);
9. a real email delivered from the configured sender.

After HTTPS has been stable, raise `DJANGO_SECURE_HSTS_SECONDS` from `3600` to `31536000`. Enable subdomains/preload only when every subdomain is permanently HTTPS.

## 4. Database backups

Create a PostgreSQL dump and a media-volume archive daily:

```sh
BACKUP_DIR=/srv/revayato-backups ./ops/backup-db.sh
```

Copy both backup files to a different provider or object-storage bucket. A backup on the same disk is not disaster recovery. Periodically restore the latest dump into a temporary database and extract the latest media archive to verify them.

Example cron entry for 03:20 UTC:

```cron
20 3 * * * cd /srv/revayato && BACKUP_DIR=/srv/revayato-backups ./ops/backup-db.sh >> /var/log/revayato-backup.log 2>&1
```

## 5. Updates and rollback

Before every update, create a database backup. Then deploy the reviewed code:

```sh
./ops/backup-db.sh
./ops/deploy.sh
```

Keep the previous application revision available. A code rollback does not reverse database migrations; destructive schema migrations require their own tested rollback plan.

Useful diagnostics:

```sh
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 backend
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 frontend
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 caddy
```

## 6. Scaling signals

Move PostgreSQL to a managed database before adding multiple application servers. Add a second backend/frontend replica and a load balancer when sustained CPU is above 60%, memory above 75%, or load tests no longer meet the target latency. Redis must remain shared by every backend replica so Watch Party rooms continue to synchronize.
