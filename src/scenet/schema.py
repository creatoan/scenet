"""The JSON Schema for Scenet documents, as people write them.

The pydantic models in :mod:`scenet.ir <scenet.ir>` are the language's real definition,
and `PanelIR.model_json_schema()` describes them faithfully. **It does not describe what
anybody types.** The YAML frontend accepts conveniences that
:func:`normalise <scenet.frontends.common.normalise>` and
:func:`merge <scenet.compose.merge>` remove before the models see the document:

- staging written as a sentence, `alice left_of bob`;
- script entries tagged by verb, `- say: {by: alice, text: ...}`;
- a setting that names a `place` instead of listing masses;
- in a scene, panels that state only what differs from what they inherit;
- `null` for a key, which is the key not written: in a scene, it leaves out what a panel
  would inherit (`settle`);
- the document's own keys, `scenet`, `$schema`, `meta` and `kind`, which the frontend takes
  off before the models read it (`split_head`), and a key starting with `x-` in any
  mapping, which it takes out (`without_extensions`).

Publishing the IR's schema made an editor flag every one of those as an error -- 21 of
the 22 gallery documents, on lines that compiled. So the published schema starts from
the IR's and puts each convenience back, next to a note of the code it mirrors. Every
field, enum and docstring still comes from the models; only the shape changes.

Example:
    >>> from scenet.schema import panel_schema
    >>> schema = panel_schema()
    >>> script = schema["properties"]["script"]
    >>> [branch.get("type") for branch in script["anyOf"]]
    ['array', 'null']
    >>> sorted(script["anyOf"][0]["items"]["anyOf"][0]["properties"])
    ['say']
"""

import inspect
import json
import re
from typing import Any

from scenet.assets.artwork import ArtworkContract
from scenet.assets.contract import (
    CORE_EXPRESSIONS,
    CORE_POSES,
    Landmark,
    PuppetSpec,
    default_library,
)
from scenet.compose import DIRECTION_KEY, ID_KEY, NOT_DEFAULTS, REMOVE_KEY
from scenet.core import PageCore, PanelCore
from scenet.identifiers import EXTENSION_PREFIX, GRAMMAR
from scenet.ir import (
    IDENTIFIER_PATTERN,
    PUPPET_KEYS,
    CaptionKind,
    PageLayout,
    PanelIR,
    Predicate,
)
from scenet.limits import LIMITS
from scenet.namespace import DOCUMENT_KEYS, KIND_KEY, AssetHead, DocumentHead, Kind
from scenet.places import Place

__all__ = [
    "artwork_schema",
    "core_schema",
    "page_core_schema",
    "panel_schema",
    "puppet_schema",
    "scene_schema",
]

DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: The definition every actor id and panel name refers to, so its pattern -- some twelve
#: thousand characters, the letters of Unicode spelled out -- is written once.
IDENTIFIER = "Identifier"

#: The pattern every extension key matches, in any mapping: `x-`, then anything.
EXTENSION_PATTERN = f"^{EXTENSION_PREFIX}"

#: What an extension key holds, in the schema: anything at all.
EXTENSION = {"description": "An extension: a key a tool writes, which Scenet ignores."}

#: Docstring sections written for the Python reference, which an editor showing a
#: description to someone writing YAML leaves out: everything from the first of them on.
PYTHON_SECTIONS = re.compile(
    r"^(?:Args|Returns|Raises|Example|Examples|See Also):\s*$", re.MULTILINE
)


#: A Sphinx role, `` :class:`CameraSpec <scenet.ir.CameraSpec>` `` or `` :attr:`x` ``: the
#: text it shows, or else its target's last name, is what a reader of YAML is shown.
ROLE = re.compile(r":[a-z]+:`~?(?:(?P<text>[^`<]+?)\s*<[^>]+>|(?P<target>[^`]+))`")

#: A blank line, which ends a paragraph.
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _plain(description: str) -> str:
    """A description as a reader of YAML sees it: no Sphinx role, and one line per paragraph.

    The text a role shows is kept as code. A docstring's own line breaks are not the
    author's, and an editor's hover would keep them, so each paragraph is joined into one.
    """
    text = ROLE.sub(
        lambda match: f"`{(match['text'] or match['target'].rsplit('.', 1)[-1]).strip()}`",
        description,
    )
    paragraphs = PARAGRAPH_BREAK.split(text.strip())
    return "\n\n".join(" ".join(paragraph.split()) for paragraph in paragraphs)


def _for_authors(node: object) -> None:
    """Make every description in a schema one an author can read.

    Each is cut at its first Python-only section, and its roles and line breaks are made
    plain (`_plain`).
    """
    if isinstance(node, dict):
        description = node.get("description")
        if isinstance(description, str):
            found = PYTHON_SECTIONS.search(description)
            if found:
                description = description[: found.start()]
            node["description"] = _plain(description)
        for value in node.values():
            _for_authors(value)
    elif isinstance(node, list):
        for value in node:
            _for_authors(value)


def _summaries(schema: dict[str, Any]) -> None:
    """Cut each definition's description, and the document's, to its first paragraph.

    A definition's description is its model's or its enumeration's docstring, written for
    the Python reference: past its summary it argues the design, tabulates the values and
    names Python's types. An editor shows a key's own description, which says what the key
    means to an author; a definition's summary says what kind of thing it holds.
    """
    nodes: list[dict[str, Any]] = [schema, *schema.get("$defs", {}).values()]
    for node in nodes:
        description = node.get("description")
        if isinstance(description, str):
            node["description"] = PARAGRAPH_BREAK.split(description.strip(), maxsplit=1)[0]


