"""The files a document names, as each reader takes them: faces, contracts, bounds (#379).

Held function by function, so that what a finding says, where it points and which rule it
breaks are each compared whole: the readers' contracts beside `tests/test_paths_contract.py`.
"""

from pathlib import Path

import fonts.ttf
import pytest
from pydantic import ValidationError

import scenet.lettering
import scenet.limits
from scenet.assets.artwork import ArtworkContract, ContractError, load_contract, undrawn
from scenet.errors import FileReadError, PanelSyntaxError, RuleViolationError
from scenet.frontends.yaml_front import parse_panel
from scenet.images import load_image
from scenet.ir import Face, LetteringSpec, PanelIR
from scenet.lettering import FONT_CACHE_ENTRIES, load_font, typeface_for
from scenet.limits import describe
from scenet.solve.text import FontMetrics
from tests.images import tiny_png

FONT = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[missing-attribute]  # pyright: ignore[reportAttributeAccessIssue]
LOC = ("lettering", "font")


@pytest.mark.parametrize(
    ("size", "said"),
    [
        (1, "1 byte"),
        (2, "2 bytes"),
        (1023, "1023 bytes"),
        (1024, "1 KiB"),
        (2049, "2049 bytes"),
        (3 * 2**20, "3 MiB"),
        (2**20 + 1024, "1025 KiB"),
        (2**30, "1 GiB"),
    ],
)
def test_a_bound_in_words(size: int, said: str):
    assert describe(size) == said


@pytest.fixture
def empty_cache():
    scenet.lettering._BY_CONTENT.clear()
    yield
    scenet.lettering._BY_CONTENT.clear()


def _face(index: int) -> bytes:
    """The same face with bytes after its tables: another digest, the same font."""
    return FONT.read_bytes() + bytes(4 * index)


@pytest.mark.usefixtures("empty_cache")
class TestAFaceADocumentNames:
    def test_it_is_known_by_the_path_written(self):
        metrics = load_font("fonts/a.ttf", {"fonts/a.ttf": _face(0)}, loc=LOC)
        assert metrics.path == Path("fonts/a.ttf")

    def test_the_face_used_longest_ago_is_let_go_first(self):
        first = FontMetrics.digest(_face(0))
        load_font("a.ttf", {"a.ttf": _face(0)}, loc=LOC)
        for index in range(1, FONT_CACHE_ENTRIES + 1):
            load_font("a.ttf", {"a.ttf": _face(index)}, loc=LOC)
        assert first not in scenet.lettering._BY_CONTENT
        assert FontMetrics.digest(_face(FONT_CACHE_ENTRIES)) in scenet.lettering._BY_CONTENT
        assert len(scenet.lettering._BY_CONTENT) == FONT_CACHE_ENTRIES

    def test_a_file_that_is_no_font_is_refused_where_it_is_named(self):
        with pytest.raises(PanelSyntaxError) as raised:
            load_font("fonts/a.ttf", {"fonts/a.ttf": b"not a font"}, loc=LOC)
        assert (raised.value.rule, raised.value.loc) == ("font-file", LOC)
        assert raised.value.args[0] == (
            "font file 'fonts/a.ttf' is not a font that can be measured: a TrueType or OpenType "
            "file with a Unicode character map is needed"
        )

    @pytest.mark.parametrize("face", ["italic", "bold_italic", "display"])
    def test_each_face_is_refused_at_its_own_key(self, face: str):
        spec = LetteringSpec.model_validate({"font": {"regular": "a.ttf", face: "missing.ttf"}})
        with pytest.raises(PanelSyntaxError) as raised:
            typeface_for(spec, {"a.ttf": _face(0)})
        assert raised.value.loc == ("lettering", "font", face)

    def test_a_display_face_named_is_declared(self):
        spec = LetteringSpec.model_validate({"font": {"regular": "a.ttf", "display": "b.ttf"}})
        lettering = typeface_for(spec, {"a.ttf": _face(0), "b.ttf": _face(1)})
        assert lettering.declared == frozenset({Face.REGULAR, Face.DISPLAY})
        assert not lettering.stands_in(Face.DISPLAY)
        assert lettering.stands_in(Face.ITALIC)


