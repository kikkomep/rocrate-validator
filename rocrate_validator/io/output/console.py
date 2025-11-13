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

from io import StringIO
from typing import Callable

from rich.console import Console as BaseConsole

import rocrate_validator.log as logging

from . import BaseOutputFormatter, OutputFormatter

logger = logging.getLogger(__name__)


class Console(BaseConsole):
    """Rich console that can be disabled."""

    def __init__(self, *args, disabled: bool = False, interactive: bool = True,
                 formatters: dict[type, OutputFormatter] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled = disabled
        self.interactive = interactive
        self._formatters = {}
        self._formatters_opts: dict[type, BaseOutputFormatter] = {}
        # Register provided formatters if any
        if formatters:
            for type_, formatter in formatters.items():
                self.register_formatter(formatter, type_)

    def register_formatter(self, formatter: OutputFormatter, type_: type | None = None):
        if type_ is None and not isinstance(formatter, BaseOutputFormatter):
            raise ValueError("Type must be provided for non-BaseOutputFormatter formatters.")
        if type_ is None:
            formatter: BaseOutputFormatter = formatter  # type: ignore
            for t, f in formatter._fmap.items():
                self._formatters[t] = f
                self._formatters_opts[t] = formatter
            # inject self console into the formatter
            formatter._console = self
        else:
            self._formatters[type_] = formatter
            # # inject self console into the formatter
            # formatter._console = self

    def print(self, obj, *args, **kwargs):
        if not self.disabled:
            formatter = self._formatters.get(type(obj))
            formatter_opts = self._formatters_opts.get(type(obj))
            if formatter:
                # Try to extract settings from formatter_opts if available
                settings = formatter_opts._settings if formatter_opts else {}
                # Use the formatter to format the object
                if isinstance(formatter, Callable):
                    formatted_output = formatter(obj, console=self, settings=settings)
                else:
                    formatted_output = formatter.format(obj, console=self, settings=settings)
                # Print the formatted output
                super().print(formatted_output, *args, **kwargs)
            else:
                # No formatter found, use default print
                super().print(obj, *args, **kwargs)


class BufferedConsole(Console):
    """ A console that buffers output for later retrieval """

    def __init__(self, formatters: dict[type, BaseOutputFormatter] = None, **kwargs):
        self.output_buffer: StringIO = StringIO()
        super().__init__(file=self.output_buffer, record=True, formatters=formatters, **kwargs)

    def get_buffered_output(self) -> str:
        """ Retrieve the buffered output as a single string """
        return self.output_buffer.getvalue()

    def flush_to_file(self, file_path: str):
        """ Flush the buffered output to a specified file """
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.get_buffered_output())
            self.clear_buffer()

    def clear_buffer(self):
        """ Clear the output buffer """
        self.output_buffer.truncate(0)
        self.output_buffer.seek(0)
