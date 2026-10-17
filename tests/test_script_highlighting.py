"""The comic-script highlighting fixtures say what the compiler says.

Two tokenizers colour comic scripts: the playground's Monarch rules and the VS Code
extension's TextMate grammar. Both are tested against the fixtures in
`tests/script_highlighting/`: each `.script` sits beside a `.tokens` file giving, line by
line, the spans a highlighter colours and what each one is.

This module holds those fixtures to the compiler's own reading of the script. A
highlighter cannot then agree with a fixture on a reading the compiler does not share,
and a change to the format that moves a line from one kind to another fails here until
the fixtures, and so both tokenizers, follow it.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scenet.frontends.script_front import (
    VOICE_OVER,
    _page_label,
    _read_script,
    _split_front_matter,
    _unquoted,
    _unquoted_spoken,
)

FIXTURES = Path(__file__).parent / "script_highlighting"
NAMES = sorted(path.stem for path in FIXTURES.glob("*.script"))

CLASSES = {
    "front-matter-delimiter",
    "front-matter",
    "page-keyword",
    "page-label",
    "page-count",
    "panel-keyword",
    "panel-label",
    "directive-marker",
    "directive-name",
    "directive-value",
    "cue-name",
    "cue-parenthetical",
    "caption-keyword",
    "caption-kind",
    "caption-speaker",
    "caption-text",
    "sfx-keyword",
    "sfx-parenthetical",
    "sfx-text",
    "dialogue",
    "prose",
    "markdown",
    "balloon-number",
}

Line = list[tuple[str, str]]


def _script(name: str) -> str:
    return (FIXTURES / f"{name}.script").read_text(encoding="utf-8")


def _tokens(name: str) -> list[Line]:
    rows = (FIXTURES / f"{name}.tokens").read_text(encoding="utf-8").splitlines()
    return [[(kind, text) for kind, text in json.loads(row)] for row in rows]


def _as_fixture_says(lines: list[Line]) -> list[dict[str, Any]]:
    """The panels a fixture describes, read from its classes alone."""
    panels: list[dict[str, Any]] = []
    page: str | None = None
    speaker: str | None = None
    # Lines under a PAGE heading belong to the page, not to the panel before it.
    inside = False
    for line in lines:
        spans = dict(line)
        if "page-keyword" in spans:
            page = _page_label(spans["page-label"])
            speaker = None
            inside = False
        elif "panel-keyword" in spans:
            panels.append(
                {
                    # `Panel One` is panel `1`, as `PAGE TWO` is page `2`.
                    "label": _page_label(spans["panel-label"]),
                    "page": page,
                    # Dark Horse's `Panel 1. A corner.`: the description on its line.
                    "description": [spans["prose"]] if "prose" in spans else [],
                    "events": [],
                    "directives": [],
                }
            )
            speaker = None
            inside = True
        elif inside:
            speaker = _in_panel(panels[-1], spans, speaker)
    for panel in panels:
        panel["events"] = [_as_lettered(event) for event in panel["events"]]
    return panels


def _as_lettered(event: tuple[str, ...]) -> tuple[str, ...]:
    """An event with the writer's quotation marks off, as the compiler takes them off."""
    if event[0] == "say":
        return (event[0], event[1], _unquoted(event[2]))
    if event[0] == "caption" and event[2] == "spoken":
        return (event[0], _unquoted_spoken(event[1]), event[2])
    return event


def _is_voice_over(parenthetical: str) -> bool:
    return any(word.strip().lower() in VOICE_OVER for word in parenthetical.split(","))


def _join(panel: dict[str, Any], more: str) -> None:
    """A wrapped line, joined onto the speech or caption above it."""
    event = panel["events"][-1]
    at = 2 if event[0] == "say" else 1
    panel["events"][-1] = (*event[:at], f"{event[at]} {more}", *event[at + 1 :])


def _in_panel(panel: dict[str, Any], spans: dict[str, str], waiting: Any) -> Any:
    """Add one line of a panel's body to it, and say what the next line belongs to.

    `waiting` is what the line after this one is the text of: a cue, as `("say", NAME)`
    or a voice over's `("spoken", NAME)`; a caption label, as `("caption", KIND)`; or
    anything else, when a line of text continues whatever came last.
    """
    if "directive-name" in spans:
        panel["directives"].append(spans["directive-name"])
        return waiting
    for kind, read in _READERS:
        if kind in spans:
            return read(panel, spans, waiting)
    if "prose" in spans:
        panel["description"].append(spans["prose"])
    return waiting


