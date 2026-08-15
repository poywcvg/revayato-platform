<script setup lang="ts">
import type { AgeRating, CinematicIconName, ContentType, Movie } from "~/types";
import type { CatalogFilters, CatalogSort } from "~/composables/content/useContent";
import {
  adaptApiCatalogItem,
  type ApiCatalogItem,
  type ApiListResponse,
  unwrapApiList,
} from "~/data/catalogAdapter";
import {
  CATALOG_PAGE_SIZE,
  clampPage,
  offsetFromPage,
  pageFromQuery,
  totalPagesFor,
} from "~/composables/usePagination";
import { featuredScore, newestTimestamp, popularScore, trendingScore } from "~/utils/trendingScore";
import { countryCodeForName, localizeCountry } from "~/data/countries";

interface ApiCatalogSearchResponse {
  query?: string;
  match_type?: "direct" | "similar" | "none";
  movies?: ApiCatalogItem[];
  series?: ApiCatalogItem[];
}

const props = defineProps<{ type?: ContentType; discovery?: boolean }>();
const route = useRoute();
const router = useRouter();
const config = useRuntimeConfig();
const { api } = useApi();
const {
  catalog,
  genres,
  pending: catalogPending,
  error: catalogError,
  loadFromApi,
} =
  useCatalog();
const { trackFilterApply, trackSearch, trackSortApply } = useAnalyticsEvent();
const updatingFromRoute = ref(false);
const remoteItems = shallowRef<Movie[]>([]);
const remoteTotal = ref(0);
const remotePending = ref(false);
const remoteLoaded = ref(false);
const remoteError = ref<string | null>(null);
const showingRelatedResults = ref(false);
let catalogRequestId = 0;
let catalogAbortController: AbortController | null = null;
const pending = computed(
  () => remotePending.value || (!remoteLoaded.value && catalogPending.value),
);
const error = computed(() => remoteError.value || catalogError.value);
const validSorts: CatalogSort[] = ["newest", "rating", "popular", "trending", "featured", "imdb_top"];
const normalizeSort = (value: unknown): CatalogSort =>
  validSorts.includes(String(value) as CatalogSort)
    ? (String(value) as CatalogSort)
    : "newest";
