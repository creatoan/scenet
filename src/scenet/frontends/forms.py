"""The two forms of a collection the author names: a mapping, and a list (#356).

`panels:` and `cast:` are mappings whose keys the author chooses, and whose order means
something: the panels are read in it, and the first of the cast is the one the camera
frames. A tool that sorts keys -- PyYAML's `dump` does by default -- reorders the comic
without a word, and a structured-output mode that cannot write a mapping with chosen keys
cannot write either. So each may also be written as a list, each item naming itself:

.. code-block:: yaml

    panels:
      - name: street
        cast: [{id: alice, reference: alice}]
      - name: close
        over: street

Staging has a sentence form for people and a mapping form for programs; this is the same
idea the other way round. The list form is lowered to the mapping form as soon as the
document is read -- before `over:` is resolved and before a scene's defaults are merged --
so nothing past here knows it was written, and both forms are one language.
"""

from dataclasses import dataclass
from typing import Any

from scenet.ir import CastMember, PanelIR

__all__ = ["NAMING_KEYS", "PANELS_SHAPE", "FormFault", "as_lists", "lowered", "lowered_cast"]

#: Each collection that may be written as a list, and the key each of its items is named
#: by: `name` for a panel, as a page names it, and `id` for a cast member, an actor id.
NAMING_KEYS: dict[str, str] = {"panels": "name", "cast": "id"}

#: What `panels:` must be, as the finding refusing anything else says.
PANELS_SHAPE = (
    "'panels' must be a mapping of name to panel, or a list of panels each with its `name`"
)

#: The keys an item of each collection may say, which name no item of the mapping form.
_FIELDS: dict[str, frozenset[str]] = {
    "panels": frozenset({*PanelIR.model_fields, "over"}),
    "cast": frozenset(CastMember.model_fields),
}

#: What each collection holds, for a message.
_WHAT = {"panels": "panel", "cast": "cast member"}


@dataclass(frozen=True, slots=True)
class FormFault:
    """A list form written wrong, where it is written.

    Attributes:
        message: What is wrong, and what to write.
        rule: The catalogue rule it breaks.
        loc: Where, as the document is written: an item's index, then its naming key.
    """

    message: str
    rule: str
    loc: tuple[str | int, ...]


def lowered(document: dict[str, Any]) -> tuple[dict[str, Any], tuple[FormFault, ...]]:
    """A document with every list form written as the mapping form.

    The document's `cast`, its `panels`, and the `cast` of every panel. An item at fault is
    left out of what is lowered, so the rest can still be checked.

    Returns:
        The document, and its faults in the order they are written.

    Example:
        >>> from scenet.frontends.forms import lowered
        >>> lowered({"panels": [{"name": "one", "cast": [{"id": "a", "reference": "alice"}]}]})
        ({'panels': {'one': {'cast': {'a': {'reference': 'alice'}}}}}, ())
    """
    faults: list[FormFault] = []
    result = _with_cast(document, (), faults)
    panels = result.get("panels")
    if isinstance(panels, list):
        named = _named(panels, "panels", ("panels",), faults)
        result["panels"] = {
            name: _with_cast(panel, ("panels", index), faults)
            for name, (index, panel) in named.items()
        }
    elif isinstance(panels, dict):
        result["panels"] = {
            name: _with_cast(panel, ("panels", name), faults) if isinstance(panel, dict) else panel
            for name, panel in panels.items()
        }
    return result, tuple(faults)


def lowered_cast(
    settings: dict[str, Any], at: tuple[str | int, ...] = ()
) -> tuple[dict[str, Any], tuple[FormFault, ...]]:
    """A mapping with its `cast` written as the mapping form, and nothing else lowered.

    For a comic script's front matter or `@cast:` directive, where there are no panels.

    Example:
        >>> from scenet.frontends.forms import lowered_cast
        >>> lowered_cast({"cast": [{"id": "ALICE", "reference": "alice"}]})
        ({'cast': {'ALICE': {'reference': 'alice'}}}, ())
    """
    faults: list[FormFault] = []
    return _with_cast(settings, at, faults), tuple(faults)


