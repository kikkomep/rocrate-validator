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
Projection of a :class:`ValidationSession` into the ``v2`` JSON report.

The report has the same shape whether one crate or a thousand were validated:
a single crate is simply a session with one entry, so ``crates`` is always a
list and the only difference is ``session.mode``. Everything is projected from
the persisted :class:`BatchCrateEntry` records, which are complete even for a
resumed session, so the report never depends on live validation objects.

The session block deliberately carries no timestamps: the *bookkeeping* of when
a session started and was last touched belongs to the session file, not to a
report that describes an outcome. Timings of the validation itself remain
available under ``statistics``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rocrate_validator.constants import REPORT_SCHEMA_VERSION
from rocrate_validator.models.outcome import crate_counts
from rocrate_validator.models.result import CustomEncoder
from rocrate_validator.utils import log as logging
from rocrate_validator.utils.versioning import get_version

if TYPE_CHECKING:
    from rocrate_validator.models import BatchCrateEntry, ValidationSession

# set up logging
logger = logging.getLogger(__name__)

# Statistics counters summed across crates. Percentages and identifier lists are
# deliberately not aggregated: they describe a single validation run and adding
# them up would produce numbers that look meaningful but are not.
_SUMMABLE_STATISTICS = (
    "total_requirements",
    "total_passed_requirements",
    "total_failed_requirements",
    "total_checks",
    "total_passed_checks",
    "total_failed_checks",
)

# Statistics sub-structures listing every requirement/check identifier one by
# one. They dwarf the rest of the report, so they are reported only on demand —
# the headline counters stay available either way.
_DETAILED_STATISTICS = (
    "requirements",
    "checks",
    "passed_requirements",
    "failed_requirements",
    "passed_checks",
    "failed_checks",
)


def dump_json(data: dict[str, Any], stream) -> None:
    """
    Write a report straight to the stream, bypassing the Rich console.

    The reports are data, not a rendering: going through a console would make
    their bytes depend on the terminal width and colour support.
    """
    stream.write(json.dumps(data, indent=4, cls=CustomEncoder))
    stream.write("\n")


def report_meta() -> dict[str, str]:
    """The ``meta`` block: what produced the report, and to which schema."""
    return {
        "generated_by": "rocrate-validator",
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "rocrate_validator_version": get_version(),
    }


def issue_profile(issue: dict[str, Any]) -> str | None:
    """The identifier of the profile owning the check that raised ``issue``."""
    check = issue.get("check") or {}
    requirement = check.get("requirement") or {}
    profile = requirement.get("profile") or {}
    return profile.get("identifier")


def results_by_profile(entry: BatchCrateEntry) -> dict[str, dict[str, Any]]:
    """
    The crate's issues bucketed per profile.

    Seeded from the profiles the crate was *validated against*, so a profile
    that raised no issue still appears with an empty list — bucketing the issues
    alone would silently drop every profile that passed. Profiles met only
    through inheritance are added as they are encountered.
    """
    buckets: dict[str, dict[str, Any]] = {profile: {"issues": []} for profile in entry.profiles or []}
    for issue in entry.issues or []:
        identifier = issue_profile(issue)
        if identifier is None:
            continue
        buckets.setdefault(identifier, {"issues": []})["issues"].append(issue)
    return buckets


def crate_entry(entry: BatchCrateEntry, *, verbose: bool = False) -> dict[str, Any]:
    """
    Project one crate entry into its ``crates[]`` item.

    ``path`` is the identifying key (``name`` is a convenience derived from it),
    matching both the persisted entry and the ``path``/``crate`` columns of the
    CSV report, where ``crate`` means the crate *name*.
    """
    item: dict[str, Any] = {
        "path": entry.path,
        "name": Path(entry.path).name,
        "size_bytes": entry.size_bytes,
        "status": entry.status,
        "passed": entry.passed,
        "profiles": entry.profiles or [],
        "duration": entry.duration,
        "error": entry.error,
        "issues": entry.issues or [],
        "statistics": crate_statistics(entry, verbose=verbose),
    }
    if verbose:
        item["results_by_profile"] = results_by_profile(entry)
    return item


