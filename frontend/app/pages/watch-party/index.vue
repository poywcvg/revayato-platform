<script setup lang="ts">
import type { AppErrorDetails, Movie, WatchRoom } from "~/types";

definePageMeta({ middleware: "auth" });

const {
  catalog,
  source,
  pending,
  error: catalogError,
  loadFromApi,
} = useCatalog();
const { api } = useApi();
const notifications = useNotifications();
const creatingId = ref<number | null>(null);
const actionError = ref<AppErrorDetails | null>(null);
const availableItems = computed(() => catalog.value.slice(0, 12));
const catalogReady = computed(() => source.value === "api");

function selectionFor(item: Movie) {
  if (item.type === "movie")
    return { content_type: "movie" as const, content_id: item.id };
  const episode =
    item.episodes?.find((candidate) => candidate.hls_url) || item.episodes?.[0];
  return episode
    ? { content_type: "episode" as const, content_id: episode.id }
    : null;
}

function detailPath(item: Movie) {
  return `/${item.type === "movie" ? "movies" : "series"}/${item.slug}${item.type === "series" ? "#episodes" : ""}`;
}

async function createParty(item: Movie) {
  const selection = selectionFor(item);
  if (!selection || creatingId.value !== null || !catalogReady.value) return;
  creatingId.value = item.id;
  actionError.value = null;
  try {
    const room = await api<WatchRoom>("/watch-party/rooms/", {
      method: "POST",
      body: selection,
    });
    await navigateTo(`/watch-party/${room.invite_code}`);
  } catch (error) {
    actionError.value = getAppError(error, "ساخت اتاق ممکن نشد.");
    notifications.error(actionError.value.title, actionError.value.message);
  } finally {
    creatingId.value = null;
  }
}

onMounted(() => {
  if (source.value !== "api") void loadFromApi();
});

useSeoMeta({
  title: "تماشای گروهی",
  description: "ساخت اتاق خصوصی برای تماشای هم‌ زمان فیلم و سریال با دوستان",
});
</script>

