package com.revayato.app.ui.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ripple
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Matrix
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.LocalThemeController
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.theme.ThemeMode
import kotlin.math.cos
import kotlin.math.sin

// Drawn in the switch's own 60.667 × 35 units (the uiverse sun/moon switch),
// then scaled to the requested height.
private const val PILL_W = 60.667f
private const val PILL_H = 35f
private const val KNOB_R = 15.167f
private const val KNOB_DAY_X = 2.333f
private const val KNOB_NIGHT_X = 28f
private const val KNOB_Y = 2.333f

private val SkyDay = Color(0xFF83CBD8)
private val SkyNight = Color(0xFF2B4360)
private val SunOuter = Color(0xFFF8E664)
private val SunGlow = Color(0x4AF6FEF7)
private val SunInner = Color(0xFFFCF4B9)
private val MoonFace = Color(0xFFCCE6EE)
private val MoonPatch = Color(0xFFA6CAD0)
private val StarColor = Color(0xFFDEF8FF)

/** Moon craters, relative to the knob: (x, y, r) of each circle's centre. */
private val MoonPatches = listOf(
    floatArrayOf(20.594f, 5.487f, 2f),
    floatArrayOf(16.951f, 18.943f, 2f),
    floatArrayOf(9.601f, 8.035f, 1f),
    floatArrayOf(27.666f, 18.879f, 1f),
    floatArrayOf(9.601f, 22.494f, 1f),
    floatArrayOf(27.166f, 11.021f, 1.5f),
)

private const val CLOUD_D =
    "M3512.81,173.815a4.463,4.463,0,0,1,2.243.62.95.95,0,0,1,.72-1.281,4.852,4.852,0,0,1,2.623.519" +
        "c.034.02-.5-1.968.281-2.716a2.117,2.117,0,0,1,2.829-.274,1.821,1.821,0,0,1,.854,1.858" +
        "c.063.037,2.594-.049,3.285,1.273s-.865,2.544-.807,2.626a12.192,12.192,0,0,1,2.278.892" +
        "c.553.448,1.106,1.992-1.62,2.927a7.742,7.742,0,0,1-3.762-.3c-1.28-.49-1.181-2.65-1.137-2.624" +
        "s-1.417,2.2-2.623,2.2a4.172,4.172,0,0,1-2.394-1.206,3.825,3.825,0,0,1-2.771.774" +
        "c-3.429-.46-2.333-3.267-2.2-3.55A3.721,3.721,0,0,1,3512.81,173.815Z"

/** Each star: path data + its SVG transform as (a, b, c, d, e, f), inside the stars group. */
private val StarShapes: List<Pair<String, FloatArray>> = listOf(
    "M.774,0,.566.559,0,.539.458.933.25,1.492l.485-.361.458.394L1.024.953,1.509.592.943.572Z" to
        floatArrayOf(-1f, 0.017f, -0.017f, -1f, 24.231f, 3.055f),
    "M1.341.529.836.472.736,0,.505.46,0,.4.4.729l-.231.46L.605.932l.4.326L.9.786Z" to
        floatArrayOf(-0.777f, 0.629f, -0.629f, -0.777f, 23.185f, 12.358f),
    "M.015,1.065.475.9l.285.365L.766.772l.46-.164L.745.494.751,0,.481.407,0,.293.285.658Z" to
        floatArrayOf(0.438f, 0.899f, -0.899f, 0.438f, 23.177f, 29.735f),
    "M1.161,1.6,1.059,1,1.574.722.962.607.86,0,.613.572,0,.457.446.881.2,1.454l.516-.274Z" to
        rotateAt(12.677f, 0.388f, 104f),
    "M.873,1.648l.114-.62L1.579.945,1.03.62,1.144,0,.706.464.157.139.438.7,0,1.167l.592-.083Z" to
        floatArrayOf(-0.07f, 0.998f, -0.998f, -0.07f, 11.066f, 15.457f),
    "M.593,0,.638.724,0,.982l.7.211.045.724.36-.64.7.211L1.342.935,1.7.294,1.063.552Z" to
        rotateAt(8.326f, 28.061f, 11f),
    "M.816,0,.5.455,0,.311.323.767l-.312.455.516-.215.323.456L.827.911,1.343.7.839.552Z" to
        rotateAt(5.012f, 5.962f, 172f),
    "M1.261,0,.774.571.114.3.487.967,0,1.538.728,1.32l.372.662.047-.749.728-.218L1.215.749Z" to
        rotateAt(2.218f, 14.616f, 169f),
)

private fun rotateAt(tx: Float, ty: Float, degrees: Float): FloatArray {
    val r = Math.toRadians(degrees.toDouble())
    val c = cos(r).toFloat()
    val s = sin(r).toFloat()
    return floatArrayOf(c, s, -s, c, tx, ty)
}

