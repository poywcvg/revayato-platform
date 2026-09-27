package com.revayato.app.feature.catalog

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Animation
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.Category
import androidx.compose.material.icons.rounded.Explore
import androidx.compose.material.icons.rounded.FamilyRestroom
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Gavel
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.NightsStay
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material.icons.rounded.Science
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.SportsMartialArts
import androidx.compose.material.icons.rounded.TheaterComedy
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.data.model.GenreDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState

/**
 * A dedicated, browsable genres page: every published genre rendered as a large
 * gradient card carrying a genre-relevant icon + title count. Tapping a card opens
 * the catalog list already filtered to that genre (ordered by popularity), so the
 * page is a real entry point into the catalogue rather than a flat list of words.
 */
@Composable
fun GenresScreen(
    onBack: () -> Unit,
    onOpenGenre: (GenreDto) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: GenresViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val navBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()

    Column(modifier.fillMaxSize()) {
        BackTopBar(title = "ژانرها", onBack = onBack)
        when {
            state.loading -> LoadingState(Modifier.fillMaxSize())
            state.error != null -> ErrorState(state.error!!, Modifier.fillMaxSize(), onRetry = viewModel::load)
            state.genres.isEmpty() -> EmptyState("ژانری برای نمایش نیست", modifier = Modifier.fillMaxSize())
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 24.dp + navBottom),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                items(state.genres, key = { it.id }) { genre ->
                    GenreTile(
                        genre = genre,
                        gradient = gradientFor(genre),
                        icon = iconFor(genre.title),
                        onClick = { onOpenGenre(genre) },
                    )
                }
            }
        }
    }
}

@Composable
private fun GenreTile(
    genre: GenreDto,
    gradient: List<Color>,
    icon: ImageVector,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(1.35f)
            .clip(RoundedCornerShape(20.dp))
            .background(Brush.linearGradient(gradient))
            .clickable(onClick = onClick),
    ) {
        // Oversized, low-opacity icon bleeds off the corner as a decorative motif.
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.16f),
            modifier = Modifier
                .align(Alignment.TopEnd)
                .offset(x = 14.dp, y = (-10).dp)
                .size(96.dp),
        )
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(22.dp),
            )
            Text(
                text = genre.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                maxLines = 2,
            )
            if (genre.titleCount > 0) {
                Text(
                    text = "${genre.titleCount} عنوان",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.White.copy(alpha = 0.82f),
                )
            }
        }
    }
}

/** Rich, saturated gradient pairs — deliberately punchier than the small chips so a
 *  full-bleed tile reads well. Chosen by a stable hash of the slug so a genre keeps
 *  its colour across app launches. */
private val GENRE_GRADIENTS = listOf(
    listOf(Color(0xFFEF476F), Color(0xFF8C1C3B)),
    listOf(Color(0xFF3A6EA5), Color(0xFF12406B)),
    listOf(Color(0xFF9B5DE5), Color(0xFF5A2A8C)),
    listOf(Color(0xFF06D6A0), Color(0xFF0A6E56)),
    listOf(Color(0xFFF2994A), Color(0xFF9C4B16)),
    listOf(Color(0xFF2EC4B6), Color(0xFF14776E)),
    listOf(Color(0xFFF2C14E), Color(0xFF9C7A16)),
    listOf(Color(0xFF577590), Color(0xFF33475B)),
    listOf(Color(0xFFE07A5F), Color(0xFF8C3B22)),
    listOf(Color(0xFF6A4C93), Color(0xFF3A2A57)),
)

private fun gradientFor(genre: GenreDto): List<Color> {
    val key = genre.slug.ifBlank { genre.title }
    val index = (key.hashCode() % GENRE_GRADIENTS.size + GENRE_GRADIENTS.size) % GENRE_GRADIENTS.size
    return GENRE_GRADIENTS[index]
}

/** Map a Persian genre title to a fitting icon so the page reads by symbol, not just
 *  by text. Falls back to a neutral category glyph for anything unrecognised. */
private fun iconFor(title: String): ImageVector = when {
    title.contains("اکشن") || title.contains("رزمی") -> Icons.Rounded.SportsMartialArts
    title.contains("کمدی") || title.contains("طنز") -> Icons.Rounded.TheaterComedy
    title.contains("درام") -> Icons.Rounded.TheaterComedy
    title.contains("ترس") || title.contains("وحشت") || title.contains("هراس") -> Icons.Rounded.NightsStay
    title.contains("علمی") || title.contains("تخیلی") -> Icons.Rounded.Science
    title.contains("انیمیشن") || title.contains("انیمه") || title.contains("کارتون") -> Icons.Rounded.Animation
    title.contains("ماجرا") -> Icons.Rounded.Explore
    title.contains("جنایی") || title.contains("جرم") -> Icons.Rounded.Gavel
    title.contains("عاشقانه") || title.contains("رمانتیک") -> Icons.Rounded.Favorite
    title.contains("مستند") -> Icons.Rounded.Public
    title.contains("خانوادگی") || title.contains("کودک") -> Icons.Rounded.FamilyRestroom
    title.contains("فانتزی") || title.contains("خیال") -> Icons.Rounded.AutoAwesome
    title.contains("موزیک") || title.contains("موسیقی") -> Icons.Rounded.MusicNote
    title.contains("معما") || title.contains("رازآلود") || title.contains("راز") -> Icons.Rounded.Search
    title.contains("تاریخ") -> Icons.Rounded.History
    title.contains("هیجان") || title.contains("دلهره") -> Icons.Rounded.Bolt
    title.contains("جنگ") -> Icons.Rounded.LocalFireDepartment
    else -> Icons.Rounded.Category
}