def panel_schema() -> dict[str, Any]:
    """The schema for a single-panel document.

    Returns:
        A JSON Schema (draft 2020-12) that accepts exactly the surface syntax a
        `.panel.yaml` file is written in.
    """
    schema = PanelIR.model_json_schema()
    definitions: dict[str, Any] = schema["$defs"]
    _with_head(schema, DocumentHead, definitions)
    _only_kinds(schema, Kind.PANEL)
    _one_identifier(schema, definitions)
    _accept_staging_sentences(definitions)
    _accept_verb_tagged_script(schema, definitions)
    _accept_named_places(definitions)
    _accept_one_font_file(definitions)
    _accept_cast_removal(schema)
    _puppet_or_figure(definitions)
    _core_vocabulary(definitions)
    _positive_size(definitions)
    _speaker_only_when_spoken(definitions)
    _accept_nulls(schema, definitions)
    _accept_cast_list(schema, definitions)
    _accept_extensions(schema)
    _summaries(schema)
    _for_authors(schema)
    schema["$schema"] = DIALECT
    schema["title"] = "Scenet panel"
    return schema


def core_schema() -> dict[str, Any]:
    """The schema for a Panel Core, the `*.core.json` a compile writes.

    A Core is read back as the models say, so this is the models' own schema, with the
    identifier's pattern -- some twelve thousand characters -- written once. What a schema
    cannot say, a balloon's runs spelling its lines, reading a Core back checks.

    Returns:
        A JSON Schema (draft 2020-12) for a Panel Core.

    Example:
        >>> from scenet.schema import core_schema
        >>> core_schema()["title"]
        'Scenet Panel Core'
    """
    return _core_schema(PanelCore, "Scenet Panel Core")


def page_core_schema() -> dict[str, Any]:
    """The schema for a Page Core: where every panel's frame is on a page.

    Returns:
        A JSON Schema (draft 2020-12) for a Page Core.

    Example:
        >>> from scenet.schema import page_core_schema
        >>> page_core_schema()["title"]
        'Scenet Page Core'
    """
    return _core_schema(PageCore, "Scenet Page Core")


def _core_schema(model: type[PanelCore] | type[PageCore], title: str) -> dict[str, Any]:
    """A Core model's schema, the way every published one is made."""
    schema = model.model_json_schema()
    _one_identifier(schema, schema.setdefault("$defs", {}))
    _summaries(schema)
    _for_authors(schema)
    schema["$schema"] = DIALECT
    schema["title"] = title
    return schema


def artwork_schema() -> dict[str, Any]:
    """The schema for an artwork contract, a `*.art.yaml` file beside its picture.

    A contract is written as the model reads it, with no conveniences to put back, so
    this is the model's own schema. What it cannot say -- every point on the picture,
    every region a simple polygon, the size the picture's own -- `scenet check` does.

    Returns:
        A JSON Schema (draft 2020-12) for an artwork contract.

    Example:
        >>> from scenet.schema import artwork_schema
        >>> sorted(artwork_schema()["properties"])
        ['$schema', 'figures', 'keep_out', 'meta', 'scenet', 'size']
    """
    schema = ArtworkContract.model_json_schema()
    _with_head(schema, AssetHead, schema.setdefault("$defs", {}))
    _accept_extensions(schema)
    _summaries(schema)
    _for_authors(schema)
    schema["$schema"] = DIALECT
    schema["title"] = "Scenet artwork contract"
    return schema


def puppet_schema() -> dict[str, Any]:
    """The schema for a puppet file, a `*.puppet.yaml` a cast member names by its path.

    A puppet is written as the model reads it, so this is the model's own schema, plus
    what of its validators a schema can state: every landmark is there, `head_top` is
    zero, and the default pose is declared. What it cannot say -- landmarks increasing
    downward, a skeleton that is a tree, every joint a part or a pose names declared --
    `scenet check` does, in the puppet file, on a document that casts it.

    Returns:
        A JSON Schema (draft 2020-12) for a puppet file.

    Example:
        >>> from scenet.schema import puppet_schema
        >>> puppet_schema()["required"]
        ['name', 'units_per_head', 'landmarks', 'joints', 'face', 'poses']
    """
    schema = PuppetSpec.model_json_schema()
    _with_head(schema, AssetHead, schema.setdefault("$defs", {}))
    _every_landmark(schema)
    _default_pose(schema)
    _accept_extensions(schema)
    _summaries(schema)
    _for_authors(schema)
    schema["$schema"] = DIALECT
    schema["title"] = "Scenet puppet"
    return schema


def scene_schema() -> dict[str, Any]:
    """The schema for a multi-panel document.

    Built from the panel schema rather than declared separately, so the two can never
    describe different languages. A scene allows the same keys as a panel -- there they
    act as defaults every panel inherits -- plus `panels`, whose members may
    additionally carry `over`.

    Returns:
        A JSON Schema (draft 2020-12) for a `.scene.yaml` file.
    """
    panel = panel_schema()
    definitions: dict[str, Any] = panel.pop("$defs")
    # The document's own keys are the scene's, never a panel's: `split_head`.
    head = {key: value for key, value in panel["properties"].items() if key in DOCUMENT_KEYS}
    properties = {
        key: _removable(_inheritable(value, definitions))
        for key, value in panel["properties"].items()
        if key not in DOCUMENT_KEYS
    }
    # A description says what one picture shows, and a script what one panel says, so a
    # panel may have one but the scene may not offer one to every panel:
    # `compose.NOT_DEFAULTS`.
    defaults = {key: value for key, value in properties.items() if key not in NOT_DEFAULTS}

    member = {key: value for key, value in panel.items() if key not in ("title", "$schema")}
    # A direction is the whole document's, never one panel's: `panel-direction` (#68).
    member["properties"] = {
        **{key: value for key, value in properties.items() if key != DIRECTION_KEY},
        "over": {
            "type": "string",
            "description": (
                "Name of a panel to inherit from. Only the differences need stating: "
                "mappings merge recursively and lists replace."
            ),
        },
    }

    # `page:` and `pages:` lay the panels out. They are not panel defaults, so they are
    # added whole rather than loosened like the inherited keys above.
    layout = PageLayout.model_json_schema(ref_template="#/$defs/{model}")
    _summaries(layout)
    definitions.update(layout.pop("$defs"))
    _accept_panel_names(definitions)
    _one_kind_of_tier(definitions)
    # Mirror `without_nulls`: what a page holds takes a null as a panel's keys do.
    _accept_nulls({"properties": layout["properties"]}, definitions)

    scene = {
        "$schema": DIALECT,
        "title": "Scenet scene",
        "$defs": definitions,
        "type": "object",
        "properties": {
            **head,
            **defaults,
            "page": layout["properties"]["page"],
            "pages": layout["properties"]["pages"],
            "panels": {
                "description": (
                    "The panels, in the order they are read: a mapping of each panel under "
                    "its name, an identifier, or a list of panels each with its `name`, "
                    "which no tool that sorts keys can reorder. Each may inherit from "
                    "another with `over`."
                ),
                # One node for both forms, rather than `anyOf`, so an editor reports a fault
                # inside a panel where it is: `additionalProperties` reads a mapping only,
                # and `items` a list only.
                "type": ["object", "array"],
                # The language's limit, for either form (#363).
                "maxProperties": LIMITS.panels_per_document,
                "maxItems": LIMITS.panels_per_document,
                # Mirror `_validate_panels`: a name is part of every file the panel is
                # written to, and what a page or an `over:` names it by.
                "propertyNames": {"$ref": f"#/$defs/{IDENTIFIER}"},
                "additionalProperties": member,
                "items": _entries(PANEL_ENTRY, _entry(member, ID_KEY), definitions),
            },
        },
        "additionalProperties": False,
        # Mirror `diagnose_source` and `parse_scene_document`: without `panels:` a document is
        # one panel, and there is nothing for a page to lay out.
        "dependentRequired": {"page": ["panels"], "pages": ["panels"]},
    }
    _only_kinds(scene, Kind.PANEL, Kind.SCENE)
    _kind_is_the_shape(scene)
    _accept_extensions(scene)
    _for_authors(scene)
    return scene


