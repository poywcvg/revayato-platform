package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.SupportReplyRequest
import com.revayato.app.data.model.SupportTicketDetailDto
import com.revayato.app.data.model.SupportTicketDto
import com.revayato.app.data.model.SupportTicketListItemDto
import com.revayato.app.data.model.SupportTicketRequest
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The client half of the admin↔user support conversation. Powers «درخواست‌های من»
 * (list + thread + reply) and the in-app «درخواست جدید» composer. The admin half
 * lives only on the web panel — the app never touches the /admin endpoints.
 */
@Singleton
class SupportRepository @Inject constructor(
    private val api: ApiService,
) {
    /** Every ticket the signed-in user has opened, newest activity first. */
    suspend fun myTickets(): ApiResult<List<SupportTicketListItemDto>> =
        safeApiCall { api.myTickets() }

    /** One conversation, including the opening message and all replies. */
    suspend fun ticketDetail(code: String): ApiResult<SupportTicketDetailDto> =
        safeApiCall { api.ticketDetail(code) }

    /** Post a follow-up reply; returns the refreshed thread. */
    suspend fun reply(code: String, body: String): ApiResult<SupportTicketDetailDto> =
        safeApiCall { api.replyTicket(code, SupportReplyRequest(body)) }

    /**
     * Open a fresh request in the chosen [category]. `body` must be at least 10
     * characters (enforced server-side too). `relatedTitle`/`relatedYear`/
     * `relatedUrl` power the content_request automation (same contract as the
     * web /contact form) — without them a title request cannot auto-resolve.
     * Returns the tracking code so the caller can open the new conversation.
     */
    suspend fun create(
        category: String,
        subject: String,
        body: String,
        relatedTitle: String = "",
        relatedYear: Int? = null,
        relatedUrl: String = "",
    ): ApiResult<SupportTicketDto> = safeApiCall {
        api.createSupportTicket(
            SupportTicketRequest(
                category = category,
                subject = subject.take(255),
                body = body,
                relatedTitle = relatedTitle.take(255),
                relatedYear = relatedYear,
                relatedUrl = relatedUrl.take(500),
            ),
        )
    }
}
