from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    READY_FOR_REVIEW = "ready_for_review"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    NEEDS_ACTION = "needs_action"


@dataclass(frozen=True)
class LanguageProfile:
    id: str
    label: str
    preferred_audio_language: str
    accept_dual_audio: bool
    keep_original_audio: bool
    priority: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_language_profile() -> LanguageProfile:
    return LanguageProfile(
        id="pt-BR-default",
        label="Portugues Brasil",
        preferred_audio_language="pt-BR",
        accept_dual_audio=True,
        keep_original_audio=True,
        priority="dubbed-first",
    )


@dataclass(frozen=True)
class SyncReview:
    status: str
    confidence: float
    suggested_offset_seconds: float | None
    suggested_trim_start_seconds: float
    suggested_trim_end_seconds: float
    reason: str
    duration_diff_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperationPlan:
    id: str
    workflow_id: str
    target_path: str
    source_path: str
    output_path: str
    language_profile_id: str
    ptbr_stream_index: int
    sync_review: SyncReview
    manual_offset_seconds: float | None = None
    manual_trim_start_seconds: float = 0.0
    manual_trim_end_seconds: float = 0.0
    will_replace_original: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sync_review"] = self.sync_review.to_dict()
        return payload


@dataclass(frozen=True)
class WorkflowJob:
    id: str
    workflow_id: str
    status: JobStatus
    target_name: str
    source_name: str
    recipe_id: str | None
    created_at: str
    updated_at: str
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class Recipe:
    id: str
    job_id: str
    workflow_id: str
    label: str
    target_name: str
    source_name: str
    output_name: str
    language_profile_id: str
    sync_summary: str
    validation_status: str
    report_path: str
    output_path: str
    created_at: str
    contains_absolute_paths: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
