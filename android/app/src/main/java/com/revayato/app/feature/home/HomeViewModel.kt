package com.revayato.app.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.orNull
import com.revayato.app.core.playback.WatchProgressEntry
import com.revayato.app.core.playback.WatchProgressStore
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.repository.CatalogQuery
import com.revayato.app.data.repository.CatalogRepository
import com.revayato.app.navigation.Routes
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class HomeData(
    val hero: List<CatalogCardDto>,
    val rails: List<HomeRail>,
    val continueWatching: List<WatchProgressEntry> = emptyList(),
    val genres: List<GenreDto> = emptyList(),
)

data class HomeRail(
    val key: String,
    val title: String,
    val items: List<CatalogCardDto>,
    // Full nav route for the "مشاهده بیشتر" button — points at the catalog page whose
    // server-side algorithm reproduces this exact shelf. Null hides the button.
    val seeAllRoute: String? = null,
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
    private val watchProgressStore: WatchProgressStore,
) : ViewModel() {

    // Catalog-only result; the Continue Watching shelf is merged in live below so
    // the shelf reflects playback the instant the user returns from the player.
    private val _catalog = MutableStateFlow<UiState<HomeData>>(UiState.Loading)

    val state: StateFlow<UiState<HomeData>> =
        combine(_catalog, watchProgressStore.entries) { catalog, entries ->
            when (catalog) {
                is UiState.Loading -> UiState.Loading
                is UiState.Error -> catalog
                is UiState.Success -> UiState.Success(catalog.data.copy(continueWatching = entries))
            }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), UiState.Loading)

    init {
        load()
    }

    fun load() {
        _catalog.value = UiState.Loading
        viewModelScope.launch {
            // Every shelf is fetched in parallel; the backend caches each list, so a
            // dozen concurrent reads is cheap. Each rail below carries a `seeAllRoute`
            // whose server-side sort/filter reproduces the same ordering full-screen.
            val recentDef = async { catalogRepository.recent(limit = 20) }
            val recsDef = async { catalogRepository.recommendations() }
            val moviesDef = async { catalogRepository.movies(CatalogQuery(sort = "newest", limit = 20)) }
            val seriesDef = async { catalogRepository.series(CatalogQuery(sort = "newest", limit = 20)) }
            val popularMoviesDef = async { catalogRepository.movies(CatalogQuery(sort = "popular", limit = 20)) }
            val popularSeriesDef = async { catalogRepository.series(CatalogQuery(sort = "popular", limit = 20)) }
            val topRatedDef = async { catalogRepository.movies(CatalogQuery(sort = "rating", limit = 20)) }
            val dubbedDef = async { catalogRepository.movies(CatalogQuery(availability = "dubbed", sort = "popular", limit = 20)) }
            val subtitledDef = async { catalogRepository.movies(CatalogQuery(availability = "subtitle", sort = "newest", limit = 20)) }
            val animeDef = async { catalogRepository.anime(limit = 20) }
            val top250MoviesDef = async { catalogRepository.top250("movie", limit = 20) }
            val top250SeriesDef = async { catalogRepository.top250("series", limit = 20) }
            val animationDef = async { catalogRepository.movies(CatalogQuery(contentFormat = "animation", sort = "popular", limit = 20)) }
            val collectionsDef = async { catalogRepository.collections() }
            val genresDef = async { catalogRepository.genres() }

            // Progressive rendering: publish each shelf the instant its data lands
            // — always re-sorted into the canonical page order — instead of blocking
            // the whole screen on the slowest of a dozen concurrent calls. First
            // paint now happens on the first shelf that returns; the rest fill in as
            // they arrive, so the home feed feels immediate even on a slow network.
            val rails = linkedMapOf<String, HomeRail>()
            var hero: List<CatalogCardDto> = emptyList()
            var genres: List<GenreDto> = emptyList()
            var newest: List<CatalogCardDto> = emptyList()

            fun publish() {
                if (hero.isEmpty() && rails.isEmpty()) return
                val ordered = rails.values.sortedBy { rail ->
                    RAIL_ORDER.indexOf(rail.key).let { if (it < 0) RAIL_ORDER.size else it }
                }
                _catalog.value = UiState.Success(HomeData(hero = hero, rails = ordered, genres = genres))
            }

            // A shelf is fetched, folded into the accumulator, then published. Each
            // await suspends only on its own call, so a slow shelf never delays the
            // ones that already arrived.
            suspend fun stage(fetch: suspend () -> Unit) {
                fetch()
                publish()
            }

            // Newest movies lead: they seed the hero and a top shelf, so the page can
            // paint as soon as this single (cached) call returns.
            stage {
                newest = moviesDef.await().orNull()?.results.orEmpty()
                if (newest.isNotEmpty()) {
                    hero = newest.filter { it.backdropUrl != null }.take(6).ifEmpty { newest.take(6) }
                    rails["movies"] = HomeRail("movies", "جدیدترین فیلم‌ها", newest, Routes.catalogList("movies", "جدیدترین فیلم‌ها", sort = "newest"))
                }
            }
            stage {
                val recent = recentDef.await().orNull().orEmpty()
                if (recent.isNotEmpty()) rails["recent"] = HomeRail("recent", "تازه‌ها و به‌روزشده‌ها", recent, Routes.catalogList("recent", "تازه‌ها و به‌روزشده‌ها"))
            }
            stage {
                val popularMovies = popularMoviesDef.await().orNull()?.results.orEmpty()
                if (popularMovies.isNotEmpty()) rails["popular-movies"] = HomeRail("popular-movies", "محبوب‌ترین فیلم‌ها", popularMovies, Routes.catalogList("movies", "محبوب‌ترین فیلم‌ها", sort = "popular"))
            }
            stage {
                val recs = recsDef.await().orNull().orEmpty()
                if (recs.isNotEmpty()) rails["recs"] = HomeRail("recs", "پیشنهاد برای شما", recs)
            }
            stage {
                val series = seriesDef.await().orNull()?.results.orEmpty()
                if (series.isNotEmpty()) rails["series"] = HomeRail("series", "جدیدترین سریال‌ها", series, Routes.catalogList("series", "جدیدترین سریال‌ها", sort = "newest"))
            }
            stage {
                val topRated = topRatedDef.await().orNull()?.results.orEmpty()
                if (topRated.isNotEmpty()) rails["top"] = HomeRail("top", "برترین‌های امتیاز", topRated, Routes.catalogList("movies", "برترین‌های امتیاز", sort = "rating"))
            }
            stage {
                val dubbed = dubbedDef.await().orNull()?.results.orEmpty()
                if (dubbed.isNotEmpty()) rails["dubbed"] = HomeRail("dubbed", "دوبله فارسی", dubbed, Routes.catalogList("movies", "دوبله فارسی", sort = "popular", availability = "dubbed"))
            }
            stage {
                val popularSeries = popularSeriesDef.await().orNull()?.results.orEmpty()
                if (popularSeries.isNotEmpty()) rails["popular-series"] = HomeRail("popular-series", "محبوب‌ترین سریال‌ها", popularSeries, Routes.catalogList("series", "محبوب‌ترین سریال‌ها", sort = "popular"))
            }
            stage {
                val subtitled = subtitledDef.await().orNull()?.results.orEmpty()
                if (subtitled.isNotEmpty()) rails["subtitled"] = HomeRail("subtitled", "زیرنویس‌دار", subtitled, Routes.catalogList("movies", "زیرنویس‌دار", sort = "newest", availability = "subtitle"))
            }
            stage {
                val chart = top250MoviesDef.await().orNull().orEmpty()
                if (chart.isNotEmpty()) rails["top250-movies"] = HomeRail("top250-movies", "۲۵۰ فیلم برتر IMDb", chart, Routes.catalogList("top250", "۲۵۰ برتر IMDb"))
            }
            stage {
                val chart = top250SeriesDef.await().orNull().orEmpty()
                if (chart.isNotEmpty()) rails["top250-series"] = HomeRail("top250-series", "۲۵۰ سریال برتر IMDb", chart, Routes.catalogList("top250", "۲۵۰ برتر IMDb", format = "series"))
            }
            stage {
                val anime = animeDef.await().orNull().orEmpty()
                if (anime.isNotEmpty()) rails["anime"] = HomeRail("anime", "دنیای انیمه", anime, Routes.catalogList("anime", "دنیای انیمه"))
            }
            stage {
                val animation = animationDef.await().orNull()?.results.orEmpty()
                if (animation.isNotEmpty()) rails["animation"] = HomeRail("animation", "انیمیشن‌ها", animation, Routes.catalogList("movies", "انیمیشن‌ها", sort = "popular", format = "animation"))
            }
            stage {
                collectionsDef.await().orNull().orEmpty().filter { it.items.isNotEmpty() }.take(4).forEach { c ->
                    rails["collection-${c.slug}"] = HomeRail("collection-${c.slug}", c.title, c.items)
                }
            }
            stage { genres = genresDef.await().orNull().orEmpty() }

            // Nothing came back from any shelf → surface the empty state.
            if (_catalog.value is UiState.Loading) {
                _catalog.value = UiState.Error("محتوایی برای نمایش پیدا نشد")
            }
        }
    }

    companion object {
        // Canonical top-to-bottom shelf order. Shelves publish as they arrive but
        // are always rendered in this order; collection shelves (dynamic keys) fall
        // through to the end in arrival order.
        private val RAIL_ORDER = listOf(
            // The IMDb Top 250 shelves sit right under the fresh arrivals — the most
            // seen slot after the hero, as asked.
            "recent", "top250-movies", "top250-series", "recs", "popular-movies", "series", "top",
            "dubbed", "movies", "popular-series", "subtitled", "anime", "animation",
        )
    }
}
