"""The display face sound effects are lettered in: Bangers, shipped with Scenet.

Source Sans is a text face, and a sound effect wants a heavy display face. No PyPI
package carries one, so Bangers (Vernon Adams, SIL Open Font License 1.1) is vendored
into the package under `scenet/fonts/` -- which the OFL permits, provided the licence
travels with it. The licence gate checks installed distributions and cannot see a file
inside one, so what it would have checked is checked here instead: the file is the one
fetched from google/fonts, and its licence is the OFL, in the font and beside it.
"""

import hashlib
from importlib.resources import files
from pathlib import Path

from fontTools.ttLib import TTFont

from scenet.ir import Face
from scenet.solve.text import DISPLAY_FONT_PATH, SHIPPED_FACES, FontMetrics, Typeface

ROOT = Path(__file__).resolve().parents[1]

#: The SHA-256 of `ofl/bangers/Bangers-Regular.ttf` in google/fonts at commit
#: cf67eacb4b4c70430d1c02e55ba0d02232e85fa1 (Bangers 2.100, 2023-06-22). A different file
#: is a different font, and needs its licence read again.
UPSTREAM_SHA256 = "4160a7311de9342674cce9160cde9fcbb30f48190397d86ff1b70b455af65824"


class TestItShips:
    def test_the_font_is_package_data(self):
        packaged = files("scenet").joinpath("fonts", "Bangers-Regular.ttf")
        assert packaged.is_file()
        assert Path(str(packaged)) == DISPLAY_FONT_PATH

    def test_it_is_the_file_fetched_from_google_fonts(self):
        assert hashlib.sha256(DISPLAY_FONT_PATH.read_bytes()).hexdigest() == UPSTREAM_SHA256

    def test_its_licence_travels_with_it(self):
        licence = files("scenet").joinpath("fonts", "OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in licence
        assert "The Bangers Project Authors" in licence

    def test_the_font_says_the_same_licence(self):
        name = TTFont(str(DISPLAY_FONT_PATH))["name"]
        assert "SIL Open Font License, Version 1.1" in (name.getDebugName(13) or "")

    def test_the_notices_record_it(self):
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        assert "### Bangers" in notices


class TestItIsPartOfTheFamily:
    def test_it_is_the_shipped_display_face(self):
        assert SHIPPED_FACES[Face.DISPLAY] == DISPLAY_FONT_PATH
        assert Typeface().face(Face.DISPLAY).path == DISPLAY_FONT_PATH

    def test_it_is_measured_like_any_face(self):
        bangers = FontMetrics(DISPLAY_FONT_PATH)
        assert bangers.family == "Bangers"
        assert bangers.units_per_em == 1000
        assert bangers.measure("BLAM", 100) > bangers.measure("tok", 100) > 0

    def test_it_draws_every_letter_a_sound_effect_is_written_in(self):
        bangers = FontMetrics(DISPLAY_FONT_PATH)
        outlines = bangers.glyph_outlines("BLAM! Kaboom? 123 Éé")
        drawn = [
            path
            for (path, _), character in zip(outlines, "BLAM! Kaboom? 123 Éé", strict=True)
            if character != " "
        ]
        assert all(path.startswith("M") for path in drawn)

    def test_it_is_kerned(self):
        assert FontMetrics(DISPLAY_FONT_PATH).kerning("A", "V") < 0
