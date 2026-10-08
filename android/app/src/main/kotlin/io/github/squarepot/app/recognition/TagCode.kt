package io.github.squarepot.app.recognition

/**
 * A plant label number: exactly six decimal digits, as encoded in a 10×10 Data Matrix.
 *
 * The label format is fixed by the project; anything else read from a symbol is not a label.
 * `000000` is reserved and never issued (docs/adr/0001-label-code-format.md).
 */
@JvmInline
value class TagCode private constructor(val value: String) {
    override fun toString(): String = value

    companion object {
        private const val LENGTH = 6
        private const val RESERVED = "000000"

        /** Returns the code, or null when [raw] is not a valid label payload. */
        fun parse(raw: String?): TagCode? =
            raw?.takeIf { it.length == LENGTH && it != RESERVED && it.all { c -> c in '0'..'9' } }?.let(::TagCode)
    }
}
