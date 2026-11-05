"""The fog and cloud veil's noise, as print rasterises it (#282).

The SVG draws the veil with `feTurbulence`, whose exact algorithm SVG 1.1 gives as C code.
Print computes the same noise itself, vectorised with numpy; the oracle here is that C code
transliterated line by line into plain Python, and the two must agree to the last bit, at any
point and for any seed Scenet writes. One departure from the C, made in both: a gradient whose
two random components are both zero stays (0, 0), as Chromium's renderer keeps it, where the C
divides 0 by 0.
"""

import hashlib
import math
import os
import subprocess
import sys

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scenet.core import CoreVeil
from scenet.emit.turbulence import (
    VEIL_STEP,
    fractal_noise,
    lattice,
    park_miller,
    veil_alpha,
)

RAND_M = 2147483647
RAND_A = 16807
RAND_Q = 127773
RAND_R = 2836
BSIZE = 0x100
BM = 0xFF
PERLIN_N = 0x1000

#: The veil of seed 1155, 300 by 200 units, as first computed and checked against the oracle.
PINNED = "352f9508669717bad4f26e510c6b611f21dc56c1a0805e209504c042f30b0abb"


def _setup_seed(seed: int) -> int:
    if seed <= 0:
        seed = -(seed % (RAND_M - 1)) + 1
    return min(seed, RAND_M - 1)


def _random(seed: int) -> int:
    result = RAND_A * (seed % RAND_Q) - RAND_R * (seed // RAND_Q)
    if result <= 0:
        result += RAND_M
    return result


def _init(seed: int) -> tuple[list[int], list[list[list[float]]]]:
    """`init` of SVG 1.1's reference code, line by line."""
    selector = [0] * (BSIZE + BSIZE + 2)
    gradient = [[[0.0, 0.0] for _ in range(BSIZE + BSIZE + 2)] for _ in range(4)]
    seed = _setup_seed(seed)
    for k in range(4):
        for i in range(BSIZE):
            selector[i] = i
            for j in range(2):
                seed = _random(seed)
                gradient[k][i][j] = float((seed % (BSIZE + BSIZE)) - BSIZE) / BSIZE
            s = math.sqrt(
                gradient[k][i][0] * gradient[k][i][0] + gradient[k][i][1] * gradient[k][i][1]
            )
            if s != 0:
                gradient[k][i][0] /= s
                gradient[k][i][1] /= s
    # C leaves `i` at BSize when its loop ends, and `while(--i)` counts down from there.
    i = BSIZE
    while True:
        i -= 1
        if i == 0:
            break
        k = selector[i]
        seed = _random(seed)
        j = seed % BSIZE
        selector[i] = selector[j]
        selector[j] = k
    for i in range(BSIZE + 2):
        selector[BSIZE + i] = selector[i]
        for k in range(4):
            for j in range(2):
                gradient[k][BSIZE + i][j] = gradient[k][i][j]
    return selector, gradient


def _s_curve(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _lerp(t: float, a: float, b: float) -> float:
    return a + t * (b - a)


def _noise2(
    selector: list[int], gradient: list[list[list[float]]], channel: int, x: float, y: float
) -> float:
    """`noise2` of SVG 1.1's reference code, without stitching, line by line."""
    t = x + PERLIN_N
    bx0 = int(t)
    bx1 = bx0 + 1
    rx0 = t - int(t)
    rx1 = rx0 - 1.0
    t = y + PERLIN_N
    by0 = int(t)
    by1 = by0 + 1
    ry0 = t - int(t)
    ry1 = ry0 - 1.0
    bx0 &= BM
    bx1 &= BM
    by0 &= BM
    by1 &= BM
    i = selector[bx0]
    j = selector[bx1]
    b00 = selector[i + by0]
    b10 = selector[j + by0]
    b01 = selector[i + by1]
    b11 = selector[j + by1]
    sx = _s_curve(rx0)
    sy = _s_curve(ry0)
    q = gradient[channel][b00]
    u = rx0 * q[0] + ry0 * q[1]
    q = gradient[channel][b10]
    v = rx1 * q[0] + ry0 * q[1]
    a = _lerp(sx, u, v)
    q = gradient[channel][b01]
    u = rx0 * q[0] + ry1 * q[1]
    q = gradient[channel][b11]
    v = rx1 * q[0] + ry1 * q[1]
    b = _lerp(sx, u, v)
    return _lerp(sy, a, b)


def _turbulence(
    seed: int, channel: int, point: tuple[float, float], frequency: float, octaves: int
) -> float:
    """`turbulence` of SVG 1.1's reference code, as `fractalNoise` and without stitching."""
    selector, gradient = _init(seed)
    total = 0.0
    x, y = point[0] * frequency, point[1] * frequency
    ratio = 1.0
    for _ in range(octaves):
        total += _noise2(selector, gradient, channel, x, y) / ratio
        x *= 2
        y *= 2
        ratio *= 2
    return total


def test_the_random_numbers_are_park_and_millers():
    """The test the C code's own comment gives: the 10,000th number from seed 1."""
    seed = 1
    for _ in range(10_000):
        seed = park_miller(seed)
    assert seed == 1043618065


@pytest.mark.parametrize("seed", [0, 1, 2, 346, 1155, 1690, 2327, 2860, 30388, 51658, 65535])
def test_the_lattice_is_the_reference_codes(seed: int):
    selector, gradient = _init(seed)
    built = lattice(seed)
    assert built.selector.tolist() == selector
    assert built.gradient.tolist() == gradient


def test_seed_zero_is_seed_one():
    assert lattice(0).gradient.tolist() == lattice(1).gradient.tolist()


@pytest.mark.parametrize(("seed", "channel", "index"), [(1155, 0, 99), (346, 1, 164)])
def test_a_gradient_drawn_as_zero_stays_zero(seed: int, channel: int, index: int):
    """Where the C code would divide 0 by 0: Chromium keeps (0, 0), and so does print."""
    gradient = lattice(seed).gradient
    assert gradient[channel][index].tolist() == [0.0, 0.0]
    assert not np.isnan(gradient).any()


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=65535),
    channel=st.integers(min_value=0, max_value=1),
    x=st.floats(min_value=0, max_value=3000, allow_nan=False),
    y=st.floats(min_value=0, max_value=3000, allow_nan=False),
    octaves=st.integers(min_value=1, max_value=4),
    frequency=st.sampled_from([0.0016, 0.0022, 0.0042, 0.05]),
)
def test_the_noise_is_the_reference_codes_to_the_bit(
    *, seed: int, channel: int, x: float, y: float, octaves: int, frequency: float
):
    found = fractal_noise(lattice(seed), channel, np.array([x]), np.array([y]), frequency, octaves)
    assert found[0] == _turbulence(seed, channel, (x, y), frequency, octaves)


