# روایتو — اپ اندروید (موبایل + Android TV)

React Native app (single codebase) on the **react-native-tvos** fork (0.76.9-0).
The same APK runs on phones and Android TV: UI touches/DPAD-focus are unified,
layout switches via `Platform.isTV`.

Scope (v1): **browse + playback**. No auth yet — the data layer models a future
`Authorization: Bearer` seam. The app talks only to the existing Django backend;
all media URLs (poster/backdrop/video_url/subtitle src) are already **absolute**
from the API — the app never prefixes a CDN base.

## Prerequisites

- Node.js 18+ and **pnpm** (root workspace uses pnpm 11.x).
- **JDK 17+** (e.g. Temurin 17) and **Android SDK** with `compileSdk 35`,
  `minSdk 24`, build-tools. Set `ANDROID_HOME` and add `platform-tools` to PATH.
  From the repo root:
  ```powershell
  $env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
  @($env:ANDROID_HOME, "$env:ANDROID_HOME\platform-tools") | % { if ($_ -notin $env:Path -split ';') { $env:Path = "$_;$env:Path" } }
  ```
- An Android emulator (AVD, API 24–35) or a device/TV reachable via `adb`.

## Install

```bash
cd ../..            # repo root
pnpm install        # installs backend, frontend, and android-app together
```

## Run

Three terminals (Metro must serve the JS bundle while the app runs):

**1 — Backend (Django):**
```powershell
docker compose up -d redis
cd backend
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

**2 — Web (optional, for API parity):**
```powershell
cd frontend
pnpm dev
```

**3 — App:**
```powershell
# Metro bundle server
pnpm app:start

# a new terminal, then install+launch on a running emulator / connected device
pnpm app:android
```

> **API base URL**: the dev default is `http://10.0.2.2:8000/api` (emulator's
> loopback to the host). On a physical device/TV set `API_BASE_URL` to your
> machine's LAN IP before building, e.g.
> `$env:API_BASE_URL = "http://192.168.1.20:8000/api"; pnpm app:android`.
> Cleartext HTTP is enabled for **debug builds only**.

## Scripts (all from repo root)

| command            | what it does                                        |
| ------------------ | --------------------------------------------------- |
| `pnpm app:start`   | Metro dev server for the app                        |
| `pnpm app:android` | build + install on the connected emulator/device    |
| `pnpm app:typecheck` | `tsc --noEmit` against the app                      |
| `pnpm app:lint`    | ESLint over `src` (0 errors expected)               |
| `pnpm app:test`    | Jest unit tests for the data layer (node env)       |
| `pnpm app:assets`  | re-link bundled fonts via `react-native-asset`      |

## How to point the app at a running backend

1. Backend up on host port 8000 (see above).
2. `$env:API_BASE_URL = "http://<HOST_IP>:8000/api"` — `<HOST_IP>` is
   `10.0.2.2` for the Android emulator, your LAN IP for a physical device/TV.
3. `pnpm app:android`.

Env values are read at bundle time — restart Metro after changing them.

## Project layout

```
src/
  config/        API base + cache/flags          (react-native-free, unit-testable)
  api/           fetch client, DTO types, endpoints, cache
  data/          catalogAdapter (API → AppMedia), translations (fa-IR)
  screens/       Home / Browse / Search / Detail / Genres / GenreBrowse / Countries
  components/    ui/ (AppText, Chip, PosterCard…) + list/ + detail/
  player/        VideoSurface (sole react-native-video user), PlayerShell,
                 Player/Episode players, resume, subtitle tracks
  navigation/    Phone (bottom tabs) vs TV (single stack) chosen via Platform.isTV
  hooks/         useApiGet (SWR), useTVLayout, …
  utils/         fa-IR format, media-URL normalize, resume keys
  theme/         dark palette + Vazirmatn
  assets/fonts/  Vazirmatn TTFs (bundled by react-native-asset)
```

## TV-specific details

- Manifest: `android:uses-feature android.hardware.touchscreen required=false`,
  `android.hardware.leanback`. The same APK ships both `LAUNCHER` and
  `LEANBACK_LAUNCHER` intents; a 320×180 TV banner is bundled.
- DPAD: playback overlay sleeps and wakes on any key; Play/Pause on center,
  ±10 s seek on left/right. Grid rails use `hasTVPreferredFocus` (first tile)
  and auto-scroll on focus.
- `Platform.isTV` is the official fork field — never sniff `Platform.OS`.

## Verification (no Android toolchain needed)

```bash
pnpm app:typecheck   # strict TS, 0 errors
pnpm app:lint        # 0 errors
pnpm app:test        # data-adapter units against real serializer payloads
```

Manual runbook once a device is available: home rails, search, series detail
(episode switching with no refetch), HLS playback + subtitles, resume after
app-kill, and cold-start offline state.