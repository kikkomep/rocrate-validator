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

import pytest

from rocrate_validator.models import BatchSession, ValidationSession
from rocrate_validator.models import batch as batch_module

CRATES_PATH = Path(__file__).resolve().parent.parent / "data" / "crates"
CRATE = str(CRATES_PATH / "valid" / "workflow-roc")
INVALID_CRATE = str(CRATES_PATH / "invalid" / "0_file_descriptor_format")

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


def test_definitions_are_recorded_and_survive_a_round_trip(tmp_path):
    """The issues name their check, so the session has to carry what the names mean."""
    session_file = tmp_path / "session.json"
    with ValidationSession.open(path=session_file, settings=BASE_SETTINGS) as session:
        session.validate(INVALID_CRATE, profile_identifiers="ro-crate-1.1")

    assert session.check_definitions, "a crate that raised issues must have defined their checks"
    assert "ro-crate-1.1" in session.profile_definitions
    assert session.profile_definitions["ro-crate-1.1"]["uri"], "a definition is the whole profile, not just its name"

    stored = json.loads(session_file.read_text())
    loaded = ValidationSession.load(session_file)
    for key, definitions in (
        ("checks", session.check_definitions),
        ("requirements", session.requirement_definitions),
        ("profiles", session.profile_definitions),
    ):
        assert stored[key] == definitions
        assert getattr(loaded, f"{key[:-1]}_definitions") == definitions


def test_the_tables_hold_one_definition_however_many_issues_point_at_it(tmp_path):
    """The whole point: the check is stored once, not once per issue it raised."""
    with ValidationSession.open(path=tmp_path / "s.json", settings=BASE_SETTINGS) as session:
        session.validate(INVALID_CRATE, profile_identifiers="ro-crate-1.1")

    issues = session.crates[0].issues or []
    assert issues, "the crate must have raised issues for this test to mean anything"
    assert all(isinstance(i["check"], str) for i in issues), "an issue names its check"
    assert len(session.check_definitions) <= len({i["check"] for i in issues})
    # every reference resolves, and resolving restores a self-contained issue
    inlined = session.inlined_issues(issues)
    assert [i["check"]["identifier"] for i in inlined] == [i["check"] for i in issues]
    assert all(isinstance(i["check"]["requirement"]["profile"], dict) for i in inlined)


def _saved_session(path: Path) -> ValidationSession:
    """A session already persisted once, so a further save overwrites a valid file."""
    session = ValidationSession(validation_settings=BASE_SETTINGS, crate_paths=[CRATE], session_path=path)
    session.save()
    return session


def test_save_leaves_the_previous_file_intact_when_serialisation_fails(tmp_path, monkeypatch):
    session_file = tmp_path / "s.json"
    session = _saved_session(session_file)
    intact = session_file.read_text()

    def exploding_dumps(*_args, **_kwargs):
        raise RuntimeError("serialisation blew up halfway")

    monkeypatch.setattr(batch_module.json, "dumps", exploding_dumps)
    with pytest.raises(RuntimeError):
        session.save()

    assert session_file.read_text() == intact, "a failed save must not touch the previous session"
    assert not list(tmp_path.glob("*.tmp")), "the temporary file must not be left behind"


def test_save_is_never_observed_partial(tmp_path, monkeypatch):
    session_file = tmp_path / "s.json"
    session = _saved_session(session_file)
    previous = json.loads(session_file.read_text())

    real_replace = Path.replace
    observed = []

    def observing_replace(self, target):
        # the instant before publication: the new session is written whole to
        # the temporary file, and the target must still hold the previous one
        observed.append((json.loads(self.read_text()), json.loads(Path(target).read_text())))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", observing_replace)
    session.save()

    assert len(observed) == 1
    staged, published = observed[0]
    assert published == previous, "the target went through an intermediate state"
    assert staged != previous, "the staged file is not the new session"
    assert json.loads(session_file.read_text()) == staged, "the staged session was not published"
    assert not list(tmp_path.glob("*.tmp")), "the temporary file must not be left behind"
