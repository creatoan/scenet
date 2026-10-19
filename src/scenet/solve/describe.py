"""The words a panel is read in, for a reader who cannot see it.

Two things, both built here so that Panel Core carries them and the emitter copies them
without deciding anything:

- **A description** of what the panel shows. The author's, when there is one -- written as
  `description:`, or a comic script's prose. Otherwise generated from what the panel
  holds, covering what *AccessComics* (Lee, Joh, Yoo & Oh) found blind readers wanted
  narrated: the shot, the place and the hour, who is where, facing whom, with what face
  and what marks. `"Medium shot. A street at night, in the rain. Alice, left, pointing,
  angry, looking at Bob; Bob, right, arms crossed, sweating."`
- **A label for each script entry**: who says it, how, and the words --
  `"Bob, whispering: I know."` -- in the one reading order balloons, captions and sound
  effects share.

Generated text is **templated English**, and that is its limit: a French script's prose is
read in French, but the words round its dialogue are English. Every phrase is in a table
below, keyed by the enum it reads, so a value with no phrase is a test failure rather
than a gap a reader hears. Nothing depends on a locale, or on the order a set or a dict
happens to iterate in: the cast is read left to right, ties broken by id.

This sees no artwork. Where a figure is comes in as one number, its face's x, the same
rounded value Panel Core records.
"""

from collections.abc import Mapping, Sequence

from scenet.emphasis import plain
from scenet.ir import (
    BalloonKind,
    CameraAngle,
    CaptionEvent,
    CaptionKind,
    Mark,
    MassKind,
    PanelIR,
    Predicate,
    SayEvent,
    ScriptEvent,
    SettingSpec,
    ShotType,
    TimeOfDay,
    TypeSize,
    Weather,
)
from scenet.places import PLACES, Place

__all__ = [
    "ANGLES",
    "EXPRESSIONS",
    "INDOOR",
    "MARKS",
    "PLACE_NAMES",
    "SHOTS",
    "TIMES",
    "WEATHERS",
    "describe",
    "label",
    "labels",
    "name",
    "sentence",
]

#: Each rung of the shot ladder, as a letterer's script would name it.
SHOTS: dict[ShotType, str] = {
    ShotType.LONG_SHOT: "Long shot",
    ShotType.WIDE: "Long shot",
    ShotType.FULL_SHOT: "Full shot",
    ShotType.MEDIUM_FULL: "Medium full shot",
    ShotType.COWBOY: "Cowboy shot",
    ShotType.MEDIUM_SHOT: "Medium shot",
    ShotType.MEDIUM_CLOSE_UP: "Medium close-up",
    ShotType.CLOSE_UP: "Close-up",
    ShotType.BIG_CLOSE_UP: "Big close-up",
    ShotType.EXTREME_CLOSE_UP: "Extreme close-up",
}

#: The camera's height, said after the shot; eye level goes without saying.
ANGLES: dict[CameraAngle, str] = {
    CameraAngle.LOW: "from a low angle",
    CameraAngle.EYE_LEVEL: "",
    CameraAngle.HIGH: "from a high angle",
}

#: Each named place, as the start of a sentence.
PLACE_NAMES: dict[Place, str] = {
    Place.ALLEY: "An alley",
    Place.DESERT: "A desert",
    Place.DOCKS: "The docks",
    Place.FIELD: "A field",
    Place.FOREST: "A forest",
    Place.MOUNTAIN: "A mountainside",
    Place.OFFICE: "An office",
    Place.ROOM: "A room",
    Place.SHORE: "A shore",
    Place.STREET: "A street",
}

#: COCO-Stuff's indoor supercategories: masses that make a backdrop an interior.
INDOOR: frozenset[MassKind] = frozenset(
    {MassKind.CEILING, MassKind.FLOOR, MassKind.FURNITURE, MassKind.WALL, MassKind.WINDOW}
)

TIMES: dict[TimeOfDay, str] = {
    TimeOfDay.DAWN: "at dawn",
    TimeOfDay.DAY: "by day",
    TimeOfDay.DUSK: "at dusk",
    TimeOfDay.NIGHT: "at night",
}

