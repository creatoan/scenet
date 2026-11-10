"""The fog and cloud veil's noise, computed for print.

The SVG draws the veil with `feTurbulence`, and a browser computes its noise. A PDF has no
such filter, so print computes the same noise itself and carries it as a raster: SVG 1.1's
reference algorithm, which the specification calls "the exact algorithm used for this filter
effect" and which browsers implement. The Filter Effects draft has since changed how that
algorithm draws its gradients; browsers have not, and print follows what the screen shows.

One departure from the C code. A gradient whose two random components are both zero -- 243 of
the 65,536 seeds Scenet writes draw one -- is divided by its zero length there. Chromium keeps
it (0, 0); so does print, where the C code would leave NaN.

The noise is sampled at the centre of each sample, one per :data:`VEIL_STEP` panel units
(127 dpi at a tenth of a millimetre a unit): about fifteen samples across the finest octave of
fog, which looks no different printed than twice as many. It is computed in float64 with
addition, subtraction, multiplication and `floor` alone, in an explicit loop over octaves --
nothing whose result could depend on the platform, the vector unit or the order of a sum -- so
the same veil is the same bytes everywhere, Pyodide included.
"""

import functools
import math
from dataclasses import dataclass

import numpy as np

from scenet.core import CoreVeil

#: Panel units between samples: 127 dpi.
VEIL_STEP = 2.0

#: The reference code's constants: Park and Miller's generator, and the lattice's size.
RAND_M = 2147483647
RAND_A = 16807
RAND_Q = 127773
RAND_R = 2836
LATTICE = 0x100
WRAP = 0xFF
PERLIN_N = 0x1000

#: Rows worked out at once, so a veil over a whole page holds no more than a band in memory.
BAND = 256