def _caption_label(panel: dict[str, Any], spans: dict[str, str], _waiting: Any) -> Any:
    kind = spans.get("caption-kind")
    if kind is not None and _is_voice_over(kind):
        kind = "spoken"
    kind = kind or ("spoken" if "caption-speaker" in spans else "locale")
    if "caption-text" not in spans:
        return ("caption", kind)
    panel["events"].append(("caption", spans["caption-text"], kind))
    return "complete"


def _caption_text(panel: dict[str, Any], spans: dict[str, str], waiting: Any) -> Any:
    if isinstance(waiting, tuple) and waiting[0] == "caption":
        panel["events"].append(("caption", spans["caption-text"], waiting[1]))
    else:
        _join(panel, spans["caption-text"])
    return None


def _sound(panel: dict[str, Any], spans: dict[str, str], _waiting: Any) -> Any:
    # The sound is on the SFX line, or on the line after a bare `SFX:` cue.
    if "sfx-text" in spans:
        panel["events"].append(("sfx", spans["sfx-text"]))
    return "complete"


def _cue(panel: dict[str, Any], spans: dict[str, str], _waiting: Any) -> Any:
    voice_over = _is_voice_over(spans.get("cue-parenthetical", ""))
    cue = ("spoken" if voice_over else "say", spans["cue-name"])
    if "dialogue" not in spans:
        return cue
    # `ALICE: Hello.`: the line is on the cue's own line.
    return _dialogue(panel, {"dialogue": spans["dialogue"]}, cue)


def _dialogue(panel: dict[str, Any], spans: dict[str, str], waiting: Any) -> Any:
    if isinstance(waiting, tuple) and waiting[0] == "say":
        panel["events"].append(("say", waiting[1], spans["dialogue"]))
    elif isinstance(waiting, tuple) and waiting[0] == "spoken":
        panel["events"].append(("caption", spans["dialogue"], "spoken"))
    else:
        # A wrapped line of the same speech.
        _join(panel, spans["dialogue"])
    return None


#: Which reader takes a line, by the first of these classes on it.
_READERS = (
    ("caption-keyword", _caption_label),
    ("caption-text", _caption_text),
    ("sfx-keyword", _sound),
    ("sfx-text", _sound),
    ("cue-name", _cue),
    ("dialogue", _dialogue),
)


def _as_compiler_reads(text: str) -> list[dict[str, Any]]:
    """The same, from the script frontend's own drafts."""
    front, body, offset = _split_front_matter(text, None)
    cast = frozenset(front.get("cast", {}))
    panels = []
    for draft in _read_script(body, None, offset=offset, cast=cast).drafts.values():
        events = []
        for event in draft.events:
            if "say" in event:
                events.append(("say", event["say"]["by"], event["say"]["text"]))
            elif "sfx" in event:
                events.append(("sfx", event["sfx"]["text"]))
            else:
                events.append(("caption", event["caption"]["text"], event["caption"]["kind"]))
        panels.append(
            {
                "label": draft.label,
                "page": draft.page,
                "description": draft.description,
                "events": events,
                "directives": [*draft.camera, *draft.settings],
            }
        )
    return panels


@pytest.mark.parametrize("name", NAMES)
def test_every_line_is_described(name: str):
    lines = _script(name).split("\n")
    if lines[-1] == "":
        lines.pop()
    tokens = _tokens(name)
    assert len(tokens) == len(lines)
    for number, (line, spans) in enumerate(zip(lines, tokens, strict=True), start=1):
        for kind, text in spans:
            assert kind in CLASSES, f"line {number}: unknown class {kind!r}"
            assert text, f"line {number}: an empty {kind!r} span"
            assert text in line, f"line {number}: {text!r} is not on the line"


@pytest.mark.parametrize("name", NAMES)
def test_the_panels_are_the_compilers(name: str):
    assert _as_fixture_says(_tokens(name)) == _as_compiler_reads(_script(name))


@pytest.mark.parametrize("name", NAMES)
def test_front_matter_is_where_the_compiler_finds_it(name: str):
    _, _, offset = _split_front_matter(_script(name), None)
    front = {"front-matter", "front-matter-delimiter"}
    for number, spans in enumerate(_tokens(name)):
        inside = any(kind in front for kind, _ in spans)
        if number < offset:
            assert inside or not spans, f"line {number + 1} is front matter"
        else:
            assert not inside, f"line {number + 1} is not front matter"


def test_the_fixtures_cover_every_class():
    """A class no fixture uses is a rule no test holds either tokenizer to."""
    used = {kind for name in NAMES for line in _tokens(name) for kind, _ in line}
    assert used == CLASSES
