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

"""Tests for the in-memory ``ValidationCache`` (profiles/shapes reuse)."""

from pathlib import Path

from rocrate_validator import services
from rocrate_validator.models import Severity, ValidationCache
from rocrate_validator.utils.paths import get_profiles_path

CRATES_PATH = Path(__file__).resolve().parent.parent / "data" / "crates"
CRATE = str(CRATES_PATH / "valid" / "workflow-roc")


def _settings(**overrides) -> dict:
    settings = {
        "rocrate_uri": CRATE,
        "profile_identifier": "ro-crate-1.1",
        "skip_availability_check": True,
        "disable_remote_crate_download": True,
    }
    settings.update(overrides)
    return settings


def _fingerprint(result) -> tuple:
    return (
        result.passed(),
        sorted((issue.check.identifier, issue.severity.name) for issue in result.issues),
    )


def test_cache_reuses_loaded_profiles():
    """A second validation sharing the cache hits it instead of reloading."""
    cache = ValidationCache()
    first = services.validate(_settings(), cache=cache)
    assert cache.info["misses"] > 0
    assert cache.info["hits"] == 0
    misses_after_first = cache.info["misses"]

    second = services.validate(_settings(), cache=cache)
    assert cache.info["misses"] == misses_after_first, "second run must not reload any profiles"
    assert cache.info["hits"] > 0
    assert _fingerprint(first) == _fingerprint(second)


def test_cached_results_match_uncached():
    """Sharing a cache must not change the validation outcome."""
    uncached = services.validate(_settings())
    cache = ValidationCache()
    cached = services.validate(_settings(), cache=cache)
    assert _fingerprint(uncached) == _fingerprint(cached)


def test_cache_key_isolates_different_parameters():
    """Loads that differ in severity or publicID must not share an entry."""
    cache = ValidationCache()
    profiles_path = get_profiles_path()
    required = cache.get_or_load_profiles(profiles_path, severity=Severity.REQUIRED)
    optional = cache.get_or_load_profiles(profiles_path, severity=Severity.OPTIONAL)
    per_crate = cache.get_or_load_profiles(
        profiles_path, publicID="https://example.org/crate/", severity=Severity.REQUIRED
    )
    assert cache.info["profile_entries"] == 3
    assert cache.info["hits"] == 0
    assert cache.info["misses"] == 3
    assert required and optional and per_crate

    # same parameters -> same (identical) profile objects, no new entry
    again = cache.get_or_load_profiles(profiles_path, severity=Severity.REQUIRED)
    assert cache.info["profile_entries"] == 3
    assert cache.info["hits"] == 1
    assert [id(p) for p in again] == [id(p) for p in required]


def test_cache_returns_defensive_list_copy():
    """Mutating a returned list must not corrupt the cached entry."""
    cache = ValidationCache()
    profiles_path = get_profiles_path()
    first = cache.get_or_load_profiles(profiles_path)
    first.clear()
    second = cache.get_or_load_profiles(profiles_path)
    assert second, "cached entry must survive mutation of previously returned lists"


def test_clear_drops_entries():
    cache = ValidationCache()
    cache.get_or_load_profiles(get_profiles_path())
    assert cache.info["entries"] == 1
    cache.clear()
    assert cache.info["entries"] == 0


def test_data_graph_cache_hits_until_file_changes(tmp_path):
    """The data-graph entry is reused while the source file is unchanged and reloaded when it changes."""
    metadata = tmp_path / "ro-crate-metadata.json"
    metadata.write_text('{"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": []}')
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return object()  # stand-in for the parsed graph

    cache = ValidationCache()
    kwargs = {"metadata_file_path": metadata, "publicID": "https://example.org/crate/"}

    first = cache.get_or_load_data_graph(loader, **kwargs)
    second = cache.get_or_load_data_graph(loader, **kwargs)
    assert calls["n"] == 1, "unchanged file must not be re-parsed"
    assert second is first
    assert cache.info["data_graph_entries"] == 1

    # modify the file: the stamp (mtime_ns, size) changes -> reload
    metadata.write_text('{"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": [{}]}')
    third = cache.get_or_load_data_graph(loader, **kwargs)
    assert calls["n"] == 2, "a modified file must be re-parsed"
    assert third is not first

    # refresh forces a reload even without changes
    cache.get_or_load_data_graph(loader, refresh=True, **kwargs)
    assert calls["n"] == 3


