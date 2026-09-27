package com.revayato.app.feature.catalog

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Animation
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.Fireplace
import androidx.compose.material.icons.rounded.LiveTv
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.NewReleases
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentRed
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CountryDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.PersonListItemDto
import com.revayato.app.feature.discovery.DiscoveryData
import com.revayato.app.feature.discovery.DiscoveryViewModel
import com.revayato.app.navigation.Routes
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.PersonAvatar
import com.revayato.app.ui.components.SectionHeader

/** A palette of soft gradient pairs cycled across the genre tiles. */
private val TILE_GRADIENTS = listOf(
    listOf(Color(0xFF3A6EA5), Color(0xFF12406B)),
    listOf(Color(0xFF9B5DE5), Color(0xFF5A2A8C)),
    listOf(Color(0xFFE07A5F), Color(0xFF8C3B22)),
    listOf(Color(0xFF2EC4B6), Color(0xFF14776E)),
    listOf(Color(0xFFF2C14E), Color(0xFF9C7A16)),
    listOf(Color(0xFFEF476F), Color(0xFF8C1C3B)),
    listOf(Color(0xFF06D6A0), Color(0xFF0A6E56)),
    listOf(Color(0xFF577590), Color(0xFF33475B)),
)

private val CHIP_ACCENTS = listOf(AccentYellow, AccentRed, AccentBlue, PlayAccent, BrandMint)

/** A one-tap access shortcut backed by a ready-made catalog route. */
private data class QuickAccess(
    val label: String,
    val icon: ImageVector,
    val colors: List<Color>,
    val route: String,
)

private val QUICK_ACCESS = listOf(
    QuickAccess("۲۵۰ برتر IMDb", Icons.Rounded.EmojiEvents, listOf(Color(0xFFF5C518), Color(0xFF8A6A00)), Routes.catalogList("top250", "۲۵۰ برتر IMDb")),
    QuickAccess("فیلم‌ها", Icons.Rounded.Movie, listOf(Color(0xFF3A6EA5), Color(0xFF12406B)), Routes.catalogList("movies", "فیلم‌ها", sort = "popular")),
    QuickAccess("سریال‌ها", Icons.Rounded.LiveTv, listOf(Color(0xFF9B5DE5), Color(0xFF5A2A8C)), Routes.catalogList("series", "سریال‌ها", sort = "popular")),
    QuickAccess("دوبله فارسی", Icons.Rounded.Mic, listOf(Color(0xFF06D6A0), Color(0xFF0A6E56)), Routes.catalogList("movies", "دوبله فارسی", sort = "popular", availability = "dubbed")),
    QuickAccess("زیرنویس‌دار", Icons.Rounded.ClosedCaption, listOf(Color(0xFF577590), Color(0xFF33475B)), Routes.catalogList("movies", "زیرنویس‌دار", sort = "newest", availability = "subtitle")),
    QuickAccess("دنیای انیمه", Icons.Rounded.Fireplace, listOf(Color(0xFFEF476F), Color(0xFF8C1C3B)), Routes.catalogList("anime", "دنیای انیمه")),
    QuickAccess("انیمیشن", Icons.Rounded.Animation, listOf(Color(0xFFF2C14E), Color(0xFF9C7A16)), Routes.catalogList("movies", "انیمیشن‌ها", sort = "popular", format = "animation")),
    QuickAccess("تازه‌ها", Icons.Rounded.NewReleases, listOf(Color(0xFFE07A5F), Color(0xFF8C3B22)), Routes.catalogList("recent", "تازه‌ها و به‌روزشده‌ها")),
)

