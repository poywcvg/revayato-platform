package com.revayato.app.feature.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowDropDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material.icons.rounded.Refresh
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentRed
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.SurfaceHover
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.AnalyticsBehaviorDto
import com.revayato.app.data.model.AnalyticsCatalogDto
import com.revayato.app.data.model.AnalyticsEngagementDto
import com.revayato.app.data.model.AnalyticsFunnelStageDto
import com.revayato.app.data.model.AnalyticsKpiDto
import com.revayato.app.data.model.AnalyticsNamedValueDto
import com.revayato.app.data.model.AnalyticsRetentionDto
import com.revayato.app.data.model.AnalyticsSearchTermDto
import com.revayato.app.data.model.AnalyticsSeriesPointDto
import com.revayato.app.data.model.AnalyticsTopContentDto
import com.revayato.app.data.model.AnalyticsUserTotalsDto
import com.revayato.app.feature.collection.BackTopBar

@Composable
fun DashboardScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.load() }

    Column(modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { BackTopBar(title = "داشبورد آمار", onBack = onBack) }
            Box(
                Modifier
                    .padding(end = 12.dp)
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(Color(0x1FFFFFFF))
                    .clickable { viewModel.load(refresh = true) },
                contentAlignment = Alignment.Center,
            ) {
                if (state.refreshing) {
                    CircularProgressIndicator(Modifier.size(20.dp), color = BrandMint, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Rounded.Refresh, contentDescription = "به‌روزرسانی", tint = TextPrimary, modifier = Modifier.size(22.dp))
                }
            }
        }

        when {
            state.loading && state.overview == null -> CenterBox {
                CircularProgressIndicator(color = BrandMint)
            }
            state.forbidden -> CenterBox {
                Text("این بخش فقط برای مدیران است.", color = TextSecondary, textAlign = TextAlign.Center)
            }
            state.overview == null && state.users == null && state.error != null -> CenterBox {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(state.error ?: "خطا در دریافت آمار", color = TextSecondary, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "تلاش دوباره",
                        color = OnBrand,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .background(BrandMint)
                            .clickable { viewModel.load(refresh = true) }
                            .padding(horizontal = 20.dp, vertical = 10.dp),
                    )
                }
            }
            else -> DashboardContent(state = state, onPeriod = viewModel::setPeriod)
        }
    }
}

