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
One report file per crate, plus a manifest tying them together.

This is the *layout* of the output, orthogonal to its schema: both the v2 and
the legacy report can be split, because "which document" and "how many files"
are independent questions. Splitting suits pipelines that pick up one crate's
report at a time; the manifest is what tells them which files belong to the run.

Files are written and overwritten, never deleted: a previous run that validated
other crates leaves its files behind, and the manifest — not the directory
listing — is the authority on what the current run produced.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rocrate_validator.utils import log as logging
from rocrate_validator.utils.io_helpers.output.json.report import build_report, report_meta
from rocrate_validator.utils.versioning import get_version

if TYPE_CHECKING:
    from rocrate_validator.models import BatchCrateEntry, ValidationSession

# set up logging
logger = logging.getLogger(__name__)

# Where the split reports go when no -o prefix is given.
DEFAULT_REPORT_DIR = Path("validation-report")

# Characters kept verbatim in a crate id; everything else becomes an underscore
# so the id is usable as a file name on any platform.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(relative_path: str) -> str:
    """Turn a relative crate path into a flat, file-name-safe id."""
    flattened = relative_path.replace("\\", "/").replace("/", "__")
    return _UNSAFE_IN_FILENAME.sub("_", flattened).strip("_") or "crate"


def crate_ids(entries: list[BatchCrateEntry]) -> dict[str, str]:
    """
    Map each crate path to the id naming its report file.

    The id is the crate path relative to what the crates have in common, so the
    directory structure survives as ``sub__crateA`` instead of collapsing to a
    bare name. With a single crate there is no common prefix to strip — the
    crate *is* the common path — so its own name is used. Ids that collide after
    sanitising get a numeric suffix, in discovery order.
    """
    paths = [entry.path for entry in entries]
    common = ""
    if len(paths) > 1:
        try:
            common = os.path.commonpath(paths) + os.sep
        except (ValueError, TypeError):
            # Mixed local paths and remote URIs, or nothing in common.
            common = ""

    ids: dict[str, str] = {}
    taken: set[str] = set()
    for path in paths:
        relative = path[len(common) :] if common and path.startswith(common) else Path(path).name
        candidate = _sanitize(relative)
        if candidate in taken:
            base, suffix = candidate, 1
            while candidate in taken:
                candidate = f"{base}-{suffix:03d}"
                suffix += 1
        taken.add(candidate)
        ids[path] = candidate
    return ids


def crate_legacy_doc(entry: BatchCrateEntry, validation_settings: dict[str, Any]) -> dict[str, Any]:
    """
    Re-project one crate entry into a self-contained legacy document.

    Not a slice of the batch report: the legacy format has no batch envelope, so
    the crate's outcome is wrapped in the ``meta`` and ``validation_settings``
    that a single-crate legacy report carries at its top level, with
    ``profile_identifiers`` set to the profiles this crate was validated against.
    """
    settings = dict(validation_settings or {})
    # The batch settings describe no single crate, so the URI is filled in per
    # crate here (which also keeps the placeholder the batch settings carry out
    # of the report).
    settings["rocrate_uri"] = entry.path
    settings["profile_identifiers"] = entry.profiles or []
    return {
        "meta": {
            "generated_by": "rocrate-validator",
            "version": get_version(),
        },
        "validation_settings": settings,
        "passed": entry.passed,
        "issues": entry.issues or [],
        "statistics": entry.statistics,
    }


def crate_v2_doc(
    session: ValidationSession,
    entry: BatchCrateEntry,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    """One crate as a standalone v2 report — the same envelope, ``crates`` of one."""
    return build_report(
        session,
        passed=bool(entry.passed),
        verbose=verbose,
        crates=[entry],
        # The whole session's status would be wrong here: a crate that validated
        # cleanly must not be reported as "interrupted" because *another* crate
        # left the run unfinished. Every other field of the block already
        # describes this crate alone; the run's own status is in the manifest.
        status=_entry_session_status(entry),
    )


def _entry_session_status(entry: BatchCrateEntry) -> str:
    """The session status a one-crate report deserves: was this crate processed?"""
    return "completed" if entry.status in ("completed", "failed") else "interrupted"


def resolve_destination(output_dir: Path | None) -> Path:
    """The directory the split reports go to (default ``validation-report/``)."""
    return Path(output_dir) if output_dir is not None else DEFAULT_REPORT_DIR


def _file_name(identifier: str) -> str:
    return f"{identifier}.json"


def manifest(
    session: ValidationSession,
    entries: list[BatchCrateEntry],
    ids: dict[str, str],
    files: dict[str, str],
    *,
    schema: str,
    passed: bool,
) -> dict[str, Any]:
    """The index of the split run: which crate went to which file, and how it fared."""
    return {
        "meta": report_meta(),
        "mode": "single" if len(entries) == 1 else "batch",
        # The status of the run itself, which an empty split run reports nowhere
        # else: with no crates the manifest is the only document written.
        "status": session.status,
        "schema": schema,
        "passed": passed,
        "total_crates": len(entries),
        "completed_crates": sum(1 for entry in entries if entry.status == "completed"),
        "failed_crates": sum(1 for entry in entries if entry.status in ("completed", "failed") and not entry.passed),
        "crates": [
            {
                "id": ids[entry.path],
                "path": entry.path,
                "file": files[entry.path],
                "status": entry.status,
                "passed": entry.passed,
            }
            for entry in entries
        ],
    }


def split_documents(
    session: ValidationSession,
    *,
    schema: str,
    passed: bool,
    verbose: bool = False,
    output_dir: Path | None = None,
) -> tuple[Path, dict[str, dict[str, Any]], str]:
    """
    Build everything a split run writes, without touching the filesystem.

    :returns: the destination directory, a ``{file name: document}`` mapping
        (manifest included) and the name of the manifest file
    """
    entries = session.crates
    directory = resolve_destination(output_dir)
    ids = crate_ids(entries)
    files = {entry.path: _file_name(ids[entry.path]) for entry in entries}

    documents: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if schema == "legacy":
            documents[files[entry.path]] = crate_legacy_doc(entry, session.validation_settings)
        else:
            documents[files[entry.path]] = crate_v2_doc(session, entry, verbose=verbose)

    index_name = _file_name("index")
    documents[index_name] = manifest(session, entries, ids, files, schema=schema, passed=passed)
    return directory, documents, index_name
