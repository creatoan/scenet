# Sphinx configuration.
#
# Docs source stays Markdown (MyST) so that GitHub renders every page without a build
# step -- a reader who lands in the repository gets the documentation, not a pile of
# markup they have to compile.
#
# Warnings are errors in CI (`sphinx-build -W`). A broken cross-reference or a page
# missing from a toctree fails the build rather than quietly producing a worse site.

import enum
import functools
import importlib
import importlib.util
import inspect
import operator
import os
import re
import sys
import types
import typing
import zlib
from collections.abc import Collection, Iterator
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from types import ModuleType

from docutils import nodes
from docutils.utils import get_source_line
from pygments.lexers.special import TextLexer
from sphinx.application import Sphinx
from sphinx.pycode import ModuleAnalyzer
from sphinx.util import logging

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# The documentation's own extensions: `scenet-example`, which compiles a key card's document.
sys.path.insert(0, str(Path(__file__).parent / "_ext"))

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
    "scenet_examples",
]

exclude_patterns = ["_build", "_ext", "Thumbs.db", ".DS_Store"]

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
    # No "undoc-members", so a member without a docstring is left out. Sphinx reads any
    # value given for a flag as on, `False` included, and this file once said `False`:
    # every field was then documented twice -- by its class's `Attributes:` section and
    # again bare -- and `__new__` and `__init__` always showed. An enum's members, which
    # never have a docstring of their own, are kept by `_api_members_only` below.
    #
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

# -- Cross-references ------------------------------------------------------------
#
# A reference that reaches nothing is a warning, so `-W` fails the build on it. With this
# off, the API reference shipped from v0.8 on with no Python object in it, and not one
# warning said so (#316). What is left out below cannot be linked at all.

nitpicky = True
nitpick_ignore = [
    # Shapely documents each kind of geometry, not the base class they share, which is
    # the type `scenet.solve.sfx.place_effects` takes.
    ("py:class", "shapely.geometry.base.BaseGeometry"),
]
nitpick_ignore_regex = [
    # A function defined inside another has no page. One shows in a type alias, as the
    # discriminator `scenet.ir.tag_by` builds: `FaceMark` is "alias of Annotated[...]".
    (r"py:.*", r".*\.<locals>\..*"),
    # PyYAML publishes no inventory to link into, so none of its names can be linked:
    # `scenet.safe_yaml` is written against its loader, nodes and errors.
    (r"py:.*", r"yaml\..*"),
]

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
    "numpy": ("https://numpy.org/doc/stable", None),
    # The MCP SDK, for `scenet.mcp`. Its site is not Sphinx, but it publishes the same
    # inventory, filed under each name's defining module.
    "mcp": ("https://py.sdk.modelcontextprotocol.io", None),
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
    # Learn, Guides, Language, Python API, Gallery, Playground, About: none in a "More" menu.
    "header_links_before_dropdown": 7,
    "icon_links": [
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/scenet/",
            "icon": "fa-solid fa-box",
        },
    ],
    # The playground is named in the navbar, among the sections, and not left an icon at
    # the far end. It is in the landing page's table of contents, and `navbar-nav.html`
    # makes its link relative: each version's documentation opens that version's playground.
    "navbar_start": ["navbar-logo", "version-switcher"],
    "navbar_center": ["navbar-nav"],
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
    # The maintainer's documentation is for contributors, so it is linked here, not in the
    # navbar, which is for readers.
    "footer_end": ["contribute-link"],
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


#: Where the Markdown links the package's source: on main, the only one GitHub can show.
_SOURCE = "https://github.com/creatoan/scenet/blob/main/src/"


def _source_at(documented: str, target: str) -> str:
    """A source link at the release a build documents: its tag, or main for `dev`."""
    if documented == "dev" or not target.startswith(_SOURCE):
        return target
    return target.replace("/blob/main/", f"/blob/v{documented}/", 1)


def _source_links_follow_their_version(app: Sphinx, doctree: nodes.document, docname: str) -> None:
    for reference in doctree.findall(nodes.reference):
        target = reference.get("refuri")
        if target:
            reference["refuri"] = _source_at(release, target)


def _playground_links_stay_in_their_version(
    app: Sphinx, doctree: nodes.document, docname: str
) -> None:
    root = app.builder.get_relative_uri(docname, "index").removesuffix("index.html")
    for reference in doctree.findall(nodes.reference):
        target = reference.get("refuri", "")
        if target.startswith(_PLAYGROUND):
            reference["refuri"] = f"{root}playground/{target.removeprefix(_PLAYGROUND)}"


# -- What the link check cannot check ------------------------------------------
#
# `.github/workflows/linkcheck.yml` runs `-b linkcheck` every week. Two kinds of result
# there are not about the link, and are named here so that everything else still fails the
# run -- tests/test_linkcheck.py holds this section to its rules.
#
# The playground keeps its state in the fragment, `#example=<file>` or `#src=<token>`, and
# its script reads it; no element has that id, so each one was "Anchor not found". Only the
# fragment is skipped: the playground's page is checked like any other, and `^!` is
# Sphinx's own default, kept.
linkcheck_anchors_ignore = ["^!", r"^(example|src)="]