@Composable
private fun DashboardContent(
    state: DashboardState,
    onPeriod: (DashboardPeriod) -> Unit,
) {
    val overview = state.overview
    val totals = state.users?.totals
    val realtime = overview?.realtime

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        // Period selector
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DashboardPeriod.entries.forEach { period ->
                    val selected = state.period == period
                    Text(
                        period.label,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (selected) OnBrand else TextSecondary,
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (selected) BrandMint else BgElevated)
                            .clickable { onPeriod(period) }
                            .padding(horizontal = 16.dp, vertical = 9.dp),
                    )
                }
            }
        }

        // Realtime online strip
        if (realtime != null) {
            item {
                Column {
                    SectionTitle("همین حالا آنلاین")
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        RealtimePill("کاربر آنلاین", realtime.onlineUsers, live = true, modifier = Modifier.weight(1f))
                        RealtimePill("مهمان", realtime.onlineGuests, modifier = Modifier.weight(1f))
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        RealtimePill("پخش زنده", realtime.liveWatchSessions, modifier = Modifier.weight(1f))
                        RealtimePill("اتاق واچ‌پارتی", realtime.activeWatchRooms, modifier = Modifier.weight(1f))
                    }
                }
            }
        }

        // Catalog composition
        val catalog = overview?.catalog
        if (catalog != null && catalog.total > 0) {
            item { SectionTitle("کاتالوگ") }
            item {
                val cards = listOf(
                    StatCardData("فیلم", catalog.movies.fa(), null),
                    StatCardData("سریال", catalog.series.fa(), "${catalog.episodes.fa()} قسمت"),
                    StatCardData("دوبله", catalog.dubbed.fa(), null),
                    StatCardData("زیرنویس", catalog.withSubtitle.fa(), null),
                )
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    cards.chunked(2).forEach { pair ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                            if (pair.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }
        }

        // Overview KPIs
        if (overview != null && overview.kpis.isNotEmpty()) {
            item { SectionTitle("نمای کلی") }
            items(overview.kpis.chunked(2)) { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    pair.forEach { kpi -> KpiCard(kpi, Modifier.weight(1f)) }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }

        // User statistics
        if (totals != null) {
            item { SectionTitle("آمار کاربران") }
            item {
                val cards = userStatCards(totals)
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    cards.chunked(2).forEach { pair ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                            if (pair.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }
        }

        // ---- Behaviour analytics ----
        val behavior = state.behavior
        if (behavior != null && behavior.summary.trackedEvents > 0) {
            // Summary strip
            item { SectionTitle("تحلیل رفتار") }
            item {
                val s = behavior.summary
                val cards = listOf(
                    StatCardData("رویدادها", s.trackedEvents.fa(), "در این بازه"),
                    StatCardData("کاربران فعال", s.activeUsers.fa(), "${s.anonymousSessions.fa()} مهمان"),
                    StatCardData("رویداد/کاربر", (s.eventsPerActive ?: 0.0).fa(), "میانگین عمق"),
                    StatCardData("نرخ تکمیل", behavior.funnel.completionRate?.let { "${it.fa()}٪" } ?: "—", "پخش تا پایان"),
                )
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    cards.chunked(2).forEach { pair ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                            if (pair.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }

            // Behaviour funnel
            if (behavior.funnel.stages.isNotEmpty()) {
                item {
                    Column {
                        SectionTitle("قیف رفتار")
                        Spacer(Modifier.height(10.dp))
                        FunnelCard(behavior.funnel.stages)
                    }
                }
            }

            // Discovery / search CTR
            val disc = behavior.discovery
            if (disc.searches > 0) {
                item { SectionTitle("کشف و جستجو") }
                item {
                    val cards = listOf(
                        StatCardData("جستجوها", disc.searches.fa(), "${disc.uniqueTerms.fa()} عبارت یکتا"),
                        StatCardData("کلیک نتیجه", disc.resultClicks.fa(), "نرخ کلیک ${disc.clickThroughRate?.let { it.fa() } ?: "۰"}٪"),
                        StatCardData("بدون نتیجه", disc.zeroResultSearches.fa(), "${disc.zeroResultRate?.let { it.fa() } ?: "۰"}٪ جستجوها"),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        cards.chunked(2).forEach { pair ->
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                                if (pair.size == 1) Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                }
            }

            // Session depth
            val sess = behavior.sessions
            if (sess.sessions > 0) {
                item { SectionTitle("عمق نشست‌ها") }
                item {
                    val cards = listOf(
                        StatCardData("نشست‌ها", sess.sessions.fa(), "${sess.avgEventsPerSession.fa()} رویداد میانگین"),
                        StatCardData("مدت میانگین", "${sess.avgDurationMinutes.fa()} دقیقه", "میانه ${sess.medianEventsPerSession.fa()} رویداد"),
                        StatCardData("نرخ پرش", sess.bounceRate?.let { "${it.fa()}٪" } ?: "—", "نشست تک‌رویدادی"),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        cards.chunked(2).forEach { pair ->
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                                if (pair.size == 1) Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                }
                if (sess.depthDistribution.any { it.value > 0 }) {
                    item {
                        Column {
                            Spacer(Modifier.height(4.dp))
                            BarListCard(sess.depthDistribution, AccentBlue)
                        }
                    }
                }
            }

            // Retention & stickiness
            item { SectionTitle("ماندگاری و چسبندگی") }
            item { RetentionCard(behavior.retention) }

            // Action mix
            if (behavior.actionMix.any { it.value > 0 }) {
                item { SectionTitle("ترکیب کنش‌ها") }
                item { BarListCard(behavior.actionMix.take(10), BrandMint) }
            }

            // Content interest
            if (behavior.contentInterest.any { it.value > 0 }) {
                item { SectionTitle("کانون توجه") }
                item { BarListCard(behavior.contentInterest, PlayAccent) }
            }
        }

        // Registrations mini chart
        val points = state.users?.registrations?.points.orEmpty()
        if (points.any { it.value > 0 }) {
            item {
                Column {
                    SectionTitle("عضویت‌های جدید")
                    Spacer(Modifier.height(12.dp))
                    RegistrationsBars(points)
                }
            }
        }

        // Top active users
        val top = state.users?.topActiveUsers.orEmpty()
        if (top.isNotEmpty()) {
            item { SectionTitle("فعال‌ترین کاربران") }
            item {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(BgElevated),
                ) {
                    top.forEachIndexed { index, user ->
                        TopUserRow(
                            rank = index + 1,
                            username = user.username,
                            watchHours = user.watchTimeHours,
                            interactions = user.interactions,
                            plays = user.plays,
                            rooms = user.roomsHosted,
                        )
                        if (index != top.lastIndex) {
                            Box(Modifier.fillMaxWidth().height(1.dp).background(OutlineSoft))
                        }
                    }
                }
            }
        }

        // Engagement KPIs
        val engagement = state.engagement
        if (engagement != null) {
            item { SectionTitle("تماشا و تعامل") }
            item {
                val cards = engagementStatCards(engagement)
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    cards.chunked(2).forEach { pair ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { c -> StatCard(c.label, c.value, c.hint, Modifier.weight(1f)) }
                            if (pair.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }
        }

        // Top watched content
        val topWatched = state.content?.topWatched.orEmpty()
        if (topWatched.isNotEmpty()) {
            item { SectionTitle("پربازدیدترین‌ها") }
            item {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(BgElevated),
                ) {
                    topWatched.forEachIndexed { index, row ->
                        TopContentRow(rank = index + 1, item = row)
                        if (index != topWatched.lastIndex) {
                            Box(Modifier.fillMaxWidth().height(1.dp).background(OutlineSoft))
                        }
                    }
                }
            }
        }

        // Search terms
        val terms = engagement?.searchTerms.orEmpty().filter { it.term.isNotBlank() }.take(12)
        if (terms.isNotEmpty()) {
            item { SectionTitle("جستجوهای پرتکرار") }
            item { SearchTermsFlow(terms) }
        }

        item { Spacer(Modifier.height(8.dp)) }
    }
}

private fun engagementStatCards(e: AnalyticsEngagementDto): List<StatCardData> = listOf(
    StatCardData("میانگین نشست", "${e.averageSessionMinutes.fa()} دقیقه", "${e.plays.fa()} پخش"),
    StatCardData("نرخ تکمیل", e.completionRate?.let { "${it.fa()}٪" } ?: "—", "${e.completes.fa()} تکمیل"),
    StatCardData("اتاق واچ‌پارتی", e.watchRooms.fa(), "در این بازه"),
    StatCardData("لایک‌ها", e.likesTotal.fa(), "${e.likesInPeriod.fa()} در بازه"),
    StatCardData("امتیازها", e.ratingsTotal.fa(), e.averageRating?.let { "میانگین ${it.fa()}" } ?: null),
    StatCardData("واچ‌لیست", e.watchlistTotal.fa(), "${e.watchlistInPeriod.fa()} در بازه"),
)

@Composable
private fun TopContentRow(rank: Int, item: AnalyticsTopContentDto) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(28.dp).clip(CircleShape).background(SurfaceHover),
            contentAlignment = Alignment.Center,
        ) {
            Text(rank.fa(), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = BrandMint)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                item.title.ifBlank { "بدون عنوان" },
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                if (item.contentType == "series") "سریال" else "فیلم",
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
            )
        }
        Spacer(Modifier.width(8.dp))
        Column(horizontalAlignment = Alignment.End) {
            Text(item.activity.fa(), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Black, color = BrandMint)
            Text("فعالیت", style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
    }
}

@Composable
private fun SearchTermsFlow(terms: List<AnalyticsSearchTermDto>) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        terms.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                pair.forEach { term ->
                    Row(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(10.dp))
                            .background(SurfaceHover)
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            term.term,
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(term.count.fa(), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Black, color = BrandMint)
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

private data class StatCardData(val label: String, val value: String, val hint: String?)

private fun userStatCards(t: AnalyticsUserTotalsDto): List<StatCardData> = listOf(
    StatCardData("کل کاربران", t.users.fa(), "${t.verified.fa()} تأییدشده"),
    StatCardData("فعال روزانه (DAU)", t.dau.fa(), "چسبندگی ${t.stickiness.fa()}٪"),
    StatCardData("فعال هفتگی (WAU)", t.wau.fa(), "${t.mau.fa()} فعال ماهانه"),
    StatCardData("عضویت امروز", t.newToday.fa(), "${t.newInPeriod.fa()} در بازه"),
    StatCardData("بازگشتی در بازه", t.returningInPeriod.fa(), "${t.activeInPeriod.fa()} فعال"),
    StatCardData("نرخ تأیید ایمیل", "${t.verifiedRate.fa()}٪", "${t.unverified.fa()} تأییدنشده"),
)

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black, color = TextPrimary)
}

@Composable
private fun CenterBox(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) { content() }
}

@Composable
private fun RealtimePill(label: String, value: Int, modifier: Modifier = Modifier, live: Boolean = false) {
    Column(
        modifier
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (live) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(PlayAccent))
                Spacer(Modifier.width(6.dp))
            }
            Text(value.fa(), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black, color = TextPrimary)
        }
        Spacer(Modifier.height(2.dp))
        Text(label, style = MaterialTheme.typography.labelMedium, color = TextMuted)
    }
}

@Composable
private fun KpiCard(kpi: AnalyticsKpiDto, modifier: Modifier = Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text(
                formatKpiValue(kpi),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Black,
                color = TextPrimary,
                modifier = Modifier.weight(1f),
            )
            kpi.deltaPercent?.let { DeltaBadge(it) }
        }
        Spacer(Modifier.height(4.dp))
        Text(kpi.label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = TextSecondary)
        kpi.hint?.takeIf { it.isNotBlank() }?.let {
            Spacer(Modifier.height(2.dp))
            Text(it, style = MaterialTheme.typography.labelSmall, color = TextMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun DeltaBadge(delta: Double) {
    val up = delta >= 0
    val color = if (up) PlayAccent else ErrorRed
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(color.copy(alpha = 0.14f))
            .padding(horizontal = 7.dp, vertical = 3.dp),
    ) {
        Icon(
            if (up) Icons.Rounded.KeyboardArrowUp else Icons.Rounded.ArrowDropDown,
            contentDescription = null,
            tint = color,
            modifier = Modifier.size(14.dp),
        )
        Text(
            "${kotlin.math.abs(delta).fa()}٪",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = color,
        )
    }
}

@Composable
private fun StatCard(label: String, value: String, hint: String?, modifier: Modifier = Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
    ) {
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black, color = TextPrimary)
        Spacer(Modifier.height(4.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = TextSecondary)
        hint?.takeIf { it.isNotBlank() }?.let {
            Spacer(Modifier.height(2.dp))
            Text(it, style = MaterialTheme.typography.labelSmall, color = TextMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun RegistrationsBars(points: List<AnalyticsSeriesPointDto>) {
    val recent = points.takeLast(14)
    val max = (recent.maxOfOrNull { it.value } ?: 0).coerceAtLeast(1)
    val total = recent.sumOf { it.value }
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
    ) {
        Row(
            Modifier.fillMaxWidth().height(120.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            recent.forEach { point ->
                val fraction = point.value.toFloat() / max.toFloat()
                Box(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight(fraction.coerceIn(0.02f, 1f))
                        .clip(RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp))
                        .background(if (point.value > 0) BrandMint else SurfaceHover),
                )
            }
        }
        Spacer(Modifier.height(10.dp))
        Text(
            "مجموع ${total.fa()} عضویت در ${recent.size.fa()} روز اخیر",
            style = MaterialTheme.typography.labelMedium,
            color = TextMuted,
        )
    }
}

@Composable
private fun TopUserRow(
    rank: Int,
    username: String,
    watchHours: Double,
    interactions: Int,
    plays: Int,
    rooms: Int,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(28.dp).clip(CircleShape).background(SurfaceHover),
            contentAlignment = Alignment.Center,
        ) {
            Text(rank.fa(), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = BrandMint)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                username.ifBlank { "کاربر" },
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                "$interactions تعامل · $plays پخش" + if (rooms > 0) " · $rooms واچ‌پارتی" else "",
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
            )
        }
        Spacer(Modifier.width(8.dp))
        Column(horizontalAlignment = Alignment.End) {
            Text("${watchHours.fa()} س", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Black, color = BrandMint)
            Text("تماشا", style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
    }
}

private val funnelPalette = listOf(AccentBlue, BrandMint, AccentYellow, PlayAccent)

@Composable
private fun FunnelCard(stages: List<AnalyticsFunnelStageDto>) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        stages.forEachIndexed { index, stage ->
            val color = funnelPalette[index % funnelPalette.size]
            Column {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        stage.label,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary,
                        modifier = Modifier.weight(1f),
                    )
                    stage.stepConversion?.let {
                        Text(
                            "${it.fa()}٪ تبدیل",
                            style = MaterialTheme.typography.labelSmall,
                            color = TextMuted,
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(
                        stage.value.fa(),
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Black,
                        color = TextPrimary,
                    )
                }
                Spacer(Modifier.height(6.dp))
                val fraction = ((stage.pctOfTop ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f)
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(10.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .background(SurfaceHover),
                ) {
                    Box(
                        Modifier
                            .fillMaxHeight()
                            .fillMaxWidth(fraction.coerceAtLeast(0.02f))
                            .clip(RoundedCornerShape(6.dp))
                            .background(color),
                    )
                }
            }
        }
    }
}

@Composable
private fun BarListCard(items: List<AnalyticsNamedValueDto>, color: Color) {
    val max = (items.maxOfOrNull { it.value } ?: 0).coerceAtLeast(1)
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items.forEach { row ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    row.label,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.width(88.dp),
                )
                Spacer(Modifier.width(8.dp))
                Box(
                    Modifier
                        .weight(1f)
                        .height(9.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .background(SurfaceHover),
                ) {
                    val fraction = (row.value.toFloat() / max.toFloat()).coerceIn(0.02f, 1f)
                    Box(
                        Modifier
                            .fillMaxHeight()
                            .fillMaxWidth(fraction)
                            .clip(RoundedCornerShape(6.dp))
                            .background(color),
                    )
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    row.value.fa(),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Black,
                    color = TextPrimary,
                    modifier = Modifier.width(44.dp),
                    textAlign = TextAlign.End,
                )
            }
        }
    }
}

@Composable
private fun RetentionCard(r: AnalyticsRetentionDto) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .padding(14.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            RetentionStat("روزانه", r.dau, Modifier.weight(1f))
            RetentionStat("هفتگی", r.wau, Modifier.weight(1f))
            RetentionStat("ماهانه", r.mau, Modifier.weight(1f))
        }
        Spacer(Modifier.height(14.dp))
        PercentBar("چسبندگی (DAU/MAU)", r.stickiness, BrandMint)
        Spacer(Modifier.height(10.dp))
        PercentBar("بازگشت هفته‌به‌هفته", r.wowRetentionRate, AccentBlue)
        if (r.wowPriorCohort > 0) {
            Spacer(Modifier.height(8.dp))
            Text(
                "${r.wowRetained.fa()} از ${r.wowPriorCohort.fa()} کاربر فعالِ هفته‌ی قبل بازگشتند",
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
            )
        }
    }
}