@Composable
fun CategoriesScreen(
    onNavigate: (route: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: DiscoveryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    when (val s = state) {
        is UiState.Loading -> LoadingState(modifier.fillMaxSize())
        is UiState.Error -> ErrorState(s.message, modifier.fillMaxSize(), onRetry = viewModel::load)
        is UiState.Success -> DiscoveryContent(s.data, onNavigate, modifier)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DiscoveryContent(
    data: DiscoveryData,
    onNavigate: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 28.dp),
    ) {
        // ---- Quick access shortcuts ----
        item(key = "quick-header") {
            SectionHeader(title = "دسترسی سریع", accent = BrandMint)
        }
        item(key = "quick") {
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(QUICK_ACCESS, key = { it.label }) { q ->
                    QuickAccessTile(q, onClick = { onNavigate(q.route) })
                }
            }
        }

        // ---- Genres ----
        if (data.genres.isNotEmpty()) {
            item(key = "genres-header") {
                SectionHeader(
                    title = "ژانرها",
                    accent = AccentBlue,
                    onSeeAll = { onNavigate(Routes.GENRES) },
                )
            }
            item(key = "genres") {
                FlowRow(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    data.genres.forEachIndexed { index, genre ->
                        GenreChip(
                            genre = genre,
                            accent = CHIP_ACCENTS[index % CHIP_ACCENTS.size],
                            onClick = { onNavigate(Routes.catalogList("movies", genre.title, genre = genre.slug, sort = "popular")) },
                        )
                    }
                }
            }
        }

        // ---- Countries ----
        if (data.countries.isNotEmpty()) {
            item(key = "countries-header") {
                SectionHeader(
                    title = "کشورها",
                    accent = AccentYellow,
                    onSeeAll = { onNavigate(Routes.COUNTRIES) },
                )
            }
            item(key = "countries") {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(data.countries.take(16), key = { it.id }) { country ->
                        CountryPill(
                            country = country,
                            onClick = {
                                onNavigate(
                                    Routes.catalogList("movies", country.name, country = country.filterValue, sort = "popular"),
                                )
                            },
                        )
                    }
                }
            }
        }

        // ---- Actors ----
        if (data.actors.isNotEmpty()) {
            item(key = "actors-header") {
                SectionHeader(
                    title = "بازیگران",
                    accent = AccentRed,
                    onSeeAll = { onNavigate(Routes.ACTORS) },
                )
            }
            item(key = "actors") {
                PeopleCarousel(data.actors) { onNavigate(Routes.actorDetail(it.slug)) }
            }
        }

        // ---- Directors ----
        if (data.directors.isNotEmpty()) {
            item(key = "directors-header") {
                SectionHeader(
                    title = "کارگردانان",
                    accent = PlayAccent,
                    onSeeAll = { onNavigate(Routes.DIRECTORS) },
                )
            }
            item(key = "directors") {
                PeopleCarousel(data.directors) { onNavigate(Routes.directorDetail(it.slug)) }
            }
        }
    }
}

@Composable
private fun QuickAccessTile(q: QuickAccess, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(96.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(q.colors))
            .clickable(onClick = onClick)
            .padding(vertical = 16.dp, horizontal = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(q.icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(26.dp))
        Text(
            text = q.label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center,
            maxLines = 1,
        )
    }
}

@Composable
private fun GenreChip(genre: GenreDto, accent: Color, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(accent.copy(alpha = 0.14f))
            .border(1.dp, accent.copy(alpha = 0.45f), RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = genre.title,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = accent,
        )
        val count = genre.titleCount
        if (count > 0) {
            Text(
                text = count.toString(),
                style = MaterialTheme.typography.labelSmall,
                color = accent.copy(alpha = 0.75f),
            )
        }
    }
}

@Composable
private fun CountryPill(country: CountryDto, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(88.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Color(0x14FFFFFF))
            .border(1.dp, Color(0x1FFFFFFF), RoundedCornerShape(16.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 14.dp, horizontal = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = country.name,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
            maxLines = 2,
        )
        Text(
            text = "${country.titleCount} عنوان",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun PeopleCarousel(people: List<PersonListItemDto>, onClick: (PersonListItemDto) -> Unit) {
    LazyRow(
        contentPadding = PaddingValues(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        items(people, key = { it.id }) { person ->
            PersonAvatar(
                name = person.displayName,
                imageUrl = person.imageUrl,
                subtitle = person.birthPlace,
                onClick = { onClick(person) },
                modifier = Modifier.width(96.dp),
            )
        }
    }
}
