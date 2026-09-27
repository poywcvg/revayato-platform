package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The newest published build, as described by `GET api/app/version/`.
 *
 * Revayato is sideloaded from revayato.com/downloads/, never installed from
 * Google Play, so Play's In-App Updates API has nothing to talk to — this is the
 * replacement. The backend reads its answer from a manifest that sits beside the
 * APK files themselves and refuses to describe a build whose file is missing, so
 * a non-empty [downloadUrl] is a URL that really resolves.
 *
 * [available] is "we have a published build at all"; [updateAvailable] is the
 * server's answer to *this* caller's `version_code`. [mandatory] means the
 * installed build is below the minimum the backend still supports — the sheet
 * then cannot be dismissed.
 */
@Serializable
data class AppReleaseDto(
    val available: Boolean = false,
    @SerialName("update_available") val updateAvailable: Boolean = false,
    val mandatory: Boolean = false,
    @SerialName("version_code") val versionCode: Int = 0,
    @SerialName("version_name") val versionName: String = "",
    @SerialName("min_supported_version_code") val minSupportedVersionCode: Int = 0,
    @SerialName("download_url") val downloadUrl: String = "",
    @SerialName("size_bytes") val sizeBytes: Long = 0L,
    /** Checksum of the published APK; empty when the server could not hash it. */
    val sha256: String = "",
    @SerialName("released_at") val releasedAt: String = "",
    /** Short Persian release notes, already trimmed and capped server-side. */
    val notes: List<String> = emptyList(),
)
