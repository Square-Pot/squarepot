// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class ServerSettingsTest {
    private val url = "https://plants.example.org"

    @Test
    fun `a valid address and token can be used`() {
        assertNull(ServerSettings(url, "ci-token-0123456789").problem)
        assertNull(ServerSettings(" $url ", " token ").problem)
        assertNull(ServerSettings("http://10.0.2.2:8000", "t").problem)
    }

    @Test
    fun `an address that is not http(s) is a problem`() {
        assertEquals(SettingsProblem.URL, ServerSettings("", "t").problem)
        assertEquals(SettingsProblem.URL, ServerSettings("plants.example.org", "t").problem)
        assertEquals(SettingsProblem.URL, ServerSettings("ftp://plants.example.org", "t").problem)
    }

    @Test
    fun `a token that cannot go in a header is a problem`() {
        assertEquals(SettingsProblem.TOKEN, ServerSettings(url, "").problem)
        assertEquals(SettingsProblem.TOKEN, ServerSettings(url, "   ").problem)
        assertEquals(SettingsProblem.TOKEN, ServerSettings(url, "secrеt").problem) // Cyrillic е
        assertEquals(SettingsProblem.TOKEN, ServerSettings(url, "two words").problem)
        assertEquals(SettingsProblem.TOKEN, ServerSettings(url, "tab\there").problem)
    }

    @Test
    fun `no client is built for unusable settings, so OkHttp never sees a bad header`() {
        val http = OkHttpClient()
        assertNull(apiFor(ServerSettings(url, "токен"), http))
        assertNull(apiFor(ServerSettings("not a url", "token"), http))
        assertNotNull(apiFor(ServerSettings(url, "token"), http))
    }
}
