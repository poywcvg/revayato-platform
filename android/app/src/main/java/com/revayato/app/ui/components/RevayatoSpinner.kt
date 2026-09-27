package com.revayato.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.BrandMint
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * The Revayato brand loading spinner: ten rounded blades arranged radially with
 * a staggered ripple, so the same motion the web player uses shows up in-app.
 *
 * Mirrors the web LoadingSpinnerA component (10 blades, 1s ripple, per-blade
 * 0.1s stagger). [size] is the full footprint the blade ring occupies.
 */
@Composable
fun RevayatoSpinner(
    modifier: Modifier = Modifier,
    size: Dp = 44.dp,
    color: Color = BrandMint,
) {
    val bladeCount = 10
    val periodMs = 1000
    val transition = rememberInfiniteTransition(label = "revayato-spinner")
    // A single normalized 0..1 clock; each blade reads it with its own phase.
    val clock by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = periodMs, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "clock",
    )

    Canvas(modifier = modifier.size(size)) {
        val center = Offset(this.size.width / 2f, this.size.height / 2f)
        val base = this.size.minDimension / 6f
        val bladeW = base * 0.5f
        val bladeLen = base * 1.5f
        // Rest distance from centre to the blade's mid-point (matches web translate).
        val restRadius = base * 2.25f
        val rippleRadius = base * 3.0f

        for (i in 0 until bladeCount) {
            val phase: Float = (i + 1) / bladeCount.toFloat()
            // Ripple: blade pushes outward around its own phase point in the cycle.
            val local: Float = (clock + phase) % 1f
            val pulse: Float = 1f - kotlin.math.abs(local - 0.5f) * 2f // triangle 0..1..0
            val radius: Float = restRadius + (rippleRadius - restRadius) * pulse
            val angleDeg: Float = (i + 1) * 36f
            val angleRad: Double = (angleDeg - 90f).toDouble() * PI / 180.0
            val dirX: Float = cos(angleRad).toFloat()
            val dirY: Float = sin(angleRad).toFloat()
            val cx: Float = center.x + dirX * radius
            val cy: Float = center.y + dirY * radius
            // Draw the blade as a rounded capsule pointing outward from centre.
            val half: Float = bladeLen / 2f
            val alpha: Float = max(0.35f, 0.35f + 0.65f * pulse)
            drawLine(
                color = color.copy(alpha = alpha),
                start = Offset(cx - dirX * half, cy - dirY * half),
                end = Offset(cx + dirX * half, cy + dirY * half),
                strokeWidth = bladeW,
                cap = StrokeCap.Round,
            )
        }
    }
}
