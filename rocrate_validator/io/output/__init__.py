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


from typing import Any, Optional, Protocol

from rich.console import Console

import rocrate_validator.log as logging

# set up logging
logger = logging.getLogger(__name__)


class OutputFormatter(Protocol):
    def format(self, data: Any, console: Console = None, settings: dict = None) -> str:
        pass


class CallableOutputFormatter(Protocol):
    """Protocol for callable formatters."""

    def __call__(self, data: Any, console: Console = None, settings: dict = None) -> str:
        pass


class BaseOutputFormatter(OutputFormatter):

    def __init__(self, console: Optional[Console] = None, settings: dict = None):
        self._console = console
        self._settings = settings or {}
        self._fmap = {}

    def add_type_formatter(self, data_type: type, formatter: OutputFormatter | CallableOutputFormatter):
        """Register a formatter for a specific data type."""
        self._fmap[data_type] = formatter

    def get_type_formatter(self, data_type: type) -> OutputFormatter | CallableOutputFormatter:
        """Retrieve the formatter for a specific data type."""
        formatter = self._fmap.get(data_type)
        if not formatter:
            raise NotImplementedError(f"No formatter registered for type: {data_type.__name__}")
        return formatter

    def get_data_formatter(self, data: Any) -> OutputFormatter | CallableOutputFormatter:
        """Retrieve the formatter for a specific data type."""
        data_type = type(data)
        formatter = self._fmap.get(data_type)
        if not formatter:
            raise NotImplementedError(f"No formatter registered for type: {data_type.__name__}")
        return formatter

    def get_type_formatters(self) -> dict[type, CallableOutputFormatter]:
        """Retrieve all registered formatters."""
        return dict(self._fmap)

    def format(self, data: Any, console: Console = None, settings: dict = None) -> str:
        """Format the given data using the appropriate formatter."""
        settings = settings or self._settings
        formatter = self.get_data_formatter(data)
        if console:
            self._console = console
        if hasattr(formatter, 'format'):
            return formatter.format(data, console=self._console, settings=settings)
        else:
            return formatter(data, console=self._console, settings=settings)
