package io.github.squarepot.app.bench

import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.SystemClock
import androidx.documentfile.provider.DocumentFile
import io.github.squarepot.app.decoder.DecoderInput
import io.github.squarepot.app.decoder.TagDecoder
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Runs every decoder over every photo in a folder the user picked, at the live analysis
 * resolution, scores the results against the folder's [BenchManifest] when there is one, and
 * writes the report as JSON next to the photos.
 *
 * Photos are made upright and scaled so that the long side is [ANALYSIS_LONG_SIDE] px, what the
 * camera analysis sees, so that the numbers match live use rather than full-resolution stills.
 */
class BenchRunner(private val context: Context, private val decoders: List<TagDecoder>) {

    class Result(val summary: BenchSummary, val photos: Int, val labelledPhotos: Int, val outputName: String)

    private val loader = BenchImageLoader(context.contentResolver, ANALYSIS_LONG_SIDE)

    /** Blocks. [onProgress] is called with (done, total) from the calling thread. */
    fun run(folder: Uri, onProgress: (Int, Int) -> Unit): Result {
        val tree = requireNotNull(DocumentFile.fromTreeUri(context, folder)) { "Not a folder: $folder" }
        val manifest = readManifest(tree)
        val photos = tree.listFiles()
            .filter { it.isFile && it.type?.startsWith("image/") == true }
            .sortedBy { it.name }
        val outcomes = mutableListOf<PhotoOutcome>()
        val photoJson = JSONArray()

        photos.forEachIndexed { index, photo ->
            val name = photo.name ?: photo.uri.toString()
            val expected = manifest[name]
            val image = loader.load(photo.uri)
            if (image == null) {
                photoJson.put(JSONObject().put("name", name).put("error", "cannot decode image"))
            } else {
                if (index == 0) warmUp(image.bitmap)
                val measured = decoders.map { measure(name, it, image.bitmap, expected) }
                outcomes += measured
                photoJson.put(photoJson(name, image, expected, measured))
                image.bitmap.recycle()
            }
            onProgress(index + 1, photos.size)
        }

        val missing = BenchManifest.missingPhotos(manifest, photos.map { it.name.orEmpty() })
        val summary = BenchSummary.of(outcomes)
        val outputName = "squarepot-bench-" + SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(Date())
        val report = JSONObject()
            .put("format", FORMAT)
            .put("device", deviceJson())
            .put("analysisLongSide", ANALYSIS_LONG_SIDE)
            .put("repeats", REPEATS)
            .put("manifest", if (manifest.isEmpty()) JSONObject.NULL else BenchManifest.FILE_NAME)
            .put("missingPhotos", JSONArray(missing))
            .put("summary", summaryJson(summary))
            .put("photos", photoJson)
        write(tree, outputName, report)
        val labelled = photos.count { (it.name ?: "") in manifest }
        return Result(summary, photos.size, labelled, "$outputName.json")
    }

    private fun readManifest(tree: DocumentFile): Map<String, Expectation> {
        val file = tree.findFile(BenchManifest.FILE_NAME) ?: return emptyMap()
        val text = context.contentResolver.openInputStream(file.uri)?.use { it.readBytes().decodeToString() }
        return BenchManifest.parse(requireNotNull(text) { "Cannot read ${BenchManifest.FILE_NAME}" })
    }

    private fun measure(photo: String, decoder: TagDecoder, bitmap: Bitmap, expected: Expectation?): PhotoOutcome {
        val input = DecoderInput.Still(bitmap)
        var codes = emptySet<String>()
        val millis = List(REPEATS) { run ->
            val start = SystemClock.elapsedRealtimeNanos()
            val found = decoder.decode(input)
            val ms = (SystemClock.elapsedRealtimeNanos() - start) / NANOS_PER_MILLI
            if (run == 0) codes = found.map { it.code.value }.toSet()
            ms
        }
        return PhotoOutcome(photo, decoder.id, codes, millis, expected)
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
        const val ANALYSIS_LONG_SIDE = 1280
        const val REPEATS = 3
        private const val FORMAT = 3
        private const val WARM_UP_RUNS = 2
        private const val NANOS_PER_MILLI = 1_000_000f
    }
}