# Hosts that answer every automated client with an error page, whatever the link, so the
# check cannot tell a live page from a dead one. Ignored by host, never by page: a link
# there is "cannot verify", not "fine". Each was seen failing in the weekly runs.
linkcheck_ignore = [
    # The ACM Digital Library: 403 Forbidden.
    r"^https://dl\.acm\.org/",
    # ACM's DOI prefix, which redirects to the Digital Library above.
    r"^https://doi\.org/10\.1145/",
    # Elsevier's ScienceDirect: 403 Forbidden.
    r"^https://www\.sciencedirect\.com/",
    # PubMed Central: 403 Forbidden.
    r"^https://pmc\.ncbi\.nlm\.nih\.gov/",
    # GNOME's GitLab, behind a bot challenge: 406 Not Acceptable.
    r"^https://gitlab\.gnome\.org/",
]

# A server's bad minute is not a dead link: blambot.com answered 500 once in eleven weeks.
linkcheck_retries = 3


# -- A heading's address -------------------------------------------------------
#
# A heading is linked by its slug, as MyST and GitHub make it: `camera.md#camerashot`. MyST
# resolves such a link inside the documentation, but Sphinx's HTML names the section after
# docutils' id, `camera-shot`, so the same address typed elsewhere -- the playground's "Read
# about it", a rule's help, a link on GitHub -- landed at the top of the page (#319).


def _heading_slug(title: str) -> str:
    """A heading's anchor as MyST makes it, by `mdit_py_plugins.anchors`' rule."""
    return re.sub(r"[^\w\- ]", "", title.strip().lower().replace(" ", "-"))


def _heading_slugs_are_ids(app: Sphinx | None, doctree: nodes.document) -> None:
    """Give every section its heading's slug as an id too, unless something has it already."""
    for section in doctree.findall(nodes.section):
        title = section.next_node(nodes.title)
        if title is None:
            continue
        slug = _heading_slug(title.astext())
        if slug and slug not in section["ids"] and slug not in doctree.ids:
            section["ids"].append(slug)
            doctree.ids[slug] = section


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


# -- Which members are API -----------------------------------------------------
#
# Each public name has a page of its own, which `scripts/build_api_pages.py` writes: its
# card, then its autodoc entry. The module pages document the internals, and leave each of
# those names off, so that no object is described twice.


