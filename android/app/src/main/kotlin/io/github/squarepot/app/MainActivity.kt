// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.squarepot.app.bench.BenchScreen
import io.github.squarepot.app.camera.CameraScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                Surface {
                    var showBench by rememberSaveable { mutableStateOf(false) }
                    if (showBench) {
                        BackHandler { showBench = false }
                        BenchScreen(viewModel(), onBack = { showBench = false })
                    } else {
                        CameraScreen(viewModel(), onOpenBench = { showBench = true })
                    }
                }
            }
        }
    }
}
