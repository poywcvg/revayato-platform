<script setup lang="ts">
import type { AgeRating, CinematicIconName, ContentType } from "~/types";
import type { CatalogSort } from "~/composables/content/useContent";

const props = defineProps<{ type?: ContentType; discovery?: boolean }>();
const route = useRoute();
const router = useRouter();
const { catalog, genres, pending, error, loadFromApi, resetToMock } =
  useCatalog();
const { trackFilterApply, trackSearch, trackSortApply } = useAnalyticsEvent();
const updatingFromRoute = ref(false);
const validSorts: CatalogSort[] = ["newest", "rating", "popular", "trending"];
const normalizeSort = (value: unknown): CatalogSort =>
  validSorts.includes(String(value) as CatalogSort)
    ? (String(value) as CatalogSort)
    : "newest";
const filters = reactive<CatalogFilters>({
  query: String(route.query.q || ""),
  genre: String(route.query.genre || ""),
  year: String(route.query.year || "all"),
  ageRating: (route.query.age as AgeRating | "all") || "all",
  country: String(route.query.country || "all"),
  language: String(route.query.language || "all"),
  availability:
    route.query.availability === "dubbed" ||
    route.query.availability === "subtitle"
      ? route.query.availability
      : "all",
  format: ["animation", "short", "live_action"].includes(
    String(route.query.format),
  )
    ? (route.query.format as CatalogFilters["format"])
    : "all",
  minRating: String(route.query.min_rating || "all"),
  sort: normalizeSort(route.query.sort),
  type:
    route.query.type === "movie" || route.query.type === "series"
      ? route.query.type
      : props.type,
});
type DiscoveryContentKind = "all" | ContentType | "animation";
const typeOptions: Array<{
  label: string;
  value: DiscoveryContentKind;
  icon: CinematicIconName;
}> = [
  { label: "همه", value: "all", icon: "clapperboard" },
  { label: "فیلم", value: "movie", icon: "movie" },
  { label: "سریال", value: "series", icon: "series" },
  { label: "انیمیشن", value: "animation", icon: "animation" },
];
const contentKind = computed<DiscoveryContentKind>({
  get: () =>
    filters.format === "animation" ? "animation" : filters.type || "all",
  set: (value) => {
    updatingFromRoute.value = true;
    filters.type = value === "movie" || value === "series" ? value : undefined;
    if (value === "animation") filters.format = "animation";
    else if (filters.format === "animation") filters.format = "all";
    nextTick(() => {
      updatingFromRoute.value = false;
      syncRouteQuery();
      trackFilterApply("content_type", value, props.type);
    });
  },
});

