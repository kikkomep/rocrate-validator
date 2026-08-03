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

import csv
import io
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from pytest import fixture, mark

from rocrate_validator import services
from rocrate_validator.cli.main import cli
from rocrate_validator.models import BatchCrateEntry, BatchSession, BatchValidationResult, ValidationSettings
from rocrate_validator.requirements.python import PyFunctionCheck
from rocrate_validator.requirements.shacl.checks import SHACLCheck
from rocrate_validator.services import discover_ro_crates
from rocrate_validator.utils import log as logging
from rocrate_validator.utils.io_helpers.output.csv_report import CSV_REPORT_FIELDS
from rocrate_validator.utils.paths import get_user_runs_dir, get_user_sessions_dir
from rocrate_validator.utils.versioning import get_version
from tests.conftest import SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER
from tests.ro_crates import CRATES_DATA_PATH, InvalidFileDescriptor, ValidROC

# set up logging
logger = logging.getLogger(__name__)


@fixture
def cli_runner() -> CliRunner:
    # Force a wide terminal: the CLI renders output through Rich, which wraps
    # and truncates tables/panels to the terminal width (defaulting to 80
    # columns when stdout is captured). Pinning COLUMNS keeps the rendered
    # output deterministic regardless of the environment's actual width.
    return CliRunner(env={"COLUMNS": "200"})


def test_version(cli_runner: CliRunner):
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert get_version() in result.output


def test_validate_subcmd_invalid_rocrate1(cli_runner: CliRunner):
    result = cli_runner.invoke(
        cli,
        ["validate", str(InvalidFileDescriptor().invalid_json_format), "--verbose", "--no-paging", "-p", "ro-crate"],
    )
    logger.error(result.output)
    assert result.exit_code == 1


def test_validate_subcmd_valid_local_folder_rocrate(cli_runner: CliRunner):
    result = cli_runner.invoke(cli, ["validate", str(ValidROC().wrroc_paper_long_date), "--verbose", "--no-paging"])
    assert result.exit_code == 0
    assert re.search(r"RO-Crate.*is a valid", result.output)


def test_validate_subcmd_valid_remote_rocrate(cli_runner: CliRunner):
    result = cli_runner.invoke(
        cli,
        [
            "validate",
            str(ValidROC().sort_and_change_remote),
            "--verbose",
            "--no-paging",
            "--skip-checks",
            SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER,
        ],
    )
    assert result.exit_code == 0
    assert re.search(r"RO-Crate.*is a valid", result.output)


def test_validate_subcmd_invalid_local_archive_rocrate(cli_runner: CliRunner):
    result = cli_runner.invoke(
        cli,
        [
            "validate",
            str(ValidROC().sort_and_change_archive),
            "--verbose",
            "--no-paging",
            "--skip-checks",
            SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER,
        ],
    )
    assert result.exit_code == 0
    assert re.search(r"RO-Crate.*is a valid", result.output)


def test_validate_skip_checks_option(cli_runner: CliRunner):
    # Patch the validation service to capture the skip_checks argument
    called_args: list = []
    called_kwargs: dict = {}

    def mock_validate(*args, **kwargs):
        logger.warning(f"Mock validate called with args: {args}, kwargs: {kwargs}")

        called_args.extend(args)
        called_kwargs.update(kwargs)

        logger.debug(f"Args: {args}")
        logger.debug(f"Kwargs: {kwargs}")
        logger.debug(f"Called args: {called_args}")
        logger.debug(f"Called kwargs: {called_kwargs}")

    with patch("rocrate_validator.cli.commands.validate.services.validate") as mock_validate_rocrate:
        mock_validate_rocrate.return_value = None
        mock_validate_rocrate.side_effect = mock_validate

        skip_checks_1 = ("a", "b", "c")
        skip_checks_2 = ("d", "e", "f")
        result = cli_runner.invoke(
            cli,
            [
                "--no-interactive",
                "validate",
                str(ValidROC().sort_and_change_remote),
                "--skip-checks",
                ",".join(skip_checks_1),
                "--skip-checks",
                ",".join(skip_checks_2),
                "--no-paging",
            ],
        )

        # Check the exit code which should be 2
        # because the validation service is mocked and does not return a valid result
        assert result.exit_code == 2
        # Check if 'skip_checks' is in the called arguments
        settings = called_args[0]
        assert isinstance(settings, dict), "Validation settings should be a dictionary"

        # Check if the skip_checks attribute is not None
        assert settings["skip_checks"] is not None, "skip_checks should not be None"

        # Check if the skip_checks value matches the expected value
        assert list(skip_checks_1 + skip_checks_2) == settings["skip_checks"], (
            f"Expected skip_checks to be {list(skip_checks_1 + skip_checks_2)}, but got {settings['skip_checks']}"
        )


def test_validate_output_file_text_report(cli_runner: CliRunner, tmp_path: Path):
    output_file = tmp_path / "report.txt"
    result = cli_runner.invoke(
        cli,
        [
            "validate",
            str(ValidROC().wrroc_paper_long_date),
            "--verbose",
            "--no-paging",
            "-o",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "AttributeError" not in result.output
    assert output_file.exists(), "The text report file was not created"
    assert output_file.read_text(encoding="utf-8").strip(), "The text report file is empty"


def test_validate_output_file_json_report(cli_runner: CliRunner, tmp_path: Path):
    output_file = tmp_path / "report.json"
    result = cli_runner.invoke(
        cli,
        [
            "validate",
            str(ValidROC().wrroc_paper_long_date),
            "--no-paging",
            "--output-format",
            "json",
            "-w",
            "10000",
            "-o",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "AttributeError" not in result.output
    assert output_file.exists(), "The JSON report file was not created"
    json.loads(output_file.read_text(encoding="utf-8"))  # must be valid JSON


def _widest_line(text: str) -> int:
    return max((len(line.rstrip()) for line in text.splitlines()), default=0)


@mark.parametrize("width", [60, 100])
def test_validate_sizes_a_redirected_text_report(cli_runner: CliRunner, width: int):
    """
    ``-w`` sizes the report wherever it goes, not only into ``-o``.

    A report redirected out of the terminal is the same document written to a
    file by another route: with no terminal to take a width from, it would
    otherwise fall back to a default 80 columns.
    """
    result = cli_runner.invoke(
        cli, ["validate", str(ValidROC().wrroc_paper_long_date), "--no-paging", "-w", str(width)]
    )

    assert result.exit_code in (0, 1), result.output
    assert _widest_line(result.stdout) <= width
    assert _widest_line(result.stdout) > width - 10, "the report should fill the width it was given"


def test_sessions_report_sizes_its_text_report(cli_runner: CliRunner, isolated_sessions_dir):
    """The same document rebuilt from a session takes the same option."""
    _write_session_with_failures(isolated_sessions_dir, name="sized")

    result = cli_runner.invoke(cli, ["sessions", "report", "sized", "-w", "60"])

    assert result.exit_code == 0, result.output
    assert _widest_line(result.stdout) <= 60


def test_validate_with_invalid_profiles_path_dir(cli_runner: CliRunner):
    dummy_profiles_path = "/tmp/dummy_profiles"
    result = cli_runner.invoke(
        cli,
        [
            "validate",
            str(ValidROC().wrroc_paper_long_date),
            "--profiles-path",
            dummy_profiles_path,
            "--verbose",
            "--no-paging",
        ],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 2
    # On narrow terminals the Rich error panel wraps the message across lines
    # and inserts box-drawing borders (│) between words; strip those and
    # collapse whitespace so the match does not depend on terminal width.
    normalized_output = re.sub(r"[\s│]+", " ", result.output)
    assert re.search(f"Path '{dummy_profiles_path}' does not exist.", normalized_output)


def test_profiles_list(cli_runner: CliRunner):
    """
    Test the list of profiles.
    """
    result = cli_runner.invoke(cli, ["profiles", "list", "--no-paging"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "ro-crate-1.1" in result.output  # Check for a known profile


def test_extra_profiles_list(cli_runner: CliRunner, fake_profiles_path: Path):
    """
    Test the list of extra profiles.
    """
    result = cli_runner.invoke(
        cli,
        ["profiles", "--extra-profiles-path", str(fake_profiles_path), "list", "--no-paging"],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0
    assert "Profile A" in result.output  # Check for a known extra profile


# Profile used for `profiles describe` tests.
_DESCRIBE_TEST_PROFILE = "ro-crate-1.1"


def _first_visible_check():
    """Return the first non-hidden (Python-backed) check of the test profile."""
    profile = services.get_profile(_DESCRIBE_TEST_PROFILE)
    for requirement in profile.requirements:
        if requirement.hidden:
            continue
        for check in requirement.get_checks():
            if isinstance(check, PyFunctionCheck):
                return profile, requirement, check
    raise RuntimeError("No Python-backed check found in test profile")


def _first_shacl_check():
    """Return the first non-hidden SHACL-backed check of the test profile."""
    profile = services.get_profile(_DESCRIBE_TEST_PROFILE)
    for requirement in profile.requirements:
        if requirement.hidden:
            continue
        for check in requirement.get_checks():
            if isinstance(check, SHACLCheck):
                return profile, requirement, check
    raise RuntimeError("No SHACL-backed check found in test profile")


def test_profiles_describe_default(cli_runner: CliRunner):
    """The default describe view (no check id) shows the profile compact view."""
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, "--no-paging"])
    assert result.exit_code == 0
    assert _DESCRIBE_TEST_PROFILE in result.output
    assert "Profile Requirements" in result.output


def test_profiles_describe_verbose(cli_runner: CliRunner):
    """The verbose describe view (no check id) shows individual check identifiers."""
    _, _, check = _first_visible_check()
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, "-v", "--no-paging"])
    assert result.exit_code == 0
    assert check.identifier in result.output


def test_describe_check_relative_id(cli_runner: CliRunner):
    """Resolving a check by '<req#>.<check#>' renders the single-check view."""
    _, requirement, check = _first_visible_check()
    relative = f"{requirement.order_number}.{check.order_number}"
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, relative, "--no-paging"])
    assert result.exit_code == 0, result.output
    assert check.identifier in result.output
    assert check.severity.name in result.output


def test_describe_check_full_id(cli_runner: CliRunner):
    """Resolving a check by full '<profile>_<req#>.<check#>'."""
    _, _, check = _first_visible_check()
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, check.identifier, "--no-paging"])
    assert result.exit_code == 0, result.output
    assert check.identifier in result.output


def test_describe_check_unknown(cli_runner: CliRunner):
    """An out-of-range check id produces a usage error with a hint."""
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, "99.99", "--no-paging"])
    assert result.exit_code == 2
    assert "No requirement #99" in result.output


def test_describe_check_bad_format(cli_runner: CliRunner):
    """A non-numeric check id is rejected with a format hint."""
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, "not-an-id", "--no-paging"])
    assert result.exit_code == 2
    assert "Invalid check identifier" in result.output