def _veil(**changes: object) -> CoreVeil:
    fields: dict[str, object] = {
        "tone": "#b7b7b7",
        "opacity": 0.55,
        "frequency": 0.0042,
        "octaves": 4,
        "seed": 30388,
    }
    return CoreVeil.model_validate({**fields, **changes})


class TestTheVeilsAlpha:
    def test_it_is_sampled_once_per_two_units(self):
        alpha = veil_alpha(_veil(), 101.0, 40.0)
        assert VEIL_STEP == 2.0
        assert (alpha.columns, alpha.rows) == (51, 20)
        assert len(alpha.data) == 51 * 20

    def test_each_sample_is_the_colour_matrixs_alpha(self):
        veil = _veil(seed=346, opacity=0.3, frequency=0.0016, octaves=3)
        alpha = veil_alpha(veil, 24.0, 12.0)
        for row in range(alpha.rows):
            for column in range(alpha.columns):
                point = ((column + 0.5) * VEIL_STEP, (row + 0.5) * VEIL_STEP)
                red = min(
                    1.0,
                    max(
                        0.0,
                        (_turbulence(veil.seed, 0, point, veil.frequency, veil.octaves) + 1) / 2,
                    ),
                )
                green = min(
                    1.0,
                    max(
                        0.0,
                        (_turbulence(veil.seed, 1, point, veil.frequency, veil.octaves) + 1) / 2,
                    ),
                )
                level = min(1.0, max(0.0, veil.opacity * red + veil.opacity / 2 * green))
                assert alpha.data[row * alpha.columns + column] == math.floor(255 * level + 0.5)

    def test_it_varies_as_fog_does(self):
        data = veil_alpha(_veil(), 600.0, 400.0).data
        assert min(data) < max(data)
        assert max(data) <= round(255 * 0.55 * 1.5)

    def test_a_seed_with_a_zero_gradient_gives_a_fixed_veil(self):
        """Seed 1155 draws a (0, 0) gradient in R: its veil is pinned, so it cannot drift."""
        veil = _veil(tone="#222222", opacity=0.3, frequency=0.0016, octaves=3, seed=1155)
        alpha = veil_alpha(veil, 300.0, 200.0)
        assert hashlib.sha256(alpha.data).hexdigest() == PINNED

    def test_the_same_veil_is_the_same_bytes_whatever_the_hash_seed(self):
        script = (
            "import hashlib\n"
            "from scenet.core import CoreVeil\n"
            "from scenet.emit.turbulence import veil_alpha\n"
            "veil = CoreVeil(tone='#222222', opacity=0.3, frequency=0.0016, octaves=3, seed=1155)\n"
            "print(hashlib.sha256(veil_alpha(veil, 700.0, 500.0).data).hexdigest())\n"
        )
        digests = {
            subprocess.run(  # noqa: S603 -- our own interpreter, running our own script
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
            ).stdout
            for seed in ("0", "12345")
        }
        veil = _veil(tone="#222222", opacity=0.3, frequency=0.0016, octaves=3, seed=1155)
        local = hashlib.sha256(veil_alpha(veil, 700.0, 500.0).data).hexdigest()
        assert digests == {local + "\n"}

    def test_a_large_veil_is_worked_out_in_bands_with_the_same_result(self):
        veil = _veil()
        whole = veil_alpha(veil, 300.0, 2100.0)
        assert whole.rows > 512
        rows = np.frombuffer(whole.data, dtype=np.uint8).reshape(whole.rows, whole.columns)
        top = veil_alpha(veil, 300.0, 200.0)
        assert rows[: top.rows].tobytes() == top.data


def test_every_number_is_one_the_generator_can_give():
    """Schrage's step is right modulo M whichever way it corrects a result, so the 10,000th
    number alone cannot tell; each number staying between 1 and M - 1 can (#310)."""
    seed = 1
    for _ in range(10_000):
        seed = park_miller(seed)
        assert 0 < seed < RAND_M


def test_the_step_that_gives_one_gives_one():
    """1 is the one result the generator keeps without correcting it at the edge (#310)."""
    assert park_miller(pow(RAND_A, -1, RAND_M)) == 1
