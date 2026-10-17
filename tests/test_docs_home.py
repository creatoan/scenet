"""The documentation's home page shows its example compiled, and opens it in the playground.

The example is the gallery's first, the one the playground opens by default, so all three
must stay one document: the YAML on the page, the picture under it, and the share link the
"Open it in the playground" button carries. Each is checked against the gallery file, and
the picture against the golden digest of that file's build -- so it cannot drift from what
the compiler draws today. `scripts/update_golden.py` rewrites the picture with the goldens.
"""

import base64
import hashlib
import json
import re
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "docs" / "index.md"
EXAMPLE = ROOT / "examples" / "gallery" / "01-two-characters.panel.yaml"
PICTURE = ROOT / "docs" / "images" / "two-characters.svg"
DIGESTS = ROOT / "tests" / "golden" / "digests.json"
PLAYGROUND = "https://creatoan.github.io/scenet/playground/"


def _home() -> str:
    return HOME.read_text(encoding="utf-8")


def _example() -> str:
    """The gallery document, without the comment that introduces it there."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines(keepends=True)
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return "".join(lines)


def _first_yaml_block() -> str:
    match = re.search(r"```yaml\n(.*?)```", _home(), re.DOTALL)
    assert match, "the home page shows a YAML example"
    return match.group(1)


def test_the_example_is_the_gallerys_first():
    """The one the playground opens by default, and the gallery compiles in every test run."""
    assert _first_yaml_block() == _example()
    manifest = (ROOT / "examples" / "gallery" / "manifest.yaml").read_text(encoding="utf-8")
    assert re.search(r"examples:\s*\n\s*- file: 01-two-characters\.panel\.yaml", manifest)


def test_the_picture_is_what_the_compiler_draws():
    """The same bytes `scenet build` writes for the gallery file, per the goldens."""
    digests = json.loads(DIGESTS.read_text(encoding="utf-8"))
    assert hashlib.sha256(PICTURE.read_bytes()).hexdigest() == digests["01-two-characters.svg"], (
        "stale; run `uv run python scripts/update_golden.py`"
    )


def test_the_picture_follows_the_example():
    home = _home()
    picture = home.index("](images/two-characters.svg)")
    assert home.index("```yaml") < picture < home.index("## Try it without installing anything")


def test_the_button_opens_this_example_in_the_playground():
    """A share link, as the playground's own Share button makes: deflate-raw, base64url."""
    match = re.search(re.escape(PLAYGROUND) + r"#src=([A-Za-z0-9_-]+)", _home())
    assert match, "the home page links the playground with the example in the fragment"
    token = match.group(1)
    packed = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert zlib.decompress(packed, wbits=-15).decode("utf-8") == _example()
