package com.revayato.app.navigation

import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.RevayatoMotion
import com.revayato.app.core.theme.RevayatoTheme
import com.revayato.app.ui.components.ThemeToggle

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import com.revayato.app.ui.icons.RevIcons
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.feature.auth.ForgotPasswordScreen
import com.revayato.app.feature.auth.LoginScreen
import com.revayato.app.feature.auth.RegisterScreen
import com.revayato.app.feature.catalog.CatalogListScreen
import com.revayato.app.feature.catalog.CategoriesScreen
import com.revayato.app.feature.catalog.GenresScreen
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.feature.collection.CollectionScreen
import com.revayato.app.feature.collections.CollectionDetailScreen
import com.revayato.app.feature.collections.CollectionSource
import com.revayato.app.feature.collections.MyCollectionsScreen
import com.revayato.app.feature.support.MyRequestsScreen
import com.revayato.app.feature.support.RequestDetailScreen
import com.revayato.app.feature.dashboard.DashboardScreen
import com.revayato.app.feature.discovery.CountriesScreen
import com.revayato.app.feature.people.PeopleListScreen
import com.revayato.app.feature.people.PersonDetailScreen
import com.revayato.app.feature.detail.MovieDetailScreen
import com.revayato.app.feature.detail.SeriesDetailScreen
import com.revayato.app.feature.downloads.DownloadsScreen
import com.revayato.app.feature.home.HomeScreen
import com.revayato.app.feature.library.LibraryScreen
import com.revayato.app.feature.player.PlayerArgs
import com.revayato.app.feature.player.PlayerScreen
import com.revayato.app.feature.profile.ProfileScreen
import com.revayato.app.feature.profile.PublicProfileScreen
import com.revayato.app.feature.search.SearchScreen
import com.revayato.app.feature.watchparty.WatchPartyLandingScreen
import com.revayato.app.feature.watchparty.WatchPartyRoomScreen
import androidx.compose.foundation.layout.Column
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch

/*
 * Motion is deliberately declared once, here. Detail pages share a gentle
 * push/settle, tabs cross-fade instead of sliding (a tab is a lateral sibling,
 * not a child), search rises from the top, and the two cinema routes fade from
 * black. This is what keeps every navigation feeling like the same product.
 */
