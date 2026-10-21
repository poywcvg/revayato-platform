package com.revayato.app.core.search

import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.PersonDto
import java.text.Normalizer
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Deterministic, client-side relevance for the two search payloads.
 *
 * The server decides *which* titles are candidates; this decides the order the
 * reader actually sees. That distinction matters: the search index is shared by
 * an English-first web index and a Persian-first app, and its result order can
 * change with the query. Sorting here guarantees the same nearest-first ladder
 * for every customer and every keystroke:
 *
 *   exact title → title prefix → word prefix → phrase inside title →
 *   every query word present → typo-tolerant token match → other metadata hit
 *
 * Ties keep the server's original order, so we never make an arbitrary reshuffle
 * out of equally relevant results.
 */
object SearchRanker {
    private val combiningMarks = Regex("\\p{M}+")
    private val nonWord = Regex("[^\\p{L}\\p{N} ]+")
    private val whitespace = Regex("\\s+")
    private val zeroWidth = Regex("[\\u200B-\\u200F\\uFEFF]")
    private val persianDigits = "۰۱۲۳۴۵۶۷۸۹"
    private val arabicDigits = "٠١٢٣٤٥٦٧٨٩"
    private val searchIntentWords = setOf("دانلود", "فیلم", "سریال", "تماشا", "آنلاین", "خرید")

    fun rankTitles(query: String, items: List<CatalogCardDto>): List<CatalogCardDto> {
        val q = normalize(query)
        if (q.isBlank() || items.size < 2) return items
        return items
            .mapIndexed { index, item ->
                Ranked(item, scoreTitle(q, item), index)
            }
            .sortedWith(
                compareByDescending<Ranked<CatalogCardDto>> { it.score }
                    .thenBy { it.index },
            )
            .map { it.item }
    }

    fun rankPeople(query: String, people: List<PersonDto>): List<PersonDto> {
        val q = normalize(query)
        if (q.isBlank() || people.size < 2) return people
        return people
            .mapIndexed { index, person ->
                Ranked(person, scoreText(q, listOf(person.name to 120)), index)
            }
            .sortedWith(
                compareByDescending<Ranked<PersonDto>> { it.score }
                    .thenBy { it.index },
            )
            .map { it.item }
    }

    private data class Ranked<T>(val item: T, val score: Int, val index: Int)

    private fun scoreTitle(query: String, item: CatalogCardDto): Int {
        val stripped = stripIntent(query)
        val fields = listOfNotNull(
            item.title.takeIf { it.isNotBlank() }?.let { it to 120 },
            item.secondaryTitle?.takeIf { it.isNotBlank() }?.let { it to 100 },
            item.originalTitle?.takeIf { it.isNotBlank() }?.let { it to 96 },
            item.englishTitle.takeIf { it.isNotBlank() && it != item.title }?.let { it to 90 },
        ).distinctBy { normalize(it.first) }
        if (fields.isEmpty()) return 0

        val withOriginal = scoreText(query, fields)
        if (stripped == query || stripped.isBlank()) return withOriginal
        // «دانلود فیلم …» should find the title exactly as well as «…» does.
        return max(withOriginal, scoreText(stripped, fields))
    }

    private fun scoreText(query: String, fields: List<Pair<String, Int>>): Int {
        if (query.isBlank()) return 0
        val qTokens = query.split(' ').filter { it.isNotBlank() }
        var best = 0

        for ((raw, weight) in fields) {
            val field = normalize(raw)
            if (field.isBlank()) continue
            val base = matchScore(query, qTokens, field)
            if (base <= 0) continue

            // Prefer the title that is closest in length to the query, and the
            // primary Persian title over a secondary/English alias.
            val lengthPenalty = min(abs(field.length - query.length), 28) * 2
            val candidate = base + weight - lengthPenalty
            if (candidate > best) best = candidate
        }
        return best
    }

