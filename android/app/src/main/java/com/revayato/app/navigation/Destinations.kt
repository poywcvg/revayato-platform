package com.revayato.app.navigation

import androidx.compose.ui.graphics.vector.ImageVector
import com.revayato.app.ui.icons.RevIcons

/**
 * Top-level destinations. The bottom navigation bar shows [bottomBar] in order:
 * دسته‌بندی‌ها · سریال · خانه · فیلم · کتابخانه — with Home in the centre.
 * The last tab (enum name CONTINUE, route "continue") opens [LibraryScreen] — the
 * user's watchlist / favourites / downloads. It is labelled «کتابخانه» (not «ادامه
 * تماشا») so a title the user saved from a detail page is obviously findable here.
 * PROFILE stays in the enum (reached from the top bar / drawer) but is no longer
 * a bottom tab. (Search and watch-party are reached from the top bar / drawer.)
 */
enum class TopLevelDestination(
    val route: String,
    val label: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector,
) {
    CATEGORIES("categories", "دسته‌بندی‌ها", RevIcons.LayoutGrid, RevIcons.LayoutGrid),
    SERIES("browse/series", "سریال", RevIcons.DeviceTv, RevIcons.DeviceTv),
    HOME("home", "خانه", RevIcons.Home, RevIcons.Home),
    MOVIES("browse/movies", "فیلم", RevIcons.Movie, RevIcons.Movie),
    PROFILE("profile", "پروفایل", RevIcons.User, RevIcons.User),
    CONTINUE("continue", "کتابخانه", RevIcons.Bookmark, RevIcons.Bookmark),
    ;

    companion object {
        /** Tabs shown in the bottom bar, left→right, with Home centred. */
        val bottomBar = listOf(CATEGORIES, SERIES, HOME, MOVIES, CONTINUE)
    }
}

/** Non-tab routes and their argument helpers. */
object Routes {
    const val HOME = "home"
    const val SEARCH = "search"
    const val WATCH_PARTY = "watch_party"
    const val MOVIE_DETAIL = "movie/{slug}"
    const val SERIES_DETAIL = "series/{slug}"
    const val PLAYER = "player/{contentType}/{id}?slug={slug}&title={title}&url={url}&position={position}&episode={episode}&subtitles={subtitles}&qualities={qualities}"
    const val WATCH_PARTY_ROOM = "watch_party/room/{code}"
    const val LOGIN = "auth/login"
    const val REGISTER = "auth/register"
    const val FORGOT_PASSWORD = "auth/forgot"
    const val COLLECTION = "collection/{slug}"
    // User collections ("کالکشن") + public profiles — distinct from editorial COLLECTION.
    const val MY_COLLECTIONS = "me/collections"
    const val MY_COLLECTION = "me/collection/{slug}"
    // Support conversations ("درخواست‌های من") — client side of the admin↔user inbox.
    const val MY_REQUESTS = "me/requests"
    const val REQUEST_DETAIL = "me/request/{code}"
    const val SHARED_COLLECTION = "c/{token}"
    const val PUBLIC_PROFILE = "u/{username}"
    const val PUBLIC_COLLECTION = "u/{username}/collection/{slug}"
    const val DOWNLOADS = "downloads"
    const val DASHBOARD = "dashboard"
    const val CATALOG_LIST =
        "catalog/{kind}?title={title}&genre={genre}&country={country}&sort={sort}&format={format}&availability={availability}"
    const val ACTORS = "people/actors"
    const val DIRECTORS = "people/directors"
    const val COUNTRIES = "discover/countries"
    const val GENRES = "discover/genres"
    const val ACTOR_DETAIL = "actor/{slug}"
    const val DIRECTOR_DETAIL = "director/{slug}"

    fun movieDetail(slug: String) = "movie/$slug"
    fun seriesDetail(slug: String) = "series/$slug"
    fun watchPartyRoom(code: String) = "watch_party/room/$code"
    fun collection(slug: String) = "collection/$slug"
    fun myCollection(slug: String) = "me/collection/${android.net.Uri.encode(slug)}"
    fun requestDetail(code: String) = "me/request/${android.net.Uri.encode(code)}"
    fun sharedCollection(token: String) = "c/${android.net.Uri.encode(token)}"
    fun publicProfile(username: String) = "u/${android.net.Uri.encode(username)}"
    fun publicCollection(username: String, slug: String) =
        "u/${android.net.Uri.encode(username)}/collection/${android.net.Uri.encode(slug)}"
    fun actorDetail(slug: String) = "actor/${android.net.Uri.encode(slug)}"
    fun directorDetail(slug: String) = "director/${android.net.Uri.encode(slug)}"

    private fun enc(value: String) = android.net.Uri.encode(value)

    /**
     * Catalog list with an algorithm baked in. [sort] (newest/popular/top_rated/title),
     * [format] (animation/live_action/short), [availability] (dubbed/subtitle/download)
     * and [country] (code or name) all map straight to the backend catalog filters, so
     * a "see more" opens exactly the shelf the caller described.
     */
    fun catalogList(
        kind: String,
        title: String,
        genre: String = "",
        country: String = "",
        sort: String = "",
        format: String = "",
        availability: String = "",
    ) = "catalog/$kind?title=${enc(title)}&genre=${enc(genre)}&country=${enc(country)}" +
        "&sort=${enc(sort)}&format=${enc(format)}&availability=${enc(availability)}"
}
