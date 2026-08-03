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

from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import cast

import rich_click as click
from rich.padding import Padding
from rich.rule import Rule

from rocrate_validator import constants, services
from rocrate_validator.cli.commands.errors import handle_error
from rocrate_validator.cli.main import cli
from rocrate_validator.cli.ui.text.validate import (
    BatchValidationCommandView,
    FooterRow,
    ValidationCommandView,
    format_profile_selection,
    render_batch_footer,
    render_batch_header,
    render_details_block,
)
from rocrate_validator.errors import ROCrateInvalidURIError
from rocrate_validator.models import (
    BatchValidationResult,
    Severity,
    ValidationCache,
    ValidationResult,
    ValidationSession,
    ValidationSettings,
)
from rocrate_validator.utils import log as logging
from rocrate_validator.utils.io_helpers.input import get_single_char, multiple_choice
from rocrate_validator.utils.io_helpers.output.console import Console
from rocrate_validator.utils.io_helpers.output.csv_report import write_report_csv
from rocrate_validator.utils.io_helpers.output.json import JSONOutputFormatter
from rocrate_validator.utils.io_helpers.output.json.fanout import split_documents
from rocrate_validator.utils.io_helpers.output.json.report import build_report, dump_json
from rocrate_validator.utils.io_helpers.output.text import TextOutputFormatter
from rocrate_validator.utils.io_helpers.output.text.layout.report import LiveTextProgressLayout, get_app_header_rule
from rocrate_validator.utils.io_helpers.output.text.statistics import render_issue_reference
from rocrate_validator.utils.paths import get_profiles_path, get_user_sessions_dir
from rocrate_validator.utils.uri import URI, validate_rocrate_uri

# set the default profiles path
DEFAULT_PROFILES_PATH = get_profiles_path()

# set up logging
logger = logging.getLogger(__name__)

# Organise the (long) list of `validate` options into labelled sections in the
# `--help` output. Options not listed here are shown under a default group.
# The key is matched against the command path with fnmatch, so the leading
# wildcard makes it work regardless of the program name (entry point, `python -m`,
# or the test runner). Applied via the command's own ``rich_config`` below.
_VALIDATE_OPTION_GROUPS = {
    "* validate": [
        {
            "name": "Batch validation",
            "options": [
                "--batch",
                "--batch-pattern",
            ],
        },
        {
            "name": "Sessions & resume",
            "options": [
                "--session",
                "--resume",
                "--no-resume",
            ],
        },
        {
            "name": "Profiles",
            "options": [
                "--profile-identifier",
                "--no-auto-profile",
                "--disable-profile-inheritance",
                "--profiles-path",
                "--extra-profiles-path",
            ],
        },
        {
            "name": "Requirements & checks",
            "options": [
                "--requirement-severity",
                "--requirement-severity-only",
                "--skip-checks",
                "--metadata-only",
                "--fail-fast",
                "--relative-root-path",
                "--creation-time",
                "--enforce-availability",
                "--skip-availability-check",
            ],
        },
        {
            "name": "Output",
            "options": [
                "--output-format",
                "--output-file",
                "--json-schema",
                "--split-per-crate",
                "--output-line-width",
                "--verbose",
                "--no-paging",
            ],
        },
        {
            "name": "Cache & network",
            "options": [
                "--cache-max-age",
                "--cache-path",
                "--no-cache",
                "--offline",
            ],
        },
    ],
}


def validate_uri(ctx, param, value):  # pylint: disable=unused-argument
    """
    Validate that each positional value is a usable RO-Crate path or URI.

    ``ctx`` is part of the click callback signature but is not used here.
    The argument is variadic, so ``value`` is a tuple of URIs.
    """
    for uri in value or ():
        try:
            validate_rocrate_uri(uri)
        except ROCrateInvalidURIError as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception("Invalid RO-Crate URI provided: %s", uri)
            raise click.BadParameter(e.message, param=param) from e
    return value