def test_describe_check_profile_mismatch(cli_runner: CliRunner):
    """A full id whose prefix doesn't match the requested profile is rejected."""
    result = cli_runner.invoke(
        cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, "some-other-profile_1.1", "--no-paging"]
    )
    assert result.exit_code == 2
    assert "does not belong to profile" in result.output


def test_describe_check_verbose_python(cli_runner: CliRunner):
    """Verbose single-check view on a Python-backed check shows the function source."""
    _, requirement, check = _first_visible_check()
    relative = f"{requirement.order_number}.{check.order_number}"
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, relative, "-v", "--no-paging"])
    assert result.exit_code == 0, result.output
    assert "Source" in result.output
    # The decorated check function is what gets serialized
    assert "@check" in result.output


def test_describe_check_verbose_shacl(cli_runner: CliRunner):
    """Verbose single-check view on a SHACL-backed check shows turtle source."""
    _, requirement, check = _first_shacl_check()
    relative = f"{requirement.order_number}.{check.order_number}"
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, relative, "-v", "--no-paging"])
    assert result.exit_code == 0, result.output
    assert "Source" in result.output
    # SHACL serialized as turtle should contain a sh: prefix and a NodeShape/PropertyShape declaration
    assert "sh:" in result.output


def test_describe_check_verbose_shacl_includes_target(cli_runner: CliRunner):
    """For nested PropertyShape checks, the snippet must include the owning NodeShape's target."""
    profile = services.get_profile(_DESCRIBE_TEST_PROFILE)
    nested = None
    for requirement in profile.requirements:
        if requirement.hidden:
            continue
        for check in requirement.get_checks():
            if isinstance(check, SHACLCheck) and getattr(check._shape, "parent", None) is not None:
                nested = (requirement, check)
                break
        if nested:
            break
    if nested is None:
        # No nested PropertyShape check available in this profile; nothing to assert here.
        return
    requirement, check = nested
    relative = f"{requirement.order_number}.{check.order_number}"
    result = cli_runner.invoke(cli, ["profiles", "describe", _DESCRIBE_TEST_PROFILE, relative, "-v", "--no-paging"])
    assert result.exit_code == 0, result.output
    # The snippet must surface the owning shape's target declaration so the user can see
    # what the property check applies to.
    assert any(
        t in result.output
        for t in ("sh:targetClass", "sh:targetNode", "sh:targetSubjectsOf", "sh:targetObjectsOf", "sh:target ")
    )


###############################################################################
# BATCH MODE TESTS
###############################################################################


def test_discover_ro_crates_directory():
    """Test discover_ro_crates finds crates in a directory."""
    valid_path = CRATES_DATA_PATH / "valid"
    crates = discover_ro_crates(valid_path)
    assert len(crates) > 0
    # Should find subdirectories with ro-crate-metadata.json
    assert any("wrroc-paper-long-date" in str(c) for c in crates)
    assert any("wrroc-paper" in str(c) for c in crates)
    # Should find .zip files
    assert any(c.suffix == ".zip" for c in crates)


def test_discover_ro_crates_no_match_pattern():
    """Test discover_ro_crates with a pattern that matches nothing."""
    valid_path = CRATES_DATA_PATH / "valid"
    crates = discover_ro_crates(valid_path, pattern="nonexistent*.zip")
    assert len(crates) == 0


def test_discover_ro_crates_is_flat(tmp_path):
    """Discovery is flat: a crate's nested payload is not treated as a separate crate."""
    crate = tmp_path / "crateB"
    (crate / "data").mkdir(parents=True)
    (crate / "ro-crate-metadata.json").write_text("{}")
    # A nested metadata file is a payload of crateB and must NOT be discovered.
    (crate / "data" / "ro-crate-metadata.json").write_text("{}")

    crates = discover_ro_crates(tmp_path)
    assert any(c.name == "crateB" for c in crates)
    assert all(c.resolve() != (crate / "data").resolve() for c in crates)


def test_discover_ro_crates_detached_metadata_files(tmp_path):
    """Detached crates defined as immediate `*-ro-crate-metadata.json` files are found."""
    # Two detached crates (metadata files directly in the scan dir).
    (tmp_path / "crate_0001-ro-crate-metadata.json").write_text("{}")
    (tmp_path / "crate_0002-ro-crate-metadata.json").write_text("{}")
    # A directory crate alongside them.
    dir_crate = tmp_path / "crate_0003"
    dir_crate.mkdir()
    (dir_crate / "ro-crate-metadata.json").write_text("{}")
    # Non-crate files must be ignored.
    (tmp_path / "generation_report.json").write_text("{}")
    (tmp_path / ".DS_Store").write_text("")

    crates = discover_ro_crates(tmp_path)
    names = {c.name for c in crates}
    assert "crate_0001-ro-crate-metadata.json" in names
    assert "crate_0002-ro-crate-metadata.json" in names
    assert "crate_0003" in names
    assert "generation_report.json" not in names
    assert ".DS_Store" not in names
    assert len(crates) == 3


def test_discover_ro_crates_self_as_crate():
    """Test that a directory with ro-crate-metadata.json is found as a crate."""
    crate_dir = ValidROC().wrroc_paper_long_date
    crates = discover_ro_crates(crate_dir)
    assert len(crates) >= 1
    assert crate_dir.resolve() in crates


def test_discover_ro_crates_invalid_dir():
    """Test discover_ro_crates raises on non-directory."""
    with tempfile.NamedTemporaryFile() as tmp:
        import pytest

        with pytest.raises(NotADirectoryError):
            discover_ro_crates(Path(tmp.name))


def _make_dir_crate(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "ro-crate-metadata.json").write_text("{}")


def test_discover_ro_crates_nested_collections(tmp_path):
    """With no crate at the scan root, discovery descends until levels holding crates."""
    _make_dir_crate(tmp_path / "repoA" / "c1")
    _make_dir_crate(tmp_path / "repoA" / "c2")
    _make_dir_crate(tmp_path / "repoB" / "deeper" / "c3")
    # Hidden directories are not traversed and non-crate files do not contribute.
    _make_dir_crate(tmp_path / ".cache" / "c4")
    (tmp_path / "README.md").write_text("")

    crates = discover_ro_crates(tmp_path)
    assert {c.name for c in crates} == {"c1", "c2", "c3"}
    # The pattern applies to the crate names across all nested collections.
    assert {c.name for c in discover_ro_crates(tmp_path, pattern="c1")} == {"c1"}


def test_discover_ro_crates_direct_crates_stop_the_descent(tmp_path):
    """A level directly holding crates is a collection root: siblings are not explored."""
    _make_dir_crate(tmp_path / "crateA")
    _make_dir_crate(tmp_path / "sub" / "crateB")

    crates = discover_ro_crates(tmp_path)
    assert {c.name for c in crates} == {"crateA"}


