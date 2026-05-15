from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class ProbeBackendKind(StrEnum):
    FAKE = "fake"
    FFPROBE = "ffprobe"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class AudioProbeFinding:
    code: str
    message: str
    category: str = "diagnostic"
    confidence: float = 1.0
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("code is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class AudioProbeRequest:
    request_id: str
    item_id: str
    relative_path: str
    workspace_root: str
    backend: str = ProbeBackendKind.FAKE.value
    timeout_seconds: int = 30
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.item_id.strip():
            raise ValueError("item_id is required")
        if not self.relative_path.strip():
            raise ValueError("relative_path is required")
        if not self.workspace_root.strip():
            raise ValueError("workspace_root is required")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        self._validate_relative_path()

    def _validate_relative_path(self) -> None:
        from .safety import is_safe_relative_path
        if not is_safe_relative_path(self.relative_path):
            raise ValueError(
                f"relative_path must be a safe relative path: {self.relative_path!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class AudioProbeResult:
    request_id: str
    item_id: str
    relative_path: str
    backend: str
    success: bool = False
    duration_seconds: float | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    codec: str | None = None
    bitrate_bps: int | None = None
    channels: int | None = None
    format_name: str | None = None
    file_size_bytes: int | None = None
    decode_ok: bool = False
    has_audio_stream: bool = False
    stream_count: int = 0
    audio_stream_count: int = 0
    findings: list[AudioProbeFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.item_id.strip():
            raise ValueError("item_id is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class AudioProbePolicy:
    name: str = "default-probe"
    version: str = "1"
    min_duration_seconds: float = 0.1
    max_duration_seconds: float = 7200.0
    min_sample_rate: int = 8000
    max_sample_rate: int = 384000
    min_bit_depth: int = 8
    min_channels: int = 1
    timeout_seconds: int = 30
    require_audio_stream: bool = True
    require_decode: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
