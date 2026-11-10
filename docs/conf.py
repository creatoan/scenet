# Sphinx configuration.
#
# Docs source stays Markdown (MyST) so that GitHub renders every page without a build
# step -- a reader who lands in the repository gets the documentation, not a pile of
# markup they have to compile.
#
# Warnings are errors in CI (`sphinx-build -W`). A broken cross-reference or a page
# missing from a toctree fails the build rather than quietly producing a worse site.

import importlib
import os
import re
import sys
import zlib
from collections.abc import Collection, Iterator
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path

from docutils import nodes
from docutils.utils import get_source_line
from sphinx.application import Sphinx
from sphinx.util import logging

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# The MCP SDK is imported here, before any extension runs, and not left for autodoc to
# reach. sphinx-autodoc-typehints executes the `if TYPE_CHECKING:` block of each module
# whose annotations it resolves -- pydantic's among them -- and once it has done that to
# pydantic, a model declaring `extra="allow"` no longer builds. The SDK defines several,
# so `scenet.mcp` failed to import part-way through the build. Built first, they are
# already built.
import mcp  # noqa: F401

# -- Project ------------------------------------------------------------------

project = "Scenet"
# No personal name here or anywhere else in the repository, deliberately.
copyright = f"{datetime.now(UTC).year}, Scenet contributors"
author = "Scenet contributors"

# Which version this documents. The site serves several -- the latest release at its root,
# `main` under /dev/, each minor version under /vX.Y/ -- and the version switcher and the
# warning banner key on what each build says here (docs/explanation/design_decisions.md).
#
# A release documents the installed package. The build of `main` says "dev", which
# scripts/build_site.py sets: between releases `main` carries the last release's version
# number, so it could not be told apart otherwise. An explicit X.Y.Z is for the tests.
_documented = os.environ.get("SCENET_DOCS_VERSION") or package_version("scenet")
if _documented == "dev":
    release = version = "dev"
else:
    release = _documented
    version = ".".join(release.split(".")[:2])

# Every page of every version names its counterpart at the root as canonical, so a search
# engine sends readers to the current documentation rather than an old copy of it.
html_baseurl = "https://creatoan.github.io/scenet/"

# -- General ------------------------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # understands the Google-style Args/Returns/Raises sections
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",  # every documented symbol links to its source
    "sphinx_autodoc_typehints",
    "sphinx_design",
    "sphinx_copybutton",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Single backticks mean "code", matching how the docstrings read in source and in
# `help()`. Without this, rST's default turns them into title references.
default_role = "literal"

# -- MyST ---------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",  # bare URLs become links
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# linkify, left to itself, treats anything shaped like a domain as a link -- and `.id`,
# `.by`, `.at`, `.name`, `.ir` and `.cy` are all real top-level domains. So every
# `CoreActor.id` and `SayEvent.by` in the API reference became a hyperlink to somebody
# else's website. Fuzzy linking off: an explicit scheme is now required, which still
# covers every real URL in these documents.
myst_linkify_fuzzy_links = False

# -- autodoc ------------------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",  # source order is meaningful; alphabetical is not
    "show-inheritance": True,
    "undoc-members": False,
    # Pydantic adds a dozen machinery members to every model. They are noise in a
    # reference page and none of them are part of this project's API.
    "exclude-members": (
        "model_config,model_fields,model_computed_fields,model_post_init,"
        "model_construct,model_copy,model_dump,model_dump_json,model_json_schema,"
        "model_parametrized_name,model_rebuild,model_validate,model_validate_json,"
        "model_validate_strings,copy,dict,json,schema,schema_json,construct,"
        "parse_obj,parse_raw,parse_file,from_orm,update_forward_refs,validate"
    ),
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented_params"
autodoc_class_signature = "separated"
always_use_bars_union = True
typehints_use_signature = False
typehints_use_signature_return = False

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_rtype = False