def test_a_font_a_caller_names_has_the_font_bound(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(scenet.limits, "FONT_BYTES", 10)
    with pytest.raises(FileReadError) as raised:
        FontMetrics(FONT)
    assert raised.value.strerror == "larger than 10 bytes, the most Scenet reads of a font"


def _rule_of(error: ValidationError) -> str:
    fault = (error.errors()[0].get("ctx") or {}).get("error")
    assert isinstance(fault, RuleViolationError)
    return fault.rule


class TestAContract:
    def test_a_point_off_the_picture_breaks_the_contract_rule(self):
        with pytest.raises(ValidationError) as raised:
            ArtworkContract.model_validate(
                {"size": [10, 10], "figures": {"a": {"face": {"center": [20, 5], "radius": 2}}}}
            )
        assert _rule_of(raised.value) == "artwork-contract"

    @pytest.mark.parametrize(
        "region",
        [
            [[0, 0], [10, 10], [10, 0], [0, 10]],  # its edges cross, and it has an area
            [[0, 0], [5, 5], [10, 10]],  # its corners lie on one line
        ],
    )
    def test_a_region_with_no_inside_is_refused(self, region: list[list[int]]):
        with pytest.raises(ValidationError) as raised:
            ArtworkContract.model_validate({"size": [10, 10], "keep_out": [region]})
        assert _rule_of(raised.value) == "artwork-contract"
        assert "a region must be a simple polygon with an inside: its edges may not cross" in str(
            raised.value
        )

    def test_a_region_of_one_pixel_is_a_region(self):
        contract = ArtworkContract.model_validate(
            {"size": [10, 10], "keep_out": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
        )
        assert len(contract.keep_out) == 1

    def _load(self, text: str) -> None:
        files = {"art/a.png": tiny_png(), "art/a.art.yaml": text.encode()}
        load_contract(load_image("art/a.png", files, loc=()), files, loc=("setting", "image"))

    def test_not_a_mapping_says_what_one_holds(self):
        with pytest.raises(ContractError) as raised:
            self._load("- size\n")
        assert raised.value.args[0] == (
            "artwork contract 'art/a.art.yaml': it must be a mapping of size, figures and keep_out"
        )

    def test_an_unknown_key_says_what_the_keys_are(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(tiny_png())
        (tmp_path / "art" / "a.art.yaml").write_text("size: [3, 2]\nsecret: 1\n", encoding="utf-8")
        image = load_image("art/a.png", tmp_path, loc=())
        with pytest.raises(ContractError) as raised:
            load_contract(image, tmp_path, loc=("setting", "image"))
        assert raised.value.args[0] == (
            "artwork contract 'art/a.art.yaml', line 2: not a key an artwork contract has: size, "
            "figures and keep_out at the top, and face, mouth and body for a figure"
        )


def _panel(script: str) -> PanelIR:
    return parse_panel(
        "setting: {image: art/a.png}\ncast: {ana: {figure: ana}, ben: {figure: ben}}\n" + script
    )


class TestAFigureNotDrawn:
    CONTRACT = ArtworkContract.model_validate({"size": [10, 10]})

    def test_a_line_said_by_one_says_who_the_picture_draws(self):
        (fault,) = undrawn(
            _panel("script: [{say: {by: ben, text: Hi.}}]\n"),
            self.CONTRACT,
            "art/a.png",
        )
        assert fault.args[0].startswith(
            "'ben' speaks in script entry 0, as figure 'ben', which 'art/a.png' does not draw: "
            "its contract declares nobody."
        )
        assert (fault.rule, fault.loc) == ("unknown-figure", ("script", 0, "say", "by"))

    def test_a_sound_made_by_one(self):
        (fault,) = undrawn(
            _panel("script: [{sfx: {text: BANG, from: ben}}]\n"),
            self.CONTRACT,
            "art/a.png",
        )
        assert fault.args[0].startswith(
            "'ben' makes a sound in script entry 0, as figure 'ben', which 'art/a.png' does not "
            "draw"
        )
        assert fault.loc == ("script", 0, "sfx", "from")

    def test_a_sound_from_nobody_is_nobody_s(self):
        assert undrawn(_panel("script: [{sfx: {text: BANG}}]\n"), self.CONTRACT, "art/a.png") == []
