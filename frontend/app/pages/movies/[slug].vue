<script setup lang="ts">
const route = useRoute()
const slug = computed(() => decodeRouteSlug(route.params.slug))
const { movie, refresh, pending } = useMovieBySlug(slug, 'movie')

// Page addresses are English; an old (Persian) address still resolves in the API
// and is answered here with a permanent redirect to the current one.
let redirecting = false
function redirectToCanonical(loaded: { slug: string } | null | undefined) {
  if (!loaded?.slug || loaded.slug === slug.value) return
  redirecting = true
  return navigateTo(
    { path: `/movies/${loaded.slug}`, query: route.query, hash: route.hash },
    { redirectCode: 301, replace: true },
  )
}

// Load full detail (download_links / cast are omitted from the list cache).
// Block the render ONLY when there is nothing to show yet: on the server (so the
// SSR HTML + SEO are complete and a hard refresh paints instantly) and on a client
// deep-link with no cached rail card. When a list card is already cached — the
// common case, the user tapped a rail — render it immediately and upgrade to the
// full detail in the background, so client navigation never sits frozen behind the
// (slow) detail API under the out-in page transition.
if (import.meta.server || !movie.value) {
  await redirectToCanonical(await refresh())
}
else {
  void refresh().then((loaded) => { void redirectToCanonical(loaded) })
}

if (!redirecting && (!movie.value || movie.value.type !== 'movie')) {
  throw createError({ statusCode: 404, message: 'فیلم پیدا نشد' })
}

// Title / description / schema.org graph are built in ~/utils/seo so movie and
// series pages stay identical in structure (and change together).
useDetailSeo(movie)
</script>

<template>
  <!-- Single root required for Nuxt pageTransition (out-in); multi-root blanks the page. -->
  <div>
    <CatalogDetail v-if="movie" :item="movie" />
    <div v-else-if="pending" class="media-detail content-section grid min-h-[55svh] place-items-center py-10" aria-busy="true">
      <LoadingSpinnerA size="large">در حال آماده‌سازی صفحه فیلم…</LoadingSpinnerA>
    </div>
  </div>
</template>