# -- intersphinx ---------------------------------------------------------------
#
# Cross-project links, so a `dict[str, PuppetSpec]` in a signature reaches the standard
# library docs and a `ValidationError` reaches pydantic's. This is the thing Qt gets
# right that most Python projects skip: a reference that dead-ends at a type name you
# have to go and search for is half a reference.

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
    "shapely": ("https://shapely.readthedocs.io/en/stable", None),
}
# Resolving these needs network access. CI has it; a local build without it should warn
# rather than fail, so the timeout is short.
intersphinx_timeout = 10

# -- HTML ----------------------------------------------------------------------

html_theme = "pydata_sphinx_theme"
templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["scenet.css"]
html_title = f"Scenet {version}"
html_copy_source = False
html_show_sourcelink = False

html_theme_options = {
    "github_url": "https://github.com/creatoan/scenet",
    "use_edit_page_button": False,
    "show_prev_next": True,
    "navigation_with_keys": True,
    "show_toc_level": 2,
    "header_links_before_dropdown": 6,
    "icon_links": [
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/scenet/",
            "icon": "fa-solid fa-box",
        },
    ],
    # The playground is named in the navbar, beside the sections, and not left an icon at
    # the far end. A template rather than an entry in `external_links`, because it is
    # relative: each version's documentation opens that version's playground.
    "navbar_start": ["navbar-logo", "version-switcher"],
    "navbar_center": ["navbar-nav", "playground-link"],
    # One switcher.json for every version, so an old version lists the releases made after
    # it. Site-absolute rather than a full URL, so the local preview -- served under
    # /scenet/ too -- reads the one beside it. See scripts/site_versions.py.
    "switcher": {"json_url": "/scenet/switcher.json", "version_match": version},
    # The check fetches json_url while building: a network request, and a -W failure
    # whenever the file is not there yet. scripts/site_versions.py checks the file instead.
    "check_switcher": False,
    # Shown on /dev/ and on old versions, with a link to the same page in the latest.
    "show_version_warning_banner": True,
    "footer_start": ["copyright"],
    "footer_end": [],
}

html_context = {
    "github_user": "creatoan",
    "github_repo": "scenet",
    "github_version": "main",
    "default_mode": "auto",
}

# -- Links to the playground ---------------------------------------------------
#
# The Markdown links the playground by its full address, the only kind that works where
# GitHub renders these pages. Built, each link becomes relative, so every version of the
# documentation opens its own version's playground rather than the latest one's.

_PLAYGROUND = f"{html_baseurl}playground/"


def _playground_links_stay_in_their_version(
    app: Sphinx, doctree: nodes.document, docname: str
) -> None:
    root = app.builder.get_relative_uri(docname, "index").removesuffix("index.html")
    for reference in doctree.findall(nodes.reference):
        target = reference.get("refuri", "")
        if target.startswith(_PLAYGROUND):
            reference["refuri"] = f"{root}playground/{target.removeprefix(_PLAYGROUND)}"


# -- What a build must show ----------------------------------------------------
#
# `-W` fails a build on what Sphinx warns about, and Sphinx does not warn about a page that
# renders the wrong thing. From v0.8 on, every version of the API reference showed
# autodoc's reStructuredText as text -- MyST had read it as Markdown -- and published an
# `objects.inv` with no Python object in it, while every build passed (#316). Both checks
# below warn, so `-W` fails such a build.

_logger = logging.getLogger("scenet.docs")

#: What autodoc, napoleon and sphinx-autodoc-typehints write for reStructuredText to read.
#: Found as text on a built page, it is markup that never rendered.
_RAW_MARKUP = (".. py:", ":py:", ".. admonition::", ".. seealso::", "sphinx_autodoc_typehints")

#: Elements that show their text exactly as it is written. Markup quoted in code is meant.
_AS_WRITTEN = (nodes.literal, nodes.literal_block, nodes.raw, nodes.comment)