const title = computed(() =>
  props.discovery
    ? "جستجوی پیشرفته"
    : props.type === "movie"
      ? "فیلم‌ها"
      : "سریال‌ها",
);
const eyebrow = computed(() =>
  props.discovery
    ? "فیلتر دقیق برای پیدا کردن انتخاب مناسب"
    : props.type === "movie"
      ? "فهرست فیلم‌ها"
      : "داستان‌های دنباله‌دار",
);
const description = computed(() =>
  props.discovery
    ? "نام فیلم یا سریال را بنویس و در صورت نیاز، نتیجه‌ها را بر اساس نوع، ژانر، سال، زبان یا امتیاز محدود کن."
    : props.type === "movie"
      ? "فیلم بعدی‌ات را با فیلتر ژانر، زبان، کشور و امتیاز پیدا کن."
      : "سریال‌های تازه و محبوب را مرور کن و برای تماشای بعدی به لیستت اضافه کن.",
);
const scopedCatalog = computed(() =>
  props.type
    ? catalog.value.filter((item) => item.type === props.type)
    : catalog.value,
);
const years = computed(() =>
  [...new Set(scopedCatalog.value.map((item) => item.year))].sort(
    (a, b) => b - a,
  ),
);
const countries = computed(() =>
  [
    ...new Set(
      scopedCatalog.value.flatMap((item) =>
        item.country.split(/[،,]/).map((value) => value.trim()),
      ),
    ),
  ]
    .filter(Boolean)
    .sort(),
);
const languages = computed(() =>
  [
    ...new Set(
      scopedCatalog.value.flatMap((item) =>
        item.language.split(/[،,]/).map((value) => value.trim()),
      ),
    ),
  ]
    .filter(Boolean)
    .sort(),
);
const yearOptions = computed(() => [
  { value: "all", label: "همه سال‌ها" },
  ...years.value.map((year) => ({ value: String(year), label: String(year) })),
]);
const countryOptions = computed(() => [
  { value: "all", label: "همه کشورها" },
  ...countries.value.map((country) => ({ value: country, label: country })),
]);
const languageFilterOptions = computed(() => [
  { value: "all", label: "همه زبان‌ها" },
  ...languages.value.map((language) => ({ value: language, label: language })),
]);
const ageRatingOptions = [
  { value: "all", label: "همه رده‌های سنی" },
  { value: "12+", label: "۱۲+" },
  { value: "15+", label: "۱۵+" },
  { value: "18+", label: "۱۸+" },
] as const;
const sortOptions = [
  { value: "newest", label: "جدیدترین", description: "تازه‌ترین فیلم‌ها و سریال‌ها" },
  { value: "popular", label: "محبوب‌ترین", description: "بر اساس استقبال کاربران" },
  { value: "rating", label: "بیشترین امتیاز", description: "بالاترین امتیاز منتقدان و کاربران" },
  { value: "trending", label: "ترند", description: "پرطرفدارهای همین حالا" },
] as const;
const availabilityOptions = [
  { value: "all", label: "همه نسخه‌ها" },
  { value: "dubbed", label: "دوبله فارسی" },
  { value: "subtitle", label: "زیرنویس فارسی" },
] as const;
const formatOptions = [
  { value: "all", label: "همه فرمت‌ها" },
  { value: "live_action", label: "لایو اکشن" },
  { value: "animation", label: "انیمیشن" },
  { value: "short", label: "کوتاه و سبک" },
] as const;
const ratingOptions = [
  { value: "all", label: "همه امتیازها" },
  { value: "7", label: "۷ به بالا" },
  { value: "8", label: "۸ به بالا" },
  { value: "8.5", label: "۸.۵ به بالا" },
] as const;
const { results: filteredItems, total: resultCount } = useSearch(filters);
const quickSearches = [
  "اکشن کره‌ای",
  "دوبله فارسی",
  "سریال جنایی",
  "انیمیشن خانوادگی",
  "علمی‌تخیلی",
  "فیلم کوتاه و سبک",
];
const sortLabels: Record<CatalogSort, string> = {
  newest: "جدیدترین",
  popular: "محبوب‌ترین",
  rating: "بیشترین امتیاز",
  trending: "ترند",
};
const activeSortLabel = computed(() => sortLabels[filters.sort]);
type RemovableFilterKey =
  | "query"
  | "genre"
  | "year"
  | "ageRating"
  | "country"
  | "language"
  | "availability"
  | "format"
  | "minRating"
  | "type";
const activeFilterChips = computed<
  Array<{ key: RemovableFilterKey; label: string }>
>(() => {
  const chips: Array<{ key: RemovableFilterKey; label: string }> = [];
  if (filters.query)
    chips.push({ key: "query", label: `جستجو: ${filters.query}` });
  if (filters.genre)
    chips.push({
      key: "genre",
      label:
        genres.find((genre) => genre.slug === filters.genre)?.title ||
        filters.genre,
    });
  if (filters.year !== "all")
    chips.push({ key: "year", label: `سال ${filters.year}` });
  if (filters.ageRating !== "all")
    chips.push({ key: "ageRating", label: `رده ${filters.ageRating}` });
  if (filters.country !== "all")
    chips.push({ key: "country", label: filters.country });
  if (filters.language !== "all")
    chips.push({ key: "language", label: filters.language });
  if (filters.availability !== "all")
    chips.push({
      key: "availability",
      label:
        filters.availability === "dubbed" ? "دوبله فارسی" : "زیرنویس فارسی",
    });
  if (filters.format !== "all")
    chips.push({
      key: "format",
      label:
        filters.format === "animation"
          ? "انیمیشن"
          : filters.format === "short"
            ? "کوتاه"
            : "لایو اکشن",
    });
  if (filters.minRating !== "all")
    chips.push({ key: "minRating", label: `امتیاز ${filters.minRating}+` });
  if (filters.type !== props.type)
    chips.push({
      key: "type",
      label:
        filters.type === "movie"
          ? "فیلم‌ها"
          : filters.type === "series"
            ? "سریال‌ها"
            : "همه محتوا",
    });
  return chips;
});
const activeFilters = computed(() => activeFilterChips.value.length);

