<script setup lang="ts">
import {
  ACTORS_PAGE_SIZE,
  clampPage,
  offsetFromPage,
  pageFromQuery,
  totalPagesFor,
} from '~/composables/usePagination'

const route = useRoute()
const router = useRouter()
const { list } = useActors()
const page = computed(() => pageFromQuery(route.query.page))

const { data, pending, error, refresh } = await useAsyncData(
  () => `actors-index-${page.value}`,
  async () => {
    const response = await list({
      limit: ACTORS_PAGE_SIZE,
      offset: offsetFromPage(page.value, ACTORS_PAGE_SIZE),
      withMeta: true,
    })
    return response
  },
  {
    watch: [page],
    server: true,
    default: () => ({ items: [], count: 0 }),
  },
)

const actors = computed(() => data.value?.items || [])
const total = computed(() => data.value?.count || actors.value.length)
const totalPages = computed(() => totalPagesFor(total.value, ACTORS_PAGE_SIZE))
const safePage = computed(() => clampPage(page.value, totalPages.value))

async function goToPage(nextPage: number) {
  const target = clampPage(nextPage, totalPages.value)
  const query = { ...route.query } as Record<string, string | string[] | undefined>
  if (target <= 1) delete query.page
  else query.page = String(target)
  await router.replace({ query })
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch(totalPages, (pages) => {
  if (page.value > pages) void goToPage(pages)
})

useSeoMeta({
  title: 'بازیگران',
  description: 'فهرست بازیگران فیلم‌ها و سریال‌های روایتو؛ از صفحه هر بازیگر به فیلم‌شناسی‌اش برو.',
})
</script>

<template>
  <div class="cinema-page page-section">
    <PageHero
      title="بازیگران"
      eyebrow="جلوی دوربین"
      description="بازیگرانی که در کاتالوگ روایتو حضور دارند. با انتخاب هر نفر، فیلم‌ها و سریال‌های مرتبط را ببین."
      icon="user"
      :count="total"
      count-label="بازیگر"
    />

    <CatalogSourceNotice :error="error ? String(error.message || error) : null" :pending="pending" @retry="() => refresh()" />

    <div v-if="actors.length" class="people-grid mt-6">
      <ActorCard
        v-for="(actor, index) in actors"
        :key="actor.id"
        :actor="actor"
        :priority="index < 6"
      />
    </div>
    <EmptyState
      v-else-if="!pending"
      title="هنوز بازیگری ثبت نشده است"
      description="با کامل شدن اطلاعات فیلم‌ها و سریال‌ها، بازیگران اینجا نمایش داده می‌شوند."
      icon="user"
      action-label="مرور فیلم‌ها"
      action-href="/movies"
    />

    <CatalogPagination
      :page="safePage"
      :total-pages="totalPages"
      :total="total"
      :pending="pending"
      label="صفحه‌بندی بازیگران"
      @change="goToPage"
    />
  </div>
</template>
