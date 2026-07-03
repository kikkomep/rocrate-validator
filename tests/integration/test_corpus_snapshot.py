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
Snapshot tests of the validation results over the crate corpus.

These tests validate every discoverable crate in ``tests/data/crates`` and
compare a per-crate fingerprint (pass/fail + the sorted set of issues) against
a committed snapshot. Their purpose is to catch regressions in validation
results — in particular during changes that must not alter any outcome, such
as the profile/shapes and data-graph caching work.

Two scenarios are covered:

- the whole corpus against the ``ro-crate-1.1`` profile with default severity
  (the homogeneous-batch scenario targeted by the caches);
- the workflow crates against ``workflow-ro-crate`` at ``OPTIONAL`` severity,
  which loads the ``should``/``may`` requirement levels whose SHACL shapes use
  *relative* ``sh:targetNode`` IRIs resolved against the crate ``publicID``
  (the known crate-dependent shapes case the cache key must respect).

To regenerate the snapshot after an intentional behaviour change::

    SNAPSHOT_UPDATE=1 pytest tests/integration/test_corpus_snapshot.py
"""

import json
import os
from pathlib import Path

import pytest

from rocrate_validator import services
from rocrate_validator.models import ValidationCache, ValidationSettings

CURRENT_PATH = Path(__file__).resolve().parent
CRATES_ROOT = (CURRENT_PATH / ".." / "data" / "crates").resolve()
SNAPSHOT_PATH = (CURRENT_PATH / ".." / "data" / "snapshots" / "corpus_fingerprints.json").resolve()

# Crates exercising the publicID-dependent shapes (relative sh:targetNode IRIs
# in the workflow-ro-crate should/may requirement levels).
WRROC_CRATES = ["valid/workflow-roc", "valid/wrroc-paper"]


def _discover_corpus() -> list[Path]:
    crates: list[Path] = []
    for subset in ("valid", "invalid"):
        crates.extend(services.discover_ro_crates(CRATES_ROOT / subset, pattern="*"))
    return sorted(crates)


def _validate_fingerprint(
    crate: Path, profile_identifier: str, requirement_severity: str, cache: ValidationCache | None = None
) -> dict:
    settings = ValidationSettings.parse(
        {
            "rocrate_uri": str(crate),
            "profile_identifier": profile_identifier,
            "requirement_severity": requirement_severity,
            "skip_availability_check": True,
            "disable_remote_crate_download": True,
        }
    )
    result = services.validate(settings, cache=cache)
    # Normalize the (machine-dependent) crate base URI out of the entities so
    # the snapshot is stable across checkouts.
    base = f"file://{crate}"
    issues = sorted(
        "|".join(
            (
                issue.check.identifier,
                issue.severity.name,
                (issue.violatingEntity or "").replace(base, "<crate>"),
            )
        )
        for issue in result.issues
    )
    return {"passed": result.passed(), "issues": issues}


def _corpus_fingerprints(cache: ValidationCache | None = None) -> dict[str, dict]:
    fingerprints: dict[str, dict] = {}
    for crate in _discover_corpus():
        key = f"ro-crate-1.1::{crate.relative_to(CRATES_ROOT)}"
        fingerprints[key] = _validate_fingerprint(crate, "ro-crate-1.1", "REQUIRED", cache=cache)
    for rel in WRROC_CRATES:
        crate = CRATES_ROOT / rel
        key = f"workflow-ro-crate@OPTIONAL::{rel}"
        fingerprints[key] = _validate_fingerprint(crate, "workflow-ro-crate", "OPTIONAL", cache=cache)
    return fingerprints


def test_corpus_results_match_snapshot() -> None:
    """The validation outcome of the whole corpus matches the committed snapshot."""
    actual = _corpus_fingerprints()

    if os.environ.get("SNAPSHOT_UPDATE"):
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SNAPSHOT_PATH.open("w") as f:
            json.dump(actual, f, indent=2, sort_keys=True)
            f.write("\n")
        pytest.skip(f"Snapshot regenerated at {SNAPSHOT_PATH}; review and commit it.")

    assert SNAPSHOT_PATH.exists(), (
        f"Snapshot not found at {SNAPSHOT_PATH}. "
        "Generate it with: SNAPSHOT_UPDATE=1 pytest tests/integration/test_corpus_snapshot.py"
    )
    with SNAPSHOT_PATH.open() as f:
        expected = json.load(f)

    assert set(actual) == set(expected), (
        "Corpus changed: crates added/removed vs the snapshot. "
        f"Only in actual: {sorted(set(actual) - set(expected))}; "
        f"only in snapshot: {sorted(set(expected) - set(actual))}. "
        "If intentional, regenerate with SNAPSHOT_UPDATE=1."
    )
    mismatches = {k: (expected[k], actual[k]) for k in sorted(expected) if actual[k] != expected[k]}
    assert not mismatches, (
        "Validation results diverged from the snapshot for: "
        f"{json.dumps(mismatches, indent=2)}\n"
        "If the change is intentional, regenerate with SNAPSHOT_UPDATE=1."
    )


def test_shared_cache_results_match_snapshot() -> None:
    """Sharing one ValidationCache across the whole corpus must not change any result.

    This is the consistency guarantee for the profiles/shapes cache:
    every crate — including the workflow-ro-crate@OPTIONAL entries
    whose shapes are publicID-dependent — must produce exactly
    the snapshot fingerprint when profiles are reused.
    """
    if os.environ.get("SNAPSHOT_UPDATE"):
        pytest.skip("snapshot regeneration run")
    assert SNAPSHOT_PATH.exists(), (
        f"Snapshot not found at {SNAPSHOT_PATH}. "
        "Generate it with: SNAPSHOT_UPDATE=1 pytest tests/integration/test_corpus_snapshot.py"
    )
    with SNAPSHOT_PATH.open() as f:
        expected = json.load(f)

    cache = ValidationCache()
    actual = _corpus_fingerprints(cache=cache)

    assert cache.info["hits"] > 0, "the shared cache was never hit across the corpus"
    mismatches = {k: (expected.get(k), actual[k]) for k in sorted(actual) if actual[k] != expected.get(k)}
    assert not mismatches, f"Cached validation diverged from the snapshot for: {json.dumps(mismatches, indent=2)}"
