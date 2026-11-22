"""How much Scenet reads of a file: the bounds on what a document can make it read.

A document names files -- a picture, a font, a puppet, an artwork contract -- and a caller
names the document. Each is read whole, so each is bounded: a file larger than its bound
is refused by its size, before a byte of it is read, and the refusal is a finding of the
read's own rule. A bound is generous for a real comic; it is there so that a path to
something enormous, or endless, is an answer rather than a process that runs out of
memory.

Every bound is a number of bytes, and a module attribute, read at the moment of each read:
a host that wants tighter ones sets them before it compiles.

Example:
    >>> from scenet.limits import IMAGE_BYTES, describe
    >>> describe(IMAGE_BYTES)
    '128 MiB'
"""

__all__ = ["DOCUMENT_BYTES", "FONT_BYTES", "IMAGE_BYTES", "describe"]

#: A document, and the text files it names: a puppet file, an artwork contract. A
#: hundred-page comic script is well under a megabyte.
DOCUMENT_BYTES = 8 * 2**20

#: A picture to letter over. A 600 dpi A4 page, the largest a printer asks for, is a PNG of
#: some 30 to 60 MiB.
IMAGE_BYTES = 128 * 2**20

#: A lettering face. A font that covers Chinese, Japanese or Korean is some 20 MiB.
FONT_BYTES = 64 * 2**20

_UNITS = (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10))


def describe(size: int) -> str:
    """A number of bytes in words, in the largest unit it is a whole number of.

    Args:
        size: The number of bytes.

    Returns:
        `8 MiB`, say, or `10 bytes`.

    Example:
        >>> from scenet.limits import describe
        >>> describe(2048), describe(2049), describe(1)
        ('2 KiB', '2049 bytes', '1 byte')
    """
    for unit, scale in _UNITS:
        if size >= scale and size % scale == 0:
            return f"{size // scale} {unit}"
    return "1 byte" if size == 1 else f"{size} bytes"
