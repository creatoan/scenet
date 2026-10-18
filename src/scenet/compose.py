"""Sparse override between panels.

Borrowed from OpenUSD's composition arcs, and specifically from `over`: a panel names
a parent and states only what differs from it.

This matters more for comics than it might look. Consecutive panels in a scene are
mostly identical -- the same cast, the same staging, the same camera -- with one thing
changed. Restating all of it per panel is both tedious and a place for inconsistencies
to creep in, which is exactly the continuity error comics readers notice.

    panels:
      p1:
        camera: {shot: medium_shot}
        cast:
          alice: {reference: alice, at: left_third}
      p2:
        over: p1                      # everything from p1...
        camera: {shot: close_up}      # ...except the framing

Taking something away is JSON Merge Patch's rule (RFC 7386): "If the value is null,
remove". `cast: {bob: null}` leaves Bob out of a panel that would otherwise inherit him.
"""

from dataclasses import dataclass
from typing import Any

from scenet.errors import CompositionError

__all__ = ["OVER_KEY", "Dropped", "merge", "names", "relation_text", "resolve_overrides", "settle"]

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


def settle(document: dict[str, Any]) -> tuple[dict[str, Any], tuple[Dropped, ...]]:
    """Apply the removals a complete document's `null`s ask for.

    Every key whose value is `null` goes, in mappings at any depth -- not inside lists,
    which Merge Patch treats as values. A cast member who goes takes with them every
    staging relation that names them, since none can hold in a panel they are not in.

    Returns:
        The document, and the relations dropped, in the order they were written.

    Example:
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
    staging = settled.get("staging")
    if not leaving or not isinstance(staging, list):
        return settled, ()
    kept: list[object] = []
    dropped: list[Dropped] = []
    for index, relation in enumerate(staging):
        actor = next((actor for actor in leaving if names(relation, actor)), None)
        if actor is None:
            kept.append(relation)
        else:
            dropped.append(Dropped(index, relation, actor))
    return {**settled, "staging": kept}, tuple(dropped)


def _without_nulls(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _without_nulls(value) if isinstance(value, dict) else value
        for key, value in mapping.items()
        if value is not None
    }
