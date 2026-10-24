// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.content.Context
import android.text.format.DateUtils
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.withStyle
import io.github.squarepot.app.R
import io.github.squarepot.app.data.CaptionLine
import io.github.squarepot.app.data.TextRun
import io.github.squarepot.app.data.caption
import io.github.squarepot.app.recognition.TagCode
import java.time.LocalDate

/** What the caption of a selected label says. */
sealed interface CaptionContent {
    /** The local copy has not answered yet: the number tab alone. */
    data object Pending : CaptionContent

    data class Lines(val lines: List<CaptionLine>) : CaptionContent

    /** The copy has no plant with this number; [hint] says how old the copy is. */
    data class NotInCopy(val hint: String) : CaptionContent

    /** Several plants share the number. */
    data object Collision : CaptionContent
}

/** The words captions need, in the UI language. */
class CaptionTexts(private val context: Context) {
    val appPick: String = context.getString(R.string.caption_app_pick)
    val yourPick: String = context.getString(R.string.caption_your_pick)
    val yourPickCopy: String = context.getString(R.string.caption_your_pick_copy)
    val notInCopy: String = context.getString(R.string.caption_not_in_copy)
    val collision: String = context.getString(R.string.caption_collision)

    /** An age in whole months: months under two years, whole years from then on, as the schema says. */
    fun age(months: Int): String = if (months < MONTHS_SHOWN_AS_MONTHS) {
        context.resources.getQuantityString(R.plurals.age_months, months, months)
    } else {
        val years = months / MONTHS_PER_YEAR
        context.resources.getQuantityString(R.plurals.age_years, years, years)
    }

    /** Why a number is not in the copy: how old the copy is, or that there is none yet. */
    fun notInCopyHint(refreshedAt: Long?): String = if (refreshedAt == null) {
        context.getString(R.string.caption_no_copy_hint)
    } else {
        val time = DateUtils.formatDateTime(context, refreshedAt, DATE_AND_TIME)
        context.getString(R.string.caption_not_in_copy_hint, time)
    }

    private companion object {
        const val DATE_AND_TIME = DateUtils.FORMAT_SHOW_TIME or DateUtils.FORMAT_SHOW_DATE
        const val MONTHS_SHOWN_AS_MONTHS = 24
        const val MONTHS_PER_YEAR = 12
    }
}

/** [CaptionTexts] for the current context, again when the language changes. */
@Composable
fun rememberCaptionTexts(): CaptionTexts {
    val context = LocalContext.current
    val configuration = LocalConfiguration.current
    return remember(context, configuration) { CaptionTexts(context) }
}

/** What the caption of the label [code] says, from the plants looked up so far. */
fun CameraUiState.captionContent(code: TagCode, texts: CaptionTexts, today: LocalDate): CaptionContent {
    val found = plants[code.value] ?: return CaptionContent.Pending
    return when (found.size) {
        0 -> CaptionContent.NotInCopy(texts.notInCopyHint(refreshedAt))
        1 -> CaptionContent.Lines(caption(found.single(), schema, captionFields, captions.nameMode, today))
        else -> CaptionContent.Collision
    }
}

/** A caption line as text; a custom column's name is set in [muted]. */
fun CaptionLine.annotated(muted: Color, age: (Int) -> String): AnnotatedString = when (this) {
    is CaptionLine.FieldNumber -> AnnotatedString(text)

    is CaptionLine.Name -> runs.annotated()

    is CaptionLine.Age -> AnnotatedString(age(months))

    is CaptionLine.Custom -> buildAnnotatedString {
        withStyle(SpanStyle(color = muted)) { append("$column: ") }
        append(value)
    }

    is CaptionLine.Text -> runs.annotated()
}

/** Text runs with their italics. */
fun List<TextRun>.annotated(): AnnotatedString = buildAnnotatedString {
    this@annotated.forEach { run ->
        if (run.italic) withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(run.text) } else append(run.text)
    }
}
