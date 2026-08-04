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

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from rich.cells import cell_len
from rich.console import Group
from rich.padding import Padding
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table

from rocrate_validator.models.outcome import crate_counts, crate_outcome
from rocrate_validator.models.severity import Severity
from rocrate_validator.utils import log as logging
from rocrate_validator.utils.io_helpers.colors import get_severity_color
from rocrate_validator.utils.io_helpers.output.console import Console
from rocrate_validator.utils.io_helpers.output.text import TextOutputFormatter
from rocrate_validator.utils.io_helpers.output.text.layout.report import ValidationReportLayout

if TYPE_CHECKING:
    from collections.abc import Callable

    from rocrate_validator.models import (
        BatchCrateEntry,
        BatchValidationResult,
        ValidationResult,
        ValidationSession,
        ValidationSettings,
        ValidationStatistics,
    )
    from rocrate_validator.utils.io_helpers.output.pager import SystemPager

# set up logging
logger = logging.getLogger(__name__)

# Number of bytes per unit step when formatting human-readable sizes.
_BYTES_PER_UNIT = 1024
# Minimum path components below the common prefix needed to derive a source label.
_MIN_REL_PARTS_FOR_SOURCE = 2


def _severity_rank(severity_name: str) -> int:
    """Sort key for serialized severity names (unknown names sort last)."""
    try:
        return int(Severity[severity_name].value)
    except KeyError:
        return -1


class _SpacedProgress(Progress):
    """
    A :class:`rich.progress.Progress` that renders a blank line above its status
    bar, separating the live ``Batch: … passed … failed`` line from the per-crate
    results printed above it. The blank is part of the (transient) live region, so
    it is cleared together with the bar when validation ends.
    """

    def get_renderable(self):
        return Group("", super().get_renderable())


def format_crate_line(
    index: int,
    total: int,
    *,
    status: str,
    name: str,
    detail: str = "",
    profiles: list[str] | None = None,
    index_width: int | None = None,
    name_width: int = 0,
) -> str:
    """
    Render a single per-crate result line, shared by the live batch run and the
    static ``sessions show`` rendering so both stay identical.

    ``status`` is one of ``passed`` / ``failed`` / ``error`` / ``pending``;
    ``detail`` is the trailing text (e.g. ``(3 issues)`` or an error message).
    The running index is right-aligned and the name left-padded so the status
    text lines up across rows.
    """
    iw = index_width if index_width is not None else len(str(total))
    idx = f"[{index:>{iw}}/{total}]"
    name_cell = f"{name:<{name_width}}"
    prof = f"  [white]profile:[/white] [bold magenta]{', '.join(profiles)}[/bold magenta]" if profiles else ""
    if status == "passed":
        return f"  [green]✓[/green] {idx} {name_cell}  [bold green]passed[/bold green] [green]{detail}[/green]{prof}"
    if status == "failed":
        return f"  [red]✗[/red] {idx} {name_cell}  [bold red]failed[/bold red] [red]{detail}[/red]{prof}"
    if status == "error":
        return f"  [yellow]⚠[/yellow] {idx} {name_cell}  [yellow]{detail}[/yellow]"
    return f"  [dim]·[/dim] {idx} {name_cell}  [dim]pending[/dim]"


def format_batch_totals(counts: dict[str, int]) -> str:
    """
    The line closing the summary table, from the four disjoint buckets.

    ``counts`` is :func:`crate_counts` — the same counters the JSON report and
    ``sessions list`` are built from, so the three cannot drift into disagreeing
    on what a run did. Errored and pending crates are named only when there are
    any: on the ordinary run this reads exactly as it always did.
    """
    cells = [
        f"[green]{counts['passed_crates']} passed[/green]",
        f"[red]{counts['invalid_crates']} failed[/red]",
    ]
    if counts["errored_crates"]:
        cells.append(f"[yellow]{counts['errored_crates']} errored[/yellow]")
    if counts["pending_crates"]:
        cells.append(f"[dim]{counts['pending_crates']} pending[/dim]")
    return f"[bold]Total: {counts['total_crates']} crates | {' | '.join(cells)}[/bold]"


