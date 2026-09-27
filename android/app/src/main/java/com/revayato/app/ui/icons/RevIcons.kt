package com.revayato.app.ui.icons

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/**
 * Local, dependency-free icon set drawn from Tabler Icons (MIT, no attribution).
 *
 * We embed only the handful of glyphs the app actually uses as [ImageVector]s built
 * from Tabler's raw SVG path data, instead of pulling in the whole compose-icons
 * wrapper library. The wrapper ships ~1260 classes; on this memory-constrained build
 * box the non-minified debug variant dexes every one of them and OOM-crashes D8, so
 * the local definitions below are the deliberate, lightweight alternative.
 *
 * All glyphs share Tabler's 24×24 canvas and 2px round outline styling.
 */
object RevIcons {

    private const val VIEWPORT = 24f

    /** Builds a white 2px-stroke outline icon from one or more Tabler SVG path strings. */
    private fun outline(name: String, vararg paths: String): ImageVector {
        val builder = ImageVector.Builder(
            name = name,
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = VIEWPORT,
            viewportHeight = VIEWPORT,
        )
        for (d in paths) {
            builder.addPath(
                pathData = addPathNodes(d),
                stroke = SolidColor(Color.White),
                strokeLineWidth = 2f,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
            )
        }
        return builder.build()
    }

    val LayoutGrid: ImageVector by lazy {
        outline(
            "LayoutGrid",
            "M4 4m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
            "M14 4m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
            "M4 14m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
            "M14 14m0 1a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v4a1 1 0 0 1 -1 1h-4a1 1 0 0 1 -1 -1z",
        )
    }

    val DeviceTv: ImageVector by lazy {
        outline(
            "DeviceTv",
            "M3 7m0 2a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z",
            "M16 3l-4 4l-4 -4",
        )
    }

    val Home: ImageVector by lazy {
        outline(
            "Home",
            "M5 12l-2 0l9 -9l9 9l-2 0",
            "M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7",
            "M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6",
        )
    }

    val Movie: ImageVector by lazy {
        outline(
            "Movie",
            "M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z",
            "M8 4l0 16",
            "M16 4l0 16",
            "M4 8l4 0",
            "M4 16l4 0",
            "M4 12l16 0",
            "M16 8l4 0",
            "M16 16l4 0",
        )
    }

    val User: ImageVector by lazy {
        outline(
            "User",
            "M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0",
            "M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2",
        )
    }

    val History: ImageVector by lazy {
        outline(
            "History",
            "M12 8l0 4l2 2",
            "M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5",
        )
    }

    val Bookmark: ImageVector by lazy {
        outline(
            "Bookmark",
            "M18 7v14l-6 -4l-6 4v-14a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4z",
        )
    }

    val Menu2: ImageVector by lazy {
        outline(
            "Menu2",
            "M4 6l16 0",
            "M4 12l16 0",
            "M4 18l16 0",
        )
    }

    val Search: ImageVector by lazy {
        outline(
            "Search",
            "M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0",
            "M21 21l-6 -6",
        )
    }
}
