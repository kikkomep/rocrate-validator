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
    assert cache.info == {"entries": 3, "hits": 0, "misses": 3}
    assert required and optional and per_crate

    # same parameters -> same (identical) profile objects, no new entry
    again = cache.get_or_load_profiles(profiles_path, severity=Severity.REQUIRED)
    assert cache.info["entries"] == 3
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
