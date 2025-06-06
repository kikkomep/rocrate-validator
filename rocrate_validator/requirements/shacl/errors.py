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

from rocrate_validator.errors import ValidationError
from rocrate_validator.requirements.shacl.validator import \
    SHACLValidationResult


class SHACLValidationError(ValidationError):

    def __init__(
        self,
        result: SHACLValidationResult = None,
        message: str = "Document does not conform to SHACL shapes.",
        path: str = ".",
        code: int = 500,
    ):
        super().__init__(message, path, code)
        self._result = result

    @property
    def result(self) -> SHACLValidationResult:
        return self._result

    def __repr__(self):
        return (
            f"SHACLValidationError({self._message!r}, {self._path!r}, {self.result!r})"
        )
