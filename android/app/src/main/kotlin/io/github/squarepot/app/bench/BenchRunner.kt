// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.SystemClock
import androidx.documentfile.provider.DocumentFile
import io.github.squarepot.app.decoder.DecoderInput
import io.github.squarepot.app.decoder.TagDecoder
import io.github.squarepot.app.recognition.Detection
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Runs every decoder over every photo in a folder the user picked, at each analysis size in
 * [ANALYSIS_LONG_SIDES], scores the results against the folder's [BenchManifest] when there is
 * one, and writes the report as JSON next to the photos.
 *
 * Photos are made upright and scaled so that the long side matches a camera analysis frame
 * (1280 for 720p, 1920 for 1080p, 2560 for a larger stream), for the live mode, and decoded once
 * more at their own resolution, for the photo mode. Photos smaller than a size are decoded at
 * their own size. Each decoder is reported per size, as `<decoder>@<long side>` or
 * `<decoder>@full`.
 */
class BenchRunner(private val context: Context, private val decoders: List<TagDecoder>) {

    class Result(val summary: BenchSummary, val photos: Int, val labelledPhotos: Int, val outputName: String)

    private val loaders = ANALYSIS_LONG_SIDES.map { BenchImageLoader(context.contentResolver, it) }

    /** Blocks. [onProgress] is called with (done, total) from the calling thread. */
    fun run(folder: Uri, onProgress: (Int, Int) -> Unit): Result {
        val tree = requireNotNull(DocumentFile.fromTreeUri(context, folder)) { "Not a folder: $folder" }
        val manifest = readManifest(tree)
        val photos = tree.listFiles()
            .filter { it.isFile && it.type?.startsWith("image/") == true }
            .map { (it.name ?: it.uri.toString()) to it }
            .sortedBy { (name, _) -> name }
        val outcomes = mutableListOf<PhotoOutcome>()
        val photoJson = JSONArray()

        photos.forEachIndexed { index, (name, photo) ->
            val expected = manifest[name]
            loaders.forEach { loader ->
                val (json, measured) = benchPhoto(name, photo.uri, expected, loader, warm = index == 0)
                photoJson.put(json)
                outcomes += measured
            }
            onProgress(index + 1, photos.size)
        }

        val missing = BenchManifest.missingPhotos(manifest, photos.map { (name, _) -> name })
        val summary = BenchSummary.of(outcomes)
        val outputName = "squarepot-bench-" + SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(Date())
        val report = JSONObject()
            .put("format", FORMAT)
            .put("app", appJson())
            .put("device", deviceJson())
            .put("analysisLongSides", JSONArray(ANALYSIS_LONG_SIDES.map(::sizeLabel)))
            .put("repeats", REPEATS)
            .put("manifest", if (manifest.isEmpty()) JSONObject.NULL else BenchManifest.FILE_NAME)
            .put("missingPhotos", JSONArray(missing))
            .put("summary", summaryJson(summary))
            .put("photos", photoJson)
        write(tree, outputName, report)
        val labelled = photos.count { (name, _) -> name in manifest }
        return Result(summary, photos.size, labelled, "$outputName.json")
    }

    /** Decodes one photo at one size with every decoder; returns its JSON entry and the outcomes. */
    private fun benchPhoto(
        name: String,
        uri: Uri,
        expected: Expectation?,
        loader: BenchImageLoader,
        warm: Boolean,
    ): Pair<JSONObject, List<PhotoOutcome>> {
        val longSide = loader.longSide
        val image = loader.load(uri)
        if (image == null) {
            val error = JSONObject()
                .put("name", name)
                .put("longSide", sizeLabel(longSide))
                .put("error", "cannot decode image")
            return error to emptyList()
        }
        if (warm) warmUp(image.bitmap)
        val measured = decoders.map { measure(name, it, "${it.id}@${sizeLabel(longSide)}", image.bitmap, expected) }
        val json = photoJson(name, image, expected, measured).put("longSide", sizeLabel(longSide))
        image.bitmap.recycle()
        return json to measured
    }

    private fun readManifest(tree: DocumentFile): Map<String, Expectation> {
        val file = tree.findFile(BenchManifest.FILE_NAME) ?: return emptyMap()
        val text = context.contentResolver.openInputStream(file.uri)?.use { it.readBytes().decodeToString() }
        return BenchManifest.parse(requireNotNull(text) { "Cannot read ${BenchManifest.FILE_NAME}" })
    }

    private fun measure(
        photo: String,
        decoder: TagDecoder,
        id: String,
        bitmap: Bitmap,
        expected: Expectation?,
    ): PhotoOutcome {
        val input = DecoderInput.Still(bitmap)
        var found = emptyList<Detection>()
        val millis = List(REPEATS) { run ->
            val start = SystemClock.elapsedRealtimeNanos()
            val detections = decoder.decode(input)
            val ms = (SystemClock.elapsedRealtimeNanos() - start) / NANOS_PER_MILLI
            if (run == 0) found = detections
            ms
        }
        val codes = found.map { it.code.value }.toSet()
        return PhotoOutcome(photo, id, codes, millis, expected, found.maxByOrNull { it.area }?.code?.value)
    }

    /** First calls load models and native code; keep them out of the timings. */
    private fun warmUp(bitmap: Bitmap) {
        repeat(WARM_UP_RUNS) { decoders.forEach { it.decode(DecoderInput.Still(bitmap)) } }
    }

    private fun write(tree: DocumentFile, name: String, report: JSONObject) {
        val file = requireNotNull(tree.createFile("application/json", name)) { "Cannot create $name" }
        context.contentResolver.openOutputStream(file.uri)?.use {
            it.write(report.toString(2).toByteArray())
        } ?: error("Cannot write $name")
    }

    companion object {
        /** Stands for a photo's own resolution in [ANALYSIS_LONG_SIDES]. */
        const val FULL_RESOLUTION = Int.MAX_VALUE
        val ANALYSIS_LONG_SIDES = listOf(1280, 1920, 2560, FULL_RESOLUTION)

        fun sizeLabel(longSide: Int): String = if (longSide == FULL_RESOLUTION) "full" else longSide.toString()

        const val REPEATS = 3
        private const val FORMAT = 4
        private const val WARM_UP_RUNS = 2
        private const val NANOS_PER_MILLI = 1_000_000f
    }
}
