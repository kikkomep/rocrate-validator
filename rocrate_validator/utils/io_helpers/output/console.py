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

from typing import Any

from rich.console import Console as BaseConsole

from rocrate_validator.utils import log as logging

from . import BaseOutputFormatter, OutputFormatter

logger = logging.getLogger(__name__)


class Console(BaseConsole):
    """Rich console that can be disabled."""

    def __init__(
        self,
        *args,
        disabled: bool = False,
        interactive: bool = True,
        formatters: dict[type, Any] | None = None,
        **kwargs,
    ):
        force_jupyter = kwargs.pop("force_jupyter", None)
        if force_jupyter is None:
            force_jupyter = False if self.__jupyter_environment__() else None
        super().__init__(*args, force_jupyter=force_jupyter, **kwargs)
        self.disabled = disabled
        self.interactive = interactive
        self._notices: Console | None = None
        self._formatters: dict[type, Any] = {}
        self._formatters_opts: dict[type, BaseOutputFormatter] = {}
        # Register provided formatters if any
        if formatters:
            for type_, formatter in formatters.items():
                self.register_formatter(formatter, type_)

    @property
    def notices(self) -> "Console":
        """
        The twin of this console on stderr, for everything that is not the document.

        Warnings, progress, headers and verdicts are what the tool has to *say*
        about a run; the standard output carries what was asked for — a report,
        a listing. Keeping the two apart is what lets ``-f json`` be piped
        straight into a parser whatever the run had to report along the way.

        The twin mirrors this console's colour and whether it is disabled at
        all, is built once, and is its own ``notices``, so passing it around
        cannot spawn a chain of consoles. It is declared with ``stderr=True``
        rather than bound to ``sys.stderr``: Rich then resolves the stream at
        each write, so a caller redirecting it afterwards — a test harness, an
        embedding application — is honoured.

        Its **width is its own**, taken from stderr: the two streams can go to
        different places, and a report narrowed with ``--output-line-width``
        must not shrink the progress bar in the terminal watching it.
        """
        if self.stderr:
            return self
        if self._notices is None:
            self._notices = Console(
                stderr=True,
                no_color=self.no_color,
                disabled=self.disabled,
                interactive=self.interactive,
            )
        return self._notices

    def apply_report_width(self, width: int | None) -> None:
        """
        Render the document ``width`` columns wide, unless a terminal decides.

        ``--output-line-width`` exists because a report leaving the screen — a
        file, or a redirected stdout — has no terminal to take its width from,
        and would otherwise fall back to a default 80 columns. When there *is* a
        terminal, its size wins: a report shown in a window should fit it.
        """
        if width and not self.is_terminal:
            self.width = width

    def __jupyter_environment__(self) -> bool:
        from rocrate_validator.cli.utils import running_in_jupyter  # noqa: PLC0415

        return running_in_jupyter()

    def register_formatter(self, formatter: OutputFormatter, type_: type | None = None):
        if type_ is None and not isinstance(formatter, BaseOutputFormatter):
            raise ValueError("type_ must be provided if formatter is not a BaseOutputFormatter")
        if isinstance(formatter, BaseOutputFormatter):
            for t, f in formatter.get_type_formatters().items():
                self._formatters[t] = f
        else:
            assert type_ is not None  # guaranteed by the check above
            self._formatters[type_] = formatter

    def __format_data__(self, obj):
        formatter = self._formatters.get(type(obj))
        if formatter:
            return formatter(obj)
        return obj

    def print(self, *objects, **kwargs):
        if not self.disabled:
            formatted = tuple(self.__format_data__(o) for o in objects)
            super().print(*formatted, **kwargs)
