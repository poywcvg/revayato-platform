package com.revayato.app.feature.player

import android.media.MediaCodecList
import android.media.MediaFormat

/**
 * Codec-compatibility helpers for the online player.
 *
 * Many catalog mirrors are **x265 / HEVC / 10-bit** (providers list the x265
 * 1080p encode as the "best" quality, so a pure resolution sort makes it the
 * default). A large slice of Android phones — budget chips, older SoCs — have
 * **no hardware HEVC/AV1 decoder**, so ExoPlayer's `MediaCodecVideoRenderer`
 * fails to initialise the decoder and playback dies with a decoder error while
 * the picture reloads/buffers. This is the root of the field report
 * «خیلی از فیلم‌ها روی بعضی گوشی‌ها پخش نمی‌شه» ("many films don't play on some
 * phones").
 *
 * The web player already avoids this with `utils/downloadMeta.ts`
 * (`videoCodecFamily` + browser codec probing). This is a faithful Kotlin port:
 * the codec family is read from the provider filename/quality tokens (the only
 * signal available before load), and device decode support is probed once via
 * [MediaCodecList] so a HEVC-capable phone is *not* penalised.
 */
enum class VideoCodecFamily { HEVC, AV1, H264, UNKNOWN }

/** Read the codec family from a source URL + quality/label tokens. */
fun videoCodecFamily(url: String?, quality: String? = null, label: String? = null): VideoCodecFamily {
    val blob = "${url.orEmpty()} ${quality.orEmpty()} ${label.orEmpty()}".lowercase()
    if (Regex("(dolby[\\s._-]*vision|dovi|\\bdvhe\\b|\\bdvh1\\b)").containsMatchIn(blob)) return VideoCodecFamily.HEVC
    if (Regex("(\\bx265\\b|\\bh265\\b|\\bhevc\\b|\\bhev1\\b|\\bhvc1\\b)").containsMatchIn(blob)) return VideoCodecFamily.HEVC
    if (Regex("(\\bav1\\b|\\bav01\\b)").containsMatchIn(blob)) return VideoCodecFamily.AV1
    if (Regex("(\\bx264\\b|\\bh264\\b|\\bavc1\\b|\\bavc\\b)").containsMatchIn(blob)) return VideoCodecFamily.H264
    // Standalone 10-bit encodes are virtually always HEVC in these providers.
    if (Regex("\\b10[\\s._-]?bit\\b").containsMatchIn(blob)) return VideoCodecFamily.HEVC
    return VideoCodecFamily.UNKNOWN
}

/** Device decode-capability probe (cached): does this phone have a HEVC/AV1 decoder? */
object DeviceCodecSupport {
    private val hevc: Boolean by lazy { hasDecoder(MediaFormat.MIMETYPE_VIDEO_HEVC) }
    private val av1: Boolean by lazy { hasDecoder("video/av01") }

    fun supportsHevc(): Boolean = hevc
    fun supportsAv1(): Boolean = av1

    private fun hasDecoder(mime: String): Boolean = runCatching {
        val codecs = MediaCodecList(MediaCodecList.REGULAR_CODECS)
        codecs.codecInfos.any { info ->
            !info.isEncoder && info.supportedTypes.any { it.equals(mime, ignoreCase = true) }
        }
    }.getOrDefault(false)
}

/**
 * True when this source's codec is unlikely to decode on *this* device — an HEVC
 * file on a phone with no HEVC decoder, or an AV1 file with no AV1 decoder. Such
 * a source should never be the auto-play default when a compatible mirror
 * exists, and on a decoder error the player should fall back off it.
 */
fun codecLikelyUnsupported(url: String?, quality: String? = null, label: String? = null): Boolean =
    when (videoCodecFamily(url, quality, label)) {
        VideoCodecFamily.HEVC -> !DeviceCodecSupport.supportsHevc()
        VideoCodecFamily.AV1 -> !DeviceCodecSupport.supportsAv1()
        else -> false
    }

/**
 * Compatibility rank for ordering candidate mirrors on *this* device: higher is
 * safer to start on. H.264 is universally decodable; a codec this device can't
 * decode is pushed to the bottom. Resolution is a secondary sort applied by the
 * caller — compatibility wins so the default source actually plays.
 */
fun deviceCodecRank(url: String?, quality: String? = null, label: String? = null): Int =
    when (videoCodecFamily(url, quality, label)) {
        VideoCodecFamily.H264 -> 3
        VideoCodecFamily.UNKNOWN -> 2
        VideoCodecFamily.HEVC -> if (DeviceCodecSupport.supportsHevc()) 2 else -10
        VideoCodecFamily.AV1 -> if (DeviceCodecSupport.supportsAv1()) 2 else -10
    }
