package com.revayato.app.feature.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.orNull
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CountryDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.PersonListItemDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Everything the discovery hub renders in one shot: genres, countries, people. */
data class DiscoveryData(
    val genres: List<GenreDto> = emptyList(),
    val countries: List<CountryDto> = emptyList(),
    val actors: List<PersonListItemDto> = emptyList(),
    val directors: List<PersonListItemDto> = emptyList(),
)

@HiltViewModel
class DiscoveryViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<DiscoveryData>>(UiState.Loading)
    val state: StateFlow<UiState<DiscoveryData>> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = UiState.Loading
        viewModelScope.launch {
            val genresDef = async { catalogRepository.genres() }
            val countriesDef = async { catalogRepository.countries() }
            // Featured-first so the carousels lead with the recognisable names; the
            // "see all" pages fall back to the full popularity-ranked lists.
            val actorsDef = async { catalogRepository.actors(featured = true, limit = 20) }
            val directorsDef = async { catalogRepository.directors(featured = true, limit = 20) }

            val genres = genresDef.await().orNull().orEmpty()
                .sortedByDescending { it.titleCount }
            val countries = countriesDef.await().orNull().orEmpty()
                .sortedByDescending { it.titleCount }
            val actors = actorsDef.await().orNull()?.results.orEmpty()
            val directors = directorsDef.await().orNull()?.results.orEmpty()

            _state.value = if (genres.isEmpty() && countries.isEmpty() && actors.isEmpty() && directors.isEmpty()) {
                UiState.Error("محتوایی برای نمایش پیدا نشد")
            } else {
                UiState.Success(
                    DiscoveryData(
                        genres = genres,
                        countries = countries,
                        actors = actors,
                        directors = directors,
                    ),
                )
            }
        }
    }
}