def format_batch_progress(*, passed: int, failed: int, errored: int, remaining: int) -> str:
    """
    The running tally shown under the progress bar.

    The three outcomes are counted apart, as everywhere else the run is
    reported: a crate the validation could not run on is not a crate that did
    not conform. Only the closing verdict unites failed and errored, and says
    so. The errored tally appears only once there is one — on a healthy run a
    column of zeros would steal room from the bar itself.
    """
    errored_cell = f"[yellow]{errored} errored[/yellow] " if errored else ""
    return (
        f"[bold]Batch:[/bold] "
        f"[green]{passed} passed[/green] "
        f"[red]{failed} failed[/red] "
        f"{errored_cell}"
        f"[dim]{remaining} remaining[/dim]"
    )


# The Status cell of the summary table, per crate outcome. A crate the
# validation could not run on is not a failed validation, and one that was
# never reached is neither: labelling both FAILED (as the cell used to, for
# anything that did not pass) told three different situations as one.
_SUMMARY_STATUS = {
    "passed": "[green]✓ PASSED[/green]",
    "invalid": "[red]✗ FAILED[/red]",
    "errored": "[yellow]⚠ ERROR[/yellow]",
    "pending": "[dim]· PENDING[/dim]",
}

_STATUS_STYLES = {
    "completed": "green",
    "in_progress": "yellow",
    "interrupted": "yellow",
    "unknown": "red",
}


def format_profile_selection(profile_identifiers: list[str] | None, no_auto_profile: bool) -> tuple[str, str]:
    """Return the profile-selection label and its Rich style for the header."""
    if profile_identifiers:
        return ", ".join(profile_identifiers), "magenta"
    if no_auto_profile:
        return "ro-crate (auto-detection disabled)", "dim italic"
    return "auto-detected per crate", "dim italic"


def render_batch_header(
    console: Console,
    *,
    headline: str,
    rows: list[tuple[str, str, str]],
    status: str | None = None,
) -> None:
    """
    Render the batch/session header: a headline (optionally with a coloured status
    badge) followed by a bullet list of ``(label, value, value_style)`` rows with
    bold labels aligned to a common width.

    Shared by the ``validate`` batch run and the ``sessions show``/``resume``
    commands so the header looks the same everywhere.
    """
    console.print()
    if status:
        st = _STATUS_STYLES.get(status, "white")
        headline = f"{headline}   [{st}]●[/{st}] [bold {st}]{status}[/bold {st}]"
    console.print(headline)
    console.print()
    label_width = max((len(label) for label, _, _ in rows), default=0)
    for label, value, value_style in rows:
        console.print(f"  [dim]•[/dim] [bold]{label:<{label_width}}[/bold]   [{value_style}]{value}[/{value_style}]")
    console.print()


class FooterRow(NamedTuple):
    """
    One line of the "where things went" block: an icon, a bold label, a path.

    ``note`` is an optional second line hanging under the path (same column),
    for what qualifies the destination rather than naming it — how many files
    were written there, say.
    """

    icon: str
    label: str
    path: str
    path_style: str
    note: str = ""


def render_details_block(console: Console, rows: list[FooterRow], *, indent: str = "  ") -> None:
    """
    Render the aligned ``icon · label · path`` block that tells where the output
    of a run was written.

    Labels are padded to a common width, and a row's ``note`` is printed under
    its path, in the same column. Shared by the batch footer and by the paths
    that have no verdict to print (a single crate written in split mode), so
    "where are my files" always looks the same.
    """
    if not rows:
        return
    label_width = max(len(row.label) for row in rows)
    for row in rows:
        label = f"[bold]{row.label:<{label_width}}[/bold]"
        console.print(f"{indent}{row.icon} {label}  [{row.path_style}]{row.path}[/{row.path_style}]")
        if row.note:
            # Align the note under the path: the icon is not always one cell wide.
            console.print(f"{indent}{' ' * (cell_len(row.icon) + 1 + label_width + 2)}[dim]{row.note}[/dim]")