private fun pageEnter() =
    slideInHorizontally(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
    ) { it / 7 } +
        fadeIn(tween(220, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
            initialScale = 0.985f,
        )

private fun pageExit() =
    slideOutHorizontally(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
    ) { -it / 14 } +
        fadeOut(tween(RevayatoMotion.Fast))

private fun popPageEnter() =
    slideInHorizontally(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
    ) { -it / 10 } +
        fadeIn(tween(220, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
            initialScale = 0.99f,
        )

private fun popPageExit() =
    slideOutHorizontally(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
    ) { it / 8 } +
        fadeOut(tween(RevayatoMotion.Fast))

private fun tabEnter() =
    fadeIn(tween(RevayatoMotion.Fast, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(260, easing = RevayatoMotion.Decelerate),
            initialScale = 0.992f,
        )

private fun tabExit() = fadeOut(tween(150))

private fun searchEnter() =
    slideInVertically(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Decelerate),
    ) { -it / 18 } +
        fadeIn(tween(200, easing = RevayatoMotion.Decelerate))

private fun authEnter() =
    slideInVertically(
        animationSpec = tween(RevayatoMotion.Standard, easing = RevayatoMotion.Emphasized),
    ) { it / 10 } +
        fadeIn(tween(220, easing = RevayatoMotion.Decelerate))

private fun playerEnter() =
    fadeIn(tween(260, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(340, easing = RevayatoMotion.Decelerate),
            initialScale = 0.96f,
        )

private fun roomEnter() =
    fadeIn(tween(240, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(320, easing = RevayatoMotion.Decelerate),
            initialScale = 0.975f,
        )

private fun cinemaExit() = fadeOut(tween(180, easing = RevayatoMotion.StandardEasing))

private fun settleEnter() =
    fadeIn(tween(240, easing = RevayatoMotion.Decelerate)) +
        scaleIn(
            animationSpec = tween(300, easing = RevayatoMotion.Decelerate),
            initialScale = 0.985f,
        )

@Composable
fun RevayatoRoot(
    isLoggedIn: Boolean,
    sessionEvents: SharedFlow<Unit>,
) {
    val navController = rememberNavController()
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    // A dead refresh token anywhere in the app funnels the user back to login.
    LaunchedEffect(sessionEvents) {
        sessionEvents.collect {
            navController.navigate(Routes.LOGIN) {
                popUpTo(navController.graph.findStartDestination().id) { inclusive = false }
                launchSingleTop = true
            }
        }
    }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val chromeRoutes = remember { TopLevelDestination.entries.map { it.route }.toSet() + Routes.HOME }
    val authRoutes = remember { setOf(Routes.LOGIN, Routes.REGISTER, Routes.FORGOT_PASSWORD) }
    val showChrome = currentRoute in chromeRoutes

    // The drawer belongs only to the top-level chrome screens. While we are on ANY
    // non-chrome route (detail / player / …), keep it *continuously* pinned shut:
    // the moment anything at all nudges it open — an edge drag on the landscape
    // player, a config-change re-layout, stray restored state — snap it straight
    // back to Closed with no animation, so the side menu can never appear over the
    // video. This continuous guard replaces the old one-shot close, which could be
    // out-run by whatever was opening the drawer after the player was already shown.
    LaunchedEffect(showChrome) {
        if (!showChrome) {
            // targetValue flips the instant an open is *initiated* (before any
            // animation paints), so we snap shut earlier than currentValue would.
            snapshotFlow { drawerState.targetValue }.collect { value ->
                if (value != DrawerValue.Closed) {
                    runCatching { drawerState.snapTo(DrawerValue.Closed) }
                }
            }
        }
    }

    fun closeDrawer() = scope.launch { drawerState.close() }

    fun goTab(route: String) {
        navController.navigate(route) {
            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    fun drawerGo(route: String) {
        closeDrawer()
        navController.navigate(route) { launchSingleTop = true }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        // Edge-swipe is allowed *only* on the top-level "chrome" screens. On the
        // landscape player (and every detail route) it stays off so volume /
        // brightness / seek gestures — or an accidental edge drag — can never pull
        // the side menu open over the video. Chrome screens are the only place the
        // drawer lives, and there showChrome is true so it can still be swiped shut.
        gesturesEnabled = showChrome,
        drawerContent = {
            BrowseDrawerContent(
                isLoggedIn = isLoggedIn,
                onTop250 = { drawerGo(Routes.catalogList("top250", "۲۵۰ برتر IMDb")) },
                onWatchParty = {
                    closeDrawer()
                    if (isLoggedIn) navController.navigate(Routes.WATCH_PARTY) { launchSingleTop = true }
                    else navController.navigate(Routes.LOGIN)
                },
                onDownloads = { drawerGo(Routes.DOWNLOADS) },
                onProfile = { closeDrawer(); goTab(TopLevelDestination.PROFILE.route) },
                onLogin = { drawerGo(Routes.LOGIN) },
                onLogout = { closeDrawer(); goTab(TopLevelDestination.PROFILE.route) },
            )
        },
    ) {
        Scaffold(
            modifier = Modifier.fillMaxSize(),
            containerColor = MaterialTheme.colorScheme.background,
            topBar = {
                AnimatedVisibility(
                    visible = showChrome,
                    enter = fadeIn(),
                    exit = fadeOut(),
                ) {
                    RevayatoTopBar(
                        onMenu = { scope.launch { drawerState.open() } },
                        onSearch = { navController.navigate(Routes.SEARCH) { launchSingleTop = true } },
                    )
                }
            },
            bottomBar = {
                AnimatedVisibility(
                    visible = showChrome,
                    enter = slideInVertically { it },
                    exit = slideOutVertically { it },
                ) {
                    RevayatoBottomBar(navController = navController, onSelect = ::goTab)
                }
            },
        ) { innerPadding ->
            NavHost(
                navController = navController,
                startDestination = Routes.HOME,
                modifier = Modifier.fillMaxSize(),
                enterTransition = {
                    val from = initialState.destination.route
                    val to = targetState.destination.route
                    when {
                        to == Routes.PLAYER -> playerEnter()
                        to == Routes.WATCH_PARTY_ROOM -> roomEnter()
                        to == Routes.SEARCH -> searchEnter()
                        from == Routes.PLAYER -> settleEnter()
                        to in chromeRoutes && from in chromeRoutes -> tabEnter()
                        to in authRoutes || from in authRoutes -> authEnter()
                        else -> pageEnter()
                    }
                },
                exitTransition = {
                    val from = initialState.destination.route
                    val to = targetState.destination.route
                    when {
                        from == Routes.PLAYER -> cinemaExit()
                        to == Routes.PLAYER -> cinemaExit()
                        to == Routes.SEARCH || from == Routes.SEARCH -> fadeOut(tween(160))
                        from in chromeRoutes && to in chromeRoutes -> tabExit()
                        else -> pageExit()
                    }
                },
                popEnterTransition = {
                    val from = initialState.destination.route
                    val to = targetState.destination.route
                    when {
                        to == Routes.PLAYER -> playerEnter()
                        from == Routes.PLAYER -> settleEnter()
                        from in chromeRoutes && to in chromeRoutes -> tabEnter()
                        else -> popPageEnter()
                    }
                },
                popExitTransition = {
                    val from = initialState.destination.route
                    val to = targetState.destination.route
                    when {
                        from == Routes.PLAYER -> cinemaExit()
                        to == Routes.PLAYER -> cinemaExit()
                        from in chromeRoutes && to in chromeRoutes -> tabExit()
                        else -> popPageExit()
                    }
                },
            ) {
                // ---- Home (start) ----
                composable(Routes.HOME) {
                    HomeScreen(
                        modifier = Modifier.padding(innerPadding),
                        onOpenTitle = navController::openTitle,
                        onOpenCollection = { navController.navigate(Routes.collection(it)) },
                        onSeeAllRoute = { route -> navController.navigate(route) },
                        onResume = { entry ->
                            navController.openPlayer(
                                contentType = entry.contentType,
                                id = entry.id,
                                slug = entry.slug,
                                title = entry.title,
                                url = entry.url,
                                positionMs = entry.positionMs,
                                episodeId = entry.episodeId,
                                subtitlesEncoded = entry.subtitlesEncoded,
                                qualitiesEncoded = entry.qualitiesEncoded,
                            )
                        },
                        onOpenGenre = { genre ->
                            navController.navigate(Routes.catalogList("movies", genre.title, genre.slug))
                        },
                    )
                }

                // ---- Bottom-nav tabs ----
                composable(TopLevelDestination.CATEGORIES.route) {
                    CategoriesScreen(
                        modifier = Modifier.padding(innerPadding),
                        onNavigate = { route -> navController.navigate(route) { launchSingleTop = true } },
                    )
                }
                composable(TopLevelDestination.MOVIES.route) {
                    CatalogListScreen(
                        kind = "movies",
                        title = "فیلم‌ها",
                        embedded = true,
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        modifier = Modifier.padding(innerPadding),
                    )
                }
                composable(TopLevelDestination.SERIES.route) {
                    CatalogListScreen(
                        kind = "series",
                        title = "سریال‌ها",
                        embedded = true,
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        modifier = Modifier.padding(innerPadding),
                    )
                }
                composable(TopLevelDestination.CONTINUE.route) {
                    LibraryScreen(
                        modifier = Modifier.padding(innerPadding),
                        isLoggedIn = isLoggedIn,
                        onOpenTitle = navController::openTitle,
                        onOpenDownloads = { navController.navigate(Routes.DOWNLOADS) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                    )
                }
                composable(TopLevelDestination.PROFILE.route) {
                    ProfileScreen(
                        modifier = Modifier.padding(innerPadding),
                        isLoggedIn = isLoggedIn,
                        onOpenDownloads = { navController.navigate(Routes.DOWNLOADS) },
                        onOpenDashboard = { navController.navigate(Routes.DASHBOARD) },
                        onLogin = { navController.navigate(Routes.LOGIN) },
                        onOpenMyCollections = { navController.navigate(Routes.MY_COLLECTIONS) },
                        onOpenMyRequests = { navController.navigate(Routes.MY_REQUESTS) },
                        onOpenCollection = { slug -> navController.navigate(Routes.myCollection(slug)) },
                        onOpenTitle = navController::openTitle,
                        onLoggedOut = {
                            navController.navigate(Routes.HOME) {
                                popUpTo(navController.graph.findStartDestination().id)
                                launchSingleTop = true
                            }
                        },
                    )
                }

                // ---- Search ----
                composable(Routes.SEARCH) {
                    Column(Modifier.fillMaxSize()) {
                        BackTopBar(title = "جستجو", onBack = navController::navigateUp)
                        SearchScreen(
                            onOpenTitle = navController::openTitle,
                            onOpenPerson = { slug -> navController.navigate(Routes.actorDetail(slug)) },
                        )
                    }
                }

                // ---- Watch party landing (login-gated) ----
                composable(Routes.WATCH_PARTY) {
                    WatchPartyLandingScreen(
                        modifier = Modifier.padding(innerPadding),
                        isLoggedIn = isLoggedIn,
                        onEnterRoom = { navController.navigate(Routes.watchPartyRoom(it)) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                    )
                }

                // ---- Detail ----
                composable(
                    route = Routes.MOVIE_DETAIL,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    MovieDetailScreen(
                        slug = entry.arguments?.getString("slug").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        onPlay = navController::openPlayer,
                        onWatchTogether = { navController.navigate(Routes.watchPartyRoom(it)) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                        onOpenPerson = { kind, slug ->
                            navController.navigate(
                                if (kind == "director") Routes.directorDetail(slug) else Routes.actorDetail(slug),
                            )
                        },
                        onOpenGenre = { genre ->
                            navController.navigate(
                                Routes.catalogList("movies", genre.title, genre = genre.slug, sort = "popular"),
                            )
                        },
                        onOpenLibrary = { goTab(TopLevelDestination.CONTINUE.route) },
                    )
                }
                composable(
                    route = Routes.SERIES_DETAIL,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    SeriesDetailScreen(
                        slug = entry.arguments?.getString("slug").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        onPlay = navController::openPlayer,
                        onWatchTogether = { navController.navigate(Routes.watchPartyRoom(it)) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                        onOpenPerson = { kind, slug ->
                            navController.navigate(
                                if (kind == "director") Routes.directorDetail(slug) else Routes.actorDetail(slug),
                            )
                        },
                        onOpenGenre = { genre ->
                            navController.navigate(
                                Routes.catalogList("series", genre.title, genre = genre.slug, sort = "popular"),
                            )
                        },
                        onOpenLibrary = { goTab(TopLevelDestination.CONTINUE.route) },
                    )
                }

                // ---- Player ----
                composable(
                    route = Routes.PLAYER,
                    arguments = listOf(
                        navArgument("contentType") { type = NavType.StringType },
                        navArgument("id") { type = NavType.IntType },
                        navArgument("slug") { type = NavType.StringType; defaultValue = "" },
                        navArgument("title") { type = NavType.StringType; defaultValue = "" },
                        navArgument("url") { type = NavType.StringType; defaultValue = "" },
                        navArgument("position") { type = NavType.LongType; defaultValue = 0L },
                        navArgument("episode") { type = NavType.IntType; defaultValue = 0 },
                        navArgument("subtitles") { type = NavType.StringType; defaultValue = "" },
                        navArgument("qualities") { type = NavType.StringType; defaultValue = "" },
                    ),
                ) { entry ->
                    val args = entry.arguments!!
                    // The cinema stays dark whatever the app theme is.
                    RevayatoTheme(darkTheme = true) { PlayerScreen(
                        args = PlayerArgs(
                            contentType = args.getString("contentType").orEmpty(),
                            id = args.getInt("id"),
                            slug = args.getString("slug").orEmpty(),
                            title = args.getString("title").orEmpty(),
                            url = args.getString("url").orEmpty(),
                            startPositionMs = args.getLong("position"),
                            episodeId = args.getInt("episode"),
                            subtitlesEncoded = args.getString("subtitles").orEmpty(),
                            qualitiesEncoded = args.getString("qualities").orEmpty(),
                        ),
                        onBack = navController::navigateUp,
                    ) }
                }

                // ---- Watch party room ----
                composable(
                    route = Routes.WATCH_PARTY_ROOM,
                    arguments = listOf(navArgument("code") { type = NavType.StringType }),
                ) { entry ->
                    RevayatoTheme(darkTheme = true) {
                        WatchPartyRoomScreen(
                            code = entry.arguments?.getString("code").orEmpty(),
                            onBack = navController::navigateUp,
                            onOpenPlayer = navController::openPlayer,
                        )
                    }
                }

                // ---- Collections / lists ----
                composable(
                    route = Routes.COLLECTION,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    CollectionScreen(
                        slug = entry.arguments?.getString("slug").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                    )
                }

                // ---- User collections ("کالکشن") & public profiles ----
                composable(Routes.MY_COLLECTIONS) {
                    MyCollectionsScreen(
                        modifier = Modifier.padding(innerPadding),
                        isLoggedIn = isLoggedIn,
                        onBack = navController::navigateUp,
                        onOpenCollection = { slug -> navController.navigate(Routes.myCollection(slug)) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                    )
                }
                composable(Routes.MY_REQUESTS) {
                    MyRequestsScreen(
                        modifier = Modifier.padding(innerPadding),
                        isLoggedIn = isLoggedIn,
                        onBack = navController::navigateUp,
                        onOpenRequest = { code -> navController.navigate(Routes.requestDetail(code)) },
                        onRequireLogin = { navController.navigate(Routes.LOGIN) },
                    )
                }
                composable(
                    route = Routes.REQUEST_DETAIL,
                    arguments = listOf(navArgument("code") { type = NavType.StringType }),
                ) { entry ->
                    RequestDetailScreen(
                        modifier = Modifier.padding(innerPadding),
                        code = entry.arguments?.getString("code").orEmpty(),
                        onBack = navController::navigateUp,
                    )
                }
                composable(
                    route = Routes.MY_COLLECTION,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    CollectionDetailScreen(
                        modifier = Modifier.padding(innerPadding),
                        source = CollectionSource.Owned(entry.arguments?.getString("slug").orEmpty()),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        onOpenProfile = { username -> navController.navigate(Routes.publicProfile(username)) },
                    )
                }
                composable(
                    route = Routes.SHARED_COLLECTION,
                    arguments = listOf(navArgument("token") { type = NavType.StringType }),
                ) { entry ->
                    CollectionDetailScreen(
                        modifier = Modifier.padding(innerPadding),
                        source = CollectionSource.Shared(entry.arguments?.getString("token").orEmpty()),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        onOpenProfile = { username -> navController.navigate(Routes.publicProfile(username)) },
                    )
                }
                composable(
                    route = Routes.PUBLIC_COLLECTION,
                    arguments = listOf(
                        navArgument("username") { type = NavType.StringType },
                        navArgument("slug") { type = NavType.StringType },
                    ),
                ) { entry ->
                    CollectionDetailScreen(
                        modifier = Modifier.padding(innerPadding),
                        source = CollectionSource.Public(
                            username = entry.arguments?.getString("username").orEmpty(),
                            slug = entry.arguments?.getString("slug").orEmpty(),
                        ),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                        onOpenProfile = { username -> navController.navigate(Routes.publicProfile(username)) },
                    )
                }
                composable(
                    route = Routes.PUBLIC_PROFILE,
                    arguments = listOf(navArgument("username") { type = NavType.StringType }),
                ) { entry ->
                    PublicProfileScreen(
                        modifier = Modifier.padding(innerPadding),
                        username = entry.arguments?.getString("username").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenCollection = { username, slug ->
                            navController.navigate(Routes.publicCollection(username, slug))
                        },
                        onOpenTitle = navController::openTitle,
                    )
                }
                composable(
                    route = Routes.CATALOG_LIST,
                    arguments = listOf(
                        navArgument("kind") { type = NavType.StringType },
                        navArgument("title") { type = NavType.StringType; defaultValue = "" },
                        navArgument("genre") { type = NavType.StringType; defaultValue = "" },
                        navArgument("country") { type = NavType.StringType; defaultValue = "" },
                        navArgument("sort") { type = NavType.StringType; defaultValue = "" },
                        navArgument("format") { type = NavType.StringType; defaultValue = "" },
                        navArgument("availability") { type = NavType.StringType; defaultValue = "" },
                    ),
                ) { entry ->
                    val args = entry.arguments
                    CatalogListScreen(
                        kind = args?.getString("kind").orEmpty(),
                        title = args?.getString("title").orEmpty(),
                        genre = args?.getString("genre").orEmpty(),
                        country = args?.getString("country").orEmpty(),
                        format = args?.getString("format").orEmpty(),
                        availability = args?.getString("availability").orEmpty(),
                        initialSort = args?.getString("sort").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                    )
                }

                // ---- People & discovery ----
                composable(Routes.ACTORS) {
                    PeopleListScreen(
                        kind = "actors",
                        onBack = navController::navigateUp,
                        onOpenPerson = { slug -> navController.navigate(Routes.actorDetail(slug)) },
                    )
                }
                composable(Routes.DIRECTORS) {
                    PeopleListScreen(
                        kind = "directors",
                        onBack = navController::navigateUp,
                        onOpenPerson = { slug -> navController.navigate(Routes.directorDetail(slug)) },
                    )
                }
                composable(
                    route = Routes.ACTOR_DETAIL,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    PersonDetailScreen(
                        kind = "actor",
                        slug = entry.arguments?.getString("slug").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                    )
                }
                composable(
                    route = Routes.DIRECTOR_DETAIL,
                    arguments = listOf(navArgument("slug") { type = NavType.StringType }),
                ) { entry ->
                    PersonDetailScreen(
                        kind = "director",
                        slug = entry.arguments?.getString("slug").orEmpty(),
                        onBack = navController::navigateUp,
                        onOpenTitle = navController::openTitle,
                    )
                }
                composable(Routes.GENRES) {
                    GenresScreen(
                        onBack = navController::navigateUp,
                        onOpenGenre = { genre ->
                            navController.navigate(
                                Routes.catalogList("movies", genre.title, genre = genre.slug, sort = "popular"),
                            )
                        },
                    )
                }
                composable(Routes.COUNTRIES) {
                    CountriesScreen(
                        onBack = navController::navigateUp,
                        onOpenCountry = { filterValue, name ->
                            navController.navigate(
                                Routes.catalogList("movies", name, country = filterValue, sort = "popular"),
                            )
                        },
                    )
                }

                // ---- Downloads ----
                composable(Routes.DOWNLOADS) {
                    DownloadsScreen(
                        onBack = navController::navigateUp,
                        onPlay = navController::openPlayer,
                    )
                }

                // ---- Staff analytics dashboard ----
                composable(Routes.DASHBOARD) {
                    DashboardScreen(
                        modifier = Modifier.padding(innerPadding),
                        onBack = navController::navigateUp,
                    )
                }

                // ---- Auth ----
                composable(Routes.LOGIN) {
                    LoginScreen(
                        onBack = navController::navigateUp,
                        onLoggedIn = navController::navigateUp,
                        // The ورود | ثبت‌نام switch swaps screens instead of stacking them,
                        // so back always returns to where the user came from.
                        onRegister = {
                            navController.navigate(Routes.REGISTER) {
                                popUpTo(Routes.LOGIN) { inclusive = true }
                                launchSingleTop = true
                            }
                        },
                        onForgotPassword = { navController.navigate(Routes.FORGOT_PASSWORD) },
                    )
                }
                composable(Routes.REGISTER) {
                    RegisterScreen(
                        onBack = navController::navigateUp,
                        onRegistered = navController::navigateUp,
                        onLogin = {
                            navController.navigate(Routes.LOGIN) {
                                popUpTo(Routes.REGISTER) { inclusive = true }
                                launchSingleTop = true
                            }
                        },
                    )
                }
                composable(Routes.FORGOT_PASSWORD) {
                    ForgotPasswordScreen(onBack = navController::navigateUp)
                }
            }
        }
    }
}

/** Minimal translucent "glass" top bar: brand mark flanked by menu + search. */
@Composable
private fun RevayatoTopBar(
    onMenu: () -> Unit,
    onSearch: () -> Unit,
) {
    val topInset = WindowInsets.safeDrawing.asPaddingValues().calculateTopPadding()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgMain.copy(alpha = 0.72f))
            .padding(top = topInset)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        GlassButton(icon = RevIcons.Menu2, contentDescription = "منو", onClick = onMenu)
        Spacer(Modifier.size(8.dp))
        Text(
            "روایتو",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Black,
            color = TextPrimary,
            modifier = Modifier.weight(1f),
        )
        ThemeToggle(height = 28.dp)
        Spacer(Modifier.size(8.dp))
        GlassButton(icon = RevIcons.Search, contentDescription = "جستجو", onClick = onSearch)
    }
}

@Composable
private fun GlassButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .size(42.dp)
            .background(NeutralSurface, CircleShape)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = contentDescription, tint = TextPrimary, modifier = Modifier.size(22.dp))
    }
}

@Composable
private fun RevayatoBottomBar(
    navController: NavHostController,
    onSelect: (String) -> Unit,
) {
    NavigationBar(
        containerColor = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
    ) {
        val backStackEntry by navController.currentBackStackEntryAsState()
        TopLevelDestination.bottomBar.forEach { destination ->
            val selected = backStackEntry?.destination?.hierarchy?.any {
                it.route == destination.route
            } == true
            NavigationBarItem(
                selected = selected,
                onClick = { onSelect(destination.route) },
                icon = {
                    Icon(
                        imageVector = if (selected) destination.selectedIcon else destination.unselectedIcon,
                        contentDescription = destination.label,
                    )
                },
                label = { Text(destination.label, style = MaterialTheme.typography.labelSmall) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = OnBrand,
                    selectedTextColor = Brand,
                    indicatorColor = Brand,
                    unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                ),
            )
        }
    }
}

/** Navigate to a movie or series detail based on the card's content type. */
fun NavHostController.openTitle(contentType: String, slug: String) {
    if (contentType.equals("series", ignoreCase = true) || contentType.equals("tv", ignoreCase = true)) {
        navigate(Routes.seriesDetail(slug))
    } else {
        navigate(Routes.movieDetail(slug))
    }
}

/** Launch the player. Subtitles/qualities are passed pre-encoded as `label|url` pairs joined by `;;`.
 *  [slug] + [episodeId] let the player trigger the backend's auto-subtitle import. */
fun NavHostController.openPlayer(
    contentType: String,
    id: Int,
    slug: String,
    title: String,
    url: String,
    positionMs: Long,
    episodeId: Int,
    subtitlesEncoded: String,
    qualitiesEncoded: String,
) {
    val safeSlug = android.net.Uri.encode(slug)
    val safeTitle = android.net.Uri.encode(title)
    val safeUrl = android.net.Uri.encode(url)
    val safeSubs = android.net.Uri.encode(subtitlesEncoded)
    val safeQualities = android.net.Uri.encode(qualitiesEncoded)
    navigate(
        "player/$contentType/$id?slug=$safeSlug&title=$safeTitle&url=$safeUrl" +
            "&position=$positionMs&episode=$episodeId&subtitles=$safeSubs&qualities=$safeQualities",
    )
}
