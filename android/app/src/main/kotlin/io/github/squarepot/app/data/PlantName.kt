// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.DisplayDto
import io.github.squarepot.app.data.api.FieldSchemaDto

/**
 * The plant's botanical name: the schema's computed `name`, composed from its `from` fields in
 * order, skipping empty ones, each with its display rules (prefix, case, italics, quotes), as in
 * "*Lithops* aff. *lesliei* ‘Albinica’". Mirrors the server's label caption
 * (server/src/squarepot_server/labels/caption.py). Empty when there is no schema or no such field.
 */
fun botanicalName(schema: FieldSchemaDto?, fields: Map<String, String>): List<TextRun> {
    schema ?: return emptyList()
    val displays = schema.fields.associate { it.key to (it.display ?: DisplayDto()) }
    val parts = schema.computed.firstOrNull { it.key == NAME }?.from.orEmpty()
    val runs = mutableListOf<TextRun>()
    parts.forEach { key ->
        val value = fields[key]?.trim().orEmpty()
        if (value.isEmpty()) return@forEach
        if (runs.isNotEmpty()) runs += TextRun(" ")
        runs += styled(value, displays[key] ?: DisplayDto())
    }
    return runs
}

/** The name as plain text, without italics. */
fun List<TextRun>.plain(): String = joinToString("") { it.text }

private fun styled(value: String, display: DisplayDto): List<TextRun> {
    var text = applyCase(value, display.case)
    if (display.quote) text = "‘$text’"
    val prefix = display.prefix?.let { listOf(TextRun("$it ")) }.orEmpty()
    return prefix + TextRun(text, display.italic)
}

private fun applyCase(value: String, case: String): String = when (case) {
    "lower" -> value.lowercase()
    "upper" -> value.uppercase()
    "title" -> value.split(" ").joinToString(" ") { it.take(1).uppercase() + it.drop(1).lowercase() }
    else -> value
}

private const val NAME = "name"
