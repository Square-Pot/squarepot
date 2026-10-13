// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app

import android.app.Application
import io.github.squarepot.app.data.AppContainer
import io.github.squarepot.app.data.SyncWorker

class SquarepotApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        // Refresh the copy whenever the app starts; it waits for a network if there is none.
        SyncWorker.enqueue(this)
    }
}
