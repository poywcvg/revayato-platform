package com.revayato.app.feature.detail

/**
 * Map the detail-screen free-text «گزارش خطا» onto the structured 12-value
 * server catalogue (`apps/catalog/report_catalog.py`) so a report filed outside
 * the player still rides the same auto-remediation engine as the web / player
 * reports instead of landing as an unactionable free-text ticket.
 *
 * Order matters: check the most specific signals first (download, subtitle sync
 * vs missing, audio desync vs silent) and fall back to `other` — the server
 * normalizes unknown values to `other` anyway.
 */
fun inferStructuredProblemType(reason: String, isSeries: Boolean = false): String {
    val text = reason.trim()
    if (text.isEmpty()) return "other"
    // Download links are their own repair lane.
    if (text.contains("دانلود") || text.contains("download", ignoreCase = true)) return "download_dead"
    // Subtitles: missing vs out-of-sync vs garbled are three different repairs.
    val mentionsSubtitle = text.contains("زیرنویس") || text.contains("subtitle", ignoreCase = true) ||
        text.contains("ساب") || text.contains("caption", ignoreCase = true)
    if (mentionsSubtitle) {
        if (text.contains("هماهنگ") || text.contains("عقب") || text.contains("جلو") ||
            text.contains("سینک") || text.contains("sync", ignoreCase = true) ||
            text.contains("تاخیر") || text.contains("تأخیر")
        ) return "subtitle_sync"
        if (text.contains("خراب") || text.contains("به‌هم") || text.contains("بهم") ||
            text.contains("نامفهوم") || text.contains("بی‌ربط") || text.contains("garbled", ignoreCase = true)
        ) return "subtitle_garbled"
        return "subtitle_missing"
    }
    // Audio: silent vs desync.
    if (text.contains("صدا") || text.contains("دوبله") || text.contains("audio", ignoreCase = true) ||
        text.contains("صوت")
    ) {
        if (text.contains("هماهنگ") || text.contains("سینک") || text.contains("sync", ignoreCase = true) ||
            text.contains("عقب") || text.contains("جلو")
        ) return "audio_desync"
        return "audio_silent"
    }
    // Playback: stalling vs not playing at all.
    if (text.contains("قطع") || text.contains("وصل") || text.contains("بافر") ||
        text.contains("buffer", ignoreCase = true) || text.contains("می‌ایستد") ||
        text.contains("گیر")
    ) return "buffering"
    if (text.contains("پخش") || text.contains("باز نمی") || text.contains("خطا") ||
        text.contains("play", ignoreCase = true) || text.contains("لود")
    ) return "playback"
    // Picture quality.
    if (text.contains("کیفیت") || text.contains("تار") || text.contains("quality", ignoreCase = true) ||
        text.contains("رزولوشن") || text.contains("نسخه")
    ) return "quality"
    // Wrong content.
    if (text.contains("قسمت") || text.contains("episode", ignoreCase = true)) {
        return if (isSeries) "wrong_episode" else "wrong_title"
    }
    if (text.contains("عنوان") || text.contains("اشتباه") || text.contains("فرق") ||
        text.contains("اطلاعات") || text.contains("اسم") || text.contains("wrong", ignoreCase = true)
    ) return "wrong_title"
    return "other"
}