@Composable
private fun RetentionStat(label: String, value: Int, modifier: Modifier = Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(SurfaceHover)
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value.fa(), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black, color = TextPrimary)
        Text(label, style = MaterialTheme.typography.labelSmall, color = TextMuted)
    }
}

@Composable
private fun PercentBar(label: String, percent: Double?, color: Color) {
    Column {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = TextSecondary, modifier = Modifier.weight(1f))
            Text("${percent?.fa() ?: "—"}٪", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Black, color = TextPrimary)
        }
        Spacer(Modifier.height(5.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(RoundedCornerShape(5.dp))
                .background(SurfaceHover),
        ) {
            val fraction = ((percent ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f)
            Box(
                Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(fraction)
                    .clip(RoundedCornerShape(5.dp))
                    .background(color),
            )
        }
    }
}

private fun formatKpiValue(kpi: AnalyticsKpiDto): String = when (kpi.format) {
    "hours" -> "${kpi.value.fa()} س"
    "percent" -> "${kpi.value.fa()}٪"
    else -> kpi.value.fa()
}

/** Persian-digit formatting. Whole doubles drop the decimal; others keep one place. */
private fun Number.fa(): String {
    val raw = when (this) {
        is Double -> if (this % 1.0 == 0.0) this.toLong().toString() else String.format("%.1f", this)
        is Float -> if (this % 1.0f == 0.0f) this.toLong().toString() else String.format("%.1f", this)
        else -> this.toString()
    }
    val digits = charArrayOf('۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹')
    return buildString {
        for (ch in raw) append(if (ch in '0'..'9') digits[ch - '0'] else ch)
    }
}