def render_batch_footer(
    console: Console,
    batch_result: BatchValidationResult,
    rows: list[FooterRow],
) -> None:
    """
    Render the final batch verdict followed by an aligned details block.

    Shared by the ``validate`` and ``sessions resume`` commands so their output
    stays consistent. The whole block is indented by two spaces so the icons
    line up with the per-crate ``✓``/``✗`` marks printed above it.
    """
    indent = "  "
    if batch_result.passed():
        console.print(
            f"\n{indent}[green]✅ [bold]All {batch_result.total_crates()} RO-Crate(s) passed validation![/bold][/green]"
        )
    else:
        console.print(
            f"\n{indent}[red]❌ [bold]{len(batch_result.failed_entries())} "
            f"out of {batch_result.total_crates()} RO-Crate(s) failed validation.[/bold][/red]"
        )
    if rows:
        console.print()  # blank line separating the verdict from the details block
        render_details_block(console, rows, indent=indent)
    console.print()  # trailing blank line to separate the output from the next prompt


class ValidationCommandView:
    """
    A class to handle the validation command view
    """

    def __init__(
        self,
        validation_settings: ValidationSettings | None,
        interactive: bool = True,
        no_paging: bool = False,
        pager: SystemPager | None = None,
        console: Console | None = None,
    ):
        self.console = console or Console()
        self.interactive = interactive
        self.pager = pager if not no_paging else None
        # reference to the validation settings
        self.validation_settings = validation_settings
        # reference to the report layout
        self._report_layout: ValidationReportLayout | None = None

        # Register text output formatter
        self.console.register_formatter(TextOutputFormatter())

        logger.debug("ValidationCommandView initialized with console: %s", self.console)

    @property
    def report_layout(self) -> ValidationReportLayout:
        """
        Get the current report layout

        Returns:
            The current report layout
        """
        if self._report_layout is None:
            assert self.validation_settings is not None, "Validation settings must be set"
            self._report_layout = ValidationReportLayout(console=self.console, settings=self.validation_settings)

        return self._report_layout

    def show_validation_progress(self, validation_command: Callable) -> Any:
        """
        Show validation progress using a progress bar

        Args:
            validate_command: The validation command to execute

        Returns:
            The result of the validation command
        """
        logger.debug("Starting validation with progress bar")

        result = self.report_layout.live(
            lambda: validation_command(self.validation_settings, subscribers=self.report_layout.subscribers)
        )
        logger.debug("Validation completed  with result: %s", result)
        return result

    def display_validation_statistics(self, statistics: ValidationStatistics) -> None:
        """
        Display the validation statistics

        Args:
            statistics: The validation statistics
        """
        assert statistics is not None, "Validation statistics must be provided"

        with self.console.pager(pager=self.pager, styles=not self.console.no_color) if self.pager else self.console:
            self.console.print(statistics)

    def display_validation_result(self, result: ValidationResult) -> None:
        """
        Display the validation report layout

        Args:
            result: The validation result
        """
        assert result is not None, "Validation result must be provided"

        logger.debug("Displaying validation result")

        with self.console.pager(pager=self.pager, styles=not self.console.no_color) if self.pager else self.console:
            self.console.print(result)


