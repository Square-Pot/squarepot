// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import io.github.squarepot.app.SquarepotApplication

/**
 * Runs a sync as soon as the phone is online, so a sync asked for in the greenhouse happens when
 * the phone gets back into coverage. Network and server failures are retried with backoff.
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = (applicationContext as SquarepotApplication).container
        return when (val outcome = container.sync()) {
            is SyncOutcome.Failed -> if (outcome.failure in RETRIED) Result.retry() else Result.failure()
            is SyncOutcome.Updated, SyncOutcome.NotConfigured -> Result.success()
        }
    }

    companion object {
        const val NAME = "sync"

        private val RETRIED = setOf(SyncFailure.NETWORK, SyncFailure.SERVER)

        /**
         * Queues a sync for when the phone is online. With [restart], a sync already waiting
         * (perhaps in backoff) is replaced, so it runs now if there is a network.
         */
        fun enqueue(context: Context, restart: Boolean = false) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            val policy = if (restart) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP
            WorkManager.getInstance(context).enqueueUniqueWork(NAME, policy, request)
        }
    }
}