def test_discover_ro_crates_no_crates_anywhere(tmp_path):
    """A crateless tree (including symlinked dirs, never followed) yields no crates."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    # A symlink loop back to the scan root must not be followed.
    (tmp_path / "a" / "loop").symlink_to(tmp_path, target_is_directory=True)
    assert discover_ro_crates(tmp_path) == []


def test_batch_crate_entry_serialization():
    """Test BatchCrateEntry to_dict/from_dict roundtrip."""
    entry = BatchCrateEntry(
        path="/tmp/test-crate",
        status="completed",
        passed=True,
        duration=1.23,
        issues=[{"message": "test issue"}],
        statistics={"total_checks": 10},
    )
    data = entry.to_dict()
    restored = BatchCrateEntry.from_dict(data)
    assert restored.path == entry.path
    assert restored.status == entry.status
    assert restored.passed == entry.passed
    assert restored.duration == entry.duration
    assert restored.issues == entry.issues
    assert restored.statistics == entry.statistics


def test_batch_result_to_dict_is_the_v2_report():
    """The programmatic API returns the same report the CLI writes."""
    session = BatchSession(validation_settings={}, crate_paths=["/tmp/test-crate"])
    session.crates[0].status = "completed"
    session.crates[0].passed = True

    report = BatchValidationResult(session).to_dict()
    assert report["meta"]["report_schema_version"] == "2.0"
    assert sorted(report) == [
        "checks",
        "crates",
        "meta",
        "passed",
        "profiles",
        "requirements",
        "session",
        "statistics",
        "validation_settings",
    ]
    # The pre-v2 keys moved to the legacy renderer.
    assert "batch_passed" not in report
    assert "results" not in report


def test_batch_session_save_load(tmp_path):
    """Test BatchSession save/load roundtrip."""
    settings = {"profile_identifier": "ro-crate", "requirement_severity": "REQUIRED"}
    session = BatchSession(
        validation_settings=settings,
        crate_paths=["/tmp/crate1", "/tmp/crate2"],
        session_path=tmp_path / "session.json",
    )
    assert session.total_crates == 2
    assert session.processed_crates == 0

    # Simulate a completed crate
    session.crates[0].status = "completed"
    session.crates[0].passed = True
    session.save()

    # Load it back
    loaded = BatchSession.load(tmp_path / "session.json")
    assert loaded.total_crates == 2
    assert loaded.processed_crates == 1
    assert loaded.passed_crates == 1
    assert loaded.validation_settings["profile_identifier"] == "ro-crate"
    assert loaded.crates[0].status == "completed"
    assert loaded.crates[0].passed is True
    assert loaded.crates[1].status == "pending"


def test_batch_session_get_pending():
    """Test get_pending returns only pending/in_progress entries."""
    session = BatchSession(
        validation_settings={},
        crate_paths=["/tmp/a", "/tmp/b", "/tmp/c"],
    )
    session.crates[0].status = "completed"
    session.crates[1].status = "in_progress"
    pending = session.get_pending()
    assert len(pending) == 2
    assert pending[0].path == "/tmp/b"
    assert pending[1].path == "/tmp/c"


def test_batch_session_is_completed():
    """Test is_completed returns True only when all crates done."""
    session = BatchSession(validation_settings={}, crate_paths=["/tmp/a"])
    assert not session.is_completed()
    session.crates[0].status = "completed"
    session.crates[0].passed = True
    assert session.is_completed()


def test_batch_session_is_completed_counts_errored_crates():
    """A crate the validation could not run on is processed all the same."""
    session = BatchSession(validation_settings={}, crate_paths=["/tmp/a"])
    session.mark_errored("/tmp/a", "Not an RO-Crate")
    assert session.is_completed()


def test_batch_session_mark_errored():
    """Test mark_errored updates session state correctly."""
    session = BatchSession(validation_settings={}, crate_paths=["/tmp/a"])
    session.mark_errored("/tmp/a", "Connection error", 0.5)
    assert session.crates[0].status == "errored"
    assert session.crates[0].passed is False
    assert session.crates[0].error == "Connection error"
    assert session.errored_crates == 1
    assert session.invalid_crates == 0, "an error is not an invalid crate"
    assert session.processed_crates == 1


def test_batch_validate_valid_crates(cli_runner: CliRunner):
    """Test batch validation of valid crates via CLI."""
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper*",
            # The wrroc-paper crates declare RO-Crate 1.1: validate against the
            # matching version (the bare "ro-crate" now resolves to the newest
            # available profile, 1.2, against which these 1.1 crates fail).
            "--profile-identifier",
            "ro-crate-1.1",
            "--verbose",
            "--no-paging",
        ],
    )
    # Should succeed with at least 2 valid crates found
    assert result.exit_code == 0, result.output
    assert "Validation Summary" in result.output


def test_batch_validate_session_opt_in(cli_runner: CliRunner, isolated_sessions_dir):
    """With --session, the batch is recorded as a permanent session; the runs dir stays clean."""
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--session",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--no-resume",
        ],
    )
    assert result.exit_code == 0, result.output
    # A session file must have been created under the user sessions directory.
    sessions = list(isolated_sessions_dir.glob("*.json"))
    assert sessions, "no session file was created despite --session"
    session_data = json.loads(max(sessions, key=lambda p: p.stat().st_mtime).read_text())
    assert session_data["session"]["status"] == "completed"
    assert session_data["session"]["passed_crates"] >= 1
    assert session_data["crates"][0]["status"] == "completed"
    # The profile used is recorded per crate in the session.
    assert session_data["crates"][0]["profiles"] == ["ro-crate-1.1"]
    # With --session no temporary run-state is created at all.
    assert not list(get_user_runs_dir().glob("*.json"))


def test_batch_validate_no_session_by_default(cli_runner: CliRunner, isolated_sessions_dir):
    """Without --session, a completed batch leaves neither a session nor a run-state behind."""
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--no-resume",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not list(isolated_sessions_dir.glob("*.json")), "no session must be recorded without --session"
    assert not list(get_user_runs_dir().glob("*.json")), "the run-state must be deleted on completion"


def test_batch_validate_json_output(cli_runner: CliRunner, tmp_path):
    """Test batch validation with JSON output file."""
    output_file = tmp_path / "batch_output.json"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--output-format",
            "json",
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert data["meta"]["report_schema_version"] == "2.0"
    assert data["session"]["mode"] == "single", "one matched crate is a session of one"
    assert data["passed"] is True
    assert [crate["name"] for crate in data["crates"]] == ["wrroc-paper-long-date"]


def test_batch_validate_json_output_legacy_schema(cli_runner: CliRunner, tmp_path):
    """--json-schema legacy keeps emitting the pre-v2 batch envelope."""
    output_file = tmp_path / "batch_output.json"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--output-format",
            "json",
            "--json-schema",
            "legacy",
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output_file.read_text())
    assert "batch_passed" in data
    assert "results" in data
    assert data["meta"]["version"], "the legacy report keeps its own meta.version"


def test_batch_validate_split_per_crate(cli_runner: CliRunner, tmp_path, monkeypatch):
    """--split-per-crate writes one report per crate plus the manifest tying them together."""
    coll, _ = _make_collection(tmp_path, n=2)
    # The default destination is relative to the working directory.
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", str(coll), "-f", "json", "--split-per-crate", *_VALIDATE_OPTS]
    )
    assert result.exit_code in (0, 1), result.output

    report_dir = tmp_path / "validation-report"
    assert sorted(p.name for p in report_dir.glob("*.json")) == ["crate-0.json", "crate-1.json", "index.json"]

    manifest = json.loads((report_dir / "index.json").read_text())
    assert manifest["schema"] == "v2"
    assert manifest["total_crates"] == 2
    assert [crate["file"] for crate in manifest["crates"]] == ["crate-0.json", "crate-1.json"]

    # Each file is a standalone v2 report of exactly one crate.
    for crate in manifest["crates"]:
        document = json.loads((report_dir / crate["file"]).read_text())
        assert document["meta"]["report_schema_version"] == "2.0"
        assert [item["path"] for item in document["crates"]] == [crate["path"]]


def test_batch_validate_split_per_crate_legacy(cli_runner: CliRunner, tmp_path):
    """Splitting is orthogonal to the schema: the same layout, legacy documents inside."""
    coll, _ = _make_collection(tmp_path, n=2)
    out_dir = tmp_path / "out"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "--split-per-crate",
            "--json-schema",
            "legacy",
            "-d",
            str(out_dir),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output

    # Files go directly into --output-dir.
    assert sorted(p.name for p in out_dir.glob("*.json")) == [
        "crate-0.json",
        "crate-1.json",
        "index.json",
    ]
    document = json.loads((out_dir / "crate-0.json").read_text())
    assert sorted(document) == ["issues", "meta", "passed", "statistics", "validation_settings"]
    assert json.loads((out_dir / "index.json").read_text())["schema"] == "legacy"


def test_split_per_crate_legacy_keeps_the_check_inside_every_issue(cli_runner: CliRunner, tmp_path):
    """The legacy split documents predate the definition tables: issues stay self-contained."""
    coll = tmp_path / "collection"
    coll.mkdir()
    shutil.copytree(InvalidFileDescriptor().invalid_jsonld_not_compacted, coll / "bad-crate")
    out_dir = tmp_path / "out"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "--split-per-crate",
            "--json-schema",
            "legacy",
            "-d",
            str(out_dir),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code == 1, result.output

    document = json.loads((out_dir / "bad-crate.json").read_text())
    issues = document["issues"]
    assert issues, "an invalid crate must report issues for this test to mean anything"
    check = issues[0]["check"]
    assert isinstance(check, dict), "the legacy schema carries the check object, not its identifier"
    assert check["identifier"]
    assert check["requirement"]["profile"]["identifier"] == "ro-crate-1.1"


def test_split_per_crate_rejects_non_json_formats(cli_runner: CliRunner, tmp_path):
    """The flag shapes the JSON report only; asking for it elsewhere is an error."""
    coll, _ = _make_collection(tmp_path, n=1)
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", str(coll), "-f", "csv", "--split-per-crate", *_VALIDATE_OPTS]
    )
    assert result.exit_code == 2
    assert "--split-per-crate applies to the JSON report only" in result.output


def test_output_dir_with_relative_output_file(cli_runner: CliRunner, tmp_path):
    """-d + relative -o: the output file is resolved against the base directory."""
    coll, _ = _make_collection(tmp_path, n=1)
    out_dir = tmp_path / "reports"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "-d",
            str(out_dir),
            "-o",
            "result.json",
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output
    assert (out_dir / "result.json").exists()
    data = json.loads((out_dir / "result.json").read_text())
    assert data["meta"]["report_schema_version"] == "2.0"


def test_output_dir_with_absolute_output_file_warns(cli_runner: CliRunner, tmp_path):
    """-d + absolute -o: -d is ignored with a warning, the absolute path is used."""
    coll, _ = _make_collection(tmp_path, n=1)
    out_dir = tmp_path / "ignored-dir"
    abs_file = tmp_path / "absolute.json"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "-d",
            str(out_dir),
            "-o",
            str(abs_file),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output
    assert "Warning:" in result.stderr
    assert "--output-dir is ignored when --output-file is an absolute path" in result.stderr
    assert abs_file.exists()
    assert not out_dir.exists()


def test_output_dir_without_output_file_or_split_warns(cli_runner: CliRunner, tmp_path):
    """-d alone, with neither -o nor --split-per-crate: warns, output goes to stdout."""
    coll, _ = _make_collection(tmp_path, n=1)
    out_dir = tmp_path / "unused-dir"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "-d",
            str(out_dir),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output
    assert "Warning:" in result.stderr
    assert "--output-dir has no effect" in result.stderr
    assert not out_dir.exists()


def test_split_per_crate_warns_when_output_file_is_also_given(cli_runner: CliRunner, tmp_path, monkeypatch):
    """-o is ignored with --split-per-crate; the user gets a warning on stderr."""
    coll, _ = _make_collection(tmp_path, n=1)
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "--split-per-crate",
            "-o",
            str(tmp_path / "ignored.json"),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output
    assert "Warning:" in result.stderr
    assert "--output-file is ignored with --split-per-crate" in result.stderr
    # The reports still went to the default directory, not the -o file.
    assert (tmp_path / "validation-report").is_dir()
    assert (tmp_path / "validation-report" / "index.json").exists()


def test_split_per_crate_with_output_dir(cli_runner: CliRunner, tmp_path, monkeypatch):
    """--split-per-crate with an explicit --output-dir writes reports there."""
    coll, _ = _make_collection(tmp_path, n=2)
    out_dir = tmp_path / "my-reports"
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(coll),
            "-f",
            "json",
            "--split-per-crate",
            "-d",
            str(out_dir),
            *_VALIDATE_OPTS,
        ],
    )
    assert result.exit_code in (0, 1), result.output
    assert sorted(p.name for p in out_dir.glob("*.json")) == ["crate-0.json", "crate-1.json", "index.json"]
    manifest = json.loads((out_dir / "index.json").read_text())
    assert manifest["schema"] == "v2"
    assert [crate["file"] for crate in manifest["crates"]] == ["crate-0.json", "crate-1.json"]


def test_batch_validate_mixed_crates(cli_runner: CliRunner, tmp_path):
    """Test batch validation with mix of valid and invalid crates."""
    # Create temp dir with both valid and invalid crates
    batch_dir = tmp_path / "batch_mixed"
    batch_dir.mkdir()
    valid_src = ValidROC().wrroc_paper_long_date
    invalid_src = InvalidFileDescriptor().invalid_json_format

    # Copy valid crate
    import shutil

    shutil.copytree(valid_src, batch_dir / "valid_crate", symlinks=True)
    # Copy invalid crate
    shutil.copytree(invalid_src, batch_dir / "invalid_crate", symlinks=True)

    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            str(batch_dir),
            "--profile-identifier",
            "ro-crate",
            "--no-paging",
            "--verbose",
        ],
    )
    # Should fail because at least one crate fails
    assert result.exit_code == 1, result.output
    assert "Validation Summary" in result.output
    # Verbose per-crate details are rendered (from the session entries)
    assert "Failed crate details:" in result.output


def test_batch_verbose_details_rendered_from_session_entries():
    """
    Verbose failed-crate details must come from the persisted session entries:
    no live ValidationResult is retained by a batch run (their contexts would
    pin every crate's graphs in memory for the whole batch).
    """
    import io

    from rocrate_validator.cli.ui.text.validate import BatchValidationCommandView
    from rocrate_validator.models import BatchValidationResult
    from rocrate_validator.utils.io_helpers.output.console import Console

    session = BatchSession(validation_settings={}, crate_paths=["/tmp/crate_x", "/tmp/crate_y"])
    failed = session.crates[0]
    failed.status = "completed"
    failed.passed = False
    failed.duration = 1.2
    failed.statistics = {"total_checks": 3, "total_passed_checks": 2, "total_failed_checks": 1}
    failed.issues = [
        {
            "severity": "REQUIRED",
            "message": "The root entity is missing",
            "check": {"identifier": "ro-crate-1.1_1.1", "name": "Root entity existence"},
        }
    ]
    errored = session.crates[1]
    errored.status = "errored"
    errored.passed = False
    errored.error = "RO-Crate metadata not found"

    out = Console(file=io.StringIO(), width=200, color_system=None)
    BatchValidationCommandView(console=out).show_summary(BatchValidationResult(session), verbose=True)
    rendered = out.file.getvalue()

    assert "Failed crate details:" in rendered
    assert "ro-crate-1.1_1.1" in rendered
    assert "The root entity is missing" in rendered
    # Entries that errored out (no check breakdown) show their error message
    assert "RO-Crate metadata not found" in rendered


def test_batch_validate_keep_results(tmp_path):
    """Live results are dropped by default and retained only with keep_results=True."""
    crate = str(ValidROC().wrroc_paper_long_date)
    settings = ValidationSettings.parse({"profile_identifier": ("ro-crate",)})

    dropped = services.batch_validate(
        settings,
        [crate],
        state_path=tmp_path / "dropped.json",
        profile_identifiers=["ro-crate"],
        no_auto_profile=True,
    )
    assert dropped.live_results == [], "live results must not be retained by default"
    assert dropped.total_crates() == 1, "the session outcome is recorded regardless"

    kept = services.batch_validate(
        settings,
        [crate],
        state_path=tmp_path / "kept.json",
        profile_identifiers=["ro-crate"],
        no_auto_profile=True,
        keep_results=True,
    )
    assert [path for path, _ in kept.live_results] == [crate]
    assert all(hasattr(result, "passed") for _, result in kept.live_results)


def test_batch_prepare_session_auto_resume(tmp_path):
    """An interrupted session is auto-resumed: completed crates are carried over."""
    session_file = tmp_path / "auto_session.json"
    paths = ["/tmp/crate_a", "/tmp/crate_b", "/tmp/crate_c"]

    # Simulate a previously interrupted session with one completed crate.
    session = BatchSession(validation_settings={}, crate_paths=paths, session_path=session_file)
    session.crates[0].status = "completed"
    session.crates[0].passed = True
    session.status = "interrupted"
    session.save()

    settings = ValidationSettings.parse({"profile_identifier": ("ro-crate",)})

    # Resume (fresh=False): the completed crate is skipped, the rest are pending.
    resumed, pending = services._prepare_batch_session(settings, paths, session_file, fresh=False)
    assert resumed.processed_crates == 1
    assert resumed.total_crates == 3
    assert set(pending) == {"/tmp/crate_b", "/tmp/crate_c"}

    # Fresh (fresh=True): everything is re-validated, nothing carried over.
    restarted, pending_fresh = services._prepare_batch_session(settings, paths, session_file, fresh=True)
    assert restarted.processed_crates == 0
    assert set(pending_fresh) == set(paths)


def test_batch_session_path_reflects_profile_selection(tmp_path):
    """The session key must distinguish profile selections, order-independently."""
    settings = ValidationSettings.parse(
        {"rocrate_uri": ".", "profile_identifier": "ro-crate", "requirement_severity": "REQUIRED"}
    )

    def sp(profile_identifiers, no_auto_profile=False, severity_only=False):
        s = ValidationSettings.parse(
            {
                "rocrate_uri": ".",
                "profile_identifier": "ro-crate",
                "requirement_severity": "REQUIRED",
                "requirement_severity_only": severity_only,
            }
        )
        return services.resolve_batch_session_path(
            s, tmp_path, "*", profile_identifiers=profile_identifiers, no_auto_profile=no_auto_profile
        )

    # Different multi-profile sets sharing the first profile must NOT collide.
    assert sp(["ro-crate-1.1", "ro-crate-1.2"]) != sp(["ro-crate-1.1", "ro-crate-process-run"])
    # Profile order does not matter.
    assert sp(["ro-crate-1.1", "ro-crate-1.2"]) == sp(["ro-crate-1.2", "ro-crate-1.1"])
    # Auto-detection, disabled auto-detection and an explicit profile are all distinct.
    assert sp(None, no_auto_profile=False) != sp(None, no_auto_profile=True)
    assert sp(["ro-crate-1.1"]) != sp(None, no_auto_profile=False)
    # requirement_severity_only changes the key (it is dropped by to_dict()).
    assert sp(["ro-crate-1.1"], severity_only=False) != sp(["ro-crate-1.1"], severity_only=True)

    # Sanity: a stable selection resolves to a stable path.
    assert services.resolve_batch_session_path(
        settings, tmp_path, "*", profile_identifiers=["ro-crate-1.1"]
    ) == services.resolve_batch_session_path(settings, tmp_path, "*", profile_identifiers=["ro-crate-1.1"])


def test_batch_footer_reports_saved_paths(cli_runner: CliRunner, tmp_path):
    """The end-of-batch footer reports where the report file was saved."""
    output_file = tmp_path / "report.txt"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--output-format",
            "text",
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    # The footer (on stderr) names the saved artifacts and the input scanned.
    assert "Report (text)" in result.stderr
    assert str(output_file) in result.stderr
    # Without --session no session path is advertised (the run-state is
    # ephemeral and already deleted at this point).
    assert "Session" not in result.stderr
    assert "Input" in result.stderr
    # Per-crate progress lines show the crate relative to the input path
    # (the bare crate name, not an absolute path).
    assert "] wrroc-paper-long-date" in result.stderr


def test_batch_header_shows_session_with_opt_in(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """With --session, the header advertises the session file location."""
    coll, _ = _make_collection(tmp_path, n=1)
    result = cli_runner.invoke(
        cli,
        ["--no-interactive", "validate", str(coll), "--session-name", "header-check", *_VALIDATE_OPTS],
    )
    assert result.exit_code == 0, result.output
    assert "Session" in result.stderr
    assert "header-check.json" in result.stderr


def test_batch_validate_csv_output(cli_runner: CliRunner, tmp_path):
    """Test batch validation with CSV output file."""
    output_file = tmp_path / "batch_output.csv"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--output-format",
            "csv",
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output_file.exists()
    # utf-8-sig: spreadsheet tools detect the encoding from the BOM.
    rows = output_file.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0].startswith("source,crate,path,profiles,status,error,size_bytes,duration_s")
    assert "issue_severity,message" in rows[0]
    # The profile used is recorded in the CSV row.
    assert ",ro-crate-1.1," in rows[1]
    # One data row for the validated (passed, issue-less) crate.
    assert len(rows) == 2
    assert "wrroc-paper-long-date" in rows[1]
    assert ",PASSED," in rows[1]


def test_csv_output_in_single_mode(cli_runner: CliRunner):
    """CSV is available for a single crate too, with the very same columns as the batch one."""
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(ValidROC().wrroc_paper_long_date),
            "--profile-identifier",
            "ro-crate",
            "--no-paging",
            "--skip-checks",
            SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER,
            "--output-format",
            "csv",
        ],
    )
    # The verdict is beside the point here; only a crash would be.
    assert result.exit_code in (0, 1), result.output
    rows = list(csv.reader(io.StringIO(result.output)))
    assert rows[0] == CSV_REPORT_FIELDS
    # One crate, so no collection root to group by: the source column stays empty.
    assert {row[0] for row in rows[1:]} == {""}
    assert {row[1] for row in rows[1:]} == {"wrroc-paper-long-date"}


def test_batch_validate_no_crates_found(cli_runner: CliRunner, tmp_path):
    """Test batch with no matching crates."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            str(empty_dir),
            "--no-paging",
        ],
    )
    assert result.exit_code == 0
    # The notice belongs on stderr, so it never lands inside a machine-readable report.
    assert "No RO-Crates found" in result.stderr


