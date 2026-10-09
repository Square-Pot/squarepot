// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import org.junit.Assert.assertEquals
import org.junit.Test

class BenchSummaryTest {
    private fun o(photo: String, decoder: String, vararg codes: String, ms: Float = 10f) =
        PhotoOutcome(photo, decoder, codes.toSet(), listOf(ms))

    @Test
    fun `counts decoded photos, codes and exclusive wins per decoder`() {
        val summary = BenchSummary.of(
            listOf(
                o("a.jpg", "mlkit", "111111", "222222", ms = 8f),
                o("a.jpg", "zxing-cpp", "111111", ms = 12f),
                o("b.jpg", "mlkit", ms = 9f),
                o("b.jpg", "zxing-cpp", "333333", ms = 14f),
                o("c.jpg", "mlkit", ms = 7f),
                o("c.jpg", "zxing-cpp", ms = 11f),
            ),
        )

        val ml = summary.decoders.single { it.decoderId == "mlkit" }
        assertEquals(3, ml.photos)
        assertEquals(1, ml.photosDecoded)
        assertEquals(2, ml.codes)
        assertEquals(8f, ml.medianMillis)

        val zx = summary.decoders.single { it.decoderId == "zxing-cpp" }
        assertEquals(2, zx.photosDecoded)
        assertEquals(14f, zx.p95Millis)

        assertEquals(mapOf("zxing-cpp" to 1), summary.onlyDecodedBy)
        assertEquals(1, summary.decodedByNone)
    }

    @Test
    fun `scores labelled photos per decoder and per condition`() {
        val glare = Expectation(setOf("111111"), setOf("glare"))
        val tiltGlare = Expectation(setOf("222222", "333333"), setOf("tilt", "glare"))
        val empty = Expectation(emptySet(), setOf("lowlight"))
        val outcomes = listOf(
            PhotoOutcome("a.jpg", "mlkit", setOf("111111"), listOf(1f), glare),
            PhotoOutcome("b.jpg", "mlkit", setOf("222222", "999999"), listOf(1f), tiltGlare),
            PhotoOutcome("c.jpg", "mlkit", setOf("444444"), listOf(1f), empty),
            PhotoOutcome("d.jpg", "mlkit", setOf("555555"), listOf(1f), expected = null),
        )

        val ml = BenchSummary.of(outcomes).decoders.single()
        assertEquals(Score(photos = 3, expected = 3, correct = 2, wrong = 2), ml.labelled)
        assertEquals(2f / 3, ml.labelled.rate, 1e-6f)
        assertEquals(Score(photos = 2, expected = 3, correct = 2, wrong = 1), ml.byCondition["glare"])
        assertEquals(Score(photos = 1, expected = 2, correct = 1, wrong = 1), ml.byCondition["tilt"])
        assertEquals(Score(photos = 1, expected = 0, correct = 0, wrong = 1), ml.byCondition["lowlight"])
        assertEquals(setOf("333333"), outcomes[1].missed)
    }

    @Test
    fun `empty run gives empty summary`() {
        val summary = BenchSummary.of(emptyList())
        assertEquals(emptyList<DecoderSummary>(), summary.decoders)
        assertEquals(0, summary.decodedByNone)
    }
}