class BatchValidationCommandView:
    """
    Displays batch validation progress and results in text mode.
    """

    def __init__(self, console: Console):
        self._console = console
        self.console.register_formatter(TextOutputFormatter())

    @property
    def console(self) -> Console:
        return self._console

    def run_with_progress(
        self,
        batch_validate_fn: Callable,
        settings: ValidationSettings,
        rocrate_uris: list[str],
        state_path: Path | None = None,
        fresh: bool = False,
        ephemeral: bool = True,
        profile_identifiers: list[str] | None = None,
        no_auto_profile: bool = False,
        base_path: Path | None = None,
        carried_over: dict[str, int] | None = None,
    ) -> BatchValidationResult:
        """
        Run batch validation with a persistent Rich progress bar on stderr.

        The progress bar stays visible at the bottom of the terminal during
        validation and is replaced by the summary once complete. When ``base_path``
        is given, each crate is shown relative to it so the lines stay short.

        :param carried_over: the outcomes a resumed run starts with (the buckets
            of :func:`crate_counts`). Only the pending crates are validated
            again, so without this the tally would open at zero and end up
            disagreeing with the summary table printed right below it.
        """
        total = len(rocrate_uris)
        carried = carried_over or {}
        passed_count = int(carried.get("passed_crates") or 0)
        failed_count = int(carried.get("invalid_crates") or 0)
        errored_count = int(carried.get("errored_crates") or 0)

        def _display(crate_path: str) -> str:
            """Render a crate path relative to ``base_path`` (the scan root) when possible."""
            if base_path is None:
                return crate_path
            try:
                rel = os.path.relpath(crate_path, base_path)
            except ValueError:
                return crate_path
            return "." if rel == os.curdir else rel

        # Column widths so the per-crate lines line up: a fixed-width running index
        # (e.g. "[ 1/43]") and crate names padded to the longest name, so the
        # trailing "passed (N issues)" / "failed (N issues)" all start at the same
        # column.
        index_width = len(str(total))
        name_width = max((len(_display(p)) for p in rocrate_uris), default=0)

        # Progress is a notice, not the report: on stderr it stays visible even
        # when stdout is redirected to a file (see :attr:`Console.notices`).
        progress_console = self.console.notices

        progress = _SpacedProgress(
            TextColumn("{task.description}", justify="left"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•", style="dim"),
            TimeElapsedColumn(),
            console=progress_console,
            transient=True,
            expand=True,
        )

        with progress:
            already_done = passed_count + failed_count + errored_count
            task = progress.add_task(
                description=(
                    format_batch_progress(
                        passed=passed_count,
                        failed=failed_count,
                        errored=errored_count,
                        remaining=total - already_done,
                    )
                    if already_done
                    else "[cyan]⏳ Initialising batch...[/cyan]"
                ),
                total=total,
                completed=already_done,
            )

            # `_total` is the service's own count — on a resume it covers the
            # pending crates alone. The tally and the numbering are about the
            # whole corpus, so they use `total` and the crates already done.
            def _progress_callback(crate_path, index, _total, status, message, profiles=None):
                nonlocal passed_count, failed_count, errored_count
                # Finalisation: writing a large session to disk can take a moment;
                # show it on the bar so the run does not look frozen at 100%.
                if status == "saving":
                    progress.update(task, description="[cyan]💾 Saving session…[/cyan]")
                    return
                disp = _display(crate_path)
                if status == "passed":
                    passed_count += 1
                    progress.update(task, advance=1)
                elif status == "failed":
                    failed_count += 1
                    progress.update(task, advance=1)
                elif status == "error":
                    errored_count += 1
                    progress.update(task, advance=1)
                if status in ("passed", "failed", "error"):
                    progress_console.print(
                        format_crate_line(
                            already_done + index,
                            total,
                            status=status,
                            name=disp,
                            detail=message or "",
                            profiles=profiles,
                            index_width=index_width,
                            name_width=name_width,
                        )
                    )
                # Update the status line at the bottom
                progress.update(
                    task,
                    description=format_batch_progress(
                        passed=passed_count,
                        failed=failed_count,
                        errored=errored_count,
                        remaining=total - passed_count - failed_count - errored_count,
                    ),
                )

            return batch_validate_fn(
                settings=settings,
                rocrate_uris=rocrate_uris,
                state_path=state_path,
                fresh=fresh,
                ephemeral=ephemeral,
                progress_callback=_progress_callback,
                profile_identifiers=profile_identifiers,
                no_auto_profile=no_auto_profile,
            )

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        """Format a byte count as a human-readable string."""
        size = float(num_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < _BYTES_PER_UNIT:
                return f"{size:.1f} {unit}"
            size /= _BYTES_PER_UNIT
        return f"{size:.1f} TB"

    @staticmethod
    def _crate_disk_size(crate_path: str) -> str | None:
        """Return a human-readable disk size for a crate path, or None if unavailable."""
        try:
            p = Path(crate_path)
            if p.is_dir():
                total_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            elif p.is_file():
                total_bytes = p.stat().st_size
            else:
                return None
        except OSError:
            return None
        return BatchValidationCommandView._format_size(total_bytes)

    @staticmethod
    def _summary_source_and_name(crate_path: str, common: str, common_prefix: str) -> tuple[str, str]:
        """
        Split a crate path into a (source, crate-name) pair relative to the
        common prefix of the session paths: the source is the crate's parent
        path below the common root, which identifies its collection in corpora
        organised per source (e.g. ``<root>/<source>/<crate>``). With a flat
        corpus the source is the same for every crate and the summary table
        omits the column altogether.
        """
        if common_prefix and crate_path.startswith(common_prefix):
            rel_parts = Path(crate_path[len(common_prefix) :]).parts
            if len(rel_parts) >= _MIN_REL_PARTS_FOR_SOURCE:
                return str(Path(*rel_parts[:-1])), rel_parts[-1]
            # crate is a direct child of common prefix: use common's last dir as source
            return Path(common).name, (rel_parts[0] if rel_parts else crate_path)
        return Path(crate_path).parent.name, Path(crate_path).name

    def _add_summary_row(
        self,
        table: Table,
        entry: BatchCrateEntry,
        *,
        source: str | None,
        crate_name: str,
    ) -> None:
        """
        Append a single crate's summary row to the batch table from its session
        entry; ``source`` is prepended only when the table shows the column.
        """
        stats = entry.statistics or {}
        size = (
            self._format_size(entry.size_bytes)
            if entry.size_bytes is not None
            else self._crate_disk_size(entry.path) or "—"
        )
        duration = entry.duration
        cells = [
            crate_name,
            ", ".join(entry.profiles or []) or "—",
            size,
            _SUMMARY_STATUS[crate_outcome(entry.status, entry.passed)],
            str(stats.get("total_checks", 0)),
            str(stats.get("total_passed_checks", 0)),
            str(len(entry.issues or [])),
            f"{duration:.2f}s" if duration else "—",
        ]
        if source is not None:
            cells.insert(0, source)
        table.add_row(*cells)

    def show_summary(self, batch_result: BatchValidationResult, verbose: bool = False):
        """
        Show the batch validation summary table and optional per-crate details.

        Both the table and the verbose per-crate details are sourced from the
        persistent session entries, so they stay complete even when this
        invocation only re-validated part of a resumed batch.
        """
        # The four disjoint buckets, not `failed_entries()` (which unites the
        # invalid and the errored on purpose, for the closing verdict).
        counts = crate_counts(batch_result.crates)

        # Compute common prefix once so each crate's parent path below it
        # identifies the collection the crate belongs to (workflowhub, rohub,
        # …) in corpora organised per source, e.g. .../workflowhub/crate.
        all_paths = [entry.path for entry in batch_result.crates]
        try:
            common = str(Path(os.path.commonpath(all_paths)))
            common_prefix = common + os.sep
        except (ValueError, TypeError):
            common = ""
            common_prefix = ""

        sources_and_names = [
            self._summary_source_and_name(entry.path, common, common_prefix) for entry in batch_result.crates
        ]
        # With a flat corpus the source is the same on every row (the scan
        # root): the column would carry no information, so it is omitted.
        show_source = len({source for source, _ in sources_and_names}) > 1

        # Summary table
        table = Table(
            title="Validation Summary",
            title_style="bold",
            show_header=True,
            header_style="bold cyan",
            border_style="blue",
            expand=True,
        )
        if show_source:
            table.add_column("Source", style="dim", no_wrap=True)
        table.add_column("RO-Crate", style="white", no_wrap=True, ratio=1)
        table.add_column("Profile", style="cyan", no_wrap=True)
        table.add_column("Size", justify="right", min_width=9)
        table.add_column("Status", min_width=8, max_width=10)
        table.add_column("Checks", justify="right", min_width=6)
        table.add_column("Passed", justify="right", min_width=6)
        table.add_column("Issues", justify="right", min_width=6)
        table.add_column("Duration", justify="right", min_width=8)

        for entry, (source, crate_name) in zip(batch_result.crates, sources_and_names, strict=True):
            self._add_summary_row(
                table,
                entry,
                source=source if show_source else None,
                crate_name=crate_name,
            )

        self.console.print(Padding(Rule(style="blue"), (0, 0)))
        self.console.print(table)

        # Overall stats
        self.console.print(Padding(f"\n{format_batch_totals(counts)}", (0, 2)))

        # Per-crate details in verbose mode, sourced from the session entries
        # like the summary table: details are available for every failed crate,
        # including those validated by an earlier run of a resumed session.
        failures = batch_result.failed_entries()
        if verbose and failures:
            self.console.print(Padding(Rule(style="dim"), (1, 0)))
            self.console.print(Padding("[bold]Failed crate details:[/bold]", (0, 2)))
            for entry in failures:
                self._show_crate_detail(entry, batch_result.session)
                self.console.print(Padding(Rule(style="dim"), (0, 0)))

    def _show_crate_detail(self, entry: BatchCrateEntry, session: ValidationSession):
        """
        Show the detailed outcome of a failed crate in verbose batch mode.

        Rendered entirely from the persisted session entry (headline statistics
        and serialized issues), so it needs no in-memory validation result. The
        session is what turns the check each issue names back into an object.
        """
        header = f"\n[red]✗ FAILED[/red]: [bold]{entry.path}[/bold]"
        if entry.duration:
            header += f" ({entry.duration:.2f}s)"
        self.console.print(Padding(header, (1, 2)))

        if entry.error:
            # The validation itself errored out (e.g. unreadable crate): there
            # is no check breakdown, only the error message.
            self.console.print(Padding(f"[red]Error:[/red] {entry.error}", (0, 4)))
            return

        stats = entry.statistics or {}
        if stats:
            # Counter colours mirror the statistics tables (total checks in
            # blue, passed in green, failed in red).
            self.console.print(
                Padding(
                    f"Checks executed: [bold blue]{stats.get('total_checks', 0)}[/bold blue] | "
                    f"Passed: [bold green]{stats.get('total_passed_checks', 0)}[/bold green] | "
                    f"Failed: [bold red]{stats.get('total_failed_checks', 0)}[/bold red]",
                    (0, 4),
                )
            )

        # Group the crate's issues by severity, then by failed check.
        issues_by_severity: dict[str, dict[str, list[dict]]] = {}
        for issue in session.inlined_issues(entry.issues):
            severity_name = issue.get("severity") or "REQUIRED"
            check = issue.get("check") or {}
            check_label = f"[bold]{check.get('identifier', '?')}[/bold] - {check.get('name', '')}"
            issues_by_severity.setdefault(severity_name, {}).setdefault(check_label, []).append(issue)

        for severity_name in sorted(issues_by_severity, key=_severity_rank, reverse=True):
            checks = issues_by_severity[severity_name]
            color = get_severity_color(severity_name)
            severity_label = severity_name.capitalize()
            self.console.print(
                Padding(
                    f"\n[bold {color}]╔══ {severity_label} ({len(checks)} failed) ═══[/bold {color}]",
                    (0, 4),
                )
            )
            for check_label, issues in checks.items():
                self.console.print(Padding(f"  {check_label}", (0, 6)))
                for issue in issues:
                    self.console.print(
                        Padding(
                            f"    └─ [{color}]{severity_label}[/{color}] {issue.get('message', '')}",
                            (0, 8),
                        )
                    )