def test_batch_no_crates_found_still_emits_a_json_report(cli_runner: CliRunner, tmp_path):
    """
    A batch that matched nothing yields an empty report, not an empty stream:
    a consumer should not have to tell "nothing matched" apart from "the command
    produced no output".
    """
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", "--batch", str(empty_dir), "-f", "json", *_VALIDATE_OPTS]
    )
    assert result.exit_code == 0, result.output

    # stdout parses on its own: the human notice went to stderr.
    report = json.loads(result.stdout)
    assert report["crates"] == []
    assert report["passed"] is True
    assert report["session"]["total_crates"] == 0
    assert report["statistics"]["crates_with_statistics"] == 0
    assert "No RO-Crates found" in result.stderr


def test_batch_no_crates_found_still_emits_a_csv_header(cli_runner: CliRunner, tmp_path):
    """The CSV of an empty batch is its header row: a valid, empty table."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", "--batch", str(empty_dir), "-f", "csv", *_VALIDATE_OPTS]
    )
    assert result.exit_code == 0, result.output
    rows = list(csv.reader(io.StringIO(result.stdout)))
    assert rows == [CSV_REPORT_FIELDS]


def test_batch_no_crates_found_split_writes_only_the_manifest(cli_runner: CliRunner, tmp_path, monkeypatch):
    """Splitting an empty batch leaves the manifest alone to say so."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        cli,
        ["--no-interactive", "validate", "--batch", str(empty_dir), "-f", "json", "--split-per-crate", *_VALIDATE_OPTS],
    )
    assert result.exit_code == 0, result.output

    report_dir = tmp_path / "validation-report"
    assert [p.name for p in report_dir.glob("*.json")] == ["index.json"]
    manifest = json.loads((report_dir / "index.json").read_text())
    assert manifest["crates"] == []
    assert manifest["total_crates"] == 0


def test_batch_with_output_file_text(cli_runner: CliRunner, tmp_path):
    """Test batch validation writes text output to file."""
    output_file = tmp_path / "batch_report.txt"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--output-format",
            "text",
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output_file.exists()
    content = output_file.read_text()
    assert "Validation Summary" in content


def test_batch_canonical_positional_target(cli_runner: CliRunner):
    """The scan root can be given as the positional RO-CRATE-URI argument (no -B)."""
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper*",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Validation Summary" in result.output


def test_no_resume_ignores_saved_session(cli_runner: CliRunner):
    """--no-resume re-validates from scratch instead of resuming a saved session."""
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper-long-date",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--no-resume",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Validation Summary" in result.output


def test_batch_pattern_requires_batch_mode(cli_runner: CliRunner):
    """--batch-pattern must be rejected when the input is a single crate."""
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            str(ValidROC().wrroc_paper_long_date),
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--batch-pattern",
            "foo*",
        ],
    )
    assert result.exit_code != 0
    assert "batch mode" in result.output.lower()


# ---------------------------------------------------------------------------
# Input auto-detection, opt-in sessions and resume
# ---------------------------------------------------------------------------