def _with_cast(
    document: dict[str, Any], at: tuple[str | int, ...], faults: list[FormFault]
) -> dict[str, Any]:
    """The mapping with its `cast`, if a list, as the mapping form."""
    cast = document.get("cast")
    if not isinstance(cast, list):
        return dict(document)
    named = _named(cast, "cast", (*at, "cast"), faults)
    return {**document, "cast": {name: member for name, (_, member) in named.items()}}


def _named(
    items: list[Any], key: str, at: tuple[str | int, ...], faults: list[FormFault]
) -> dict[str, tuple[int, dict[str, Any]]]:
    """Each item of a list form under the name it gives itself, with its index.

    An item that is not a mapping, names nothing, names itself with something other than
    text, or names itself as an earlier item did, is a fault, and left out.
    """
    naming = NAMING_KEYS[key]
    what = _WHAT[key]
    named: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            faults.append(
                FormFault(
                    f"each {what} in the list form is a mapping that says its `{naming}`, "
                    f"not {type(item).__name__}",
                    "invalid-field",
                    (*at, index),
                )
            )
            continue
        if naming not in item:
            faults.append(FormFault(_unnamed(item, key), "missing-field", (*at, index)))
            continue
        name = item[naming]
        if not isinstance(name, str):
            faults.append(
                FormFault(
                    f"a {what}'s `{naming}` is text: quote it, `{naming}: '{name}'`",
                    "invalid-identifier",
                    (*at, index, naming),
                )
            )
            continue
        if name in named:
            faults.append(
                FormFault(
                    f"{what} '{name}' is item {index} and item {named[name][0]} of `{key}`; "
                    f"each {what} is listed once, with everything it says",
                    "duplicate-key",
                    (*at, index, naming),
                )
            )
            continue
        named[name] = (index, {field: value for field, value in item.items() if field != naming})
    return named


def _unnamed(item: dict[str, Any], key: str) -> str:
    """Why an item of a list form that does not name itself is refused, and what to write.

    `- bob: {reference: bob}` is the mapping form's entry written as an item: the two forms
    mixed in one key. Said as such, with the item as it should be.
    """
    naming = NAMING_KEYS[key]
    what = _WHAT[key]
    if len(item) == 1:
        ((name, value),) = item.items()
        if isinstance(value, dict) and isinstance(name, str) and name not in _FIELDS[key]:
            fields = ", ".join(f"{field}: ..." for field in value)
            written = f"{{{naming}: {name}{', ' + fields if fields else ''}}}"
            return (
                f"this item is written as the mapping form writes a {what}, `{name}:` and "
                f"what it says: in the list form, write `{written}`, or write the whole "
                f"`{key}` as a mapping"
            )
    return f"each {what} in the list form says its `{naming}`"


def as_lists(document: dict[str, Any]) -> dict[str, Any]:
    """A document with its panels and every cast written as lists, in the order written.

    The naming key comes first in each item. A cast that leaves somebody out with `null`
    stays a mapping: a list has no item for nobody.

    Example:
        >>> from scenet.frontends.forms import as_lists
        >>> as_lists({"cast": {"a": {"reference": "alice"}}})
        {'cast': [{'id': 'a', 'reference': 'alice'}]}
    """
    result = _cast_as_list(document)
    panels = result.get("panels")
    if isinstance(panels, dict):
        result["panels"] = [
            {"name": name, **(_cast_as_list(panel) if isinstance(panel, dict) else {})}
            for name, panel in panels.items()
        ]
    return result


def _cast_as_list(document: dict[str, Any]) -> dict[str, Any]:
    """The mapping with its `cast` as a list, unless it leaves somebody out."""
    cast = document.get("cast")
    if not isinstance(cast, dict) or not all(isinstance(member, dict) for member in cast.values()):
        return dict(document)
    return {**document, "cast": [{"id": actor, **member} for actor, member in cast.items()]}
