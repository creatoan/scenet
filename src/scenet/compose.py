"""Sparse override between panels.

Borrowed from OpenUSD's composition arcs, and specifically from `over`: a panel names
a parent and states only what differs from it.

This matters more for comics than it might look. Consecutive panels in a scene are
mostly identical -- the same cast, the same staging, the same camera -- with one thing
changed. Restating all of it per panel is both tedious and a place for inconsistencies
to creep in, which is exactly the continuity error comics readers notice.

.. code-block:: yaml

    panels:
      p1:
        camera: {shot: medium_shot}
        cast:
          alice: {reference: alice, at: left_third}
      p2:
        over: p1                      # everything from p1...
        camera: {shot: close_up}      # ...except the framing

Taking something away is JSON Merge Patch's rule (RFC 7396): "If the value is null,
remove". `cast: {bob: null}` leaves Bob out of a panel that would otherwise inherit him.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from functools import cache
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel

from scenet.errors import CompositionError
from scenet.ir import (
    CaptionEvent,
    CastMember,
    PanelIR,
    Predicate,
    SayEvent,
    SettingSpec,
    SfxEvent,
)

__all__ = [
    "ID_KEY",
    "KEYED",
    "OVER_KEY",
    "PANELS_SHAPE",
    "REMOVE_KEY",
    "Dropped",
    "FormFault",
    "Lowered",
    "as_lists",
    "looks_toward",
    "lowered",
    "merge",
    "names",
    "on_their_side",
    "relation_text",
    "resolve_beneath",
    "resolve_overrides",
    "settle",
    "without_nulls",
]

# The key naming a panel's parent. Spelled as USD spells it, since the semantics are
# deliberately the same.
OVER_KEY = "over"

#: The one key a panel does not take from the panel it is over. A description says what
#: one picture shows, and a panel drawn over another is a different picture: inherited,
#: its parent's words would be wrong to exactly the reader who cannot see that they are.
DESCRIPTION_KEY = "description"

#: Why a description written where every panel would inherit it -- beside `panels:`, or in
#: a comic script's front matter -- is refused. The rule is `unknown-key`, whose help says
#: to check the spelling, so the message carries the fix.
NOT_A_DEFAULT = (
    "'description' describes one panel, so it is not a default every panel inherits; "
    "write it on the panel it describes"
)

#: The key a panel's lines are written under.
SCRIPT_KEY = "script"

#: Why a script written where every panel would inherit it -- beside `panels:` -- is
#: refused: every panel would say the same lines, and a panel that should say none would
#: have to take them away one by one.
SCRIPT_NOT_A_DEFAULT = (
    "'script' is what one panel says, so it is not a default every panel inherits: write it "
    "on the panel that says it, or on one the others are drawn `over`"
)

#: Each key a scene may not offer every panel as a default, and why, which is the message
#: refusing it. The rule is `unknown-key`, whose help says to check the spelling.
NOT_DEFAULTS = {DESCRIPTION_KEY: NOT_A_DEFAULT, SCRIPT_KEY: SCRIPT_NOT_A_DEFAULT}


#: The key a whole document's reading direction is written under. Every panel takes
#: it from the document -- beside `panels:`, or in a comic script's front matter -- and
#: none writes its own.
DIRECTION_KEY = "direction"


def own_direction(where: str) -> str:
    """Why a panel's own `direction` is refused, and where to write it instead.

    Example:
        >>> from scenet.compose import own_direction
        >>> own_direction("beside `panels:`").endswith("once, beside `panels:`")
        True
    """
    return (
        "'direction' says which way the whole comic is read, so a panel cannot have one of "
        "its own: a page read one way holding a panel read the other has no order a reader "
        f"could follow. Write it once, {where}"
    )


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge `override` onto `base`, with `override` winning.

    Mappings merge recursively so that changing one actor's pose leaves the rest of
    the cast alone. Lists replace wholesale rather than concatenating: `script` and
    `staging` are ordered wholes, and appending to an inherited script would make it
    impossible to write a panel where somebody says less than in the panel before.

    A `null` is kept, not applied: it has to remove the key from whatever the document
    is merged over next as well -- a scene's defaults come last -- so it is `settle`,
    once the document is whole, that takes it out.
    """
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = merge(existing, value)
        else:
            result[key] = value
    return result