#: The definitions of an item of a list form, which `_inheritable` loosens as a
#: mapping's value although it is inside a list: lowered, it is one.
CAST_ENTRY = "CastEntry"
PANEL_ENTRY = "PanelEntry"

#: What each item's naming key says, as its card's first line.
_NAMING = {
    CAST_ENTRY: "The actor id of the cast member, in the list form of `cast`: an identifier.",
    PANEL_ENTRY: (
        "The panel's name, in the list form of `panels`: an identifier, which a page and an "
        "`over` name it by."
    ),
}


def _entry(value: dict[str, Any], naming: str) -> dict[str, Any]:
    """An item of a list form: the mapping form's value, naming itself first with `naming`."""
    entry = {key: item for key, item in value.items() if key != "title"}
    entry["type"] = "object"
    identifier = {"$ref": f"#/$defs/{IDENTIFIER}"}
    entry["properties"] = {naming: identifier, **value.get("properties", {})}
    entry["required"] = [naming, *value.get("required", ())]
    return entry


def _entries(name: str, entry: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Mirror `scenet.compose.lowered`: an item of a list form, naming itself by its `id`.

    Returns:
        A reference to it, the `items` of a node that takes either form.
    """
    for branch in entry.get("anyOf", [entry]):
        branch["properties"][ID_KEY] = {
            **branch["properties"][ID_KEY],
            "description": _NAMING[name],
        }
    definitions[name] = entry
    return {"$ref": f"#/$defs/{name}"}


def _accept_cast_list(schema: dict[str, Any], definitions: dict[str, Any]) -> None:
    """Mirror `lowered`: `cast: [{id: alice, ...}]` is `cast: {alice: {...}}`.

    After `_accept_nulls`: lowered, an item is a mapping's value, which takes a null on any
    key it does not require, as `settle` reads it. An item is a member, or one that says
    nothing but its `id` and `remove: true`, which leaves them out as `bob: null` does.
    """
    cast: dict[str, Any] = schema["properties"]["cast"]
    member = _entry(definitions["CastMember"], ID_KEY)
    member["properties"][REMOVE_KEY] = {
        "description": REMOVE_MEANS,
        "anyOf": [{"const": False}, {"type": "null"}],
    }
    removal = {
        "type": "object",
        "properties": {
            ID_KEY: {"$ref": f"#/$defs/{IDENTIFIER}"},
            REMOVE_KEY: {"description": REMOVE_MEANS, "const": True},
        },
        "required": [ID_KEY, REMOVE_KEY],
        "additionalProperties": False,
    }
    # The mapping's own node takes the list too, as `panels` does in a scene.
    mapping = next(branch for branch in cast["anyOf"] if branch.get("type") == "object")
    mapping["type"] = ["object", "array"]
    mapping["items"] = _entries(CAST_ENTRY, {"anyOf": [member, removal]}, definitions)
    # The limit on a cast, `maxProperties` for the mapping, is a list's too (#363).
    mapping["maxItems"] = LIMITS.actors_per_panel


#: What `remove` says, as its card's first line.
REMOVE_MEANS = (
    "In the list form of `cast`, `true` leaves the member out of a panel that would inherit "
    "them, as `null` does in the mapping form; the item then says nothing but its `id`."
)


def _with_head(schema: dict[str, Any], model: type[AssetHead], definitions: dict[str, Any]) -> None:
    """Mirror `split_head`: the document's own keys, which no model of its content has.

    Written first, as a document writes them.
    """
    head = model.model_json_schema(ref_template="#/$defs/{model}")
    definitions.update(head.pop("$defs", {}))
    schema["properties"] = {**head["properties"], **schema["properties"]}


def _only_kinds(schema: dict[str, Any], *kinds: Kind) -> None:
    """Mirror `kind_fault` and `_no_book`: the kinds a document checked with this schema is.

    Said under `not`, for the reason `_puppet_or_figure` gives: the key keeps the one
    description, and the definition of the kinds stays whole.
    """
    kind: dict[str, Any] = schema["properties"][KIND_KEY]
    kind["not"] = {"enum": [value.value for value in Kind if value not in kinds]}


def _kind_is_the_shape(scene: dict[str, Any]) -> None:
    """Mirror `kind_fault`: a document that says it is a scene has `panels:`, and a panel not.

    Under `allOf`, since a condition beside `type` is a condition on one shape, not a
    choice between shapes.
    """
    scene["allOf"] = [
        {
            "if": {"required": [KIND_KEY], "properties": {KIND_KEY: {"const": Kind.SCENE.value}}},
            "then": {"required": ["panels"]},
        },
        {
            "if": {"required": [KIND_KEY], "properties": {KIND_KEY: {"const": Kind.PANEL.value}}},
            "then": {"not": {"required": ["panels"]}},
        },
    ]


def _accept_extensions(schema: dict[str, Any]) -> None:
    """Mirror `without_extensions`: every mapping takes a key that starts with `x-`.

    Whatever it holds, since nothing reads it. A mapping whose keys the author chooses --
    the cast, the panels -- takes one too: no identifier starts with `x-`, so its key is
    never an actor's or a panel's, and its value is never read as one.
    """

    def visit(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        for value in list(node.values()):
            visit(value)
        kind = node.get("type")
        if kind == "object" or (isinstance(kind, list) and "object" in kind):
            node.setdefault("patternProperties", {})[EXTENSION_PATTERN] = EXTENSION
        names = node.get("propertyNames")
        extension = {"pattern": EXTENSION_PATTERN}
        if isinstance(names, dict) and extension not in names.get("anyOf", ()):
            node["propertyNames"] = {"anyOf": [names, extension]}

    visit(schema)


def _one_identifier(schema: dict[str, Any], definitions: dict[str, Any]) -> None:
    """Write the identifier's pattern once, as a definition the cast keys and `by` refer to.

    The models state it where it is used -- `KEYS_ARE_IDENTIFIERS`, `ActorId` -- so each
    model's own schema stands alone; the published one says it once.
    """
    reference = {"$ref": f"#/$defs/{IDENTIFIER}"}

    def visit(node: object) -> None:
        if isinstance(node, dict):
            if node.get("pattern") == IDENTIFIER_PATTERN:
                del node["pattern"]
                node.pop("type", None)
                node.update(reference)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    definitions[IDENTIFIER] = {
        "title": IDENTIFIER,
        "description": (
            f"An actor id or a panel name. {GRAMMAR}. The letters, digits and marks are "
            "Unicode's, spelled out by code point, so every reader of this schema agrees."
        ),
        "type": "string",
        "pattern": IDENTIFIER_PATTERN,
    }


def _one_kind_of_tier(definitions: dict[str, Any]) -> None:
    """Mirror `_check_one_kind` and `_check_slant`: what a tier holds, and when it leans.

    A tier holds panels or columns, never both and never neither. A slant leans the upright
    gutters between two panels or more, which a tier of columns does not have, and makes
    corners no inset can be set into. That a page's panels are the scene's, and that its
    margins leave room, compares one value with another, which a schema cannot.
    """
    tier: dict[str, Any] = definitions["Tier"]
    # Each a key written with an entry in it, said under `not` for the reason
    # `_puppet_or_figure` gives. Under `allOf`, since a `oneOf` beside `type` reads to an
    # editor as the shapes a tier may take, where this is one shape and a condition on it.
    tier["allOf"] = [
        {
            "oneOf": [
                {"required": [key], "not": {"properties": {key: {"maxItems": 0}}}}
                for key in ("panels", "columns")
            ]
        }
    ]
    inset = {
        "type": "object",
        "required": ["insets"],
        "properties": {"insets": {"minItems": 1}},
    }
    tier["if"] = {"required": ["slant"], "properties": {"slant": {"not": {"const": 0}}}}
    tier["then"] = {
        "properties": {
            "columns": {"maxItems": 0},
            "panels": {"minItems": 2, "items": {"not": inset}},
        }
    }


def _puppet_or_figure(definitions: dict[str, Any]) -> None:
    """Mirror `CastMember`'s validators and `_figures_stand_alone`: one of the two, alone.

    The model makes both `reference` and `figure` optional and requires one in a
    validator, which no schema is generated from. A member names one; never both as
    values -- `reference: null` beside a figure is how a panel overrides an inherited
    puppet, as `settle` removes it -- and nothing that poses or places a puppet beside a
    figure.
    """
    member: dict[str, Any] = definitions["CastMember"]
    # Written, and not as `null`, which `settle` takes away: a key is there only then. Not
    # "is a string", since `figure: 1984` names a figure too, and is text as written.
    written = {"not": {"type": "null"}}
    # The test for null is under `not`, not `properties`, which an editor would read as
    # the key's own description, empty here, in place of the one it has. It requires the
    # key itself, so in a scene, whose panels need not name either (`_inheritable` drops
    # the outer `required`), a member that leaves both out still passes.
    member["anyOf"] = [
        {"required": [key], "not": {"required": [key], "properties": {key: {"type": "null"}}}}
        for key in ("reference", "figure")
    ]
    member["not"] = {
        "required": ["reference", "figure"],
        "properties": {"reference": written, "figure": written},
    }
    member["if"] = {"required": ["figure"], "properties": {"figure": written}}
    member["then"] = {"properties": {key: {"type": "null"} for key in PUPPET_KEYS}}
    # `settle` removes a null before anything reads it, so a puppet's key written as null
    # -- over an inherited puppet that becomes a figure -- is accepted, as it compiles.
    properties: dict[str, Any] = member["properties"]
    for key in PUPPET_KEYS:
        properties[key] = _removable(properties[key])


def _every_landmark(schema: dict[str, Any]) -> None:
    """Mirror `check_landmarks_complete_and_ordered`: all nine landmarks, from a zero top.

    Any shot may crop at any of them, so one left out is a puppet some ordinary shot
    cannot frame. Listed in `Landmark`'s head-to-foot order, the order they are written
    in. `head_top` is the origin the others are measured down from, so it is zero.
    """
    landmarks: dict[str, Any] = schema["properties"]["landmarks"]
    landmarks["required"] = [landmark.value for landmark in Landmark]
    landmarks["properties"] = {
        Landmark.HEAD_TOP.value: {
            "const": 0,
            "description": "The origin every other landmark is measured down from.",
        }
    }


def _default_pose(schema: dict[str, Any]) -> None:
    """Mirror `check_default_pose`: every puppet declares the core vocabulary.

    The model gives `poses` and `expressions` defaults, so they are not required there;
    the validator makes them so, and every core pose and expression in them: a document
    that keeps to those is valid with any puppet.
    """
    schema["required"].append("poses")
    # A face with features to move declares the core expressions; one without, none.
    schema.setdefault("allOf", []).append(
        {
            "if": {"required": ["face"], "properties": {"face": {"required": ["features"]}}},
            "then": {"required": ["expressions"]},
        }
    )
    for key, core in (("poses", CORE_POSES), ("expressions", CORE_EXPRESSIONS)):
        declared: dict[str, Any] = schema["properties"][key]
        declared["required"] = list(core)
        declared["description"] = (
            f"{declared['description']} Every puppet declares the core {key}: "
            f"{', '.join(f'`{name}`' for name in core)}; it may declare more of its own."
        )


def _core_vocabulary(definitions: dict[str, Any]) -> None:
    """Mirror `scenet check` on a cast member's pose and expression, as far as a schema can.

    Each offers the core vocabulary, which every puppet declares, so an editor and a model
    are shown it; any other name stays allowed, since a supplied puppet may declare more,
    and the compiler checks it. A member whose `reference` names a shipped puppet takes
    that puppet's own names only.
    """
    member: dict[str, Any] = definitions["CastMember"]
    properties: dict[str, Any] = member["properties"]
    for key, core in (("pose", CORE_POSES), ("expression", CORE_EXPRESSIONS)):
        node = properties[key]
        branches = node.get("anyOf", [{k: v for k, v in node.items() if k not in _OUTER}])
        offered = {"enum": list(core), "description": f"A {key} every puppet declares."}
        outer = {k: v for k, v in node.items() if k in _OUTER}
        properties[key] = {**outer, "anyOf": [offered, *branches]}
    library = default_library()
    shipped = []
    for name in sorted(library.names()):
        puppet = library.get(name)
        own = {"pose": sorted(puppet.poses), "expression": sorted(puppet.expressions)}
        # Under `not`, as every condition on a key is: `then: {properties: ...}` would be
        # read as the key's own description by whatever lists the keys.
        shipped.append(
            {
                "if": {"required": ["reference"], "properties": {"reference": {"const": name}}},
                "then": {
                    "not": {
                        "anyOf": [
                            {
                                "required": [key],
                                "properties": {
                                    key: {"not": {"anyOf": [{"enum": names}, {"type": "null"}]}}
                                },
                            }
                            for key, names in own.items()
                        ]
                    }
                },
            }
        )
    member["allOf"] = [*member.get("allOf", ()), *shipped]


#: A node's keys that say what it is rather than what it takes.
_OUTER = ("title", "description", "default")


def _positive_size(definitions: dict[str, Any]) -> None:
    """Mirror `_check_positive_panel_spec`: a panel is wider and taller than nothing.

    Its other half, a margin that leaves room, compares two numbers, which a schema
    cannot; `scenet check` says both under `panel-geometry`.
    """
    size: dict[str, Any] = definitions["PanelSpec"]["properties"]["size"]
    for side in size["prefixItems"]:
        side["exclusiveMinimum"] = 0


def _speaker_only_when_spoken(definitions: dict[str, Any]) -> None:
    """Mirror `_check_speaker_is_meaningful`: only a quoted caption names who speaks.

    A caption of any other kind -- or of none, which is `locale` -- may write `by` only as
    `null`, which is a caption in a list, so a value the model reads as no speaker.
    """
    caption: dict[str, Any] = definitions["CaptionEvent"]
    quoted = [kind.value for kind in CaptionKind if kind.is_quoted]
    caption["if"] = {"required": ["kind"], "properties": {"kind": {"enum": quoted}}}
    caption["else"] = {"properties": {"by": {"type": "null"}}}


def _accept_nulls(schema: dict[str, Any], definitions: dict[str, Any]) -> None:
    """Mirror `settle`: in any document, a key whose value is `null` is a key not written.

    `settle` takes every such key away before anything reads the document -- in a single
    panel as in a scene, where it is how a panel leaves out what it inherits -- at any
    depth, in a mapping inside a list too, where it can only be a key not written. So the
    schema takes a `null` wherever that is, except for a key the mapping requires, which
    taken away leaves the mapping without it.
    """
    seen: set[str] = set()

    def loosen(node: dict[str, Any]) -> None:
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            if name not in seen:
                seen.add(name)
                loosen(definitions[name])
            return
        required = set(node.get("required", ()))
        properties: dict[str, Any] = node.get("properties", {})
        for key, value in properties.items():
            loosen(value)
            if key not in required:
                properties[key] = _removable(value)
        values = node.get("additionalProperties")
        if isinstance(values, dict):
            loosen(values)
            node["additionalProperties"] = _removable(values)
        items = node.get("items")
        if isinstance(items, dict):
            loosen(items)
        for item in node.get("prefixItems", ()):
            loosen(item)
        for combinator in ("anyOf", "oneOf", "allOf"):
            for branch in node.get(combinator, ()):
                loosen(branch)

    loosen(schema)


def _accept_cast_removal(schema: dict[str, Any]) -> None:
    """Mirror `settle`: `bob: null` leaves an inherited cast member out of the panel."""
    cast: dict[str, Any] = schema["properties"]["cast"]
    cast["additionalProperties"] = {
        "anyOf": [
            cast["additionalProperties"],
            {
                "type": "null",
                "description": (
                    "Leaves a cast member this panel would inherit out of it, and every "
                    "staging relation that names them."
                ),
            },
        ]
    }


def _accept_one_font_file(definitions: dict[str, Any]) -> None:
    """Mirror `normalise`: `font: path` stands for `font: {regular: path}`."""
    spec: dict[str, Any] = definitions["FontSpec"]
    mapping = {key: value for key, value in spec.items() if key not in ("title", "description")}
    definitions["FontSpec"] = {
        "title": spec["title"],
        "description": spec.get("description", ""),
        "anyOf": [
            {
                "type": "string",
                "description": (
                    "One font file, relative to the document, lettering every face: "
                    "`fonts/Comic.ttf` stands for `{regular: fonts/Comic.ttf}`."
                ),
            },
            mapping,
        ],
    }


def _accept_staging_sentences(definitions: dict[str, Any]) -> None:
    """Mirror `parse_relation`: a staging entry may be `subject predicate object`.

    The pattern is built from :class:`Predicate <scenet.ir.Predicate>`, so a predicate
    added to the language is accepted here without anyone remembering to. The mapping
    form stays valid, because the frontend passes a mapping through untouched.
    """
    relation: dict[str, Any] = definitions["Relation"]
    predicates = [member.value for member in Predicate]
    sentence = {
        "type": "string",
        "pattern": rf"^\s*\S+\s+({'|'.join(predicates)})\s+\S+\s*$",
        # Not a JSON Schema keyword. VS Code and monaco-yaml show it in place of the
        # raw regular expression, which tells nobody what went wrong.
        "patternErrorMessage": (
            f"Write 'subject predicate object', where the predicate is one of: "
            f"{', '.join(predicates)}"
        ),
        "description": (
            "A staging sentence, `subject predicate object` -- for example "
            "`alice left_of bob`. Predicates: " + ", ".join(predicates) + "."
        ),
    }
    mapping = {key: value for key, value in relation.items() if key not in ("title", "description")}
    definitions["Relation"] = {
        "title": relation["title"],
        "description": relation.get("description", ""),
        "anyOf": [sentence, mapping],
    }


def _accept_verb_tagged_script(schema: dict[str, Any], definitions: dict[str, Any]) -> None:
    """Mirror `normalise`: each script entry is a one-key mapping naming its verb.

    The frontend moves the key into the payload as `verb`, which is where the event
    models expect it. So here the reverse: the verb comes out of each event and becomes
    the key that wraps it. The verbs are read from the models' own `verb` constants.
    """
    script: dict[str, Any] = schema["properties"]["script"]
    branches: list[dict[str, Any]] = []
    # `oneOf`, because the IR picks the event by its verb (see `tag_by`). Here the verb
    # is the wrapping key instead, which separates the branches just as well.
    for branch in script["items"]["oneOf"]:
        name = branch["$ref"].rsplit("/", 1)[1]
        event: dict[str, Any] = definitions[name]
        verb = event["properties"].pop("verb")["const"]
        if "required" in event:
            event["required"] = [field for field in event["required"] if field != "verb"]
        branches.append(
            {
                "type": "object",
                "properties": {
                    verb: {"$ref": f"#/$defs/{name}", "description": VERB_MEANINGS[verb]}
                },
                "required": [verb],
                "additionalProperties": False,
            }
        )
    script["items"] = {"anyOf": branches}


#: What each script verb puts on the panel: the hover over `say:` in `- say: {...}`.
VERB_MEANINGS = {
    "say": "A line of dialogue, in a balloon whose tail points at the speaker.",
    "caption": "A caption: a box in which the panel speaks in its own voice, with no tail.",
    "sfx": "A sound effect: letters lettered into the picture, with no balloon.",
}


#: The setting keys that cannot be written together, mirroring `expand_place`: a place
#: *is* a mass list, and a picture is a backdrop of its own, which a horizon -- placing
#: masses -- has nothing to do with.
EXCLUSIVE_SETTING_KEYS = (
    ("place", "masses"),
    ("image", "place"),
    ("image", "masses"),
    ("image", "horizon"),
)


def _accept_named_places(definitions: dict[str, Any]) -> None:
    """Mirror `expand_place`: a setting names a place, lists masses or names an image.

    Each of those, and a horizon, may also be `null`, which takes away one a panel would
    otherwise inherit (`settle`) -- which is why two of them only clash when neither is.
    A fit needs an image; in a scene the image may be inherited, so `_inheritable` lets a
    panel give the fit alone.
    """
    definitions["Place"] = {
        "title": "Place",
        "description": inspect.cleandoc(Place.__doc__ or ""),
        "type": "string",
        "enum": [place.value for place in Place],
    }
    setting: dict[str, Any] = definitions["SettingSpec"]
    properties: dict[str, Any] = setting["properties"]
    properties["place"] = {
        "anyOf": [{"$ref": "#/$defs/Place"}, {"type": "null"}],
        "description": (
            "A named place, which stands for the list of masses it expands into. "
            "Write this, `masses` or `image`, never two of them."
        ),
    }
    for key in ("masses", "horizon"):
        properties[key] = _removable(properties[key])
    setting["not"] = {
        "anyOf": [
            {
                "required": list(pair),
                "properties": {key: {"not": {"type": "null"}} for key in pair},
            }
            for pair in EXCLUSIVE_SETTING_KEYS
        ]
    }
    # A fit needs an image beside it -- and `dependentRequired` would take `image: null`,
    # which `settle` removes, for one, and hold `fit: null`, which it removes too, to it.
    setting["dependentSchemas"] = {
        "fit": {
            "anyOf": [
                {"properties": {"fit": {"type": "null"}}},
                {"required": ["image"], "properties": {"image": {"not": {"type": "null"}}}},
            ]
        }
    }


def _accept_panel_names(definitions: dict[str, Any]) -> None:
    """Mirror `normalise_layout`: a panel in a tier or column may be written as its name."""
    for name in ("PanelPlacement", "StackedPanel"):
        placement: dict[str, Any] = definitions[name]
        mapping = {
            key: value for key, value in placement.items() if key not in ("title", "description")
        }
        definitions[name] = {
            "title": placement["title"],
            "description": placement.get("description", ""),
            "anyOf": [
                {
                    "type": ["string", "number", "boolean"],
                    "description": "A panel's name, which stands for `{use: name}`.",
                },
                mapping,
            ],
        }


def _inheritable(node: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Loosen a scene property, which may be stated only in part.

    :func:`merge <scenet.compose.merge>` deep-merges mappings and replaces lists. So
    anything reached through mapping keys may leave fields to be inherited -- an
    override can change one actor's pose without restating its `reference` -- while
    anything inside a list must still be whole. That is why `items` is never descended.
    """
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[1]
        partial = _partial_definition(name, definitions)
        return node if partial == name else {**node, "$ref": f"#/$defs/{partial}"}

    # A key one field needs beside it may be inherited as much as a required one.
    loosened = {
        key: value
        for key, value in node.items()
        if key not in ("required", "dependentRequired", "dependentSchemas")
    }
    if isinstance(node.get("additionalProperties"), dict):
        loosened["additionalProperties"] = _inheritable(node["additionalProperties"], definitions)
    items = node.get("items")
    entry = items.get("$ref", "").rsplit("/", 1)[-1] if isinstance(items, dict) else ""
    if entry in (CAST_ENTRY, PANEL_ENTRY):
        # An item of a list form is a mapping's value once lowered, so it may be stated in
        # part as one may -- but for the name it gives itself.
        partial = _partial_definition(entry, definitions)
        definitions[partial]["required"] = [ID_KEY]
        loosened["items"] = {"$ref": f"#/$defs/{partial}"}
    if "properties" in node:
        loosened["properties"] = {
            key: _removable(_inheritable(value, definitions))
            for key, value in node["properties"].items()
        }
    for combinator in ("anyOf", "oneOf", "allOf"):
        if combinator in node:
            loosened[combinator] = [
                _inheritable(branch, definitions) for branch in node[combinator]
            ]
    return loosened


def _removable(node: dict[str, Any]) -> dict[str, Any]:
    """Mirror `settle`: in a scene, a key reached through mappings may be `null`.

    A null removes what a panel would otherwise inherit -- `camera: null` on a panel of
    figures over one that has a camera, `weather: null` to clear the sky again -- at any
    depth, never inside a list. A key that already takes a null is left as it is.
    """
    if node.get("type") == "null" or any(
        branch.get("type") == "null" for branch in node.get("anyOf", [])
    ):
        return node
    outer = {key: node[key] for key in ("title", "description", "default") if key in node}
    inner = {key: value for key, value in node.items() if key not in outer}
    return {**outer, "anyOf": [inner, {"type": "null"}]}


def _partial_definition(name: str, definitions: dict[str, Any]) -> str:
    """The name of a copy of `name` with nothing required, adding it if it differs."""
    definition: dict[str, Any] = definitions[name]
    loosened = _inheritable(definition, definitions)
    if loosened == definition:
        return name
    partial = f"Partial{name}"
    description = definition.get("description", "")
    loosened["description"] = (
        f"{description}\n\n" if description else ""
    ) + "In a scene any of these may be inherited, so none is required here."
    definitions[partial] = loosened
    return partial


# ---------------------------------------------------------------- the strict schema

#: The JSON Schema keywords a strict schema is written with: what the structured-output
#: modes of the providers recorded in `docs/explanation/prior_art.md` all take. Every other
#: keyword says something those modes refuse or ignore, and the frontend checks it.
STRICT_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "description",
        "enum",
        "items",
        "properties",
        "required",
        "type",
    }
)

