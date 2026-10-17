package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.EngagementEventRequest
import com.revayato.app.data.model.RateRequest
import com.revayato.app.data.model.RatingDto
import com.revayato.app.data.model.RatingSummaryDto
import com.revayato.app.data.model.SupportTicketDto
import com.revayato.app.data.model.SupportTicketRequest
import com.revayato.app.data.model.ToggleRequest
import com.revayato.app.data.model.WatchlistItemDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class EngagementRepository @Inject constructor(
    private val api: ApiService,
) {
    suspend fun watchlist(): ApiResult<List<WatchlistItemDto>> = safeApiCall { api.watchlist() }

    suspend fun likes(): ApiResult<List<WatchlistItemDto>> = safeApiCall { api.likes() }

    suspend fun toggleWatchlist(contentType: String, objectId: Int): ApiResult<Boolean> =
        safeApiCall { api.toggleWatchlist(ToggleRequest(contentType, objectId)).isOn }

    suspend fun toggleLike(contentType: String, objectId: Int): ApiResult<Boolean> =
        safeApiCall { api.toggleLike(ToggleRequest(contentType, objectId)).isOn }

    suspend fun rate(
        contentType: String,
        objectId: Int,
        score: Double,
        review: String? = null,
        isSpoiler: Boolean? = null,
    ): ApiResult<RatingDto> =
        safeApiCall { api.rate(RateRequest(contentType, objectId, score, review, isSpoiler)) }

    /** Aggregate site rating + user reviews for a title (comments & ratings panel). */
    suspend fun ratingSummary(contentType: String, objectId: Int): ApiResult<RatingSummaryDto> =
        safeApiCall { api.ratingSummary(contentType, objectId) }

    /**
     * Legacy fallback for a detail-screen problem report: a free-text "bug"
     * support ticket so it reaches the admin support inbox; returns the tracking
     * code so the user can be told their report was recorded. Prefer the
     * structured `CatalogRepository.reportContentIssue` path (auto-remediated);
     * this stays only for when that intake is unreachable.
     * `reason` must be at least 10 characters (enforced server-side too).
     */
    suspend fun reportProblem(
        title: String,
        year: Int?,
        url: String,
        reason: String,
    ): ApiResult<SupportTicketDto> = safeApiCall {
        api.createSupportTicket(
            SupportTicketRequest(
                category = "bug",
                subject = "گزارش خطا: ${title.take(160)}",
                body = reason,
                relatedTitle = title.take(255),
                relatedYear = year,
                relatedUrl = url,
            ),
        )
    }

    /**
     * Fire-and-forget download telemetry. Emitted when the user enqueues a
     * download so the staff downloads dashboard sees real Android demand
     * (platform = "android") alongside web clicks. Failures are swallowed —
     * telemetry must never block a download.
     */
    suspend fun trackDownload(
        titleId: Int,
        slug: String,
        contentType: String,
        quality: String,
        sourcePage: String,
    ) {
        runCatching {
            api.sendEvent(
                EngagementEventRequest(
                    eventType = "download",
                    sourcePage = sourcePage,
                    titleId = titleId,
                    titleSlug = slug,
                    contentType = contentType,
                    quality = quality.ifBlank { null },
                    platform = "android",
                ),
            )
        }
    }

    /** Fire-and-forget playback progress telemetry; failures are swallowed. */
    suspend fun reportProgress(
        titleId: Int,
        slug: String,
        contentType: String,
        progressPercent: Double,
        sourcePage: String,
    ) {
        runCatching {
            api.sendEvent(
                EngagementEventRequest(
                    eventType = "progress",
                    sourcePage = sourcePage,
                    titleId = titleId,
                    titleSlug = slug,
                    contentType = contentType,
                    progressPercent = progressPercent.coerceIn(0.0, 100.0),
                ),
            )
        }
    }
}
