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


import contextlib
import shutil
import signal
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from fnmatch import fnmatch
from pathlib import Path

from rocrate_validator.constants import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_GATEWAY_TIMEOUT,
    ROCRATE_METADATA_FILE,
    RUN_STATE_TTL_DAYS,
)
from rocrate_validator.errors import ProfileNotFound
from rocrate_validator.events import Subscriber
from rocrate_validator.models import (
    BatchCrateEntry,
    BatchSession,
    BatchValidationResult,
    Profile,
    Severity,
    ValidationCache,
    ValidationResult,
    ValidationSession,
    ValidationSettings,
    Validator,
)
from rocrate_validator.utils import log as logging
from rocrate_validator.utils.http import HttpRequester
from rocrate_validator.utils.paths import (
    get_batch_session_path,
    get_profiles_path,
    get_run_state_path,
    get_user_runs_dir,
)
from rocrate_validator.utils.uri import URI

# set the default profiles path
DEFAULT_PROFILES_PATH = get_profiles_path()

# set up logging
logger = logging.getLogger(__name__)


def detect_profiles(settings: dict | ValidationSettings, cache: ValidationCache | None = None) -> list[Profile]:
    # initialize the validator
    validator = __initialise_validator__(settings, cache=cache)
    # detect the profiles
    profiles = validator.detect_rocrate_profiles()
    logger.debug("Profiles detected: %s", profiles)
    return profiles


def validate_metadata_as_dict(
    metadata_dict: dict,
    settings: dict | ValidationSettings,
    subscribers: list[Subscriber] | None = None,
    cache: ValidationCache | None = None,
) -> ValidationResult:
    """
    Validate the RO-Crate metadata only against a profile and return the validation result.
    """
    assert metadata_dict is not None, "Metadata dictionary cannot be None"
    assert isinstance(metadata_dict, dict), "Metadata must be a dictionary"
    # set the RO-Crate metadata dictionary in the settings
    if isinstance(settings, dict):
        settings["metadata_dict"] = metadata_dict
        settings["metadata_only"] = True
    else:
        settings.metadata_dict = metadata_dict
        settings.metadata_only = True
    # validate the RO-Crate metadata
    return validate(settings, subscribers, cache=cache)


def validate(
    settings: dict | ValidationSettings,
    subscribers: list[Subscriber] | None = None,
    cache: ValidationCache | None = None,
) -> ValidationResult:
    """
    Validate a RO-Crate against a profile and return the validation result

    :param settings: the validation settings
    :type settings: Union[dict, ValidationSettings]

    :param subscribers: the list of subscribers
    :type subscribers: Optional[list[Subscriber]]

    :param cache: an optional cache of loaded profiles/shapes; sharing the
        same instance across calls avoids re-parsing them on every validation
    :type cache: Optional[ValidationCache]

    :return: the validation result
    :rtype: ValidationResult

    """
    # initialize the validator
    validator = __initialise_validator__(settings, subscribers, cache=cache)
    # validate the RO-Crate
    result = validator.validate()
    logger.debug("Validation completed: %s", result)
    return result


def _build_validator(
    settings: ValidationSettings, subscribers: list[Subscriber] | None, cache: ValidationCache | None = None
) -> Validator:
    """Create a validator for the given settings and register any subscribers."""
    validator = Validator(settings, cache=cache)
    logger.debug("Validator created. Starting validation...")
    if subscribers:
        for subscriber in subscribers:
            validator.add_subscriber(subscriber)
    return validator


def _extract_and_validate(
    settings: ValidationSettings,
    subscribers: list[Subscriber] | None,
    rocrate_path: Path,
    cache: ValidationCache | None = None,
) -> Validator:
    """Extract a (local or downloaded) zipped RO-Crate to a temp dir and validate it."""
    original_data_path = settings.rocrate_uri
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            with zipfile.ZipFile(rocrate_path, "r") as zip_ref:
                zip_ref.extractall(tmp_dir)
                logger.debug("RO-Crate extracted to temporary directory: %s", tmp_dir)
            settings.rocrate_uri = URI(str(tmp_dir))
            return _build_validator(settings, subscribers, cache=cache)
        finally:
            if original_data_path is not None:
                settings.rocrate_uri = original_data_path
                logger.debug("Original data path restored: %s", original_data_path)