    private fun matchScore(query: String, qTokens: List<String>, field: String): Int {
        if (field == query) return 4_000
        if (field.startsWith(query)) return 3_400

        val fieldTokens = field.split(' ').filter { it.isNotBlank() }
        if (fieldTokens.any { it.startsWith(query) }) return 3_050
        if (query.length >= 2 && field.contains(query)) return 2_550

        // All query words occur as word-prefixes somewhere in the title.
        if (qTokens.size > 1 && qTokens.all { token ->
                fieldTokens.any { it.startsWith(token) || token.startsWith(it) && it.length >= 3 }
            }
        ) return 2_300

        if (query.length < 3) return 0

        // Typo tolerance per word. Averaging token similarity (instead of one
        // edit-distance over the whole phrase) keeps long titles from drowning
        // a single mistyped word.
        val similarities = qTokens.map { token ->
            fieldTokens.maxOfOrNull { similarity(token, it) } ?: 0f
        }
        val average = similarities.average().toFloat()
        val allCloseEnough = similarities.all { it >= 0.72f }
        if (allCloseEnough && average >= 0.78f) {
            return (1_650 * average).toInt()
        }

        // A single very close word in a longer title still beats unrelated hits.
        val strongest = similarities.maxOrNull() ?: 0f
        if (strongest >= 0.84f) return (1_250 * strongest).toInt()

        return 0
    }

    /** Characters people type interchangeably on Persian keyboards. */
    fun normalize(raw: String): String {
        var value = raw.trim()
        if (value.isEmpty()) return ""
        // NFD lets us drop Latin accents as well as Persian diacritics.
        value = Normalizer.normalize(value, Normalizer.Form.NFKC)
            .replace('ي', 'ی')
            .replace('ك', 'ک')
            .replace('ۀ', 'ه')
            .replace('ة', 'ه')
            .replace('أ', 'ا')
            .replace('إ', 'ا')
            .replace('آ', 'ا')
            .replace('ؤ', 'و')
            .replace('ئ', 'ی')
            .replace('ى', 'ی')
        val folded = StringBuilder(value.length)
        value.forEach { ch ->
            val p = persianDigits.indexOf(ch)
            val a = arabicDigits.indexOf(ch)
            folded.append(
                when {
                    p >= 0 -> ('0' + p)
                    a >= 0 -> ('0' + a)
                    else -> ch
                },
            )
        }
        return nonWord.replace(
            whitespace.replace(
                zeroWidth.replace(
                    combiningMarks.replace(
                        Normalizer.normalize(folded.toString(), Normalizer.Form.NFD),
                        "",
                    ),
                    " ",
                ),
                " ",
            ).lowercase(Locale.ROOT),
            " ",
        ).trim().let { whitespace.replace(it, " ") }
    }

    private fun stripIntent(query: String): String {
        val tokens = query.split(' ').filter { it.isNotBlank() }
        if (tokens.size < 2) return query
        val remaining = tokens.filterNot { it in searchIntentWords }
        return if (remaining.isEmpty()) query else remaining.joinToString(" ")
    }

    /** 0..1 similarity between two words, based on bounded Levenshtein distance. */
    private fun similarity(a: String, b: String): Float {
        if (a == b) return 1f
        if (a.isEmpty() || b.isEmpty()) return 0f
        if (a.startsWith(b) || b.startsWith(a)) {
            return min(a.length, b.length).toFloat() / max(a.length, b.length)
        }
        val distance = editDistance(a, b, maxDistance = 4)
        if (distance > 4) return 0f
        return 1f - distance.toFloat() / max(a.length, b.length)
    }

    private fun editDistance(a: String, b: String, maxDistance: Int): Int {
        if (abs(a.length - b.length) > maxDistance) return maxDistance + 1
        var previous = IntArray(b.length + 1) { it }
        var current = IntArray(b.length + 1)
        for (i in 1..a.length) {
            current[0] = i
            var rowMin = current[0]
            for (j in 1..b.length) {
                val substitution = previous[j - 1] + if (a[i - 1] == b[j - 1]) 0 else 1
                current[j] = min(
                    min(previous[j] + 1, current[j - 1] + 1),
                    substitution,
                )
                rowMin = min(rowMin, current[j])
            }
            if (rowMin > maxDistance) return maxDistance + 1
            val swap = previous
            previous = current
            current = swap
        }
        return previous[b.length]
    }
}