const currentPage = computed(() => pageFromQuery(route.query.page));
const filters = reactive<CatalogFilters>({
  query: String(route.query.q || ""),
  genre: String(route.query.genre || ""),
  year: String(route.query.year || "all"),
  ageRating: (route.query.age as AgeRating | "all") || "all",
  country: String(route.query.country || "all"),
  language: String(route.query.language || "all"),
  availability:
    route.query.availability === "dubbed" ||
    route.query.availability === "subtitle" ||
    route.query.availability === "download"
      ? route.query.availability
      : "all",
  format: ["animation", "short", "live_action"].includes(
    String(route.query.format),
  )
    ? (route.query.format as CatalogFilters["format"])
    : "all",
  minRating: String(route.query.min_rating || "all"),
  sort: normalizeSort(route.query.sort),
  type: props.type || (
    route.query.type === "movie" || route.query.type === "series"
      ? route.query.type
      : undefined
  ),
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
      syncRouteQuery({ resetPage: true });
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
    .sort((a, b) => a.localeCompare(b, "fa")),
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
  ...[
    ...new Set([
      ...years.value.map(String),
      ...(filters.year !== "all" ? [filters.year] : []),
    ]),
  ]
    .sort((left, right) => Number(right) - Number(left))
    .map((year) => ({ value: year, label: year })),
]);
const countryOptions = computed(() => {
  const values = new Map<string, string>()
  for (const country of countries.value) {
    const code = countryCodeForName(country) || country
    values.set(code, localizeCountry(country, code))
  }
  if (filters.country !== "all") {
    const code = countryCodeForName(filters.country) || filters.country
    values.set(code, localizeCountry(filters.country, code))
  }
  return [
    { value: "all", label: "همه کشورها" },
    ...[...values.entries()]
      .sort((left, right) => left[1].localeCompare(right[1], "fa"))
      .map(([value, label]) => ({ value, label })),
  ]
});
const languageFilterOptions = computed(() => [
  { value: "all", label: "همه زبان‌ها" },
  ...[
    ...new Set([
      ...languages.value,
      ...(filters.language !== "all" ? [filters.language] : []),
    ]),
  ]
    .sort((left, right) => left.localeCompare(right, "fa"))
    .map((language) => ({ value: language, label: language })),
]);
const ageRatingOptions = [
  { value: "all", label: "همه رده‌های سنی" },
  { value: "12+", label: "۱۲+" },
  { value: "15+", label: "۱۵+" },
  { value: "18+", label: "۱۸+" },
] as const;
const sortOptions = [
  { value: "newest", label: "جدیدترین", description: "تازه‌ترین عناوین اضافه‌شده" },
  { value: "imdb_top", label: "IMDb Top 250", description: "رتبه‌بندی رسمی Top 250 IMDb" },
  { value: "featured", label: "منتخب‌ها", description: "بر اساس کیفیت و انتخاب تحریریه" },
  { value: "popular", label: "محبوب‌ترین", description: "بر اساس بازدید و پسند کاربران" },
  { value: "rating", label: "بیشترین امتیاز", description: "بالاترین امتیاز منتقدان و کاربران" },
  { value: "trending", label: "ترند", description: "پرطرفدار و تازه در حال رشد" },
] as const;
const availabilityOptions = [
  { value: "all", label: "همه نسخه‌ها" },
  { value: "dubbed", label: "دوبله فارسی" },
  { value: "subtitle", label: "زیرنویس فارسی" },
  { value: "download", label: "قابل دانلود" },
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
const { results: localFilteredItems, total: localResultCount } =
  useSearch(filters);
const filteredItems = computed(() =>
  remoteLoaded.value && (remoteItems.value.length || !filters.query.trim())
    ? remoteItems.value
    : localFilteredItems.value.slice(
        offsetFromPage(currentPage.value, CATALOG_PAGE_SIZE),
        offsetFromPage(currentPage.value, CATALOG_PAGE_SIZE) + CATALOG_PAGE_SIZE,
      ),
);
const resultCount = computed(() =>
  remoteLoaded.value && (remoteItems.value.length || !filters.query.trim())
    ? remoteTotal.value
    : localResultCount.value,
);
const totalPages = computed(() =>
  totalPagesFor(resultCount.value, CATALOG_PAGE_SIZE),
);
const safePage = computed(() => clampPage(currentPage.value, totalPages.value));
type QuickFilter = { label: string; filters: Partial<CatalogFilters> };
const quickSearches = computed<QuickFilter[]>(() => {
  if (props.type === "movie") {
    return [
      { label: "فیلم‌های اکشن", filters: { genre: "action" } },
      { label: "دوبله فارسی", filters: { availability: "dubbed" } },
      { label: "زیرنویس فارسی", filters: { availability: "subtitle" } },
      { label: "انیمیشن", filters: { format: "animation" } },
      { label: "امتیاز ۸ به بالا", filters: { minRating: "8" } },
      { label: "قابل دانلود", filters: { availability: "download" } },
    ];
  }
  if (props.type === "series") {
    return [
      { label: "سریال‌های جنایی", filters: { genre: "crime" } },
      { label: "دوبله فارسی", filters: { availability: "dubbed" } },
      { label: "زیرنویس فارسی", filters: { availability: "subtitle" } },
      { label: "انیمیشن", filters: { format: "animation" } },
      { label: "امتیاز ۸ به بالا", filters: { minRating: "8" } },
      { label: "قابل دانلود", filters: { availability: "download" } },
    ];
  }
  return [
    { label: "فیلم‌های اکشن", filters: { type: "movie", genre: "action" } },
    { label: "سریال‌های جنایی", filters: { type: "series", genre: "crime" } },
    { label: "دوبله فارسی", filters: { availability: "dubbed" } },
    { label: "انیمیشن خانوادگی", filters: { format: "animation", genre: "family" } },
    { label: "علمی‌تخیلی", filters: { genre: "sci-fi" } },
    { label: "امتیاز ۸ به بالا", filters: { minRating: "8" } },
  ];
});
const resultLabel = computed(() => {
  const count = resultCount.value.toLocaleString("fa-IR");
  if (props.type === "movie") return `${count} فیلم`;
  if (props.type === "series") return `${count} سریال`;
  return `${count} نتیجه`;
});
const sortLabels: Record<CatalogSort, string> = {
  newest: "جدیدترین",
  imdb_top: "IMDb Top 250",
  featured: "منتخب‌ها",
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
        genres.value.find((genre) => genre.slug === filters.genre)?.title ||
        filters.genre,
    });
  if (filters.year !== "all")
    chips.push({ key: "year", label: `سال ${filters.year}` });
  if (filters.ageRating !== "all")
    chips.push({ key: "ageRating", label: `رده ${filters.ageRating}` });
  if (filters.country !== "all")
    chips.push({
      key: "country",
      label: localizeCountry(filters.country, countryCodeForName(filters.country)),
    });
  if (filters.language !== "all")
    chips.push({ key: "language", label: filters.language });
  if (filters.availability !== "all")
    chips.push({
      key: "availability",
      label:
        filters.availability === "dubbed"
          ? "دوبله فارسی"
          : filters.availability === "subtitle"
            ? "زیرنویس فارسی"
            : "قابل دانلود",
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

function applyQuickFilter(preset: QuickFilter) {
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
    ...preset.filters,
  } satisfies CatalogFilters);
  nextTick(() => {
    updatingFromRoute.value = false;
    syncRouteQuery({ resetPage: true });
    trackFilterApply("quick_filter", preset.label, props.type);
  });
}

