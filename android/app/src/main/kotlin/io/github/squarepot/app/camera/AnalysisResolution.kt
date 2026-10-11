// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.util.Size
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy

/**
 * The size of the frames the decoders see. The spike compares them: labels seen at an angle from
 * arm's length are only 1–4 px per module at 720p, at or below what either decoder can read.
 */
enum class AnalysisResolution {
    P720,
    P1080,

    /** The largest 16:9 analysis size the camera offers, even if the frame rate drops. */
    MAX,
    ;

    fun selector(): ResolutionSelector {
        val builder = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
        when (this) {
            P720 -> builder.setResolutionStrategy(closestTo(SIZE_720P))

            P1080 -> builder.setResolutionStrategy(closestTo(SIZE_1080P))

            MAX ->
                builder
                    .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
                    .setAllowedResolutionMode(ResolutionSelector.PREFER_HIGHER_RESOLUTION_OVER_CAPTURE_RATE)
        }
        return builder.build()
    }

    private fun closestTo(size: Size) =
        ResolutionStrategy(size, ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
}

private val SIZE_720P = Size(1280, 720)
private val SIZE_1080P = Size(1920, 1080)