def crate_statistics(entry: BatchCrateEntry, *, verbose: bool = False) -> dict[str, Any] | None:
    """The crate's statistics, reduced to the headline counters unless verbose."""
    if not entry.statistics:
        return None
    if verbose:
        return entry.statistics
    return {key: value for key, value in entry.statistics.items() if key not in _DETAILED_STATISTICS}


def aggregate_statistics(entries: list[BatchCrateEntry]) -> dict[str, Any]:
    """
    Sum the per-crate statistics into the report-level ``statistics`` block.

    Crates that never produced statistics — those that errored out before
    validating — are counted explicitly: summing them silently would understate
    every total without any trace in the report.
    """
    with_statistics = [entry.statistics for entry in entries if entry.statistics]
    aggregated: dict[str, Any] = {
        "crates": len(entries),
        "crates_with_statistics": len(with_statistics),
        "crates_without_statistics": len(entries) - len(with_statistics),
    }

    profiles: list[str] = []
    for statistics in with_statistics:
        for profile in statistics.get("profiles") or []:
            if profile not in profiles:
                profiles.append(profile)
    aggregated["profiles"] = sorted(profiles)

    for key in _SUMMABLE_STATISTICS:
        aggregated[key] = sum(int(statistics.get(key) or 0) for statistics in with_statistics)

    by_severity: dict[str, int] = {}
    for statistics in with_statistics:
        for severity, count in (statistics.get("total_checks_by_severity") or {}).items():
            by_severity[severity] = by_severity.get(severity, 0) + int(count or 0)
    aggregated["total_checks_by_severity"] = by_severity

    # Wall-clock of the run is not the sum of the per-crate durations once the
    # validation is parallel, so this is reported as what it is: validation time.
    aggregated["total_validation_time"] = sum(float(entry.duration or 0.0) for entry in entries)
    return aggregated


def build_report(
    session: ValidationSession,
    *,
    passed: bool,
    verbose: bool = False,
    crates: list[BatchCrateEntry] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Build the ``v2`` report of a session.

    :param passed: the overall outcome, decided by the caller (a batch is
        passed only once every crate completed, which the session alone cannot
        tell apart from a partial run)
    :param crates: the entries to report on; defaults to the whole session
    :param status: overrides the session status. Every other field of the
        ``session`` block is computed from ``crates``, so a caller reporting on
        a *subset* must override the status too, or the document would describe
        its subset everywhere but there. Defaults to the session's own status.
    """
    entries = session.crates if crates is None else crates
    return {
        "meta": report_meta(),
        "session": {
            "mode": "single" if len(entries) == 1 else "batch",
            "status": session.status if status is None else status,
            **crate_counts(entries),
        },
        "validation_settings": validation_settings(session),
        "passed": passed,
        "statistics": aggregate_statistics(entries),
        "crates": [crate_entry(entry, verbose=verbose) for entry in entries],
    }


def validation_settings(session: ValidationSession) -> dict[str, Any]:
    """
    The criteria the crates were validated against, in a single block.

    The persisted settings are a full dump of :class:`ValidationSettings`,
    including local absolute paths and internal flags; the report exposes the
    curated subset that describes *what was validated how*, plus the profile
    resolution options (kept apart in the session file for resume purposes).
    """
    settings = session.validation_settings or {}
    reported = {
        key: settings[key]
        for key in (
            "requirement_severity",
            "metadata_only",
            "abort_on_first",
            "enable_profile_inheritance",
            "skip_checks",
        )
        if key in settings
    }
    reported["profile_identifiers"] = session.profile_identifiers or []
    reported["no_auto_profile"] = session.no_auto_profile
    reported["requirement_severity_only"] = session.requirement_severity_only
    return reported
