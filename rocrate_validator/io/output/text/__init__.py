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

import rocrate_validator.log as logging
from rocrate_validator.models import ValidationResult, ValidationStatistics

from .. import BaseOutputFormatter
from .formatters import format_validation_result, format_validation_statistics

# set up logging
logger = logging.getLogger(__name__)


class TextOutputFormatter(BaseOutputFormatter):

    def __init__(self):
        super().__init__()
        self.add_type_formatter(ValidationResult, format_validation_result)
        self.add_type_formatter(ValidationStatistics, format_validation_statistics)
