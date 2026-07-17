<script setup lang="ts">
import type {
  AppErrorDetails,
  PlaybackSnapshot,
  WatchPartyPlaybackEvent,
  WatchPartyPlaybackState,
  WatchRoom,
} from "~/types";

definePageMeta({ layout: "player", middleware: "auth" });

interface PlayerHandle {
  applyRemotePlayback: (state: PlaybackSnapshot) => Promise<void>;
  getPlaybackSnapshot: () => PlaybackSnapshot;
}

const route = useRoute();
const code = computed(() => String(route.params.code));
const { api } = useApi();
const notifications = useNotifications();
const socket = useWatchPartySocket(code);
const player = useTemplateRef<PlayerHandle>("player");
const loading = ref(true);
const actionPending = ref(false);
const pageError = ref<AppErrorDetails | null>(null);
const playerReady = ref(false);
let hostSyncTimer: ReturnType<typeof setInterval> | undefined;

const room = computed(() => socket.room.value);
const isHost = computed(() => Boolean(room.value?.is_host));
const inviteUrl = computed(() =>
  import.meta.client
    ? `${window.location.origin}/watch-party/${encodeURIComponent(code.value)}`
    : `/watch-party/${encodeURIComponent(code.value)}`,
);
const returnPath = computed(() => {
  const content = room.value?.content;
  if (!content) return "/";
  return content.type === "movie"
    ? `/movies/${content.slug}`
    : `/series/${content.slug}`;
});

function reportError(error: unknown, fallback: string) {
  pageError.value = getAppError(error, fallback);
  notifications.error(pageError.value.title, pageError.value.message);
}

async function loadRoom() {
  loading.value = true;
  pageError.value = null;
  socket.disconnect(false);
  try {
    const found = await api<WatchRoom>(`/watch-party/rooms/${code.value}/`);
    socket.setInitialRoom(found);
    if (found.status !== "active") {
      pageError.value = {
        title: found.status === "expired" ? "زمان اتاق تمام شده" : "اتاق پایان یافته",
        message: found.status === "expired" ? "مدت استفاده از این اتاق به پایان رسیده است." : "میزبان این اتاق را بسته است.",
        hint: "یک اتاق تازه بساز یا از میزبان بخواه لینک تازه‌ای بفرستد.",
        fields: [],
      };
      return;
    }
    const joined = await api<WatchRoom>(
      `/watch-party/rooms/${code.value}/join/`,
      { method: "POST" },
    );
    socket.setInitialRoom(joined);
    socket.connect();
  } catch (error) {
    reportError(error, "ورود به اتاق ممکن نشد.");
  } finally {
    loading.value = false;
  }
}

function adjustedState(state: WatchPartyPlaybackState): PlaybackSnapshot {
  let position = state.position_seconds;
  if (state.is_playing) {
    const elapsed = Math.max(
      0,
      (socket.serverNowMs() - Date.parse(state.updated_at)) / 1000,
    );
    position += elapsed * state.playback_rate;
  }
  return {
    is_playing: state.is_playing,
    position_seconds:
      state.duration_seconds > 0
        ? Math.min(position, state.duration_seconds)
        : position,
    duration_seconds: state.duration_seconds,
    playback_rate: state.playback_rate,
  };
}

async function applyPartyState(state: WatchPartyPlaybackState) {
  if (!playerReady.value) return;
  await player.value?.applyRemotePlayback(adjustedState(state));
}

async function handleRemotePlayback(event: WatchPartyPlaybackEvent) {
  if (
    isHost.value &&
    !["playback.state", "playback.sync.response"].includes(event.type)
  )
    return;
  await applyPartyState(event.state);
}

function sendPlayback(
  type: "playback.play" | "playback.pause" | "playback.seek" | "playback.sync",
  state: PlaybackSnapshot,
) {
  if (!isHost.value) return;
  socket.sendEvent({ type, ...state });
}

async function handlePlayerReady() {
  playerReady.value = true;
  if (socket.playbackState.value)
    await applyPartyState(socket.playbackState.value);
  socket.requestSync();
}

