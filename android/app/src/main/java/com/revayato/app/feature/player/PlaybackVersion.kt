package com.revayato.app.feature.player

import com.revayato.app.data.model.DownloadLinkDto

/**
 * How a playable mirror carries Persian: a Farsi dub, burned-in ("hard") subtitles,
 * toggleable soft subtitles, or the untouched original. Mirrors the web app's
 * classification (`utils/playbackVersions.ts`) so both clients group links the same
 * way. [order] drives the section order shown in the pickers.
 */
enum class PlaybackVersionKind(val title: String, val order: Int) {
    DUBBED("دوبله فارسی", 0),
    HARDSUB("زیرنویس چسبیده", 1),
    SOFTSUB("زیرنویس نرم", 2),
    ORIGINAL("نسخه اصلی", 3),
    ;

    /**
     * Lowercase token the backend's `ensure_playback_subtitles` understands for its
     * `version` field, so it can select the correct softsub/hardsub lane.
     */
    val backendToken: String
        get() = when (this) {
            DUBBED -> "dubbed"
            HARDSUB -> "hardsub"
            SOFTSUB -> "softsub"
            ORIGINAL -> "original"
        }
}

/** One selectable mirror: a concrete URL at a given quality, tagged with its version. */
data class PlaybackOption(
    val url: String,
    val qualityLabel: String,
    val kind: PlaybackVersionKind,
    val sizeLabel: String = "",
)

/** A version section (e.g. «دوبله فارسی») holding its quality mirrors, best first. */
data class PlaybackGroup(
    val kind: PlaybackVersionKind,
    val options: List<PlaybackOption>,
)

/** Lowercased blob of the fields that hint at a link's version. */
private fun DownloadLinkDto.versionBlob(): String =
    "${kind.orEmpty()} ${label} ${subtitleType.orEmpty()} ${url}".lowercase()

/** Classify a single download/stream link into its Persian playback version. */
fun classifyPlaybackVersion(link: DownloadLinkDto): PlaybackVersionKind {
    val kind = link.kind.orEmpty().lowercase()
    val subtitleType = link.subtitleType.orEmpty().lowercase()
    val blob = link.versionBlob()

    if (kind in setOf("dubbed", "dub", "persian_dub", "farsi_dub") ||
        Regex("(dubbed|\\bdub\\b|دوبله)").containsMatchIn(blob)
    ) {
        return PlaybackVersionKind.DUBBED
    }
    if (kind in setOf("hardsub", "hard-sub", "hard_sub") ||
        subtitleType.contains("hard") ||
        Regex("(hardsub|hard[-_ ]?sub|هاردساب|چسبیده)").containsMatchIn(blob)
    ) {
        return PlaybackVersionKind.HARDSUB
    }
    if (kind in setOf("softsub", "soft-sub", "soft_sub", "subtitle", "sub") ||
        subtitleType.contains("soft") ||
        subtitleType.isNotBlank() ||
        Regex("(softsub|soft[-_ ]?sub|سافت|زیرنویس\\s*نرم|farsi[\\s._-]*sub|fa[\\s._-]*sub)").containsMatchIn(blob)
    ) {
        return PlaybackVersionKind.SOFTSUB
    }
    return PlaybackVersionKind.ORIGINAL
}

/** Numeric resolution rank of a quality label so higher resolutions sort first. */
private fun resolutionRank(label: String): Int =
    Regex("(\\d{3,4})\\s*p", RegexOption.IGNORE_CASE).find(label)?.groupValues?.get(1)?.toIntOrNull() ?: 0

/** True for sidecar/subtitle/playlist URLs that are not standalone video mirrors. */
private fun DownloadLinkDto.isNonVideo(): Boolean {
    if (!subtitleType.isNullOrBlank()) {
        // A soft-sub *video* encode is fine; only bare subtitle files are dropped.
    }
    val path = url.substringBefore('?')
    return path.endsWith(".vtt", true) || path.endsWith(".srt", true) ||
        path.endsWith(".ass", true) || path.endsWith(".ssa", true) ||
        path.endsWith(".m3u8", true)
}

/**
 * Group a title's (or episode's) download/stream links into version sections, each
 * holding de-duplicated quality mirrors sorted best-first. Subtitle sidecar files
 * and HLS playlists are excluded — these are downloadable/streamable video mirrors.
 */
fun groupPlaybackLinks(links: List<DownloadLinkDto>): List<PlaybackGroup> {
    val options = links
        .asSequence()
        .filter { it.url.isNotBlank() }
        .filterNot { it.kind.equals("subtitle", ignoreCase = true) && it.subtitleType.isNullOrBlank() && it.isNonVideo() }
        .filterNot { it.isNonVideo() }
        .map { link ->
            val quality = link.quality.ifBlank { link.label.ifBlank { link.sizeLabel.ifBlank { "کیفیت" } } }
            PlaybackOption(
                url = link.url,
                qualityLabel = quality,
                kind = classifyPlaybackVersion(link),
                sizeLabel = link.sizeLabel,
            )
        }
        .distinctBy { it.url }
        .toList()

    return options
        .groupBy { it.kind }
        .map { (kind, opts) ->
            PlaybackGroup(kind, opts.sortedByDescending { resolutionRank(it.qualityLabel) })
        }
        .sortedBy { it.kind.order }
}
