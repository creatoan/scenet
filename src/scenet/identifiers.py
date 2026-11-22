r"""One grammar for actor ids and panel names, with separators reserved for the future.

An actor id and a panel name are both an **identifier**: one to sixty-four letters, digits,
`_` and `-`, with the combining marks that accent a letter, starting with a letter or a
digit. `Zoé` and `健` are identifiers; `old man`, `a/b` and `-x` are not.

Five characters are **reserved** and never part of one: `.`, `/`, `:`, `#` and `@`. A
reference that reaches beyond its own document will need a separator nothing else can
mean -- `chapter/panel`, `file#panel` -- and a panel's name is part of a file name, where
`/` and `.` already mean something. So are some **words**: the predicates of a staging
sentence, read as the sentence's verb, and the labels a comic script reads as a caption or
a sound effect, `CAP`, `CAPTION`, `SFX` and their French twins. They are compared without
case, as :meth:`str.casefold` compares them: `Left_Of` and `sfx` are reserved too. And no
identifier starts with `x-`, which marks an **extension** key in any mapping of a document
(:mod:`scenet.namespace`): a key under `cast:` or `panels:` is an id or an extension, never
both. `X-ray`, in a capital, is an id, as it is no extension.

**One definition, three readers.** The JSON Schema states :attr:`Grammar.pattern`; the
validator matches the same pattern, and says which part of the grammar a name breaks; the
comic-script frontend asks the validator. The pattern is written in the regular expressions
Python's `re` and ECMAScript's (with the `u` flag, as JSON Schema 2020-12 reads them) agree
on, so an editor, a model decoding against the schema and `scenet check` refuse the same
names. Neither has a class for "a letter" that means the same in both -- Python's `re` has no
`\p{L}`, and ECMAScript's follows its engine's Unicode -- so the letters, digits and marks
are spelled out, from one pinned Unicode version, in :mod:`scenet.identifier_tables`.

Example:
    >>> from scenet.identifiers import Grammar
    >>> grammar = Grammar(("left_of",))
    >>> grammar.problem("Zoé") is None
    True
    >>> grammar.problem("a/b").split(". ")[0]
    "'a/b' is not an id: '/' is reserved, for references between documents"
    >>> grammar.problem("LEFT_OF").split(". ")[0]
    "'LEFT_OF' is not an id: it is a reserved word"
"""

import functools
import re
from dataclasses import dataclass

from scenet.identifier_tables import CASES, CONTINUES, STARTS

__all__ = [
    "EXTENSION_PREFIX",
    "GRAMMAR",
    "LABEL_WORDS",
    "MAX_LENGTH",
    "RESERVED_CHARACTERS",
    "Grammar",
]

#: The longest an identifier is, in characters (code points).
MAX_LENGTH = 64

#: The characters no identifier holds, kept for references between documents.
RESERVED_CHARACTERS = "./:#@"

#: What an extension key starts with, in any mapping of any document: a key a tool writes
#: and Scenet ignores. In lower case, as OpenAPI spells it.
EXTENSION_PREFIX = "x-"

#: The labels a comic script reads as a caption or a sound effect rather than a speaker's
#: cue: an actor called `CAP` could never speak. The French ones are the script frontend's
#: too (:mod:`scenet.frontends.script_front`).
LABEL_WORDS = (
    "cap",
    "caption",
    "sfx",
    "récitatif",
    "recitatif",
    "narratif",
    "cartouche",
    "onomatopée",
    "onomatopee",
)

#: The grammar, in words, as every refusal states it.
GRAMMAR = (
    f"An id is 1 to {MAX_LENGTH} letters, digits, '_' and '-', and the marks that accent a "
    "letter, starting with a letter or a digit; '.', '/', ':', '#' and '@' are reserved, and "
    "so, in any case, are the words of a staging sentence and of a comic script's labels; "
    f"and no id starts with '{EXTENSION_PREFIX}', which marks an extension key"
)

#: The end of the text, in both dialects. Python's `$` also matches before a final line
#: break, so `a` followed by one would pass a schema validator written in Python.
END = r"(?![\s\S])"

#: Printable ASCII, which a message shows as itself beside its code point.
_ASCII = range(0x20, 0x7F)


