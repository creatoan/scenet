"""The `scenet-example` directive: a document, the picture it compiles to, and a playground link.

A key card in the language reference ends on a minimal document that shows its key. Written
as this directive rather than as a plain YAML block, it is compiled when the documentation is
built, as `scenet build` would compile it, and shown with its picture and a link that opens
it in the playground::

    ```{scenet-example}
    camera: {shot: close_up}
    cast: {alice: {reference: alice}}
    ```

The picture is the compiler's output for the version being documented. It is kept with the
build's environment and written beside the build's own images, never into `docs/`, so no
stale copy can sit in the source. A document that does not compile fails the build, as
`tests/test_doc_examples.py` fails it. On GitHub, which renders the page without Sphinx, the
block reads as the document it holds.

Options:

`:kind:`
    `panel`, `scene` or `script`. Left out, a document holding `panels:` or `pages:` is a
    scene and any other a panel.
`:beside:`
    A folder of the repository the document is compiled in, so that the files it names -- a
    picture, a font, a puppet -- are found: `examples/gallery`. A link cannot carry those
    files to the playground, so such a document names the gallery example to open instead.
`:playground:`
    The gallery example the link opens, in place of the document itself.
"""

import base64
import hashlib
import html
import re
import zlib
from pathlib import Path
from typing import Any, ClassVar

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util.docutils import SphinxDirective

from scenet import compile_book, compile_script, compile_source, render, render_pages, render_strip

ROOT = Path(__file__).resolve().parents[2]

#: The playground, by its full address. `docs/conf.py` makes it relative in each version.
PLAYGROUND = "https://creatoan.github.io/scenet/playground/"

#: Where the pictures are written, under the build's output.
PICTURES = "_images/examples"

#: What a document is, by its option: the directive reads `:kind:` as the tests do.
KINDS = ("panel", "scene", "script")


def share_token(text: str) -> str:
    """The playground's share token for a document: raw deflate, then base64url.

    `playground/src/persist.ts` decodes it with `DecompressionStream("deflate-raw")`.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = compressor.compress(text.encode("utf-8")) + compressor.flush()
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def kind_of(text: str) -> str:
    """A panel, unless the document holds panels or pages: a scene."""
    return "scene" if re.search(r"^(panels|pages):", text, re.MULTILINE) else "panel"


def picture(text: str, kind: str, beside: Path | None) -> str:
    """The SVG a document compiles to, as `scenet build` draws it, its pictures in it."""
    if kind == "panel":
        result = compile_source(text, base=beside)
        return render(result.core, fonts=result.fonts, embed=result.images)
    book = (
        compile_script(text, base=beside) if kind == "script" else compile_book(text, base=beside)
    )
    cores = {name: result.core for name, result in book.panels.items()}
    if book.pages:
        return render_pages(book.pages, cores, fonts=book.fonts, embed=book.images)
    return render_strip(list(cores.items()), fonts=book.fonts, embed=book.images)


def spoken(svg: str) -> str:
    """What a screen reader says of the picture: every title it holds, in order."""
    titles = re.findall(r"<title>(.*?)</title>", svg, re.DOTALL)
    return " ".join(html.unescape(title) for title in titles)


def _pictures(env: BuildEnvironment) -> dict[str, dict[str, str]]:
    """The pictures each page's examples compiled to, by page and file name."""
    if not hasattr(env, "scenet_examples"):
        env.scenet_examples = {}  # type: ignore[attr-defined]
    return env.scenet_examples  # type: ignore[attr-defined,no-any-return]


class ScenetExample(SphinxDirective):
    """A document of the language, compiled: its source, its picture and a playground link."""

    has_content = True
    option_spec: ClassVar[dict[str, Any]] = {  # type: ignore[misc]
        "kind": lambda value: directives.choice(value, KINDS),
        "beside": directives.unchanged_required,
        "playground": directives.unchanged_required,
    }

    def run(self) -> list[nodes.Node]:
        """The document as a code block, then its picture, then the playground link."""
        text = "\n".join(self.content) + "\n"
        kind = self.options.get("kind") or kind_of(text)
        beside = ROOT / self.options["beside"] if "beside" in self.options else None
        if beside is not None and "playground" not in self.options:
            raise self.error(":beside: needs :playground:, the gallery example to open")
        try:
            svg = picture(text, kind, beside)
        except Exception as error:
            raise self.error(f"this example does not compile: {error}") from error

        name = hashlib.sha256(f"{kind}\n{text}".encode()).hexdigest()[:16] + ".svg"
        _pictures(self.env).setdefault(self.env.docname, {})[name] = svg
        root = self.env.app.builder.get_relative_uri(self.env.docname, "index")
        root = root.removesuffix("index.html")

        language = "scenet-script" if kind == "script" else "yaml"
        source = nodes.literal_block(text, text, language=language)
        shown = nodes.raw(
            "",
            f'<p class="scenet-example-picture"><img src="{root}{PICTURES}/{name}" '
            f'alt="{html.escape(spoken(svg), quote=True)}"></p>',
            format="html",
        )
        if "playground" in self.options:
            target = f"{PLAYGROUND}#example={self.options['playground']}"
        else:
            target = f"{PLAYGROUND}#src={share_token(text)}"
        link = nodes.paragraph()
        link += nodes.reference("", "Open in the playground", refuri=target)
        container = nodes.container(classes=["scenet-example"])
        container += [source, shown, link]
        return [container]


def _purge(app: Sphinx, env: BuildEnvironment, docname: str) -> None:
    _pictures(env).pop(docname, None)


def _merge(app: Sphinx, env: BuildEnvironment, docnames: set[str], other: BuildEnvironment) -> None:
    _pictures(env).update(
        {docname: found for docname, found in _pictures(other).items() if docname in docnames}
    )


def _write(app: Sphinx, exception: BaseException | None) -> None:
    """Write every picture beside the build's images, once the pages that show them are."""
    if exception is not None or app.builder.format != "html":
        return
    folder = Path(app.builder.outdir) / PICTURES
    folder.mkdir(parents=True, exist_ok=True)
    for found in _pictures(app.env).values():
        for name, svg in sorted(found.items()):
            (folder / name).write_text(svg, encoding="utf-8", newline="\n")


def setup(app: Sphinx) -> dict[str, object]:
    """Register the directive, and keep its pictures with the build's environment."""
    app.add_directive("scenet-example", ScenetExample)
    app.connect("env-purge-doc", _purge)
    app.connect("env-merge-info", _merge)
    app.connect("build-finished", _write)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
