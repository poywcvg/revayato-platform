package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.AppReleaseDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Asks the backend what the newest published Android build is. The app is
 * sideloaded from revayato.com/downloads/, so Play never tells us — see
 * `config/app_release.py` on the backend for the manifest this reads.
 */
@Singleton
class AppUpdateRepository @Inject constructor(
    private val api: ApiService,
) {
    /** Sending our own build lets the server decide whether the update is required. */
    suspend fun latest(installedVersionCode: Int): ApiResult<AppReleaseDto> =
        safeApiCall { api.appVersion(installedVersionCode) }
}