# Shared trailing options for the validate invocations in this section.
_VALIDATE_OPTS = ["-p", "ro-crate-1.1", "--no-paging", "--skip-availability-check"]


def _make_collection(tmp_path: Path, n: int = 2) -> tuple[Path, list[str]]:
    """A collection directory holding ``n`` copies of a small valid crate."""
    src = ValidROC().wrroc_paper_long_date
    coll = tmp_path / "collection"
    coll.mkdir()
    crates = []
    for i in range(n):
        dst = coll / f"crate-{i}"
        shutil.copytree(src, dst)
        crates.append(str(dst))
    return coll, crates


def _write_interrupted_state(state_path: Path, crate_paths: list[str], completed_count: int = 1) -> None:
    """Persist an interrupted batch state with the first crates marked completed."""
    session = BatchSession(validation_settings={}, crate_paths=crate_paths, session_path=state_path)
    for i in range(completed_count):
        session.crates[i].status = "completed"
        session.crates[i].passed = True
    session.status = "interrupted"
    session.profile_identifiers = ["ro-crate-1.1"]
    session.save()


def test_autodetect_single_crate_dir(cli_runner: CliRunner, isolated_sessions_dir):
    """A directory with its own ro-crate-metadata.json is validated as a single crate."""
    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", crate, *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "Batch validation" not in result.output
    assert "[OK]" in result.output


