package com.revayato.app.feature.library

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.ui.UiState
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.PosterGrid

@Composable
fun LibraryScreen(
    isLoggedIn: Boolean,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onOpenDownloads: () -> Unit,
    onRequireLogin: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: LibraryViewModel = hiltViewModel(),
) {
    if (!isLoggedIn) {
        EmptyState(
            title = "کتابخانه‌ات اینجاست",
            subtitle = "برای دیدن فهرست تماشا و علاقه‌مندی‌ها وارد شو",
            actionLabel = "ورود",
            onAction = onRequireLogin,
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    LaunchedEffect(Unit) { viewModel.load() }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var tab by remember { mutableIntStateOf(0) }
    val tabs = listOf("فهرست تماشا", "علاقه‌مندی‌ها", "دانلودها")

    Column(modifier.fillMaxSize()) {
        TabRow(
            selectedTabIndex = tab,
            containerColor = MaterialTheme.colorScheme.background,
            contentColor = Brand,
            indicator = { positions ->
                if (tab < positions.size) {
                    TabRowDefaults.SecondaryIndicator(
                        Modifier.tabIndicatorOffset(positions[tab]),
                        color = Brand,
                    )
                }
            },
        ) {
            tabs.forEachIndexed { index, title ->
                Tab(
                    selected = tab == index,
                    onClick = {
                        tab = index
                        if (index == 2) onOpenDownloads()
                    },
                    text = { Text(title, style = MaterialTheme.typography.labelLarge) },
                    selectedContentColor = Brand,
                    unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        when (val s = state) {
            is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
            is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = viewModel::load)
            is UiState.Success -> {
                val items = if (tab == 1) s.data.favorites else s.data.watchlist
                if (tab == 2) {
                    EmptyState(
                        title = "دانلودها",
                        subtitle = "برای مدیریت فایل‌های دانلودشده وارد بخش دانلودها شو",
                        actionLabel = "باز کردن دانلودها",
                        onAction = onOpenDownloads,
                        modifier = Modifier.fillMaxSize(),
                    )
                } else if (items.isEmpty()) {
                    EmptyState(
                        title = if (tab == 1) "هنوز چیزی نپسندیدی" else "فهرست تماشایت خالی است",
                        subtitle = "از صفحهٔ هر فیلم یا سریال اضافه کن",
                        modifier = Modifier.fillMaxSize(),
                    )
                } else {
                    PosterGrid(
                        items = items,
                        onItemClick = { onOpenTitle(it.contentType, it.slug) },
                    )
                }
            }
        }
    }
}