async function resetFilters() {
  updatingFromRoute.value = true;
  Object.assign(filters, {
    query: "",
    genre: "",
    year: "all",
    ageRating: "all",
    country: "all",
    language: "all",
    availability: "all",
    format: "all",
    minRating: "all",
    sort: "newest",
    type: props.type,
  } satisfies CatalogFilters);
  await router.replace({ query: {} });
  updatingFromRoute.value = false;
  trackFilterApply("clear_all", "all", props.type);
}

function removeFilter(key: RemovableFilterKey) {
  if (key === "query" || key === "genre") filters[key] = "";
  else if (key === "ageRating") filters.ageRating = "all";
  else if (key === "type") filters.type = props.type;
  else filters[key] = "all";
}

function syncRouteQuery() {
  void router.replace({
    query: {
      ...(filters.query && { q: filters.query }),
      ...(filters.genre && { genre: filters.genre }),
      ...(filters.year !== "all" && { year: filters.year }),
      ...(filters.ageRating !== "all" && { age: filters.ageRating }),
      ...(filters.country !== "all" && { country: filters.country }),
      ...(filters.language !== "all" && { language: filters.language }),
      ...(filters.availability !== "all" && {
        availability: filters.availability,
      }),
      ...(filters.format !== "all" && { format: filters.format }),
      ...(filters.minRating !== "all" && { min_rating: filters.minRating }),
      ...(filters.sort !== "newest" && { sort: filters.sort }),
      ...(filters.type &&
        filters.type !== props.type && { type: filters.type }),
    },
  });
}

function applyRouteQuery() {
  updatingFromRoute.value = true;
  filters.query = String(route.query.q || "");
  filters.genre = String(route.query.genre || "");
  filters.year = String(route.query.year || "all");
  filters.ageRating = ["12+", "15+", "18+"].includes(String(route.query.age))
    ? (route.query.age as AgeRating)
    : "all";
  filters.country = String(route.query.country || "all");
  filters.language = String(route.query.language || "all");
  filters.availability =
    route.query.availability === "dubbed" ||
    route.query.availability === "subtitle"
      ? route.query.availability
      : "all";
  filters.format = ["animation", "short", "live_action"].includes(
    String(route.query.format),
  )
    ? (route.query.format as CatalogFilters["format"])
    : "all";
  filters.minRating = String(route.query.min_rating || "all");
  filters.sort = normalizeSort(route.query.sort);
  filters.type =
    route.query.type === "movie" || route.query.type === "series"
      ? route.query.type
      : props.type;
  nextTick(() => {
    updatingFromRoute.value = false;
  });
}

watch(
  () => filters.genre,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackFilterApply("genre", value || "all", props.type);
  },
);
watch(
  () => filters.year,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackFilterApply("year", value, props.type);
  },
);
watch(
  () => filters.ageRating,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackFilterApply("age_rating", value, props.type);
  },
);
for (const key of [
  "country",
  "language",
  "availability",
  "format",
  "minRating",
] as const) {
  watch(
    () => filters[key],
    (value) => {
      if (updatingFromRoute.value) return;
      syncRouteQuery();
      trackFilterApply(key, value, props.type);
    },
  );
}
watch(
  () => filters.type,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackFilterApply("content_type", value || "all", props.type);
  },
);
watch(
  () => filters.sort,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackSortApply(value, props.type);
  },
);
watchDebounced(
  () => filters.query,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery();
    trackSearch(value, filteredItems.value.length);
  },
  { debounce: 650 },
);
watch(() => route.query, applyRouteQuery, { deep: true });
</script>

