r"""Emphasis in lettering: the words a script underlines, and a letterer sets in bold italic.

Blambot's *Comic Book Grammar & Tradition*: "There's almost no plain bold in comics
dialogue. Typically, bold italic is used when emphasis is placed on a word." Dark Horse's
script format asks writers to underline the words they want stressed. Plain text has no
underline, so an author writes the word between underscores -- `I _told_ you` -- which is
what this module reads.

**Underscores, and only underscores.** Markdown's other marker, `*`, starts an alias in
YAML when it opens a plain value (`text: *told* you` does not parse), and it is one of the
characters a typed grawlix is made of. An underscore has neither problem.

The rules are Markdown's for an underscore, which is what keeps `snake_case` literal:

- an underscore **opens** a span when nothing alphanumeric is before it and something
  other than a space is after it;
- inside a span, an underscore **closes** it when something other than a space is before
  it and nothing alphanumeric is after it;
- any other underscore is just an underscore -- so is one beside another, as in
  `__init__` -- and `\_` writes one anywhere;
- spans do not nest, and may run across words: `_told you_`.

A span opened and never closed is refused rather than guessed at. It is almost always a
missing underscore, and setting the rest of the line in bold italic would be a confident
wrong answer.

Pure and dependency-free on purpose: the IR uses it to refuse an unclosed span while the
source is still in view, and the solver uses it to decide which face each character is
measured and drawn in. The two cannot disagree, because they call the same function.
"""

from dataclasses import dataclass

__all__ = ["MARKER", "EmphasisError", "Span", "parse", "plain"]

#: What opens and closes a span.
MARKER = "_"

#: Written before a marker to make it an ordinary underscore.
ESCAPE = "\\"


@dataclass(frozen=True, slots=True)
class Span:
    """A stretch of text, emphasised or not.

    Attributes:
        text: What is lettered, markers and escapes already removed.
        emphasised: Whether it is set in the emphasis face.
    """

    text: str
    emphasised: bool


class EmphasisError(ValueError):
    """A span was opened and never closed.

    Attributes:
        position: Index of the opening underscore in the text as written.
    """

    def __init__(self, text: str, position: int) -> None:
        """Build the error, naming where the span opened.

        Args:
            text: The text as written.
            position: Index of the opening underscore.
        """
        self.position = position
        opened = text[position : position + 12]
        super().__init__(
            f"the emphasis opened by the underscore at character {position + 1} "
            f"({opened!r}) is never closed; end it with '_' after the last stressed word, "
            "or write '\\_' for an underscore that is not emphasis"
        )


def _opens(text: str, index: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    if before == MARKER or after in ("", MARKER) or after.isspace():
        return False
    return not before.isalnum()


def _closes(text: str, index: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    if before in ("", MARKER) or after == MARKER or before.isspace():
        return False
    return not after.isalnum()


def parse(text: str) -> tuple[Span, ...]:
    """Split text into emphasised and plain spans.

    Args:
        text: A line of dialogue or a caption, as the author wrote it.

    Returns:
        The spans in order, each non-empty, adjacent ones never alike. Text with no
        marker in it is one plain span.

    Raises:
        EmphasisError: A span was opened and never closed.

    Example:
        >>> from scenet.emphasis import parse
        >>> [(span.text, span.emphasised) for span in parse("I _told_ you")]
        [('I ', False), ('told', True), (' you', False)]
    """
    spans: list[Span] = []
    current: list[str] = []
    emphasised = False
    opened_at = -1

    def flush() -> None:
        if current:
            spans.append(Span("".join(current), emphasised))
            current.clear()

    index = 0
    while index < len(text):
        character = text[index]
        if character == ESCAPE and text[index + 1 : index + 2] == MARKER:
            current.append(MARKER)
            index += 2
            continue
        if character == MARKER:
            if not emphasised and _opens(text, index):
                flush()
                emphasised, opened_at = True, index
                index += 1
                continue
            if emphasised and _closes(text, index):
                flush()
                emphasised = False
                index += 1
                continue
        current.append(character)
        index += 1

    if emphasised:
        raise EmphasisError(text, opened_at)
    flush()
    return tuple(spans)


def plain(text: str) -> str:
    """The text as it is read: markers and escapes removed.

    Args:
        text: As the author wrote it.

    Returns:
        What is lettered.

    Raises:
        EmphasisError: A span was opened and never closed.

    Example:
        >>> from scenet.emphasis import plain
        >>> plain("I _told_ you")
        'I told you'
    """
    return "".join(span.text for span in parse(text))