def test_data_graph_not_cached_without_stable_file():
    """Crates without a stable local metadata file (remote/zip/in-memory) are never cached."""
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return object()

    cache = ValidationCache()
    cache.get_or_load_data_graph(loader, metadata_file_path=None, publicID="https://example.org/")
    cache.get_or_load_data_graph(loader, metadata_file_path=None, publicID="https://example.org/")
    assert calls["n"] == 2
    assert cache.info["data_graph_entries"] == 0


def test_data_graph_key_isolates_publicID(tmp_path):
    """The same metadata file parsed under different publicIDs gets separate entries."""
    metadata = tmp_path / "ro-crate-metadata.json"
    metadata.write_text('{"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": []}')
    cache = ValidationCache()
    a = cache.get_or_load_data_graph(object, metadata_file_path=metadata, publicID="https://a.example/")
    b = cache.get_or_load_data_graph(object, metadata_file_path=metadata, publicID="https://b.example/")
    assert a is not b
    assert cache.info["data_graph_entries"] == 2


def test_data_graph_reused_across_validations(tmp_path):
    """Re-validating an unchanged crate through a shared cache reuses the data graph; a change on disk is picked up."""
    import json
    import shutil

    crate = tmp_path / "crate"
    shutil.copytree(CRATES_PATH / "valid" / "workflow-roc", crate)
    cache = ValidationCache()

    first = services.validate(_settings(rocrate_uri=str(crate)), cache=cache)
    assert cache.info["data_graph_entries"] == 1
    hits_before = cache.info["hits"]

    second = services.validate(_settings(rocrate_uri=str(crate)), cache=cache)
    assert cache.info["data_graph_entries"] == 1
    assert cache.info["hits"] > hits_before
    assert _fingerprint(first) == _fingerprint(second)

    # break the crate on disk: the shared cache must not hide the change
    metadata_file = crate / "ro-crate-metadata.json"
    metadata = json.loads(metadata_file.read_text())
    root = next(e for e in metadata["@graph"] if e["@id"] == "./")
    del root["license"]
    metadata_file.write_text(json.dumps(metadata))

    third = services.validate(_settings(rocrate_uri=str(crate)), cache=cache)
    assert _fingerprint(third) != _fingerprint(first), "the modified crate must be re-parsed and re-validated"


def test_profile_cache_lru_eviction():
    """Beyond the bound, the least-recently-used profile entry is evicted."""
    cache = ValidationCache(max_profile_entries=2)
    profiles_path = get_profiles_path()
    cache.get_or_load_profiles(profiles_path, publicID="file:///a/")
    cache.get_or_load_profiles(profiles_path, publicID="file:///b/")
    # Touch "a" so that "b" becomes the least recently used entry.
    cache.get_or_load_profiles(profiles_path, publicID="file:///a/")
    cache.get_or_load_profiles(profiles_path, publicID="file:///c/")

    assert cache.info["profile_entries"] == 2, "the bound must hold"
    assert cache.info["evictions"] == 1

    misses = cache.info["misses"]
    cache.get_or_load_profiles(profiles_path, publicID="file:///a/")
    assert cache.info["misses"] == misses, "the recently-used entry must survive"
    cache.get_or_load_profiles(profiles_path, publicID="file:///b/")
    assert cache.info["misses"] == misses + 1, "the evicted entry must reload"


def test_data_graph_cache_lru_eviction(tmp_path):
    """Beyond the bound, the least-recently-used data graph is evicted."""
    cache = ValidationCache(max_data_graph_entries=1)
    file_a = tmp_path / "a.json"
    file_a.write_text("{}")
    file_b = tmp_path / "b.json"
    file_b.write_text("{}")

    graph_a, graph_b = object(), object()
    assert cache.get_or_load_data_graph(lambda: graph_a, file_a, publicID=None) is graph_a
    assert cache.get_or_load_data_graph(lambda: graph_b, file_b, publicID=None) is graph_b
    assert cache.info["data_graph_entries"] == 1, "the bound must hold"
    assert cache.info["evictions"] == 1

    reloaded = object()
    assert cache.get_or_load_data_graph(lambda: reloaded, file_a, publicID=None) is reloaded, (
        "the evicted graph must be reloaded through the loader"
    )