def _load_api_pages() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "build_api_pages.py"
    spec = importlib.util.spec_from_file_location("build_api_pages", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_api_pages", module)
    spec.loader.exec_module(module)
    return module


def _publicly_documented() -> set[int]:
    """The identity of every object a public page documents, but the version string."""
    documented: list[str] = _load_api_pages().documented_publicly()
    return {id(_resolve(name)) for name in documented if not isinstance(_resolve(name), str)}


_PUBLIC_PAGES = _publicly_documented()

#: What pydantic runs on a model and nobody calls: validators and serializers. A model's
#: computed fields are not among them; they are read like any other field.
_PYDANTIC_MACHINERY = (
    "validators",
    "field_validators",
    "root_validators",
    "field_serializers",
    "model_serializers",
    "model_validators",
)


def _pydantic_machinery(member: object, name: str) -> bool:
    """Whether a member is a validator or a serializer of the model that defines it."""
    function = getattr(member, "__func__", member)
    module = sys.modules.get(getattr(function, "__module__", None) or "")
    owner: object = module
    for part in getattr(function, "__qualname__", "").split(".")[:-1]:
        owner = getattr(owner, part, None)
    decorators = getattr(owner, "__pydantic_decorators__", None)
    return any(name in getattr(decorators, kind, {}) for kind in _PYDANTIC_MACHINERY)


def _api_members_only(  # noqa: PLR0917 -- the signature Sphinx calls it with
    app: Sphinx, what: str, name: str, member: object, skip: bool, options: object
) -> bool | None:
    """Keep an enum's members, which carry no docstring of their own, and drop machinery.

    An enum's members are its values -- `BalloonKind.SHOUT` is the `shout` an author
    writes -- so they are listed whether documented or not. What a `StrEnum` gets from
    `enum` for building its members, and the validators pydantic calls, are not API. A
    module page leaves off what a public page documents.
    """
    if what == "module" and id(member) in _PUBLIC_PAGES:
        return True
    if isinstance(member, enum.Enum) and type(member).__members__.get(name) is member:
        return False
    if name == "__new__" and member is enum.Enum.__new__:
        return True
    if _pydantic_machinery(member, name):
        return True
    return None


def _public_bases(
    app: Sphinx, name: str, obj: object, options: object, bases: list[object]
) -> None:
    """Show a private base as what it is built on: `_Strict` as pydantic's `BaseModel`."""
    bases[:] = [shown for base in bases for shown in _shown_as(base)]


def _shown_as(base: object) -> list[object]:
    if isinstance(base, type) and base.__name__.startswith("_"):
        return [shown for parent in base.__bases__ for shown in _shown_as(parent)]
    return [base]


def _no_inline_types(  # noqa: PLR0917 -- the signature Sphinx calls it with
    app: Sphinx, what: str, name: str, obj: object, options: object, lines: list[str]
) -> None:
    """Keep napoleon from reading an attribute's first line as `type: description`.

    Google style lets `#: int: The count.` give a type inline, so napoleon reads the first
    line of every attribute, constant and property docstring that way: `#: How a drop is
    sampled: ...` became a type called "How a drop is sampled". Types here come from the
    annotations, and a docstring is a description only. So this runs before napoleon and
    puts an empty comment first, the one line it reads for a type, which holds none.
    """
    if what in {"attribute", "data", "property"} and any(line.strip() for line in lines):
        lines[:0] = ["..", ""]


# -- Type aliases ----------------------------------------------------------------
#
# Autodoc writes an alias as "alias of" what it stands for. A discriminated union, as
# `scenet.core.FaceMark` is, stands for `Annotated[Annotated[FaceStroke, Tag("stroke")] |
# ..., Discriminator(...)]`: pydantic's machinery, which says nothing to a reader. Shown
# without its metadata, it reads `FaceStroke | FaceDisc | ...`, what a value may be.


def _without_metadata(annotation: object) -> object:
    """An annotation with every `Annotated` layer taken off, inside unions as well."""
    if typing.get_origin(annotation) is typing.Annotated:
        return _without_metadata(typing.get_args(annotation)[0])
    if typing.get_origin(annotation) in {typing.Union, types.UnionType}:
        return functools.reduce(
            operator.or_, (_without_metadata(arm) for arm in typing.get_args(annotation))
        )
    return annotation


def _readable_aliases() -> None:
    """Have autodoc write each alias it shows without pydantic's metadata."""
    from sphinx.ext.autodoc import _generate  # noqa: PLC0415 -- only once autodoc is loaded

    if getattr(_generate.restify, "_scenet", False):
        return
    shown = _generate.restify

    def restify(annotation: object, *args: object, **kwargs: object) -> str:
        return shown(_without_metadata(annotation), *args, **kwargs)  # type: ignore[arg-type]

    restify._scenet = True  # type: ignore[attr-defined]
    _generate.restify = restify  # type: ignore[assignment]


# -- Fields pydantic describes -----------------------------------------------------
#
# A model's field is listed only when something describes it: an `Attributes:` entry or a
# docstring under it. A field described with `Field(description=...)`, as the MCP server's
# results are for the model that reads them, is described the same way on its page. A
# docstring under a field is its description too (`use_attribute_docstrings`), and autodoc
# lists the field by it already, so it is not listed twice.


def _documented_attributes(cls: type) -> set[str]:
    """The fields of a class that have a docstring under them."""
    analyzer = ModuleAnalyzer.for_module(cls.__module__)
    analyzer.analyze()
    return {attribute for (owner, attribute) in analyzer.attr_docs if owner == cls.__qualname__}


def _field_descriptions(  # noqa: PLR0917 -- the signature Sphinx calls it with
    app: Sphinx, what: str, name: str, obj: object, options: object, lines: list[str]
) -> None:
    """Add an `Attributes:` entry for each field only `Field(description=...)` describes."""
    fields = getattr(obj, "model_fields", None)
    if what != "class" or not isinstance(fields, dict) or not isinstance(obj, type):
        return
    own = inspect.get_annotations(obj)
    documented = _documented_attributes(obj)
    described = "\n".join(lines)
    entries = [
        f"    {field}: {info.description}"
        for field, info in fields.items()
        if field in own
        and field not in documented
        and getattr(info, "description", None)
        and not re.search(rf"^\s+{field}( \(.*\))?:", described, re.MULTILINE)
    ]
    if entries:
        lines += ["", "Attributes:", *entries, ""]


def setup(app: Sphinx) -> None:
    # The site tests' two-page build of this configuration leaves autodoc out, and then
    # its events do not exist to listen to.
    if "sphinx.ext.autodoc" in app.extensions:
        # Napoleon and sphinx-autodoc-typehints listen at the default priority, 500, and
        # lower runs first: the docstring napoleon reads, and the bases before they become
        # text.
        app.connect("autodoc-process-docstring", _no_inline_types, priority=400)
        app.connect("autodoc-process-docstring", _field_descriptions, priority=400)
        _readable_aliases()
        app.connect("autodoc-process-bases", _public_bases, priority=400)
        app.connect("autodoc-skip-member", _api_members_only)
    # A comic script's fence names its language as the editor extension does, so that
    # `tests/test_doc_examples.py` knows to compile it (#317). Pygments has no lexer for it,
    # and it is shown as text, which is what a script is.
    app.add_lexer("scenet-script", TextLexer)
    app.connect("doctree-read", _heading_slugs_are_ids)
    app.connect("doctree-resolved", _playground_links_stay_in_their_version)
    app.connect("doctree-resolved", _source_links_follow_their_version)
    app.connect("doctree-resolved", _no_raw_markup)
    app.connect("build-finished", _every_public_name_is_documented)
