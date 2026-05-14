from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean


SafeMetadata = dict[str, Any]


class SearchKind(StrEnum):
    TRACK = "track"
    ALBUM = "album"


@dataclass(slots=True, frozen=True)
class SearchQuery:
    kind: SearchKind
    artist: str
    title: str | None = None
    album: str | None = None
    extra_terms: list[str] = field(default_factory=list)
    limit: int | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SearchKind(self.kind))
        if not self.artist.strip():
            raise ValueError("artist is required")
        if self.kind == SearchKind.TRACK and not (self.title and self.title.strip()):
            raise ValueError("title is required for track search")
        if self.kind == SearchKind.ALBUM and not (self.album and self.album.strip()):
            raise ValueError("album is required for album search")
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CandidateFile:
    filename: str
    size_bytes: int | None = None
    declared_bitrate: int | None = None
    extension: str | None = None
    duration_seconds: int | None = None
    locked: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("filename is required")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SearchCandidate:
    candidate_id: str
    provider: str
    files: list[CandidateFile]
    username: str | None = None
    directory: str | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    raw_score: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SearchProviderResult:
    provider: str
    query: SearchQuery
    candidates: list[SearchCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timeout_reached: bool = False
    response_count: int = 0
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        if self.response_count < 0:
            raise ValueError("response_count cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ProviderHealth:
    provider: str
    available: bool
    status_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class DownloadRequest:
    provider: str
    candidate_id: str
    files: list[CandidateFile] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class TransferStatus:
    provider: str
    transfer_id: str
    state: str
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class DownloadArtifact:
    provider: str
    candidate_id: str
    artifact_id: str
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
