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

"""Unit tests of the per-crate report fan-out (ids, destination, documents)."""

from pathlib import Path

from rocrate_validator.models import BatchCrateEntry
from rocrate_validator.utils.io_helpers.output.json.fanout import (
    DEFAULT_REPORT_DIR,
    crate_ids,
    crate_legacy_doc,
    resolve_destination,
)


def _entries(*paths: str) -> list[BatchCrateEntry]:
    return [BatchCrateEntry(path=path, status="completed", passed=True) for path in paths]


def test_crate_ids_keep_the_directory_structure():
    """Crates below the common root keep their sub-path, flattened into the id."""
    ids = crate_ids(_entries("/data/crateA", "/data/sub/crateA", "/data/sub/deep/crateB"))
    assert list(ids.values()) == ["crateA", "sub__crateA", "sub__deep__crateB"]


def test_crate_ids_disambiguate_collisions():
    """Two paths flattening to the same id get a numeric suffix, in order."""
    ids = crate_ids(_entries("/data/x/c", "/data/x__c"))
    assert list(ids.values()) == ["x__c", "x__c-001"]


def test_crate_ids_of_a_single_crate_use_its_name():
    """A lone crate is its own common path, so the relative path would be empty."""
    ids = crate_ids(_entries("/data/sub/crateA"))
    assert list(ids.values()) == ["crateA"]


def test_crate_ids_fall_back_to_the_name_without_a_common_path():
    """Local paths mixed with remote URIs have no common prefix to strip."""
    ids = crate_ids(_entries("/data/crateA", "https://example.org/crates/crateB"))
    assert set(ids.values()) == {"crateA", "crateB"}


def test_resolve_destination_defaults_to_the_report_directory():
    assert resolve_destination(None) == DEFAULT_REPORT_DIR


def test_resolve_destination_returns_the_given_directory():
    """--output-dir is an explicit directory; it is used directly."""
    assert resolve_destination(Path("out")) == Path("out")
    assert resolve_destination(Path("/abs/path/to/reports")) == Path("/abs/path/to/reports")


def test_crate_legacy_doc_is_self_contained():
    """The legacy document carries its own meta and settings, unlike a v2 item."""
    entry = BatchCrateEntry(
        path="/data/crateA",
        status="completed",
        passed=False,
        profiles=["ro-crate-1.1"],
        issues=[{"severity": "REQUIRED"}],
        statistics={"total_checks": 3},
    )
    document = crate_legacy_doc(entry, {"requirement_severity": "REQUIRED", "rocrate_uri": "<property object>"})

    assert sorted(document) == ["issues", "meta", "passed", "statistics", "validation_settings"]
    assert sorted(document["meta"]) == ["generated_by", "version"], "legacy meta stays as it always was"
    assert document["passed"] is False
    assert document["issues"] == entry.issues
    # The batch settings describe no single crate: the URI is filled in per crate.
    assert document["validation_settings"]["rocrate_uri"] == "/data/crateA"
    assert document["validation_settings"]["profile_identifiers"] == ["ro-crate-1.1"]