function publishHostPlaybackState() {
  if (!isHost.value || !playerReady.value || socket.connectionStatus.value !== "connected") return;
  const state = player.value?.getPlaybackSnapshot();
  if (state) sendPlayback("playback.sync", state);
}

async function activateMemberPlayback() {
  if (socket.playbackState.value)
    await applyPartyState(socket.playbackState.value);
  socket.requestSync();
}

async function leaveRoom() {
  if (actionPending.value) return;
  actionPending.value = true;
  try {
    socket.disconnect();
    await api(`/watch-party/rooms/${code.value}/leave/`, { method: "POST" });
    await navigateTo(returnPath.value);
  } catch (error) {
    reportError(error, "خروج از اتاق انجام نشد.");
  } finally {
    actionPending.value = false;
  }
}

async function endRoom() {
  if (actionPending.value) return;
  actionPending.value = true;
  try {
    const ended = await api<WatchRoom>(
      `/watch-party/rooms/${code.value}/end/`,
      { method: "POST" },
    );
    socket.setInitialRoom(ended);
    socket.disconnect(false);
  } catch (error) {
    reportError(error, "پایان دادن به اتاق انجام نشد.");
  } finally {
    actionPending.value = false;
  }
}

watch(
  () => socket.lastPlaybackEvent.value?.sequence,
  () => {
    const event = socket.lastPlaybackEvent.value;
    if (event) void handleRemotePlayback(event);
  },
);

onMounted(() => {
  void loadRoom();
  hostSyncTimer = setInterval(publishHostPlaybackState, 4000);
});

onBeforeUnmount(() => {
  if (hostSyncTimer) clearInterval(hostSyncTimer);
  hostSyncTimer = undefined;
});

useSeoMeta({
  title: () =>
    room.value ? `تماشای گروهی ${room.value.content.title}` : "تماشای گروهی",
  description: "اتاق خصوصی تماشای هم‌ زمان فیلم و سریال",
});
</script>

