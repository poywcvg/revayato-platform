<script setup lang="ts">
/**
 * One release on جدول پخش: framed poster card with the title's year, name and
 * ratings under it; subtitle / dub / online-play marks stacked on the poster
 * and the episode (or episode range) pinned to its foot.
 */
const props = defineProps<{ entry: ScheduleEntry }>()

const name = computed(() => props.entry.series_original_title || props.entry.series_title)
const badge = computed(() => releaseBadge(props.entry))
const episode = computed(() => (props.entry.type === 'episode' ? episodeTag(props.entry) : ''))
</script>

<template>
  <NuxtLink :to="scheduleLink(entry)" class="sc-card" :title="entry.series_title">
    <div class="sc-card__poster">
      <img
        v-if="entry.poster_url"
        :src="entry.poster_url"
        :alt="entry.series_title"
        loading="lazy"
        decoding="async"
      >
      <span v-else class="sc-card__fallback" aria-hidden="true">
        <CinematicIcon :name="entry.type === 'movie' ? 'movie' : 'series'" class="size-6" />
      </span>

      <span v-if="badge" class="sc-card__badge">{{ badge }}</span>

      <span class="sc-card__marks">
        <span v-if="entry.has_subtitle" class="sc-card__mark" title="زیرنویس فارسی">
          <CinematicIcon name="captions" class="size-3.5" />
          <span class="sr-only">زیرنویس فارسی</span>
        </span>
        <span v-if="entry.is_dubbed" class="sc-card__mark" title="دوبله فارسی">
          <CinematicIcon name="audio" class="size-3.5" />
          <span class="sr-only">دوبله فارسی</span>
        </span>
        <span class="sc-card__mark" title="پخش آنلاین">
          <CinematicIcon name="play" class="size-3.5" />
          <span class="sr-only">پخش آنلاین</span>
        </span>
      </span>

      <span v-if="episode" class="sc-card__ep">{{ episode }}</span>
    </div>

    <div class="sc-card__info" dir="ltr">
      <span class="sc-card__year tabular-nums">{{ entry.year ? `(${entry.year})` : '\u00A0' }}</span>
      <h3 class="sc-card__title font-latin">{{ name }}</h3>
      <p class="sc-card__ratings tabular-nums">
        <span v-if="entry.imdb_rating" class="sc-card__rating">
          <span class="sc-card__imdb" aria-label="IMDb">IMDb</span>{{ entry.imdb_rating }}<small>/10</small>
        </span>
        <span v-if="entry.site_rating" class="sc-card__rating" title="امتیاز کاربران روایتو">
          <img src="/favicon.svg?v=2" alt="روایتو" class="sc-card__brand" width="14" height="14">{{ entry.site_rating }}<small>/10</small>
        </span>
      </p>
    </div>
  </NuxtLink>
</template>

<style scoped>
.sc-card {
  --sc-warm: var(--theme-accent-primary);
  --sc-warm-ink: var(--theme-on-accent);
  display: flex;
  height: 100%;
  min-width: 0;
  flex-direction: column;
  gap: 0.6rem;
  border-radius: 0.9rem;
  background: color-mix(in srgb, var(--theme-bg-elevated) 82%, transparent);
  padding: 0.55rem 0.55rem 0.7rem;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-border) 70%, transparent);
  transition: background-color 160ms ease, box-shadow 160ms ease;
}


.sc-card:focus-visible {
  outline: 2px solid var(--sc-warm);
  outline-offset: 2px;
}

.sc-card__poster {
  position: relative;
  aspect-ratio: 2 / 3;
  overflow: hidden;
  border-radius: 0.6rem;
  background: var(--theme-bg-surface);
}

.sc-card__poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 240ms ease;
}

.sc-card__fallback {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  color: var(--theme-text-muted);
}

/* Subtitle / dub / play marks, stacked like the rest of the catalog's posters. */
.sc-card__marks {
  position: absolute;
  inset-block-start: 0.4rem;
  inset-inline-end: 0.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.sc-card__mark {
  display: grid;
  width: 1.5rem;
  height: 1.5rem;
  place-items: center;
  border-radius: 999px;
  background: rgb(0 0 0 / 66%);
  color: #fff;
}

.sc-card__badge {
  position: absolute;
  inset-block-start: 0.4rem;
  inset-inline-start: 0.4rem;
  max-width: calc(100% - 2.6rem);
  overflow: hidden;
  border-radius: 0.4rem;
  background: var(--sc-warm);
  padding: 0.1rem 0.4rem;
  color: var(--sc-warm-ink);
  font-size: 0.6875rem;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-card__ep {
  position: absolute;
  inset-inline: 0.4rem;
  inset-block-end: 0.4rem;
  width: fit-content;
  max-width: calc(100% - 0.8rem);
  overflow: hidden;
  border-radius: 0.45rem;
  background: rgb(0 0 0 / 72%);
  padding: 0.15rem 0.45rem;
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-card__info {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
  padding-inline: 0.15rem;
  text-align: left;
}

.sc-card__year {
  height: 1.1rem;
  color: var(--theme-text-muted);
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1.1rem;
}

.sc-card__title {
  overflow: hidden;
  height: 1.2rem;
  color: var(--theme-text-primary);
  font-size: 0.8125rem;
  font-weight: 700;
  line-height: 1.2rem;
  text-overflow: ellipsis;
  white-space: nowrap;
  unicode-bidi: plaintext;
}

.sc-card__ratings {
  display: flex;
  height: 1.25rem;
  overflow: hidden;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.15rem;
  color: var(--theme-text-primary);
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}

.sc-card__rating {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.sc-card__rating small {
  margin-inline-start: -0.2rem;
  color: var(--theme-text-muted);
  font-size: 0.6875rem;
  font-weight: 700;
}

.sc-card__imdb {
  border-radius: 0.2rem;
  background: #f5c518;
  padding: 0 0.2rem;
  color: #000;
  font-family: system-ui, sans-serif;
  font-size: 0.5625rem;
  font-weight: 900;
  line-height: 1.5;
}

.sc-card__brand {
  width: 0.9rem;
  height: 0.9rem;
}

@media (hover: hover) and (pointer: fine) {
  .sc-card:hover {
    background: color-mix(in srgb, var(--theme-bg-elevated) 94%, var(--sc-warm) 6%);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sc-warm) 40%, transparent);
  }

  .sc-card:hover .sc-card__poster img { transform: scale(1.04); }
}

@media (prefers-reduced-motion: reduce) {
  .sc-card,
  .sc-card__poster img { transition: none; }

  .sc-card:hover .sc-card__poster img { transform: none; }
}
</style>
