import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class RadarrConfig:
    url: str
    api_key: str
    ptbrmerger_profile_name: str
    ptbrmerger_root_folder: str
    ptbrmerger_tag_name: str
    ptbrmerger_min_score: int = 10000
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

@dataclass
class ProcessingConfig:
    queue_file: str = "queue.json"
    max_attempts: int = 3
    preserve_failed_artifacts: bool = True

@dataclass
class DiagnosticsConfig:
    enable_runtime_heuristics: bool = True
    enable_offset_diagnostics: bool = True
    offset_suspected_threshold_seconds: int = 180

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
    diagnostics: DiagnosticsConfig

_config_instance: Optional[AppConfig] = None

def load_config(config_path: Path) -> AppConfig:
    """
    Lê o arquivo YAML de forma segura e o converte estritamente
    para o objeto AppConfig baseado em DataClasses.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path.absolute()}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return AppConfig(
        radarr=RadarrConfig(**data.get("radarr", {})),
        qbittorrent=QBittorrentConfig(**data.get("qbittorrent", {})),
        ffmpeg=FFMpegConfig(**data.get("ffmpeg", {})),
        sync=SyncConfig(**data.get("sync", {})),
        notifications=NotificationsConfig(**data.get("notifications", {})),
        logging=LoggingConfig(**data.get("logging", {})),
        ptbr_keywords=PtbrKeywordsConfig(**data.get("ptbr_keywords", {})),
        processing=ProcessingConfig(**data.get("processing", {})),
        diagnostics=DiagnosticsConfig(**data.get("diagnostics", {})),
    )

def get_config() -> AppConfig:
    """
    Garante o carregamento lazy e em Singleton das configurações de App.
    Permitindo acesso em qualquer lugar do script sem multiplos reads IO.
    """
    global _config_instance
    if _config_instance is None:
        # Resolve 'root_dir' sendo a pasta acima de 'src/'
        root_dir = Path(__file__).resolve().parent.parent
        config_file = root_dir / "config.yml"
        _config_instance = load_config(config_file)
    return _config_instance