<template>
  <div class="cinema-page min-h-dvh text-ink">
    <div class="page-shell py-3 sm:py-6 lg:py-8">
      <div v-if="loading" class="grid min-h-[70vh] place-items-center">
        <div class="text-center">
          <span
            class="mx-auto block size-11 animate-spin rounded-full border-2 border-line border-t-primary-500"
          />
          <p class="mt-4 text-sm font-bold text-secondary">
            در حال ورود به اتاق خصوصی…
          </p>
        </div>
      </div>

      <section
        v-else-if="pageError && !room"
        class="mx-auto grid min-h-[65vh] max-w-lg place-items-center text-center"
      >
        <div
          class="rounded-3xl border border-line bg-surface p-7 shadow-2xl shadow-black/25"
        >
          <span
            class="mx-auto grid size-14 place-items-center rounded-2xl bg-error/10 text-error ring-1 ring-error/20"
            ><CinematicIcon name="alert-triangle" class="size-7"
          /></span>
          <h1 class="mt-5 text-xl font-black">{{ pageError.title }}</h1>
          <p class="mt-2 text-sm leading-7 text-secondary">{{ pageError.message }}</p>
          <p v-if="pageError.hint" class="mt-2 text-xs leading-6 text-muted">{{ pageError.hint }}</p>
          <div class="mt-6 flex justify-center gap-2">
            <button
              type="button"
              class="min-h-11 rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400"
              @click="loadRoom"
            >
              تلاش دوباره</button
            ><NuxtLink
              to="/"
              class="inline-flex min-h-11 items-center rounded-xl border border-line bg-elevated px-5 text-sm font-black text-secondary hover:text-ink"
              >صفحه اصلی</NuxtLink
            >
          </div>
        </div>
      </section>

      <template v-else-if="room">
        <header
          class="mb-4 flex flex-wrap items-center justify-between gap-3 sm:mb-5"
        >
          <div class="flex min-w-0 items-center gap-3">
            <NuxtLink
              :to="returnPath"
              class="grid size-11 shrink-0 place-items-center rounded-xl border border-line bg-surface text-secondary transition hover:border-primary-500/35 hover:bg-primary-500/10 hover:text-primary-400"
              aria-label="بازگشت"
              ><CinematicIcon name="arrow-right" class="size-5"
            /></NuxtLink>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span
                  class="inline-flex items-center gap-1.5 text-[10px] font-black text-crimson-hover"
                  ><span
                    class="size-1.5 animate-pulse rounded-full bg-crimson"
                  />تماشای گروهی</span
                ><span
                  v-if="isHost"
                  class="rounded-md bg-primary-500/15 px-1.5 py-0.5 text-[9px] font-black text-primary-400"
                  >میزبان</span
                >
              </div>
              <h1 class="mt-1 truncate text-lg font-black sm:text-2xl">
                {{ room.content.title }}
              </h1>
            </div>
          </div>
          <p class="text-[11px] text-muted">کنترل پخش در اختیار میزبان است.</p>
        </header>

        <UiErrorAlert v-if="pageError" class="mb-4" :error="pageError" @close="pageError = null" />

        <section
          v-if="room.status !== 'active'"
          class="mx-auto grid min-h-[55vh] max-w-xl place-items-center text-center"
        >
          <div class="rounded-3xl border border-line bg-surface p-8">
            <span
              class="mx-auto grid size-14 place-items-center rounded-2xl bg-wine text-crimson-hover ring-1 ring-crimson/25"
              ><CinematicIcon name="clock" class="size-7"
            /></span>
            <h2 class="mt-5 text-xl font-black">
              این تماشای گروهی پایان یافته است
            </h2>
            <p class="mt-2 text-sm leading-7 text-secondary">
              برای شروع دوباره، از صفحه محتوا یک اتاق خصوصی تازه بسازید.
            </p>
            <NuxtLink
              :to="returnPath"
              class="mt-6 inline-flex min-h-11 items-center rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400"
              >بازگشت به محتوا</NuxtLink
            >
          </div>
        </section>

        <div
          v-else
          class="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_390px]"
        >
          <section class="min-w-0" aria-label="پخش هم‌ زمان">
            <VideoPlayer
              ref="player"
              :src="room.content.video_url"
              :poster="
                room.content.backdrop_url || room.content.poster_url || ''
              "
              :title="room.content.title"
              :controls="isHost"
              low-latency
              @ready="handlePlayerReady"
              @playback-play="sendPlayback('playback.play', $event)"
              @playback-pause="sendPlayback('playback.pause', $event)"
              @playback-seek="sendPlayback('playback.seek', $event)"
            />
            <div
              class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-[11px] text-muted"
            >
              <p v-if="isHost" class="inline-flex items-center gap-1.5">
                <CinematicIcon
                  name="play"
                  class="size-4 text-primary-400"
                />هر کاری با پخش انجام بدهی، برای بقیه هم انجام می‌شود.
              </p>
              <p v-else class="inline-flex items-center gap-1.5">
                <CinematicIcon
                  name="lock"
                  class="size-4 text-crimson-hover"
                />کنترل پخش فقط در اختیار {{ room.host.display_name }} است.
              </p>
              <button
                v-if="!isHost"
                type="button"
                class="min-h-10 rounded-lg bg-elevated px-3 py-1.5 font-black text-secondary ring-1 ring-line hover:bg-primary-500/10 hover:text-primary-400"
                @click="activateMemberPlayback"
              >
                هماهنگ شدن با میزبان
              </button>
            </div>
            <div
              class="mt-4 rounded-2xl border border-line bg-surface p-4 sm:p-5"
            >
              <h2 class="text-base font-black">{{ room.content.title }}</h2>
              <p
                class="mt-2 line-clamp-3 text-xs leading-6 text-secondary sm:text-sm sm:leading-7"
              >
                {{
                  room.content.description ||
                  "توضیحی برای این محتوا ثبت نشده است."
                }}
              </p>
            </div>
          </section>

          <WatchPartyPanel
            :room="room"
            :members="socket.members.value"
            :messages="socket.messages.value"
            :connection-status="socket.connectionStatus.value"
            :latency-ms="socket.latencyMs.value"
            :invite-url="inviteUrl"
            :error-message="socket.socketError.value?.message"
            @send="socket.sendChat"
            @retry="socket.connect"
            @leave="leaveRoom"
            @end="endRoom"
          />
        </div>
      </template>
    </div>
  </div>
</template>
