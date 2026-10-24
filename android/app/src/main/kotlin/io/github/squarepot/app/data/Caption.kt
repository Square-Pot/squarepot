// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.FieldSchemaDto
import java.time.DateTimeException
import java.time.LocalDate
import java.time.Period

/**
 * One entry of a caption, like the server's label entries: a schema field, the computed name or
 * age, or a custom column.
 */
sealed interface CaptionField {
    /** A schema field, or the computed `name` or `age`, by key. */
    data class Field(val key: String) : CaptionField

    /** A custom column of the sheet, by name, shown as `Name: value`. */
    data class Custom(val column: String) : CaptionField
}

/** How a long botanical name is set. */
enum class NameMode {
    /** In full, on as many lines as it takes. */
    FULL,

    /** In full, cut after two lines. */
    TWO_LINES,

    /** The genus as its initial: "M. theresae var. albiflora". */
    SHORT_GENUS,
}

/** One line of a caption, ready to draw. */
sealed interface CaptionLine {
    /** The field number, set small. */
    data class FieldNumber(val text: String) : CaptionLine

    /** The botanical name; [maxLines] is null for no limit. */
    data class Name(val runs: List<TextRun>, val maxLines: Int?) : CaptionLine

    /** Whole months since seeding (or purchase); the UI words it. */
    data class Age(val months: Int) : CaptionLine

    /** A custom column as `Name: value`. */
    data class Custom(val column: String, val value: String) : CaptionLine

    /** Any other field, with its display rules. */
    data class Text(val runs: List<TextRun>) : CaptionLine
}

/**
 * The caption's fields until the owner chooses their own: field number, name, ex and the first
 * custom column of [customColumns] (the collections' columns, in order), if there is one. The
 * label number is on the number tab already. This is the app's own default (lead, 2026-10-25),
 * not the server's `overlay` preset, which holds only the name.
 */
fun defaultCaptionFields(customColumns: List<String>): List<CaptionField> =
    listOf(CaptionField.Field(FIELD_NUMBER), CaptionField.Field(NAME), CaptionField.Field(EX)) +
        customColumns.take(1).map { CaptionField.Custom(it) }

/** The lines of [plant]'s caption for [chosen], in order; entries the plant has no value for are left out. */
fun caption(
    plant: PlantView,
    schema: FieldSchemaDto?,
    chosen: List<CaptionField>,
    nameMode: NameMode,
    today: LocalDate,
): List<CaptionLine> {
    val values = plant.fields.associate { it.key to it.value }
    val displays = schema?.fields.orEmpty().associate { it.key to it.display }
    return chosen.mapNotNull { entry ->
        when (entry) {
            is CaptionField.Custom -> plant.custom[entry.column]?.trim()?.takeIf { it.isNotEmpty() }
                ?.let { CaptionLine.Custom(entry.column, it) }

            is CaptionField.Field -> when (entry.key) {
                NAME -> nameLine(plant, schema, values, nameMode)

                AGE -> ageInMonths(values, today)?.let { CaptionLine.Age(it) }

                else -> values[entry.key]?.trim()?.takeIf { it.isNotEmpty() }?.let { value ->
                    val runs = styled(value, displays[entry.key])
                    if (entry.key == FIELD_NUMBER) CaptionLine.FieldNumber(runs.plain()) else CaptionLine.Text(runs)
                }
            }
        }
    }
}

/** A neighbouring label's short name, genus initial and species: "M. theresae". Empty without a genus. */
fun shortName(plant: PlantView, schema: FieldSchemaDto?): List<TextRun> {
    val values = plant.fields.associate { it.key to it.value }
    val genus = values[GENUS]?.trim().orEmpty()
    if (genus.isEmpty()) return emptyList()
    return botanicalName(schema, listOfNotNull(GENUS to initial(genus), values[SPECIES]?.let { SPECIES to it }).toMap())
}

/** The caption as one line of plain text for the clipboard, entries joined by " · "; [age] words an age. */
fun List<CaptionLine>.copyText(age: (Int) -> String): String = joinToString(" · ") { line ->
    when (line) {
        is CaptionLine.FieldNumber -> line.text
        is CaptionLine.Name -> line.runs.plain()
        is CaptionLine.Age -> age(line.months)
        is CaptionLine.Custom -> "${line.column}: ${line.value}"
        is CaptionLine.Text -> line.runs.plain()
    }
}

/** Whole months since `seeding_date`, else `purchase_date`, as the schema's `age`; null without a usable date. */
fun ageInMonths(fields: Map<String, String>, today: LocalDate): Int? {
    val since = listOf(SEEDING_DATE, PURCHASE_DATE).firstNotNullOfOrNull { key -> fields[key]?.let(::parseDate) }
    return since?.let { Period.between(it, today).toTotalMonths().toInt() }?.takeIf { it >= 0 }
}

private fun nameLine(
    plant: PlantView,
    schema: FieldSchemaDto?,
    values: Map<String, String>,
    mode: NameMode,
): CaptionLine.Name? {
    val runs = when (mode) {
        NameMode.SHORT_GENUS -> values[GENUS]?.trim()?.takeIf { it.isNotEmpty() }
            ?.let { botanicalName(schema, values + (GENUS to initial(it))) }
            ?: plant.name

        else -> plant.name
    }
    if (runs.isEmpty()) return null
    return CaptionLine.Name(runs, if (mode == NameMode.TWO_LINES) 2 else null)
}

private fun initial(genus: String) = genus.take(1).uppercase() + "."

private fun parseDate(value: String): LocalDate? = try {
    LocalDate.parse(value.trim())
} catch (_: DateTimeException) {
    null
}

private const val NAME = "name"
private const val AGE = "age"
private const val FIELD_NUMBER = "field_number"
private const val EX = "ex"
private const val GENUS = "genus"
private const val SPECIES = "species"
private const val SEEDING_DATE = "seeding_date"
private const val PURCHASE_DATE = "purchase_date"
