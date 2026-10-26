// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Which plants a photo from a card shows, and when the owner is asked whose it is. */
class PhotoReviewTest {
    private val known = setOf("004217", "004218", "004219")
    private val shot = Shot(File("shot.jpg"), takenAt = 0)

    @Test
    fun `a photo is the card's plant's, with the other plants of the copy it shows`() {
        assertEquals(listOf("004217"), photoLabels("004217", decoded = emptyList(), known))
        assertEquals(listOf("004217"), photoLabels("004217", listOf("004217", "999999"), known))
        assertEquals(listOf("004217", "004218"), photoLabels("004217", listOf("004218", "004217", "004218"), known))
    }

    @Test
    fun `one plant on the photo asks nothing`() {
        val review = PhotoReview(shot, "004217", labels = listOf("004217"))
        assertFalse(review.askWhose)
        assertTrue(review.others.isEmpty())
    }

    @Test
    fun `two plants on the photo ask whose it is, and the other can be marked as seen`() {
        val review = PhotoReview(shot, "004217", labels = listOf("004217", "004218"))
        assertTrue(review.askWhose)
        assertEquals(listOf("004218"), review.others)
        assertEquals(listOf("004217"), review.copy(owner = "004218").others)
    }

    @Test
    fun `nothing is asked while the photo is being read`() {
        assertFalse(PhotoReview(shot, "004217").askWhose)
    }
}
