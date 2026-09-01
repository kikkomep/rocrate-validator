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

"""Tests for RO-Crate metadata descriptor suffix matching.

These tests verify that the SPARQL filters correctly identify metadata descriptors
using suffix matching (STRENDS) rather than substring matching (CONTAINS).

The key behavior:
- Standard descriptor `ro-crate-metadata.json` → matches
- `.bak` descriptor `ro-crate-metadata.json.bak` → does NOT match
"""

import logging
from pathlib import Path

from rocrate_validator import models
from tests.shared import do_entity_test

logger = logging.getLogger(__name__)

BASE_PATH = Path(__file__).resolve().parents[3] / "data" / "crates" / "invalid" / "6_descriptor_suffix_matching"


def test_standard_descriptor_is_identified():
    """A standard ro-crate-metadata.json descriptor must be identified."""
    do_entity_test(
        BASE_PATH / "standard_descriptor",
        models.Severity.REQUIRED,
        True,
        profile_identifier="ro-crate-1.1",
    )


def test_bak_descriptor_is_not_identified():
    """A .bak descriptor must NOT be treated as the metadata descriptor.

    With CONTAINS, `ro-crate-metadata.json.bak` would match the filter.
    With STRENDS, it does not end with `ro-crate-metadata.json` and is rejected.

    This test expects the DESIRED behavior (STRENDS). It will fail until the
    CONTAINS→STRENDS conversion is complete.
    """
    do_entity_test(
        BASE_PATH / "bak_descriptor",
        models.Severity.REQUIRED,
        False,
        ["RO-Crate Metadata File Descriptor entity existence"],
        ["The root of the document MUST have an entity with @id `ro-crate-metadata.json`"],
        profile_identifier="ro-crate-1.1",
    )