def resolve_overrides(panels: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Resolve every panel's `over` chain into a self-contained document.

    Panels are resolved lazily with memoisation, so a chain is walked once however
    many panels hang off it, and declaration order does not matter -- a panel may
    inherit from one declared later.
    """
    resolved: dict[str, dict[str, Any]] = {}

    def resolve(name: str, seen: tuple[str, ...]) -> dict[str, Any]:
        if name in resolved:
            return resolved[name]

        document = dict(panels[name])
        parent_name = document.pop(OVER_KEY, None)
        if parent_name is None:
            resolved[name] = document
            return document

        # Every fault is reported at the `over:` that names the wrong thing, since that
        # is the line to change.
        at = ("panels", name, OVER_KEY)
        if not isinstance(parent_name, str):
            raise CompositionError(
                f"panel '{name}': 'over' must name a single panel, "
                f"found {type(parent_name).__name__}",
                loc=at,
            )
        if parent_name not in panels:
            raise CompositionError(
                f"panel '{name}' is over '{parent_name}', which does not exist; "
                f"declared panels are {sorted(panels)}",
                loc=at,
            )
        if parent_name in seen or parent_name == name:
            chain = " -> ".join([*seen, name, parent_name])
            raise CompositionError(f"'over' chain is cyclic: {chain}", loc=at)
        inherited = {
            key: value
            for key, value in resolve(parent_name, (*seen, name)).items()
            if key != DESCRIPTION_KEY
        }
        composed = merge(inherited, document)
        resolved[name] = composed
        return composed

    # Sorted so that an error in a shared ancestor is reported against the same panel
    # on every run.
    for name in sorted(panels):
        resolve(name, ())
    return {name: resolved[name] for name in panels}


@dataclass(frozen=True)
class Dropped:
    """A staging relation that named somebody a panel left out.

    Attributes:
        index: Where it stood in the panel's staging, as inherited.
        relation: The relation, as written.
        actor: Who it named that is not in the panel.
    """

    index: int
    relation: object
    actor: str


def names(relation: object, actor: str) -> bool:
    """Whether a staging relation, as written, names an actor as subject or object."""
    if isinstance(relation, str):
        words = relation.split()
        return bool(words) and actor in (words[0], words[-1])
    if isinstance(relation, dict):
        return actor in (relation.get("subject"), relation.get("object"))
    return False


def relation_text(relation: object) -> str:
    """A staging relation as a sentence, however it was written."""
    if isinstance(relation, dict):
        return " ".join(str(relation.get(key, "")) for key in ("subject", "predicate", "object"))
    return str(relation)


def resolve_beneath(panels: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every panel's `over` chain resolved as if no `null` had been written in it.

    What each removal takes away: whoever a panel leaves out, as they stood in the panels
    it is over, so a line they speak from off panel can end on their side (`settle`).
    """
    return resolve_overrides(
        {
            name: _without_nulls(document) if isinstance(document, dict) else document
            for name, document in panels.items()
        }
    )


def looks_toward(relation: object, actor: str, leaving: Collection[str]) -> bool:
    """Whether a relation is somebody still drawn looking at an actor who is not."""
    if isinstance(relation, str):
        words = relation.split()
        if len(words) != 3:
            return False
        subject, predicate, target = words
    elif isinstance(relation, dict):
        subject, predicate, target = (
            relation.get(key) for key in ("subject", "predicate", "object")
        )
    else:
        return False
    return predicate == Predicate.LOOKING_AT.value and target == actor and subject not in leaving


def on_their_side(event: object, cast: dict[str, Any]) -> object:
    """An off-panel line with no side named, given the side its speaker was written at."""
    if not isinstance(event, dict):
        return event
    say = event.get("say")
    if not isinstance(say, dict) or say.get("off_panel") is not True:
        return event
    by = say.get("by")
    member = cast.get(by) if isinstance(by, str) else None
    at = str(member.get("at", "")) if isinstance(member, dict) else ""
    side = next((value for value in ("left", "right") if at.startswith(value)), None)
    return event if side is None else {**event, "say": {**say, "off_panel": side}}


def settle(
    document: dict[str, Any], *, beneath: dict[str, Any] | None = None
) -> tuple[dict[str, Any], tuple[Dropped, ...]]:
    """Apply the removals a complete document's `null` values ask for.

    Every key whose value is `null` goes, in mappings at any depth -- not inside lists,
    which Merge Patch treats as values. A cast member who goes takes with them every
    staging relation that names them, since none can hold in a panel they are not in.

    All but one kind, while they are heard from off panel in it, as a comic script's
    `CAROL (OP)` has it: `bob looking_at carol` still holds, since Bob may look toward
    the side of the frame she is heard from. That side is the one she was written to
    stand on, `at: left_third` being the left, unless her line names one.

    Args:
        document: The panel, merged whole.
        beneath: The same panel with no removal written (`resolve_beneath`): where
            whoever it leaves out stood. Without it, their lines are left as written.

    Returns:
        The document, and the relations dropped, in the order they were written.

    Example:
        >>> from scenet.compose import settle
        >>> settled, dropped = settle({"cast": {"a": {}, "b": None}, "staging": ["a left_of b"]})
        >>> settled, [item.actor for item in dropped]
        ({'cast': {'a': {}}, 'staging': []}, ['b'])
    """
    cast = document.get("cast")
    leaving = (
        [actor for actor, member in cast.items() if member is None]
        if isinstance(cast, dict)
        else []
    )
    settled = _without_nulls(document)
    if not leaving:
        return settled, ()
    script = settled.get("script")
    heard = _heard(script, leaving)
    stood = beneath.get("cast") if beneath is not None else None
    if heard and isinstance(script, list) and isinstance(stood, dict):
        theirs = {actor: stood[actor] for actor in heard if actor in stood}
        settled["script"] = [on_their_side(event, theirs) for event in script]
    staging = settled.get("staging")
    if not isinstance(staging, list):
        return settled, ()
    kept: list[object] = []
    dropped: list[Dropped] = []
    for index, relation in enumerate(staging):
        actor = next((actor for actor in leaving if names(relation, actor)), None)
        if actor is None or (actor in heard and looks_toward(relation, actor, leaving)):
            kept.append(relation)
        else:
            dropped.append(Dropped(index, relation, actor))
    return {**settled, "staging": kept}, tuple(dropped)


def _heard(script: object, leaving: Collection[str]) -> set[str]:
    """Who, of those a panel leaves out, speaks in it from off panel."""
    if not isinstance(script, list):
        return set()
    says = (event.get("say") for event in script if isinstance(event, dict))
    return {
        say["by"]
        for say in says
        if isinstance(say, dict)
        and say.get("by") in leaving
        and say.get("off_panel") not in (None, False)
    }


@dataclass(frozen=True, slots=True)
class _Each:
    """A mapping whose keys the author chooses -- the cast -- each value read as `model`."""

    model: "Reader"


@dataclass(frozen=True, slots=True)
class _Items:
    """A list whose items are mappings, each read as `model`: a script, staging, masses."""

    model: "Reader"


@dataclass(frozen=True, slots=True)
class _Verbs:
    """A script entry as written: its verb, `say`, `caption` or `sfx`, over the event."""


#: What reads a mapping in a document: the model whose fields its keys are, `_Each`,
#: `_Items` for a list of mappings, `_Verbs` for a script entry, or `None` for a mapping
#: the language does not know, under a key it does not know.
Reader = type[BaseModel] | _Each | _Items | _Verbs | None

#: What each verb of a script entry holds.
_VERBS: dict[str, type[BaseModel]] = {"say": SayEvent, "caption": CaptionEvent, "sfx": SfxEvent}

#: Keys a mapping is written with that its model has no field for, because the frontend
#: rewrites them before the model reads it: a setting's `place`, which `expand_place`
#: turns into masses.
_SURFACE_KEYS: dict[type[BaseModel], tuple[str, ...]] = {SettingSpec: ("place",)}


def _reader(annotation: object) -> Reader:
    """What reads a field's value, where that value is a mapping."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _reader(get_args(annotation)[0])
    if origin is Union or origin is UnionType:
        return next(
            (found for found in map(_reader, get_args(annotation)) if found is not None), None
        )
    if origin is dict:
        return _Each(_reader(get_args(annotation)[1]))
    if origin is tuple or origin is list:
        inner = _reader(get_args(annotation)[0])
        return _Items(inner) if inner is not None else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


@cache
def _keys(model: type[BaseModel]) -> dict[str, Reader]:
    """Every key a mapping read as `model` may be written with, and what reads its value."""
    keys: dict[str, Reader] = dict.fromkeys(_SURFACE_KEYS.get(model, ()))
    for name, info in model.model_fields.items():
        keys[info.alias or name] = _reader(info.annotation)
    if model is PanelIR:
        # Written by its verb, `{say: {...}}`, which the frontend turns into the event.
        keys[SCRIPT_KEY] = _Items(_Verbs())
    return keys


def _keys_of(reader: Reader) -> dict[str, Reader] | None:
    """The keys a mapping read by `reader` may be written with, `None` for any key."""
    if isinstance(reader, _Verbs):
        return dict(_VERBS)
    return _keys(reader) if isinstance(reader, type) else None


def without_nulls(mapping: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    """A mapping read as `model` with every key whose value is `null` taken away.

    What `settle` does for a panel, for what a scene's pages are read as.

    Example:
        >>> from scenet.compose import without_nulls
        >>> from scenet.ir import PageLayout
        >>> without_nulls({"pages": [{"tiers": [{"height": None, "panels": ["a"]}]}]}, PageLayout)
        {'pages': [{'tiers': [{'panels': ['a']}]}]}
    """
    return _without_nulls(mapping, model)


def _without_nulls(mapping: dict[str, Any], reader: Reader = PanelIR) -> dict[str, Any]:
    """The mapping with every key whose value is `null` taken away, at any depth.

    In a mapping inside a list too -- a script entry, a staging relation, a mass, a tier --
    where nothing is inherited for a `null` to take away, so it can only be a key not
    written: what a document that writes every key, as a strict schema has a model do,
    writes for the keys it leaves out. Except a key the language does not have there:
    `colour: null` is a typo like `colour: red`, so it is kept, for validation to report as
    the unknown key it is -- which is what the schema says of it.
    """
    keys = _keys_of(reader)
    kept: dict[str, Any] = {}
    for key, value in mapping.items():
        if keys is not None and key not in keys:
            kept[key] = value
            continue
        if value is None:
            continue
        inner = (
            keys[key] if keys is not None else reader.model if isinstance(reader, _Each) else None
        )
        if isinstance(value, dict):
            kept[key] = _without_nulls(value, inner)
        elif isinstance(value, list) and isinstance(inner, _Items):
            kept[key] = [
                _without_nulls(item, inner.model) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            kept[key] = value
    return kept


# ---------------------------------------------------------------- keyed collections

#: The collections an author names the members of: written as a mapping, each member under
#: its key, or as a list whose items each say their `id`. Their order is part of the
#: document -- the panels are read in it, and the first of the cast is the one the camera
#: frames -- and a tool that sorts keys reorders a mapping without a word; a list it cannot.
KEYED: tuple[str, ...] = ("panels", "cast")

#: The key an item of a list form names itself by, which the mapping form writes as its key.
ID_KEY = "id"

#: The key that leaves a cast member out in the list form, as `bob: null` does in the
#: mapping form: `{id: bob, remove: true}`. A verb, as `use`, `read` and `prefer` are.
REMOVE_KEY = "remove"

#: What `panels:` must be, as the finding refusing anything else says.
PANELS_SHAPE = "'panels' must be a mapping of name to panel, or a list of panels each with its `id`"

#: The keys an item of each collection may say, which name no entry of the mapping form.
_FIELDS: dict[str, frozenset[str]] = {
    "panels": frozenset({*PanelIR.model_fields, OVER_KEY}),
    "cast": frozenset({*CastMember.model_fields, REMOVE_KEY}),
}

#: What each collection holds, for a message.
_WHAT = {"panels": "panel", "cast": "cast member"}

#: A path in a document, in pydantic's `loc` form.
Loc = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class FormFault:
    """A list form written wrong, where it is written.

    Attributes:
        message: What is wrong, and what to write.
        rule: The catalogue rule it breaks.
        loc: Where, as the document is written: an item's index, then its key.
    """

    message: str
    rule: str
    loc: Loc


@dataclass(frozen=True, slots=True)
class Lowered:
    """A document with every keyed collection as the mapping form, and where each was written.

    Attributes:
        document: The document, each list form as the mapping it stands for.
        faults: Each item of a list form written wrong, in the order written. An item at
            fault is left out of `document`, so the rest can still be checked.
        written: Where each member of a list form was written, by its path once lowered:
            `("cast", "alice")` was `("cast", 2)`.
    """

    document: dict[str, Any]
    faults: tuple[FormFault, ...] = ()
    written: dict[Loc, Loc] = field(default_factory=dict[Loc, Loc])

    def where(self, path: Loc) -> Loc:
        """A path into the lowered document, as the document is written.

        A member's key, `[key]`, is the `id` its item writes.

        Example:
            >>> from scenet.compose import lowered
            >>> found = lowered({"cast": [{"id": "a"}, {"id": "b", "at": "x"}]})
            >>> found.where(("cast", "b", "at")), found.where(("cast", "b", "[key]"))
            (('cast', 1, 'at'), ('cast', 1, 'id'))
        """
        for length in range(len(path), 0, -1):
            prefix = path[:length]
            if prefix in self.written:
                rest = path[length:]
                if rest == (_KEY,):
                    rest = (ID_KEY,)
                return (*self.written[prefix], *rest)
        return path


#: The step pydantic names a key by, `scenet.frontends.positions.KEY`, which imports this.
_KEY = "[key]"


def lowered(document: dict[str, Any]) -> Lowered:
    """A document with every keyed collection written as the mapping form, before any merge.

    The document's `cast`, its `panels`, and each panel's `cast`, one value at a time: a
    scene may write its panels as a list and its cast as a mapping. Called before `over:` is
    resolved and before a scene's defaults or a comic script's front matter are merged, so
    a cast written as a list merges actor by actor, as the mapping does. Only keyed
    collections: a shorthand that stands for a value -- one font file for a family, a place
    for its masses, a staging sentence -- replaces the whole value it stands for, and is
    expanded once the panel is whole (`scenet.frontends.common.normalise`).

    Example:
        >>> from scenet.compose import lowered
        >>> lowered(
        ...     {"panels": [{"id": "one", "cast": [{"id": "a", "reference": "alice"}]}]}
        ... ).document
        {'panels': {'one': {'cast': {'a': {'reference': 'alice'}}}}}
        >>> lowered({"cast": [{"id": "bob", "remove": True}]}).document
        {'cast': {'bob': None}}
    """
    faults: list[FormFault] = []
    written: dict[Loc, Loc] = {}
    result = _with_cast(document, (), (), faults, written)
    panels = result.get("panels")
    if isinstance(panels, list):
        named = _named(panels, "panels", ("panels",), faults)
        lowered_panels: dict[str, Any] = {}
        for name, (index, panel) in named.items():
            written[("panels", name)] = ("panels", index)
            lowered_panels[name] = _with_cast(
                panel, ("panels", name), ("panels", index), faults, written
            )
        result["panels"] = lowered_panels
    elif isinstance(panels, dict):
        result["panels"] = {
            name: _with_cast(panel, ("panels", name), ("panels", name), faults, written)
            if isinstance(panel, dict)
            else panel
            for name, panel in panels.items()
        }
    return Lowered(result, tuple(faults), written)


def _with_cast(
    document: dict[str, Any],
    at: Loc,
    written_at: Loc,
    faults: list[FormFault],
    written: dict[Loc, Loc],
) -> dict[str, Any]:
    """The mapping with its `cast`, if a list, as the mapping form."""
    cast = document.get("cast")
    if not isinstance(cast, list):
        return dict(document)
    members: dict[str, Any] = {}
    for actor, (index, member) in _named(cast, "cast", (*written_at, "cast"), faults).items():
        written[(*at, "cast", actor)] = (*written_at, "cast", index)
        before = len(faults)
        lowered_member = _member(member, (*written_at, "cast", index), faults)
        if len(faults) == before:
            # An item at fault is left out, as `_named` leaves one out.
            members[actor] = lowered_member
    return {**document, "cast": members}


def _member(member: dict[str, Any], at: Loc, faults: list[FormFault]) -> dict[str, Any] | None:
    """A cast member of the list form, `None` for one its item removes."""
    remove = member.get(REMOVE_KEY)
    rest = {key: value for key, value in member.items() if key != REMOVE_KEY}
    if remove is None:
        # Not written, or written as `null`, which is a key not written.
        return rest
    if not isinstance(remove, bool):
        faults.append(
            FormFault(
                f"`{REMOVE_KEY}` is true, to leave the member out of the panel, or false",
                "invalid-field",
                (*at, REMOVE_KEY),
            )
        )
        return rest
    if remove and rest:
        faults.append(
            FormFault(
                f"a member with `{REMOVE_KEY}: true` is left out, so it says nothing else: "
                f"delete {', '.join(f'`{key}`' for key in rest)}, or `{REMOVE_KEY}`",
                "invalid-field",
                (*at, REMOVE_KEY),
            )
        )
    return None if remove else rest


def _named(
    items: list[Any], key: str, at: Loc, faults: list[FormFault]
) -> dict[str, tuple[int, dict[str, Any]]]:
    """Each item of a list form under the `id` it gives itself, with its index.

    An item that is not a mapping, has no `id`, has one that is not text, or has one an
    earlier item has, is a fault, and is left out.
    """
    what = _WHAT[key]
    named: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            faults.append(
                FormFault(
                    f"each {what} in the list form is a mapping that says its `{ID_KEY}`, "
                    f"not {type(item).__name__}",
                    "invalid-field",
                    (*at, index),
                )
            )
            continue
        name = item.get(ID_KEY)
        if name is None:
            # `id: null` is a key not written, as a null always is.
            faults.append(FormFault(_unnamed(item, key), "missing-field", (*at, index)))
            continue
        if not isinstance(name, str):
            faults.append(
                FormFault(
                    f"a {what}'s `{ID_KEY}` is text: quote it, `{ID_KEY}: '{name}'`",
                    "invalid-identifier",
                    (*at, index, ID_KEY),
                )
            )
            continue
        if name in named:
            faults.append(
                FormFault(
                    f"{what} '{name}' is item {named[name][0]} and item {index} of `{key}`; "
                    f"each {what} is listed once, with everything it says",
                    "duplicate-key",
                    (*at, index, ID_KEY),
                )
            )
            continue
        named[name] = (index, {field: value for field, value in item.items() if field != ID_KEY})
    return named


def _unnamed(item: dict[str, Any], key: str) -> str:
    """Why an item of a list form with no `id` is refused, and what to write.

    `- bob: {reference: bob}` is the mapping form's entry written as an item: both forms in
    one value. Said as such, with the item as it should be.
    """
    what = _WHAT[key]
    if len(item) == 1:
        ((name, value),) = item.items()
        if isinstance(value, dict) and isinstance(name, str) and name not in _FIELDS[key]:
            fields = ", ".join(f"{field}: ..." for field in value)
            written = f"{{{ID_KEY}: {name}{', ' + fields if fields else ''}}}"
            return (
                f"this item is written as the mapping form writes a {what}, `{name}:` and "
                f"what it says: in the list form, write `{written}`, or write the whole "
                f"`{key}` as a mapping"
            )
    return f"each {what} in the list form says its `{ID_KEY}`"


def as_lists(document: dict[str, Any]) -> dict[str, Any]:
    """A document with its panels and every cast written as lists, in the order written.

    The `id` comes first in each item, and a member a panel leaves out is
    `{id: bob, remove: true}`. What `lowered` undoes.

    Example:
        >>> from scenet.compose import as_lists
        >>> as_lists({"cast": {"a": {"reference": "alice"}, "b": None}})
        {'cast': [{'id': 'a', 'reference': 'alice'}, {'id': 'b', 'remove': True}]}
    """
    result = _cast_as_list(document)
    panels = result.get("panels")
    if isinstance(panels, dict):
        result["panels"] = [
            {ID_KEY: name, **(_cast_as_list(panel) if isinstance(panel, dict) else {})}
            for name, panel in panels.items()
        ]
    return result


def _cast_as_list(document: dict[str, Any]) -> dict[str, Any]:
    """The mapping with its `cast`, if a mapping, as a list."""
    cast = document.get("cast")
    if not isinstance(cast, dict) or not all(
        member is None or isinstance(member, dict) for member in cast.values()
    ):
        return dict(document)
    return {
        **document,
        "cast": [
            {ID_KEY: actor, REMOVE_KEY: True} if member is None else {ID_KEY: actor, **member}
            for actor, member in cast.items()
        ],
    }
