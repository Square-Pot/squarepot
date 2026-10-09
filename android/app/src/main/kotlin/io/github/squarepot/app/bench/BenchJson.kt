// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

// JSON pieces of the bench report, format 2.

/** The device a bench ran on, for comparing phones. */
internal fun deviceJson() = JSONObject()
    .put("manufacturer", Build.MANUFACTURER)
    .put("model", Build.MODEL)
    .put("sdk", Build.VERSION.SDK_INT)
    .put("abis", JSONArray(Build.SUPPORTED_ABIS.toList()))

/** One photo: how it was loaded, what it is known to show, and each decoder's result. */
internal fun photoJson(name: String, image: BenchImage, expected: Expectation?, outcomes: List<PhotoOutcome>) =
    JSONObject()
        .put("name", name)
        .put("width", image.bitmap.width)
        .put("height", image.bitmap.height)
        .put("exifRotation", image.exifRotation)
        .put("exifFlipped", image.exifFlipped)
        .put("expected", expected?.let(::expectationJson) ?: JSONObject.NULL)
        .put(
            "decoders",
            JSONObject().apply {
                outcomes.forEach { o ->
                    val result = JSONObject()
                        .put("codes", JSONArray(o.codes.sorted()))
                        .put("ms", JSONArray(o.millis.map { it.toDouble() }))
                    if (expected != null) {
                        result
                            .put("correct", JSONArray(o.correct.sorted()))
                            .put("missed", JSONArray(o.missed.sorted()))
                            .put("wrong", JSONArray(o.wrong.sorted()))
                    }
                    put(o.decoderId, result)
                }
            },
        )

/** Per-decoder totals, as in [BenchSummary]. */
internal fun summaryJson(summary: BenchSummary) = JSONObject()
    .put(
        "decoders",
        JSONArray(
            summary.decoders.map {
                JSONObject()
                    .put("id", it.decoderId)
                    .put("photos", it.photos)
                    .put("photosDecoded", it.photosDecoded)
                    .put("codes", it.codes)
                    .put("medianMs", it.medianMillis.toDouble())
                    .put("p95Ms", it.p95Millis.toDouble())
                    .put("labelled", scoreJson(it.labelled))
                    .put("byCondition", JSONObject(it.byCondition.mapValues { (_, s) -> scoreJson(s) }))
            },
        ),
    )
    .put("onlyDecodedBy", JSONObject(summary.onlyDecodedBy))
    .put("decodedByNone", summary.decodedByNone)

private fun expectationJson(e: Expectation) = JSONObject()
    .put("codes", JSONArray(e.codes.sorted()))
    .put("conditions", JSONArray(e.conditions.sorted()))

private fun scoreJson(s: Score) = JSONObject()
    .put("photos", s.photos)
    .put("expected", s.expected)
    .put("correct", s.correct)
    .put("wrong", s.wrong)
    .put("rate", s.rate.toDouble())
