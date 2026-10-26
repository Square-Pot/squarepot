// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.content.Context
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.view.LifecycleCameraController
import androidx.core.content.ContextCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import java.util.UUID
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** A photo just taken: the JPEG in the app's cache and when it was taken, epoch millis. */
class Shot(val file: File, val takenAt: Long)

/**
 * Takes full-resolution photos with the live camera's controller, which inventory mode binds
 * with photo capture next to analysis. The live camera sets [controller] while it is on screen.
 */
class Shutter {
    var controller: LifecycleCameraController? = null

    /** Takes a photo into the cache; null when the camera is not ready. Throws [ImageCaptureException]. */
    suspend fun take(context: Context): Shot? {
        val camera = controller ?: return null
        val file = File(context.cacheDir, "shots").apply { mkdirs() }.resolve("${UUID.randomUUID()}.jpg")
        val takenAt = System.currentTimeMillis()
        suspendCancellableCoroutine { done ->
            camera.takePicture(
                ImageCapture.OutputFileOptions.Builder(file).build(),
                ContextCompat.getMainExecutor(context),
                object : ImageCapture.OnImageSavedCallback {
                    override fun onImageSaved(output: ImageCapture.OutputFileResults) = done.resume(Unit)

                    override fun onError(exception: ImageCaptureException) = done.resumeWithException(exception)
                },
            )
        }
        return Shot(file, takenAt)
    }
}