@cli.command("validate")
@click.rich_config(
    help_config=click.RichHelpConfiguration(
        text_markup="rich",
        option_groups=_VALIDATE_OPTION_GROUPS,  # type: ignore[arg-type]
    )
)
@click.argument("rocrate-uri", callback=validate_uri, nargs=-1)
@click.option(
    "-rr",
    "--relative-root-path",
    help="Use root-relative paths for all file references in the RO-Crate",
    default=None,
    show_default=True,
)
@click.option(
    "-m",
    "--metadata-only",
    is_flag=True,
    help="Validate the metadata only, without checking the crate's data entities",
    default=False,
    show_default=True,
)
@click.option(
    "-ff",
    "--fail-fast",
    is_flag=True,
    help="Stop the validation at the first failed check",
    default=False,
    show_default=True,
)
@click.option(
    "--creation-time",
    is_flag=True,
    help=(
        "Validate as at crate-creation time: referenced resources are expected "
        "to be available (enables the availability checks)"
    ),
    default=False,
    show_default=True,
)
@click.option(
    "--enforce-availability",
    is_flag=True,
    help="Always run the availability checks on web-based data entities",
    default=False,
    show_default=True,
)
@click.option(
    "--skip-availability-check",
    is_flag=True,
    help="Skip availability checks for web-based data entities",
    default=False,
    show_default=True,
)
@click.option(
    "--profiles-path",
    type=click.Path(exists=True),
    default=DEFAULT_PROFILES_PATH,
    show_default=True,
    help="Path containing the profiles files",
)
@click.option(
    "--extra-profiles-path",
    type=click.Path(exists=True),
    default=None,
    show_default=True,
    help="Path containing additional user profiles files",
)
@click.option(
    "-p",
    "--profile-identifier",
    multiple=True,
    type=click.STRING,
    default=None,
    show_default=True,
    metavar="Profile-ID",
    help="Identifier of the profile to use for validation",
)
@click.option(
    "-np",
    "--no-auto-profile",
    is_flag=True,
    help="Disable automatic detection of the profile to use for validation",
    default=False,
    show_default=True,
)
@click.option(
    "-nh",
    "--disable-profile-inheritance",
    is_flag=True,
    help="Disable inheritance of profiles",
    default=False,
    show_default=True,
)
@click.option(
    "-l",
    "--requirement-severity",
    type=click.Choice([s.name for s in Severity], case_sensitive=False),
    default=Severity.REQUIRED.name,
    show_default=True,
    help="Severity of the requirements to validate",
)
@click.option(
    "-lo",
    "--requirement-severity-only",
    is_flag=True,
    help="Validate only the requirements of the specified severity (no requirements with lower severity)",
    default=False,
    show_default=True,
)
@click.option(
    "-s",
    "--skip-checks",
    multiple=True,
    type=click.STRING,
    default=None,
    show_default=True,
    metavar="Fully-Qualified-Check-IDs",
    help=(
        "Comma-separated list of check identifiers to skip (may be given multiple times). "
        "Use the fully-qualified form <Profile-ID>_<Requirement#>.<Check#>, "
        "e.g. [bold cyan]ro-crate-1.1_12.1[/bold cyan]; list the identifiers with "
        "[bold orange1]rocrate-validator profiles describe <Profile-ID> -v[/bold orange1]"
    ),
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show the detailed validation report (in batch mode, the details of every failed crate)",
    default=False,
    show_default=True,
)
@click.option(
    "--no-paging",
    is_flag=True,
    help="Disable pagination of the validation details",
    default=False,
    show_default=True,
    hidden=sys.platform == "win32",
)
@click.option(
    "-f",
    "--output-format",
    type=click.Choice(["text", "csv", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help=("Output format of the validation report; [bold]csv[/bold] is the raw data, one row per reported issue"),
)
@click.option(
    "-o",
    "--output-file",
    type=click.Path(path_type=Path),
    default=None,
    show_default=True,
    help="Path to the output file for the validation report",
)
@click.option(
    "-d",
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    show_default=False,
    help=(
        "Base directory for the report: with [bold]--split-per-crate[/bold], each crate and "
        "the manifest go there; otherwise [bold]--output-file[/bold] (when relative) is "
        "resolved against it"
    ),
)
@click.option(
    "--json-schema",
    type=click.Choice(["v2", "legacy"], case_sensitive=False),
    default="v2",
    show_default=True,
    help=(
        "Schema of the JSON report: [bold]v2[/bold] has the same shape for single and batch "
        "validations, [bold]legacy[/bold] reproduces the pre-v2 report of each mode. "
        "Ignored by the other output formats"
    ),
)
@click.option(
    "--split-per-crate",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "Write one JSON report per crate plus an [bold]index.json[/bold] manifest, instead of a "
        "single document. Reports go to [bold]--output-dir[/bold] (default: [bold]validation-report/[/bold])"
    ),
)
@click.option(
    "-w",
    "--output-line-width",
    type=click.INT,
    default=120,
    show_default=True,
    help="Line width of the report when written to a file",
)
@click.option(
    "--cache-max-age",
    type=click.INT,
    default=constants.DEFAULT_HTTP_CACHE_MAX_AGE,
    show_default=True,
    help="Maximum age of the HTTP cache in seconds ([bold green]-1[/bold green] for no expiration)",
)
@click.option(
    "--cache-path",
    type=click.Path(),
    default=None,
    show_default=True,
    help="Path to the HTTP cache directory",
)
@click.option(
    "-nc",
    "--no-cache",
    is_flag=True,
    help=(
        "Disable the HTTP cache entirely: every request goes to the network "
        "and nothing is persisted. Incompatible with [bold]--offline[/bold]."
    ),
    default=False,
    show_default=True,
)
@click.option(
    "--offline",
    is_flag=True,
    help=(
        "Offline mode: HTTP requests are served only from the cache. "
        "Pre-populate the cache with [bold]rocrate-validator cache warm[/bold]."
    ),
    default=False,
    show_default=True,
)
# Batch mode options
@click.option(
    "-b",
    "--batch",
    is_flag=True,
    help=(
        "Force batch mode: scan every [bold]RO-CRATE-URI[/bold] directory for the crates it "
        "contains (batch mode is otherwise auto-detected from the input)"
    ),
    default=False,
    show_default=True,
)
@click.option(
    "--batch-pattern",
    type=click.STRING,
    default="*",
    show_default=True,
    help="Glob pattern filtering the crate names in batch mode (intermediate directories are not matched)",
)
# Sessions & resume options
@click.option(
    "-S",
    "--session",
    "session",
    is_flag=True,
    default=False,
    help=(
        "Record this validation as a permanent session, browsable with "
        "[bold orange1]sessions list/show/report[/bold orange1]. The session is "
        "auto-named from a hash of the target and criteria; use "
        "[bold]--session-name[/bold] to give it a mnemonic name"
    ),
)
@click.option(
    "--session-name",
    "session_name",
    default=None,
    metavar="NAME",
    help=(
        "Name the recorded session [bold]sessions/<NAME>.json[/bold] instead of "
        "the auto-generated hash. Implies [bold]--session[/bold]"
    ),
)
@click.option(
    "--resume",
    is_flag=True,
    help=(
        "Resume the interrupted run matching this command (same target, profiles and severity), "
        "when one exists; start a fresh validation otherwise"
    ),
    default=False,
    show_default=True,
)
@click.option(
    "--no-resume",
    is_flag=True,
    help=(
        "Never resume: ignore any interrupted run matching this command and "
        "re-validate every RO-Crate from scratch (no prompt in interactive mode)"
    ),
    default=False,
    show_default=True,
)
@click.pass_context
# The CLI command surfaces every validation option as a parameter; pylint counts
# those arguments as locals, so the limit is not meaningful here.
# pylint: disable-next=too-many-locals
def validate(  # noqa: C901, PLR0914
    ctx,
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    extra_profiles_path: Path | None = None,
    profile_identifier: tuple[str, ...] = (),
    metadata_only: bool = False,
    creation_time: bool = False,
    enforce_availability: bool = False,
    skip_availability_check: bool = False,
    no_auto_profile: bool = False,
    disable_profile_inheritance: bool = False,
    requirement_severity: str = Severity.REQUIRED.name,
    requirement_severity_only: bool = False,
    skip_checks: list[str] | None = None,
    rocrate_uri: tuple[str, ...] = (),
    relative_root_path: Path | None = None,
    fail_fast: bool = False,
    no_paging: bool = False,
    verbose: bool = False,
    output_format: str = "text",
    output_file: Path | None = None,
    output_dir: Path | None = None,
    output_line_width: int | None = None,
    json_schema: str = "v2",
    split_per_crate: bool = False,
    cache_max_age: int = constants.DEFAULT_HTTP_CACHE_MAX_AGE,
    cache_path: Path | None = None,
    no_cache: bool = False,
    offline: bool = False,
    batch: bool = False,
    batch_pattern: str = "*",
    session: bool = False,
    session_name: str | None = None,
    resume: bool = False,
    no_resume: bool = False,
):
    """
    [magenta]rocrate-validator:[/magenta] Validate RO-Crates against one or more profiles (single crate or batch)
    """
    console: Console = ctx.obj["console"]
    pager = ctx.obj["pager"]
    interactive = ctx.obj["interactive"]
    # Get the no_paging flag
    enable_pager = not no_paging
    # override the enable_pager flag if the interactive flag is False
    if not interactive or sys.platform == "win32":
        enable_pager = False

    # The positional argument is variadic: no argument defaults to the current
    # directory, one argument is auto-detected (single crate vs collection),
    # several arguments are an explicit list validated in batch mode.
    rocrate_uris = list(rocrate_uri) or ["."]

    # -S/--session opts into a permanent session; --session-name names it (and
    # implies -S). Reduce the two flags to the tri-state the rest of the command
    # consumes: None (no session), "" (auto-named session), or the given name.
    if session_name is not None:
        session_opt: str | None = session_name
    elif session:
        session_opt = ""
    else:
        session_opt = None

    _log_validation_inputs(
        profiles_path=profiles_path,
        extra_profiles_path=extra_profiles_path,
        profile_identifier=profile_identifier,
        requirement_severity=requirement_severity,
        requirement_severity_only=requirement_severity_only,
        disable_profile_inheritance=disable_profile_inheritance,
        rocrate_uri=rocrate_uris,
        fail_fast=fail_fast,
        cache_max_age=cache_max_age,
        cache_path=cache_path,
        no_cache=no_cache,
        offline=offline,
    )

    detected = _preflight_input_checks(
        console,
        rocrate_uris,
        offline=offline,
        no_cache=no_cache,
        resume=resume,
        no_resume=no_resume,
        batch=batch,
        batch_pattern=batch_pattern,
        session_opt=session_opt,
    )

    skip_checks_list = _parse_skip_checks(skip_checks)

    try:
        # Validation settings
        validation_settings = {
            "profiles_path": profiles_path,
            "extra_profiles_path": extra_profiles_path,
            "profile_identifier": profile_identifier,
            "requirement_severity": requirement_severity,
            "requirement_severity_only": requirement_severity_only,
            "disable_inherited_profiles_issue_reporting": disable_profile_inheritance,
            # The single-crate target, or a placeholder for (possibly empty)
            # batch runs, where the URI is set per crate during validation.
            "rocrate_uri": detected.crate_paths[0] if detected.crate_paths else rocrate_uris[0],
            "rocrate_relative_root_path": relative_root_path,
            "abort_on_first": fail_fast,
            "skip_checks": skip_checks_list,
            "metadata_only": metadata_only,
            "cache_max_age": cache_max_age if not no_cache else -1,
            "cache_path": cache_path,
            "offline": offline,
            "no_cache": no_cache,
            # When offline is requested, remote crate fetching must use the cache
            # instead of the "disable download" short-circuit.
            "disable_remote_crate_download": not offline,
            "creation_time": creation_time,
            "enforce_availability": enforce_availability,
            "skip_availability_check": skip_availability_check,
        }

        _check_output_options(
            output_format=output_format,
            split_per_crate=split_per_crate,
        )

        output_file = _resolve_output_destination(
            console,
            output_file=output_file,
            output_dir=output_dir,
            split_per_crate=split_per_crate,
        )

        # Print the application header
        if output_format == "text" and output_file is None:
            console.print(get_app_header_rule())

        # Batch mode validates the detected crates and exits with the aggregated
        # status. Profiles are resolved *per crate* inside the batch (explicit
        # selection or per-crate auto-detection), so the single-crate profile
        # resolution below is intentionally skipped for batch runs.
        if detected.mode == "batch":
            _run_batch_validation(
                console,
                base_settings=validation_settings,
                profile_identifiers=list(profile_identifier),
                no_auto_profile=no_auto_profile,
                cache_max_age=cache_max_age,
                verbose=verbose,
                detected=detected,
                batch_pattern=batch_pattern,
                session_opt=session_opt,
                resume=resume,
                no_resume=no_resume,
                interactive=interactive,
                output_format=output_format,
                output_file=output_file,
                output_dir=output_dir,
                output_line_width=output_line_width,
                json_schema=json_schema,
                split_per_crate=split_per_crate,
            )

        # Single-crate validation is atomic: there is no run-state to resume.
        if resume:
            Console(file=sys.stderr, no_color=console.no_color, width=console.width).print(
                "[yellow]--resume has no effect on a single-crate validation "
                "(nothing to resume); running a fresh validation.[/yellow]"
            )

        # Resolve (and guard) the named session path up front, before any
        # validation work: an existing non-empty session must not be
        # silently overwritten.
        single_session_path = _named_session_path(session_opt, resume=resume) if session_opt else None

        # Get the available profiles
        available_profiles = services.get_profiles(profiles_path, extra_profiles_path=extra_profiles_path)

        # Resolve the concrete list of profile identifiers (auto-detection,
        # interactive selection, or fallback to the base `ro-crate` profile).
        profile_identifiers, autodetection = _resolve_profile_identifiers(
            console,
            interactive,
            no_auto_profile,
            available_profiles,
            list(profile_identifier),
            validation_settings,
        )

        # Single-crate mode: validate against the selected profiles and report.
        started = time.time()
        results, is_valid = _run_single_validations(
            profile_identifiers,
            validation_settings,
            autodetection=autodetection,
            console=console,
            pager=pager,
            interactive=interactive,
            enable_pager=enable_pager,
            verbose=verbose,
            fail_fast=fail_fast,
            output_format=output_format,
            output_file=output_file,
            output_line_width=output_line_width,
        )
        duration = time.time() - started
        # Record the validation in the sessions history (same history as batch
        # runs, browsable with `sessions list/show`) only when opted in.
        if session_opt is not None:
            _record_single_validation_session(
                validation_settings,
                rocrate_uri=detected.crate_paths[0],
                results=results,
                duration=duration,
                profile_identifiers=list(profile_identifier),
                no_auto_profile=no_auto_profile,
                session_path=single_session_path,
            )
        if output_format in ("json", "csv"):
            _write_single_report(
                validation_settings,
                results=results,
                profile_identifiers=profile_identifiers,
                is_valid=is_valid,
                rocrate_uri=detected.crate_paths[0],
                duration=duration,
                explicit_profiles=list(profile_identifier),
                no_auto_profile=no_auto_profile,
                console=console,
                interactive=interactive,
                verbose=verbose,
                output_file=output_file,
                output_dir=output_dir,
                output_line_width=output_line_width,
                json_schema=json_schema,
                split_per_crate=split_per_crate,
                output_format=output_format,
            )

        # Exit with appropriate status code.
        # using ctx.exit seems to raise an Exception that gets caught below,
        # so we use sys.exit instead.
        sys.exit(0 if is_valid else 1)
    except click.UsageError:
        # Usage errors are reported natively by Click (message + usage hint)
        # instead of the generic "unexpected error" handler.
        raise
    except Exception as e:
        handle_error(e, console)


@dataclass
class _DetectedInput:
    """The outcome of the input auto-detection (see :func:`_detect_input`)."""

    mode: str  # "single" | "batch"
    crate_paths: list[str]  # the crates to validate
    targets: list[str] = field(default_factory=list)  # normalized user inputs, keying the state file
    scan_root: Path | None = None  # the collection root, when the input is one directory


def _is_single_crate_uri(uri: str) -> bool:
    """
    Whether ``uri`` denotes one crate on its own: a remote URI, a local file
    (zipped crate or detached metadata) or a directory holding its own
    ``ro-crate-metadata.json``. A local directory without a metadata file is a
    (potential) collection instead.
    """
    parsed = URI(str(uri))
    if parsed.is_remote_resource():
        return True
    path = parsed.as_path()
    if path.is_dir():
        return (path / constants.ROCRATE_METADATA_FILE).exists()
    return True  # local file: the URI callback restricts these to .zip/.json/.jsonld


def _detect_input(rocrate_uris: list[str], *, batch: bool, batch_pattern: str) -> _DetectedInput:
    """
    Auto-detect the validation mode from the positional input(s).

    - one URI that is a crate (zip, metadata file, remote URI or directory
      with its own ``ro-crate-metadata.json``) → **single** mode;
    - one directory without a metadata file → its crates are discovered
      recursively and validated in **batch** mode;
    - several URIs → an explicit list, validated in **batch** mode; a
      collection directory in the list is expanded to the crates it contains;
    - ``-b/--batch`` forces batch mode: every directory is scanned with
      :func:`services.discover_ro_crates`, whether or not it is itself a crate.

    The returned targets are the *user inputs* (normalized), not the discovered
    crates, so the resume key stays stable when a collection gains new crates.
    """
    multiple = len(rocrate_uris) > 1
    if batch_pattern != "*" and multiple:
        raise click.UsageError(
            "--batch-pattern applies to a directory scan; it cannot be combined with an explicit list of RO-Crates."
        )

    targets = services.normalize_state_targets(cast("list[str | Path]", rocrate_uris))

    # Single crate (auto-detected), unless -b forces a directory scan.
    if not batch and not multiple and _is_single_crate_uri(rocrate_uris[0]):
        return _DetectedInput(mode="single", crate_paths=[rocrate_uris[0]], targets=targets)

    # Batch: expand every input into the crates it holds.
    crate_paths: list[str] = []
    scan_root: Path | None = None
    for uri in rocrate_uris:
        if not URI(str(uri)).is_remote_resource() and Path(uri).is_dir() and (batch or not _is_single_crate_uri(uri)):
            scan_dir = Path(uri).resolve()
            found = [str(p) for p in services.discover_ro_crates(scan_dir, pattern=batch_pattern)]
            # An empty scan is an input error when the directory was auto-detected
            # as a collection (probably a mistyped path); with an explicit
            # -b/--batch it is a valid outcome, reported gracefully by the caller.
            if not found and not batch:
                raise click.BadParameter(f"No RO-Crate metadata found under: {scan_dir}", param_hint="RO-CRATE-URI")
            crate_paths.extend(found)
            if not multiple:
                scan_root = scan_dir
        else:
            # A crate given directly (zip, metadata file, crate dir or remote URI).
            crate_paths.append(str(uri))

    # De-duplicate while preserving order (e.g. overlapping inputs).
    crate_paths = list(dict.fromkeys(crate_paths))
    return _DetectedInput(mode="batch", crate_paths=crate_paths, targets=targets, scan_root=scan_root)


def _sanitize_session_name(name: str) -> str:
    """Sanitize a user-supplied session name for use as a file name."""
    slug = re.sub(r"[^\w.-]+", "-", name.strip()).strip("-.")
    if not slug:
        raise click.UsageError(f"Invalid session name: {name!r}")
    return slug


def _read_state_summary(state_path: Path) -> dict | None:
    """The ``session`` header of a state file, or ``None`` when unreadable."""
    try:
        return json.loads(Path(state_path).read_text(encoding="utf-8")).get("session", {})
    except Exception:  # missing, corrupt or unreadable: treat as absent
        return None


def _is_interrupted_state(state_path: Path) -> dict | None:
    """The state summary when ``state_path`` holds an interrupted run, else ``None``."""
    if not state_path.exists():
        return None
    summary = _read_state_summary(state_path)
    if not summary:
        return None
    if summary.get("status") in ("in_progress", "interrupted") and (summary.get("pending_crates") or 0) > 0:
        return summary
    return None


def _named_session_path(session_name: str, *, resume: bool) -> Path:
    """
    Resolve (and guard) the file path of a named session.

    An existing session with the same name is only reused when it is empty
    (just created by ``sessions new``) or when ``--resume`` is given; anything
    else is a usage error, so a permanent session is never silently overwritten.
    """
    name = _sanitize_session_name(session_name)
    session_path = get_user_sessions_dir() / f"{name}.json"
    if session_path.exists() and not resume:
        summary = _read_state_summary(session_path)
        if summary is None or (summary.get("total_crates") or 0) > 0:
            raise click.UsageError(
                f"Session '{name}' already exists: resume it with --resume "
                f"(or `sessions resume {name}`), restart it with `sessions restart {name}`, "
                "or pick another name."
            )
    return session_path


def _resolve_batch_state(
    batch_settings: ValidationSettings,
    detected: _DetectedInput,
    *,
    batch_pattern: str,
    session_opt: str | None,
    resume: bool,
    profile_identifiers: list[str],
    no_auto_profile: bool,
) -> tuple[Path, bool]:
    """
    Resolve the state file the batch writes to, returning ``(path, ephemeral)``.

    Without ``--session`` the state is a temporary run-state (deleted on
    completion, kept for ``--resume`` when interrupted). With ``--session`` the
    state *is* the permanent session file — hash-derived when unnamed, or
    ``sessions/<NAME>.json`` when a name is given.
    """
    if session_opt is None:
        return (
            services.resolve_run_state_path(
                batch_settings,
                detected.targets,
                batch_pattern,
                profile_identifiers=profile_identifiers,
                no_auto_profile=no_auto_profile,
            ),
            True,
        )
    if session_opt == "":
        return (
            services.resolve_session_state_path(
                batch_settings,
                detected.targets,
                batch_pattern,
                profile_identifiers=profile_identifiers,
                no_auto_profile=no_auto_profile,
            ),
            False,
        )
    return _named_session_path(session_opt, resume=resume), False


def _decide_fresh(
    console: Console,
    state_path: Path,
    *,
    resume: bool,
    no_resume: bool,
    interactive: bool,
) -> bool:
    """
    Decide whether the batch starts fresh or resumes an interrupted state.

    ``--no-resume`` always starts fresh and ``--resume`` always resumes (when
    there is something to resume). Without either flag, a matching interrupted
    state triggers an interactive prompt; in non-interactive mode the run
    starts fresh, so scripted runs stay predictable and reproducible.
    """
    if no_resume:
        return True
    interrupted = _is_interrupted_state(state_path)
    if interrupted is None:
        return False  # nothing to resume: a fresh run either way
    if resume:
        return False
    total = interrupted.get("total_crates") or 0
    processed = total - (interrupted.get("pending_crates") or 0)
    if interactive:
        stderr_console = Console(file=sys.stderr, no_color=console.no_color, width=console.width)
        stderr_console.print(
            f"[yellow]Found an interrupted validation matching this command "
            f"({processed}/{total} crates already validated).[/yellow]"
        )
        return not click.confirm("Resume it? ('n' restarts from scratch)", default=True, err=True)
    logger.info(
        "Interrupted state found at %s (%d/%d crates) but running non-interactively: starting fresh. "
        "Pass --resume to continue it.",
        state_path,
        processed,
        total,
    )
    return True


# Threads the CLI options through to the batch helpers; pylint counts these
# pass-through arguments as locals, so the limit is not meaningful here.
# pylint: disable-next=too-many-locals
def _run_batch_validation(
    console: Console,
    *,
    base_settings: dict,
    profile_identifiers: list[str],
    no_auto_profile: bool,
    cache_max_age: int,
    verbose: bool,
    detected: _DetectedInput,
    batch_pattern: str,
    session_opt: str | None,
    resume: bool,
    no_resume: bool,
    interactive: bool,
    output_format: str,
    output_file: Path | None,
    output_dir: Path | None,
    output_line_width: int | None,
    json_schema: str = "v2",
    split_per_crate: bool = False,
) -> None:
    """Run batch validation end-to-end and exit with the aggregated status code."""
    crate_paths = detected.crate_paths
    batch_settings = _build_batch_settings(
        base_settings,
        profile_identifiers=profile_identifiers,
        cache_max_age=cache_max_age,
        verbose=verbose,
    )
    if not crate_paths:
        _report_empty_batch(
            console,
            batch_settings,
            output_format=output_format,
            output_file=output_file,
            output_dir=output_dir,
            output_line_width=output_line_width,
            verbose=verbose,
            json_schema=json_schema,
            split_per_crate=split_per_crate,
        )
        sys.exit(0)

    # The state file location is derived deterministically from the user input
    # and settings: a temporary run-state by default, the permanent session
    # file with --session (written incrementally from the start, no promotion).
    state_path, ephemeral = _resolve_batch_state(
        batch_settings,
        detected,
        batch_pattern=batch_pattern,
        session_opt=session_opt,
        resume=resume,
        profile_identifiers=profile_identifiers,
        no_auto_profile=no_auto_profile,
    )
    fresh = _decide_fresh(console, state_path, resume=resume, no_resume=no_resume, interactive=interactive)

    # Base directory used to render the crate paths relative (and shown as Input).
    input_base = detected.scan_root or _common_base_path(crate_paths)
    _print_batch_header(
        console,
        count=len(crate_paths),
        session_path=None if ephemeral else state_path,
        input_path=input_base,
        profile_identifiers=profile_identifiers,
        no_auto_profile=no_auto_profile,
    )

    batch_view = BatchValidationCommandView(console=console)
    # Run batch validation with a progress bar on stderr (always visible,
    # even when the report goes to a file).
    batch_result = batch_view.run_with_progress(
        batch_validate_fn=services.batch_validate,
        settings=batch_settings,
        rocrate_uris=crate_paths,
        state_path=state_path,
        fresh=fresh,
        ephemeral=ephemeral,
        profile_identifiers=profile_identifiers,
        no_auto_profile=no_auto_profile,
        base_path=input_base,
    )
    # Writing a large report to a file can take a moment; show a spinner on
    # stderr while it happens (skipped when the summary is rendered to the
    # console, which is itself the visible output).
    if split_per_crate or output_file:
        status_msg = (
            f"[cyan]Writing split reports to {output_dir or 'validation-report/'}…[/cyan]"
            if split_per_crate
            else f"[cyan]Writing report to {output_file}…[/cyan]"
        )
        status_console = Console(file=sys.stderr, no_color=console.no_color, width=console.width)
        report_ctx = status_console.status(status_msg)
    else:
        report_ctx = nullcontext()
    with report_ctx:
        report_path = _write_batch_report(
            batch_view,
            batch_result,
            output_format=output_format,
            output_file=output_file,
            output_dir=output_dir,
            output_line_width=output_line_width,
            verbose=verbose,
            json_schema=json_schema,
            split_per_crate=split_per_crate,
        )
    _report_batch_status(
        console,
        batch_result,
        state_path=state_path,
        ephemeral=ephemeral,
        output_file=report_path,
        output_format=output_format,
        split_per_crate=split_per_crate,
    )
    sys.exit(0 if batch_result.passed() else 1)


# Threads the CLI options through to the rendering helpers; pylint counts these
# pass-through arguments as locals, so the limit is not meaningful here.
# pylint: disable-next=too-many-locals
def _run_single_validations(
    profile_identifiers: list[str],
    validation_settings: dict,
    *,
    autodetection: bool,
    console: Console,
    pager,
    interactive: bool,
    enable_pager: bool,
    verbose: bool,
    fail_fast: bool,
    output_format: str,
    output_file: Path | None,
    output_line_width: int | None,
) -> tuple[dict, bool]:
    """Validate the RO-Crate against each selected profile, returning (results, overall-validity)."""
    is_valid = True
    results = {}
    # One cache for the whole run: when the crate is validated against multiple
    # profiles, the parsed profiles/shapes and the crate data graph are reused.
    cache = ValidationCache()
    for profile in profile_identifiers:
        # Duplicate settings for each profile and set the profile identifier
        logger.info("\nValidating RO-Crate against profile: [bold cyan]%s[/bold cyan]", profile)
        profile_settings = validation_settings.copy()
        profile_settings["profile_identifier"] = profile
        logger.debug("Profile selected for validation: %s", profile)
        logger.debug("Profile autodetected: %s", autodetection)

        # Perform the validation and render the result for the chosen output target.
        if output_format == "text" and not output_file:
            result = _render_console_result(
                profile_settings,
                console=console,
                pager=pager,
                interactive=interactive,
                enable_pager=enable_pager,
                verbose=verbose,
                cache=cache,
            )
        else:
            result = _render_file_or_collected_result(
                profile,
                profile_settings,
                console=console,
                interactive=interactive,
                verbose=verbose,
                output_format=output_format,
                output_file=output_file,
                output_line_width=output_line_width,
                cache=cache,
            )
        results[profile] = result

        # Update the global validation status
        is_valid = is_valid and result.passed()

        # Interrupt the validation if the fail fast mode is enabled
        if fail_fast and not is_valid:
            break

    return results, is_valid


def _record_single_validation_session(
    validation_settings: dict,
    *,
    rocrate_uri: str | Path,
    results: dict[str, ValidationResult],
    duration: float,
    profile_identifiers: list[str],
    no_auto_profile: bool,
    session_path: Path | None = None,
) -> None:
    """
    Record a single-crate validation in the sessions history (best effort:
    a recording failure never fails the validation).

    Without an explicit ``session_path`` (named session), the path is
    deterministic for (crate, profile selection, severity), so re-validating
    the same target overwrites the previous history entry instead of
    accumulating duplicates — the history keeps the latest outcome,
    consistently with batch sessions and ``ValidationSession.validate``.
    """
    try:
        settings_obj = ValidationSettings.parse(dict(validation_settings))
        explicit_profiles = list(profile_identifiers) if profile_identifiers else None
        if session_path is None:
            session_path = services.resolve_single_crate_session_path(
                settings_obj,
                rocrate_uri,
                profile_identifiers=explicit_profiles,
                no_auto_profile=no_auto_profile,
            )
        session = _build_single_session(
            validation_settings,
            rocrate_uri=rocrate_uri,
            results=results,
            duration=duration,
            profile_identifiers=profile_identifiers,
            no_auto_profile=no_auto_profile,
            session_path=session_path,
        )
        session.save()
        logger.debug("Validation recorded in session: %s", session_path)
    except Exception as e:
        logger.debug("Could not record the validation session: %s", e)


def _build_single_session(
    validation_settings: dict,
    *,
    rocrate_uri: str | Path,
    results: dict[str, ValidationResult],
    duration: float,
    profile_identifiers: list[str],
    no_auto_profile: bool,
    session_path: Path | None = None,
) -> ValidationSession:
    """
    Build the session of a single-crate validation.

    A single crate is a session of one, which is what makes the report identical
    in both modes: the session is persisted when the run opted into one, and is
    otherwise transient, built only to be projected into the report.
    """
    settings_obj = ValidationSettings.parse(dict(validation_settings))
    session = ValidationSession(
        validation_settings=settings_obj.to_dict() if hasattr(settings_obj, "to_dict") else {},
        crate_paths=[str(rocrate_uri)],
        session_path=session_path,
    )
    session.profile_identifiers = list(profile_identifiers) if profile_identifiers else None
    session.no_auto_profile = no_auto_profile
    session.requirement_severity_only = bool(getattr(settings_obj, "requirement_severity_only", False))
    session.add_results(str(rocrate_uri), list(results.items()), duration)
    if session.is_completed():
        session.status = "completed"
    return session


def _build_batch_settings(
    base_settings: dict,
    *,
    profile_identifiers: list[str],
    cache_max_age: int,
    verbose: bool,
) -> ValidationSettings:
    """Derive the shared batch ``ValidationSettings`` from the single-crate settings."""
    # Batch mode targets a directory of crates, so only the per-crate RO-Crate URI
    # is dropped (it is set per crate during validation). The creation-time and
    # availability flags are intentionally kept so they apply uniformly to every
    # crate, exactly as they would in single-crate validation.
    batch_settings_dict = {k: v for k, v in base_settings.items() if k != "rocrate_uri"}
    batch_settings_dict.update(
        {
            # Base profile for the shared settings object; the actual profile(s) used
            # for each crate are resolved per crate by the services layer (explicit
            # ``--profile-identifier`` list or per-crate auto-detection).
            "profile_identifier": profile_identifiers[0] if profile_identifiers else "ro-crate",
            "cache_max_age": cache_max_age,
            "verbose": verbose,
        }
    )
    return ValidationSettings.parse(batch_settings_dict)


def _common_base_path(crate_paths: list[str]) -> Path | None:
    """The common parent directory of the (local) crate paths, when derivable."""
    local = [p for p in crate_paths if not URI(str(p)).is_remote_resource()]
    if not local:
        return None
    if len(local) == 1:
        return Path(local[0]).resolve().parent
    try:
        return Path(os.path.commonpath([str(Path(p).resolve()) for p in local]))
    except (ValueError, TypeError):
        return None


def _report_empty_batch(
    console: Console,
    batch_settings: ValidationSettings,
    *,
    output_format: str,
    output_file: Path | None,
    output_dir: Path | None,
    output_line_width: int | None,
    verbose: bool,
    json_schema: str,
    split_per_crate: bool,
) -> None:
    """
    Report a batch that matched no crate at all.

    The machine-readable formats still get a well-formed, empty report — an
    empty ``crates`` list, zeroed statistics — so a consumer never has to tell
    "nothing matched" apart from "the command produced nothing". The human
    notice goes to stderr, where it cannot pollute that report.
    """
    Console(file=sys.stderr, no_color=console.no_color, width=console.width).print(
        "[bold yellow]No RO-Crates found for batch validation.[/bold yellow]"
    )
    if output_format not in ("json", "csv"):
        return
    session = ValidationSession(
        validation_settings=batch_settings.to_dict() if hasattr(batch_settings, "to_dict") else {},
        crate_paths=[],
    )
    session.status = "completed"
    _write_batch_report(
        BatchValidationCommandView(console=console),
        BatchValidationResult(session),
        output_format=output_format,
        output_file=output_file,
        output_dir=output_dir,
        output_line_width=output_line_width,
        verbose=verbose,
        json_schema=json_schema,
        split_per_crate=split_per_crate,
    )


def _check_output_options(*, output_format: str, split_per_crate: bool) -> None:
    """Reject option combinations the output formats cannot honour."""
    # Splitting concerns the JSON report only: the CSV is already one row per
    # issue, and the text report is meant to be read as a whole.
    if split_per_crate and output_format != "json":
        raise click.UsageError("--split-per-crate applies to the JSON report only (use -f json).")


def _resolve_output_destination(
    console: Console,
    *,
    output_file: Path | None,
    output_dir: Path | None,
    split_per_crate: bool,
) -> Path | None:
    """
    Combine ``--output-file`` and ``--output-dir`` into the single file to write.

    Returns the resolved path, with its parent directory created, or ``None``
    when the report goes to stdout or to the split-mode writer (which resolves
    its own destination from ``--output-dir``).
    """

    def warn(message: str) -> None:
        Console(file=sys.stderr, no_color=console.no_color, width=console.width).print(
            f"[yellow]Warning:[/yellow] {message}"
        )

    # Warn when -o is used with --split-per-crate: the split mode writes one
    # file per crate and ignores the single-file output option.
    if split_per_crate:
        if output_file is not None:
            warn(
                "--output-file is ignored with --split-per-crate; "
                "reports go to --output-dir (default: validation-report/)"
            )
        return None

    # --output-dir provides the base directory for a relative --output-file.
    # When --output-file is absolute the directory is superfluous and ignored.
    if output_dir is not None:
        if output_file is None:
            warn("--output-dir has no effect without --output-file or --split-per-crate (output goes to stdout)")
        elif output_file.is_absolute():
            warn("--output-dir is ignored when --output-file is an absolute path")
        else:
            output_file = output_dir / output_file

    # Ensure the parent directory exists when -d is used with a relative -o.
    # (stdout needs none.)
    if output_file is not None and output_file.parent != Path():
        output_file.parent.mkdir(parents=True, exist_ok=True)

    return output_file


def _write_single_report(
    validation_settings: dict,
    *,
    results: dict[str, ValidationResult],
    profile_identifiers: list[str],
    is_valid: bool,
    rocrate_uri: str | Path,
    duration: float,
    explicit_profiles: list[str],
    no_auto_profile: bool,
    console: Console,
    interactive: bool,
    verbose: bool,
    output_file: Path | None,
    output_dir: Path | None,
    output_line_width: int | None,
    json_schema: str,
    split_per_crate: bool,
    output_format: str = "json",
) -> None:
    """
    Write the machine-readable report of a single-crate validation.

    The v2 report is projected from a session of one crate, the very same
    projection the batch uses; the legacy report keeps its own (frozen)
    renderer, which works off the live per-profile results. Splitting always
    goes through the session, whatever the schema, since it is the session that
    knows the crates. The CSV is the batch one over a session of one.
    """
    session = (
        None
        if json_schema == "legacy" and output_format == "json" and not split_per_crate
        else _build_single_session(
            validation_settings,
            rocrate_uri=rocrate_uri,
            results=results,
            duration=duration,
            profile_identifiers=explicit_profiles,
            no_auto_profile=no_auto_profile,
        )
    )
    if output_format == "csv" and session is not None:
        # ``utf-8-sig`` so spreadsheet tools (Excel) detect the encoding; the
        # BOM is skipped when the report goes to stdout.
        crate_dicts = session.inlined_crates()
        if output_file:
            with output_file.open("w", encoding="utf-8-sig", newline="") as f:
                write_report_csv(f, crate_dicts)
        else:
            write_report_csv(sys.stdout, crate_dicts)
        return
    if split_per_crate and session is not None:
        manifest = _write_split_reports(
            session,
            schema=json_schema,
            passed=is_valid,
            verbose=verbose,
            output_dir=output_dir,
        )
        _announce_split_destination(
            console,
            directory=manifest.parent,
            output_format=output_format,
            crates=len(session.crates),
        )
        return
    _emit_json_report(
        results,
        profile_identifiers,
        is_valid,
        console=console,
        interactive=interactive,
        output_file=output_file,
        output_line_width=output_line_width,
        session=session,
        verbose=verbose,
    )


def _split_reports_row(directory: Path, output_format: str, crates: int) -> FooterRow:
    """The details-block row of a split run: the destination, then what is in it."""
    return FooterRow(
        "📄",
        f"Reports ({output_format})",
        str(directory),
        "bold cyan",
        f"{crates} crate report{'' if crates == 1 else 's'} + index.json",
    )


def _announce_split_destination(console: Console, *, directory: Path, output_format: str, crates: int) -> None:
    """
    Say where a split run wrote its files, in the layout the batch footer uses.

    Only the single-crate path needs this: a batch ends with the footer, which
    carries the very same row. It goes to stderr, so it never mixes with a
    report written to stdout.
    """
    stderr_console = Console(file=sys.stderr, no_color=console.no_color, width=console.width)
    stderr_console.print()
    render_details_block(stderr_console, [_split_reports_row(directory, output_format, crates)])
    stderr_console.print()


def _write_split_reports(
    session: ValidationSession,
    *,
    schema: str,
    passed: bool,
    verbose: bool,
    output_dir: Path | None,
) -> Path:
    """
    Write one report per crate plus the manifest.

    :returns: the path of the manifest, the entry point of the whole set
    """
    directory, documents, index_name = split_documents(
        session,
        schema=schema,
        passed=passed,
        verbose=verbose,
        output_dir=output_dir,
    )
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        with (directory / name).open("w", encoding="utf-8") as f:
            dump_json(document, f)
    # Where the files went is not announced here: it belongs to the details
    # block printed at the end of the run, next to the destination of every
    # other output, instead of interrupting the per-crate results.
    return directory / index_name


def _write_batch_report(
    batch_view: BatchValidationCommandView,
    batch_result: BatchValidationResult,
    *,
    output_format: str,
    output_file: Path | None,
    output_dir: Path | None,
    output_line_width: int | None,
    verbose: bool,
    json_schema: str = "v2",
    split_per_crate: bool = False,
) -> Path | None:
    """
    Write the batch result as JSON, CSV or a text summary, to a file or the console.

    :returns: the path the report was written to (the manifest, when split), or
        ``None`` when it went to the console.

    Statistics are not rendered here: the complete document (summary,
    statistics, issue details, appendix) is available at any time from the
    recorded session via ``sessions report``.

    Where the report is saved is reported afterwards by :func:`_report_batch_status`,
    so this function does not print its own "writing to ..." notes.
    """
    if output_format == "json":
        if split_per_crate:
            return _write_split_reports(
                batch_result.session,
                schema=json_schema,
                passed=batch_result.passed(),
                verbose=verbose,
                output_dir=output_dir,
            )
        with output_file.open("w", encoding="utf-8") if output_file else nullcontext(sys.stdout) as f:
            if json_schema == "legacy":
                out = Console(color_system=None, width=output_line_width, file=f)
                out.register_formatter(JSONOutputFormatter())
                # Disable word-wrap/cropping: Rich would otherwise insert literal line
                # breaks into long string values (e.g. messages, URLs), producing
                # invalid, unescaped control characters in the JSON output.
                out.print(batch_result, soft_wrap=True)
            else:
                dump_json(
                    build_report(
                        batch_result.session,
                        passed=batch_result.passed(),
                        verbose=verbose,
                    ),
                    f,
                )
        return output_file

    crate_dicts = batch_result.session.inlined_crates(batch_result.crates)

    if output_format == "csv":
        # ``utf-8-sig`` so spreadsheet tools (Excel) detect the encoding; the
        # BOM is skipped when the report goes to stdout.
        if output_file:
            with output_file.open("w", encoding="utf-8-sig", newline="") as f:
                write_report_csv(f, crate_dicts)
        else:
            write_report_csv(sys.stdout, crate_dicts)
        return output_file
    if output_file:
        with output_file.open("w", encoding="utf-8") as f:
            out = Console(color_system=None, width=output_line_width, file=f)
            out.register_formatter(TextOutputFormatter())
            BatchValidationCommandView(console=out).show_summary(batch_result, verbose=verbose)
            # Appendix with the description of each reported issue type — only
            # when the report shows issue identifiers (verbose details).
            if verbose:
                render_issue_reference(out, crate_dicts)
    else:
        batch_view.show_summary(batch_result, verbose=verbose)
    return output_file


def _print_batch_header(
    console: Console,
    *,
    count: int,
    session_path: Path | None,
    input_path: Path | None,
    profile_identifiers: list[str],
    no_auto_profile: bool,
) -> None:
    """
    Print the batch header on stderr (always): the number of crates found, the
    session file (only for --session runs), the input scanned and the profile
    selection. Shown before the per-crate list so the relative crate paths
    printed during validation are easy to interpret.
    """
    stderr_console = Console(file=sys.stderr, no_color=console.no_color, width=console.width)
    profiles, profiles_style = format_profile_selection(profile_identifiers, no_auto_profile)
    rows: list[tuple[str, str, str]] = []
    if session_path:
        rows.append(("Session", str(session_path), "cyan"))
    if input_path:
        rows.append(("Input", str(input_path), "cyan"))
    rows.append(("Profiles", profiles, profiles_style))
    render_batch_header(
        stderr_console,
        headline=f"[bold]Batch validation[/bold] [dim]·[/dim] [cyan]{count}[/cyan] RO-Crate(s)",
        rows=rows,
    )


def _report_batch_status(
    console: Console,
    batch_result: BatchValidationResult,
    *,
    state_path: Path | None,
    ephemeral: bool,
    output_file: Path | None,
    output_format: str,
    split_per_crate: bool = False,
) -> None:
    """
    Print the final batch verdict on stderr, followed by a spaced block listing
    where the report was saved (and the state file, only when the run did not
    complete and may need to be resumed).

    Everything is written to stderr so it never pollutes machine-readable output
    (JSON/CSV) sent to stdout. The input scanned is reported up front by
    :func:`_print_batch_header`, so it is not repeated here.
    """
    stderr_console = Console(file=sys.stderr, no_color=console.no_color, width=console.width)

    rows: list[FooterRow] = []
    if output_file:
        if split_per_crate:
            rows.append(_split_reports_row(output_file.parent, output_format, batch_result.total_crates()))
        else:
            rows.append(FooterRow("📄", f"Report ({output_format})", str(output_file), "bold cyan"))
    # The state file is only useful here if the run did not finish (so it can
    # be resumed); when completed a run-state no longer exists and a session
    # is redundant with the header shown at the start.
    if state_path and not batch_result.session.is_completed():
        rows.append(FooterRow("💾", "Run state" if ephemeral else "Session", str(state_path), "cyan"))
    render_batch_footer(stderr_console, batch_result, rows)


def _log_validation_inputs(
    *,
    profiles_path,
    extra_profiles_path,
    profile_identifier,
    requirement_severity,
    requirement_severity_only,
    disable_profile_inheritance,
    rocrate_uri,
    fail_fast,
    cache_max_age,
    cache_path,
    no_cache,
    offline,
) -> None:
    """Log the raw validation input parameters for debugging."""
    logger.debug("profiles_path: %s", Path(profiles_path).resolve())
    logger.debug("extra_profiles_path: %s", Path(extra_profiles_path).resolve() if extra_profiles_path else None)
    logger.debug("profile_identifier: %s", profile_identifier)
    logger.debug("requirement_severity: %s", requirement_severity)
    logger.debug("requirement_severity_only: %s", requirement_severity_only)
    logger.debug("disable_inheritance: %s", disable_profile_inheritance)
    logger.debug("rocrate_uri: %s", rocrate_uri)
    logger.debug("fail_fast: %s", fail_fast)
    logger.debug("no fail fast: %s", not fail_fast)
    logger.debug("cache_max_age: %s", cache_max_age)
    logger.debug("cache_path: %s", Path(cache_path).resolve() if cache_path else None)
    logger.debug("no_cache: %s", no_cache)
    logger.debug("offline: %s", offline)


def _warn_if_remote_offline(console: Console, rocrate_uri: str | Path, offline: bool) -> None:
    """Warn when a remote RO-Crate is validated in offline mode (the cached copy is used)."""
    if offline and isinstance(rocrate_uri, str) and rocrate_uri.split(":", 1)[0].lower() in ("http", "https", "ftp"):
        console.print(
            Padding(
                Rule(
                    "[bold yellow]WARNING:[/bold yellow] "
                    "[bold]The target RO-Crate is remote and offline mode is enabled.[/bold]\n"
                    "The cached version of the RO-Crate will be used if available.\n"
                    "The cached copy may be out of sync with the version currently published remotely.",
                    align="center",
                    style="bold yellow",
                ),
                (1, 2, 0, 2),
            )
        )


def _preflight_input_checks(
    console: Console,
    rocrate_uris: list[str],
    *,
    offline: bool,
    no_cache: bool,
    resume: bool,
    no_resume: bool,
    batch: bool,
    batch_pattern: str,
    session_opt: str | None = None,
) -> _DetectedInput:
    """
    Run the pre-validation checks and resolve the input mode.

    Rejects contradictory flag combinations, warns about remote targets in
    offline mode, garbage-collects stale run-states (best effort, see
    ``RUN_STATE_TTL_DAYS``) and auto-detects the validation mode from the
    positional input(s); ``-b/--batch`` forces a directory scan.
    """
    # --no-cache and --offline are contradictory: offline mode requires a cache
    # to serve requests from, while no-cache disables caching entirely.
    if no_cache and offline:
        raise click.UsageError(
            "The --no-cache and --offline flags are mutually exclusive: "
            "offline mode relies on the HTTP cache to serve resources."
        )
    if resume and no_resume:
        raise click.UsageError("The --resume and --no-resume flags are mutually exclusive.")
    # Validate the session name up front (before any directory scan) so a
    # swallowed RO-CRATE-URI or a name clash fails fast with a native usage error.
    if session_opt:
        _named_session_path(session_opt, resume=resume)

    for uri in rocrate_uris:
        _warn_if_remote_offline(console, uri, offline)

    services.cleanup_stale_run_states()

    detected = _detect_input(rocrate_uris, batch=batch, batch_pattern=batch_pattern)
    _check_batch_only_options(batch_mode=detected.mode == "batch", batch_pattern=batch_pattern)
    return detected


def _check_batch_only_options(
    *,
    batch_mode: bool,
    batch_pattern: str,
) -> None:
    """
    Reject batch-only options when the detected mode is not batch.

    ``--batch-pattern`` only makes sense when a directory is scanned for
    crates; using it on a single-crate validation is a usage error rather than
    a silently ignored no-op. The check runs *after* input auto-detection,
    since batch mode is no longer implied by ``-b/--batch`` alone.
    """
    if batch_mode:
        return
    if batch_pattern != "*":
        raise click.UsageError(
            "--batch-pattern is only valid in batch mode (a directory scan); the given input is a single RO-Crate."
        )


def _parse_skip_checks(skip_checks: list[str] | None) -> list[str]:
    """Parse the comma-separated ``--skip-checks`` option into a flat list of check IDs."""
    logger.debug("skip_checks: %s", skip_checks)
    skip_checks_list: list[str] = []
    if skip_checks:
        try:
            for s in skip_checks:
                skip_checks_list.extend(_.strip() for _ in s.split(",") if _.strip())
        except Exception as e:
            logger.error("Error parsing skip_checks: %s", e)
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception("Error parsing skip_checks")
            raise ValueError(
                f"Invalid skip_checks value: {skip_checks}. "
                "It must be a comma-separated list of Fully Qualified Check IDs."
            ) from e
    logger.debug("Skip checks: %s", skip_checks_list)
    return skip_checks_list


def _resolve_profile_identifiers(
    console: Console,
    interactive: bool,
    no_auto_profile: bool,
    available_profiles: list,
    profile_identifiers: list[str],
    validation_settings: dict,
) -> tuple[list[str], bool]:
    """
    Resolve the concrete list of profile identifiers to validate against.

    Applies auto-detection and interactive selection when no profile is given,
    and falls back to the base ``ro-crate`` profile when nothing can be resolved.
    Returns the identifiers and whether they were auto-detected.
    """
    autodetection = False
    if not profile_identifiers:
        # Auto-detect the profile to use for validation (if not disabled)
        candidate_profiles = None
        if not no_auto_profile:
            candidate_profiles = services.detect_profiles(settings=validation_settings)
            logger.debug("Candidate profiles: %s", candidate_profiles)
        else:
            logger.info("Auto-detection of the profiles to use for validation is disabled")

        # Prompt the user when interactive and no single profile could be auto-detected
        if interactive and (
            not candidate_profiles or len(candidate_profiles) == 0 or len(candidate_profiles) == len(available_profiles)
        ):
            console.print(
                Padding(
                    Rule(
                        "[bold yellow]WARNING: [/bold yellow]"
                        "[bold]Unable to automatically detect the profile to use for validation[/bold]\n",
                        align="center",
                        style="bold yellow",
                    ),
                    (2, 2, 0, 2),
                )
            )
            selected_options = multiple_choice(console, available_profiles)
            if selected_options is None or isinstance(selected_options, bool):
                selected_options = []
            profile_identifiers = [available_profiles[int(o)].identifier for o in selected_options]
            logger.debug("Profile selected: %s", selected_options)
            console.print(Padding(Rule(style="bold yellow"), (1, 2)))
        elif candidate_profiles and len(candidate_profiles) < len(available_profiles):
            logger.debug("Profile identifier autodetected: %s", candidate_profiles[0].identifier)
            autodetection = True
            profile_identifiers = [_.identifier for _ in candidate_profiles]

    # Fall back to the base profile when nothing could be resolved
    if not profile_identifiers:
        console.print(f"\n{' ' * 2}[bold yellow]WARNING: [/bold yellow]", end="")
        if no_auto_profile:
            console.print("[bold]Auto-detection of the profiles to use for validation is disabled[/bold]")
        else:
            console.print("[bold]Unable to automatically detect the profile to use for validation[/bold]")
        console.print(f"{' ' * 11}[bold]The base `ro-crate` profile will be used for validation[/bold]")
        profile_identifiers = ["ro-crate"]

    return profile_identifiers, autodetection


def _render_console_result(
    validation_settings: dict,
    *,
    console: Console,
    pager,
    interactive: bool,
    enable_pager: bool,
    verbose: bool,
    cache: ValidationCache | None = None,
) -> ValidationResult:
    """Validate and render the result to the interactive/text console (no output file)."""
    validate_service = partial(services.validate, cache=cache)
    if interactive:
        command_view = ValidationCommandView(
            validation_settings=ValidationSettings.parse(validation_settings),
            console=console,
            interactive=interactive,
            no_paging=not enable_pager,
            pager=pager,
        )
        result = command_view.show_validation_progress(validate_service)
        if not result.passed():
            verbose_choice = "n"
            if interactive and not verbose:
                verbose_choice = get_single_char(
                    console,
                    choices=["y", "n"],
                    message=("[bold] > Do you want to see the validation details? ([magenta]y/n[/magenta]): [/bold]"),
                )
            if verbose_choice == "y" or verbose:
                command_view.display_validation_result(result)
        return result

    result = validate_service(validation_settings)
    console.register_formatter(TextOutputFormatter())
    console.print(result.statistics)
    if not result.passed() and verbose:
        out = Console(no_color=console.no_color, width=console.width, height=console.height)
        out.register_formatter(TextOutputFormatter())
        out.print(result)
    return result


def _render_file_or_collected_result(
    profile: str,
    validation_settings: dict,
    *,
    console: Console,
    interactive: bool,
    verbose: bool,
    output_format: str,
    output_file: Path | None,
    output_line_width: int | None,
    cache: ValidationCache | None = None,
) -> ValidationResult:
    """Validate for the file/JSON-input path, optionally writing a text report to file."""
    validate_service = partial(services.validate, cache=cache)
    if interactive:
        with LiveTextProgressLayout(
            console=console,
            profile_identifier=profile,
            validation_settings=validation_settings,
            callable_service=validate_service,
            transient=True,
        ) as result:
            logger.debug("Validation result obtained")
    else:
        result = validate_service(validation_settings)

    if result is None:
        raise RuntimeError("Validation did not produce a result")

    # Output processing for text format to file
    if output_file and output_format == "text":
        if interactive:
            console.print(f"\n{' ' * 2}📝 [bold]Writing validation results to file[/bold]{'.' * 4} ", end="")
        with output_file.open("w", encoding="utf-8") if output_file else sys.stdout as f:
            out = Console(color_system=None, width=output_line_width, height=31, file=f)
            out.register_formatter(TextOutputFormatter())
            out.print(result.statistics)  # Output the statistics first
            if not result.passed() and verbose:
                out.print(result)
        if interactive:
            console.print(f"[bold green]{output_file}[/bold green]", end="\n")
    return result


def _emit_json_report(
    results: dict,
    profile_identifiers: list[str],
    is_valid: bool,
    *,
    console: Console,
    interactive: bool,
    output_file: Path | None,
    output_line_width: int | None,
    session: ValidationSession | None = None,
    verbose: bool = False,
) -> None:
    """
    Write the aggregated validation results as JSON to a file or stdout.

    With a ``session`` the report is the v2 projection of that session; without
    one it is the legacy per-profile document.
    """
    if interactive:
        if is_valid:
            console.print(
                f"\n{' ' * 2}✅ [bold]Validation [green]PASSED![/green]. "
                f"\n{' ' * 5}RO-Crate is valid according to the profile(s): "
                f"[cyan]{', '.join(profile_identifiers)}[/cyan][/bold]"
            )
        else:
            console.print(f"\n{' ' * 2}❌ [bold]Validation [red]FAILED![/red][/bold]")
        if output_file:
            console.print(
                f"\n{' ' * 2}📝 [bold]Writing validation results in JSON format "
                f'to the file "{output_file}"[/bold]{"." * 4} ',
                end="",
            )
        else:
            console.print(f"\n{' ' * 2}📋 [bold]The validation report in JSON format: [/bold]\n")

    # Generate the JSON output and write it to the specified output file or to stdout
    with output_file.open("w", encoding="utf-8") if output_file else nullcontext(sys.stdout) as f:
        if session is None:
            out = Console(color_system=None, width=output_line_width, file=f)
            out.register_formatter(JSONOutputFormatter())
            # Disable word-wrap/cropping: Rich would otherwise insert literal line
            # breaks into long string values (e.g. messages, URLs), producing
            # invalid, unescaped control characters in the JSON output.
            out.print(results, soft_wrap=True)
        else:
            dump_json(build_report(session, passed=is_valid, verbose=verbose), f)

    if interactive and output_file:
        console.print("[bold]DONE![/bold]", end="\n\n")