def _download_remote_rocrate(
    settings: ValidationSettings,
    subscribers: list[Subscriber] | None,
    rocrate_path: URI,
    cache: ValidationCache | None = None,
) -> Validator:
    """Download a remote (http/https/ftp) RO-Crate to a temp file, then extract and validate it."""
    logger.debug("RO-Crate is a remote RO-Crate")
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        requester = HttpRequester()
        offline = bool(getattr(settings, "offline", False))
        # In offline mode, the cache is the only source of truth. Otherwise,
        # bypass the cache to refresh the stored copy so that subsequent
        # offline runs validate against the latest known remote state.
        if offline:
            response = requester.get(rocrate_path.uri, stream=True, allow_redirects=True)
        else:
            response = requester.fetch_fresh(rocrate_path.uri, stream=True, allow_redirects=True)
        with response as r:
            if r.status_code >= HTTP_STATUS_BAD_REQUEST:
                if offline and r.status_code == HTTP_STATUS_GATEWAY_TIMEOUT:
                    raise FileNotFoundError(
                        f"Remote RO-Crate '{rocrate_path.uri}' is not available in the HTTP cache. "
                        f"Validate it online first, or run "
                        f"`rocrate-validator cache warm --crate '{rocrate_path.uri}'`."
                    )
                raise FileNotFoundError(
                    f"Failed to download remote RO-Crate '{rocrate_path.uri}' (status {r.status_code})."
                )
            with Path(tmp_file.name).open("wb") as f:
                shutil.copyfileobj(r.raw, f)
        logger.debug("RO-Crate downloaded to temporary file: %s", tmp_file.name)
        return _extract_and_validate(settings, subscribers, Path(tmp_file.name), cache=cache)


def __initialise_validator__(
    settings: dict | ValidationSettings,
    subscribers: list[Subscriber] | None = None,
    cache: ValidationCache | None = None,
) -> Validator:
    """
    Validate a RO-Crate against a profile
    """
    # if settings is a dict, convert to ValidationSettings
    settings = ValidationSettings.parse(settings)

    # Validating an in-memory metadata dictionary needs no crate on disk: there
    # is no URI to resolve, so the source-resolution below does not apply.
    if getattr(settings, "metadata_dict", None) is not None:
        return _build_validator(settings, subscribers, cache=cache)

    # parse the rocrate path
    assert settings.rocrate_uri is not None, "RO-Crate URI is required"
    rocrate_path: URI = URI(str(settings.rocrate_uri))
    logger.debug("Validating RO-Crate: %s", rocrate_path)

    # check if the RO-Crate exists
    if (
        not getattr(settings, "metadata_only", False)
        and getattr(settings, "metadata_dict", None) is None
        and not rocrate_path.is_available()
    ):
        raise FileNotFoundError(f"RO-Crate not found: {rocrate_path}")

    # check if remote validation is enabled
    disable_remote_crate_download = settings.disable_remote_crate_download
    logger.debug("Remote validation: %s", disable_remote_crate_download)
    if disable_remote_crate_download:
        return _build_validator(settings, subscribers, cache=cache)

    # Resolve the RO-Crate source: remote URL, local ZIP, or local directory.
    # We support http/https/ftp protocols to download a remote RO-Crate.
    if rocrate_path.scheme in ("http", "https", "ftp"):
        return _download_remote_rocrate(settings, subscribers, rocrate_path, cache=cache)
    if rocrate_path.as_path().suffix == ".zip":
        logger.debug("RO-Crate is a local ZIP file")
        return _extract_and_validate(settings, subscribers, rocrate_path.as_path(), cache=cache)
    if rocrate_path.is_local_directory():
        logger.debug("RO-Crate is a local directory")
        settings.rocrate_uri = URI(str(rocrate_path.as_path()))
        return _build_validator(settings, subscribers, cache=cache)
    raise ValueError(
        f"Invalid RO-Crate URI: {rocrate_path}. It MUST be a local directory or a ZIP file (local or remote)."
    )


