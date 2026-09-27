# روایتو — Android App (Revayato)

A native Android client for the Revayato (روایتو) streaming platform, built from
scratch in **Kotlin** with **Jetpack Compose** and **Material 3**. It talks to the
same production backend as the web app (`https://revayato.com`), so the catalog,
accounts, watch history, watch parties and downloads stay in sync across web and
mobile.

The UI is Persian-first and fully **RTL**.

---

## Features

- **Online streaming first** — Media3/ExoPlayer player with HLS, adaptive quality,
  subtitle tracks, speed control, 10s seek, and resume-from-position.
- **Real, synced watch party** (تماشای گروهی) — join by invite code, host-controlled
  playback, live chat, member presence, and drift-corrected sync over WebSocket.
- **Downloads, both modes** (هر دو حالت):
  - **In-app offline playback** — cached with Media3 `DownloadService` + `SimpleCache`
    and played back through the same cache-backed data source.
  - **Shareable file** — saved to the phone's public `Downloads/` folder via the
    system `DownloadManager`.
- **Full catalog** — home rails, search, movie/series detail with seasons & episodes,
  collections, and paginated catalog lists.
- **Accounts** — login, register, password reset, profile, watchlist & favorites.

---

## Tech stack

| Concern            | Choice                                                        |
| ------------------ | ------------------------------------------------------------- |
| Language / UI      | Kotlin, Jetpack Compose, Material 3                           |
| Min / Target SDK   | `minSdk 24`, `targetSdk 35`, `compileSdk 35`, Java 17         |
| Player / downloads | Media3 (ExoPlayer, HLS, Cache, DownloadService) `1.5.x`       |
| Networking         | Retrofit 2 + OkHttp 4 + kotlinx.serialization                 |
| Realtime           | OkHttp WebSocket (watch party)                                |
| DI                 | Hilt (+ `hilt-navigation-compose`)                            |
| Navigation         | `androidx.navigation.compose`                                 |
| Storage            | DataStore Preferences (JWT access/refresh tokens)             |
| Images             | Coil                                                          |

---

## Architecture

Package layout under `app/src/main/java/com/revayato/app/`:

```
core/
  auth/      TokenStore (DataStore-backed JWT), auth interceptor/state
  di/        Hilt modules (network, etc.)
  download/  DownloadUtil (cache + DownloadManager), RevayatoDownloadService,
             DownloadsManager (offline + shareable file)
  network/   Retrofit/OkHttp setup, ApiResult, safeApiCall
  theme/     Color palette, typography, Material theme
  ui/        UiState, shared UI helpers
  util/      URL helpers, etc.
data/
  model/     Serializable DTOs (Catalog, WatchParty, Engagement, User…)
  remote/    Retrofit API interfaces
  repository/ Repositories (Catalog, Auth, Engagement, WatchParty)
feature/
  auth/ catalog/ collection/ detail/ downloads/ home/ library/
  player/ profile/ search/ watchparty/     ← each: ViewModel + Compose screen
navigation/  RevayatoRoot (NavHost), Destinations (routes)
ui/components/  Reusable composables (NetworkImage, MediaRail, StateViews…)
```

Each feature follows **ViewModel (Hilt) → StateFlow<UiState> → Compose screen**.
Repositories return a sealed `ApiResult<T>` (`Success`/`Error`); ViewModels map
that into `UiState`.

### Watch-party sync

The room socket connects to `wss://revayato.com/ws/watch-party/<code>/`, passing the
JWT in the WebSocket subprotocol (`watchparty.jwt.<token>`). The backend consumer
**requires prior REST membership**, so `WatchPartyRoomViewModel.connect()` calls the
REST `joinRoom` first, then opens the socket. Guests project the host's real position
using a clock offset measured via `latency.ping`/`latency.pong`, and re-seek only when
drift exceeds a tolerance. The socket uses a dedicated OkHttp client with call/read
timeouts disabled and a 20s ping interval (the REST client's 60s call timeout would
otherwise kill the long-lived connection).

### Downloads

`DownloadUtil` owns process-wide singletons (`SimpleCache`, `DownloadManager`,
notification helper) because `RevayatoDownloadService` is framework-instantiated and
can't be Hilt-injected. `PlayerViewModel` plays through the same cache-backed
`DataSource.Factory`, so a downloaded title plays without the network. The notification
channel (`revayato_downloads`) is created in `RevayatoApp`.

---

## Build & run

Requires Android Studio (Ladybug+) or the Android SDK with an API 35 platform.

```bash
cd android
./gradlew :app:assembleDebug
```

- **Debug** builds use `applicationId` `com.revayato.app.debug` and point at the
  production backend (`https://revayato.com`), so you can run against real data.
- **Release** builds use `com.revayato.app`.

Install a debug build on a connected device:

```bash
./gradlew :app:installDebug
```

### Backend endpoints

Both build types set:

- `API_BASE_URL = "https://revayato.com"`
- `WS_BASE_URL  = "wss://revayato.com"`

via `buildConfigField` in `app/build.gradle.kts`.

---

## Release signing (Play Store)

Signing is driven by an untracked `keystore.properties` at the module root:

```properties
storeFile=/absolute/path/to/revayato-release.jks
storePassword=…
keyAlias=…
keyPassword=…
```

> `keystore.properties` and the `.jks` keystore are **never committed**. If the file
> is absent, release builds fall back to unsigned.

Build a release bundle for Play:

```bash
./gradlew :app:bundleRelease
```

App identity: `applicationId = com.revayato.app`, display name **روایتو**,
`versionCode 1` / `versionName 1.0.0`. A 512×512 launcher icon lives in `store/`.

---

## Notes

- The app is **RTL-forced** and Persian-first throughout.
- JWT access/refresh tokens are stored in DataStore and attached by the network layer.
- No production credentials or keystores are part of this repository.
