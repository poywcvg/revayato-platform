package com.revayato.app.feature.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.rounded.Login
import androidx.compose.material.icons.automirrored.rounded.Message
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.LibraryAddCheck
import androidx.compose.material.icons.rounded.Share
import androidx.compose.material.icons.rounded.SystemUpdate
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.BuildConfig
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.feature.collections.CollectionCard
import com.revayato.app.feature.support.toFaDigits
import com.revayato.app.feature.update.UpdateViewModel
import kotlinx.coroutines.delay

private const val SITE_BASE = "https://revayato.com"

@Composable
fun ProfileScreen(
    isLoggedIn: Boolean,
    onOpenDownloads: () -> Unit,
    onLogin: () -> Unit,
    onLoggedOut: () -> Unit,
    onOpenMyCollections: () -> Unit,
    onOpenCollection: (slug: String) -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    modifier: Modifier = Modifier,
    onOpenMyRequests: () -> Unit = {},
    onOpenDashboard: () -> Unit = {},
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val clipboard = LocalClipboardManager.current

    LaunchedEffect(isLoggedIn) { if (isLoggedIn) viewModel.load() }
    LaunchedEffect(state.loggedOut) {
        if (state.loggedOut) {
            viewModel.consumeLoggedOut()
            onLoggedOut()
        }
    }

    val user = state.user
    val profile = state.profile

    LazyColumn(
        modifier = modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        contentPadding = PaddingValues(20.dp, 24.dp, 20.dp, 40.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        // Identity.
        item {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ProfileAvatar(
                    avatar = user?.profile?.avatar,
                    name = user?.username ?: "مهمان",
                )
                ProfileIdentity(
                    displayName = user?.username ?: if (isLoggedIn) "کاربر روایتو" else "مهمان",
                    username = user?.username.orEmpty(),
                    isVerified = user?.isVerified == true,
                    bio = user?.profile?.bio.orEmpty(),
                    memberSince = profile?.memberSince,
                )
                if (isLoggedIn && !user?.username.isNullOrBlank()) {
                    val shareLink = "$SITE_BASE/u/${user!!.username}"
                    Row(
                        Modifier
                            .clip(RoundedCornerShape(999.dp))
                            .background(Brand.copy(alpha = 0.12f))
                            .clickable {
                                clipboard.setText(AnnotatedString(shareLink))
                            }
                            .padding(horizontal = 14.dp, vertical = 7.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Icon(Icons.Rounded.Share, contentDescription = null, tint = Brand, modifier = Modifier.size(15.dp))
                        Text("اشتراک پروفایل", style = MaterialTheme.typography.labelMedium, color = Brand, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        // Stats (real numbers).
        if (isLoggedIn && profile != null) {
            item { ProfileStatsRow(profile.stats) }
        }

        // Guest prompt.
        if (!isLoggedIn) {
            item {
                Text(
                    "برای ساختن کالکشن، امتیازدهی و همگام‌سازی وارد شو.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextMuted,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        // My collections rail.
        if (isLoggedIn) {
            item {
                ProfileSectionTitle(
                    title = "کالکشن‌های من",
                    action = {
                        Text(
                            "مدیریت",
                            style = MaterialTheme.typography.labelMedium,
                            color = Brand,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.clickable(onClick = onOpenMyCollections),
                        )
                    },
                )
            }
            val collections = profile?.collections.orEmpty()
            if (collections.isEmpty()) {
                item {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(16.dp))
                            .background(MaterialTheme.colorScheme.surface)
                            .clickable(onClick = onOpenMyCollections)
                            .padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Icon(Icons.Rounded.LibraryAddCheck, contentDescription = null, tint = Brand)
                        Text("اولین کالکشنت را بساز", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, contentDescription = null, tint = TextMuted)
                    }
                }
            } else {
                item {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        items(collections, key = { it.id }) { collection ->
                            CollectionCard(
                                collection = collection,
                                onClick = { onOpenCollection(collection.slug) },
                                modifier = Modifier.width(150.dp),
                            )
                        }
                    }
                }
            }
        }

        // My reviews.
        val reviews = profile?.reviews.orEmpty()
        if (isLoggedIn && reviews.isNotEmpty()) {
            item { ProfileSectionTitle(title = "نقدهای من") }
            items(reviews, key = { "${it.contentType}-${it.objectId}" }) { review ->
                ReviewCard(review = review, onOpenTitle = onOpenTitle)
            }
        }

        // Settings.
        item {
            Column {
                if (user?.isStaff == true) {
                    ProfileRow(icon = Icons.Rounded.BarChart, label = "داشبورد آمار", onClick = onOpenDashboard)
                }
                ProfileRow(icon = Icons.AutoMirrored.Rounded.Message, label = "درخواست‌های من", onClick = onOpenMyRequests)
                ProfileRow(icon = Icons.Rounded.Download, label = "دانلودهای من", onClick = onOpenDownloads)
                UpdateCheckRow()
                ProfileRow(icon = Icons.Rounded.Info, label = "دربارهٔ روایتو", onClick = {})
            }
        }

        // Auth action.
        item {
            if (isLoggedIn) {
                Button(
                    onClick = viewModel::logout,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = BgElevated, contentColor = ErrorRed),
                ) {
                    Icon(Icons.AutoMirrored.Rounded.Logout, contentDescription = null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.size(8.dp))
                    Text("خروج از حساب", fontWeight = FontWeight.Bold)
                }
            } else {
                Button(
                    onClick = onLogin,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Brand, contentColor = OnBrand),
                ) {
                    Icon(Icons.AutoMirrored.Rounded.Login, contentDescription = null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.size(8.dp))
                    Text("ورود / ثبت‌نام", fontWeight = FontWeight.Bold)
                }
            }
        }
        item {
            Text(
                // Read from the build, not typed by hand: a stale version number
                // here is the one thing that makes the updater look broken.
                "روایتو نسخهٔ ${toFaDigits(BuildConfig.VERSION_NAME)}",
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ProfileRow(
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
    note: String? = null,
    noteColor: Color = TextMuted,
    trailing: (@Composable () -> Unit)? = null,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = Brand, modifier = Modifier.size(22.dp))
        Spacer(Modifier.size(14.dp))
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            if (note != null) {
                Text(note, style = MaterialTheme.typography.labelSmall, color = noteColor)
            }
        }
        if (trailing != null) {
            trailing()
        } else {
            Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, contentDescription = null, tint = TextMuted)
        }
    }
}

/**
 * «بررسی بروزرسانی» — the manual half of the in-app updater.
 *
 * The sheet itself is hosted by the activity (`AppUpdateHost`), so when there
 * *is* a newer build this row does nothing visible: the sheet takes over. All
 * it owns is the other two answers a manual check can have — "you already have
 * the newest build" and "the check could not reach us" — because a button that
 * silently does nothing reads as broken.
 */
@Composable
private fun UpdateCheckRow(viewModel: UpdateViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    // These notes answer a tap; they should not outlive the reader's attention.
    LaunchedEffect(state.upToDate) {
        if (state.upToDate) {
            delay(4_000)
            viewModel.dismissUpToDate()
        }
    }
    LaunchedEffect(state.error, state.prompting) {
        if (state.error != null && !state.prompting) {
            delay(6_000)
            viewModel.clearError()
        }
    }

    ProfileRow(
        icon = Icons.Rounded.SystemUpdate,
        label = "بررسی بروزرسانی",
        onClick = viewModel::checkNow,
        note = when {
            state.upToDate -> "جدیدترین نسخه را داری"
            state.error != null && !state.prompting -> state.error
            else -> null
        },
        noteColor = if (state.upToDate) PlayAccent else ErrorRed,
        trailing = if (state.checking) {
            {
                CircularProgressIndicator(
                    modifier = Modifier.size(18.dp),
                    strokeWidth = 2.dp,
                    color = Brand,
                )
            }
        } else {
            null
        },
    )
}
