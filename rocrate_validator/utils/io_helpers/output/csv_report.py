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
Raw CSV export of a validation report.

The export is issue-grained: one row per reported issue, with the owning
crate's fields denormalised onto every row. Crates that reported no issue
(passed, or errored before validating) still contribute one row with the
issue columns empty, so the file covers the whole corpus. The flat layout
targets external analysis tools (spreadsheets, pandas, R, ...): a pivot on
``path`` reproduces the per-crate summary, one on ``check_identifier`` the
per-check breakdown.
"""

from __future__ import annotations

import csv

from rocrate_validator.utils.io_helpers.output.text.statistics import (
    common_path_prefix,
    normalise_crate,
    source_below,
)

# Crate-level columns, repeated on every row of the same crate.
_CRATE_FIELDS = [
    "source",
    "crate",
    "path",
    "profiles",
    "status",
    "error",
    "size_bytes",
    "duration_s",
    "total_checks",
    "passed_checks",
    "failed_checks",
    "total_issues",
]

# Issue-level columns, empty when the crate reported no issue.
_ISSUE_FIELDS = [
    "issue_severity",
    "message",
    "violating_entity",
    "violating_property",
    "violating_property_value",
    "check_identifier",
    "check_name",
    "check_severity",
    "requirement_identifier",
    "requirement_name",
    "profile_identifier",
]

#: Column layout of the raw CSV report.
CSV_REPORT_FIELDS = _CRATE_FIELDS + _ISSUE_FIELDS


def write_report_csv(file, crate_dicts: list[dict]) -> None:
    """
    Write the raw CSV report for ``crate_dicts`` (raw crate records, the
    ``BatchCrateEntry.to_dict()`` shape) to the open text ``file``.
    """
    crates = [normalise_crate(c) for c in crate_dicts]
    common_prefix = common_path_prefix([c["path"] for c in crates])
    writer = csv.writer(file)
    writer.writerow(CSV_REPORT_FIELDS)
    for crate in crates:
        crate_columns = _crate_columns(crate, common_prefix)
        if not crate["issues"]:
            writer.writerow(crate_columns + [""] * len(_ISSUE_FIELDS))
            continue
        for issue in crate["issues"]:
            writer.writerow(crate_columns + _issue_columns(issue))


def _crate_columns(crate: dict, common_prefix: str) -> list:
    """The crate-level cells, repeated on every row of the same crate."""
    # An ERROR crate never ran validation: its check counters are unknown,
    # not zero, so the cells are left empty.
    errored = crate["status"] == "ERROR"
    failed_checks = crate["failed_checks"] or max(crate["checks"] - crate["passed_checks"], 0)
    return [
        source_below(crate["path"], common_prefix),
        crate["name"],
        crate["path"],
        ";".join(crate["profiles"]),
        crate["status"],
        crate["error"] or "",
        crate["size_bytes"] if crate["size_bytes"] is not None else "",
        f"{crate['duration']:.3f}" if crate["duration"] is not None else "",
        "" if errored else crate["checks"],
        "" if errored else crate["passed_checks"],
        "" if errored else failed_checks,
        crate["n_issues"],
    ]


def _issue_columns(issue: dict) -> list:
    """The issue-level cells of one serialized issue record."""
    chk = issue.get("check") or {}
    req = chk.get("requirement") or {}
    profile = req.get("profile") or {}
    return [
        issue.get("severity") or "",
        # Multi-line SHACL messages carry the indentation of the Turtle
        # source: normalise the whitespace so each message stays a single
        # tidy cell.
        " ".join((issue.get("message") or "").split()),
        issue.get("violatingEntity") or "",
        issue.get("violatingProperty") or "",
        issue.get("violatingPropertyValue") or "",
        chk.get("identifier") or "",
        chk.get("name") or "",
        chk.get("severity") or "",
        req.get("identifier") or "",
        req.get("name") or "",
        profile.get("identifier") or "",
    ]
