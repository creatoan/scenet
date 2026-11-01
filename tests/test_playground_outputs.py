"""Every output the compiler writes can be seen in the playground (#236, #238).

The playground is the project's shop window and its first tutorial: an output it cannot show
is a gap. So every export for image models has a tab of its own, the screen-reader text has
one, and every option of `scenet build` is either something the playground shows or says why
it is not -- a new flag without an entry here fails, until someone decides which it is.
"""

import argparse
import re
from pathlib import Path

from scenet.cli import build_parser
from scenet.emit.export import EXPORTS

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")

#: Each option of `scenet build`, and where the playground shows it: an element's `#id` on
#: the page, or, for one that is not a view, why it needs none.
BUILD_OPTIONS: dict[str, str] = {
    "--output": "Where the files go: a download takes the name build gives the file.",
    "--core": "#tab-core",
    "--debug": "#tab-debug",
    "--conditioning": "#tab-pose",
    "--live-text": "#option-live-text",
    "--mono": "Write `palette: mono` in the document: it draws byte for byte what --mono does.",
    "--no-aria": "It writes less, not more; the Screen reader tab shows what it leaves out.",
    "--embed-images": "Always on: a picture beside a file is not beside a page.",
    "--strip": "#layout-strip",
    "--quiet": "The notes are always shown, under the tabs.",
}


def _ids() -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', PAGE))


def _build_options() -> set[str]:
    parser = build_parser()
    (group,) = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    build: argparse.ArgumentParser = group.choices["build"]
    return {
        max(action.option_strings, key=len)
        for action in build._actions
        if action.option_strings and not isinstance(action, argparse._HelpAction)
    }


def test_every_export_for_image_models_has_a_tab():
    tabs = set(re.findall(r'role="tab"[^>]*\bdata-export="([^"]+)"', PAGE))
    assert tabs == {suffix for suffix, _ in EXPORTS}


def test_the_screen_reader_text_has_a_tab():
    assert "tab-outline" in _ids()


def test_the_files_beside_the_document_have_a_tab():
    assert "tab-files" in _ids()


def test_every_build_option_is_shown_or_says_why_not():
    assert set(BUILD_OPTIONS) == _build_options()


def test_every_option_shown_is_on_the_page():
    ids = _ids()
    for option, where in BUILD_OPTIONS.items():
        if where.startswith("#"):
            assert where[1:] in ids, option


def test_every_layout_has_its_choice():
    """Pages, a strip, or each panel on its own: what build writes for a document of several."""
    assert {"layout-pages", "layout-strip", "layout-panels"} <= _ids()