#: What the air is doing; a clear sky goes without saying.
WEATHERS: dict[Weather, str] = {
    Weather.CLEAR: "",
    Weather.RAIN: "in the rain",
    Weather.FOG: "in fog",
    Weather.SNOW: "in the snow",
}

#: Walker's marks, read as what they say -- the table in :class:`Mark <scenet.ir.Mark>`.
MARKS: dict[Mark, str] = {
    Mark.PLEWDS: "sweating",
    Mark.SQUEANS: "dizzy",
    Mark.GRAWLIXES: "swearing",
    Mark.BRIFFITS: "dashing off",
}

#: Expressions whose name is not a word that can follow a name. Any other is read as
#: written, an underscore a space: a puppet of one's own names its own.
EXPRESSIONS: dict[str, str] = {"surprise": "surprised"}

#: What a figure doing nothing in particular does, which goes without saying.
_STANDING = "standing_neutral"
_NEUTRAL = "neutral"

#: How a balloon's line is said, after the speaker's name.
_DELIVERY: dict[BalloonKind, str] = {
    BalloonKind.SPEECH: "",
    BalloonKind.WHISPER: "whispering",
    BalloonKind.SHOUT: "shouting",
    BalloonKind.THOUGHT: "thinking",
}

#: Who speaks a caption with no speaker.
_CAPTIONS: dict[CaptionKind, str] = {
    CaptionKind.LOCALE: "Caption",
    CaptionKind.MONOLOGUE: "Caption, inner voice",
    CaptionKind.EDITORIAL: "Editor's note",
    CaptionKind.SPOKEN: "Off panel",
}

#: What a line may end with and already be a sentence: full stop, question, exclamation,
#: ellipsis, and the dashes a line broken off ends with: em, en, and a hyphen.
_ENDS = ".!?…—\u2013-"
#: What may close a line after its last mark: quotation marks and brackets -- straight,
#: curly (U+201D, U+2019) and guillemet.
_CLOSERS = "\"'”\u2019»)]"


def name(actor: str) -> str:
    """An actor id as a name: an underscore a space, and a lower-case id capitalised.

    An id written in capitals, as a comic script writes its cast, is kept as it is.

    Example:
        >>> [name(actor) for actor in ("alice", "guard_left", "ALICE")]
        ['Alice', 'Guard left', 'ALICE']
    """
    said = actor.replace("_", " ")
    if actor == actor.lower():
        said = said[:1].upper() + said[1:]
    return said


def sentence(text: str) -> str:
    """A line as a sentence: one space between words, and a full stop if it has no end.

    So two lines one after the other are heard as two -- `Hi` and `Hello` would otherwise
    run together. A line that already ends, inside its quotation marks or not, is left as
    it is.

    Example:
        >>> [sentence(line) for line in ("Hi", "You what?!", "“Get down”")]
        ['Hi.', 'You what?!', '“Get down”.']
    """
    said = " ".join(text.split())
    if said.rstrip(_CLOSERS)[-1:] in tuple(_ENDS):
        return said
    return f"{said}."


def _who(event: SayEvent) -> str:
    """Who says a line, and how: `Carol, off panel, whispering, quietly`."""
    parts = [name(event.by)]
    if event.off_panel is not False:
        parts.append("off panel")
    if delivery := _DELIVERY[event.kind]:
        parts.append(delivery)
    if event.size is TypeSize.SMALL:
        parts.append("quietly")
    return ", ".join(parts)


def label(event: ScriptEvent) -> str:
    """One script entry as it is read: who, how, and the words.

    The words are the author's, with emphasis markers off -- never the lettered lines,
    which are broken to fit and, for a spoken caption, carry quotation marks that are
    lettering rather than speech.

    Example:
        >>> from scenet.ir import SayEvent
        >>> label(SayEvent(by="bob", text="I _know_", kind="whisper"))
        'Bob, whispering: I know.'
    """
    if isinstance(event, SayEvent):
        return f"{_who(event)}: {sentence(plain(event.text))}"
    if isinstance(event, CaptionEvent):
        who = (
            f"{name(event.by)}, off panel"
            if event.kind is CaptionKind.SPOKEN and event.by is not None
            else _CAPTIONS[event.kind]
        )
        return f"{who}: {sentence(plain(event.text))}"
    # A sound effect's underscore is a letter, not emphasis.
    source = f", from {name(event.source)}" if event.source is not None else ""
    return f"Sound effect{source}: {sentence(event.text)}"