<template>
  <div class="page-shell py-7 sm:py-10">
    <PageHero
      :title="title"
      :eyebrow="eyebrow"
      :description="description"
      :count="resultCount"
      :icon="discovery ? 'search' : type === 'series' ? 'series' : 'movie'"
    >
      <div
        v-if="discovery"
        class="hide-scrollbar flex gap-2 overflow-x-auto pb-1"
      >
        <button
          v-for="item in quickSearches"
          :key="item"
          type="button"
          class="ui-chip-dark min-h-11 shrink-0"
          @click="filters.query = item"
        >
          {{ item }}
        </button>
      </div>
    </PageHero>

    <section
      class="ui-surface mb-6 p-4 sm:p-5"
      aria-label="جستجو و فیلتر محتوا"
    >
      <div
        class="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(300px,1fr)_150px_150px_170px] xl:items-end"
      >
        <div class="md:col-span-2 xl:col-span-1">
          <p class="mb-1.5 text-[11px] font-black text-slate-500">
            جستجو در فهرست
          </p>
          <SearchBar
            v-model="filters.query"
            :large="discovery"
            :placeholder="
              discovery
                ? 'جستجوی فیلم، سریال، بازیگر، کارگردان...'
                : `جستجو در ${title}...`
            "
          />
        </div>
        <div class="hidden md:block">
          <span class="mb-1.5 block text-[11px] font-black text-slate-500">سال انتشار</span>
          <UiSelect v-model="filters.year" :options="yearOptions" label="سال انتشار" />
        </div>
        <div class="hidden md:block">
          <span class="mb-1.5 block text-[11px] font-black text-slate-500">رده سنی</span>
          <UiSelect v-model="filters.ageRating" :options="ageRatingOptions" label="رده سنی" />
        </div>
        <div>
          <span class="mb-1.5 block text-[11px] font-black text-slate-500">مرتب‌سازی</span>
          <UiSelect v-model="filters.sort" :options="sortOptions" label="مرتب‌سازی نتایج" icon="sliders" />
        </div>
      </div>
      <details class="group mt-4 rounded-2xl bg-elevated ring-1 ring-line">
        <summary
          class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-black text-secondary"
        >
          <span class="inline-flex items-center gap-2"
            ><CinematicIcon name="settings" class="size-4 text-brand" />انتخاب‌های
            بیشتر
            <span
              v-if="activeFilters"
              class="rounded-md bg-primary-500/14 px-1.5 py-0.5 text-[10px] text-primary-300"
              >{{ activeFilters }}</span
            ></span
          ><CinematicIcon
            name="chevron-down"
            class="size-4 transition-transform group-open:rotate-180"
          />
        </summary>
        <div
          class="grid gap-3 border-t border-line p-4 sm:grid-cols-2 xl:grid-cols-5"
        >
          <div class="md:hidden"><span class="mb-1.5 block text-[11px] font-bold text-muted">سال انتشار</span><UiSelect v-model="filters.year" :options="yearOptions" label="سال انتشار" compact /></div>
          <div class="md:hidden"><span class="mb-1.5 block text-[11px] font-bold text-muted">رده سنی</span><UiSelect v-model="filters.ageRating" :options="ageRatingOptions" label="رده سنی" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">کشور</span><UiSelect v-model="filters.country" :options="countryOptions" label="کشور سازنده" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">زبان</span><UiSelect v-model="filters.language" :options="languageFilterOptions" label="زبان محتوا" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">نسخه پخش</span><UiSelect v-model="filters.availability" :options="availabilityOptions" label="نسخه پخش" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">فرمت</span><UiSelect v-model="filters.format" :options="formatOptions" label="فرمت محتوا" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">حداقل امتیاز</span><UiSelect v-model="filters.minRating" :options="ratingOptions" label="حداقل امتیاز" compact /></div>
        </div>
      </details>
      <div class="mt-5 flex flex-col gap-4 border-t border-line pt-4">
        <div>
          <p class="mb-2 text-xs font-black text-secondary">نوع محتوا</p>
          <div class="hide-scrollbar flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="option in typeOptions"
              :key="option.value"
              type="button"
              class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold transition"
              :class="
                contentKind === option.value
                  ? 'cinema-glow bg-primary-500 text-night-950'
                  : 'bg-elevated text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40'
              "
              :aria-pressed="contentKind === option.value"
              @click="contentKind = option.value"
            >
              <CinematicIcon
                :name="option.icon"
                class="size-4.5"
                :stroke-width="contentKind === option.value ? 2.2 : 1.8"
              />{{ option.label }}
            </button>
          </div>
        </div>
        <div>
          <p class="mb-2 text-xs font-black text-secondary">ژانر</p>
          <GenreChips v-model="filters.genre" :genres="genres" compact />
        </div>
      </div>
      <div
        v-if="activeFilters"
        class="mt-2 rounded-xl bg-primary-500/10 p-2.5 ring-1 ring-primary-500/20"
      >
        <div class="flex items-center justify-between gap-3 px-1">
          <p class="text-xs font-bold text-primary-300">فیلترهای فعال</p>
          <button
            type="button"
            class="min-h-9 text-xs font-black text-primary-300 hover:text-primary-200"
            @click="resetFilters"
          >
            پاک کردن همه
          </button>
        </div>
        <div class="hide-scrollbar mt-1.5 flex gap-2 overflow-x-auto pb-1">
          <button
            v-for="chip in activeFilterChips"
            :key="chip.key"
            type="button"
            class="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl bg-elevated px-3 text-xs font-bold text-secondary ring-1 ring-primary-500/30"
            :aria-label="`حذف فیلتر ${chip.label}`"
            @click="removeFilter(chip.key)"
          >
            <span class="max-w-44 truncate">{{ chip.label }}</span
            ><CinematicIcon name="x" class="size-3.5 text-muted" />
          </button>
        </div>
      </div>
    </section>

    <CatalogSourceNotice
      class="mb-6"
      :error="error"
      :pending="pending"
      @retry="loadFromApi"
      @dismiss="resetToMock"
    />
    <div
      class="mb-4 flex min-h-12 flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-2.5 ring-1 ring-line"
      aria-live="polite"
    >
      <div class="flex min-w-0 items-center gap-2.5">
        <span
          class="grid size-8 shrink-0 place-items-center rounded-xl bg-primary-500/14 text-primary-300"
          ><CinematicIcon name="search" class="size-4.5"
        /></span>
        <p class="truncate text-sm font-black text-ink">
          {{ pending ? "در حال جستجو..." : `${resultCount} نتیجه`
          }}<span v-if="filters.query" class="font-semibold text-muted">
            برای «{{ filters.query }}»</span
          >
        </p>
      </div>
      <span class="shrink-0 text-[11px] font-bold text-slate-500"
        >مرتب‌شده بر اساس {{ activeSortLabel }}</span
      >
    </div>
    <MovieGrid
      :items="filteredItems"
      :loading="pending"
      :empty-description="
        filters.query
          ? 'پیشنهاد: عبارت کوتاه‌تر یا ژانر متفاوت را امتحان کن.'
          : 'فیلترها را تغییر بده تا انتخاب‌های بیشتری ببینی.'
      "
    />
    <div v-if="!pending && !filteredItems.length" class="mt-4 text-center">
      <p class="text-xs font-bold text-muted">جستجوهای پیشنهادی</p>
      <div class="mt-2 flex flex-wrap justify-center gap-2">
        <button
          v-for="item in quickSearches"
          :key="item"
          type="button"
          class="min-h-11 rounded-xl bg-elevated px-3 py-2 text-xs font-bold text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40"
          @click="filters.query = item"
        >
          {{ item }}
        </button>
      </div>
    </div>
  </div>
</template>