def test_autodetect_collection_dir_batches(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """A directory without a metadata file is scanned and validated in batch mode (no -b needed)."""
    coll, _ = _make_collection(tmp_path, n=2)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", str(coll), *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "Batch validation" in result.output
    assert "Total: 2 crates" in result.output


def test_autodetect_empty_collection_errors(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """A directory holding no crate at all is rejected with a clear error."""
    empty = tmp_path / "nothing-here"
    (empty / "sub").mkdir(parents=True)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", str(empty), *_VALIDATE_OPTS])
    assert result.exit_code != 0
    assert "no ro-crate metadata found" in result.output.lower()


def test_explicit_list_batches(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Two or more positional URIs are validated as an explicit batch list."""
    _, crates = _make_collection(tmp_path, n=2)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", *crates, *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "Batch validation" in result.output
    assert "Total: 2 crates" in result.output


def test_explicit_list_expands_collection_dirs(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """A collection directory inside an explicit list is expanded to its crates (union)."""
    coll, _ = _make_collection(tmp_path, n=2)
    single = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", single, str(coll), *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "Total: 3 crates" in result.output


def test_batch_pattern_rejected_with_explicit_list(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """--batch-pattern only applies to a directory scan, not to an explicit list."""
    _, crates = _make_collection(tmp_path, n=2)
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", *crates, "--batch-pattern", "foo*", *_VALIDATE_OPTS]
    )
    assert result.exit_code != 0
    assert "explicit list" in result.output.lower()


def test_force_batch_on_crate_dir(cli_runner: CliRunner, isolated_sessions_dir):
    """-b forces a directory scan even when the directory is itself a crate."""
    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", "-b", crate, *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "Batch validation" in result.output
    assert "Total: 1 crates" in result.output


def test_resume_and_no_resume_mutually_exclusive(cli_runner: CliRunner):
    result = cli_runner.invoke(
        cli,
        ["--no-interactive", "validate", str(ValidROC().wrroc_paper_long_date), "--resume", "--no-resume"],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_single_crate_resume_is_noop_with_warning(cli_runner: CliRunner, isolated_sessions_dir):
    """--resume on a single-crate validation warns and runs fresh (validation is atomic)."""
    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", crate, "--resume", *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert "no effect" in result.output.lower()


def test_resume_continues_interrupted_run_state(cli_runner: CliRunner, isolated_sessions_dir, tmp_path, monkeypatch):
    """--resume picks up a matching interrupted run-state and validates only the pending crates."""
    coll, crates = _make_collection(tmp_path, n=2)
    state_path = tmp_path / "run-state.json"
    monkeypatch.setattr(services, "resolve_run_state_path", lambda *a, **k: state_path)
    _write_interrupted_state(state_path, crates, completed_count=1)

    result = cli_runner.invoke(cli, ["--no-interactive", "validate", str(coll), "--resume", *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    # Only the pending crate is validated; the completed one is carried over.
    assert "[1/1]" in result.output
    assert "Total: 2 crates" in result.output
    # On completion the ephemeral run-state is deleted.
    assert not state_path.exists()


def test_interrupted_run_state_starts_fresh_non_interactive(
    cli_runner: CliRunner, isolated_sessions_dir, tmp_path, monkeypatch
):
    """Without --resume, a matching interrupted state is ignored in non-interactive mode (fresh run)."""
    coll, crates = _make_collection(tmp_path, n=2)
    state_path = tmp_path / "run-state.json"
    monkeypatch.setattr(services, "resolve_run_state_path", lambda *a, **k: state_path)
    _write_interrupted_state(state_path, crates, completed_count=1)

    result = cli_runner.invoke(cli, ["--no-interactive", "validate", str(coll), *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    # Every crate is re-validated from scratch.
    assert "[1/2]" in result.output
    assert "[2/2]" in result.output
    assert not state_path.exists()


def test_resume_key_survives_new_crates_in_collection(
    cli_runner: CliRunner, isolated_sessions_dir, tmp_path, monkeypatch
):
    """A crate added to the collection after the interruption joins the resumed run as pending."""
    coll, crates = _make_collection(tmp_path, n=2)
    state_path = tmp_path / "run-state.json"
    monkeypatch.setattr(services, "resolve_run_state_path", lambda *a, **k: state_path)
    _write_interrupted_state(state_path, crates, completed_count=1)
    # A new crate lands in the collection between the interruption and the resume.
    shutil.copytree(ValidROC().wrroc_paper_long_date, coll / "crate-late")

    result = cli_runner.invoke(cli, ["--no-interactive", "validate", str(coll), "--resume", *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    # The completed crate is carried over; the pending one and the new one are validated.
    assert "[2/2]" in result.output
    assert "Total: 3 crates" in result.output


def test_run_state_key_is_input_anchored(tmp_path):
    """The run-state key derives from the user input, not from the discovered crates."""
    settings = ValidationSettings.parse({"rocrate_uri": ".", "profile_identifier": "ro-crate"})
    targets = services.normalize_state_targets([tmp_path])
    before = services.resolve_run_state_path(settings, targets, "*", profile_identifiers=["ro-crate-1.1"])
    # New content under the scan root must not change the key.
    (tmp_path / "new-crate").mkdir()
    after = services.resolve_run_state_path(
        settings, services.normalize_state_targets([tmp_path]), "*", profile_identifiers=["ro-crate-1.1"]
    )
    assert before == after
    # Explicit lists are order-independent.
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert services.resolve_run_state_path(
        settings, services.normalize_state_targets([a, b])
    ) == services.resolve_run_state_path(settings, services.normalize_state_targets([b, a]))
    # Remote URIs are keyed as-is (never Path-resolved).
    assert services.normalize_state_targets(["https://example.org/crate.zip"]) == ["https://example.org/crate.zip"]
    # Run-states and unnamed sessions live in their own directories.
    assert services.resolve_run_state_path(settings, targets).parent == get_user_runs_dir()
    assert services.resolve_session_state_path(settings, targets).parent == get_user_sessions_dir()


def test_named_session_created_and_guarded(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """--session-name NAME creates sessions/<NAME>.json; an existing session is never silently overwritten."""
    coll, _ = _make_collection(tmp_path, n=2)
    args = ["--no-interactive", "validate", str(coll), *_VALIDATE_OPTS]

    result = cli_runner.invoke(cli, [*args, "--session-name", "named-run"])
    assert result.exit_code == 0, result.output
    session_file = isolated_sessions_dir / "named-run.json"
    assert session_file.exists()
    assert json.loads(session_file.read_text())["session"]["status"] == "completed"

    # Re-running with the same name without --resume is a usage error.
    result = cli_runner.invoke(cli, [*args, "--session-name", "named-run"])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()

    # With --resume the (completed) session is re-run into the same file.
    result = cli_runner.invoke(cli, [*args, "--session-name", "named-run", "--resume"])
    assert result.exit_code == 0, result.output
    assert session_file.exists()


def test_session_flag_does_not_swallow_target(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """-S is a boolean flag: the target after it stays the RO-CRATE-URI, never a session name."""
    coll, _ = _make_collection(tmp_path, n=2)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", "--session", str(coll), *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    # The collection was validated and recorded as an auto-named session.
    sessions = list(isolated_sessions_dir.glob("*.json"))
    assert len(sessions) == 1
    assert json.loads(sessions[0].read_text())["session"]["total_crates"] == 2


def test_interrupted_session_is_resumable_via_sessions_resume(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """An interrupted --session run persists in the sessions dir and `sessions resume` completes it."""
    _, crates = _make_collection(tmp_path, n=2)
    session_file = isolated_sessions_dir / "halfway.json"
    _write_interrupted_state(session_file, crates, completed_count=1)

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume", "halfway"])
    assert result.exit_code == 0, result.output
    data = json.loads(session_file.read_text())
    assert data["session"]["status"] == "completed"
    assert data["session"]["passed_crates"] == 2
    # The permanent session survives its own completion.
    assert session_file.exists()


def test_sessions_new_and_fill(cli_runner: CliRunner, isolated_sessions_dir):
    """`sessions new` creates an empty named session that `validate --session-name <name>` then fills."""
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "new", "prepared"])
    assert result.exit_code == 0, result.output
    session_file = isolated_sessions_dir / "prepared.json"
    assert session_file.exists()
    assert json.loads(session_file.read_text())["session"]["total_crates"] == 0

    # The same name cannot be created twice.
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "new", "prepared"])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()

    # An empty named session is filled (not rejected) by validate --session-name <name>.
    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(
        cli, ["--no-interactive", "validate", crate, "--session-name", "prepared", *_VALIDATE_OPTS]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(session_file.read_text())
    assert data["session"]["total_crates"] == 1
    assert data["session"]["status"] == "completed"


def test_stale_run_states_are_garbage_collected(cli_runner: CliRunner, isolated_sessions_dir):
    """Run-states older than the TTL are removed at the start of a validate run; recent ones stay."""
    runs_dir = get_user_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    stale = runs_dir / "stale.json"
    recent = runs_dir / "recent.json"
    stale.write_text("{}", encoding="utf-8")
    recent.write_text("{}", encoding="utf-8")
    forty_days_ago = time.time() - 40 * 24 * 3600
    os.utime(stale, (forty_days_ago, forty_days_ago))

    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(cli, ["--no-interactive", "validate", crate, *_VALIDATE_OPTS])
    assert result.exit_code == 0, result.output
    assert not stale.exists(), "stale run-states must be garbage-collected"
    assert recent.exists(), "recent run-states must be kept"


def test_sessions_clear_runs(cli_runner: CliRunner, isolated_sessions_dir):
    """`sessions clear --runs` empties the run-states directory."""
    runs_dir = get_user_runs_dir()
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "leftover.json").write_text("{}", encoding="utf-8")

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "clear", "--runs", "--yes"])
    assert result.exit_code == 0, result.output
    assert "1 run-state(s)" in result.output
    assert not list(runs_dir.glob("*.json"))


def test_decide_fresh_interactive_prompt(tmp_path, monkeypatch):
    """The interactive prompt resumes on confirmation and restarts otherwise."""
    import rich_click as click_mod

    from rocrate_validator.cli.commands.validate import _decide_fresh
    from rocrate_validator.utils.io_helpers.output.console import Console as RVConsole

    console = RVConsole()
    state_path = tmp_path / "state.json"
    _write_interrupted_state(state_path, ["/tmp/a", "/tmp/b"], completed_count=1)

    # No interrupted state → fresh-equivalent (nothing to resume, no prompt).
    assert _decide_fresh(console, tmp_path / "missing.json", resume=False, no_resume=False, interactive=True) is False
    # Explicit flags bypass the prompt.
    assert _decide_fresh(console, state_path, resume=True, no_resume=False, interactive=True) is False
    assert _decide_fresh(console, state_path, resume=False, no_resume=True, interactive=True) is True
    # Interactive: confirm → resume; decline → fresh.
    monkeypatch.setattr(click_mod, "confirm", lambda *a, **k: True)
    assert _decide_fresh(console, state_path, resume=False, no_resume=False, interactive=True) is False
    monkeypatch.setattr(click_mod, "confirm", lambda *a, **k: False)
    assert _decide_fresh(console, state_path, resume=False, no_resume=False, interactive=True) is True
    # Non-interactive: predictable fresh run.
    assert _decide_fresh(console, state_path, resume=False, no_resume=False, interactive=False) is True


def _write_fake_session(sessions_dir, session_id, *, status, total, completed, failed, paths):
    """
    Create a minimal batch session file under ``sessions_dir`` for tests.

    ``completed``/``failed`` are the processed and the non-conformant crates;
    the header counters are derived from them so the fixture stays consistent
    with what the validator writes.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    now = "2026-06-22T10:00:00+00:00"
    data = {
        "session": {
            "version": "1.0",
            "rocrate_validator_version": "test",
            "created_at": now,
            "updated_at": now,
            "status": status,
            "total_crates": total,
            "passed_crates": completed - failed,
            "invalid_crates": failed,
            "errored_crates": 0,
            "pending_crates": total - completed,
        },
        "validation_settings": {},
        "batch_options": {"profile_identifiers": ["ro-crate-1.1"], "no_auto_profile": False},
        "crates": [
            {
                "path": p,
                "status": "completed",
                "passed": True,
                "profiles": ["ro-crate-1.1"],
                "issues": [],
                "statistics": {"total_checks": 1, "total_passed_checks": 1},
            }
            for p in paths
        ],
    }
    (sessions_dir / f"{session_id}.json").write_text(json.dumps(data), encoding="utf-8")


@fixture
def isolated_sessions_dir(tmp_path, monkeypatch):
    """Redirect the user cache dir to a tmp path so session tests stay isolated."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return get_user_sessions_dir()


def test_sessions_path(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "path"])
    assert result.exit_code == 0, result.output
    assert str(isolated_sessions_dir) in result.output


def test_single_validate_records_session_opt_in(cli_runner: CliRunner, isolated_sessions_dir):
    """A single-crate validation is recorded in the history only with --session (mode: single)."""
    crate = str(ValidROC().wrroc_paper_long_date)
    args = ["--no-interactive", "validate", crate, "--no-paging", "-p", "ro-crate-1.1", "--skip-availability-check"]
    result = cli_runner.invoke(cli, [*args, "--session"])
    assert result.exit_code == 0, result.output
    session_files = list(isolated_sessions_dir.glob("*.json"))
    assert len(session_files) == 1, "the validation must be recorded in the sessions history"
    data = json.loads(session_files[0].read_text())
    assert data["session"]["mode"] == "single"
    assert data["session"]["status"] == "completed"
    assert [c["path"] for c in data["crates"]] == [crate]
    assert data["crates"][0]["profiles"] == ["ro-crate-1.1"]

    # re-validating the same target overwrites the same session file
    result = cli_runner.invoke(cli, [*args, "--session"])
    assert result.exit_code == 0, result.output
    assert list(isolated_sessions_dir.glob("*.json")) == session_files


def test_single_validate_no_session_by_default(cli_runner: CliRunner, isolated_sessions_dir):
    """Without --session, a single-crate validation is not recorded in the history."""
    crate = str(ValidROC().wrroc_paper_long_date)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            crate,
            "--no-paging",
            "-p",
            "ro-crate-1.1",
            "--skip-availability-check",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not list(isolated_sessions_dir.glob("*.json"))


def test_no_session_flag_removed(cli_runner: CliRunner):
    """--no-session no longer exists: sessions are opt-in via --session."""
    result = cli_runner.invoke(
        cli,
        ["--no-interactive", "validate", str(ValidROC().wrroc_paper_long_date), "--no-session"],
    )
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_sessions_show_requires_id_non_interactive(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show"])
    assert result.exit_code != 0
    assert "specify a session id" in result.output.lower()


def test_sessions_show_not_found(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "nope404"])
    assert result.exit_code == 0, result.output
    assert "no session matches" in result.output.lower()


def test_validate_stats_removed(cli_runner: CliRunner):
    """`validate --stats` no longer exists: statistics live in `sessions report`."""
    result = cli_runner.invoke(
        cli,
        ["--no-interactive", "validate", "--batch", str(CRATES_DATA_PATH / "valid"), "--stats"],
    )
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_validate_then_sessions_report_last(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """The one-command CI flow: validate --session --batch, then report the last session with --last."""
    output_file = tmp_path / "report.md"
    valid_dir = str(ValidROC().wrroc_paper_long_date.parent)
    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--session",
            "--batch",
            valid_dir,
            "--batch-pattern",
            "wrroc-paper*",
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--no-resume",
        ],
    )
    assert result.exit_code == 0, result.output

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "--last", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "Validation Report" in content
    assert "wrroc-paper" in content


def test_sessions_report_last_rejects_id(cli_runner: CliRunner, isolated_sessions_dir):
    """--last and an explicit session ID are mutually exclusive."""
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "abc123", "--last"])
    assert result.exit_code != 0
    assert "not both" in result.output


def test_sessions_show_last_picks_most_recent(cli_runner: CliRunner, isolated_sessions_dir):
    """`show --last` targets the most recently updated session."""
    _write_fake_session(
        isolated_sessions_dir, "old001", status="completed", total=1, completed=1, failed=0, paths=["/data/crateOld"]
    )
    _write_fake_session(
        isolated_sessions_dir, "new001", status="completed", total=1, completed=1, failed=0, paths=["/data/crateNew"]
    )
    # Both fake sessions share the same timestamp: bump the second one so it is
    # unambiguously the most recent.
    newer = isolated_sessions_dir / "new001.json"
    data = json.loads(newer.read_text())
    data["session"]["updated_at"] = "2026-06-23T10:00:00+00:00"
    newer.write_text(json.dumps(data), encoding="utf-8")

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "--last"])
    assert result.exit_code == 0, result.output
    assert "crateNew" in result.output
    assert "crateOld" not in result.output


def test_sessions_resume_last_needs_resumable(cli_runner: CliRunner, isolated_sessions_dir):
    """`resume --last` only considers resumable sessions."""
    _write_fake_session(
        isolated_sessions_dir, "done01", status="completed", total=1, completed=1, failed=0, paths=["/data/crateA"]
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume", "--last"])
    assert result.exit_code == 0, result.output
    assert "no resumable" in result.output.lower()


def test_sessions_restart_last_without_sessions(cli_runner: CliRunner, isolated_sessions_dir):
    """`restart --last` with an empty history reports it gracefully."""
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "restart", "--last"])
    assert result.exit_code == 0, result.output
    assert "no validation sessions" in result.output.lower()


def test_sessions_report_last_without_sessions(cli_runner: CliRunner, isolated_sessions_dir):
    """--last with an empty history reports it gracefully."""
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "--last"])
    assert result.exit_code == 0, result.output
    assert "no validation sessions" in result.output.lower()


def test_sessions_show_stats(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir,
        "stat01",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/data/crateA", "/data/crateB"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "stat01", "--stats"])
    assert result.exit_code == 0, result.output
    assert "Statistics" in result.output
    assert "Outcome Summary" in result.output


def test_sessions_show_stats_reads_normalized_issues(cli_runner: CliRunner, isolated_sessions_dir):
    """The statistics renderers read self-contained issues: the checks the session
    entries name by identifier must be resolved back into objects first."""
    isolated_sessions_dir.mkdir(parents=True, exist_ok=True)
    now = "2026-06-22T10:00:00+00:00"
    data = {
        "session": {
            "version": "1.0",
            "rocrate_validator_version": "test",
            "created_at": now,
            "updated_at": now,
            "status": "completed",
            "total_crates": 2,
            "passed_crates": 1,
            "invalid_crates": 1,
            "errored_crates": 0,
            "pending_crates": 0,
        },
        "validation_settings": {},
        "batch_options": {"profile_identifiers": ["ro-crate-1.1"], "no_auto_profile": False},
        # the definition tables the issues reference by identifier
        "checks": {
            "ro-crate-1.1_1.1": {"identifier": "ro-crate-1.1_1.1", "name": "A check", "requirement": "ro-crate-1.1_1"}
        },
        "requirements": {"ro-crate-1.1_1": {"identifier": "ro-crate-1.1_1", "profile": "ro-crate-1.1"}},
        "profiles": {"ro-crate-1.1": {"identifier": "ro-crate-1.1", "name": "A profile"}},
        "crates": [
            {
                "path": "/data/crateA",
                "status": "completed",
                "passed": False,
                "profiles": ["ro-crate-1.1"],
                "issues": [{"severity": "REQUIRED", "message": "boom", "check": "ro-crate-1.1_1.1"}],
                "statistics": {"total_checks": 2, "total_passed_checks": 1, "total_failed_checks": 1},
            },
            {
                "path": "/data/crateB",
                "status": "completed",
                "passed": True,
                "profiles": ["ro-crate-1.1"],
                "issues": [],
                "statistics": {"total_checks": 2, "total_passed_checks": 2},
            },
        ],
    }
    (isolated_sessions_dir / "stat02.json").write_text(json.dumps(data), encoding="utf-8")

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "stat02", "--stats"])

    assert result.exit_code == 0, result.output
    assert "ro-crate-1.1_1.1" in result.output


def test_sessions_show_no_longer_writes_files(cli_runner: CliRunner, isolated_sessions_dir):
    """`show` is console-only: the file options moved to `sessions report`."""
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=1,
        completed=1,
        failed=0,
        paths=["/a/x"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "s1", "-o", "/tmp/out.txt"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_sessions_report_requires_id_non_interactive(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report"])
    assert result.exit_code != 0
    assert "session ID" in result.output


def test_sessions_report_output_file_text(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Write the report in text format (default, no colour) to a file."""
    output_file = tmp_path / "report.txt"
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/a/x", "/a/y"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file)])
    assert result.exit_code == 0, result.output
    assert "Report written to" in result.output
    content = output_file.read_text()
    assert "Validation Report" in content
    assert "Validation Summary" in content
    assert "Statistics" in content
    assert "Outcome Summary" in content
    # No ANSI colour codes in default text output.
    assert "\x1b[" not in content


def test_sessions_report_json_is_the_v2_report(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Reporting a stored session yields the same document `validate -f json` writes."""
    output_file = tmp_path / "report.json"
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/a/x", "/a/y"],
    )
    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-f", "json", "-o", str(output_file)]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(output_file.read_text())
    assert report["meta"]["report_schema_version"] == "2.0"
    assert report["session"]["mode"] == "batch"
    assert [crate["path"] for crate in report["crates"]] == ["/a/x", "/a/y"]


def test_sessions_report_output_file_text_with_color(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Write the report in text format with ANSI colour codes."""
    output_file = tmp_path / "report_color.txt"
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/a/x", "/a/y"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "--color"])
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "Statistics" in content
    assert "Outcome Summary" in content
    assert "\x1b[" in content


def test_sessions_report_output_file_md(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Write the report in markdown format to a file."""
    output_file = tmp_path / "report.md"
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/a/x", "/a/y"],
    )
    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "# Validation Report" in content
    # Header bullets carry the session provenance.
    assert "- **Session:**" in content
    assert "- **Profiles:** ro-crate-1.1" in content
    # Per-crate summary table before the statistics sections.
    assert "## Validation Summary" in content
    assert "| Crate | Status | Checks | Passed | Issues | Duration |" in content
    assert "## Outcome Summary" in content
    assert "| Status | Crates | Share |" in content
    assert "| **TOTAL**" in content
    assert "## Checks/Passed Combinations" in content


def test_sessions_report_stdout(cli_runner: CliRunner, isolated_sessions_dir):
    """Without -o the report goes to stdout (pipeable)."""
    _write_fake_session(
        isolated_sessions_dir,
        "s1",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/a/x", "/a/y"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "s1", "-f", "md"])
    assert result.exit_code == 0, result.output
    assert "# Validation Report" in result.output
    assert "## Validation Summary" in result.output


def _write_session_with_failures(sessions_dir, name: str = "s1") -> None:
    """Store a fake completed session with two passed and two failed crates."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    now = "2026-06-22T10:00:00+00:00"
    # The issue records carry the full serialized check (description, severity,
    # requirement), as written by real batch validations.
    check_alpha = {
        "identifier": "check-01",
        "name": "Check Alpha",
        "description": "Alpha checks the root data entity.",
        "severity": "REQUIRED",
        "requirement": {
            "identifier": "req-01",
            "name": "Requirement One",
            "description": "Requirement One constrains the root.",
        },
    }
    check_beta = {
        "identifier": "check-02",
        "name": "Check Beta",
        "description": "Beta checks the licence.",
        "severity": "OPTIONAL",
        "requirement": {
            "identifier": "req-02",
            "name": "Requirement Two",
            "description": "Requirement Two constrains the licence.",
        },
    }
    data = {
        "session": {
            "version": "1.0",
            "rocrate_validator_version": "test",
            "created_at": now,
            "updated_at": now,
            "status": "completed",
            "total_crates": 4,
            "passed_crates": 2,
            "invalid_crates": 2,
            "errored_crates": 0,
            "pending_crates": 0,
        },
        "validation_settings": {},
        "batch_options": {"profile_identifiers": ["ro-crate-1.1"], "no_auto_profile": False},
        "crates": [
            {
                "path": "/a/passed1",
                "status": "completed",
                "passed": True,
                "profiles": ["ro-crate-1.1"],
                "issues": [],
                "statistics": {"total_checks": 5, "total_passed_checks": 5},
            },
            {
                "path": "/a/passed2",
                "status": "completed",
                "passed": True,
                "profiles": ["ro-crate-1.1"],
                "issues": [],
                "statistics": {"total_checks": 5, "total_passed_checks": 5},
            },
            {
                "path": "/a/failed1",
                "status": "completed",
                "passed": False,
                "profiles": ["ro-crate-1.1"],
                "issues": [
                    {"severity": "REQUIRED", "message": "The root MUST have a name", "check": check_alpha},
                    {"severity": "OPTIONAL", "message": "The licence SHOULD be a URI", "check": check_beta},
                ],
                "statistics": {"total_checks": 5, "total_passed_checks": 3},
            },
            {
                "path": "/a/failed2",
                "status": "completed",
                "passed": False,
                "profiles": ["ro-crate-1.1"],
                "issues": [
                    {"severity": "REQUIRED", "check": check_alpha},
                ],
                "statistics": {"total_checks": 5, "total_passed_checks": 4},
            },
        ],
    }
    (sessions_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def test_sessions_report_md_with_failures(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Write the markdown report for a session with failures."""
    output_file = tmp_path / "report_fail.md"
    _write_session_with_failures(isolated_sessions_dir)

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "Crates analysed: **4**" in content
    assert "| PASSED | 2 | 50.0% |" in content
    assert "| FAILED | 2 | 50.0% |" in content
    assert "## Error-Type Distribution" in content
    assert "## Issue Attribution" in content
    # Check identifiers in the tables link to the appendix entries...
    assert "[`check-01`](#check-check-01)" in content
    # ...where each issue type (and its requirement) is described and anchored.
    assert "## Appendix: Issue Type Reference" in content
    assert '<a id="requirement-req-01"></a>`req-01` — Requirement One' in content
    assert '<a id="check-check-01"></a>`check-01` — Check Alpha' in content
    assert "**Severity:** REQUIRED" in content
    assert "Alpha checks the root data entity." in content
    assert "Requirement One constrains the root." in content
    # The issue messages only appear in the verbose report.
    assert "## Failed Crate Details" not in content

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "-f", "md", "-v"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "## Failed Crate Details" in content
    assert "### failed1" in content
    assert "The root MUST have a name" in content
    assert "The licence SHOULD be a URI" in content


def test_sessions_report_text_appendix(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """The text report also ends with the issue-type reference appendix."""
    output_file = tmp_path / "report_fail.txt"
    _write_session_with_failures(isolated_sessions_dir)

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file)])
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "Appendix: Issue Type Reference" in content
    # Identifiers match the ones used by the statistics tables (searchable),
    # each followed by its description.
    assert "check-01" in content
    assert "Alpha checks the root data entity." in content
    assert "req-02" in content
    assert "Requirement Two constrains the licence." in content


def test_sessions_report_csv(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """The csv format exports the raw session data, one row per issue."""
    import csv as _csv

    output_file = tmp_path / "report.csv"
    _write_session_with_failures(isolated_sessions_dir)

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "-f", "csv"]
    )
    assert result.exit_code == 0, result.output
    with output_file.open(encoding="utf-8-sig", newline="") as f:
        rows = list(_csv.DictReader(f))

    # 2 passed crates (1 row each, empty issue columns) + failed1 (2 issues) +
    # failed2 (1 issue) = 5 data rows covering the whole corpus.
    assert len(rows) == 5
    by_crate: dict[str, list[dict]] = {}
    for row in rows:
        by_crate.setdefault(row["crate"], []).append(row)
    assert len(by_crate["passed1"]) == 1
    assert by_crate["passed1"][0]["status"] == "PASSED"
    assert by_crate["passed1"][0]["check_identifier"] == ""
    assert len(by_crate["failed1"]) == 2

    issue_row = next(r for r in by_crate["failed1"] if r["check_identifier"] == "check-01")
    assert issue_row["status"] == "FAILED"
    assert issue_row["issue_severity"] == "REQUIRED"
    assert issue_row["check_name"] == "Check Alpha"
    assert issue_row["check_severity"] == "REQUIRED"
    assert issue_row["requirement_identifier"] == "req-01"
    assert issue_row["profiles"] == "ro-crate-1.1"
    assert issue_row["total_checks"] == "5"
    # The crates all sit directly under the common root: no source grouping.
    assert issue_row["source"] == ""


def _write_single_crate_session(sessions_dir, name: str = "s1", outcome: str = "failed") -> None:
    """
    Store a fake completed session holding one crate: ``failed`` (default,
    with full issue records), ``passed`` or ``error``.
    """
    sessions_dir.mkdir(parents=True, exist_ok=True)
    now = "2026-06-22T10:00:00+00:00"
    check_alpha = {
        "identifier": "check-01",
        "name": "Check Alpha",
        "description": "Alpha checks the root data entity.",
        "severity": "REQUIRED",
        "requirement": {
            "identifier": "req-01",
            "name": "Requirement One",
            "description": "Requirement One constrains the root.",
        },
    }
    crate: dict = {
        "path": "/a/mycrate",
        "status": "completed",
        "passed": outcome == "passed",
        "profiles": ["ro-crate-1.1"],
        "duration": 0.5,
        "size_bytes": 2048,
        "issues": [],
        "statistics": {"total_checks": 5, "total_passed_checks": 5, "total_failed_checks": 0},
    }
    if outcome == "failed":
        crate["issues"] = [
            {
                "severity": "REQUIRED",
                "message": "The root MUST have a name",
                "violatingEntity": "./",
                "violatingProperty": "http://schema.org/name",
                "check": check_alpha,
            },
            {
                "severity": "REQUIRED",
                "message": "The root MUST have a licence",
                "check": check_alpha,
            },
        ]
        crate["statistics"] = {"total_checks": 5, "total_passed_checks": 4, "total_failed_checks": 1}
    elif outcome == "error":
        crate.update(status="errored", passed=False, error="Not a valid RO-Crate", statistics=None)
    data = {
        "session": {
            "version": "1.0",
            "rocrate_validator_version": "test",
            "created_at": now,
            "updated_at": now,
            "status": "completed",
            "mode": "single",
            "total_crates": 1,
            "passed_crates": 1 if outcome == "passed" else 0,
            "invalid_crates": 1 if outcome == "failed" else 0,
            "errored_crates": 1 if outcome == "error" else 0,
            "pending_crates": 0,
        },
        "validation_settings": {},
        "batch_options": {"profile_identifiers": ["ro-crate-1.1"], "no_auto_profile": False},
        "crates": [crate],
    }
    (sessions_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def test_sessions_report_single_crate_md(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """A single-crate session gets the dedicated report, not the batch statistics."""
    output_file = tmp_path / "single.md"
    _write_single_crate_session(isolated_sessions_dir)

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "# Validation Report — mycrate" in content
    assert "- **Outcome:** **FAILED**" in content
    assert "## Checks Summary" in content
    assert "| 5 | 4 | 1 | 80.0% |" in content
    assert "Total issues: **2** — REQUIRED **2**" in content
    assert "## Failed Checks" in content
    assert "[`check-01`](#check-check-01)" in content
    assert "## Appendix: Issue Type Reference" in content
    # None of the (degenerate) population-level batch sections is present...
    assert "## Outcome Summary" not in content
    assert "## Issues Per Crate" not in content
    assert "## Slowest Crates" not in content
    assert "## Outlier Crates" not in content
    # ...and the issue messages only appear with --verbose.
    assert "## Issue Details" not in content

    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "s1", "-v", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "## Issue Details" in content
    assert "The root MUST have a name" in content
    assert "entity: ./ · property: http://schema.org/name" in content


def test_sessions_report_single_crate_text(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """The text single-crate report mirrors the markdown one."""
    output_file = tmp_path / "single.txt"
    _write_single_crate_session(isolated_sessions_dir)

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "report", "s1", "-v", "-o", str(output_file)])
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "Validation Report" in content
    assert "Checks Summary" in content
    assert "Failed Checks" in content
    assert "Issue Details" in content
    assert "The root MUST have a name" in content
    assert "Appendix: Issue Type Reference" in content
    assert "Outcome Summary" not in content


def test_sessions_report_single_crate_passed_and_error(cli_runner: CliRunner, isolated_sessions_dir, tmp_path):
    """Passed and errored single-crate sessions render their degenerate cases."""
    _write_single_crate_session(isolated_sessions_dir, name="ok1", outcome="passed")
    output_file = tmp_path / "single_ok.md"
    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "ok1", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "- **Outcome:** **PASSED**" in content
    assert "No issues reported." in content
    assert "## Failed Checks" not in content

    _write_single_crate_session(isolated_sessions_dir, name="err1", outcome="error")
    output_file = tmp_path / "single_err.md"
    result = cli_runner.invoke(
        cli, ["--no-interactive", "sessions", "report", "err1", "-o", str(output_file), "-f", "md"]
    )
    assert result.exit_code == 0, result.output
    content = output_file.read_text()
    assert "- **Outcome:** **ERROR**" in content
    assert "The crate could not be validated: Not a valid RO-Crate" in content
    assert "## Checks Summary" not in content


def test_sessions_show_verbose_console_details(cli_runner: CliRunner, isolated_sessions_dir):
    """`sessions show -v` renders the failed-crate details on the console."""
    _write_session_with_failures(isolated_sessions_dir)
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "s1", "-v"])
    assert result.exit_code == 0, result.output
    assert "Failed crate details:" in result.output
    assert "check-01" in result.output


def test_summary_source_column_only_for_multi_source_sessions(cli_runner: CliRunner, isolated_sessions_dir):
    """The Source column appears only when the crates come from different collections."""
    # Flat corpus: every crate is a direct child of the scan root — the source
    # would be the same on every row, so the column is omitted.
    _write_fake_session(
        isolated_sessions_dir,
        "flat01",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/data/crateA", "/data/crateB"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "flat01"])
    assert result.exit_code == 0, result.output
    assert "Source" not in result.output

    # Nested corpus (<root>/<source>/<crate>): the parent path below the common
    # root distinguishes the collections, so the column is shown.
    _write_fake_session(
        isolated_sessions_dir,
        "multi01",
        status="completed",
        total=3,
        completed=3,
        failed=0,
        paths=["/data/repoA/crate1", "/data/repoA/crate2", "/data/repoB/deeper/crate3"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "multi01"])
    assert result.exit_code == 0, result.output
    assert "Source" in result.output
    assert "repoA" in result.output
    assert "repoB/deeper" in result.output


def test_validate_batch_nested_corpus(cli_runner: CliRunner, tmp_path, isolated_sessions_dir):
    """--batch descends into a nested corpus and the summary shows the Source column."""
    import shutil

    src = ValidROC().wrroc_paper_long_date
    corpus = tmp_path / "corpus"
    shutil.copytree(src, corpus / "repoA" / "crate1")
    shutil.copytree(src, corpus / "repoB" / "crate2")

    result = cli_runner.invoke(
        cli,
        [
            "--no-interactive",
            "validate",
            "--batch",
            str(corpus),
            "--profile-identifier",
            "ro-crate-1.1",
            "--no-paging",
            "--no-resume",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "crate1" in result.output and "crate2" in result.output
    assert "Source" in result.output
    assert "repoA" in result.output and "repoB" in result.output


def test_sessions_show_renders_session(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir,
        "sess001",
        status="completed",
        total=2,
        completed=2,
        failed=0,
        paths=["/data/crateA", "/data/crateB"],
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "show", "sess001"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Header, per-crate list (relative names + profile) and summary are all shown.
    assert "Profiles" in out
    assert "crateA" in out and "crateB" in out
    assert "ro-crate-1.1" in out
    assert "Validation Summary" in out
    assert "passed validation" in out.lower()


def test_sessions_list_empty(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "list"])
    assert result.exit_code == 0, result.output
    assert "no validation sessions" in result.output.lower()


def test_sessions_list_and_json(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir, "aaa111", status="completed", total=2, completed=2, failed=0, paths=["/a/x", "/a/y"]
    )
    _write_fake_session(
        isolated_sessions_dir, "bbb222", status="interrupted", total=3, completed=1, failed=1, paths=["/b/x"]
    )

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "list"])
    assert result.exit_code == 0, result.output
    assert "Validation sessions (2)" in result.output

    result_json = cli_runner.invoke(cli, ["--no-interactive", "sessions", "ls", "--json"])
    assert result_json.exit_code == 0, result_json.output
    data = json.loads(result_json.output)
    assert {d["id"] for d in data} == {"aaa111", "bbb222"}

    filtered = cli_runner.invoke(cli, ["--no-interactive", "sessions", "list", "--status", "interrupted"])
    assert "Validation sessions (1)" in filtered.output


def test_sessions_clear_requires_scope(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "clear"])
    assert result.exit_code != 0
    assert "specify" in result.output.lower()


def test_sessions_clear_by_id(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir, "abc123def", status="completed", total=1, completed=1, failed=0, paths=["/a/x"]
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "clear", "abc123", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 session" in result.output
    assert not (isolated_sessions_dir / "abc123def.json").exists()


def test_sessions_clear_completed_only(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir, "done1", status="completed", total=1, completed=1, failed=0, paths=["/a/x"]
    )
    _write_fake_session(
        isolated_sessions_dir, "wip1", status="interrupted", total=2, completed=1, failed=0, paths=["/b/x"]
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "rm", "--completed", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (isolated_sessions_dir / "done1.json").exists()
    assert (isolated_sessions_dir / "wip1.json").exists()


def test_sessions_clear_non_interactive_requires_yes(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir, "keep1", status="completed", total=1, completed=1, failed=0, paths=["/a/x"]
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "clear", "--all"])
    assert result.exit_code == 1
    assert "--yes" in result.output
    # Nothing removed without confirmation.
    assert (isolated_sessions_dir / "keep1.json").exists()


def _make_interrupted_session(sessions_dir, session_id, crate_paths, completed_count, *, profile="ro-crate-1.1"):
    """Persist an interrupted batch session with the first crates marked completed."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{session_id}.json"
    settings = ValidationSettings.parse(
        {"rocrate_uri": crate_paths[0], "profile_identifier": profile, "requirement_severity": "REQUIRED"}
    )
    session = BatchSession(
        validation_settings=settings.to_dict(),
        crate_paths=crate_paths,
        session_path=session_file,
    )
    for i in range(completed_count):
        session.crates[i].status = "completed"
        session.crates[i].passed = True
    session.status = "interrupted"
    session.profile_identifiers = [profile]
    session.save()
    return session_file


def test_sessions_resume_requires_id_non_interactive(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume"])
    assert result.exit_code != 0
    assert "specify a session id" in result.output.lower()


def test_sessions_resume_not_found(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume", "nope404"])
    assert result.exit_code == 0, result.output
    assert "no session matches" in result.output.lower()


def test_sessions_resume_already_completed(cli_runner: CliRunner, isolated_sessions_dir):
    _write_fake_session(
        isolated_sessions_dir, "done999", status="completed", total=1, completed=1, failed=0, paths=["/a/x"]
    )
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume", "done999"])
    assert result.exit_code == 0, result.output
    assert "nothing to resume" in result.output.lower()


def test_sessions_resume_completes_interrupted(cli_runner: CliRunner, isolated_sessions_dir):
    valid_dir = ValidROC().wrroc_paper_long_date.parent
    c1 = str((valid_dir / "wrroc-paper").resolve())
    c2 = str((valid_dir / "wrroc-paper-long-date").resolve())
    session_file = _make_interrupted_session(isolated_sessions_dir, "feedface01", [c1, c2], completed_count=1)

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "resume", "feedface"])
    assert result.exit_code == 0, result.output
    assert "passed validation" in result.output.lower()

    data = json.loads(session_file.read_text())
    assert data["session"]["status"] == "completed"
    assert data["session"]["passed_crates"] == 2


def test_sessions_restart_requires_id_non_interactive(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "restart"])
    assert result.exit_code != 0
    assert "specify a session id" in result.output.lower()


def test_sessions_restart_not_found(cli_runner: CliRunner, isolated_sessions_dir):
    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "restart", "nope404"])
    assert result.exit_code == 0, result.output
    assert "no session matches" in result.output.lower()


def test_sessions_restart_revalidates_completed_session(cli_runner: CliRunner, isolated_sessions_dir):
    """`sessions restart` re-runs a completed session from scratch with the same criteria."""
    valid_dir = ValidROC().wrroc_paper_long_date.parent
    c1 = str((valid_dir / "wrroc-paper").resolve())
    c2 = str((valid_dir / "wrroc-paper-long-date").resolve())
    # A completed session with placeholder statistics: restart must overwrite
    # them with the real validation outcome.
    _write_fake_session(
        isolated_sessions_dir, "cafe0001", status="completed", total=2, completed=2, failed=0, paths=[c1, c2]
    )
    session_file = isolated_sessions_dir / "cafe0001.json"

    result = cli_runner.invoke(cli, ["--no-interactive", "sessions", "restart", "cafe0001"])
    assert result.exit_code == 0, result.output
    assert "passed validation" in result.output.lower()

    data = json.loads(session_file.read_text())
    assert data["session"]["status"] == "completed"
    assert data["session"]["passed_crates"] == 2
    assert data["session"]["invalid_crates"] == 0
    # the placeholder statistics written by the fake session have been replaced
    # by the real ones (a real run counts far more than one check per crate)
    for crate in data["crates"]:
        assert crate["statistics"]["total_checks"] > 1
