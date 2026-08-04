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

from rocrate_validator.cli.ui.text.validate import format_batch_progress, format_batch_totals
from rocrate_validator.models import (
    BatchCrateEntry,
    BatchValidationResult,
    ValidationSession,
    crate_counts,
    crate_outcome,
)
from rocrate_validator.utils.io_helpers.output.console import Console


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


def test_the_progress_tally_counts_the_three_outcomes_apart():
    """The running tally follows the same taxonomy as every other report of a run."""
    tally = format_batch_progress(passed=12, failed=3, errored=1, remaining=4)

    assert "12 passed" in tally
    assert "3 failed" in tally
    assert "1 errored" in tally, "an errored crate is not a crate that did not conform"
    assert "4 remaining" in tally


def test_the_progress_tally_stays_quiet_when_nothing_errored():
    """On a healthy run a column of zeros would steal room from the bar itself."""
    tally = format_batch_progress(passed=12, failed=3, errored=0, remaining=4)

    assert "errored" not in tally
    assert "3 failed" in tally


def test_an_errored_crate_is_not_tallied_as_a_failure(monkeypatch):
    """The live tally must not fold the two together the way it used to."""
    from rocrate_validator.cli.ui.text import validate as view_module

    recorded: list[dict] = []
    monkeypatch.setattr(view_module, "format_batch_progress", lambda **kwargs: recorded.append(kwargs) or "")

    crates = ["/data/ok", "/data/bad", "/data/broken"]

    def fake_batch(*, settings, rocrate_uris, progress_callback, **kwargs):
        progress_callback(crates[0], 1, 3, "passed", "(0 issues)")
        progress_callback(crates[1], 2, 3, "failed", "(4 issues)")
        progress_callback(crates[2], 3, 3, "error", "unreachable URI")
        return BatchValidationResult(ValidationSession(validation_settings={}, crate_paths=crates))

    view = view_module.BatchValidationCommandView(console=Console())
    view.run_with_progress(fake_batch, settings={}, rocrate_uris=crates)

    assert recorded[-1] == {"passed": 1, "failed": 1, "errored": 1, "remaining": 0}


def test_the_summary_total_names_the_errored_and_pending_crates():
    """The closing line of the summary table follows the same four buckets."""
    entries = [
        BatchCrateEntry(path="/a", status="completed", passed=True),
        BatchCrateEntry(path="/b", status="completed", passed=False),
        BatchCrateEntry(path="/c", status="errored", passed=False, error="unreachable"),
        BatchCrateEntry(path="/d", status="pending"),
    ]
    totals = format_batch_totals(crate_counts(entries))

    assert "Total: 4 crates" in totals
    assert "1 passed" in totals
    assert "1 failed" in totals, "only the invalid crate is a failure"
    assert "1 errored" in totals
    assert "1 pending" in totals


def test_the_summary_total_reads_as_before_on_an_ordinary_run():
    """Nothing errored and nothing left over: the line keeps its two counters."""
    entries = [
        BatchCrateEntry(path="/a", status="completed", passed=True),
        BatchCrateEntry(path="/b", status="completed", passed=False),
    ]
    totals = format_batch_totals(crate_counts(entries))

    assert "Total: 2 crates" in totals
    assert "errored" not in totals
    assert "pending" not in totals


def test_a_resumed_run_opens_its_tally_where_the_session_left_it(monkeypatch, tmp_path):
    """A resume validates the pending crates only: the tally must not restart from zero."""
    from rocrate_validator.cli.ui.text import validate as view_module

    recorded: list[dict] = []
    monkeypatch.setattr(view_module, "format_batch_progress", lambda **kwargs: recorded.append(kwargs) or "")

    crates = ["/data/done-ok", "/data/done-bad", "/data/pending"]

    def fake_batch(*, settings, rocrate_uris, progress_callback, **kwargs):
        # only the pending crate is validated again
        progress_callback(crates[2], 1, 1, "passed", "(0 issues)")
        return BatchValidationResult(ValidationSession(validation_settings={}, crate_paths=crates))

    view = view_module.BatchValidationCommandView(console=Console())
    view.run_with_progress(
        fake_batch,
        settings={},
        rocrate_uris=crates,
        carried_over={"passed_crates": 1, "invalid_crates": 1, "errored_crates": 0},
    )

    assert recorded[0] == {"passed": 1, "failed": 1, "errored": 0, "remaining": 1}, "the tally opens on the session"
    assert recorded[-1] == {"passed": 2, "failed": 1, "errored": 0, "remaining": 0}
