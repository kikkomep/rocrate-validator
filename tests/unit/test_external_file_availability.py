"""External file availability is an environment diagnostic, not a finding."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rocrate_validator.rocrate.entity import ROCrateEntity
from rocrate_validator.utils.uri import AvailabilityStatus


@pytest.fixture
def checkers(monkeypatch):
    loaded = []
    for level, filename, class_name in (
        ("should", "4_data_entity_existence", "DataEntityRecommendedChecker"),
        ("should", "5_web_data_entity_metadata", "WebDataEntityRecommendedChecker"),
        ("must", "4_data_entity_metadata", "DataEntityRequiredChecker"),
    ):
        spec = importlib.util.spec_from_file_location(
            filename, f"rocrate_validator/profiles/ro-crate/1.1/{level}/{filename}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, filename, module)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module.logger, "warning", MagicMock())
        loaded.append((object.__new__(getattr(module, class_name)), module.logger.warning))
    return loaded


def run_checks(checkers, identifier):
    context = MagicMock()
    context.settings.metadata_only = False
    context.fail_fast = True
    entity = ROCrateEntity(context.ro_crate.metadata, {"@id": identifier, "@type": "File"})
    context.ro_crate.metadata.get_data_entities.return_value = [] if entity.is_remote() else [entity]
    context.ro_crate.metadata.get_web_data_entities.return_value = [entity] if entity.is_remote() else []
    for checker, _warning in checkers:
        assert checker.check_availability(context) is True
    return context


@pytest.mark.parametrize("authority", ["", "localhost"])
@pytest.mark.parametrize("exists", [True, False])
def test_local_external_file_only_warns_when_missing(checkers, tmp_path, authority, exists):
    path = tmp_path / "external data.csv"
    if exists:
        path.write_text("data", encoding="utf-8")
    identifier = path.as_uri().replace("file://", f"file://{authority}", 1)
    context = run_checks(checkers, identifier)
    context.result.add_issue.assert_not_called()
    local_warning = checkers[0][1]
    if exists:
        local_warning.assert_not_called()
    else:
        assert "was not found on this system" in local_warning.call_args.args[0]


def test_remote_file_does_not_probe_matching_local_path(checkers, tmp_path, monkeypatch):
    path = tmp_path / "data.csv"
    path.write_text("local lookalike", encoding="utf-8")
    stat_call = MagicMock(side_effect=AssertionError("Remote file must not be inspected locally"))
    monkeypatch.setattr(Path, "stat", stat_call)
    context = run_checks(checkers, f"file://gs17r3b10{path}")
    stat_call.assert_not_called()
    context.result.add_issue.assert_not_called()
    assert "points to host 'gs17r3b10'" in checkers[1][1].call_args.args[0]


@pytest.mark.parametrize("failure", ["permissions", "stat"])
def test_local_file_access_failure_is_only_a_warning(checkers, tmp_path, monkeypatch, failure):
    path = tmp_path / "data.csv"
    path.write_text("data", encoding="utf-8")
    if failure == "permissions":
        monkeypatch.setattr("rocrate_validator.utils.uri.os.access", lambda *_args: False)
    else:
        monkeypatch.setattr(Path, "stat", MagicMock(side_effect=PermissionError("Access denied")))
    context = run_checks(checkers, path.as_uri())
    context.result.add_issue.assert_not_called()
    assert "this system" in checkers[0][1].call_args.args[0]


def test_other_unsupported_schemes_still_add_issue(checkers, monkeypatch):
    monkeypatch.setattr(ROCrateEntity, "check_availability", lambda _self: AvailabilityStatus.UNCHECKABLE)
    context = run_checks(checkers, "s3://bucket/data.csv")
    context.result.add_issue.assert_called_once()