function removeFilter(key: RemovableFilterKey) {
  if (key === "query" || key === "genre") filters[key] = "";
  else if (key === "ageRating") filters.ageRating = "all";
  else if (key === "type") filters.type = props.type;
  else filters[key] = "all";
}

function routeQueryFromFilters(options: { resetPage?: boolean } = {}) {
  const page = options.resetPage ? 1 : currentPage.value;
  return {
    ...(filters.query && { q: filters.query }),
    ...(filters.genre && { genre: filters.genre }),
    ...(filters.year !== "all" && { year: filters.year }),
    ...(filters.ageRating !== "all" && { age: filters.ageRating }),
    ...(filters.country !== "all" && {
      country: countryCodeForName(filters.country) || filters.country,
    }),
    ...(filters.language !== "all" && { language: filters.language }),
    ...(filters.availability !== "all" && {
      availability: filters.availability,
    }),
    ...(filters.format !== "all" && { format: filters.format }),
    ...(filters.minRating !== "all" && { min_rating: filters.minRating }),
    ...(filters.sort !== "newest" && { sort: filters.sort }),
    ...(filters.type &&
      filters.type !== props.type && { type: filters.type }),
    ...(page > 1 && { page: String(page) }),
  };
}

function comparableRouteQuery(query: typeof route.query | Record<string, string>) {
  return JSON.stringify(
    Object.entries(query)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([key, value]) => [key, String(Array.isArray(value) ? value[0] : value)])
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

let routeSyncVersion = 0;
async function syncRouteQuery(options: { resetPage?: boolean } = {}) {
  const version = ++routeSyncVersion;
  await nextTick();
  if (version !== routeSyncVersion || updatingFromRoute.value) return;
  const query = routeQueryFromFilters(options);
  if (comparableRouteQuery(route.query) === comparableRouteQuery(query)) return;
  await router.replace({ query });
}

async function goToPage(nextPage: number) {
  const target = clampPage(nextPage, totalPages.value);
  const query = routeQueryFromFilters();
  if (target <= 1) delete (query as { page?: string }).page;
  else (query as { page?: string }).page = String(target);
  await router.replace({ query });
  if (import.meta.client) window.scrollTo({ top: 0, behavior: "smooth" });
}

function applyRouteQuery() {
  updatingFromRoute.value = true;
  filters.query = String(route.query.q || "");
  filters.genre = String(route.query.genre || "");
  filters.year = String(route.query.year || "all");
  filters.ageRating = ["12+", "15+", "18+"].includes(String(route.query.age))
    ? (route.query.age as AgeRating)
    : "all";
  filters.country = (() => {
    const raw = String(route.query.country || "all");
    if (raw === "all" || !raw) return "all";
    return countryCodeForName(raw) || raw;
  })();
  filters.language = String(route.query.language || "all");
  filters.availability =
    route.query.availability === "dubbed" ||
    route.query.availability === "subtitle" ||
    route.query.availability === "download"
      ? route.query.availability
      : "all";
  filters.format = ["animation", "short", "live_action"].includes(
    String(route.query.format),
  )
    ? (route.query.format as CatalogFilters["format"])
    : "all";
  filters.minRating = String(route.query.min_rating || "all");
  filters.sort = normalizeSort(route.query.sort);
  filters.type = props.type || (
    route.query.type === "movie" || route.query.type === "series"
      ? route.query.type
      : undefined
  );
  nextTick(() => {
    updatingFromRoute.value = false;
  });
}

watch(
  () => filters.genre,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
    trackFilterApply("genre", value || "all", props.type);
  },
);
watch(
  () => filters.year,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
    trackFilterApply("year", value, props.type);
  },
);
watch(
  () => filters.ageRating,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
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
      syncRouteQuery({ resetPage: true });
      trackFilterApply(key, value, props.type);
    },
  );
}
watch(
  () => filters.type,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
    trackFilterApply("content_type", value || "all", props.type);
  },
);
watch(
  () => filters.sort,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
    trackSortApply(value, props.type);
  },
);
watchDebounced(
  () => filters.query,
  (value) => {
    if (updatingFromRoute.value) return;
    syncRouteQuery({ resetPage: true });
    trackSearch(value, filteredItems.value.length);
  },
  { debounce: 650 },
);
watch(() => route.query, applyRouteQuery, { deep: true });

