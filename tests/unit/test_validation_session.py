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

"""Tests for the programmatic ValidationSession API (persisted history + owned cache)."""

import json
from pathlib import Path

from rocrate_validator.models import BatchSession, ValidationSession

CRATES_PATH = Path(__file__).resolve().parent.parent / "data" / "crates"
CRATE = str(CRATES_PATH / "valid" / "workflow-roc")

BASE_SETTINGS = {"skip_availability_check": True, "disable_remote_crate_download": True}


def test_batch_session_is_validation_session_alias():
    assert BatchSession is ValidationSession


def test_session_records_and_persists_single_crate(tmp_path):
    session_file = tmp_path / "session.json"
    with ValidationSession.open(path=session_file, settings=BASE_SETTINGS) as session:
        outcome = session.validate(CRATE, profile_identifiers="ro-crate-1.1")
        assert outcome is not None
        assert [path for path, _ in outcome] == [CRATE]

    assert session.mode == "single"
    assert session.status == "completed"
    assert session.total_crates == session.processed_crates == 1
    assert session.pending_crates == session.errored_crates == 0

    data = json.loads(session_file.read_text())
    assert data["session"]["mode"] == "single"
    assert data["session"]["status"] == "completed"
    assert [c["path"] for c in data["crates"]] == [CRATE]
    assert data["crates"][0]["profiles"] == ["ro-crate-1.1"]

    loaded = ValidationSession.load(session_file)
    assert loaded.total_crates == 1
    assert loaded.cache.info["entries"] == 0, "the cache must never be persisted"


def test_session_default_path_lands_in_history_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    from rocrate_validator.utils.paths import get_user_sessions_dir

    with ValidationSession.open(settings=BASE_SETTINGS) as session:
        session.validate(CRATE, profile_identifiers="ro-crate-1.1")
    assert session.session_path is not None
    assert session.session_path.parent == get_user_sessions_dir()
    assert session.session_path.exists(), "the session must appear in the history browsed by `sessions list`"


def test_revalidation_overwrites_entry(tmp_path):
    with ValidationSession.open(path=tmp_path / "s.json", settings=BASE_SETTINGS) as session:
        session.validate(CRATE, profile_identifiers="ro-crate-1.1")
        first_entry = session._find_entry(CRATE)
        assert first_entry is not None
        session.validate(CRATE, profile_identifiers="ro-crate-1.1")

    assert session.total_crates == 1, "re-validation must overwrite, not append"
    assert session.processed_crates == 1
    assert session.pending_crates == 0


def test_session_cache_reused_across_validations(tmp_path):
    with ValidationSession.open(path=tmp_path / "s.json", settings=BASE_SETTINGS) as session:
        session.validate(CRATE, profile_identifiers="ro-crate-1.1")
        misses_after_first = session.cache.info["misses"]
        session.validate(CRATE, profile_identifiers="ro-crate-1.1")
        assert session.cache.info["misses"] == misses_after_first, "second validation must fully hit the session cache"
        assert session.cache.info["hits"] > 0


def test_session_interrupted_when_left_with_pending_entries(tmp_path):
    session_file = tmp_path / "s.json"
    try:
        with ValidationSession.open(path=session_file, settings=BASE_SETTINGS) as session:
            session.validate(CRATE, profile_identifiers="ro-crate-1.1")
            session._ensure_entry(str(CRATES_PATH / "valid" / "minimal-isa-ro-crate"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    data = json.loads(session_file.read_text())
    assert data["session"]["status"] == "interrupted"


def test_session_completed_despite_exception_when_all_entries_done(tmp_path):
    session_file = tmp_path / "s.json"
    try:
        with ValidationSession.open(path=session_file, settings=BASE_SETTINGS) as session:
            session.validate(CRATE, profile_identifiers="ro-crate-1.1")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    data = json.loads(session_file.read_text())
    assert data["session"]["status"] == "completed", "recorded outcomes stay valid even if the with-block raised"


def test_session_records_validation_errors(tmp_path):
    outcome = None
    with ValidationSession.open(path=tmp_path / "s.json", settings=BASE_SETTINGS) as session:
        outcome = session.validate(str(tmp_path / "missing-crate"), profile_identifiers="ro-crate-1.1")
    assert outcome is None
    entry = session._find_entry(str(tmp_path / "missing-crate"))
    assert entry is not None
    assert entry.status == "errored"
    assert entry.error


def test_session_level_profile_defaults(tmp_path):
    with ValidationSession.open(path=tmp_path / "s.json", settings=BASE_SETTINGS) as session:
        session.profile_identifiers = ["ro-crate-1.1"]
        session.validate(CRATE)  # no explicit profile: session default applies
    entry = session._find_entry(CRATE)
    assert entry is not None
    assert entry.profiles == ["ro-crate-1.1"]
