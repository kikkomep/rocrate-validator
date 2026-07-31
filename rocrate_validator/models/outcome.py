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

"""
How a validated crate is classified, and how the classification is counted.

Kept in a module of its own, with no dependency of its own, so that every
layer — the session model, the JSON report, the session list and the text
statistics — applies the *same* rule instead of each re-deriving it from
``status`` and ``passed``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rocrate_validator.models.batch import BatchCrateEntry


# Crate statuses that mean the crate has an outcome, whatever it is: everything
# else is still to be processed. `errored` is a crate the validation could not
# run on at all, as opposed to one that ran and did not conform (`completed`
# with `passed` false) — see `crate_outcome()`.
PROCESSED_STATUSES = ("completed", "errored")


def crate_outcome(status: str | None, passed: bool | None) -> str:
    """
    The bucket a crate falls into, from its status and verdict.

    * ``passed`` — validated and conformant;
    * ``invalid`` — validated, does not conform (it has issues);
    * ``errored`` — validation could not run (a non-RO-Crate input, an
      unreachable URI, …): the crate has an error message, no verdict on
      conformance;
    * ``pending`` — not processed (yet).

    The four are mutually exclusive and cover every entry, which is what lets
    the session counters always sum to the total.
    """
    if status == "errored":
        return "errored"
    if status != "completed":
        return "pending"
    return "passed" if passed else "invalid"


def crate_counts(entries: Iterable[BatchCrateEntry]) -> dict[str, int]:
    """
    How many crates fall in each bucket, plus their total.

    Reported as five explicit counters — ``total_crates`` and one per
    :func:`crate_outcome` bucket — so that no consumer has to obtain one by
    subtracting the others, and the four buckets always sum to the total (an
    invariant worth asserting on).
    """
    counts = {
        "total_crates": 0,
        "passed_crates": 0,
        "invalid_crates": 0,
        "errored_crates": 0,
        "pending_crates": 0,
    }
    for entry in entries:
        counts["total_crates"] += 1
        counts[f"{crate_outcome(entry.status, entry.passed)}_crates"] += 1
    return counts
