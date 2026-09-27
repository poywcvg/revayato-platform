package com.revayato.app.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Login
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.BgSurface
import com.revayato.app.core.theme.BrandGreen
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary

/**
 * The slide-in drawer — deliberately short. Everything the bottom bar already
 * offers (home, movies, series, categories, library) and the genre list (which
 * lives on the categories tab) is left out, so the drawer holds only the few
 * places the bar cannot reach.
 */
@Composable
fun BrowseDrawerContent(
    isLoggedIn: Boolean,
    onTop250: () -> Unit,
    onWatchParty: () -> Unit,
    onDownloads: () -> Unit,
    onProfile: () -> Unit,
    onLogin: () -> Unit,
    onLogout: () -> Unit,
) {
    ModalDrawerSheet(
        drawerContainerColor = BgSurface,
        modifier = Modifier.fillMaxWidth(0.78f),
    ) {
        Column(
            Modifier
                .verticalScroll(rememberScrollState())
                .padding(bottom = 24.dp),
        ) {
            DrawerHeader(isLoggedIn = isLoggedIn, onLogin = onLogin)
            Spacer(Modifier.height(8.dp))

            DrawerItem(Icons.Rounded.EmojiEvents, "۲۵۰ برتر IMDb", onTop250, tint = ImdbGold)
            DrawerItem(Icons.Rounded.Groups, "تماشای گروهی", onWatchParty)
            DrawerItem(Icons.Rounded.Download, "دانلودها", onDownloads)
            DrawerItem(Icons.Rounded.Person, "پروفایل", onProfile)

            Spacer(Modifier.height(8.dp))
            DrawerDivider()
            Spacer(Modifier.height(8.dp))
            if (isLoggedIn) {
                DrawerItem(Icons.AutoMirrored.Rounded.Logout, "خروج از حساب", onLogout, tint = TextMuted)
            } else {
                DrawerItem(Icons.AutoMirrored.Rounded.Login, "ورود / ثبت‌نام", onLogin, tint = BrandMint)
            }
        }
    }
}

/** IMDb's own yellow — the one colour everyone reads as "IMDb". */
private val ImdbGold = Color(0xFFF5C518)

@Composable
private fun DrawerHeader(isLoggedIn: Boolean, onLogin: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(20.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(Brush.linearGradient(listOf(BrandMint, BrandGreen))),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Rounded.Movie, contentDescription = null, tint = OnBrand)
            }
            Text("روایتو", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black, color = TextPrimary)
        }
        Spacer(Modifier.height(12.dp))
        if (isLoggedIn) {
            Text("خوش آمدی 👋", style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
        } else {
            Box(
                modifier = Modifier
                    .clip(CircleShape)
                    .background(BrandMint)
                    .clickable(onClick = onLogin)
                    .padding(horizontal = 18.dp, vertical = 8.dp),
            ) {
                Text("ورود به حساب", color = OnBrand, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            }
        }
    }
    DrawerDivider()
}

@Composable
private fun DrawerItem(icon: ImageVector, label: String, onClick: () -> Unit, tint: Color = TextPrimary) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Icon(icon, contentDescription = label, tint = tint)
        Text(label, style = MaterialTheme.typography.bodyLarge, color = tint, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun DrawerDivider() {
    Box(Modifier.fillMaxWidth().padding(horizontal = 20.dp).height(1.dp).background(OutlineSoft))
}
