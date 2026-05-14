from __future__ import annotations

from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.search import ProviderHealth, SearchCandidate, SearchKind, SearchProviderResult, SearchQuery


class FakeSearchProvider(SearchProvider):
    """In-memory provider for offline tests and CLI demonstrations."""

    def __init__(
        self,
        candidates: list[SearchCandidate] | None = None,
        *,
        name: str = "fake",
        timeout: bool = False,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        available: bool = True,
        status_message: str | None = None,
    ) -> None:
        self._name = name
        self._candidates = list(candidates or [])
        self._timeout = timeout
        self._warnings = list(warnings or [])
        self._errors = list(errors or [])
        self._available = available
        self._status_message = status_message

    @property
    def name(self) -> str:
        return self._name

    def search(self, query: SearchQuery) -> SearchProviderResult:
        warnings = list(self._warnings)
        if self._timeout:
            warnings.append("fake provider timeout reached")
        if self._errors:
            return SearchProviderResult(
                provider=self.name,
                query=query,
                warnings=warnings,
                errors=list(self._errors),
                timeout_reached=self._timeout,
                response_count=0,
            )

        matches = [candidate for candidate in self._candidates if self._matches(query, candidate)]
        ordered = sorted(matches, key=lambda candidate: (-(candidate.raw_score or 0), candidate.candidate_id))
        limited = ordered[: query.limit] if query.limit is not None else ordered
        return SearchProviderResult(
            provider=self.name,
            query=query,
            candidates=limited,
            warnings=warnings,
            timeout_reached=self._timeout,
            response_count=len(matches),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            available=self._available and not self._errors,
            status_message=self._status_message,
            warnings=list(self._warnings),
            errors=list(self._errors),
            metadata={"candidate_count": len(self._candidates)},
        )

    def _matches(self, query: SearchQuery, candidate: SearchCandidate) -> bool:
        if not _same_text(query.artist, candidate.artist):
            return False
        if query.kind == SearchKind.TRACK:
            return _same_text(query.title, candidate.title)
        return _same_text(query.album, candidate.album)


def _same_text(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    return expected.strip().casefold() == actual.strip().casefold()