@functools.cache
def _compiled(words: tuple[str, ...]) -> tuple[str, re.Pattern[str], re.Pattern[str]]:
    """The pattern for an identifier, compiled, and the one for a reserved word alone.

    Each reserved word is spelled a class per letter, of every character `str.casefold`
    folds to it. Built once per set of words, as the language's is built when it is
    imported: so a decorated function, which mutmut leaves alone, rather than a helper it
    would mutate where no test can reach the mutant.
    """
    reserved = "|".join("".join(f"[{CASES[letter]}]" for letter in word) for word in words)
    pattern = (
        f"^(?!(?:{reserved}){END})(?!{EXTENSION_PREFIX})"
        f"[{STARTS}][{CONTINUES}]{{0,{MAX_LENGTH - 1}}}{END}"
    )
    return pattern, re.compile(pattern), re.compile(f"^(?:{reserved}){END}")


_STARTS = re.compile(f"[{STARTS}]")
_CONTINUES = re.compile(f"[{CONTINUES}]")


def _code_point(character: str) -> str:
    """A character as a message names it: itself, if it can be read, and its code point."""
    point = f"U+{ord(character):04X}"
    return f"'{character}' ({point})" if ord(character) in _ASCII else point


def shown(name: str) -> str:
    """A name as a message shows it, quoted, with anything unreadable as its code point.

    Example:
        >>> from scenet.identifiers import shown
        >>> shown("old man"), shown("a" + chr(9) + "b")
        ("'old man'", "'a<U+0009>b'")
    """
    readable = (
        character
        if ord(character) in _ASCII or _CONTINUES.fullmatch(character)
        else f"<U+{ord(character):04X}>"
        for character in name
    )
    return f"'{''.join(readable)}'"


@dataclass(frozen=True, slots=True)
class Grammar:
    """The identifier grammar, with the words it reserves.

    The language's is :data:`scenet.ir.IDENTIFIERS`, whose words are the staging
    predicates and :data:`LABEL_WORDS`; a grammar of other words is for a test.

    A dataclass with nothing to set up, so mutmut can mutate everything it does: the
    pattern is compiled on first use, once per set of words.

    Attributes:
        words: The reserved words, in lower case.
    """

    words: tuple[str, ...]

    @property
    def pattern(self) -> str:
        """The pattern an identifier matches, in the dialect Python and ECMAScript share."""
        return _compiled(self.words)[0]

    def problem(self, name: str) -> str | None:
        """What is wrong with `name` as an identifier, stating the grammar, or None.

        The pattern decides; the rest says which part of the grammar `name` breaks, so a
        finding says what to change.
        """
        _, compiled, reserved = _compiled(self.words)
        if compiled.search(name) is not None:
            return None
        return f"{shown(name)} is not an id: {_why(name, reserved)}. {GRAMMAR}"


def _why(name: str, reserved: re.Pattern[str]) -> str:
    """Which part of the grammar `name`, which does not match it, breaks: first its characters."""
    if not name:
        return "it is empty"
    for character in name:
        if character in RESERVED_CHARACTERS:
            return f"'{character}' is reserved, for references between documents"
    for character in name:
        if _CONTINUES.fullmatch(character) is None:
            return f"{_code_point(character)} is not a letter, a digit, a mark, '_' or '-'"
    return _why_as_a_whole(name, reserved)


def _why_as_a_whole(name: str, reserved: re.Pattern[str]) -> str:
    """Which part of the grammar `name`, every character of which an identifier may hold, breaks.

    Starting well, it is an extension's, a reserved word or too long: no reserved word is
    either of the others, so nothing else is left once the first three are not the reason.
    """
    if _STARTS.fullmatch(name[0]) is None:
        return f"it starts with {_code_point(name[0])}, which is not a letter or a digit"
    if name.startswith(EXTENSION_PREFIX):
        return (
            f"it starts with '{EXTENSION_PREFIX}', which marks an extension key, one Scenet "
            "ignores wherever it is written"
        )
    if reserved.search(name) is not None:
        return "it is a reserved word"
    return f"it is {len(name)} characters long, more than {MAX_LENGTH}"
