// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration

/**
 * What the phone still has to send: photos and sightings of an inventory walk (ADR 0007, 0008).
 *
 * Unlike the local copy, this holds data that exists nowhere else yet, so it is never dropped.
 * Every change to these tables needs a migration in [MIGRATIONS], with a test that opens a
 * database of the previous version from its exported schema (`android/app/schemas`); without a
 * migration, Room refuses to open the database.
 */
@Database(entities = [QueuedPhoto::class, QueuedSighting::class], version = 1, exportSchema = true)
abstract class QueueDatabase : RoomDatabase() {
    abstract fun queue(): QueueDao

    companion object {
        /** Migrations from every earlier version. */
        internal val MIGRATIONS = emptyList<Migration>()

        fun open(context: Context): QueueDatabase = Room
            .databaseBuilder(context, QueueDatabase::class.java, "queue.db")
            .apply { MIGRATIONS.forEach { addMigrations(it) } }
            .build()
    }
}
