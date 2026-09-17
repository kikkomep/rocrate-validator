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

"""
RECOMMENDED compatibility check for Schema.org `@id` references.

References to Schema.org terms SHOULD use the `http://schema.org/` namespace
for compatibility with the RO-Crate JSON-LD context. This is a recommendation
only: `@id` identifies a resource, and an HTTPS identifier can be intentional.
The check therefore applies only to nested `@id` references, not to the
identifier of the entity itself.
"""

from collections.abc import Iterator
from typing import Any

from rocrate_validator.errors import ROCrateMetadataNotFoundError
from rocrate_validator.models import CheckResult, CheckResultValue, Severity, ValidationContext
from rocrate_validator.requirements.python import PyFunctionCheck, check, requirement
from rocrate_validator.utils import log as logging

logger = logging.getLogger(__name__)

CONTEXT_PREREQUISITE = ("File Descriptor @context property validation",)
HTTPS_SCHEMA_ORG = "https://schema.org/"
HTTP_SCHEMA_ORG = "http://schema.org/"


def _term_of(iri: str) -> str:
    """Return the Schema.org term denoted by an `https://schema.org/` IRI."""
    return iri[len(HTTPS_SCHEMA_ORG) :]


def _suggestion(iri: str) -> str:
    """Render the http form of an https Schema.org IRI for the issue message."""
    term = _term_of(iri)
    return f"'{term}' (i.e. '{HTTP_SCHEMA_ORG}{term}')"


def _iter_ids(value: Any) -> Iterator[str]:
    """Yield every `@id` value found in a nested JSON-LD value."""
    if isinstance(value, dict):
        raw_id = value.get("@id")
        if isinstance(raw_id, str):
            yield raw_id
        elif isinstance(raw_id, list):
            yield from (item for item in raw_id if isinstance(item, str))
        for nested_value in value.values():
            yield from _iter_ids(nested_value)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_ids(item)


def _https_schema_org_references(entity: dict[str, Any]) -> list[str]:
    """Return distinct HTTPS Schema.org IRIs used by nested `@id` references."""
    seen: dict[str, None] = {}
    for key, value in entity.items():
        if key == "@id":
            continue
        for iri in _iter_ids(value):
            if iri.startswith(HTTPS_SCHEMA_ORG):
                seen.setdefault(iri, None)
    return list(seen)


@requirement(name="Schema.org @id compatibility")
class SchemaOrgIDCompatibilityChecker(PyFunctionCheck):
    """
    Recommends the `http://schema.org/` namespace for nested `@id` references
    to Schema.org terms, without restricting entity identifiers themselves.
    """

    def __entities__(self, context: ValidationContext) -> list[Any] | None:
        """Return metadata entities, or skip when the descriptor is unavailable."""
        try:
            entities = context.ro_crate.metadata.as_dict().get("@graph", [])
        except ROCrateMetadataNotFoundError:
            logger.debug("Skipping Schema.org @id compatibility check: metadata descriptor is not available")
            context.record_skip(self, "metadata descriptor is not available", "exception")
            return None
        return entities if isinstance(entities, list) else []

    @check(
        name="Entity @id references SHOULD use the http Schema.org namespace",
        severity=Severity.RECOMMENDED,
        depends_on=CONTEXT_PREREQUISITE,
    )
    def check_id_compatibility(self, context: ValidationContext) -> CheckResultValue:
        """
        Nested `@id` references to Schema.org terms SHOULD use the HTTP form.
        """
        entities = self.__entities__(context)
        if entities is None:
            return CheckResult.SKIPPED
        result = True
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("@id", "")
            for iri in _https_schema_org_references(entity):
                context.result.add_issue(
                    f"Entity '{entity_id}' references the Schema.org IRI '{iri}' through a nested @id. "
                    f"For compatibility with the RO-Crate @context, the reference SHOULD use "
                    f"{_suggestion(iri)}",
                    self,
                )
                result = False
                if context.fail_fast:
                    return result
        return result
