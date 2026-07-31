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

"""Unit tests of the crate outcome taxonomy and of the counters derived from it."""

import json

import pytest

from rocrate_validator.models import BatchCrateEntry, ValidationSession, crate_counts, crate_outcome


@pytest.mark.parametrize(
    ("status", "passed", "expected"),
    [
        ("completed", True, "passed"),
        ("completed", False, "invalid"),
        ("completed", None, "invalid"),
        ("errored", False, "errored"),
        ("pending", None, "pending"),
        ("in_progress", None, "pending"),
        (None, None, "pending"),
    ],
)
def test_crate_outcome_classification(status, passed, expected):
    assert crate_outcome(status, passed) == expected


def test_an_errored_crate_is_not_an_invalid_one():
    """The distinction the counters exist for: no verdict is not a negative verdict."""
    assert crate_outcome("errored", False) != crate_outcome("completed", False)


def _mixed_session() -> ValidationSession:
    """One crate of each kind, so every counter is exercised at once."""
    session = ValidationSession(validation_settings={}, crate_paths=[])
    session.crates = [
        BatchCrateEntry(path="/data/ok", status="completed", passed=True),
        BatchCrateEntry(path="/data/invalid", status="completed", passed=False, issues=[{"severity": "REQUIRED"}]),
        BatchCrateEntry(path="/data/broken", status="errored", passed=False, error="Not an RO-Crate"),
        BatchCrateEntry(path="/data/never", status="pending"),
    ]
    return session


def test_the_buckets_sum_to_the_total():
    """The invariant that makes the counters readable without arithmetic."""
    counts = crate_counts(_mixed_session().crates)

    assert counts == {
        "total_crates": 4,
        "passed_crates": 1,
        "invalid_crates": 1,
        "errored_crates": 1,
        "pending_crates": 1,
    }
    assert counts["total_crates"] == sum(
        counts[bucket] for bucket in ("passed_crates", "invalid_crates", "errored_crates", "pending_crates")
    )


def test_session_counters_follow_the_entries():
    """The counters are derived, so an entry edited in place cannot desynchronise them."""
    session = _mixed_session()
    assert (session.passed_crates, session.invalid_crates, session.errored_crates) == (1, 1, 1)
    assert session.processed_crates == 3
    assert not session.is_completed()

    session.crates[-1].status = "completed"
    session.crates[-1].passed = True

    assert session.passed_crates == 2
    assert session.pending_crates == 0
    assert session.is_completed(), "an errored crate does not hold the session back: it was processed"


def test_counters_are_written_to_the_session_file(tmp_path):
    session = _mixed_session()
    session.session_path = tmp_path / "session.json"
    session.save()

    block = json.loads((tmp_path / "session.json").read_text())["session"]
    assert block["total_crates"] == 4
    assert block["errored_crates"] == 1
    assert block["invalid_crates"] == 1

    # ...and are not read back from it: the entries are the only source.
    reloaded = ValidationSession.load(tmp_path / "session.json")
    assert reloaded.counts == session.counts


def test_a_revalidated_crate_is_not_counted_twice():
    """Overwriting an outcome used to require undoing the previous increments."""
    session = _mixed_session()
    entry = session._ensure_entry("/data/invalid")

    assert entry.status == "pending", "the previous outcome is dropped"
    assert session.invalid_crates == 0
    assert session.pending_crates == 2
    assert session.total_crates == 4, "re-validation must not append a second entry"
