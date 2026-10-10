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

from scenet.frontends.script_front import _page_label, _read_panels, _split_front_matter

FIXTURES = Path(__file__).parent / "script_highlighting"
NAMES = sorted(path.stem for path in FIXTURES.glob("*.script"))

CLASSES = {
    "front-matter-delimiter",
    "front-matter",
    "page-keyword",
    "page-label",
    "panel-keyword",
    "panel-label",
    "directive-marker",
    "directive-name",
    "directive-value",
    "cue-name",
    "cue-parenthetical",
    "caption-keyword",
    "caption-kind",
    "caption-text",
    "dialogue",
    "prose",
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
    for line in lines:
        spans = dict(line)
        if "page-keyword" in spans:
            page = _page_label(spans["page-label"])
            speaker = None
            continue
        if "panel-keyword" in spans:
            panels.append(
                {
                    "label": spans["panel-label"],
                    "page": page,
                    "description": [],
                    "events": [],
                    "directives": [],
                }
            )
            speaker = None
            continue
        if not panels:
            continue
        panel = panels[-1]
        if "directive-name" in spans:
            panel["directives"].append(spans["directive-name"])
        elif "caption-keyword" in spans:
            kind = spans.get("caption-kind", "locale")
            panel["events"].append(("caption", spans["caption-text"], kind))
            speaker = None
        elif "cue-name" in spans:
            speaker = spans["cue-name"]
        elif "dialogue" in spans:
            if speaker is not None:
                panel["events"].append(("say", speaker, spans["dialogue"]))
                speaker = None
            else:
                # A wrapped line of the same speech.
                kind, by, text = panel["events"][-1]
                panel["events"][-1] = (kind, by, f"{text} {spans['dialogue']}")
        elif "prose" in spans:
            panel["description"].append(spans["prose"])
    return panels


def _as_compiler_reads(text: str) -> list[dict[str, Any]]:
    """The same, from the script frontend's own drafts."""
    _, body, offset = _split_front_matter(text, None)
    panels = []
    for draft in _read_panels(body, None, offset=offset).values():
        events = []
        for event in draft.events:
            if "say" in event:
                events.append(("say", event["say"]["by"], event["say"]["text"]))
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
