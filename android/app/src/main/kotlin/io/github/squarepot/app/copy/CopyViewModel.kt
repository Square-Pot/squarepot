// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.copy

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.data.ServerSettings
import io.github.squarepot.app.data.SettingsProblem
import io.github.squarepot.app.data.SyncFailure
import io.github.squarepot.app.data.SyncWorker
import io.github.squarepot.app.data.local.CollectionEntity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.Locale

/** What the sync worker is doing now. */
enum class SyncActivity {
    IDLE,

    /** Waiting for a network, or for a retry after a failure. */
    QUEUED,

    RUNNING,
}

data class CopyState(
    val settings: ServerSettings = ServerSettings(),
    val refreshedAt: Long? = null,
    val failure: SyncFailure? = null,
    val plantCount: Int = 0,
    val collections: List<CollectionEntity> = emptyList(),
    val activity: SyncActivity = SyncActivity.IDLE,
)

/** The result of checking a server address and token before saving them. */
sealed interface CheckResult {
    data object Running : CheckResult

    data class Reachable(val collections: Int) : CheckResult

    data class Failed(val failure: SyncFailure) : CheckResult

    data class Invalid(val problem: SettingsProblem) : CheckResult
}

data class LookupState(val query: String = "", val searched: Boolean = false, val plants: List<PlantView> = emptyList())

class CopyViewModel(application: Application) : AndroidViewModel(application) {
    private val container = (application as SquarepotApplication).container
    private val dao = container.database.copy()
    private val workManager = WorkManager.getInstance(application)

    val state: StateFlow<CopyState> = combine(
        container.settings.settings,
        dao.observeState(),
        dao.observePlantCount(),
        dao.observeCollections(),
        workManager.getWorkInfosForUniqueWorkFlow(SyncWorker.NAME).map { activityOf(it) },
    ) { settings, sync, plantCount, collections, activity ->
        CopyState(
            settings = settings,
            refreshedAt = sync?.refreshedAt,
            failure = sync?.failure?.let { name -> SyncFailure.entries.firstOrNull { it.name == name } },
            plantCount = plantCount,
            collections = collections,
            activity = activity,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(STOP_TIMEOUT_MILLIS), CopyState())

    private val _check = MutableStateFlow<CheckResult?>(null)
    val check: StateFlow<CheckResult?> = _check.asStateFlow()

    private val _lookup = MutableStateFlow(LookupState())
    val lookup: StateFlow<LookupState> = _lookup.asStateFlow()

    fun refresh() = SyncWorker.enqueue(getApplication(), restart = true)

    fun saveSettings(settings: ServerSettings) {
        viewModelScope.launch {
            container.saveSettings(settings)
            refresh()
        }
    }

    fun checkSettings(settings: ServerSettings) {
        settings.problem?.let {
            _check.value = CheckResult.Invalid(it)
            return
        }
        _check.value = CheckResult.Running
        viewModelScope.launch {
            _check.value = try {
                CheckResult.Reachable(container.check(settings)?.size ?: 0)
            } catch (e: IOException) {
                CheckResult.Failed(SyncFailure.of(e, settings.baseUrl?.isHttps == false))
            }
        }
    }

    fun clearCheck() {
        _check.value = null
    }

    fun setQuery(query: String) = _lookup.update { LookupState(query = query) }

    fun search() {
        val query = _lookup.value.query
        viewModelScope.launch {
            val plants = container.localCopy.plantsByTag(query, Locale.getDefault().language)
            _lookup.update { if (it.query == query) it.copy(searched = true, plants = plants) else it }
        }
    }

    private fun activityOf(infos: List<WorkInfo>): SyncActivity {
        val info = infos.firstOrNull { !it.state.isFinished } ?: return SyncActivity.IDLE
        return if (info.state == WorkInfo.State.RUNNING) SyncActivity.RUNNING else SyncActivity.QUEUED
    }

    private companion object {
        const val STOP_TIMEOUT_MILLIS = 5_000L
    }
}
