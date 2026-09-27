package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.AnalyticsBehaviorDto
import com.revayato.app.data.model.AnalyticsContentDto
import com.revayato.app.data.model.AnalyticsEngagementDto
import com.revayato.app.data.model.AnalyticsOverviewDto
import com.revayato.app.data.model.AnalyticsUsersDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/** Staff-only analytics. The backend gates these with IsStaffUser, so a
 *  non-staff caller receives 403 → [ApiResult.Error] with code 403. */
@Singleton
class AnalyticsRepository @Inject constructor(
    private val api: ApiService,
) {
    suspend fun overview(period: String = "30d"): ApiResult<AnalyticsOverviewDto> =
        safeApiCall { api.analyticsOverview(period).data }

    suspend fun users(period: String = "30d"): ApiResult<AnalyticsUsersDto> =
        safeApiCall { api.analyticsUsers(period).data }

    suspend fun content(period: String = "30d"): ApiResult<AnalyticsContentDto> =
        safeApiCall { api.analyticsContentTop(period).data }

    suspend fun engagement(period: String = "30d"): ApiResult<AnalyticsEngagementDto> =
        safeApiCall { api.analyticsEngagement(period).data }

    suspend fun behavior(period: String = "30d"): ApiResult<AnalyticsBehaviorDto> =
        safeApiCall { api.analyticsBehavior(period).data }
}
