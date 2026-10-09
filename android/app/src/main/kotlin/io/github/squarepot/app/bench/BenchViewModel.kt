// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.bench

import android.app.Application
import android.net.Uri
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.decoder.MlKitTagDecoder
import io.github.squarepot.app.decoder.ZxingCppTagDecoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface BenchUiState {
    data object Idle : BenchUiState
    data class Running(val done: Int, val total: Int) : BenchUiState
    data class Done(val result: BenchRunner.Result) : BenchUiState
    data class Failed(val message: String) : BenchUiState
}

class BenchViewModel(application: Application) : AndroidViewModel(application) {
    private val _state = MutableStateFlow<BenchUiState>(BenchUiState.Idle)
    val state: StateFlow<BenchUiState> = _state.asStateFlow()

    fun run(folder: Uri) {
        if (_state.value is BenchUiState.Running) return
        _state.value = BenchUiState.Running(0, 0)
        viewModelScope.launch(Dispatchers.Default) {
            val decoders = listOf(MlKitTagDecoder(), ZxingCppTagDecoder())
            val result = runCatching {
                BenchRunner(getApplication(), decoders).run(folder) { done, total ->
                    _state.value = BenchUiState.Running(done, total)
                }
            }
            decoders.forEach { it.close() }
            _state.value = result.fold(
                onSuccess = { BenchUiState.Done(it) },
                onFailure = { e ->
                    Log.e(TAG, "Bench failed", e)
                    BenchUiState.Failed(e.message ?: e.toString())
                },
            )
        }
    }

    private companion object {
        const val TAG = "Bench"
    }
}
