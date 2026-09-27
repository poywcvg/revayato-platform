package com.revayato.app.feature.player

import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.data.model.SubtitleTrackDto

/** Everything the player needs, threaded through the navigation route. */
data class PlayerArgs(
    val contentType: String,
    val id: Int,
    val slug: String,
    val title: String,
    val url: String,
    val startPositionMs: Long,
    val episodeId: Int,
    val subtitlesEncoded: String,
    val qualitiesEncoded: String = "",
) {
    val subtitles: List<PlayerSubtitle> get() = decodeSubtitles(subtitlesEncoded)

    /** Selectable online-playback renditions (different quality mirrors). */
    val qualities: List<PlayerQuality> get() = decodeQualities(qualitiesEncoded, url)

    /** True for a network stream (as opposed to a local offline file:// URI). */
    val isRemote: Boolean get() = url.startsWith("http", ignoreCase = true)
}

data class PlayerSubtitle(
    val label: String,
    val url: String,
    val language: String = "fa",
)

/** One selectable online quality rendition (e.g. "1080p" → mp4 URL). */
data class PlayerQuality(
    val label: String,
    val url: String,
)

/** A selectable embedded audio track (language), for the "صدا" picker. */
data class PlayerAudioTrack(
    val label: String,
    // Ordinal among the media's audio groups + the track inside it, used to
    // rebuild a Media3 TrackSelectionOverride when the viewer switches audio.
    val groupOrdinal: Int,
    val trackIndex: Int,
)

/** A single episode as shown in the in-player episode switcher. */
data class PlayerEpisode(
    val id: Int,
    val seasonNumber: Int,
    val episodeNumber: Int,
    val title: String,
    val poster: String?,
    val playable: Boolean,
)

/** A season grouping for the in-player episode switcher. */
data class PlayerSeason(
    val seasonNumber: Int,
    val title: String,
    val episodes: List<PlayerEpisode>,
)

private const val TRACK_SEP = ";;"
private const val FIELD_SEP = "|"

/** Encode subtitle tracks into a single route-safe string: `label|url|lang;;…`. */
fun encodeSubtitles(tracks: List<SubtitleTrackDto>): String =
    tracks
        .filter { it.src.isNotBlank() || !it.sourceUrl.isNullOrBlank() }
        .joinToString(TRACK_SEP) { t ->
            val url = (t.src.ifBlank { t.sourceUrl.orEmpty() })
            val label = t.label.ifBlank { t.language.ifBlank { "زیرنویس" } }
            val lang = t.language.ifBlank { "fa" }
            listOf(label, url, lang).joinToString(FIELD_SEP) { it.replace(FIELD_SEP, " ").replace(TRACK_SEP, " ") }
        }

/** Encode already-resolved [PlayerSubtitle]s the same way [encodeSubtitles] does. */
fun encodePlayerSubtitles(subtitles: List<PlayerSubtitle>): String =
    subtitles
        .filter { it.url.isNotBlank() }
        .joinToString(TRACK_SEP) { s ->
            listOf(s.label.ifBlank { "زیرنویس" }, s.url, s.language.ifBlank { "fa" })
                .joinToString(FIELD_SEP) { it.replace(FIELD_SEP, " ").replace(TRACK_SEP, " ") }
        }

fun decodeSubtitles(encoded: String): List<PlayerSubtitle> {
    if (encoded.isBlank()) return emptyList()
    return encoded.split(TRACK_SEP).mapNotNull { chunk ->
        val parts = chunk.split(FIELD_SEP)
        if (parts.size >= 2 && parts[1].isNotBlank()) {
            PlayerSubtitle(
                label = parts[0].ifBlank { "زیرنویس" },
                url = parts[1],
                language = parts.getOrNull(2)?.ifBlank { "fa" } ?: "fa",
            )
        } else {
            null
        }
    }
}

/**
 * Build the selectable online-quality list from a title's download/stream links,
 * newest-friendly first: real video mirrors only (subtitles/playlists dropped),
 * de-duplicated by URL, labelled by their quality tag (e.g. "1080p").
 */
fun buildQualitiesFromLinks(links: List<DownloadLinkDto>): List<PlayerQuality> =
    links
        .asSequence()
        .filter { it.url.isNotBlank() }
        .filter { it.subtitleType.isNullOrBlank() && !it.kind.equals("subtitle", ignoreCase = true) }
        .filterNot { link ->
            val path = link.url.substringBefore('?')
            path.endsWith(".vtt", true) || path.endsWith(".srt", true) ||
                path.endsWith(".ass", true) || path.endsWith(".ssa", true) ||
                path.endsWith(".m3u8", true)
        }
        .map { link ->
            val label = link.quality.ifBlank { link.label.ifBlank { link.sizeLabel.ifBlank { "کیفیت" } } }
            PlayerQuality(label = label, url = link.url)
        }
        .distinctBy { it.url }
        .sortedByDescending { qualityRank(it.label) }
        .toList()

/** Rough numeric rank of a quality label so higher resolutions sort first. */
private fun qualityRank(label: String): Int =
    Regex("(\\d{3,4})\\s*p", RegexOption.IGNORE_CASE).find(label)?.groupValues?.get(1)?.toIntOrNull() ?: 0

/** Encode selectable quality renditions into a route-safe string: `label|url;;…`. */
fun encodeQualities(qualities: List<PlayerQuality>): String =
    qualities
        .filter { it.url.isNotBlank() }
        .joinToString(TRACK_SEP) { q ->
            val label = q.label.ifBlank { "کیفیت" }
            listOf(label, q.url).joinToString(FIELD_SEP) { it.replace(FIELD_SEP, " ").replace(TRACK_SEP, " ") }
        }

/**
 * Decode quality renditions, guaranteeing the currently-playing [currentUrl] is
 * present and de-duplicated so the quality menu always reflects what's on screen.
 */
fun decodeQualities(encoded: String, currentUrl: String = ""): List<PlayerQuality> {
    val decoded = if (encoded.isBlank()) {
        emptyList()
    } else {
        encoded.split(TRACK_SEP).mapNotNull { chunk ->
            val parts = chunk.split(FIELD_SEP)
            if (parts.size >= 2 && parts[1].isNotBlank()) {
                PlayerQuality(label = parts[0].ifBlank { "کیفیت" }, url = parts[1])
            } else {
                null
            }
        }
    }
    // Guarantee the on-screen source is always selectable, even if the detail
    // screen didn't include it among the alternates.
    val withCurrent = if (currentUrl.isNotBlank() && decoded.none { it.url == currentUrl }) {
        listOf(PlayerQuality(label = "پیش‌فرض", url = currentUrl)) + decoded
    } else {
        decoded
    }
    return withCurrent.distinctBy { it.url }
}
