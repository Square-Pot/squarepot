// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.SyncWorker

/**
 * Sends the queue as soon as the phone is online, so photos and sightings taken in the
 * greenhouse go out once it is back in coverage, then syncs so the copy shows them. Failures
 * that pass (network, server, a busy server) are retried with backoff.
 */
class QueueWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = (applicationContext as SquarepotApplication).container
        val outcome = container.sendQueue()
        val sent = when (outcome) {
            is QueueOutcome.Done -> outcome.sent
            is QueueOutcome.Failed -> outcome.sent
            QueueOutcome.NotConfigured -> 0
        }
        if (sent > 0) SyncWorker.enqueue(applicationContext, restart = true)
        return when (outcome) {
            is QueueOutcome.Failed -> if (outcome.failure in SyncWorker.RETRIED) Result.retry() else Result.failure()
            // An item added while this run was sending is sent on the retry.
            is QueueOutcome.Done -> if (container.outbox.hasPending()) Result.retry() else Result.success()
            QueueOutcome.NotConfigured -> Result.success()
        }
    }

    companion object {
        const val NAME = "queue"

        /** Asks for the queue to be sent when the phone is online; a run already waiting is kept. */
        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<QueueWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(NAME, ExistingWorkPolicy.KEEP, request)
        }
    }
}
