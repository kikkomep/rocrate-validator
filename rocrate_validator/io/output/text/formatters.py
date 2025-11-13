# Copyright (c) 2024-2025 CRS4
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

from typing import Optional

from rich.align import Align
from rich.markdown import Markdown
from rich.padding import Padding

import rocrate_validator.log as logging
from rocrate_validator.colors import get_severity_color
from rocrate_validator.io.output.text.layout.report import \
    ValidationReportLayout
from rocrate_validator.models import (ValidationResult, ValidationSettings,
                                      ValidationStatistics)

from .. import OutputFormatter
from ..console import BufferedConsole, Console

# set up logging
logger = logging.getLogger(__name__)


def format_validation_result(data: ValidationResult,
                             console: Console = None,
                             settings: Optional[ValidationSettings] = None) -> str:
    """
    Format the validation result

    Args:
        result: The validation result to format
        console: Optional console instance. If None, a new BufferedConsole is created.

    Returns:
        The formatted output as string
    """
    result = data
    assert result is not None, "Validation result must be provided"

    # Settings can be used in the future for customization
    _ = settings

    # Use provided console or create a new BufferedConsole
    console = console or BufferedConsole()

    logger.debug("Validation failed: %s", result.failed_requirements)

    # Print validation details
    # Print the list of failed requirements
    console.print(
        Padding("\n[bold]The following requirements have not meet: [/bold]", (0, 2)), style="white")
    for requirement in sorted(result.failed_requirements, key=lambda x: x.identifier):
        console.print(
            Align(f"\n[profile: [magenta bold]{requirement.profile.name}[/magenta bold]]", align="right")
        )
        console.print(
            Padding(
                f"[bold][cyan][u][ {requirement.identifier} ]: "
                f"{Markdown(requirement.name).markup}[/u][/cyan][/bold]", (0, 5)), style="white")
        console.print(Padding(Markdown(requirement.description), (1, 6)))
        console.print(Padding("[white bold u]  Failed checks  [/white bold u]\n",
                              (0, 8)), style="white bold")

        for check in sorted(result.get_failed_checks_by_requirement(requirement),
                            key=lambda x: (-x.severity.value, x)):
            issue_color = get_severity_color(check.level.severity)
            console.print(
                Padding(
                    f"[bold][{issue_color}][ {check.identifier.center(16)} ][/{issue_color}]  "
                    f"[magenta]{check.name}[/magenta][/bold]:", (0, 7)),
                style="white bold")
            console.print(Padding(Markdown(check.description), (0, 0, 0, len(check.identifier) + 13)))
            console.print(Padding("[u] Detected issues [/u]", (0, 8)), style="white bold")
            for issue in sorted(result.get_issues_by_check(check),
                                key=lambda x: (-x.severity.value, x)):
                path = ""
                if issue.violatingProperty and issue.violatingPropertyValue:
                    path = f" of [yellow]{issue.violatingProperty}[/yellow]"
                if issue.violatingPropertyValue:
                    if issue.violatingProperty:
                        path += "="
                    path += f"\"[green]{issue.violatingPropertyValue}[/green]\" "  # keep the ending space
                if issue.violatingEntity:
                    path = f"{path} on [cyan]<{issue.violatingEntity}>[/cyan]"
                console.print(
                    Padding(f"- [[red]Violation[/red]{path}]: "
                            f"{Markdown(issue.message).markup}", (0, 9)))
            console.print("\n", style="white")
    # Retrieve buffered output if using BufferedConsole
    if hasattr(console, "get_buffered_output"):
        return console.get_buffered_output()
    return ""


class ValidationResultTextOutputFormatter(OutputFormatter):

    def format(self, data: ValidationResult,
               console: Console = None, settings: Optional[ValidationSettings] = None) -> str:
        return format_validation_result(data, console=console, settings=settings or self._settings)


def format_validation_statistics(data: ValidationStatistics,
                                 console: Console = None, settings: Optional[ValidationSettings] = None) -> str:
    """
    Format the validation result statistics

    Args:
        data: The validation result to format
        console: Optional console instance. If None, a new BufferedConsole is created.

    Returns:
        The formatted output as string
    """
    result = data
    assert result is not None, "Validation result must be provided"

    # Settings can be used in the future for customization
    _ = settings

    # Use provided console or create a new BufferedConsole
    console = console or BufferedConsole()

    # Print validation statistics
    layout = ValidationReportLayout(console=console, settings=data.validation_settings, statistics=data)
    console.print(layout.layout)
    console.print("\n", style="white")
    # Retrieve buffered output if using BufferedConsole
    if hasattr(console, "get_buffered_output"):
        return console.get_buffered_output()
    return ""


class ValidationStatisticsTextOutputFormatter(OutputFormatter):

    def format(self, data: ValidationStatistics,
               console: Console = None, settings: Optional[ValidationSettings] = None) -> str:
        return format_validation_statistics(data, console=console or self._console, settings=settings or self._settings)
