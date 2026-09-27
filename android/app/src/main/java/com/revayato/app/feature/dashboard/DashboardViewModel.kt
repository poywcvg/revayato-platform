package com.revayato.app.feature.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.model.AnalyticsBehaviorDto
import com.revayato.app.data.model.AnalyticsContentDto
import com.revayato.app.data.model.AnalyticsEngagementDto
import com.revayato.app.data.model.AnalyticsOverviewDto
import com.revayato.app.data.model.AnalyticsUsersDto
import com.revayato.app.data.repository.AnalyticsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Report periods offered by the backend (ALLOWED_DAYS = 7/30/90). */
enum class DashboardPeriod(val key: String, val label: String) {
    WEEK("7d", "۷ روز"),
    MONTH("30d", "۳۰ روز"),
    QUARTER("90d", "۹۰ روز"),
}

data class DashboardState(
    val loading: Boolean = false,
    val refreshing: Boolean = false,
    val period: DashboardPeriod = DashboardPeriod.MONTH,
    val overview: AnalyticsOverviewDto? = null,
    val users: AnalyticsUsersDto? = null,
    val content: AnalyticsContentDto? = null,
    val engagement: AnalyticsEngagementDto? = null,
    val behavior: AnalyticsBehaviorDto? = null,
    val error: String? = null,
    /** True when the backend returned 403 — the account is not staff. */
    val forbidden: Boolean = false,
)

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val analytics: AnalyticsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DashboardState())
    val state: StateFlow<DashboardState> = _state.asStateFlow()

    fun load(refresh: Boolean = false) {
        val hasData = _state.value.overview != null
        _state.update { it.copy(loading = !hasData, refreshing = hasData && refresh, error = null) }
        val period = _state.value.period.key
        viewModelScope.launch {
            val overviewDeferred = async { analytics.overview(period) }
            val usersDeferred = async { analytics.users(period) }
            val contentDeferred = async { analytics.content(period) }
            val engagementDeferred = async { analytics.engagement(period) }
            val behaviorDeferred = async { analytics.behavior(period) }
            val overviewResult = overviewDeferred.await()
            val usersResult = usersDeferred.await()
            val contentResult = contentDeferred.await()
            val engagementResult = engagementDeferred.await()
            val behaviorResult = behaviorDeferred.await()

            val error = (overviewResult as? ApiResult.Error)
                ?: (usersResult as? ApiResult.Error)
                ?: (contentResult as? ApiResult.Error)
                ?: (engagementResult as? ApiResult.Error)
                ?: (behaviorResult as? ApiResult.Error)
            val forbidden = error?.code == 403
            _state.update { current ->
                val newOverview = (overviewResult as? ApiResult.Success)?.data ?: current.overview
                val newUsers = (usersResult as? ApiResult.Success)?.data ?: current.users
                val newContent = (contentResult as? ApiResult.Success)?.data ?: current.content
                val newEngagement = (engagementResult as? ApiResult.Success)?.data ?: current.engagement
                val newBehavior = (behaviorResult as? ApiResult.Success)?.data ?: current.behavior
                val hasAny = newOverview != null || newUsers != null || newContent != null ||
                    newEngagement != null || newBehavior != null
                current.copy(
                    loading = false,
                    refreshing = false,
                    overview = newOverview,
                    users = newUsers,
                    content = newContent,
                    engagement = newEngagement,
                    behavior = newBehavior,
                    // Only surface a blocking error when we have nothing to show.
                    error = if (!hasAny) error?.message else null,
                    forbidden = forbidden,
                )
            }
        }
    }

    fun setPeriod(period: DashboardPeriod) {
        if (_state.value.period == period) return
        _state.update { it.copy(period = period) }
        load(refresh = true)
    }
}
