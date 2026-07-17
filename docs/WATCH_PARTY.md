# Watch Party operations

## Architecture

- Room membership, chat history, and the latest playback state are persisted in Django models.
- Django Channels handles `/ws/watch-party/<invite_code>/` and Redis carries channel-group broadcasts.
- REST and WebSocket entry points require the existing JWT-authenticated user.
- Browser WebSockets send the JWT in the `watchparty.jwt.<token>` subprotocol, not in the URL.
- A user must join through REST before opening the socket. Only the host can mutate playback or end the room.
- The current content-access boundary requires a published movie or a published episode/season/series. Replace `user_can_access_room_content` when subscription entitlements are introduced.

## Environment

Required production values:

```dotenv
DJANGO_SECRET_KEY=<long-random-secret>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.example.com,app.example.com
DJANGO_CORS_ALLOWED_ORIGINS=https://app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
REDIS_URL=redis://redis:6379/0
CHANNEL_LAYER_BACKEND=channels_redis.core.RedisChannelLayer
NUXT_PUBLIC_API_BASE=https://api.example.com/api
NUXT_PUBLIC_WS_BASE=wss://api.example.com
```

Optional tuning values are `WATCH_PARTY_MAX_MEMBERS`, `WATCH_PARTY_DEFAULT_EXPIRY_MINUTES`, and `WATCH_PARTY_CHAT_MAX_LENGTH`. Never use the in-memory channel layer outside isolated tests.

## Local Redis and ASGI

```powershell
docker compose up -d redis
cd backend
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Because Daphne is installed before Django static files, `runserver` serves HTTP and WebSockets in development. A direct production ASGI command is:

```text
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Run at least two ASGI processes behind the load balancer for availability. All processes must share the same database and Redis channel layer.

## Reverse proxy

Route both `/api/` and `/ws/` to the ASGI service. The `/ws/` location must forward HTTP/1.1 WebSocket upgrade headers and preserve the `Sec-WebSocket-Protocol` header. Terminate TLS at the proxy so browsers use `wss://` in production. Add the frontend host to `DJANGO_ALLOWED_HOSTS`; Channels uses it to validate the WebSocket `Origin`.

Avoid logging authorization and WebSocket subprotocol headers. Apply normal connection and request limits at the proxy. Redis must stay on a private network and must not be published to the public internet.

## REST endpoints

- `POST /api/watch-party/rooms/`
- `GET /api/watch-party/rooms/<code>/`
- `POST /api/watch-party/rooms/<code>/join/`
- `POST /api/watch-party/rooms/<code>/leave/`
- `GET /api/watch-party/rooms/<code>/messages/?limit=50`
- `POST /api/watch-party/rooms/<code>/end/`

Create payload:

```json
{"content_type":"movie","content_id":1,"expires_in_minutes":240}
```

Use `content_type: "episode"` with an episode ID for series playback.

## WebSocket contract

Clients send `room.join`, `room.leave`, `chat.message`, `playback.play`, `playback.pause`, `playback.seek`, periodic host `playback.sync`, `playback.sync.request`, `latency.ping`, and `heartbeat`. The server sends `room.state`, `member.joined`, `member.left`, `chat.message`, playback events/states, sync responses, `latency.pong`, and structured `error` events.

Playback payloads contain `position_seconds`, `duration_seconds`, and `playback_rate`. The persisted state also includes `is_playing`, `updated_by`, and `updated_at`. Hosts publish a lightweight state heartbeat every four seconds. Clients estimate round-trip latency and server clock offset with `latency.ping`/`latency.pong`; small drift is corrected with a temporary playback-rate adjustment and large drift is corrected with a seek. The Nuxt player suppresses local emissions while applying a remote state to prevent event loops.

## Deployment checklist

1. Install the updated `backend/requirements.txt`.
2. Provision a private Redis instance and set `REDIS_URL`.
3. Run `python manage.py migrate` to apply `watchparty.0001_initial`.
4. Serve Django with an ASGI server, not a WSGI-only process.
5. Proxy `/ws/` with upgrade and subprotocol headers intact.
6. Set the public Nuxt WebSocket base to `wss://...` and rebuild the frontend.
7. Verify two authenticated browser sessions can join, chat, synchronize playback, reconnect, and reject member playback attempts.

The repository's `compose.production.yaml` and `ops/Caddyfile` implement these ASGI, Redis, TLS, and WebSocket requirements. See `docs/DEPLOYMENT.md` for the complete public-launch runbook.

## Validation commands

```powershell
cd backend
$env:CHANNEL_LAYER_BACKEND='channels.layers.InMemoryChannelLayer'
.\.venv\Scripts\python.exe manage.py test apps.watchparty

cd ..\frontend
pnpm lint
pnpm typecheck
pnpm build
```