def discover_ro_crates(
    directory: Path,
    pattern: str = "*",
) -> list[Path]:
    """
    Scan a directory for the RO-Crates it contains.

    The directory is treated as the root of a collection of crates: when it
    *directly* contains at least one crate, only that level is inspected. A
    crate is discovered when:

    - the scan directory itself holds an ``ro-crate-metadata.json`` (a crate
      defined directly in the scan root);
    - an immediate subdirectory holds an ``ro-crate-metadata.json``;
    - an immediate entry is a ``.zip`` file (a zipped crate);
    - an immediate file is a detached crate metadata file, i.e. its name ends
      with ``ro-crate-metadata.json`` (e.g. ``crate_0001-ro-crate-metadata.json``);
      several such files can coexist in the same directory.

    When the directory contains no crate at all, its subdirectories are
    explored recursively until levels holding crates are found; the result is
    the union of those nested collections (e.g. a corpus organised per source
    as ``<root>/<source>/<crate>``). Hidden directories and symbolic links are
    not traversed, and crate payloads (data entities nested inside a crate)
    are never descended into.

    All results are filtered by the glob ``pattern`` against the crate name
    (intermediate directories are not matched against the pattern).

    :param directory: the directory to scan
    :param pattern: glob pattern to filter crates by name (default: ``*``)
    :return: sorted list of discovered RO-Crate paths
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    return sorted(c for c in _discover_crate_collection(directory) if fnmatch(c.name, pattern))


def _crates_directly_in(directory: Path) -> set[Path]:
    """The crates *directly* contained in ``directory`` (no pattern filtering)."""
    crates: set[Path] = set()

    # The directory itself may be a crate (its own ``ro-crate-metadata.json``).
    if (directory / ROCRATE_METADATA_FILE).exists():
        crates.add(directory)

    # Immediate children: subdirectory crates, zipped crates and detached crate
    # metadata files (single pass).
    for entry in directory.iterdir():
        if entry.is_dir():
            if (entry / ROCRATE_METADATA_FILE).exists():
                crates.add(entry)
        elif entry.suffix == ".zip":
            crates.add(entry)
        elif entry.name.endswith(ROCRATE_METADATA_FILE) and entry.name != ROCRATE_METADATA_FILE:
            # A detached crate defined directly as a (prefixed) metadata file;
            # the plain ``ro-crate-metadata.json`` is covered by the
            # directory-is-a-crate check above.
            crates.add(entry)

    return crates


def _discover_crate_collection(directory: Path) -> set[Path]:
    """
    The crate collection rooted at ``directory``: its direct crates when it
    holds any (the level is a collection root and the descent stops there),
    otherwise the union of the collections found by descending into its
    visible, non-symlink subdirectories.
    """
    crates = _crates_directly_in(directory)
    if crates:
        return crates
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith("."):
            try:
                crates |= _discover_crate_collection(entry)
            except OSError as e:  # unreadable subtree: skip it, keep scanning
                logger.debug("Skipping unreadable directory %s: %s", entry, e)
    return crates


def normalize_state_targets(targets: list[str | Path]) -> list[str]:
    """
    Normalize the user-supplied batch targets into the stable strings used to
    key a state file: local paths are resolved to absolute paths, remote URIs
    are kept as-is (never run through ``Path.resolve()``). Explicit lists are
    sorted so the key does not depend on the order the targets were passed in.
    """
    normalized: list[str] = []
    for target in targets:
        uri = URI(str(target))
        normalized.append(str(uri.as_path().resolve()) if not uri.is_remote_resource() else str(uri))
    return sorted(normalized)


def _state_key_parts(
    settings: ValidationSettings,
    targets: list[str],
    pattern: str,
    profile_identifiers: list[str] | None,
    no_auto_profile: bool,
) -> list[str]:
    """
    The components that deterministically identify a batch state file.

    The key is anchored to the *user input* (the scan root or the explicit
    target list, already normalized by :func:`normalize_state_targets`), never
    to the discovered crate list: crates added to a collection between runs
    must not change the key, so an interrupted run still matches and the new
    crates simply join the pending set on resume.
    """
    settings_dict = settings.to_dict() if hasattr(settings, "to_dict") else {}
    # With explicit profiles the key is their sorted list; otherwise it encodes
    # per-crate auto-detection (or the base-profile fallback when disabled).
    profile_key = str(sorted(profile_identifiers)) if profile_identifiers else f"auto:{not no_auto_profile}"
    # `requirement_severity_only` is dropped by ``ValidationSettings.to_dict()``,
    # so read it from the settings object directly rather than from the dict.
    severity_only = bool(
        getattr(settings, "requirement_severity_only", settings_dict.get("requirement_severity_only", False))
    )
    return [
        *targets,
        pattern,
        profile_key,
        str(settings_dict.get("requirement_severity", "")),
        str(severity_only),
    ]


def resolve_run_state_path(
    settings: ValidationSettings,
    targets: list[str],
    pattern: str = "*",
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
) -> Path:
    """
    Resolve the temporary run-state file path for a batch target.

    Mirrors :func:`resolve_batch_session_path` but addresses the runs
    directory: the path is derived deterministically from the user-supplied
    targets (see :func:`normalize_state_targets`) and the settings that affect
    the outcome, so re-running the same command finds the same run-state and
    an interrupted run can be resumed with ``validate --resume``.
    """
    return get_run_state_path(_state_key_parts(settings, targets, pattern, profile_identifiers, no_auto_profile))


def resolve_session_state_path(
    settings: ValidationSettings,
    targets: list[str],
    pattern: str = "*",
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
) -> Path:
    """
    Resolve the auto-managed (unnamed) session file path for a batch target.

    Same deterministic key as :func:`resolve_run_state_path`, addressed under
    the sessions directory: re-running ``validate --session`` on the same
    target with the same criteria maps to the same session file.
    """
    return get_batch_session_path(_state_key_parts(settings, targets, pattern, profile_identifiers, no_auto_profile))


def resolve_batch_session_path(
    settings: ValidationSettings,
    scan_root: Path,
    pattern: str,
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
) -> Path:
    """
    Resolve the auto-managed session file path for a single-scan-root batch.

    The path is derived deterministically from the scan root, the discovery
    options and the validation settings that affect the outcome (profiles and
    severity), so that re-running the same command resolves to the same file.
    Changing the profile selection or severity intentionally starts a new
    session.

    The profile part reflects what is *actually* applied per crate: the explicit
    ``profile_identifiers`` list (order-independent), or the auto-detection mode
    when no profile is given. This keeps distinct profile selections (e.g. two
    different multi-profile sets) on separate sessions.
    """
    return resolve_session_state_path(
        settings,
        [str(Path(scan_root).resolve())],
        pattern,
        profile_identifiers=profile_identifiers,
        no_auto_profile=no_auto_profile,
    )


def cleanup_stale_run_states(ttl_days: int = RUN_STATE_TTL_DAYS) -> int:
    """
    Garbage-collect stale run-state files (best effort).

    Interrupted runs that are never resumed would otherwise accumulate in the
    runs directory forever, invisible to ``sessions list``. Every run-state
    whose file is older than ``ttl_days`` is removed; failures are ignored.

    :param ttl_days: age threshold in days (defaults to ``RUN_STATE_TTL_DAYS``)
    :return: the number of files removed
    """
    runs_dir = get_user_runs_dir()
    if not runs_dir.is_dir():
        return 0
    cutoff = time.time() - ttl_days * 24 * 3600
    removed = 0
    for state_file in runs_dir.glob("*.json"):
        try:
            if state_file.stat().st_mtime < cutoff:
                state_file.unlink()
                removed += 1
        except OSError as e:
            logger.debug("Could not garbage-collect run-state %s: %s", state_file, e)
    if removed:
        logger.debug("Garbage-collected %d stale run-state(s)", removed)
    return removed


def resolve_single_crate_session_path(
    settings: ValidationSettings,
    rocrate_uri: str | Path,
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
) -> Path:
    """
    Resolve the auto-managed session file path for a single-crate validation.

    Mirrors :func:`resolve_batch_session_path`: the path is derived
    deterministically from the crate URI and the settings that affect the
    outcome, so re-validating the same crate with the same criteria overwrites
    the same history entry instead of accumulating duplicates.
    """
    settings_dict = settings.to_dict() if hasattr(settings, "to_dict") else {}
    profile_key = str(sorted(profile_identifiers)) if profile_identifiers else f"auto:{not no_auto_profile}"
    severity_only = bool(
        getattr(settings, "requirement_severity_only", settings_dict.get("requirement_severity_only", False))
    )
    uri = URI(str(rocrate_uri))
    target = str(uri.as_path().resolve()) if uri.is_local_resource() else str(uri)
    key_parts = [
        target,
        "single",
        profile_key,
        str(settings_dict.get("requirement_severity", "")),
        str(severity_only),
    ]
    return get_batch_session_path(key_parts)


def _load_previous_session(session_path: Path | None) -> BatchSession | None:
    """Load an existing batch session for auto-resume, or ``None`` if unavailable."""
    if not session_path or not Path(session_path).exists():
        return None
    try:
        return BatchSession.load(Path(session_path))
    except Exception:
        logger.warning("Could not load batch session at %s; starting a fresh session.", session_path)
        return None


def _prepare_batch_session(
    settings: ValidationSettings,
    rocrate_uris: list[str],
    state_path: Path | None,
    fresh: bool,
) -> tuple[BatchSession, list[str]]:
    """
    Create or resume a batch session and return it together with the
    URIs that still need to be validated.

    A previous state is resumed only when it exists and is *not* already
    completed (i.e. it was interrupted): in that case the crates that were
    already validated are carried over and only the remaining (plus any newly
    discovered) crates are validated. A completed or missing state — or an
    explicit ``fresh`` request — starts a brand-new session that revalidates
    everything.
    """
    settings_dict = settings.to_dict() if hasattr(settings, "to_dict") else {}
    session = BatchSession(
        validation_settings=settings_dict,
        crate_paths=rocrate_uris,
        session_path=state_path,
    )

    previous = None if fresh else _load_previous_session(state_path)
    if previous is None or previous.is_completed():
        return session, list(rocrate_uris)

    # Resume an interrupted session: carry over the crates that were validated
    # and validate the rest. Newly discovered crates are included as pending,
    # and so are the crates that errored out: an error is often transient (an
    # unreachable URI, a locked file), so a resume gives them another go.
    completed = {e.path: e for e in previous.crates if e.status == "completed"}
    session.crates = [completed.get(p) or BatchCrateEntry(path=p, status="pending") for p in rocrate_uris]
    # the definitions that the carried-over issues reference by identifier
    session.check_definitions = dict(previous.check_definitions)
    session.requirement_definitions = dict(previous.requirement_definitions)
    session.profile_definitions = dict(previous.profile_definitions)
    pending = [e.path for e in session.crates if e.status != "completed"]
    logger.info(
        "Resuming batch session: %d/%d crates already validated, %d to validate",
        session.total_crates - len(pending),
        session.total_crates,
        len(pending),
    )
    return session, pending


def _resolve_crate_profiles(
    settings: ValidationSettings,
    crate_path: str,
    profile_identifiers: list[str] | None,
    no_auto_profile: bool,
    cache: ValidationCache | None = None,
) -> list[str]:
    """
    Resolve the profile identifier(s) to validate a single batch crate against.

    Mirrors single-crate behaviour: an explicit ``--profile-identifier`` list wins
    and is applied to every crate; otherwise the profile is auto-detected from the
    crate itself (unless auto-detection is disabled); falling back to the base
    ``ro-crate`` profile when nothing can be resolved.
    """
    if profile_identifiers:
        return list(profile_identifiers)
    if not no_auto_profile:
        try:
            crate_settings_dict = settings.to_dict() if hasattr(settings, "to_dict") else {}
            crate_settings = ValidationSettings.parse({**crate_settings_dict, "rocrate_uri": str(crate_path)})
            detected = detect_profiles(crate_settings, cache=cache)
            if detected:
                return [p.identifier for p in detected]
        except Exception as e:  # pragma: no cover - detection is best-effort
            logger.debug("Per-crate profile auto-detection failed for %s: %s", crate_path, e)
    return ["ro-crate"]


def _validate_one_in_batch(
    settings: ValidationSettings,
    session: BatchSession,
    crate_path: str,
    idx: int,
    total: int,
    progress_callback: Callable[..., None] | None,
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
    cache: ValidationCache | None = None,
) -> list[tuple[str, ValidationResult]] | None:
    """
    Validate a single crate inside a batch, updating the session and emitting progress.

    The crate is validated against each profile resolved for it (see
    :func:`_resolve_crate_profiles`) and the per-profile outcomes are combined into
    a single session entry (the crate passes only when it passes every profile).

    Returns the list of ``(path, result)`` pairs (one per profile) on success, or
    ``None`` if validation raised.
    """
    start = time.time()
    entry = session._find_entry(str(crate_path))
    if entry:
        entry.status = "in_progress"
    if progress_callback:
        progress_callback(str(crate_path), idx + 1, total, "validating", None)

    try:
        crate_settings_dict = settings.to_dict() if hasattr(settings, "to_dict") else {}
        profiles = _resolve_crate_profiles(settings, str(crate_path), profile_identifiers, no_auto_profile, cache=cache)
        profile_results: list[tuple[str, ValidationResult]] = []
        for profile in profiles:
            crate_settings = ValidationSettings.parse(
                {
                    **crate_settings_dict,
                    "rocrate_uri": str(crate_path),
                    "profile_identifier": profile,
                }
            )
            profile_results.append((profile, validate(crate_settings, cache=cache)))
        session.add_results(str(crate_path), profile_results, time.time() - start)
        if progress_callback:
            passed = all(r.passed() for _, r in profile_results)
            status = "passed" if passed else "failed"
            total_issues = sum(len(r.issues) for _, r in profile_results)
            # The view styles the line; pass the issue-count message and the
            # profile(s) the crate was validated against separately.
            progress_callback(str(crate_path), idx + 1, total, status, f"({total_issues} issues)", profiles)
        return [(str(crate_path), r) for _, r in profile_results]
    except Exception as e:
        session.mark_errored(str(crate_path), str(e), time.time() - start)
        if progress_callback:
            progress_callback(str(crate_path), idx + 1, total, "error", str(e))
        return None


def session_validate(
    session: ValidationSession,
    rocrate_uri: str | Path,
    profile_identifiers: list[str] | str | None = None,
    no_auto_profile: bool | None = None,
    settings: dict | None = None,
) -> list[tuple[str, ValidationResult]] | None:
    """
    Validate a crate within a :class:`ValidationSession`, recording the outcome
    as a session entry and reusing the session-owned cache.

    This is the orchestration behind :meth:`ValidationSession.validate`; see
    its documentation for the semantics (profile resolution, overwrite on
    re-validation, error recording).
    """
    if isinstance(profile_identifiers, str):
        profile_identifiers = [profile_identifiers]
    if profile_identifiers is None:
        profile_identifiers = session.profile_identifiers
    if no_auto_profile is None:
        no_auto_profile = session.no_auto_profile

    crate_path = str(rocrate_uri)
    merged_settings = ValidationSettings.parse(
        {**session.validation_settings, **(settings or {}), "rocrate_uri": crate_path}
    )
    session._ensure_entry(crate_path)
    outcome = _validate_one_in_batch(
        merged_settings,
        session,
        crate_path,
        idx=session.total_crates - 1,
        total=session.total_crates,
        progress_callback=None,
        profile_identifiers=profile_identifiers,
        no_auto_profile=no_auto_profile,
        cache=session.cache,
    )
    # Keep the persisted history recoverable as the session grows. Throttled
    # like a batch run, and for the same reason: a script validating hundreds of
    # crates through this call would otherwise rewrite the whole session after
    # each one. Closing the session saves it unconditionally.
    session.save_if_due()
    return outcome


def _discard_completed_run_state(session: BatchSession, state_path: Path | None, ephemeral: bool) -> None:
    """
    Remove the run-state of a completed run.

    An ephemeral run-state only exists to make interrupted runs resumable: once
    the batch completes it is deleted; when the run did not finish (e.g. a crate
    raised and stayed pending) it persists for ``--resume``.
    """
    if not (ephemeral and state_path is not None and session.is_completed()):
        return
    try:
        Path(state_path).unlink(missing_ok=True)
    except OSError as e:
        logger.debug("Could not remove completed run-state %s: %s", state_path, e)


def _save_final_state(session: BatchSession, progress_callback: Callable | None, total: int) -> None:
    """Record the definitive state of a batch run, whatever brought it to an end."""
    if progress_callback:
        # announcing the save is cosmetic — writing a large session takes a
        # moment and the UI should show it — so it must never mask the
        # exception that may be unwinding through here
        with contextlib.suppress(Exception):
            progress_callback("", total, total, "saving", None)
    session.status = "completed" if session.is_completed() else "interrupted"
    session.save()


def batch_validate(
    settings: ValidationSettings,
    rocrate_uris: list[str],
    state_path: Path | None = None,
    fresh: bool = False,
    ephemeral: bool = True,
    progress_callback: Callable | None = None,
    profile_identifiers: list[str] | None = None,
    no_auto_profile: bool = False,
    keep_results: bool = False,
    cache: ValidationCache | None = None,
) -> BatchValidationResult:
    """
    Validate multiple RO-Crates in batch mode.

    The batch state is persisted incrementally to ``state_path`` and resumed
    when an interrupted state for the same target already exists (unless
    ``fresh`` is set). The state file is written directly at its final
    location for the whole run — there is no promotion/copy step — so an
    interrupted run is always resumable from that same file:

    - ``ephemeral=True`` (run-state, see :func:`resolve_run_state_path`): the
      file is **deleted on completion** and persists only when the run is
      interrupted, for ``validate --resume``;
    - ``ephemeral=False`` (session): the file persists after completion as a
      permanent, browsable session (``sessions list/show/report``), and with
      status ``interrupted`` when the run does not finish (``sessions resume``).

    Profiles are resolved *per crate*: an explicit ``profile_identifiers`` list is
    applied to every crate, otherwise each crate's profile is auto-detected
    (unless ``no_auto_profile`` is set), matching single-crate validation.

    :param settings: shared validation settings (severity, cache, availability, etc.)
    :param rocrate_uris: list of RO-Crate paths to validate
    :param state_path: path where the batch state is saved/resumed (run-state
        or session file, resolved by the caller); ``None`` disables persistence
    :param fresh: ignore any existing state and revalidate everything
    :param ephemeral: delete the state file on completion (run-state semantics);
        set to ``False`` to keep it as a permanent session
    :param progress_callback: optional callable(crate_path, index, total, status, message)
    :param profile_identifiers: explicit profiles to validate every crate against
    :param no_auto_profile: disable per-crate profile auto-detection
    :param keep_results: retain the live :class:`ValidationResult` of every
        crate in :attr:`BatchValidationResult.live_results`. Off by default because
        each result pins its full validation context (loaded profiles with
        their shape graphs, the crate data graph), so memory grows linearly
        with the batch size; enable it only for debugging or interactive
        exploration (e.g. notebooks) on batches that fit in memory
    :param cache: an optional shared cache of loaded profiles/shapes; when
        absent, one is created for (and scoped to) this batch run
    :return: aggregated batch validation result
    """
    session, rocrate_uris = _prepare_batch_session(settings, rocrate_uris, state_path, fresh)
    # Persist the profile resolution options on the session so it can be resumed
    # later (e.g. via `sessions resume`) with exactly the same criteria.
    session.profile_identifiers = list(profile_identifiers) if profile_identifiers else None
    session.no_auto_profile = no_auto_profile
    session.requirement_severity_only = bool(getattr(settings, "requirement_severity_only", False))
    results: list[tuple[str, ValidationResult]] = []
    total = len(rocrate_uris)
    # Write the session before validating anything: until the first save the run
    # leaves no trace on disk, so a process that dies early — or during a first
    # crate slow enough to outlast the save throttle — leaves nothing to resume.
    session.save()

    # Register SIGINT handler for graceful interruption. The state file is
    # saved (never deleted) so the run stays resumable.
    resume_hint = (
        "Re-run the same command with --resume to continue."
        if ephemeral
        else "Resume it with `rocrate-validator sessions resume`."
    )

    interrupted = False

    def _sigint_handler(_signum, _frame):
        # The handler runs at an arbitrary point of the run, so it does no I/O
        # and does not exit: it raises a flag the loop reads between two crates,
        # where the session is in a consistent state. Saving or exiting from
        # here could land in the middle of a save, or leave the crate being
        # validated recorded as neither done nor pending.
        nonlocal interrupted
        if interrupted:
            # asked twice: the crate in flight is not worth waiting for. What
            # was already validated is still written out by the finally below.
            raise KeyboardInterrupt
        interrupted = True
        print("\n⚠  Interrupting after the current crate… (Ctrl-C again to stop right away)", file=sys.stderr)

    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        # One cache for the whole batch: profiles/shapes parsed for one crate
        # are reused by every other crate resolving to the same key. The
        # session owns it, unless the caller shares an external one.
        cache = cache if cache is not None else session.cache
        for idx, crate_path in enumerate(rocrate_uris):
            # The returned live results are dropped unless explicitly asked
            # for: the outcome is already recorded in the session entry, and
            # retaining every ValidationResult would pin each crate's full
            # validation context (profiles, shape graphs, data graph), growing
            # memory linearly with the batch size until the OOM killer steps in.
            outcome = _validate_one_in_batch(
                settings,
                session,
                crate_path,
                idx,
                total,
                progress_callback,
                profile_identifiers,
                no_auto_profile,
                cache=cache,
            )
            if keep_results and outcome is not None:
                results.extend(outcome)
            # Save the session incrementally for crash/interrupt recovery, but
            # throttle it: re-serialising the whole session after every crate is
            # O(n^2) and dominates the run for big batches.
            session.save_if_due()
            if interrupted:
                break
    except KeyboardInterrupt:
        # the second Ctrl-C, raised by the handler: the crate in flight is
        # abandoned and stays pending, everything before it is kept
        interrupted = True
    finally:
        signal.signal(signal.SIGINT, original_handler)
        # The final save belongs here: an exception escaping the loop must not
        # cost the crates already validated, which is precisely when the saved
        # state is worth the most.
        _save_final_state(session, progress_callback, total)

    if interrupted:
        print(f"\n⚠  Batch interrupted. {resume_hint}", file=sys.stderr)
        sys.exit(130)

    _discard_completed_run_state(session, state_path, ephemeral)
    return BatchValidationResult(session, results)


def get_profiles(
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    extra_profiles_path: Path | None = None,
    severity=Severity.OPTIONAL,
    allow_requirement_check_override: bool = ValidationSettings.allow_requirement_check_override,
) -> list[Profile]:
    """
    Get the list of profiles supported by the package.
    The profile source path can be overridden by specifying ``profiles_path``.

    :param profiles_path: the path to the profiles directory
    :type profiles_path: Path

    :param severity: the severity level
    :type severity: Severity

    :param allow_requirement_check_override: a flag to enable or disable
        the requirement check override (default: ``True``).
        If ``True``, the requirement check of a profile ``A`` can be overridden
        by the requirement check of a profile extension ``B`` (i.e., when ``B extends A``)
        if they share the same name.
        If ``False``, a profile extension ``B`` can only
        add new requirements to the profile ``A`` (i.e., checks with name not present in ``A``)
        and an error is raised if a check with the same name is found in both profiles.
    :type allow_requirement_check_override: bool

    :return: the list of profiles
    :rtype: list[Profile]
    """
    profiles = Profile.load_profiles(
        profiles_path,
        extra_profiles_path=extra_profiles_path,
        severity=severity,
        allow_requirement_check_override=allow_requirement_check_override,
    )
    logger.debug("Profiles loaded: %s", profiles)
    return profiles


def get_profile(
    profile_identifier: str,
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    extra_profiles_path: Path | None = None,
    severity=Severity.OPTIONAL,
    allow_requirement_check_override: bool = ValidationSettings.allow_requirement_check_override,
) -> Profile:
    """
    Get the profile with the given identifier.
    The profile source path can be overridden through ``profiles_path``.
    The profile is loaded based on the given severity level and the requirement check override flag.

    :param profile_identifier: the profile identifier
    :type profile_identifier: str

    :param profiles_path: the path to the profiles directory
    :type profiles_path: Path

    :param severity: the severity level
    :type severity: Severity

    :param allow_requirement_check_override: a flag to enable or disable
        the requirement check override (default: ``True``).
        If ``True``, the requirement check of a profile ``A`` can be overridden
        by the requirement check of a profile extension ``B`` (i.e., when ``B extends A``)
        if they share the same name.
        If ``False``, a profile extension ``B`` can only
        add new requirements to the profile ``A`` (i.e., checks with name not present in ``A``)
        and an error is raised if a check with the same name is found in both profiles.
    :type allow_requirement_check_override: bool

    :return: the profile
    :rtype: Profile

    """
    profiles = get_profiles(
        profiles_path,
        extra_profiles_path=extra_profiles_path,
        severity=severity,
        allow_requirement_check_override=allow_requirement_check_override,
    )
    profile = Profile.find_in_list(profiles, profile_identifier)
    if profile is None:
        raise ProfileNotFound(profile_identifier)
    return profile
