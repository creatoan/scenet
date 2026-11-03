"""A puppet of an author's own, for tests: a file a document names by its path (#242).

Written out in full rather than derived from a shipped puppet, so a test that reads it
from a folder, from files sent with a document, or over MCP is reading exactly what an
author would write -- and so it can be told from alice and bob: five heads tall where they
are seven and a half, with a pose and an expression neither of them has.
"""

import base64

#: Where the tests put it, relative to the document: in a `puppets/` folder beside it.
KID_PATH = "puppets/kid.puppet.yaml"

KID = """\
# A child: five heads tall, so the head is big for the body.
name: kid
units_per_head: 100

landmarks:
  head_top: 0
  eyes: 50
  chin: 100
  shoulders: 120
  chest: 165
  waist: 245
  mid_thigh: 320
  knees: 375
  feet: 500

joints:
  root: {parent: null, offset: [0, 0]}
  spine: {parent: root, offset: [0, -80]}
  neck: {parent: spine, offset: [0, -45]}
  head: {parent: neck, offset: [0, -70]}
  shoulder_l: {parent: neck, offset: [-26, 4]}
  shoulder_r: {parent: neck, offset: [26, 4]}
  elbow_l: {parent: shoulder_l, offset: [0, 62]}
  elbow_r: {parent: shoulder_r, offset: [0, 62]}
  hip_l: {parent: root, offset: [-20, 8]}
  hip_r: {parent: root, offset: [20, 8]}
  knee_l: {parent: hip_l, offset: [0, 122]}
  knee_r: {parent: hip_r, offset: [0, 122]}

parts:
  - {from: neck, to: root, width: 64}
  - {from: shoulder_l, to: elbow_l, width: 22}
  - {from: shoulder_r, to: elbow_r, width: 22}
  - {from: hip_l, to: knee_l, width: 28}
  - {from: hip_r, to: knee_r, width: 28}
  - {at: head, radius: 50}

anchors:
  head_top: {joint: head, offset: [0, -50]}
  eyes: {joint: head, offset: [0, 0]}
  mouth: {joint: head, offset: [0, 26]}
  feet: {joint: root, offset: [0, 255]}

face:
  joint: head
  radius: 60
  features:
    brow_l: {offset: [-18, -30], size: 10}
    brow_r: {offset: [18, -30], size: 10}
    eye_l: {offset: [-18, -8], size: 12}
    eye_r: {offset: [18, -8], size: 12}
    mouth: {offset: [0, 26], size: 12}

gaze:
  origin: eyes

poses:
  standing_neutral: {elbow_l: -5, elbow_r: 5}
  cartwheel: {elbow_l: 160, elbow_r: -160}

expressions:
  neutral: {}
  dizzy: {eyes: closed, mouth: open}
"""


def kid(old: str = "", new: str = "") -> str:
    """The kid's file, with one piece of it written differently -- a slip to report.

    Args:
        old: Text the file holds exactly once.
        new: What to write in its place.
    """
    if not old:
        return KID
    assert KID.count(old) == 1, old
    return KID.replace(old, new)


def encoded(text: str) -> str:
    """A file's text as MCP's `files` carries it: base64."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")
