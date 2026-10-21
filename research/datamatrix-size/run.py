# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the experiment: 10x10 vs 12x12 Data Matrix at the same label size.

    python run.py all [--smoke]                  everything here: check, frames, analysis
    python run.py check                          the symbols are standard
    python run.py shard INDEX COUNT [--smoke]    one share of the frames -> raw/shard-INDEX.csv
    python run.py analyze [--smoke]              raw/*.csv -> results/

Every frame's seed comes from the config's seed and the frame's place in the
grid, so a shard draws the same frames however the work is split.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import yaml
import zxingcpp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scene  # noqa: E402

CONFIG = yaml.safe_load((HERE / "config.yaml").read_text())
RAW = HERE / "raw"
SMOKE_TRIALS = 3
FIELDS = ["axis", "value", "trial", "size", "codes", "read", "wrong", "ms"]


def points(config: dict[str, Any], smoke: bool) -> Iterator[tuple[str, Any, int, dict[str, float]]]:
    """(axis, value, trial, params) for every frame pair, in a fixed order."""
    trials = SMOKE_TRIALS if smoke else config["trials"]
    for axis, values in config["axes"].items():
        name, _, fixed = axis.partition("@")
        for value in values:
            for trial in range(trials):
                params = {**config["base"], "rotation": 0.0, name: value}
                if fixed:
                    key, _, number = fixed.partition("=")
                    params[key] = float(number)
                yield axis, value, trial, params
    mixed = config["mixed"]
    for trial in range(SMOKE_TRIALS if smoke else mixed["trials"]):
        rng = np.random.default_rng([config["seed"], 999_999, trial])
        params = dict(config["base"], rotation=0.0)
        for key, (low, high) in mixed["ranges"].items():
            params[key] = float(rng.uniform(low, high))
        params["jpeg"] = round(params["jpeg"])
        yield "mixed", 0, trial, params


def decode(image: np.ndarray) -> tuple[list[str], float]:
    options = CONFIG["decoder"]
    start = time.perf_counter()
    found = zxingcpp.read_barcodes(
        image,
        formats=zxingcpp.BarcodeFormat.DataMatrix,
        try_rotate=options["try_rotate"],
        try_invert=options["try_invert"],
        try_downscale=options["try_downscale"],
        binarizer=getattr(zxingcpp.Binarizer, options["binarizer"]),
        is_pure=options["is_pure"],
        text_mode=zxingcpp.TextMode.Plain,
    )
    return [barcode.text for barcode in found], (time.perf_counter() - start) * 1000


def job(work: tuple[int, str, Any, int, dict[str, float]]) -> list[dict[str, Any]]:
    index, axis, value, trial, params = work
    seed = np.random.SeedSequence([CONFIG["seed"], index])
    drawn = scene.scene(params, seed, CONFIG, angle_axis=axis == "rotation")
    tags = {code.tag for code in drawn.codes}
    rows = []
    for size in CONFIG["symbols"]:
        texts, ms = decode(scene.draw(drawn, size, CONFIG))
        rows.append(
            {
                "axis": axis,
                "value": value,
                "trial": trial,
                "size": size,
                "codes": len(tags),
                "read": len(tags & set(texts)),
                "wrong": sum(text not in tags for text in texts),
                "ms": round(ms, 2),
            }
        )
    return rows


def shard(index: int, count: int, smoke: bool) -> Path:
    work = [
        (number, *point)
        for number, point in enumerate(points(CONFIG, smoke))
        if number % count == index
    ]
    RAW.mkdir(exist_ok=True)
    out = RAW / f"shard-{index}.csv"
    started = time.time()
    with out.open("w", newline="") as handle, ProcessPoolExecutor(os.cpu_count()) as pool:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        for done, rows in enumerate(pool.map(job, work, chunksize=4), 1):
            writer.writerows(rows)
            if done % 500 == 0:
                print(
                    f"shard {index}: {done}/{len(work)}, {time.time() - started:.0f} s", flush=True
                )
    print(f"shard {index}: {len(work)} scenes in {time.time() - started:.0f} s")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("all", "analyze"):
        commands.add_parser(name).add_argument("--smoke", action="store_true")
    commands.add_parser("check")
    one = commands.add_parser("shard")
    one.add_argument("index", type=int)
    one.add_argument("count", type=int)
    one.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    import analyze
    import check

    if args.command == "check":
        check.main()
    elif args.command == "shard":
        shard(args.index, args.count, args.smoke)
    elif args.command == "analyze":
        analyze.main(CONFIG, RAW, args.smoke)
    else:
        check.main()
        for old in RAW.glob("shard-*.csv"):
            old.unlink()
        shard(0, 1, args.smoke)
        analyze.main(CONFIG, RAW, args.smoke)


if __name__ == "__main__":
    main()
