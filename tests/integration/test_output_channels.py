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
The standard output carries the requested document, and nothing else.

Everything the tool has to *say* about a run — logs, warnings, progress — is a
notice and belongs on the error stream, so that ``-f json`` can be piped
straight into a parser however much the run had to report along the way.

These run the CLI as a **real subprocess**, which is not a stylistic choice:
``click.testing.CliRunner`` invokes the command in-process, and an ``atexit``
hook (which is how the logs used to reach the terminal) only fires when the
*interpreter* exits — at the very end of the pytest session, in pytest's own
output, where no assertion can see it. An in-process test cannot observe this
class of defect at all.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys

import pytest

from tests.ro_crates import VALID_CRATES_DATA_PATH

# Declares conformance to a profile the validator does not implement, so the
# run logs a WARNING while producing a perfectly ordinary report. This is the
# cheapest way to have something on both channels at once.
CRATE_LOGGING_A_WARNING = VALID_CRATES_DATA_PATH / "process-run-crate"
LOGGED_WARNING = "could not be verified"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI in its own process, with the two streams kept apart."""
    return subprocess.run(
        [sys.executable, "-c", "from rocrate_validator.cli import cli; cli()", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "COLUMNS": "200", "ROCRATE_VALIDATOR_AUTO_WARM": "0"},
    )


def parse(output_format: str, text: str):
    """Parse ``text`` in the given format, failing the test if it is not one."""
    if output_format == "json":
        return json.loads(text)
    return list(csv.DictReader(io.StringIO(text)))


@pytest.mark.parametrize("output_format", ["json", "csv"])
def test_a_logged_warning_stays_off_the_document(output_format: str):
    """A WARNING during the run must not end up inside the report."""
    result = run_cli("-y", "validate", "-f", output_format, "--no-paging", str(CRATE_LOGGING_A_WARNING))

    document = parse(output_format, result.stdout)
    assert document, "the report must be on stdout"
    assert LOGGED_WARNING not in result.stdout, "a log line ended up in the document"
    assert LOGGED_WARNING in result.stderr, "the warning must still reach the user, on stderr"


def test_debug_logging_never_touches_the_document():
    """``--debug`` produces megabytes of logs; none of them belong on stdout."""
    result = run_cli("-y", "--debug", "validate", "-f", "json", "--no-paging", str(CRATE_LOGGING_A_WARNING))

    json.loads(result.stdout)  # raises if a single log line leaked
    assert len(result.stderr) > len(result.stdout), "the debug logs must be on stderr"


def test_the_profile_fallback_notice_goes_to_stderr():
    """The notice is printed before the report, so on stdout it would break every parser."""
    result = run_cli(
        "-y",
        "validate",
        "--no-auto-profile",
        "-f",
        "json",
        "--no-paging",
        str(CRATE_LOGGING_A_WARNING),
    )

    json.loads(result.stdout)
    assert "base `ro-crate` profile will be used" in result.stderr


def test_a_report_written_to_a_file_leaves_stdout_empty(tmp_path):
    """With ``-o`` there is no document to carry: stdout has nothing to say."""
    output_file = tmp_path / "report.json"
    result = run_cli(
        "-y", "validate", "-f", "json", "-o", str(output_file), "--no-paging", str(CRATE_LOGGING_A_WARNING)
    )

    assert json.loads(output_file.read_text()), "the report must be in the file"
    assert result.stdout == "", "the report went to a file, so stdout carries no document"
    assert LOGGED_WARNING in result.stderr
