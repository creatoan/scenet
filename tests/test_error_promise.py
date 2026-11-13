"""`except ScenetError` catches every error a public call raises for bad input or a bad file.

`scenet.errors` makes that promise, and it was false: renderers raised a plain `ValueError`,
`PanelCore.actor` a plain `KeyError`, `compile_file` the `OSError` it read the file with,
and `load_puppet` pydantic's `ValidationError`. Each case below is one such call. What it
raises must be a `ScenetError` -- and still the built-in it was before, so a caller's
`except ValueError` or `except FileNotFoundError` keeps working.

The second half holds the source to it: a plain built-in raised anywhere in the package is
either on the short list below, with the reason it can never reach a caller, or a failure.
"""

import ast
import builtins
from collections.abc import Callable
from pathlib import Path

import pytest

from scenet import (
    AssetError,
    CoreSyntaxError,
    FileReadError,
    MalformedAssetError,
    MissingFileError,
    PageCore,
    PanelCore,
    PanelSyntaxError,
    PuppetLibrary,
    RenderError,
    ScenetError,
    SourceError,
    UnknownActorError,
    compile_book,
    compile_book_file,
    compile_document,
    compile_file,
    compile_scene_file,
    compile_source,
    load_panel,
    load_puppet,
    load_scene,
    load_scene_document,
    load_script,
    render,
    render_conditioning,
    render_debug,
    render_page,
    render_pages,
    render_pdf,
    render_strip,
)
from scenet.assets.contract import DEFAULT_LIBRARY_PATH
from scenet.solve.text import FontMetrics
from tests.images import jpeg
from tests.under_mutmut import reads_the_source

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "scenet"
GALLERY = ROOT / "examples" / "gallery"
COMIC_NEUE = (GALLERY / "fonts" / "ComicNeue-Regular.ttf").read_bytes()

PANEL = "cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: Hello.}}]\n"
PAGE = "cast: {a: {reference: alice}}\npanels: {one: {}}\npages: [{tiers: [{panels: [one]}]}]\n"


def _raised(call: Callable[[], object]) -> BaseException:
    with pytest.raises(Exception) as caught:  # noqa: PT011 -- what it is, is what is tested
        call()
    return caught.value


def _promised(call: Callable[[], object], error: type[ScenetError], builtin: type[Exception]):
    raised = _raised(call)
    assert isinstance(raised, error), f"{type(raised).__name__}: {raised}"
    assert isinstance(raised, ScenetError)
    assert isinstance(raised, builtin), f"{type(raised).__name__} is no longer a {builtin}"


# ---------------------------------------------------------------- a file that is not there


