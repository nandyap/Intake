"""Tests.

Stub mode is permitted here regardless of environment. Real agents are
the default everywhere else, but the suite must be runnable offline and
in CI, where no Compass key exists and 14 model calls per run would be
neither cheap nor deterministic.

Set explicitly rather than inherited, so a missing key in a *deployment*
still fails loudly while a missing key in a *test run* does not.

``COMPASS_API_KEY`` is left untouched: this permits running without a
provider, it does not disable one. ``compass_check`` still needs the real
key and still gets it.
"""

import os

os.environ.setdefault("ALLOW_STUB_AGENTS", "true")
