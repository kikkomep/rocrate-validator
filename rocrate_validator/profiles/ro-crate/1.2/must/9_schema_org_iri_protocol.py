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

# NOTE: This check is deliberately kept separate from the RECOMMENDED type
# check in `should/0_entity_metadata.ttl`, which translates the specification
# sentence "The @type SHOULD include at least one Schema.org type" one-to-one.
# The two checks express different requirements: the former checks for the
# presence of a Schema.org type, while this one enforces the protocol used by
# Schema.org `@type` values. `@id` values are intentionally not covered by this
# MUST check: they identify resources and may legitimately use the HTTPS form.
#
# What was missing is the *other* requirement.  The RO-Crate @context is
# mandatory and maps every Schema.org term to an `http://schema.org/` IRI, so
# in RDF terms `https://schema.org/Dataset` is simply a different IRI from
# `http://schema.org/Dataset` and none of the profile's MUST shapes — all
# anchored on the http prefix — can see it.  The context and compaction checks
# do not catch this (`must/0_file_descriptor_format.py` excludes `@type` from
# `check_compaction` via SKIP_KEYS); the generic Schema.org type check now
# rejects https as well, but does not provide the dedicated protocol diagnostic.
#
# This check closes that gap explicitly: it reports the https IRIs where they
# are written, rather than letting the crate fail somewhere else for reasons
# that do not name the real cause.
#
# The protocol requirement is treated as MUST because the RO-Crate context
# defines Schema.org terms in the `http://schema.org/` namespace.

"""
MUST check on the protocol of Schema.org `@type` values:
  - `@type` values MUST NOT use the `https://schema.org/` namespace
"""

from collections.abc import Iterator
from typing import Any

from rocrate_validator.errors import ROCrateMetadataNotFoundError
from rocrate_validator.models import CheckResult, CheckResultValue, Severity, ValidationContext
from rocrate_validator.requirements.python import PyFunctionCheck, check, requirement
from rocrate_validator.utils import log as logging

logger = logging.getLogger(__name__)

# The check reads the parsed file descriptor and then reasons about what the
# RO-Crate @context maps: without a validated @context the whole message ("the
# context maps Schema.org terms to http://schema.org/") would be unfounded, so
# the @context check is a genuine prerequisite rather than a mere ordering hint.
# It already depends on "File Descriptor JSON format", which is what makes
# `as_dict()` readable, so that prerequisite is inherited transitively.
CONTEXT_PREREQUISITE = ("File Descriptor @context property validation",)

# The namespace the RO-Crate @context does *not* map, and its http counterpart.
HTTPS_SCHEMA_ORG = "https://schema.org/"
HTTP_SCHEMA_ORG = "http://schema.org/"


def _term_of(iri: str) -> str:
    """Return the Schema.org term denoted by an `https://schema.org/` IRI."""
    return iri[len(HTTPS_SCHEMA_ORG) :]


def _suggestion(iri: str) -> str:
    """Render the http form of an https Schema.org IRI, for the issue message."""
    term = _term_of(iri)
    return f"'{term}' (i.e. '{HTTP_SCHEMA_ORG}{term}')"


def _iter_values(value: Any, key: str) -> Iterator[str]:
    """
    Yield every string reachable under `key` in a JSON-LD value.

    Entities are flattened in an RO-Crate, but nested objects and arrays are
    still legal JSON-LD, so the walk is recursive for the same reason
    `check_compaction` walks entity keys recursively.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key:
                if isinstance(v, str):
                    yield v
                elif isinstance(v, list):
                    yield from (item for item in v if isinstance(item, str))
            else:
                yield from _iter_values(v, key)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values(item, key)


def _https_schema_org_types(entity: Any) -> list[str]:
    """Return the distinct https Schema.org IRIs found in `@type`, in order."""
    seen: dict[str, None] = {}
    for value in _iter_values(entity, "@type"):
        if value.startswith(HTTPS_SCHEMA_ORG):
            seen.setdefault(value, None)
    return list(seen)


@requirement(name="Schema.org @type protocol")
class SchemaOrgIRIProtocolChecker(PyFunctionCheck):
    """
    Checks that Schema.org `@type` values are written with the
    `http://schema.org/` namespace the RO-Crate @context defines, rather than
    the `https://` namespace shown by the schema.org website.
    """

    def __entities__(self, context: ValidationContext, what: str) -> list[Any] | None:
        """
        Return the `@graph` entities, or ``None`` when the descriptor is not
        available, so the caller reports the check as skipped rather than
        passed: there is nothing to look at, which is not the same as clean.

        The reason is recorded on the context before returning, so the skip is
        reported with its cause instead of appearing as an unexplained gap.
        """
        try:
            entities = context.ro_crate.metadata.as_dict().get("@graph", [])
        except ROCrateMetadataNotFoundError:
            logger.debug("Skipping %s check: metadata descriptor is not available", what)
            context.record_skip(self, "metadata descriptor is not available", "exception")
            return None
        return entities if isinstance(entities, list) else []

    @check(
        name="Entity @type MUST use the http Schema.org namespace",
        severity=Severity.REQUIRED,
        depends_on=CONTEXT_PREREQUISITE,
    )
    def check_type_protocol(self, context: ValidationContext) -> CheckResultValue:
        """
        `@type` values MUST NOT be `https://schema.org/` IRIs: the RO-Crate
        @context maps Schema.org terms to `http://schema.org/`, so an https
        IRI denotes a different class that no profile shape describes.
        """
        entities = self.__entities__(context, "Schema.org @type protocol")
        if entities is None:
            return CheckResult.SKIPPED
        result = True
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("@id", "")
            for iri in _https_schema_org_types(entity):
                context.result.add_issue(
                    f"Entity '{entity_id}' declares the @type '{iri}', which is not a term of "
                    f"the RO-Crate @context: the context maps Schema.org terms to "
                    f"'{HTTP_SCHEMA_ORG}', so the entity MUST be typed {_suggestion(iri)}",
                    self,
                )
                result = False
                if context.fail_fast:
                    return result
        return result