@pytest.mark.parametrize(
    ("call", "name"),
    [
        (compile_file, "missing.panel.yaml"),
        (compile_scene_file, "missing.scene.yaml"),
        (compile_book_file, "missing.panel.yaml"),
        (compile_document, "missing.scene.yaml"),
        (compile_book_file, "missing.script"),
        (load_panel, "missing.panel.yaml"),
        (load_scene, "missing.scene.yaml"),
        (load_scene_document, "missing.scene.yaml"),
        (load_script, "missing.script"),
        (load_puppet, "missing.puppet.yaml"),
        (FontMetrics, "missing.ttf"),
    ],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_a_missing_file_is_a_scenet_error_and_still_file_not_found(
    tmp_path: Path, call: Callable[[Path], object], name: str
):
    _promised(lambda: call(tmp_path / name), MissingFileError, FileNotFoundError)


def test_it_keeps_what_the_system_said(tmp_path: Path):
    raised = _raised(lambda: compile_file(tmp_path / "missing.panel.yaml"))
    assert isinstance(raised, OSError)
    assert raised.errno is not None
    assert raised.filename == str(tmp_path / "missing.panel.yaml")
    assert isinstance(raised.__cause__, FileNotFoundError)


def test_a_file_that_cannot_be_read_is_a_scenet_error_and_still_an_os_error(tmp_path: Path):
    """A folder named like a document: read, it fails, though not as "not found"."""
    folder = tmp_path / "folder.panel.yaml"
    folder.mkdir()
    _promised(lambda: compile_file(folder), FileReadError, OSError)


def test_a_document_that_is_not_utf8_is_a_syntax_error(tmp_path: Path):
    path = tmp_path / "latin1.panel.yaml"
    path.write_bytes("cast: {a: {reference: alice}}\n# café\n".encode("latin-1"))
    _promised(lambda: compile_file(path), PanelSyntaxError, ValueError)
    assert "UTF-8" in str(_raised(lambda: compile_file(path)))


@pytest.mark.parametrize("call", [compile_book_file, compile_document])
def test_an_extension_no_frontend_reads_is_a_source_error(
    tmp_path: Path, call: Callable[[Path], object]
):
    path = tmp_path / "notes.txt"
    path.write_text(PANEL, encoding="utf-8")
    _promised(lambda: call(path), SourceError, ValueError)


# ---------------------------------------------------------------- puppets and fonts


def test_a_puppet_that_is_not_one_is_a_malformed_asset_and_still_a_value_error(tmp_path: Path):
    """It was pydantic's `ValidationError`, which no `except ScenetError` caught."""
    path = tmp_path / "x.puppet.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    _promised(lambda: load_puppet(path), MalformedAssetError, ValueError)
    assert isinstance(_raised(lambda: load_puppet(path)), AssetError)


def test_its_message_names_the_file_and_the_field(tmp_path: Path):
    path = tmp_path / "x.puppet.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    message = str(_raised(lambda: load_puppet(path)))
    assert str(path) in message
    assert "units_per_head" in message


def test_a_puppet_file_that_is_not_yaml_is_a_malformed_asset_still(tmp_path: Path):
    path = tmp_path / "x.puppet.yaml"
    path.write_text("name: [\n", encoding="utf-8")
    _promised(lambda: load_puppet(path), MalformedAssetError, ValueError)


def test_two_puppets_of_one_name_in_a_folder_are_a_malformed_asset(tmp_path: Path):
    alice = (DEFAULT_LIBRARY_PATH / "alice.puppet.yaml").read_bytes()
    (tmp_path / "a.puppet.yaml").write_bytes(alice)
    (tmp_path / "b.puppet.yaml").write_bytes(alice)
    _promised(lambda: PuppetLibrary.from_directory(tmp_path), MalformedAssetError, ValueError)


def test_a_font_that_is_not_a_font_is_a_malformed_asset(tmp_path: Path):
    path = tmp_path / "x.ttf"
    path.write_bytes(b"not a font")
    _promised(lambda: FontMetrics(path), MalformedAssetError, ValueError)


# ---------------------------------------------------------------- Panel Core


@pytest.fixture(scope="module")
def core() -> PanelCore:
    return compile_source(PANEL).core


@pytest.mark.parametrize("lookup", ["actor", "speaker"])
def test_an_actor_the_panel_does_not_hold_is_a_scenet_error_and_still_a_key_error(
    core: PanelCore, lookup: str
):
    _promised(lambda: getattr(core, lookup)("nobody"), UnknownActorError, KeyError)


@pytest.mark.parametrize("model", [PanelCore, PageCore])
@pytest.mark.parametrize("text", ["{", "{}", "[]"], ids=["not-json", "incomplete", "not-a-map"])
def test_a_core_document_that_cannot_be_read_back_is_a_core_syntax_error(
    model: type[PanelCore] | type[PageCore], text: str
):
    """It was `json.JSONDecodeError` or pydantic's `ValidationError`: both `ValueError`s."""
    _promised(lambda: model.from_json(text), CoreSyntaxError, ValueError)


def test_its_message_says_where(core: PanelCore):
    assert "width" in str(_raised(lambda: PanelCore.from_json("{}")))
    assert "line 1" in str(_raised(lambda: PanelCore.from_json("{")))


# ---------------------------------------------------------------- renderers


@pytest.fixture(scope="module")
def lettered() -> PanelCore:
    """A panel lettered in a font of its own, which a renderer must be handed back."""
    return compile_source(
        "lettering: {font: fonts/neue.ttf}\n" + PANEL, base={"fonts/neue.ttf": COMIC_NEUE}
    ).core


def test_a_font_not_handed_back_is_a_render_error(lettered: PanelCore):
    _promised(lambda: render(lettered), RenderError, ValueError)


@pytest.mark.parametrize("draw", [render_debug, render_conditioning], ids=lambda d: d.__name__)
def test_a_drawing_with_no_lettering_needs_no_font(
    lettered: PanelCore, draw: Callable[[PanelCore], object]
):
    """The debug overlay draws boxes, and conditioning images draw shapes: no glyph."""
    assert draw(lettered)


def test_so_it_is_on_a_strip_a_page_and_in_print(lettered: PanelCore):
    page = compile_book(PAGE).pages[0]
    _promised(lambda: render_strip([("one", lettered)]), RenderError, ValueError)
    _promised(lambda: render_page(page, {"one": lettered}), RenderError, ValueError)
    _promised(lambda: render_pdf([page], {"one": lettered}), RenderError, ValueError)


def test_a_picture_not_handed_over_is_a_render_error():
    book = compile_book_file(GALLERY / "52-a-jpeg.panel.yaml")
    core = next(iter(book.panels.values())).core
    _promised(lambda: render(core, fonts=book.fonts, embed={}), RenderError, ValueError)
    cores = {key: result.core for key, result in book.panels.items()}
    _promised(lambda: render_pdf(book.pages, cores, fonts=book.fonts), RenderError, ValueError)


def test_a_picture_print_cannot_carry_is_a_render_error():
    book = compile_book(
        "setting: {image: art/lossless.jpg}\n" + PANEL,
        base={"art/lossless.jpg": jpeg(400, 300, frame=0xC3)},
    )
    cores = {key: result.core for key, result in book.panels.items()}
    _promised(
        lambda: render_pdf(book.pages, cores, fonts=book.fonts, images=book.images),
        RenderError,
        ValueError,
    )


def test_a_page_placing_a_panel_not_given_is_a_render_error():
    page = compile_book(PAGE).pages[0]
    _promised(lambda: render_page(page, {}), RenderError, ValueError)
    _promised(lambda: render_pages([page], {}), RenderError, ValueError)
    _promised(lambda: render_pdf([page], {}), RenderError, ValueError)


def test_nothing_to_draw_is_a_render_error():
    _promised(lambda: render_strip([]), RenderError, ValueError)
    _promised(lambda: render_pages([], {}), RenderError, ValueError)


def test_panels_read_two_ways_side_by_side_are_a_render_error(core: PanelCore):
    rtl = compile_source("direction: rtl\n" + PANEL).core
    _promised(lambda: render_strip([("a", core), ("b", rtl)]), RenderError, ValueError)


# ---------------------------------------------------------------- the source, held to it

#: Every plain built-in exception the package may raise, by module and function, with the
#: reason no caller of a public name ever sees it. Anything else is a broken promise.
NEVER_REACHES_A_CALLER: dict[tuple[str, str], str] = {
    # pydantic catches what a validator raises and re-raises its own `ValidationError`,
    # which a frontend turns into a `PanelSyntaxError` with a location.
    ("ir.py", "_holdable"): "called by validators only",
    ("ir.py", "_check_marks"): "the body of a validator",
    ("ir.py", "_check_off_panel"): "the body of a validator",
    ("core.py", "_check_runs"): "called by validators only",
    # Invariants of the compiler itself: a failure is a bug in Scenet, not bad input.
    ("solve/camera.py", "solve_camera"): "every shot's headroom and footroom leave room",
    ("solve/backdrop.py", "_luminance"): "only greys are measured",
    ("solve/backdrop.py", "solve_backdrop"): "the pipeline reads a picture's size with it",
    ("solve/text.py", "__post_init__"): "the solver builds a run with a face per character",
    ("emit/pdf.py", "_veil"): "a veil is always painted in an ink",
    ("emit/pdf.py", "_path"): "every shape the emitter draws has a path",
    # Internal names, never reached through a public one.
    ("assets/kinematics.py", "anchor"): "a posed puppet's anchors are looked up internally",
    ("spec_pack.py", "part"): "the spec pack's parts are named by the package itself",
}


def _builtin_raises() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        module = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.Raise) or node.exc is None:
                    continue
                raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if isinstance(raised, ast.Name) and isinstance(
                    getattr(builtins, raised.id, None), type
                ):
                    found.add((module, function.name))
    return found


@reads_the_source
def test_no_plain_built_in_is_raised_where_a_caller_could_see_it():
    unexplained = sorted(_builtin_raises() - set(NEVER_REACHES_A_CALLER))
    assert unexplained == [], (
        "raise a ScenetError that keeps this built-in as a base (scenet.errors), or add "
        "the function to NEVER_REACHES_A_CALLER with the reason a caller never sees it"
    )


@reads_the_source
def test_the_list_holds_nothing_that_is_gone():
    assert sorted(set(NEVER_REACHES_A_CALLER) - _builtin_raises()) == []
