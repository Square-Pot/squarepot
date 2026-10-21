# SPDX-License-Identifier: AGPL-3.0-or-later
"""raw/shard-*.csv -> results/: per-point table, summary, plots.

Per point and symbol: the share of codes read, with a Wilson 95 % interval,
wrong reads and the median decode time. Per point, the two symbols are
compared frame by frame (the frames are paired) with an exact two-sided sign
test, which for one code per frame is McNemar's exact test.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
THRESHOLD = 0.9
Z = 1.959964
# The easy end of an axis is its first value, except for these.
EASY_LAST = {"px_per_mm"}
TWO_SIDED = {"gain_mm"}
COLOURS = {10: "#1f77b4", 12: "#d62728"}


def wilson(read: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 1.0
    share = read / total
    centre = share + Z * Z / (2 * total)
    spread = Z * math.sqrt(share * (1 - share) / total + Z * Z / (4 * total * total))
    scale = 1 + Z * Z / total
    return (centre - spread) / scale, (centre + spread) / scale


def sign_test(first: int, second: int) -> float:
    """Exact two-sided p-value of `first` wins against `second` under a fair coin."""
    total = first + second
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(min(first, second) + 1)) / 2**total
    return min(1.0, 2 * tail)


def load(raw: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(raw.glob("shard-*.csv")):
        with path.open() as handle:
            for row in csv.DictReader(handle):
                row["value"] = float(row["value"])
                for key in ("trial", "size", "codes", "read", "wrong"):
                    row[key] = int(row[key])
                row["ms"] = float(row["ms"])
                rows.append(row)
    if not rows:
        raise SystemExit(f"no results in {raw}")
    return rows


def number(value: float) -> str:
    return f"{value:g}"


def limit(axis: str, values: list[float], share: dict[float, float]) -> str:
    """The hardest value reached from the easy end with every point read >= THRESHOLD."""

    def walk(ordered: list[float]) -> float | None:
        reached = None
        for value in ordered:
            if share[value] < THRESHOLD:
                break
            reached = value
        return reached

    if axis.split("@")[0] in TWO_SIDED:
        low = walk(sorted((v for v in values if v <= 0), reverse=True))
        high = walk(sorted(v for v in values if v >= 0))
        return f"{'-' if low is None else number(low)} … {'-' if high is None else number(high)}"
    ordered = values[::-1] if axis.split("@")[0] in EASY_LAST else values
    reached = walk(ordered)
    return "none" if reached is None else number(reached)


def main(config: dict[str, Any], raw: Path, smoke: bool) -> None:
    out = HERE / ("results-smoke" if smoke else "results")
    (out / "plots").mkdir(parents=True, exist_ok=True)
    rows = load(raw)
    sizes = sorted(config["symbols"])
    cells: dict[tuple[str, float, int], list[dict[str, Any]]] = defaultdict(list)
    pairs: dict[tuple[str, float, int], dict[int, int]] = defaultdict(dict)
    for row in rows:
        cells[row["axis"], row["value"], row["size"]].append(row)
        pairs[row["axis"], row["value"], row["trial"]][row["size"]] = row["read"]
    axes = list(dict.fromkeys(row["axis"] for row in rows))

    table = []
    for axis in axes:
        values = sorted({value for a, value, _ in cells if a == axis})
        if axis in config["axes"]:
            values = [float(v) for v in config["axes"][axis]]
        for value in values:
            trials = [t for (a, v, _), t in pairs.items() if a == axis and v == value]
            wins = sum(t[sizes[0]] > t[sizes[1]] for t in trials)
            losses = sum(t[sizes[0]] < t[sizes[1]] for t in trials)
            for size in sizes:
                group = cells[axis, value, size]
                total = sum(r["codes"] for r in group)
                read = sum(r["read"] for r in group)
                low, high = wilson(read, total)
                table.append(
                    {
                        "axis": axis,
                        "value": number(value),
                        "size": size,
                        "frames": len(group),
                        "codes": total,
                        "read": read,
                        "share": round(read / total, 4),
                        "ci_low": round(low, 4),
                        "ci_high": round(high, 4),
                        "wrong": sum(r["wrong"] for r in group),
                        "median_ms": round(median(r["ms"] for r in group), 2),
                        "frames_only_10_better": wins,
                        "frames_only_12_better": losses,
                        "p_sign_test": round(sign_test(wins, losses), 6),
                    }
                )
    with (out / "per_point.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, list(table[0]))
        writer.writeheader()
        writer.writerows(table)

    share = {(r["axis"], float(r["value"]), r["size"]): r for r in table}
    lines = [
        "# Results" + (" (smoke run)" if smoke else ""),
        "",
        f"Frames: {len(rows) // len(sizes)} pairs. Codes read correctly, share with a Wilson 95 % "
        "interval; p: exact two-sided sign test on the paired frames.",
        "",
        f"## Limits: the hardest value read in at least {THRESHOLD:.0%} of codes",
        "",
        "| axis | " + " | ".join(f"{s}x{s}" for s in sizes) + " |",
        "| --- | " + " | ".join("---" for _ in sizes) + " |",
    ]
    for axis in axes:
        if axis == "mixed":
            continue
        values = [float(v) for v in config["axes"][axis]]
        lines.append(
            f"| {axis} | "
            + " | ".join(
                limit(axis, values, {v: share[axis, v, s]["share"] for v in values}) for s in sizes
            )
            + " |"
        )
    lines += ["", "## Every point", ""]
    lines += [
        "| axis | value | "
        + " | ".join(f"{s}x{s} read" for s in sizes)
        + " | 10 better | 12 better | p |",
        "| --- | --- | " + " | ".join("---" for _ in sizes) + " | --- | --- | --- |",
    ]
    for axis in axes:
        values = sorted({v for a, v, _ in share if a == axis})
        if axis in config["axes"]:
            values = [float(v) for v in config["axes"][axis]]
        for value in values:
            first = share[axis, value, sizes[0]]
            cells_text = [
                f"{share[axis, value, s]['share']:.1%} "
                f"({share[axis, value, s]['ci_low']:.1%}-{share[axis, value, s]['ci_high']:.1%})"
                for s in sizes
            ]
            lines.append(
                f"| {axis} | {number(value)} | "
                + " | ".join(cells_text)
                + f" | {first['frames_only_10_better']} | {first['frames_only_12_better']}"
                f" | {first['p_sign_test']:.3g} |"
            )
    wrong = sum(r["wrong"] for r in table)
    lines += ["", f"Wrong reads, all points: {wrong}.", ""]
    (out / "summary.md").write_text("\n".join(lines))

    plotted = [a for a in axes if a != "mixed"]
    columns = 4
    figure, grid = plt.subplots(
        math.ceil(len(plotted) / columns),
        columns,
        figsize=(16, 3.2 * math.ceil(len(plotted) / columns)),
    )
    for place, axis in zip(grid.flat, plotted, strict=False):
        values = [float(v) for v in config["axes"][axis]]
        for size in sizes:
            points = [share[axis, v, size] for v in values]
            place.plot(
                values,
                [p["share"] for p in points],
                "o-",
                color=COLOURS[size],
                label=f"{size}x{size} @ {config['symbols'][size]} mm",
                markersize=3,
            )
            place.fill_between(
                values,
                [p["ci_low"] for p in points],
                [p["ci_high"] for p in points],
                color=COLOURS[size],
                alpha=0.2,
            )
        place.axhline(THRESHOLD, color="grey", linewidth=0.6, linestyle="--")
        place.set_title(axis, fontsize=10)
        place.set_ylim(-0.02, 1.02)
        place.grid(alpha=0.3)
    for place in list(grid.flat)[len(plotted) :]:
        place.axis("off")
    grid.flat[0].legend(fontsize=8, loc="lower right")
    figure.suptitle("Share of codes read: 10x10 vs 12x12, both 12 mm", fontsize=12)
    figure.tight_layout()
    figure.savefig(out / "plots" / "read-share.png", dpi=110)
    print(f"analysis: {out}")
