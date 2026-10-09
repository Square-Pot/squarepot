// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import io.github.squarepot.app.recognition.TagCode

/** What a photo is known to show: the label numbers in it and the conditions it was taken in. */
data class Expectation(val codes: Set<String>, val conditions: Set<String>)

/**
 * The ground truth of a bench folder: a `bench.csv` file next to the photos.
 *
 * ```
 * file,codes,conditions
 * IMG_0001.jpg,004217,glare
 * IMG_0002.jpg,004218 004219,tilt;lowlight
 * IMG_0003.jpg,,lowlight
 * ```
 *
 * `codes` are the label numbers visible in the photo, separated by spaces; empty means the photo
 * holds no readable label (any decode is wrong). `conditions` are free-form tags separated by `;`,
 * such as `glare`, `tilt`, `dirt`, `lowlight`, `far`. Lines starting with `#` and blank lines are
 * ignored. Photos not listed are decoded but not scored; rows whose photo is not in the folder are
 * reported by [missingPhotos].
 */
object BenchManifest {
    const val FILE_NAME = "bench.csv"
    private const val HEADER = "file,codes,conditions"
    private const val COLUMNS = 3

    /** Parses a manifest; throws [IllegalArgumentException] naming the bad line. */
    fun parse(text: String): Map<String, Expectation> {
        val rows = text.lineSequence()
            .mapIndexed { i, line -> i + 1 to line.trim() }
            .filter { (_, line) -> line.isNotEmpty() && !line.startsWith("#") }
            .toList()
        require(rows.firstOrNull()?.second?.lowercase() == HEADER) { "$FILE_NAME must start with '$HEADER'" }

        val result = linkedMapOf<String, Expectation>()
        rows.drop(1).forEach { (number, line) ->
            val cells = line.split(',')
            require(cells.size == COLUMNS) { "$FILE_NAME line $number: expected $COLUMNS columns, got ${cells.size}" }
            val (file, codes, conditions) = cells.map { it.trim() }
            require(file.isNotEmpty()) { "$FILE_NAME line $number: empty file name" }
            require(file !in result) { "$FILE_NAME line $number: $file is listed twice" }
            val parsed = codes.split(' ').filter { it.isNotEmpty() }.map { raw ->
                requireNotNull(TagCode.parse(raw)) { "$FILE_NAME line $number: '$raw' is not a label number" }.value
            }
            result[file] = Expectation(
                codes = parsed.toSet(),
                conditions = conditions.split(';').map { it.trim().lowercase() }.filter { it.isNotEmpty() }.toSet(),
            )
        }
        return result
    }

    /** Files listed in [manifest] that are not among [photos], in manifest order. */
    fun missingPhotos(manifest: Map<String, Expectation>, photos: Collection<String>): List<String> =
        manifest.keys.filter { it !in photos }
}