const remoteRequestKey = computed(() =>
  JSON.stringify({
    query: filters.query.trim(),
    genre: filters.genre,
    year: filters.year,
    ageRating: filters.ageRating,
    country: filters.country,
    language: filters.language,
    availability: filters.availability,
    format: filters.format,
    minRating: filters.minRating,
    sort: filters.sort,
    type: filters.type || "all",
    page: currentPage.value,
  }),
);

function apiFilters(options: { limit?: number; offset?: number } = {}) {
  return {
    limit: options.limit ?? CATALOG_PAGE_SIZE,
    offset: options.offset ?? offsetFromPage(currentPage.value, CATALOG_PAGE_SIZE),
    ...(filters.query.trim() && { q: filters.query.trim() }),
    ...(filters.genre && { genre: filters.genre }),
    ...(filters.year !== "all" && { year: filters.year }),
    ...(filters.ageRating !== "all" && { age_rating: filters.ageRating }),
    ...(filters.country !== "all" && {
      country: countryCodeForName(filters.country) || filters.country,
    }),
    ...(filters.language !== "all" && { language: filters.language }),
    ...(filters.availability !== "all" && {
      availability: filters.availability,
    }),
    ...(filters.format !== "all" && { content_format: filters.format }),
    ...(filters.minRating !== "all" && { min_rating: filters.minRating }),
    sort: filters.sort,
    ...(filters.sort === "imdb_top" && { top250: "1" }),
  };
}

function canShowRelatedFallback() {
  return Boolean(filters.query.trim())
    && !filters.genre
    && filters.year === "all"
    && filters.ageRating === "all"
    && filters.country === "all"
    && filters.language === "all"
    && filters.availability === "all"
    && filters.format === "all"
    && filters.minRating === "all"
    && currentPage.value <= 1;
}

function mergeSortKey(item: Movie) {
  if (filters.sort === "imdb_top") {
    const rank = Number(item.imdb_rank)
    return Number.isFinite(rank) && rank > 0 ? -rank : Number.NEGATIVE_INFINITY
  }
  if (filters.sort === "rating") {
    return Number(
      item.ratings?.find((entry) => entry.source === "imdb")?.value
      ?? item.imdb_rating
      ?? item.rating
      ?? 0,
    );
  }
  if (filters.sort === "trending") return trendingScore(item);
  if (filters.sort === "featured") return featuredScore(item);
  if (filters.sort === "popular") return popularScore(item);
  return newestTimestamp(item);
}

function mergeCatalogPages(pages: Array<{ type: ContentType; page: ApiListResponse<ApiCatalogItem> | ApiCatalogItem[] }>) {
  const mediaBase = String(config.public.mediaCdnBaseUrl);
  const offset = offsetFromPage(currentPage.value, CATALOG_PAGE_SIZE);
  const adapted = pages.flatMap(({ type, page }) =>
    unwrapApiList(page).map((item) => adaptApiCatalogItem(item, type, mediaBase)),
  );
  const total = pages.reduce(
    (sum, { page }) =>
      sum +
      (Array.isArray(page) ? page.length : page.count ?? page.results?.length ?? 0),
    0,
  );

  if (pages.length === 1) {
    return { items: adapted, total };
  }

  const merged = [...adapted].sort(
    (left, right) =>
      mergeSortKey(right) - mergeSortKey(left) || right.year - left.year,
  );
  return {
    items: merged.slice(offset, offset + CATALOG_PAGE_SIZE),
    total,
  };
}

