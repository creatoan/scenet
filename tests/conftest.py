"""Hypothesis profiles for the property tests.

A property failure has to replay identically, on a laptop and in CI alike, so the
default profile is **derandomized everywhere**: Hypothesis seeds each test from a hash
of its own source, and every run tries the same examples. Exploring with fresh seeds is
opt-in, and runs weekly rather than on every pull request.

Choose a profile with `HYPOTHESIS_PROFILE`:

- `fixed`, the default: derandomized, 20 examples, no deadline and no database.
- `ci`: the same as `fixed`. Registered under this name because Hypothesis loads a
  built-in `ci` profile of its own whenever `CI` is set, and that one runs 100 examples,
  which is too many for a compiler at around 50 ms a panel.
- `explore`: random seeds, 300 examples, and a database that remembers what failed.

A failure found under `explore` is pinned as an `@example(...)` on the test, so the
fixed run covers it from then on. `docs/maintainer/testing.md` has the details.
"""

import os
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis.database import DirectoryBasedExampleDatabase

_FIXED = settings(
    derandomize=True,
    database=None,
    # Timing on Windows runners varies too much for a per-example deadline to mean
    # anything; a slow example is not a wrong one.
    deadline=None,
    print_blob=True,
    max_examples=20,
    # Compiling a panel is genuinely slow next to what Hypothesis expects of a test.
    # Every other health check stays on: a strategy that filters too much is a bug.
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile("fixed", _FIXED)
settings.register_profile("ci", _FIXED)
settings.register_profile(
    "explore",
    settings(
        _FIXED,
        derandomize=False,
        max_examples=300,
        database=DirectoryBasedExampleDatabase(Path(".hypothesis") / "examples"),
    ),
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "fixed"))
