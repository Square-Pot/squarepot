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
import io.github.squarepot.app.camera.CaptionSettingsScreen
import io.github.squarepot.app.copy.CopyScreen

private enum class Screen { CAMERA, CAPTIONS, BENCH, COPY }

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                Surface {
                    var screen by rememberSaveable { mutableStateOf(Screen.CAMERA) }
                    BackHandler(enabled = screen != Screen.CAMERA) {
                        screen = if (screen == Screen.BENCH) Screen.CAPTIONS else Screen.CAMERA
                    }
                    when (screen) {
                        Screen.CAMERA -> CameraScreen(
                            viewModel(),
                            onOpenSettings = { screen = Screen.CAPTIONS },
                            onOpenCopy = { screen = Screen.COPY },
                        )
                        Screen.CAPTIONS -> CaptionSettingsScreen(
                            viewModel(),
                            onBack = { screen = Screen.CAMERA },
                            onOpenBench = { screen = Screen.BENCH },
                        )
                        Screen.BENCH -> BenchScreen(viewModel(), onBack = { screen = Screen.CAPTIONS })
                        Screen.COPY -> CopyScreen()
                    }
                }
            }
        }
    }
}