async function loadRemoteResults() {
  const requestId = ++catalogRequestId;
  catalogAbortController?.abort();
  const controller = new AbortController();
  catalogAbortController = controller;
  remotePending.value = true;
  remoteError.value = null;
  showingRelatedResults.value = false;
  const compactQuery = filters.query.trim().replace(/\s/g, "");
  if (compactQuery.length === 1) {
    remoteItems.value = [];
    remoteTotal.value = 0;
    remoteLoaded.value = true;
    remotePending.value = false;
    catalogAbortController = null;
    return;
  }
  const requestedType = props.type || filters.type;
  const types: ContentType[] = requestedType
    ? [requestedType]
    : ["movie", "series"];
  const offset = offsetFromPage(currentPage.value, CATALOG_PAGE_SIZE);
  // Mixed discovery needs enough candidates from each stream to build one page.
  const fetchLimit = types.length === 1
    ? CATALOG_PAGE_SIZE
    : Math.min(offset + CATALOG_PAGE_SIZE, 120);
  const fetchOffset = types.length === 1 ? offset : 0;

  try {
    const pages = await Promise.all(
      types.map(async (type) => {
        const page = await api<ApiListResponse<ApiCatalogItem> | ApiCatalogItem[]>(
          `/${type === "movie" ? "movies" : "series"}/`,
          {
            query: apiFilters({ limit: fetchLimit, offset: fetchOffset }),
            signal: controller.signal,
            timeout: 8_000,
          },
        );
        return { type, page };
      }),
    );
    if (requestId !== catalogRequestId) return;
    const mediaBase = String(config.public.mediaCdnBaseUrl);
    let { items: nextItems, total: nextTotal } = mergeCatalogPages(pages);

    if (!nextItems.length && canShowRelatedFallback()) {
      const suggestions = await api<ApiCatalogSearchResponse>("/search/", {
        query: {
          q: filters.query.trim(),
          type: requestedType || "all",
          limit: CATALOG_PAGE_SIZE,
        },
        signal: controller.signal,
        timeout: 5_000,
      });
      if (requestId !== catalogRequestId) return;
      nextItems = [
        ...(suggestions.movies || []).map((item) =>
          adaptApiCatalogItem(item, "movie", mediaBase),
        ),
        ...(suggestions.series || []).map((item) =>
          adaptApiCatalogItem(item, "series", mediaBase),
        ),
      ];
      nextTotal = nextItems.length;
      showingRelatedResults.value = suggestions.match_type === "similar";
    }

    remoteItems.value = nextItems;
    remoteTotal.value = nextTotal;
    remoteLoaded.value = true;
  } catch (cause) {
    if (requestId !== catalogRequestId) return;
    remoteLoaded.value = false;
    showingRelatedResults.value = false;
    remoteError.value =
      cause instanceof Error
        ? cause.message
        : "دریافت نتایج فیلترشده ممکن نشد.";
  } finally {
    if (requestId === catalogRequestId) {
      remotePending.value = false;
      catalogAbortController = null;
    }
  }
}

onBeforeUnmount(() => {
  catalogAbortController?.abort();
});

function retryCatalog() {
  void loadFromApi(true);
  void loadRemoteResults();
}

watchDebounced(
  remoteRequestKey,
  () => {
    if (import.meta.client) void loadRemoteResults();
  },
  { debounce: 260, maxWait: 700 },
);

watch(totalPages, (pages) => {
  if (currentPage.value > pages) void goToPage(pages);
});

// SSR the active page so /movies and /series are not an empty shell until hydration.
await loadRemoteResults();

onMounted(() => {
  // Browse pages use the remote paginated API; avoid the heavy full-catalog fan-out.
  // Discovery still benefits from a lean home catalog for local fallback search.
  if (props.discovery) void loadFromApi(false, "home");
});
</script>

