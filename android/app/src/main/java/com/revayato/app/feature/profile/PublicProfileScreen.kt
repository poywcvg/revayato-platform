package com.revayato.app.feature.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.PublicProfileDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.feature.collections.CollectionCard
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState

/**
 * Someone else's public profile: identity, real stats, their public collections
 * and reviews. Private profiles show only the identity card.
 */
@Composable
fun PublicProfileScreen(
    username: String,
    onBack: () -> Unit,
    onOpenCollection: (username: String, slug: String) -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: PublicProfileViewModel = hiltViewModel(),
) {
    LaunchedEffect(username) { viewModel.load(username) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { BackTopBar(title = "@$username", onBack = onBack) },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state) {
                is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
                is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = { viewModel.load(username) })
                is UiState.Success -> ProfileBody(
                    profile = s.data,
                    onOpenCollection = onOpenCollection,
                    onOpenTitle = onOpenTitle,
                )
            }
        }
    }
}

@Composable
private fun ProfileBody(
    profile: PublicProfileDto,
    onOpenCollection: (username: String, slug: String) -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 40.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item(span = { GridItemSpan(2) }) {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ProfileAvatar(avatar = profile.avatar, name = profile.displayName.ifBlank { profile.username })
                ProfileIdentity(
                    displayName = profile.displayName,
                    username = profile.username,
                    isVerified = profile.isVerified,
                    bio = profile.bio,
                    memberSince = profile.memberSince,
                )
            }
        }

        if (profile.isPrivate) {
            item(span = { GridItemSpan(2) }) {
                Column(
                    Modifier.fillMaxWidth().padding(top = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Icon(Icons.Rounded.Lock, contentDescription = null, tint = TextMuted, modifier = Modifier.size(34.dp))
                    Text("این پروفایل خصوصی است", fontWeight = FontWeight.Bold, color = TextSecondary)
                    Text("این کاربر کالکشن‌ها و فعالیتش را عمومی نکرده است.", style = MaterialTheme.typography.bodySmall, color = TextMuted)
                }
            }
            return@LazyVerticalGrid
        }

        item(span = { GridItemSpan(2) }) { ProfileStatsRow(profile.stats) }

        if (profile.collections.isNotEmpty()) {
            item(span = { GridItemSpan(2) }) { ProfileSectionTitle("کالکشن‌ها") }
            items(profile.collections, key = { it.id }, span = { GridItemSpan(1) }) { collection ->
                CollectionCard(
                    collection = collection,
                    onClick = { onOpenCollection(profile.username, collection.slug) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        if (profile.reviews.isNotEmpty()) {
            item(span = { GridItemSpan(2) }) { ProfileSectionTitle("نقدها") }
            items(profile.reviews, key = { "${it.contentType}-${it.objectId}" }, span = { GridItemSpan(2) }) { review ->
                ReviewCard(review = review, onOpenTitle = onOpenTitle)
            }
        }

        if (profile.collections.isEmpty() && profile.reviews.isEmpty()) {
            item(span = { GridItemSpan(2) }) {
                Row(
                    Modifier.fillMaxWidth().padding(top = 20.dp),
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Text("هنوز فعالیتی عمومی نشده است.", color = TextMuted, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
