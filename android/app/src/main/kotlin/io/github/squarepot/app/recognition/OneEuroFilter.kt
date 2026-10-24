// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import kotlin.math.PI
import kotlin.math.abs

/**
 * The 1€ filter (Casiez, Roussel and Vogel, CHI 2012): a low-pass filter whose cutoff rises with
 * the signal's speed, so a still value is smoothed hard and a moving one is followed with little
 * lag. [minCutoff] (Hz) sets the smoothing at rest, [beta] how fast the cutoff rises with speed
 * (per unit of the value per second), [derivativeCutoff] (Hz) the smoothing of the speed itself.
 */
class OneEuroFilter(private val minCutoff: Float, private val beta: Float, private val derivativeCutoff: Float = 1f) {
    private var value = 0f
    private var speed = 0f
    private var lastMillis: Long? = null

    fun filter(x: Float, timestampMillis: Long): Float {
        val last = lastMillis
        if (last == null) {
            // The first value passes through.
            value = x
            lastMillis = timestampMillis
        } else if (timestampMillis > last) {
            val dt = (timestampMillis - last) / MILLIS_PER_SECOND
            speed = lowPass(speed, (x - value) / dt, alpha(derivativeCutoff, dt))
            value = lowPass(value, x, alpha(minCutoff + beta * abs(speed), dt))
            lastMillis = timestampMillis
        }
        // A repeated or older timestamp changes nothing.
        return value
    }

    private fun lowPass(previous: Float, x: Float, alpha: Float) = previous + alpha * (x - previous)

    private fun alpha(cutoff: Float, dt: Float): Float {
        val tau = 1f / (2f * PI.toFloat() * cutoff)
        return 1f / (1f + tau / dt)
    }

    private companion object {
        const val MILLIS_PER_SECOND = 1000f
    }
}
