package com.revayato.app.feature.discovery

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.data.model.CountryDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState

private val COUNTRY_GRADIENTS = listOf(
    listOf(Color(0xFF3A6EA5), Color(0xFF12406B)),
    listOf(Color(0xFF8A72B0), Color(0xFF43325F)),
    listOf(Color(0xFFE07A5F), Color(0xFF8C3B22)),
    listOf(Color(0xFF6A8CA8), Color(0xFF2E4459)),
    listOf(Color(0xFFC4606E), Color(0xFF5E2231)),
    listOf(Color(0xFFC9894A), Color(0xFF6B3F1D)),
)

/**
 * Full country directory. Tapping a country opens its catalog list via
 * [onOpenCountry] with the backend `country` filter value (ISO code, else name).
 */
@Composable
fun CountriesScreen(
    onBack: () -> Unit,
    onOpenCountry: (filterValue: String, name: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CountriesViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(modifier.fillMaxSize()) {
        BackTopBar(title = "کشورها", onBack = onBack)
        when {
            state.loading -> LoadingState(Modifier.fillMaxSize())
            state.error != null -> ErrorState(state.error!!, Modifier.fillMaxSize(), onRetry = viewModel::load)
            state.countries.isEmpty() -> EmptyState("چیزی برای نمایش نیست", modifier = Modifier.fillMaxSize())
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.countries, key = { it.id }) { country ->
                    CountryTile(
                        country = country,
                        onClick = { onOpenCountry(country.filterValue, country.name) },
                    )
                }
            }
        }
    }
}

@Composable
private fun CountryTile(country: CountryDto, onClick: () -> Unit) {
    val colors = COUNTRY_GRADIENTS[country.id.mod(COUNTRY_GRADIENTS.size)]
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(1.9f)
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(colors))
            .clickable(onClick = onClick)
            .padding(14.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = country.name,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                textAlign = TextAlign.Center,
            )
            Text(
                text = "${country.titleCount} عنوان",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xCCFFFFFF),
            )
        }
    }
}
