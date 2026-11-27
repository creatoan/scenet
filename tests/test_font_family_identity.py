"""A font's name is its own, never a path's, and never what the process read first (#439).

A font with no `name` table used to be called by the stem of the file it was first read
from. The font cache is keyed by the digest of the bytes, so in a long-lived process (the
MCP server, `--watch`, the playground, a test run) a second document declaring the same
bytes under another file name got the first document's stem in its Panel Core, and a fresh
process gave it its own. One user's file name leaked into another user's output.
"""

import io
import json
from pathlib import Path

import fonts.ttf
import pytest
from fontTools.ttLib import TTFont

import scenet.lettering
from scenet.core import PanelCore
from scenet.lettering import FONT_CACHE_ENTRIES, load_font
from scenet.pipeline import compile_source
from scenet.solve.text import FontMetrics

SHIPPED = Path(fonts.ttf.SourceSansProSemibold)  # ty: ignore[missing-attribute]  # pyright: ignore[reportAttributeAccessIssue]

DOCUMENT = (
    "lettering: {{font: {path}}}\n"
    "cast: {{alice: {{reference: alice}}}}\n"
    "script:\n  - say: {{by: alice, text: Hello.}}\n"
)


def _nameless() -> bytes:
    """The shipped face with its `name` table taken out: a font that cannot name itself."""
    font = TTFont(SHIPPED)
    del font["name"]
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


NAMELESS = _nameless()


@pytest.fixture(autouse=True)
def empty_cache():
    scenet.lettering._BY_CONTENT.clear()
    yield
    scenet.lettering._BY_CONTENT.clear()


def _core(path: str, data: bytes = NAMELESS) -> PanelCore:
    return compile_source(DOCUMENT.format(path=path), base={path: data}).core


def _family(core: PanelCore) -> str:
    families = {font.family for font in core.fonts.values()}
    assert len(families) == 1
    return families.pop()


@pytest.mark.parametrize("order", [("alpha.ttf", "beta.ttf"), ("beta.ttf", "alpha.ttf")])
def test_a_nameless_font_has_one_family_whichever_path_it_was_read_under_first(
    order: tuple[str, str],
):
    first, second = (_core(path) for path in order)
    scenet.lettering._BY_CONTENT.clear()
    alone = _core(order[1])  # as a fresh process would have compiled the second
    assert _family(first) == _family(second) == _family(alone)
    # Whichever came first, the whole Core is the same: the path is not in it.
    assert first.model_dump_json() == second.model_dump_json()


def test_the_same_nameless_font_is_named_alike_in_a_fresh_process_and_a_warm_one():
    cold = _core("alpha.ttf")
    scenet.lettering._BY_CONTENT.clear()
    _core("beta.ttf")  # warms the cache under another name
    warm = _core("alpha.ttf")
    assert cold.model_dump_json() == warm.model_dump_json()


def test_a_nameless_font_is_called_by_its_digest_not_its_path():
    family = _family(_core("secret-customer-name.ttf"))
    assert family == FontMetrics.digest(NAMELESS)[:12]


def test_no_output_holds_a_path_stem_of_another_document():
    """What one document called its file does not reach what a later one is given."""
    _core("first-users-private-name.ttf")
    later = _core("another-name.ttf")
    assert "first-users-private-name" not in later.model_dump_json()
    assert "first-users-private-name" not in json.dumps(
        later.model_dump(mode="json"), sort_keys=True
    )


def test_a_font_with_a_name_keeps_it_whatever_the_path():
    data = SHIPPED.read_bytes()
    core = _core("whatever.ttf", data)
    assert _family(core) == FontMetrics(SHIPPED).family


def test_a_font_read_directly_is_named_by_its_digest_too(tmp_path: Path):
    path = tmp_path / "some-stem.ttf"
    path.write_bytes(NAMELESS)
    assert FontMetrics(path).family == FontMetrics.digest(NAMELESS)[:12]


def test_the_cache_never_holds_more_than_its_bound():
    data = SHIPPED.read_bytes()
    for index in range(FONT_CACHE_ENTRIES * 2 + 3):
        # Bytes after the last table change the digest and nothing a reader reads.
        load_font("a.ttf", {"a.ttf": data + bytes(4 * (index + 1))}, loc=())
        assert len(scenet.lettering._BY_CONTENT) <= FONT_CACHE_ENTRIES
    assert len(scenet.lettering._BY_CONTENT) == FONT_CACHE_ENTRIES


def test_a_face_let_go_and_read_again_gives_the_same_result():
    data = NAMELESS
    before = _core("a.ttf", data).model_dump_json()
    for index in range(FONT_CACHE_ENTRIES + 1):
        load_font("filler.ttf", {"filler.ttf": data + bytes(4 * (index + 1))}, loc=())
    assert FontMetrics.digest(data) not in scenet.lettering._BY_CONTENT
    assert _core("a.ttf", data).model_dump_json() == before