#: Keys of a document that a strict schema leaves out: `meta` holds whatever a tool keeps,
#: which no closed object can say.
_NOT_STRICT = ("meta",)


def strict_schema(*, scene: bool = False) -> dict[str, Any]:
    """The schema a structured-output mode can decode against: the common subset.

    The same language as :func:`panel_schema` and :func:`scene_schema`, in the shape
    constrained decoding accepts: `cast` and `panels` as lists, each item with its `id`; a
    staging relation, a font, a panel on a page in their mapping forms only; every key of
    every object present, `null` where nothing is meant, and no other key; text as a string.
    No condition, pattern, bound or default: those the frontend checks, as it always does.

    Args:
        scene: The scene's schema, rather than a single panel's.

    Returns:
        A JSON Schema using only :data:`STRICT_KEYWORDS`.

    Example:
        >>> from scenet.schema import STRICT_KEYWORDS, strict_schema
        >>> schema = strict_schema()
        >>> schema["additionalProperties"], "cast" in schema["required"]
        (False, True)
    """
    loose = _whole_panels(scene=scene)
    return _Strict(loose.get("$defs", {})).schema(loose)


class _Strict:
    """The transformation from the published schema to the strict one, definition by definition."""

    def __init__(self, definitions: dict[str, Any]) -> None:
        self.definitions = definitions
        self.made: dict[str, Any] = {}

    def schema(self, loose: dict[str, Any]) -> dict[str, Any]:
        """The whole strict schema, with only the definitions it still names."""
        root = self.node({key: value for key, value in loose.items() if key != "$defs"})
        # A definition no strict node names any more -- a sentence's, say -- goes.
        named = json.dumps(root) + json.dumps(self.made)
        used = {name: value for name, value in self.made.items() if f'/{name}"' in named}
        return {"$defs": dict(sorted(used.items())), **root} if used else root

    def resolved(self, node: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in node:
            node = self.definitions[node["$ref"].rsplit("/", 1)[1]]
        return node

    def kinds(self, node: dict[str, Any]) -> set[str]:
        """The JSON types a node takes, `enum` for a closed set of values."""
        node = self.resolved(node)
        if "anyOf" in node:
            return {kind for branch in node["anyOf"] for kind in self.kinds(branch)}
        written = node.get("type")
        if isinstance(written, list):
            return set(written)
        if isinstance(written, str):
            return {written}
        if "enum" in node:
            return {"enum"}
        return {"object"} if "properties" in node else set()

    def node(self, node: dict[str, Any]) -> dict[str, Any]:
        """One node, strict."""
        if "$ref" in node:
            return self.reference(node)
        described = {"description": node["description"]} if "description" in node else {}
        if "properties" in node:
            # An object's `anyOf` -- a cast member's `reference` or `figure` -- is a condition
            # on its keys, not another shape: the frontend checks it.
            return {**described, **self.typed(node, "object")}
        if "anyOf" in node or "oneOf" in node:
            return self.union(node, described)
        written = node.get("type")
        if isinstance(written, list):
            return self.types(node, written, described)
        return {**described, **self.typed(node, written)}

    def reference(self, node: dict[str, Any]) -> dict[str, Any]:
        name = node["$ref"].rsplit("/", 1)[1]
        if name not in self.made:
            self.made[name] = {}
            self.made[name] = self.node(self.definitions[name])
        target = {"$ref": f"#/$defs/{name}"}
        return (
            {"description": node["description"], "anyOf": [target]}
            if "description" in node
            else target
        )

    def union(self, node: dict[str, Any], described: dict[str, Any]) -> dict[str, Any]:
        branches = [*node.get("anyOf", ()), *node.get("oneOf", ())]
        # A shorthand that stands for a mapping -- a sentence, a font's one file, a panel's
        # name -- is left out: the mapping says the same.
        if any("object" in self.kinds(branch) for branch in branches):
            keep = {"object", "null", "array", "boolean", "enum"}
            branches = [b for b in branches if self.kinds(b) & keep or not self.kinds(b)]
        flat: list[dict[str, Any]] = []
        for branch in branches:
            made = self.node(branch)
            if not made:
                continue  # A condition, `{required: [...]}`, which says no shape.
            inner = made.get("anyOf") if set(made) <= {"anyOf", "description"} else None
            for item in inner if inner is not None else [made]:
                if item not in flat:
                    flat.append(item)
        if len(flat) == 1 and not described and set(flat[0]) <= {"$ref"}:
            return flat[0]
        return {**described, "anyOf": flat}

    def types(
        self, node: dict[str, Any], written: list[str], described: dict[str, Any]
    ) -> dict[str, Any]:
        """A node of several types, as one type or a union of them."""
        types = [kind for kind in written if kind != "null"]
        if {"object", "array"} <= set(types):
            types = ["array"]  # `cast` and `panels`: the list form only.
        elif "string" in types:
            types = ["string"]  # Text: a string, never a number or a flag.
        inner = {key: value for key, value in node.items() if key not in ("type", "description")}
        made = [self.typed(inner, kind) for kind in types]
        if "null" in written:
            made.append({"type": "null"})
        return {**described, **made[0]} if len(made) == 1 else {**described, "anyOf": made}

    def typed(self, node: dict[str, Any], written: object) -> dict[str, Any]:
        """A node of one type, with only the keywords the strict subset has."""
        result: dict[str, Any] = {}
        if "const" in node:
            result["enum"] = [node["const"]]
        if "enum" in node:
            result["enum"] = list(node["enum"])
        if written is not None:
            result["type"] = written
        if written == "array" or "items" in node or "prefixItems" in node:
            result["type"] = "array"
            result["items"] = self.items(node)
        if written == "object" or "properties" in node:
            result.update(self.closed(node))
        return result

    def items(self, node: dict[str, Any]) -> dict[str, Any]:
        prefix = node.get("prefixItems")
        if isinstance(prefix, list):
            made = [self.node(item) for item in prefix]
            unique = [item for index, item in enumerate(made) if item not in made[:index]]
            return unique[0] if len(unique) == 1 else {"anyOf": unique}
        items = node.get("items")
        return self.node(items) if isinstance(items, dict) else {}

    def closed(self, node: dict[str, Any]) -> dict[str, Any]:
        """An object: every key required, a key not required taking `null`, no other key."""
        properties = {
            key: value
            for key, value in node.get("properties", {}).items()
            if key not in _NOT_STRICT
        }
        required = set(node.get("required", ()))
        return {
            "type": "object",
            "properties": {
                key: self.node(value) if key in required else _nullable(self.node(value))
                for key, value in properties.items()
            },
            "required": list(properties),
            "additionalProperties": False,
        }


def _whole_panels(*, scene: bool) -> dict[str, Any]:
    """The loose schema a strict one is made from: one in which nothing is inherited.

    In a scene, `null` on a panel's key takes away what the panel inherits; a strict
    document writes every key, so it could not inherit and say nothing too. So a strict
    scene writes each panel whole -- no defaults beside `panels:`, no `over` -- and its
    `direction` once, at its top; a `null` is then always a key not written. Nor is a cast
    member removed from anything: `remove` is not written.
    """
    panel = panel_schema()
    definitions: dict[str, Any] = panel.pop("$defs")
    member = definitions[CAST_ENTRY]["anyOf"][0]
    definitions[CAST_ENTRY] = {
        **member,
        "properties": {
            key: value for key, value in member["properties"].items() if key != REMOVE_KEY
        },
    }
    if not scene:
        return {**panel, "$defs": definitions}
    loose = scene_schema()
    for name, definition in loose["$defs"].items():
        definitions.setdefault(name, definition)
    body = {
        key: value
        for key, value in panel["properties"].items()
        if key not in DOCUMENT_KEYS and key != DIRECTION_KEY
    }
    definitions[PANEL_ENTRY] = {
        "type": "object",
        "description": "One panel, written whole, under its `id`.",
        "properties": {ID_KEY: {"$ref": f"#/$defs/{IDENTIFIER}"}, **body},
        "required": [ID_KEY],
        "additionalProperties": False,
    }
    top = loose["properties"]
    return {
        "type": "object",
        "title": loose["title"],
        "properties": {
            **{key: value for key, value in top.items() if key in DOCUMENT_KEYS},
            DIRECTION_KEY: panel["properties"][DIRECTION_KEY],
            "panels": {
                "type": "array",
                "description": "The panels, in the order they are read, each written whole.",
                "items": {"$ref": f"#/$defs/{PANEL_ENTRY}"},
            },
            "page": top["page"],
            "pages": top["pages"],
        },
        "required": ["panels"],
        "additionalProperties": False,
        "$defs": definitions,
    }


def _nullable(node: dict[str, Any]) -> dict[str, Any]:
    """A strict node that also takes `null`, which the frontend reads as a key not written."""
    branches = node.get("anyOf")
    if isinstance(branches, list) and {"type": "null"} in branches:
        return node
    if node.get("type") == "null":
        return node
    described = {key: value for key, value in node.items() if key == "description"}
    inner = {key: value for key, value in node.items() if key != "description"}
    if set(inner) == {"anyOf"}:
        return {**described, "anyOf": [*inner["anyOf"], {"type": "null"}]}
    return {**described, "anyOf": [inner, {"type": "null"}]}
