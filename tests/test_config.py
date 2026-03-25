import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.config as config_module


def test_load_config_applies_environment_overrides(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
radarr:
  url: http://yaml-radarr:7878
  api_key: yaml-key
  ptbrmerger_profile_name: PTBRMerger
  ptbrmerger_root_folder: D:\\temp\\ptbrmerger
  ptbrmerger_tag_name: ptbrmerger

qbittorrent:
  url: http://yaml-qbit:8080
  username: yaml-user
  password: yaml-pass

ffmpeg:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe

sync:
  max_duration_diff_seconds: 30

notifications:
  discord_webhook_url: ""

logging:
  level: INFO
  file: ptbrmerger.log

ptbr_keywords:
  high_priority: ["pt-br"]
  medium_priority: ["dual"]
  indexer_names_br: ["Tracker BR"]
  blacklist: ["CAM"]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("RADARR_API_KEY", "env-radarr-key")
    monkeypatch.setenv("QBITTORRENT_PASSWORD", "env-qbit-pass")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")

    config = config_module.load_config(config_file)

    assert config.radarr.api_key == "env-radarr-key"
    assert config.qbittorrent.password == "env-qbit-pass"
    assert config.notifications.discord_webhook_url == "https://discord.example/webhook"
    assert config.qbittorrent.username == "yaml-user"


def test_get_config_falls_back_to_example_file(tmp_path: Path, monkeypatch):
    example_file = tmp_path / "config.example.yml"
    example_file.write_text(
        """
radarr:
  url: http://localhost:7878
  api_key: example-key
  ptbrmerger_profile_name: PTBRMerger
  ptbrmerger_root_folder: D:\\temp\\ptbrmerger
  ptbrmerger_tag_name: ptbrmerger

qbittorrent:
  url: http://localhost:8080
  username: example-user
  password: example-pass

ffmpeg:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe

sync:
  max_duration_diff_seconds: 30

notifications:
  discord_webhook_url: ""

logging:
  level: INFO
  file: ptbrmerger.log

ptbr_keywords:
  high_priority: ["pt-br"]
  medium_priority: ["dual"]
  indexer_names_br: ["Tracker BR"]
  blacklist: ["CAM"]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "_config_instance", None)
    monkeypatch.setattr(config_module.Path, "resolve", lambda self: tmp_path / "src" / "config.py")
    monkeypatch.delenv("PTBRMERGER_CONFIG", raising=False)

    config = config_module.get_config()

    assert config.radarr.api_key == "example-key"
    assert config.qbittorrent.username == "example-user"
