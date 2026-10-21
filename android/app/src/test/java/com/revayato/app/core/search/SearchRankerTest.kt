package com.revayato.app.core.search

import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.PersonDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SearchRankerTest {
    private fun title(id: Int, name: String) = CatalogCardDto(id = id, title = name)

    @Test
    fun `exact title ranks above prefix and word matches`() {
        val items = listOf(
            title(1, "ماتریکس بازآفرینی"),
            title(2, "فیلم ماتریکس"),
            title(3, "ماتریکس"),
        )

        val ranked = SearchRanker.rankTitles("ماتریکس", items)

        assertEquals(listOf(3, 1, 2), ranked.map { it.id })
    }

    @Test
    fun `intent words are ignored so download queries still find the title`() {
        val items = listOf(
            title(1, "ارباب حلقه‌ها"),
            title(2, "ارباب حلقه‌ها: یاران حلقه"),
            title(3, "حلقه گمشده"),
        )

        val ranked = SearchRanker.rankTitles("دانلود فیلم ارباب حلقه‌ها", items)

        assertEquals(1, ranked.first().id)
    }

    @Test
    fun `Persian and Arabic keyboard variants normalize to the same title`() {
        val items = listOf(
            title(1, "ماتریکس"),
            title(2, "دنیای غرب"),
        )

        val ranked = SearchRanker.rankTitles("ماتريكس", items)

        assertEquals(1, ranked.first().id)
    }

    @Test
    fun `Persian digits match Latin digits in titles`() {
        val items = listOf(
            title(1, "۱۹۸۴"),
            title(2, "۲۰۰۱: ادیسه فضایی"),
        )

        val ranked = SearchRanker.rankTitles("1984", items)

        assertEquals(1, ranked.first().id)
    }

    @Test
    fun `single letter typo still finds the intended title`() {
        val items = listOf(
            title(1, "Interstellar"),
            title(2, "Interstate 60"),
            title(3, "The Matrix"),
        )

        val ranked = SearchRanker.rankTitles("intersteller", items)

        assertEquals(1, ranked.first().id)
    }

    @Test
    fun `equally relevant results keep the server order`() {
        val items = listOf(
            title(11, "سریال یک"),
            title(12, "سریال دو"),
        )

        val ranked = SearchRanker.rankTitles("سریال", items)

        assertEquals(listOf(11, 12), ranked.map { it.id })
    }

    @Test
    fun `people are ranked by nearest name`() {
        val people = listOf(
            PersonDto(id = 1, name = "تام هالند"),
            PersonDto(id = 2, name = "تام هاردی"),
            PersonDto(id = 3, name = "تیموتی شالامه"),
        )

        val ranked = SearchRanker.rankPeople("تام هاردی", people)

        assertEquals(2, ranked.first().id)
    }

    @Test
    fun `blank query does not change the list`() {
        val items = listOf(title(1, "اول"), title(2, "دوم"))
        assertTrue(SearchRanker.rankTitles("   ", items).map { it.id } == listOf(1, 2))
    }
}
