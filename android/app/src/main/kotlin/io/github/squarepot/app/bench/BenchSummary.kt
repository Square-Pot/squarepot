package io.github.squarepot.app.bench

import kotlin.math.ceil

/**
 * What one decoder found on one photo, how long each repeated run took, and what the photo is
 * known to show ([expected] is null for photos missing from the manifest).
 */
data class PhotoOutcome(
    val photo: String,
    val decoderId: String,
    val codes: Set<String>,
    val millis: List<Float>,
    val expected: Expectation? = null,
) {
    val correct: Set<String> get() = expected?.let { codes intersect it.codes }.orEmpty()
    val missed: Set<String> get() = expected?.let { it.codes - codes }.orEmpty()
    val wrong: Set<String> get() = expected?.let { codes - it.codes }.orEmpty()
}

/** Scored decodes over a set of labelled photos: expected codes found, missed, and wrong reads. */
data class Score(val photos: Int, val expected: Int, val correct: Int, val wrong: Int) {
    /** Share of expected codes that were read, 0 when nothing was expected. */
    val rate: Float get() = if (expected == 0) 0f else correct.toFloat() / expected

    companion object {
        fun of(outcomes: List<PhotoOutcome>) = Score(
            photos = outcomes.size,
            expected = outcomes.sumOf { it.expected?.codes?.size ?: 0 },
            correct = outcomes.sumOf { it.correct.size },
            wrong = outcomes.sumOf { it.wrong.size },
        )
    }
}

/** Per-decoder totals over a bench run. */
data class DecoderSummary(
    val decoderId: String,
    val photos: Int,
    val photosDecoded: Int,
    val codes: Int,
    val medianMillis: Float,
    val p95Millis: Float,
    /** Over photos listed in the manifest. */
    val labelled: Score,
    /** The same, per condition tag; a photo with several tags counts under each. */
    val byCondition: Map<String, Score>,
)

data class BenchSummary(
    val decoders: List<DecoderSummary>,
    /** Photos on which exactly one decoder found something, by that decoder's id. */
    val onlyDecodedBy: Map<String, Int>,
    val decodedByNone: Int,
) {
    companion object {
        fun of(outcomes: List<PhotoOutcome>): BenchSummary {
            val decoders = outcomes.groupBy { it.decoderId }.map { (id, list) -> decoderSummary(id, list) }
                .sortedBy { it.decoderId }

            val byPhoto = outcomes.groupBy { it.photo }.values
            val onlyDecodedBy = byPhoto
                .mapNotNull { list -> list.filter { it.codes.isNotEmpty() }.singleOrNull()?.decoderId }
                .groupingBy { it }
                .eachCount()
            val decodedByNone = byPhoto.count { list -> list.all { it.codes.isEmpty() } }
            return BenchSummary(decoders, onlyDecodedBy, decodedByNone)
        }

        private fun decoderSummary(id: String, list: List<PhotoOutcome>): DecoderSummary {
            val millis = list.flatMap { it.millis }.sorted()
            val labelled = list.filter { it.expected != null }
            val conditions = labelled.flatMap { it.expected?.conditions.orEmpty() }.toSortedSet()
            return DecoderSummary(
                decoderId = id,
                photos = list.size,
                photosDecoded = list.count { it.codes.isNotEmpty() },
                codes = list.sumOf { it.codes.size },
                medianMillis = percentile(millis, MEDIAN),
                p95Millis = percentile(millis, P95),
                labelled = Score.of(labelled),
                byCondition = conditions.associateWith { c ->
                    Score.of(labelled.filter { c in it.expected?.conditions.orEmpty() })
                },
            )
        }

        private const val MEDIAN = 0.5
        private const val P95 = 0.95

        private fun percentile(sorted: List<Float>, p: Double): Float {
            if (sorted.isEmpty()) return 0f
            val rank = ceil(p * sorted.size).toInt().coerceIn(1, sorted.size)
            return sorted[rank - 1]
        }
    }
}
