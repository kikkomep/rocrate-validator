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

"""Tests for when a batch run puts its state on disk, as opposed to what it puts there."""

import json
from pathlib import Path

import pytest

from rocrate_validator import services
from rocrate_validator.models import ValidationSettings

CRATES_PATH = Path(__file__).resolve().parent.parent / "data" / "crates"
CRATES = [str(CRATES_PATH / "valid" / "workflow-roc"), str(CRATES_PATH / "valid" / "sort-and-change-case")]

BASE_SETTINGS = {"skip_availability_check": True, "disable_remote_crate_download": True}


def _settings() -> ValidationSettings:
    return ValidationSettings.parse({**BASE_SETTINGS, "rocrate_uri": CRATES[0]})


def test_session_file_exists_before_the_first_crate(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    seen_when_validating = []

    def spy(*args, **kwargs):
        seen_when_validating.append(state_path.exists())

    monkeypatch.setattr(services, "_validate_one_in_batch", spy)
    services.batch_validate(_settings(), CRATES, state_path=state_path, ephemeral=False)

    assert seen_when_validating == [True, True], "the session must be on disk before any crate is validated"


def test_session_is_saved_when_the_batch_loop_raises(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"

    def explode_on_second(settings, session, crate_path, idx, *args, **kwargs):
        if idx == 1:
            raise RuntimeError("something the loop does not handle")
        session.add_results(crate_path, [], duration=0.0)

    monkeypatch.setattr(services, "_validate_one_in_batch", explode_on_second)
    with pytest.raises(RuntimeError):
        services.batch_validate(_settings(), CRATES, state_path=state_path, ephemeral=False)

    data = json.loads(state_path.read_text())
    assert data["session"]["status"] == "interrupted"
    statuses = {c["path"]: c["status"] for c in data["crates"]}
    assert statuses[CRATES[0]] == "completed", "the crate validated before the failure must survive it"
    assert statuses[CRATES[1]] == "pending"


def test_completed_ephemeral_run_state_is_still_removed(tmp_path, monkeypatch):
    """The initial save must not leave a run-state behind once the run completes."""
    state_path = tmp_path / "run-state.json"

    def record(settings, session, crate_path, idx, *args, **kwargs):
        session.add_results(crate_path, [], duration=0.0)

    monkeypatch.setattr(services, "_validate_one_in_batch", record)
    services.batch_validate(_settings(), CRATES, state_path=state_path, ephemeral=True)

    assert not state_path.exists()