def labels(script: Sequence[ScriptEvent]) -> tuple[str, ...]:
    """Every entry's label, in script order, which is reading order."""
    return tuple(label(event) for event in script)


def _shot(panel: PanelIR) -> str:
    angle = ANGLES[panel.camera.angle]
    return f"{SHOTS[panel.camera.shot]}{f', {angle}' if angle else ''}."


def _place(setting: SettingSpec) -> str:
    """Where, from the masses: a named place's, or indoors or out."""
    masses = tuple(setting.masses)
    for place in Place:
        if PLACES[place] == masses:
            return PLACE_NAMES[place]
    return "Indoors" if any(mass.kind in INDOOR for mass in masses) else "Outdoors"


def _setting(setting: SettingSpec) -> str:
    """The place, the hour and the weather, or nothing for a panel set nowhere.

    Over a supplied picture only the weather is said: it is drawn over the picture, and
    the compiler knows it. The place and the hour are in the picture, which it has never
    seen -- so it says nothing of them rather than something it would have to guess.
    """
    if setting.is_bare:
        return ""
    weather = WEATHERS[setting.weather]
    if setting.image is not None:
        return f"{weather[0].upper()}{weather[1:]}." if weather else ""
    return f"{_place(setting)} {TIMES[setting.time]}{f', {weather}' if weather else ''}."


def _where(x: float, width: float) -> str:
    """Left, centre or right, by thirds of the panel."""
    if x < width / 3:
        return "left"
    if x > 2 * width / 3:
        return "right"
    return "centre"


def _figure(panel: PanelIR, actor: str, x: float, width: float) -> str:
    """One figure: where, how they stand, their face, their marks, and whom they face."""
    member = panel.cast[actor]
    parts = [name(actor), _where(x, width)]
    if member.pose != _STANDING:
        parts.append(member.pose.replace("_", " "))
    if member.expression != _NEUTRAL:
        parts.append(EXPRESSIONS.get(member.expression, member.expression.replace("_", " ")))
    parts.extend(MARKS[mark] for mark in member.marks)
    target = panel.gaze_targets().get(actor)
    if target is not None:
        heard = target not in panel.cast
        parts.append(f"looking {'off panel ' if heard else ''}at {name(target)}")
    depth = {Predicate.IN_FRONT_OF: "in front of", Predicate.BEHIND: "behind"}
    for relation in panel.staging:
        if relation.subject == actor and relation.predicate in depth:
            phrase = f"{depth[relation.predicate]} {name(relation.object)}"
            if phrase not in parts:
                parts.append(phrase)
    return ", ".join(parts)


def describe(panel: PanelIR, faces: Mapping[str, float], width: float) -> str:
    """What the panel shows, in words: the author's, or generated from what it holds.

    Args:
        panel: The validated panel.
        faces: Each actor's face-centre x, as Panel Core records it.
        width: The panel's width, which "left" and "right" are thirds of.

    Returns:
        One paragraph.

    Example:
        >>> from scenet import parse_panel
        >>> panel = parse_panel("setting: {place: docks, time: night}")
        >>> describe(panel, {}, 1000.0)
        'The docks at night.'
    """
    if panel.description is not None:
        return panel.description
    setting = _setting(panel.setting)
    # Only who is drawn: a figure the panel's picture does not draw is not in it (#71).
    cast = sorted((actor for actor in panel.cast if actor in faces), key=lambda a: (faces[a], a))
    if not cast:
        # A picture is not nothing, though nothing can be said of what it shows.
        empty = "A panel with no figures." if panel.setting.image else "An empty panel."
        return setting or empty
    figures = "; ".join(_figure(panel, actor, faces[actor], width) for actor in cast)
    # The shot of a cast a picture draws is whatever the artist drew, which nobody told
    # the compiler: no shot is said rather than a default one.
    shot = "" if panel.drawn_by_its_picture else _shot(panel)
    return " ".join(part for part in (shot, setting, f"{figures}.") if part)