def park_miller(seed: int) -> int:
    """The next of Park and Miller's minimal standard random numbers, as the reference has it."""
    result = RAND_A * (seed % RAND_Q) - RAND_R * (seed // RAND_Q)
    return result + RAND_M if result <= 0 else result


@dataclass(frozen=True, slots=True)
class Lattice:
    """The reference code's lattice for one seed.

    Attributes:
        selector: The shuffled lattice indices, `2 * 256 + 2` of them.
        gradient: Each channel's unit gradients, shaped `(4, 2 * 256 + 2, 2)`.
    """

    selector: np.ndarray
    gradient: np.ndarray


@functools.lru_cache(maxsize=64)
def lattice(seed: int) -> Lattice:
    """The lattice `init` builds for a seed.

    In the reference code's order: every channel's gradients first, then the shuffle.
    """
    if seed <= 0:
        seed = -(seed % (RAND_M - 1)) + 1
    seed = min(seed, RAND_M - 1)
    selector = list(range(LATTICE))
    gradient = [[(0.0, 0.0)] * LATTICE for _ in range(4)]
    for channel in range(4):
        for index in range(LATTICE):
            seed = park_miller(seed)
            x = float((seed % (LATTICE + LATTICE)) - LATTICE) / LATTICE
            seed = park_miller(seed)
            y = float((seed % (LATTICE + LATTICE)) - LATTICE) / LATTICE
            length = math.sqrt(x * x + y * y)
            gradient[channel][index] = (x / length, y / length) if length else (0.0, 0.0)
    for index in range(LATTICE - 1, 0, -1):
        seed = park_miller(seed)
        other = seed % LATTICE
        selector[index], selector[other] = selector[other], selector[index]
    # Extended as the C code extends them, entry by entry: the last two copy entries the
    # same loop has just written.
    selector += [0] * (LATTICE + 2)
    for channel in range(4):
        gradient[channel] = gradient[channel] + [(0.0, 0.0)] * (LATTICE + 2)
    for index in range(LATTICE + 2):
        selector[LATTICE + index] = selector[index]
        for channel in range(4):
            gradient[channel][LATTICE + index] = gradient[channel][index]
    return Lattice(
        selector=np.array(selector, dtype=np.int64),
        gradient=np.array(gradient, dtype=np.float64),
    )


def _noise2(grid: Lattice, channel: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The reference `noise2`, without stitching, at every point at once."""
    t = x + PERLIN_N
    bx0 = t.astype(np.int64)
    rx0 = t - bx0
    bx1 = (bx0 + 1) & WRAP
    bx0 &= WRAP
    rx1 = rx0 - 1.0
    t = y + PERLIN_N
    by0 = t.astype(np.int64)
    ry0 = t - by0
    by1 = (by0 + 1) & WRAP
    by0 &= WRAP
    ry1 = ry0 - 1.0
    selector = grid.selector
    i = selector[bx0]
    j = selector[bx1]
    b00 = selector[i + by0]
    b10 = selector[j + by0]
    b01 = selector[i + by1]
    b11 = selector[j + by1]
    sx = rx0 * rx0 * (3.0 - 2.0 * rx0)
    sy = ry0 * ry0 * (3.0 - 2.0 * ry0)
    gradient = grid.gradient[channel]
    u = rx0 * gradient[b00, 0] + ry0 * gradient[b00, 1]
    v = rx1 * gradient[b10, 0] + ry0 * gradient[b10, 1]
    a = u + sx * (v - u)
    u = rx0 * gradient[b01, 0] + ry1 * gradient[b01, 1]
    v = rx1 * gradient[b11, 0] + ry1 * gradient[b11, 1]
    b = u + sx * (v - u)
    return a + sy * (b - a)


def fractal_noise(  # noqa: PLR0917 -- the reference function's own parameters
    grid: Lattice, channel: int, x: np.ndarray, y: np.ndarray, frequency: float, octaves: int
) -> np.ndarray:
    """The reference `turbulence`, as `fractalNoise` does it.

    Each octave's noise at half the weight of the one before, summed in order.
    """
    total = np.zeros_like(x)
    vx, vy = x * frequency, y * frequency
    ratio = 1.0
    for _ in range(octaves):
        total = total + _noise2(grid, channel, vx, vy) / ratio
        vx, vy = vx * 2, vy * 2
        ratio *= 2
    return total


@dataclass(frozen=True, slots=True)
class Alpha:
    """A veil's opacity, sampled: `rows` rows of `columns` bytes, 0 clear and 255 opaque."""

    columns: int
    rows: int
    data: bytes


def veil_alpha(veil: CoreVeil, width: float, height: float, step: float = VEIL_STEP) -> Alpha:
    """How opaque a veil is over a panel, sample by sample.

    What the SVG's colour matrix makes of the noise: `opacity` of its red channel and half
    that of its green, each channel `(noise + 1) / 2` clamped to [0, 1]; then clamped, and
    rounded to a byte once.

    Args:
        veil: The veil, as Panel Core resolved it.
        width: The panel's width.
        height: The panel's height.
        step: Panel units between samples.

    Returns:
        The samples, covering the panel from its top left, the last row and column reaching
        at most a step past its edge.
    """
    return _alpha(veil.seed, veil.opacity, veil.frequency, veil.octaves, width, height, step)


@functools.lru_cache(maxsize=32)
def _alpha(  # noqa: PLR0917 -- a veil's numbers, so the cache can key on them
    seed: int,
    opacity: float,
    frequency: float,
    octaves: int,
    width: float,
    height: float,
    step: float,
) -> Alpha:
    columns, rows = math.ceil(width / step), math.ceil(height / step)
    grid = lattice(seed)
    xs = (np.arange(columns, dtype=np.float64) + 0.5) * step
    bands: list[bytes] = []
    for top in range(0, rows, BAND):
        ys = (np.arange(top, min(rows, top + BAND), dtype=np.float64) + 0.5) * step
        x, y = np.meshgrid(xs, ys)
        red = np.clip((fractal_noise(grid, 0, x, y, frequency, octaves) + 1) / 2, 0, 1)
        green = np.clip((fractal_noise(grid, 1, x, y, frequency, octaves) + 1) / 2, 0, 1)
        level = np.clip(opacity * red + opacity / 2 * green, 0, 1)
        bands.append(np.floor(255 * level + 0.5).astype(np.uint8).tobytes())
    return Alpha(columns=columns, rows=rows, data=b"".join(bands))
