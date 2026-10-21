# SPDX-License-Identifier: MIT-0
"""Frame rendering, adapted from libscanner/datamatrix-benchmark (MIT No Attribution).

Source: https://github.com/libscanner/datamatrix-benchmark, commit
05d58229fd01d0770b9a430e453768f87edd0bef, file synthetic/render_limits.py.
Licence: vendor/LICENSE.

Kept: dot gain, the label's projection onto the frame (scale, in-plane
rotation, tilt with a central projection), print contrast, anti-alias
pre-filter, defocus, motion blur, noise, the background and JPEG. Changed:
comments translated to English and code formatted for this repository;
`place()` takes a label image drawn by the caller instead of drawing one, and
draws the motion blur direction before anything else, so that two renders
from equal generators share it. JPEG goes through memory, not a
temporary file. Removed: the symbol generator (dmgen), the reader, surface
distortions, printed text, DPM dots and the sweeps.
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image
from scipy import ndimage

SRC_PX = 8  # source pixels per module of the label image


def dot_gain(sym: np.ndarray, gain: float) -> np.ndarray:
    """Dot gain: how much wider (+) or narrower (-) than nominal a dark module is,
    as a share of the module; each edge moves by half of it. The shift follows the
    distance map to the ink (growth) or to the paper (shrinkage), on a grid four
    times finer so that fractions of a pixel are not lost."""
    if gain == 0:
        return sym
    up = 4
    ink = np.kron(sym < 0.5, np.ones((up, up), bool))
    shift = abs(gain) / 2 * SRC_PX * up
    if gain > 0:
        ink = ndimage.distance_transform_edt(~ink) <= shift
    else:
        ink = ndimage.distance_transform_edt(ink) > shift
    paper = (~ink).astype(np.float32)
    return paper.reshape(sym.shape[0], up, sym.shape[1], up).mean(axis=(1, 3))


def homography(src: list[tuple[float, float]], dst: np.ndarray) -> np.ndarray:
    a = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(a, np.float64))
    h = vt[-1].reshape(3, 3)
    return h / h[2, 2]


def label_corners(
    side: float, ppm: float, angle: float, tilt: float, tilt_axis: float, focal: float
) -> np.ndarray:
    """Corners of the label (side in source pixels) in the frame, around its centre:
    scale, in-plane rotation, tilt of the plane by `tilt` degrees about an axis at
    `tilt_axis` degrees, and a central projection with a focal length of `focal` px."""
    s = ppm / SRC_PX
    half = side * s / 2
    pts = np.array(
        [[-half, -half, 0], [half, -half, 0], [half, half, 0], [-half, half, 0]], np.float64
    )
    a = math.radians(angle)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    pts = pts @ rz.T
    if tilt:
        t, ax = math.radians(tilt), math.radians(tilt_axis)
        k = np.array([math.cos(ax), math.sin(ax), 0])
        kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        r = np.eye(3) + math.sin(t) * kx + (1 - math.cos(t)) * kx @ kx
        pts = pts @ r.T
        # Tilt shrinks the visible area; the distance is chosen so that the edge
        # nearest the camera keeps the scale ppm (otherwise tilt would stand in
        # for a smaller module).
    z = pts[:, 2]
    proj = pts[:, :2] * (focal / (focal + (z - z.min())))[:, None]
    return proj


def place(
    frame: np.ndarray,
    lab: np.ndarray,
    p: dict[str, float],
    center: tuple[float, float],
    rng: np.random.Generator,
    focal: float = 2500.0,
) -> None:
    """Draw the label image `lab` (square, 0..1, SRC_PX source px per module) with
    conditions p on the frame (float32, 0..255) around `center`. Frame conditions
    (blur, noise) are applied to the area around the label."""
    motion_angle = rng.uniform(0, np.pi)
    side = lab.shape[0]
    # Print: ink and paper; contrast = (paper - ink) / paper.
    paper = p.get("paper", 245.0)
    ink = paper * (1 - p.get("contrast", 0.9))
    # A frame pixel integrates a square of SRC_PX/ppm source pixels: an
    # anti-alias pre-filter.
    pre = 0.3 * SRC_PX / p["ppm"]
    lab_f = ndimage.gaussian_filter(lab, pre) if pre > 0.3 else lab

    corners = label_corners(
        side, p["ppm"], p["angle"], p.get("tilt", 0.0), p.get("tilt_axis", 0.0), focal
    )
    corners = corners + np.asarray(center)
    src = [(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]
    hi = np.linalg.inv(homography(src, corners))
    pad = 4 + 3 * (p.get("blur", 0.0) + p.get("motion", 0.0))
    x0 = int(max(0, math.floor(corners[:, 0].min() - pad)))
    y0 = int(max(0, math.floor(corners[:, 1].min() - pad)))
    x1 = int(min(frame.shape[1], math.ceil(corners[:, 0].max() + pad)))
    y1 = int(min(frame.shape[0], math.ceil(corners[:, 1].max() + pad)))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    den = hi[2, 0] * xx + hi[2, 1] * yy + hi[2, 2]
    u = (hi[0, 0] * xx + hi[0, 1] * yy + hi[0, 2]) / den
    v = (hi[1, 0] * xx + hi[1, 1] * yy + hi[1, 2]) / den
    on = (u >= 0) & (u < side - 1) & (v >= 0) & (v < side - 1)
    val = ndimage.map_coordinates(lab_f, [v, u], order=1, mode="constant", cval=1.0)
    lum = ink + (paper - ink) * val
    region = frame[y0:y1, x0:x1]
    region[on] = lum[on]

    # Capture conditions, on the code's area.
    if p.get("blur", 0.0) > 0:
        region[:] = ndimage.gaussian_filter(region, p["blur"])
    if p.get("motion", 0.0) > 0:
        length = max(1, round(p["motion"]))
        k = np.zeros((length, length), np.float32)
        for t in np.linspace(-0.5, 0.5, 4 * length):
            cx = round((length - 1) / 2 + t * (length - 1) * math.cos(motion_angle))
            cy = round((length - 1) / 2 + t * (length - 1) * math.sin(motion_angle))
            k[cy, cx] = 1
        region[:] = ndimage.convolve(region, k / k.sum(), mode="nearest")
    if p.get("noise", 0.0) > 0:
        region += rng.normal(0, p["noise"], region.shape).astype(np.float32)
    np.clip(region, 0, 255, out=region)


def background(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    g = (
        np.linspace(0, 1, w, dtype=np.float32)[None, :] * 25
        + np.linspace(0, 1, h, dtype=np.float32)[:, None] * 15
    )
    tex = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 12) * 40
    return np.clip(135 + g + tex, 0, 255).astype(np.float32)


def to_gray8(frame: np.ndarray, jpeg: float) -> np.ndarray:
    img = Image.fromarray(np.clip(frame + 0.5, 0, 255).astype(np.uint8))
    if jpeg:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=int(jpeg))
        img = Image.open(buffer).convert("L")
    return np.asarray(img, np.uint8)
