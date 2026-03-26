import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class RadarrConfig:
    url: str
    api_key: str
    ptbrmerger_profile_name: str
    ptbrmerger_root_folder: str
    ptbrmerger_tag_name: str
    ptbrmerger_min_score: int = 10000
    ptbrmerger_max_candidates: int = 10
    timeout: int = 10
    success_tag_label: str = "ptbr-merged"


@dataclass
class QBittorrentConfig:
    url: str
    username: str
    password: str


@dataclass
class FFMpegConfig:
    ffmpeg_path: str
    ffprobe_path: str


@dataclass
class SyncConfig:
    max_duration_diff_seconds: int


@dataclass
class NotificationsConfig:
    discord_webhook_url: str
    username: str = "PTBRMerger Bot"


@dataclass
class LoggingConfig:
    level: str
    file: str
    history_file: str = "history.json"
    history_max_entries: int = 500
    group_history_file: str = "group_history.json"
    group_history_max_entries: int = 1000


@dataclass
class ProcessingConfig:
    queue_file: str = "queue.json"
    max_attempts: int = 3
    preserve_failed_artifacts: bool = True

@dataclass
class RetryConfig:
    queue_file: str = "retry_queue.json"
    enabled: bool = True
    delay_hours: list[int] = field(default_factory=lambda: [1, 6, 24])
    max_attempts: int = 3


@dataclass
class BazarrConfig:
    url: str = ""
    api_key: str = ""
    language: str = "pt-BR"
@dataclass
class DiagnosticsConfig:
    enable_runtime_heuristics: bool = True
    enable_offset_diagnostics: bool = True
    offset_suspected_threshold_seconds: int = 180
    recoverable_edge_diff_seconds: int = 180
    ambiguous_recoverable_diff_seconds: int = 240
    enable_auto_offset: bool = False
    auto_offset_max_seconds: int = 90
    auto_offset_min_confidence: float = 0.85


@dataclass
class ScoringConfig:
    history_bonus_success: int = 8
    history_penalty_cut_mismatch: int = 18
    history_penalty_runtime_incompatible: int = 14
    history_min_group_samples: int = 2
    history_min_source_samples: int = 2


@dataclass
class FingerprintConfig:
    enabled: bool = False
    sample_rate: int = 2000
    window_seconds: int = 12
    max_offset_seconds: int = 90
    min_confidence: float = 0.7
    consistency_tolerance_seconds: float = 0.75
    positions: list[str] = field(default_factory=lambda: ["head", "mid", "tail"])
    allow_borderline_cut_retry: bool = False


@dataclass
class RecoveryConfig:
    enabled: bool = True
    allow_ambiguous: bool = False
    ambiguous_min_confidence: float = 0.6
    max_offset_seconds: int = 90
    min_trim_seconds: float = 3.0
    max_trim_seconds: float = 180.0
    post_validation_max_diff_seconds: float = 3.0
    trim_tolerance_seconds: float = 1.5


@dataclass
class PtbrKeywordsConfig:
    high_priority: list[str]
    medium_priority: list[str]
    indexer_names_br: list[str]
    blacklist: list[str]


@dataclass
class AppConfig:
    radarr: RadarrConfig
    qbittorrent: QBittorrentConfig
    ffmpeg: FFMpegConfig
    sync: SyncConfig
    notifications: NotificationsConfig
    logging: LoggingConfig
    ptbr_keywords: PtbrKeywordsConfig
    processing: ProcessingConfig
    retry: RetryConfig
    bazarr: BazarrConfig
    diagnostics: DiagnosticsConfig
    scoring: ScoringConfig
    fingerprint: FingerprintConfig
    recovery: RecoveryConfig


_config_instance: Optional[AppConfig] = None

ENV_OVERRIDES: dict[tuple[str, str], str] = {
    ("radarr", "url"): "RADARR_URL",
    ("radarr", "api_key"): "RADARR_API_KEY",
    ("qbittorrent", "url"): "QBITTORRENT_URL",
    ("qbittorrent", "username"): "QBITTORRENT_USERNAME",
    ("qbittorrent", "password"): "QBITTORRENT_PASSWORD",
    ("notifications", "discord_webhook_url"): "DISCORD_WEBHOOK_URL",
}


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    for (section, key), env_name in ENV_OVERRIDES.items():
        value = os.getenv(env_name)
        if value is None or value == "":
            continue
        data.setdefault(section, {})
        data[section][key] = value
    return data


def _resolve_config_path(root_dir: Path) -> Path:
    explicit_path = os.getenv("PTBRMERGER_CONFIG")
    if explicit_path:
        return Path(explicit_path).expanduser()

    config_file = root_dir / "config.yml"
    if config_file.exists():
        return config_file

    example_file = root_dir / "config.example.yml"
    if example_file.exists():
        return example_file

    return config_file


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuracao nao encontrado: {config_path.absolute()}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data = _apply_env_overrides(data)

    return AppConfig(
        radarr=RadarrConfig(**data.get("radarr", {})),
        qbittorrent=QBittorrentConfig(**data.get("qbittorrent", {})),
        ffmpeg=FFMpegConfig(**data.get("ffmpeg", {})),
        sync=SyncConfig(**data.get("sync", {})),
        notifications=NotificationsConfig(**data.get("notifications", {})),
        logging=LoggingConfig(**data.get("logging", {})),
        ptbr_keywords=PtbrKeywordsConfig(**data.get("ptbr_keywords", {})),
        processing=ProcessingConfig(**data.get("processing", {})),
        retry=RetryConfig(**data.get("retry", {})),
        bazarr=BazarrConfig(**data.get("bazarr", {})),
        diagnostics=DiagnosticsConfig(**data.get("diagnostics", {})),
        scoring=ScoringConfig(**data.get("scoring", {})),
        fingerprint=FingerprintConfig(**data.get("fingerprint", {})),
        recovery=RecoveryConfig(**data.get("recovery", {})),
    )


def get_config() -> AppConfig:
    global _config_instance
    if _config_instance is None:
        root_dir = Path(__file__).resolve().parent.parent
        config_file = _resolve_config_path(root_dir)
        _config_instance = load_config(config_file)
    return _config_instance
