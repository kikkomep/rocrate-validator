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
Snapshot tests of the machine-readable reports (JSON and CSV).

These freeze the *documents* the CLI produces today, single and batch, so the
output-unification refactor can prove that the opt-in legacy schema still
yields exactly the same reports the current consumers parse. Without them the
compatibility claim would rest on assertions scattered across the suite, which
drift silently as soon as a field is added elsewhere.

The comparison is on the **parsed document**, not on the byte stream: the
reports go through a Rich console whose rendering depends on the terminal
width and colour support, so the bytes are not stable across environments.
Each report is parsed and normalised for the values that legitimately vary
between runs and machines (paths, timings, tool version).

To regenerate the snapshot files after an intentional format change::

    SNAPSHOT_UPDATE=1 pytest tests/integration/test_output_snapshots.py
"""

import csv
import io
import json
import os
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from rocrate_validator.cli.main import cli
from rocrate_validator.utils.versioning import get_version
from tests.conftest import SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER
from tests.ro_crates import CRATES_DATA_PATH, ValidROC

CURRENT_PATH = Path(__file__).resolve().parent
SNAPSHOT_DIR = (CURRENT_PATH / ".." / "data" / "snapshots" / "output").resolve()

# A crate that passes and one that reports a single issue, so every branch of
# the report (passing crate, failing crate, issue payload) is covered by the
# smallest possible corpus.
PASSING_CRATE = ValidROC().wrroc_paper_long_date
FAILING_CRATE = ValidROC().rocrate_with_at_base_set

BASE_OPTS = [
    "-p",
    "ro-crate-1.1",
    "--no-paging",
    "--skip-availability-check",
    "--skip-checks",
    SKIP_LOCAL_DATA_ENTITY_EXISTENCE_CHECK_IDENTIFIER,
]

# Values that change from run to run or from machine to machine, replaced by a
# placeholder before the comparison. Keyed by the JSON property name.
VOLATILE_KEYS = (
    "duration",
    "total_validation_time",
    "started_at",
    "finished_at",
    "created_at",
    "updated_at",
)

# scenario -> (target selector, extra CLI options, snapshot file name)
#
# The `legacy` scenarios are the compatibility contract: their snapshot files were
# captured before the unification, from the CLI that had no --json-schema at
# all. They must keep matching byte for byte through every change to the v2
# report — that is the whole point of the opt-in schema.
#
# One deliberate deviation: `validation_settings.rocrate_uri` used to hold the
# repr of an unbound property object (a memory address) in batch reports, and is
# now null — a placeholder nobody could depend on, fixed at its source.
LEGACY = ["--json-schema", "legacy"]
SCENARIOS = {
    "single-json": ("crate", ["-f", "json", *LEGACY], "single-json.json"),
    "single-json-verbose": ("crate", ["-f", "json", "-v", *LEGACY], "single-json-verbose.json"),
    "batch-json": ("collection", ["-f", "json", *LEGACY], "batch-json.json"),
    "batch-json-verbose": ("collection", ["-f", "json", "-v", *LEGACY], "batch-json-verbose.json"),
    "batch-csv": ("collection", ["-f", "csv"], "batch-csv.csv"),
    "single-csv": ("crate", ["-f", "csv"], "single-csv.csv"),
    "single-json-v2": ("crate", ["-f", "json"], "single-json-v2.json"),
    "single-json-v2-verbose": ("crate", ["-f", "json", "-v"], "single-json-v2-verbose.json"),
    "batch-json-v2": ("collection", ["-f", "json"], "batch-json-v2.json"),
    "batch-json-v2-verbose": ("collection", ["-f", "json", "-v"], "batch-json-v2-verbose.json"),
}


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> dict[str, Path]:
    """A collection of two crates (one passing, one failing) and a single crate."""
    root = tmp_path_factory.mktemp("snapshots")
    collection = root / "collection"
    collection.mkdir()
    shutil.copytree(PASSING_CRATE, collection / "crate-passing")
    shutil.copytree(FAILING_CRATE, collection / "crate-failing")
    return {"collection": collection, "crate": collection / "crate-failing"}


def _run(target: Path, extra_opts: list[str], output_file: Path) -> None:
    args = [
        "--no-interactive",
        "validate",
        str(target),
        *BASE_OPTS,
        *extra_opts,
        "-o",
        str(output_file),
    ]
    result = CliRunner().invoke(cli, args)
    # The failing crate makes the validation exit non-zero; only a crash matters.
    assert result.exit_code in (0, 1), result.output
    assert output_file.exists(), f"no report written for {args}: {result.output}"


def _path_replacements(corpus: dict[str, Path]) -> list[tuple[str, str]]:
    """Absolute paths leaking into the reports, longest first so nesting works."""
    replacements = [
        (str(corpus["collection"]), "<collection>"),
        (str(CRATES_DATA_PATH), "<crates>"),
        (str(Path(__file__).resolve().parents[2] / "rocrate_validator" / "profiles"), "<profiles>"),
        (os.environ.get("XDG_CACHE_HOME", "~/.cache"), "<cache>"),
    ]
    return sorted(replacements, key=lambda pair: len(pair[0]), reverse=True)


def _normalise_text(value: str, replacements: list[tuple[str, str]]) -> str:
    for actual, placeholder in replacements:
        value = value.replace(actual, placeholder)
    # The tool version is a git describe string, different in every checkout.
    value = value.replace(get_version(), "<version>")
    # Batch reports leak the repr of an unbound property, memory address included.
    value = re.sub(r"<property object at 0x[0-9a-f]+>", "<property object>", value)
    # ``violatingProperty`` sometimes carries an rdflib blank-node label, whose
    # id is drawn afresh on every parse of the data graph.
    return re.sub(r"\bn[0-9a-f]{32}b\d+\b", "<bnode>", value)


def _normalise(node, replacements: list[tuple[str, str]]):
    if isinstance(node, dict):
        return {
            key: "<volatile>" if key in VOLATILE_KEYS else _normalise(value, replacements)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_normalise(item, replacements) for item in node]
    if isinstance(node, str):
        return _normalise_text(node, replacements)
    return node


def _normalise_csv(text: str, replacements: list[tuple[str, str]]) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    duration = header.index("duration_s")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows[1:]:
        normalised = [_normalise_text(cell, replacements) for cell in row]
        normalised[duration] = "<volatile>"
        writer.writerow(normalised)
    return out.getvalue()


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_report_matches_snapshot(scenario: str, corpus: dict[str, Path], tmp_path: Path) -> None:
    """The report produced today matches the committed snapshot document."""
    target_key, extra_opts, snapshot_name = SCENARIOS[scenario]
    output_file = tmp_path / f"{scenario}.out"
    _run(corpus[target_key], extra_opts, output_file)

    replacements = _path_replacements(corpus)
    raw = output_file.read_text(encoding="utf-8-sig" if snapshot_name.endswith(".csv") else "utf-8")
    snapshot_path = SNAPSHOT_DIR / snapshot_name

    if snapshot_name.endswith(".csv"):
        actual_text = _normalise_csv(raw, replacements)
    else:
        actual_text = json.dumps(_normalise(json.loads(raw), replacements), indent=2, sort_keys=True) + "\n"

    if os.environ.get("SNAPSHOT_UPDATE"):
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(actual_text)
        pytest.skip(f"Snapshot regenerated at {snapshot_path}; review and commit it.")

    assert snapshot_path.exists(), (
        f"Snapshot not found at {snapshot_path}. "
        "Generate it with: SNAPSHOT_UPDATE=1 pytest tests/integration/test_output_snapshots.py"
    )
    assert actual_text == snapshot_path.read_text(), (
        f"The {scenario} report diverged from its snapshot. "
        "If the change is intentional, regenerate with SNAPSHOT_UPDATE=1."
    )


def test_v2_crate_item_is_identical_in_both_modes() -> None:
    """
    The reason the unification exists: the same crate yields the same
    ``crates[]`` item whether it was validated on its own or within a batch.
    """
    single = json.loads((SNAPSHOT_DIR / "single-json-v2.json").read_text())
    batch = json.loads((SNAPSHOT_DIR / "batch-json-v2.json").read_text())
    validated_alone = single["crates"][0]
    within_batch = next(crate for crate in batch["crates"] if crate["name"] == validated_alone["name"])
    assert validated_alone == within_batch


def test_v2_envelope_is_identical_in_both_modes() -> None:
    """Single and batch share the envelope; only mode and crate count differ."""
    single = json.loads((SNAPSHOT_DIR / "single-json-v2.json").read_text())
    batch = json.loads((SNAPSHOT_DIR / "batch-json-v2.json").read_text())
    assert sorted(single) == sorted(batch)
    assert single["meta"] == batch["meta"]
    assert sorted(single["session"]) == sorted(batch["session"])
    assert single["session"]["mode"] == "single"
    assert batch["session"]["mode"] == "batch"
