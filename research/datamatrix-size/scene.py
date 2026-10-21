# SPDX-License-Identifier: AGPL-3.0-or-later
"""Paired scenes: one camera frame drawn twice, once with each symbol.

Everything about a scene is drawn from the trial's own seed, in millimetres
where it is physical: where the labels lie, how they are turned and tilted,
the background, the tags, the damage blots. Then each symbol is drawn into
its own copy of the frame, with a render generator seeded the same way, so
the two frames differ only in the symbol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

import symbols
from vendor import render


@dataclass(frozen=True)
class Blot:
    x_mm: float  # centre, from the code's centre
    y_mm: float
    radius_mm: float
    dark: bool


@dataclass(frozen=True)
class Code:
    tag: str
    center: tuple[float, float]  # frame pixels
    angle: float
    tilt_axis: float
    blots: tuple[Blot, ...]


@dataclass(frozen=True)
class Scene:
    params: dict[str, float]
    background: np.ndarray
    codes: tuple[Code, ...]
    render_seed: int


def data_region_mm(config: dict[str, Any]) -> float:
    """The side of the smallest data region of the symbols: blots fall inside it."""
    return min((size - 2) * module for size, module in config["symbols"].items())


def blots(damage: float, rng: np.random.Generator, config: dict[str, Any]) -> tuple[Blot, ...]:
    """Round blots, half dark, half light, until they cover `damage` of the data region."""
    side = data_region_mm(config)
    low, high = config["blot_radius_mm"]
    found: list[Blot] = []
    covered = 0.0
    while covered < damage * side * side:
        radius = float(rng.uniform(low, high))
        x, y = rng.uniform(-side / 2, side / 2, 2)
        found.append(Blot(float(x), float(y), radius, bool(rng.random() < 0.5)))
        covered += math.pi * radius * radius
    return tuple(found)


def tag(rng: np.random.Generator, used: set[str]) -> str:
    while True:
        value = f"{int(rng.integers(1, 1_000_000)):06d}"
        if value not in used:
            used.add(value)
            return value


def scene(
    params: dict[str, float], seed: np.random.SeedSequence, config: dict[str, Any], angle_axis: bool
) -> Scene:
    """The scene of one trial. `angle_axis`: params['rotation'] is the in-plane angle,
    turned by a random quarter (the symbol looks alike in all four); otherwise the
    angle is random."""
    scene_seed, render_seed = seed.spawn(2)
    rng = np.random.default_rng(scene_seed)
    width, height = config["frame"]["width"], config["frame"]["height"]
    frame = render.background(width, height, rng)
    count = int(params["codes"])
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    pitch = config["codes_pitch_mm"] * params["px_per_mm"]
    label = config["label_mm"] * params["px_per_mm"]
    # A random place for the block of labels, wholly inside the frame.
    span_x, span_y = (columns - 1) * pitch + label, (rows - 1) * pitch + label
    room_x, room_y = max(0.0, width - span_x) / 2, max(0.0, height - span_y) / 2
    origin_x = width / 2 + rng.uniform(-room_x, room_x) * 0.8 - (columns - 1) * pitch / 2
    origin_y = height / 2 + rng.uniform(-room_y, room_y) * 0.8 - (rows - 1) * pitch / 2
    used: set[str] = set()
    codes = []
    for index in range(count):
        if angle_axis:
            angle = params["rotation"] + 90 * int(rng.integers(0, 4))
        else:
            angle = float(rng.uniform(0, 360))
        codes.append(
            Code(
                tag=tag(rng, used),
                center=(origin_x + index % columns * pitch, origin_y + index // columns * pitch),
                angle=angle,
                tilt_axis=float(rng.uniform(0, 180)),
                blots=blots(params["damage"], rng, config),
            )
        )
    return Scene(params, frame, tuple(codes), int(render_seed.generate_state(1)[0]))


def label_image(
    code: Code, size: int, module_mm: float, params: dict[str, float], config: dict[str, Any]
) -> np.ndarray:
    """The printed label in source pixels (render.SRC_PX per module), 0 ink to 1 paper."""
    px_per_mm = render.SRC_PX / module_mm
    side = round(config["label_mm"] * px_per_mm)
    modules = symbols.encode(code.tag, size)
    sym = np.kron(~modules, np.ones((render.SRC_PX, render.SRC_PX))).astype(np.float32)
    lab = np.ones((side, side), np.float32)
    offset = (side - sym.shape[0]) // 2
    lab[offset : offset + sym.shape[0], offset : offset + sym.shape[1]] = sym
    lab = render.dot_gain(lab, params["gain_mm"] / module_mm)
    if code.blots:
        yy, xx = np.mgrid[:side, :side].astype(np.float32)
        middle = offset + sym.shape[0] / 2
        for blot in code.blots:
            inside = (xx - middle - blot.x_mm * px_per_mm) ** 2 + (
                yy - middle - blot.y_mm * px_per_mm
            ) ** 2 <= (blot.radius_mm * px_per_mm) ** 2
            lab[inside] = 0.0 if blot.dark else 1.0
    return lab


def draw(scene: Scene, size: int, config: dict[str, Any]) -> np.ndarray:
    """The frame of `scene` with every label printed with the `size` symbol, as 8-bit grey."""
    module_mm = config["symbols"][size]
    frame = scene.background.copy()
    params = scene.params
    for index, code in enumerate(scene.codes):
        lab = label_image(code, size, module_mm, params, config)
        p = {
            "ppm": params["px_per_mm"] * module_mm,
            "angle": code.angle,
            "tilt": params["tilt"],
            "tilt_axis": code.tilt_axis,
            "contrast": params["contrast"],
            "blur": params["blur"],
            "motion": params["motion"],
            "noise": params["noise"],
        }
        rng = np.random.default_rng([scene.render_seed, index])
        render.place(frame, lab, p, code.center, rng)
    return render.to_gray8(frame, params["jpeg"])
