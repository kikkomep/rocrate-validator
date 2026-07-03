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

from __future__ import annotations

from typing import TYPE_CHECKING

from rocrate_validator.models._logging import logger
from rocrate_validator.models.severity import Severity

if TYPE_CHECKING:
    from pathlib import Path

    from rocrate_validator.models.profile import Profile


class ValidationCache:
    """
    In-memory cache of the expensive, reusable artifacts of a validation:
    the loaded profiles with their lazily-parsed SHACL shape registries.

    Sharing one instance across ``validate()`` calls (explicitly via the
    ``cache`` parameter, or implicitly through ``batch_validate``) avoids
    re-parsing the profile specifications and shapes graphs for every crate.
    Without a shared instance each validation uses a throwaway cache, which
    reproduces the previous (uncached) behaviour.

    Entries are keyed by everything that affects the loaded profiles,
    including ``publicID``: some profiles (e.g. workflow-ro-crate) declare
    relative ``sh:targetNode`` IRIs that resolve against the crate base URI,
    so the parsed shapes are genuinely crate-dependent for them.

    The cache holds parsed ``rdflib`` graphs and is intentionally not
    serializable: its lifetime is bound to the owning object (a batch run, a
    session, an interactive process). Instances are not thread-safe; share
    one per thread, or synchronize externally.
    """

    def __init__(self):
        self._profiles: dict[tuple, list[Profile]] = {}
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def __profiles_key__(
        profiles_path: str | Path,
        extra_profiles_path: str | Path | None,
        publicID: str | None,
        severity: Severity,
        allow_requirement_check_override: bool,
    ) -> tuple:
        return (
            str(profiles_path),
            str(extra_profiles_path) if extra_profiles_path else None,
            publicID,
            severity.name,
            bool(allow_requirement_check_override),
        )

    def get_or_load_profiles(
        self,
        profiles_path: str | Path,
        extra_profiles_path: str | Path | None = None,
        publicID: str | None = None,
        severity: Severity | None = None,
        allow_requirement_check_override: bool = True,
    ) -> list[Profile]:
        """
        Return the profiles loaded with the given parameters, reusing a
        previously loaded (and parsed) set when available.

        Mirrors the signature of :meth:`Profile.load_profiles`, which is
        invoked on a cache miss. The returned list is a copy; the cached
        ``Profile`` objects themselves are shared, which is safe because
        they are read-only during validation (see ``performance-improvements.md``).
        """
        severity = severity if severity is not None else Severity.REQUIRED
        key = self.__profiles_key__(
            profiles_path, extra_profiles_path, publicID, severity, allow_requirement_check_override
        )
        cached = self._profiles.get(key)
        if cached is not None:
            self._hits += 1
            logger.debug("ValidationCache hit for profiles key: %s", key)
            return list(cached)
        self._misses += 1
        from rocrate_validator.models.profile import Profile  # noqa: PLC0415 - avoid circular import

        profiles = Profile.load_profiles(
            profiles_path,
            extra_profiles_path=extra_profiles_path,
            publicID=publicID,
            severity=severity,
            allow_requirement_check_override=allow_requirement_check_override,
        )
        self._profiles[key] = list(profiles)
        return list(profiles)

    def clear(self) -> None:
        """Drop all cached entries."""
        self._profiles.clear()

    @property
    def info(self) -> dict:
        """Cache effectiveness counters (useful for tests and benchmarks)."""
        return {"entries": len(self._profiles), "hits": self._hits, "misses": self._misses}
