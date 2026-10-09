package io.github.squarepot.app.bench

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class BenchManifestTest {
    @Test
    fun `parses codes, conditions, empty rows and comments`() {
        val manifest = BenchManifest.parse(
            """
            # reference set v1
            file,codes,conditions
            IMG_0001.jpg,004217,glare
            IMG_0002.jpg, 004218  004219 , Tilt; lowlight

            IMG_0003.jpg,,lowlight
            """.trimIndent(),
        )
        assertEquals(Expectation(setOf("004217"), setOf("glare")), manifest["IMG_0001.jpg"])
        assertEquals(Expectation(setOf("004218", "004219"), setOf("tilt", "lowlight")), manifest["IMG_0002.jpg"])
        assertEquals(Expectation(emptySet(), setOf("lowlight")), manifest["IMG_0003.jpg"])
        assertEquals(3, manifest.size)
    }

    @Test
    fun `rejects a missing header, bad codes, wrong column counts and duplicates`() {
        listOf(
            "IMG_1.jpg,004217,glare",
            "file,codes,conditions\nIMG_1.jpg,4217,glare",
            "file,codes,conditions\nIMG_1.jpg,000000,",
            "file,codes,conditions\nIMG_1.jpg,004217",
            "file,codes,conditions\nIMG_1.jpg,004217,\nIMG_1.jpg,004218,",
            "file,codes,conditions\n,004217,",
        ).forEach { text ->
            val e = assertThrows(IllegalArgumentException::class.java) { BenchManifest.parse(text) }
            assertTrue(e.message.orEmpty().contains(BenchManifest.FILE_NAME))
        }
    }

    @Test
    fun `lists rows whose photo is not in the folder`() {
        val manifest = BenchManifest.parse("file,codes,conditions\nA.jpg,004217,\nB.jpg,,\nC.jpg,004218,glare")
        assertEquals(listOf("A.jpg", "C.jpg"), BenchManifest.missingPhotos(manifest, listOf("B.jpg", "D.jpg")))
        assertEquals(emptyList<String>(), BenchManifest.missingPhotos(manifest, listOf("C.jpg", "B.jpg", "A.jpg")))
    }
}
