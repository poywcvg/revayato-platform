package com.revayato.app.core.theme

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer

/**
 * One motion language for the whole app.
 *
 * The old screens each invented their own duration/easing (some 90 ms, some
 * 380 ms), which made moving between them feel like using several products.
 * Everything now comes from this object: a short, confident ease-out for taps,
 * a longer emphasized curve for pages and hero reveals, and one spring for
 * tactile press feedback.
 */
object RevayatoMotion {
    const val Fast = 180
    const val Standard = 280
    const val Slow = 460
    const val Hero = 900

    /** Fast, confident start; long settle. Used for page and sheet motion. */
    val Decelerate = CubicBezierEasing(0.16f, 1f, 0.30f, 1f)

    /** Symmetric for reversible content swaps. */
    val StandardEasing = CubicBezierEasing(0.42f, 0f, 0.20f, 1f)

    /** Page transition curve — a little softer than [Decelerate]. */
    val Emphasized = CubicBezierEasing(0.22f, 0.72f, 0.20f, 1f)

    val PressSpring = spring<Float>(dampingRatio = 0.62f, stiffness = 520f)
}

/**
 * Press feedback shared by posters, rows and icon controls. Pair it with a
 * no-ripple `clickable` that uses the same [interactionSource] so the whole
 * tile reacts as one surface.
 */
@Composable
fun rememberedPressScale(
    interactionSource: MutableInteractionSource,
    pressedScale: Float = 0.965f,
): Float {
    val pressed by interactionSource.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) pressedScale else 1f,
        animationSpec = RevayatoMotion.PressSpring,
        label = "revayatoPressScale",
    )
    return scale
}

/** Apply a press scale without asking the caller to know about graphics layers. */
fun Modifier.motionScale(scale: Float): Modifier =
    graphicsLayer { scaleX = scale; scaleY = scale }