<template>
  <div class="cinema-page min-h-dvh pb-16 text-ink">
    <section
      class="relative isolate overflow-hidden border-b border-line bg-gradient-to-bl from-wine via-canvas-soft to-canvas"
    >
      <div
        class="ambient-orb ambient-orb--crimson pointer-events-none absolute -left-24 -top-24 size-96 rounded-full"
        aria-hidden="true"
      />
      <div class="page-shell relative py-10 sm:py-14 lg:py-16">
        <span
          class="inline-flex items-center gap-2 rounded-full bg-crimson/15 px-3 py-1.5 text-xs font-black text-crimson-hover ring-1 ring-crimson/25"
          ><span class="size-2 animate-pulse rounded-full bg-crimson" />Watch
          Party</span
        >
        <h1 class="mt-4 max-w-3xl text-3xl font-black sm:text-5xl">
          یک داستان، چند صفحه، یک لحظه مشترک
        </h1>
        <p class="mt-4 max-w-2xl text-sm leading-8 text-secondary sm:text-base">
          یک عنوان انتخاب کن، اتاق بساز و لینک را برای دوستانت بفرست.
          میزبان پخش را کنترل می‌کند و همه هم‌زمان فیلم را می‌بینند و
          گفت‌وگو می‌کنند.
        </p>
        <div class="mt-7 grid max-w-3xl gap-3 sm:grid-cols-3">
          <div class="rounded-2xl border border-line bg-surface/80 p-4">
            <CinematicIcon name="lock" class="size-5 text-primary-400" />
            <p class="mt-3 text-sm font-black">اتاق خصوصی</p>
            <p class="mt-1 text-xs leading-6 text-muted">
              فقط کسانی که لینک دارند وارد می‌شوند
            </p>
          </div>
          <div class="rounded-2xl border border-line bg-surface/80 p-4">
            <CinematicIcon name="play" class="size-5 text-primary-400" />
            <p class="mt-3 text-sm font-black">پخش هم‌ زمان</p>
            <p class="mt-1 text-xs leading-6 text-muted">
              پخش برای همه با میزبان جلو می‌رود
            </p>
          </div>
          <div class="rounded-2xl border border-line bg-surface/80 p-4">
            <CinematicIcon name="comments" class="size-5 text-primary-400" />
            <p class="mt-3 text-sm font-black">گفت‌وگوی زنده</p>
            <p class="mt-1 text-xs leading-6 text-muted">
              اعضای اتاق با هم پیام می‌دهند
            </p>
          </div>
        </div>
      </div>
    </section>

    <section
      class="page-shell py-9 sm:py-12"
      aria-labelledby="party-catalog-title"
    >
      <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p class="text-xs font-black text-primary-400">انتخاب برای شروع</p>
          <h2 id="party-catalog-title" class="mt-1 text-2xl font-black">
            چه چیزی را با هم ببینیم؟
          </h2>
          <p class="mt-2 text-sm text-muted">
            یکی از عنوان‌های آماده پخش را انتخاب کن و اتاق خودت را بساز.
          </p>
        </div>
        <NuxtLink
          to="/movies"
          class="inline-flex min-h-11 items-center gap-1 rounded-xl px-3 text-sm font-black text-secondary hover:bg-primary-500/10 hover:text-primary-400"
          >دیدن همه عنوان‌ها<CinematicIcon name="arrow-left" class="size-4"
        /></NuxtLink>
      </div>

      <UiErrorAlert v-if="actionError" class="mb-5" :error="actionError" @close="actionError = null" />

      <div
        v-if="!catalogReady && (pending || !catalogError)"
        class="grid min-h-64 place-items-center rounded-3xl border border-line bg-surface"
      >
        <div class="text-center">
          <span
            class="mx-auto block size-10 animate-spin rounded-full border-2 border-line border-t-primary-500"
          />
          <p class="mt-3 text-sm font-bold text-secondary">
            در حال دریافت عناوین قابل پخش…
          </p>
        </div>
      </div>

      <div
        v-else-if="catalogError && !catalogReady"
        class="grid min-h-64 place-items-center rounded-3xl border border-error/20 bg-surface p-6 text-center"
      >
        <div>
          <CinematicIcon name="signal-off" class="mx-auto size-9 text-error" />
          <h3 class="mt-4 text-lg font-black">فهرست فیلم‌ها باز نشد</h3>
          <p class="mt-2 text-sm leading-7 text-secondary">
            برای ساخت اتاق باید به اینترنت و فهرست اصلی فیلم‌ها دسترسی داشته باشیم.
          </p>
          <button
            type="button"
            class="mt-5 min-h-11 rounded-xl bg-primary-500 px-5 text-sm font-black text-night-950 hover:bg-primary-400"
            @click="loadFromApi"
          >
            تلاش دوباره
          </button>
        </div>
      </div>

      <div
        v-else-if="availableItems.length"
        class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
      >
        <article
          v-for="item in availableItems"
          :key="`${item.type}-${item.id}`"
          class="cinematic-card group flex min-w-0 flex-col overflow-hidden rounded-2xl"
        >
          <NuxtLink :to="detailPath(item)" class="block"
            ><CinematicImage
              :src="item.poster_url"
              :alt="`پوستر ${item.title}`"
              ratio="poster"
              image-class="transition-transform duration-300 group-hover:scale-[1.025]"
          /></NuxtLink>
          <div class="flex flex-1 flex-col p-3">
            <p class="text-[10px] font-black text-primary-400">
              {{
                item.type === "movie"
                  ? "فیلم"
                  : `سریال · ${item.episodes?.length || 0} قسمت`
              }}
            </p>
            <h3 class="mt-1 truncate text-sm font-black">{{ item.title }}</h3>
            <p class="mt-1 text-[11px] text-muted">
              {{ item.year }} · {{ item.age_rating }}
            </p>
            <button
              v-if="selectionFor(item)"
              type="button"
              :disabled="creatingId !== null || !catalogReady"
              class="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-1.5 rounded-xl bg-primary-500 px-2 text-xs font-black text-night-950 transition hover:bg-primary-400 disabled:bg-disabled"
              @click="createParty(item)"
            >
              <span
                v-if="creatingId === item.id"
                class="size-3.5 animate-spin rounded-full border border-night-950/30 border-t-night-950"
              /><CinematicIcon v-else name="users" class="size-4" />{{
                creatingId === item.id ? "در حال ساخت…" : "ساخت اتاق"
              }}</button
            ><NuxtLink
              v-else
              :to="detailPath(item)"
              class="mt-3 inline-flex min-h-10 items-center justify-center rounded-xl border border-line bg-elevated px-2 text-xs font-black text-secondary hover:text-primary-400"
              >انتخاب قسمت</NuxtLink
            >
          </div>
        </article>
      </div>

      <EmptyState
        v-else
        title="عنوان قابل پخشی پیدا نشد"
        description="پس از انتشار فیلم یا قسمت، امکان ساخت اتاق از همین صفحه فعال می‌شود."
      />
    </section>
  </div>
</template>