def _raw_markup(doctree: nodes.Node) -> Iterator[tuple[nodes.Text, str]]:
    """Each text node on a page that holds raw markup, with the markup it holds."""
    for text in doctree.findall(nodes.Text):
        if _shown_as_written(text):
            continue
        for marker in _RAW_MARKUP:
            if marker in text:
                yield text, marker
                break


def _shown_as_written(node: nodes.Node) -> bool:
    parent = node.parent
    while parent is not None:
        if isinstance(parent, _AS_WRITTEN):
            return True
        parent = parent.parent
    return False


def _no_raw_markup(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    for text, marker in _raw_markup(doctree):
        source, _ = get_source_line(text)
        _logger.warning(
            "%s shows raw markup %r, in %r: reStructuredText that was read as something "
            "else. Autodoc runs inside an {eval-rst} fence, and docstrings are "
            "reStructuredText.",
            docname,
            marker,
            text.astext()[:60],
            location=text if source else docname,
            type="scenet",
            subtype="raw_markup",
        )


#: A line of a version 2 inventory: name, `domain:role`, priority, address, display name.
_INVENTORY_LINE = re.compile(r"(.+?)\s+(\S+)\s+(-?\d+)\s+?(\S*)\s+(.*)")


def _python_objects(inventory: Path) -> set[str]:
    """The full name of every Python object a built `objects.inv` holds.

    Read here rather than through Sphinx's loader, whose result is a private class. The
    format is four lines of header and the rest compressed: one object to a line.
    """
    header, _, body = inventory.read_bytes().partition(b"compressed using zlib.\n")
    if not header.startswith(b"# Sphinx inventory version 2\n"):
        raise ValueError(f"{inventory} is not a version 2 inventory")
    found: set[str] = set()
    for line in zlib.decompress(body).decode("utf-8").splitlines():
        match = _INVENTORY_LINE.fullmatch(line)
        if match is not None and match.group(2).startswith("py:"):
            found.add(match.group(1))
    return found


_ABSENT = object()


def _resolve(name: str) -> object:
    """The object a documented full name stands for: a module, and attributes from it."""
    parts = name.split(".")
    for split in range(len(parts), 0, -1):
        try:
            found: object = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for part in parts[split:]:
            found = getattr(found, part, _ABSENT)
        return found
    return _ABSENT


def _undocumented(documented: Collection[str]) -> list[str]:
    """Each name in `scenet.__all__` that no documented object is.

    A public name is documented under the module that defines it -- `compile_source` as
    `scenet.pipeline.compile_source` -- so a full name counts when it ends in the public
    name and stands for the same object. The same last name alone is not enough: two
    modules may each have a class called the same.
    """
    scenet = importlib.import_module("scenet")
    by_last_name: dict[str, list[str]] = {}
    for full_name in documented:
        by_last_name.setdefault(full_name.rpartition(".")[2], []).append(full_name)
    return [
        name
        for name in scenet.__all__
        if not any(
            _resolve(full_name) is getattr(scenet, name) for full_name in by_last_name.get(name, ())
        )
    ]


def _every_public_name_is_documented(app: Sphinx, exception: BaseException | None) -> None:
    # A build that documents no Python has nothing to hold to `__all__`: the site tests'
    # two-page build of this configuration, which leaves autodoc out.
    if exception is not None or app.builder.format != "html":
        return
    if "sphinx.ext.autodoc" not in app.extensions:
        return
    for name in _undocumented(_python_objects(Path(app.outdir) / "objects.inv")):
        _logger.warning(
            "scenet.%s is public, in scenet.__all__, and objects.inv holds no Python object "
            "for it: the API reference does not document it.",
            name,
            type="scenet",
            subtype="undocumented",
        )


def setup(app: Sphinx) -> None:
    app.connect("doctree-resolved", _playground_links_stay_in_their_version)
    app.connect("doctree-resolved", _no_raw_markup)
    app.connect("build-finished", _every_public_name_is_documented)
