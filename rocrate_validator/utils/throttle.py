# Copyright (c) 2024-2026 CRS4
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""How often a long run is worth writing its progress to disk."""

from __future__ import annotations

import time

# Share of the wall time a run may spend writing its progress, and the floor
# below which spacing out a save costs more safety than it buys back.
SAVE_OVERHEAD_BUDGET = 0.02
MIN_SAVE_INTERVAL_SECONDS = 2.0


class SaveThrottle:
    """
    Spacing policy for the progress saves of a long run.

    A *fixed* interval ages badly when the whole state is rewritten on every
    save: the cost of one save grows with the number of entries recorded, and
    the share of the run spent saving grows with it — it reaches tens of
    percent on batches of a few thousand crates. It is also not a number anyone
    could pick sensibly, since the right value depends on how big the state
    will get, which is not known in advance.

    So the interval is derived from what the last save actually cost: a save is
    followed by roughly ``cost / budget`` seconds of silence, which holds the
    overhead near ``budget`` however large the state grows. What degrades on a
    long run is then the *freshness* of the file — a bounded, recoverable loss
    of the last few entries — rather than the run itself.
    """

    def __init__(self, budget: float = SAVE_OVERHEAD_BUDGET, minimum: float = MIN_SAVE_INTERVAL_SECONDS):
        self._budget = budget
        self._minimum = minimum
        self._interval = minimum
        # nothing saved yet: the first entry is worth persisting straight away
        self._last_save: float | None = None

    @property
    def interval(self) -> float:
        """Seconds of silence the last save bought."""
        return self._interval

    def due(self) -> bool:
        """True when enough time has passed since the last save."""
        if self._last_save is None:
            return True
        return time.monotonic() - self._last_save >= self._interval

    def record(self, cost: float) -> None:
        """Take note of a save that took ``cost`` seconds, and space out the next one."""
        self._interval = max(self._minimum, cost / self._budget)
        self._last_save = time.monotonic()
