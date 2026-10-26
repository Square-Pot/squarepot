// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.app.Application
import android.net.Uri
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.core.graphics.scale
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.bench.BenchImageLoader
import io.github.squarepot.app.data.api.SightingKind
import io.github.squarepot.app.decoder.DecoderInput
import io.github.squarepot.app.decoder.ZxingCppTagDecoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.max

/** A photo taken from a plant's card, waiting for the owner's "Save". */
data class PhotoReview(
    val shot: Shot,
    /** The plant whose card took it. */
    val cardTag: String,
    /** The plants of the copy whose labels the photo shows, the card's first; null while it is read. */
    val labels: List<String>? = null,
    /** The plant the photo will belong to. */
    val owner: String = cardTag,
    val comment: String = "",
    /** Also mark the other plants on the photo as seen. */
    val alsoSeen: Boolean = true,
    val preview: ImageBitmap? = null,
) {
    /** Two plants or more on the photo: the owner says whose it is. */
    val askWhose: Boolean get() = labels.orEmpty().size > 1

    val others: List<String> get() = labels.orEmpty().filter { it != owner }
}

/** The plants of the copy ([known]) a photo of [cardTag]'s card shows, given the [decoded] label numbers. */
fun photoLabels(cardTag: String, decoded: List<String>, known: Set<String>): List<String> =
    (listOf(cardTag) + decoded.filter { it in known }).distinct()

/**
 * The photo just taken in inventory mode: read for labels (a second label asks whose photo it
 * is), commented, then queued for upload with "Save", or dropped with "Retake".
 */
class PhotoViewModel(application: Application) : AndroidViewModel(application) {
    private val container = (application as SquarepotApplication).container
    private val _review = MutableStateFlow<PhotoReview?>(null)
    val review: StateFlow<PhotoReview?> = _review.asStateFlow()

    /** [shot] was taken from the card of [tag]: shown for review while its labels are read. */
    fun taken(tag: String, shot: Shot) {
        _review.value = PhotoReview(shot, tag)
        viewModelScope.launch {
            val (preview, decoded) = withContext(Dispatchers.Default) { read(shot) }
            val known = container.localCopy.plants().first().mapNotNullTo(HashSet()) { it.tag }
            _review.update { review ->
                review?.takeIf { it.shot === shot }?.copy(labels = photoLabels(tag, decoded, known), preview = preview)
            }
        }
    }

    fun setOwner(tag: String) = _review.update { it?.copy(owner = tag) }

    fun setComment(comment: String) = _review.update { it?.copy(comment = comment) }

    fun setAlsoSeen(on: Boolean) = _review.update { it?.copy(alsoSeen = on) }

    /** Queues the photo for its owner, and a sighting for each other plant on it if asked. */
    fun save() {
        val review = _review.value ?: return
        _review.value = null
        viewModelScope.launch {
            container.outbox.addPhoto(review.owner, review.shot.file, review.shot.takenAt, review.comment)
            if (review.alsoSeen) review.others.forEach { container.outbox.seen(it, SightingKind.SEEN) }
        }
    }

    /** Drops the photo, to take another. */
    fun discard() {
        val review = _review.value ?: return
        _review.value = null
        viewModelScope.launch(Dispatchers.IO) { review.shot.file.delete() }
    }

    /** A small upright copy to show, and the label numbers the photo shows. */
    private fun read(shot: Shot): Pair<ImageBitmap?, List<String>> {
        val loader = BenchImageLoader(getApplication<Application>().contentResolver, DECODE_LONG_SIDE)
        val image = loader.load(Uri.fromFile(shot.file)) ?: return null to emptyList()
        val codes = ZxingCppTagDecoder().use { decoder ->
            runCatching { decoder.decode(DecoderInput.Still(image.bitmap)) }.getOrDefault(emptyList())
        }
        val bitmap = image.bitmap
        val factor = PREVIEW_LONG_SIDE.toFloat() / max(bitmap.width, bitmap.height)
        val preview = bitmap.scale((bitmap.width * factor).toInt(), (bitmap.height * factor).toInt())
        if (preview !== bitmap) bitmap.recycle()
        return preview.asImageBitmap() to codes.map { it.code.value }
    }

    private companion object {
        /** As large as the server's photo, so a label it would read is read here too. */
        const val DECODE_LONG_SIDE = 2560
        const val PREVIEW_LONG_SIDE = 1080
    }
}
