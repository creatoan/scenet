"""What a Panel Core or a Page Core says when it is read back, and looked into.

A Core is a format people hand-edit, so reading one back refuses what no compile could have
written, and says where. Each test here kills a mutant the first run of the `core` leg of
the mutation run left alive (#345); `docs/maintainer/testing.md` lists them.
"""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from scenet.core import PageCore, PanelCore
from scenet.errors import CoreSyntaxError, PanelSyntaxError, UnknownActorError
from scenet.pipeline import compile_book, compile_source
from tests.images import tiny_png

PANEL = "cast: {alice: {reference: alice}}\nscript: [{say: {by: alice, text: Hello.}}]\n"
PICTURED = "panel: {size: [1200, 600]}\nsetting: {image: art/street.png}\n" + PANEL
FILES = {"art/street.png": tiny_png(3, 2)}


def _payload(source: str = PANEL, **base: Any) -> dict[str, Any]:
    return json.loads(compile_source(source, **base).core.to_json())


def _refusal(payload: dict[str, Any]) -> tuple[str, PanelSyntaxError]:
    """The message reading the payload back gives, and the path error underneath it."""
    with pytest.raises(CoreSyntaxError) as caught:
        PanelCore.from_json(json.dumps(payload))
    cause = caught.value.__cause__
    assert isinstance(cause, ValidationError)
    (error,) = cause.errors()
    original = (error.get("ctx") or {}).get("error")
    assert isinstance(original, PanelSyntaxError)
    return str(caught.value), original


class TestAPathNoCompileWrote:
    """A Core keeps a picture's path and a puppet file's as the document wrote them."""

    def test_an_absolute_picture_is_refused_as_an_image_path(self):
        payload = _payload(PICTURED, base=FILES)
        payload["backdrop"]["image"]["href"] = "/srv/art/street.png"
        message, original = _refusal(payload)
        assert message.startswith("invalid Panel Core:")
        assert "the image path '/srv/art/street.png' is absolute" in message
        assert original.rule == "image-file"

    def test_an_absolute_puppet_file_is_refused_as_a_puppet_path(self):
        payload = _payload()
        payload["actors"][0]["reference"] = "/srv/puppets/kid.puppet.yaml"
        message, original = _refusal(payload)
        assert "the puppet path '/srv/puppets/kid.puppet.yaml' is absolute" in message
        assert original.rule == "puppet-file"

    def test_a_shipped_puppet_is_a_name_not_a_path(self):
        payload = _payload()
        assert payload["actors"][0]["reference"] == "alice"
        assert PanelCore.from_json(json.dumps(payload)).actors[0].reference == "alice"


class TestWhatAReadBackSays:
    def test_a_panel_core_is_named_as_one(self):
        with pytest.raises(CoreSyntaxError, match=r"^invalid Panel Core:\n  at width: "):
            PanelCore.from_json(json.dumps({**_payload(), "width": "wide"}))

    def test_a_page_core_is_named_as_one(self):
        (page,) = compile_book(_PAGE).pages
        payload = json.loads(page.to_json())
        payload["width"] = "wide"
        with pytest.raises(CoreSyntaxError, match=r"^invalid Page Core:\n  at width: "):
            PageCore.from_json(json.dumps(payload))


_PAGE = """\
cast: {alice: {reference: alice}}
pages:
  - tiers:
      - panels: [café, ending]
panels:
  café: {}
  ending: {}
"""


class TestAPageCoreIsText:
    def test_a_name_beyond_ascii_is_written_as_it_is(self):
        """`ensure_ascii=False`: a panel called `café` is `café` in the file, not an escape."""
        (page,) = compile_book(_PAGE).pages
        written = page.to_json()
        assert '"panel": "café"' in written
        assert "\\u" not in written


class TestLookingIntoAPanel:
    def test_an_actor_nobody_plays_is_named(self):
        core = compile_source(PANEL).core
        with pytest.raises(UnknownActorError, match="no actor 'nobody' in panel"):
            core.actor("nobody")

    def test_a_tail_aims_at_the_face_when_there_is_no_mouth(self):
        """A hand-edited puppet's anchors may leave the mouth out."""
        payload = _payload()
        del payload["actors"][0]["anchors"]["mouth"]
        core = PanelCore.from_json(json.dumps(payload))
        face, mouth = core.speaker("alice")
        assert mouth == (face.cx, face.cy)


class TestMonochrome:
    def test_air_without_a_veil_stays_without_one(self):
        """A Core may carry weather and no veil: one written by hand, or before the veil."""
        payload = _payload("palette: tinted\nsetting: {place: street, weather: rain}\n" + PANEL)
        assert payload["backdrop"]["atmosphere"]["veil"] is not None
        payload["backdrop"]["atmosphere"]["veil"] = None
        mono = PanelCore.from_json(json.dumps(payload)).as_mono()
        assert mono.backdrop is not None
        assert mono.backdrop.atmosphere is not None
        assert mono.backdrop.atmosphere.veil is None
        assert mono.backdrop.atmosphere.colour == ""
