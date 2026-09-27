package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.CollectionCreateRequest
import com.revayato.app.data.model.CollectionItemMutationDto
import com.revayato.app.data.model.CollectionItemRequest
import com.revayato.app.data.model.CollectionPickRowDto
import com.revayato.app.data.model.PublicProfileDto
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/**
 * User collections ("کالکشن") + public profiles. All data is real and DB-backed;
 * the repository is a thin, localized wrapper over [ApiService].
 */
@Singleton
class CollectionsRepository @Inject constructor(
    private val api: ApiService,
) {
    // ---- Owner ----
    suspend fun myCollections(): ApiResult<List<UserCollectionDto>> =
        safeApiCall { api.myCollections() }

    suspend fun myCollectionDetail(slug: String): ApiResult<UserCollectionDto> =
        safeApiCall { api.myCollectionDetail(slug) }

    suspend fun create(
        title: String,
        description: String = "",
        visibility: String,
        accent: String = "",
    ): ApiResult<UserCollectionDto> = safeApiCall {
        api.createCollection(CollectionCreateRequest(title.trim(), description.trim(), visibility, accent))
    }

    suspend fun update(
        slug: String,
        title: String,
        description: String,
        visibility: String,
        accent: String = "",
    ): ApiResult<UserCollectionDto> = safeApiCall {
        api.updateCollection(slug, CollectionCreateRequest(title.trim(), description.trim(), visibility, accent))
    }

    suspend fun delete(slug: String): ApiResult<Unit> =
        safeApiCall { api.deleteCollection(slug); Unit }

    // ---- Items ----
    suspend fun addItem(
        slug: String,
        contentType: String,
        objectId: Int,
        note: String = "",
    ): ApiResult<CollectionItemMutationDto> =
        safeApiCall { api.addCollectionItem(slug, CollectionItemRequest(contentType, objectId, note)) }

    suspend fun removeItem(
        slug: String,
        contentType: String,
        objectId: Int,
    ): ApiResult<CollectionItemMutationDto> =
        safeApiCall { api.removeCollectionItem(slug, CollectionItemRequest(contentType, objectId)) }

    /** Rows for the «افزودن به کالکشن» picker, each flagged whether it already holds the title. */
    suspend fun containing(contentType: String, objectId: Int): ApiResult<List<CollectionPickRowDto>> =
        safeApiCall { api.collectionsContaining(contentType, objectId) }

    // ---- Public reads ----
    suspend fun sharedCollection(token: String): ApiResult<UserCollectionDto> =
        safeApiCall { api.sharedCollection(token) }

    suspend fun publicCollection(username: String, slug: String): ApiResult<UserCollectionDto> =
        safeApiCall { api.publicCollection(username, slug) }

    suspend fun publicProfile(username: String): ApiResult<PublicProfileDto> =
        safeApiCall { api.publicProfile(username) }
}