private fun svgPath(d: String, m: FloatArray): Path {
    val path = PathParser().parsePathString(d).toPath()
    path.transform(
        Matrix().apply {
            values[Matrix.ScaleX] = m[0]
            values[Matrix.SkewY] = m[1]
            values[Matrix.SkewX] = m[2]
            values[Matrix.ScaleY] = m[3]
            values[Matrix.TranslateX] = m[4]
            values[Matrix.TranslateY] = m[5]
        },
    )
    return path
}

/**
 * The day/night switch: a sky pill whose sun slides across into a moon, the
 * cloud giving way to stars. Checked = dark. Tapping sets an explicit light or
 * dark choice; «خودکار» lives in the settings row.
 */
@Composable
fun ThemeToggle(
    modifier: Modifier = Modifier,
    height: Dp = 30.dp,
) {
    val controller = LocalThemeController.current
    val night = controller.isDark
    val progress by animateFloatAsState(
        targetValue = if (night) 1f else 0f,
        animationSpec = tween(durationMillis = 250, easing = FastOutSlowInEasing),
        label = "themeToggle",
    )
    val cloud = remember { svgPath(CLOUD_D, floatArrayOf(1f, 0f, 0f, 1f, -3469.97f, -164.44f)) }
    val stars = remember {
        StarShapes.map { (d, m) -> svgPath(d, m.copyOf().also { it[4] += 3.585f; it[5] += 1.325f }) }
    }
    val pill = remember {
        Path().apply {
            addRoundRect(
                androidx.compose.ui.geometry.RoundRect(0f, 0f, PILL_W, PILL_H, CornerRadius(PILL_H / 2)),
            )
        }
    }
    val width = height * (PILL_W / PILL_H)

    Canvas(
        modifier = modifier
            .size(width = width, height = height)
            .clip(RoundedCornerShape(50))
            .toggleable(
                value = night,
                role = Role.Switch,
                interactionSource = remember { MutableInteractionSource() },
                indication = ripple(bounded = true),
                onValueChange = { dark -> controller.setMode(if (dark) ThemeMode.DARK else ThemeMode.LIGHT) },
            )
            .semantics {
                contentDescription = "حالت تاریک"
                stateDescription = if (night) "تاریک" else "روشن"
            },
    ) {
        val k = size.height / PILL_H
        scale(scale = k, pivot = Offset.Zero) {
            clipPath(pill) {
                drawSky(progress, cloud, stars)
            }
        }
    }
}

private fun DrawScope.drawSky(p: Float, cloud: Path, stars: List<Path>) {
    drawRoundRect(
        color = lerp(SkyDay, SkyNight, p),
        size = Size(PILL_W, PILL_H),
        cornerRadius = CornerRadius(PILL_H / 2),
    )
    if (p > 0f) {
        stars.forEach { drawPath(it, StarColor, alpha = p) }
    }

    val knobX = KNOB_DAY_X + (KNOB_NIGHT_X - KNOB_DAY_X) * p
    translate(left = knobX, top = KNOB_Y) {
        val c = Offset(KNOB_R, KNOB_R)
        if (p < 1f) {
            val a = 1f - p
            drawCircle(SunOuter, radius = KNOB_R, center = c, alpha = a)
            drawCircle(SunGlow, radius = 11.667f, center = c, alpha = a)
            drawCircle(SunInner, radius = 7f, center = c, alpha = a)
        }
        if (p > 0f) {
            drawCircle(MoonFace, radius = KNOB_R, center = c, alpha = p)
            MoonPatches.forEach { (x, y, r) -> drawCircle(MoonPatch, radius = r, center = Offset(x, y), alpha = p) }
        }
    }

    if (p < 1f) drawPath(cloud, Color.White, alpha = 1f - p)
}

/**
 * The full choice, for settings: follow the phone, always light, always dark.
 * A three-part segmented control; the selected part is filled with the brand.
 */
@Composable
fun ThemeModePicker(modifier: Modifier = Modifier) {
    val controller = LocalThemeController.current
    val options = listOf(
        ThemeMode.SYSTEM to "خودکار",
        ThemeMode.LIGHT to "روشن",
        ThemeMode.DARK to "تاریک",
    )
    androidx.compose.foundation.layout.Row(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(NeutralSurface)
            .padding(3.dp)
            .selectableGroup(),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(3.dp),
    ) {
        options.forEach { (mode, label) ->
            val selected = controller.mode == mode
            androidx.compose.foundation.layout.Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(9.dp))
                    .background(if (selected) Brand else Color.Transparent)
                    .selectable(selected = selected, role = Role.RadioButton) { controller.setMode(mode) }
                    .padding(vertical = 9.dp),
                contentAlignment = androidx.compose.ui.Alignment.Center,
            ) {
                androidx.compose.material3.Text(
                    label,
                    style = androidx.compose.material3.MaterialTheme.typography.labelLarge,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    color = if (selected) OnBrand else TextSecondary,
                )
            }
        }
    }
}
