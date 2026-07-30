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
Unit tests of the projection of a session into the JSON report.

These cover the cases that are hard to reach through the CLI — a profile that
raised no issue, a crate that errored before producing any statistics, a batch
that matched nothing — and where a wrong answer is silent rather than loud.
"""

from rocrate_validator.models import BatchCrateEntry, BatchSession, BatchValidationResult
from rocrate_validator.utils.io_helpers.output.json.report import (
    aggregate_statistics,
    build_report,
    crate_entry,
    results_by_profile,
)


def _issue(profile: str) -> dict:
    """A serialized issue attributed to ``profile``, as the reports carry it."""
    return {
        "severity": "REQUIRED",
        "message": "something is off",
        "check": {"identifier": f"{profile}_1.1", "requirement": {"profile": {"identifier": profile}}},
    }


def test_results_by_profile_keeps_a_profile_that_raised_no_issue():
    """Bucketing the issues alone would silently drop every profile that passed."""
    entry = BatchCrateEntry(
        path="/data/crateA",
        status="completed",
        passed=False,
        profiles=["ro-crate-1.1", "workflow-ro-crate"],
        issues=[_issue("ro-crate-1.1")],
    )
    buckets = results_by_profile(entry)

    assert sorted(buckets) == ["ro-crate-1.1", "workflow-ro-crate"]
    assert buckets["workflow-ro-crate"] == {"issues": []}
    assert buckets["ro-crate-1.1"]["issues"] == entry.issues


def test_results_by_profile_adds_inherited_profiles_from_the_issues():
    """Profile inheritance can attribute an issue to a profile not asked for."""
    entry = BatchCrateEntry(
        path="/data/crateA",
        status="completed",
        passed=False,
        profiles=["workflow-ro-crate"],
        issues=[_issue("ro-crate-1.1")],
    )
    buckets = results_by_profile(entry)

    assert sorted(buckets) == ["ro-crate-1.1", "workflow-ro-crate"]
    assert buckets["workflow-ro-crate"] == {"issues": []}


def test_crate_statistics_drop_the_detailed_lists_unless_verbose():
    """The per-check identifier lists dwarf the report, so they are opt-in."""
    entry = BatchCrateEntry(
        path="/data/crateA",
        status="completed",
        passed=True,
        profiles=["ro-crate-1.1"],
        statistics={"total_checks": 37, "checks": {"identifiers": ["a", "b"]}, "requirements": {"count": 15}},
    )
    assert crate_entry(entry)["statistics"] == {"total_checks": 37}
    assert crate_entry(entry, verbose=True)["statistics"] == entry.statistics


def test_aggregate_statistics_counts_the_crates_without_statistics():
    """A crate that errored out has no statistics: summing it in would understate the totals."""
    entries = [
        BatchCrateEntry(
            path="/data/ok",
            status="completed",
            passed=True,
            duration=1.5,
            statistics={
                "total_checks": 10,
                "total_passed_checks": 10,
                "total_checks_by_severity": {"REQUIRED": 10},
                "profiles": ["ro-crate-1.1"],
            },
        ),
        BatchCrateEntry(path="/data/broken", status="failed", passed=False, error="boom", duration=0.1),
    ]
    aggregated = aggregate_statistics(entries)

    assert aggregated["crates"] == 2
    assert aggregated["crates_with_statistics"] == 1
    assert aggregated["crates_without_statistics"] == 1
    # The totals cover the crate that produced statistics, and say so above.
    assert aggregated["total_checks"] == 10
    assert aggregated["total_checks_by_severity"] == {"REQUIRED": 10}
    assert aggregated["profiles"] == ["ro-crate-1.1"]
    # Durations are known even for a crate that never validated.
    assert aggregated["total_validation_time"] == 1.6


def test_report_of_a_batch_that_matched_nothing():
    """An empty batch is a well-formed report, not an absent one."""
    session = BatchSession(validation_settings={}, crate_paths=[])
    session.status = "completed"
    report = build_report(session, passed=BatchValidationResult(session).passed())

    assert report["crates"] == []
    assert report["passed"] is True, "nothing was validated, so nothing failed"
    assert report["session"]["mode"] == "batch"
    assert report["session"]["total_crates"] == 0
    assert report["statistics"]["crates"] == 0
    assert report["statistics"]["crates_with_statistics"] == 0
    assert report["statistics"]["total_checks"] == 0


def test_report_of_a_session_of_one_is_flagged_single():
    """The mode follows the number of crates reported on, not the command used."""
    session = BatchSession(validation_settings={}, crate_paths=["/data/crateA"])
    session.crates[0].status = "completed"
    session.crates[0].passed = True

    assert build_report(session, passed=True)["session"]["mode"] == "single"
