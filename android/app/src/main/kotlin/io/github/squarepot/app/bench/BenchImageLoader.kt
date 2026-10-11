// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import kotlin.math.max

/** A photo as the bench decodes it: upright, scaled to the analysis size. */
class BenchImage(val bitmap: Bitmap, val exifRotation: Int, val exifFlipped: Boolean)

/**
 * Loads a photo the way the live camera would see it: EXIF orientation applied (phones usually
 * store photos sideways with an orientation tag, while camera frames arrive upright), and the
 * long side scaled down to [longSide] px.
 */
class BenchImageLoader(private val resolver: ContentResolver, val longSide: Int) {

    fun load(uri: Uri): BenchImage? {
        val sourceLongSide = sourceLongSideOf(uri)
        val decoded = if (sourceLongSide > 0) decodeSampled(uri, sampleSizeFor(sourceLongSide)) else null
        return decoded?.let { scaleAndOrient(it, uri) }
    }

    private fun sourceLongSideOf(uri: Uri): Int {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        return max(bounds.outWidth, bounds.outHeight)
    }

    /** Largest power-of-two subsampling that keeps the long side at or above the target. */
    private fun sampleSizeFor(sourceLongSide: Int): Int {
        var sample = 1
        while (sourceLongSide / (sample * 2) >= longSide) sample *= 2
        return sample
    }

    private fun decodeSampled(uri: Uri, sample: Int): Bitmap? {
        val options = BitmapFactory.Options().apply {
            inSampleSize = sample
            inPreferredConfig = Bitmap.Config.ARGB_8888
        }
        return resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
    }

    /** Scales the long side to [longSide] and applies the EXIF transform, in one matrix pass. */
    private fun scaleAndOrient(bitmap: Bitmap, uri: Uri): BenchImage {
        val factor = (longSide.toFloat() / max(bitmap.width, bitmap.height)).coerceAtMost(1f)
        val exif = resolver.openInputStream(uri)?.use { ExifInterface(it) }
        val rotation = exif?.rotationDegrees ?: 0
        val flipped = exif?.isFlipped ?: false
        // EXIF transpose/transverse are a rotation followed by a horizontal flip.
        val matrix = Matrix().apply {
            postScale(factor, factor)
            postRotate(rotation.toFloat())
            if (flipped) postScale(-1f, 1f)
        }
        if (matrix.isIdentity) return BenchImage(bitmap, rotation, flipped)
        val result = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        if (result !== bitmap) bitmap.recycle()
        return BenchImage(result, rotation, flipped)
    }
}
