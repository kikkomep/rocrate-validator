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

import logging

from rocrate_validator import models
from tests.ro_crates import InvalidFileDescriptor, ValidROC
from tests.shared import do_entity_test

logger = logging.getLogger(__name__)


#  Global set up the paths
paths = InvalidFileDescriptor()


def test_missing_file_descriptor():
    """Test a RO-Crate without a file descriptor."""
    with paths.missing_file_descriptor as rocrate_path:
        do_entity_test(
            rocrate_path,
            models.Severity.REQUIRED,
            False,
            ["File Descriptor existence"],
            []
        )


def test_not_valid_json_format():
    """Test a RO-Crate with an invalid JSON file descriptor format."""
    do_entity_test(
        paths.invalid_json_format,
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON format"],
        []
    )


def test_not_valid_jsonld_format_missing_context():
    """Test a RO-Crate with an invalid JSON-LD file descriptor format."""
    do_entity_test(
        f"{paths.invalid_jsonld_format}/missing_context",
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        []
    )


def test_not_valid_jsonld_format_not_flattened():
    """Test a RO-Crate with an invalid JSON-LD file descriptor format.
    One or more entities in the file descriptor are not flattened.
    """
    do_entity_test(
        f"{paths.invalid_jsonld_format}/not_flattened",
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ["RO-Crate file descriptor \"ro-crate-metadata.json\" is not fully flattened"]
    )


def test_not_valid_jsonld_format_missing_ids():
    """
    Test a RO-Crate with an invalid JSON-LD file descriptor format.
    One or more entities in the file descriptor do not contain the @id attribute.
    """
    do_entity_test(
        f"{paths.invalid_jsonld_format}/missing_id",
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ["file descriptor does not contain the @id attribute"]
    )


def test_not_valid_jsonld_format_missing_types():
    """
    Test a RO-Crate with an invalid JSON-LD file descriptor format.
    One or more entities in the file descriptor do not contain the @type attribute.
    """
    do_entity_test(
        f"{paths.invalid_jsonld_format}/missing_type",
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ["file descriptor does not contain the @type attribute"]
    )


def test_invalid_jsonld_context():
    """
    Test a RO-Crate with an invalid JSON-LD file descriptor format.
    The file descriptor contains an invalid context.
    """
    do_entity_test(
        f"{paths.invalid_jsonld_format}/invalid_context_uri",
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ["Unable to retrieve the JSON-LD context 'https://w3id.org/ro/terms/invalid/context'"],
        profile_identifier="ro-crate",
        abort_on_first=True
    )


def test_invalid_jsonld_not_compacted():
    """
    Test a RO-Crate with an invalid JSON-LD file descriptor format.
    The file descriptor is not compacted.
    """
    do_entity_test(
        paths.invalid_jsonld_not_compacted,
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ['The 1 occurrence of the "https://schema.org/name" URI cannot be used as a key']
    )


def test_invalid_jsonld_unexpected_key():
    """
    Test a RO-Crate with an invalid JSON-LD file descriptor format.
    The file descriptor contains an unexpected key.
    """
    do_entity_test(
        paths.invalid_jsonld_unexpected_key,
        models.Severity.REQUIRED,
        False,
        ["File Descriptor JSON-LD format"],
        ['The 1 occurrence of the JSON-LD key "hasPartx" is not allowed in the compacted format',
         'The 2 occurrences of the JSON-LD key "namex" are not allowed in the compacted format']
    )


def test_valid_jsonld_custom_term():
    """
    Test a RO-Crate with a valid JSON-LD file descriptor format
    which contains custom terms.
    """
    do_entity_test(
        ValidROC().rocrate_with_custom_terms,
        models.Severity.REQUIRED,
        True,
        [],
        []
    )