<template>
  <div class="page-section">
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
          :key="item.label"
          type="button"
          class="ui-chip-dark min-h-11 shrink-0"
          @click="applyQuickFilter(item)"
        >
          {{ item.label }}
        </button>
      </div>
    </PageHero>

    <section
      class="ui-surface mb-6 p-4 sm:p-5"
      aria-label="جستجو و فیلتر محتوا"
    >
      <div
        class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_190px] sm:items-end"
      >
        <div>
          <p class="mb-1.5 text-[11px] font-black text-muted">
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
        <div>
          <span class="mb-1.5 block text-[11px] font-black text-muted">مرتب‌سازی</span>
          <UiSelect v-model="filters.sort" :options="sortOptions" label="مرتب‌سازی نتایج" icon="sliders" />
        </div>
      </div>
      <details class="group mt-3 rounded-2xl bg-elevated ring-1 ring-line">
        <summary
          class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-black text-secondary"
        >
          <span class="inline-flex items-center gap-2"
            ><CinematicIcon name="sliders" class="size-4 text-brand" />فیلترها
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
          class="grid gap-3 border-t border-line p-3 sm:grid-cols-2 sm:p-4 xl:grid-cols-4"
        >
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">کشور سازنده</span><UiSelect v-model="filters.country" :options="countryOptions" label="کشور سازنده" icon="globe" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">سال انتشار</span><UiSelect v-model="filters.year" :options="yearOptions" label="سال انتشار" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">رده سنی</span><UiSelect v-model="filters.ageRating" :options="ageRatingOptions" label="رده سنی" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">زبان</span><UiSelect v-model="filters.language" :options="languageFilterOptions" label="زبان محتوا" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">نسخه پخش</span><UiSelect v-model="filters.availability" :options="availabilityOptions" label="نسخه پخش" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">فرمت</span><UiSelect v-model="filters.format" :options="formatOptions" label="فرمت محتوا" compact /></div>
          <div><span class="mb-1.5 block text-[11px] font-bold text-muted">حداقل امتیاز</span><UiSelect v-model="filters.minRating" :options="ratingOptions" label="حداقل امتیاز" compact /></div>
          <div class="sm:col-span-2 xl:col-span-4">
            <p class="mb-2 text-[11px] font-bold text-muted">ژانر</p>
            <GenreChips v-model="filters.genre" :genres="genres" compact />
          </div>
        </div>
      </details>
      <div v-if="!type" class="mt-4 border-t border-line pt-4">
        <div v-if="!type">
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
      </div>
      <div
        v-if="activeFilters"
        class="mt-2 rounded-xl bg-primary-500/10 p-2.5 ring-1 ring-primary-500/20"
      >
        <div class="flex items-center justify-between gap-3 px-1">
          <p class="text-xs font-bold text-primary-300">فیلترهای فعال</p>
          <button
            type="button"
            class="min-h-11 text-xs font-black text-primary-300 hover:text-primary-200"
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
            class="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl bg-elevated px-3 text-xs font-bold text-secondary ring-1 ring-primary-500/30"
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
      @retry="retryCatalog"
    />
    <div
      class="ui-surface mb-4 flex min-h-12 flex-wrap items-center justify-between gap-3 px-4 py-2.5"
      aria-live="polite"
    >
      <div class="flex min-w-0 items-center gap-2.5">
        <span
          class="grid size-8 shrink-0 place-items-center rounded-xl bg-primary-500/14 text-primary-300"
          ><CinematicIcon name="search" class="size-4.5"
        /></span>
        <p class="truncate text-sm font-black text-ink">
          {{ pending ? "در حال جستجو..." : showingRelatedResults ? `${resultLabel} مرتبط` : resultLabel
          }}<span v-if="filters.query" class="font-semibold text-muted">
            برای «{{ filters.query }}»</span
          >
        </p>
      </div>
      <span class="shrink-0 text-[11px] font-bold text-muted"
        >مرتب‌شده بر اساس {{ activeSortLabel }}</span
      >
    </div>
    <div
      v-if="!pending && showingRelatedResults"
      class="mb-4 flex items-start gap-3 rounded-2xl bg-primary-500/10 px-4 py-3 text-sm text-secondary ring-1 ring-primary-500/25"
      role="status"
    >
      <CinematicIcon name="search" class="mt-0.5 size-4.5 shrink-0 text-brand" />
      <p>
        نتیجهٔ مستقیمی برای «{{ filters.query }}» پیدا نشد؛ نزدیک‌ترین فیلم‌ها و سریال‌های مرتبط یا هم‌نام نمایش داده شده‌اند.
      </p>
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
    <CatalogPagination
      :page="safePage"
      :total-pages="totalPages"
      :total="resultCount"
      :pending="pending"
      :label="`صفحه‌بندی ${title}`"
      @change="goToPage"
    />
    <div v-if="!pending && !filteredItems.length" class="mt-4 text-center">
      <p class="text-xs font-bold text-muted">جستجوهای پیشنهادی</p>
      <div class="mt-2 flex flex-wrap justify-center gap-2">
        <button
          v-for="item in quickSearches"
          :key="item.label"
          type="button"
          class="min-h-11 rounded-xl bg-elevated px-3 py-2 text-xs font-bold text-secondary ring-1 ring-line hover:text-primary-300 hover:ring-primary-500/40"
          @click="applyQuickFilter(item)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>
  </div>
</template>
