import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.sync_intelligence import GroupHistoryManager, parse_release_metadata


def test_parse_release_metadata_extracts_group_and_source():
    metadata = parse_release_metadata("Alien.Romulus.2024.1080p.AMZN.WEB-DL.DUAL.5.1-BYNDR")

    assert metadata["group"] == "byndr"
    assert metadata["source"] == "AMZN.WEBDL"


def test_parse_release_metadata_handles_unknowns():
    metadata = parse_release_metadata("Movie 2026 1080p x264")

    assert metadata["group"] == "unknown"
    assert metadata["source"] == "unknown"


def test_parse_release_metadata_does_not_treat_ptbr_suffix_as_group():
    metadata = parse_release_metadata("Movie.2026.1080p.WEB-DL.DUAL.PT-BR")

    assert metadata["group"] == "unknown"


def test_parse_release_metadata_does_not_treat_webdl_suffix_as_group():
    metadata = parse_release_metadata("Sonic.3.O.Filme.2024.1080p.WEB-DL.DUAL.5.1")

    assert metadata["group"] == "unknown"


def test_group_history_manager_rewards_successful_combo(tmp_path: Path):
    manager = GroupHistoryManager(tmp_path / "group_history.json")
    manager.append_attempt(
        {
            "group": "sf",
            "source_4k": "AMZN.WEBDL",
            "source_1080p": "AMZN.WEBDL",
            "result": "SUCCESS",
        }
    )

    bonus, reason = manager.score_candidate(source_4k="AMZN.WEBDL", source_1080p="AMZN.WEBDL", group="sf")

    assert bonus > 0
    assert "combo-success" in reason


def test_group_history_manager_penalizes_known_cut_mismatch(tmp_path: Path):
    manager = GroupHistoryManager(tmp_path / "group_history.json")
    manager.append_attempt(
        {
            "group": "badgrp",
            "source_4k": "AMZN.WEBDL",
            "source_1080p": "WEBRIP",
            "result": "CUT_MISMATCH",
        }
    )

    bonus, reason = manager.score_candidate(source_4k="AMZN.WEBDL", source_1080p="WEBRIP", group="badgrp")

    assert bonus < 0
    assert "combo-cut" in reason


def test_group_history_manager_ignores_generic_source_combo_penalties(tmp_path: Path):
    manager = GroupHistoryManager(tmp_path / "group_history.json")
    manager.append_attempt(
        {
            "group": "unknown",
            "source_4k": "WEBDL",
            "source_1080p": "WEBDL",
            "release_title": "Real.Movie.2026.1080p.WEB-DL.DUAL",
            "result": "CUT_MISMATCH",
        }
    )

    bonus, reason = manager.score_candidate(source_4k="WEBDL", source_1080p="WEBDL", group="unknown")

    assert bonus == 0
    assert reason == "history:none"


def test_group_history_manager_ignores_synthetic_candidate_events(tmp_path: Path):
    manager = GroupHistoryManager(tmp_path / "group_history.json")
    manager.append_attempt(
        {
            "group": "sf",
            "source_4k": "AMZN.WEBDL",
            "source_1080p": "AMZN.WEBDL",
            "release_title": "candidate 1",
            "result": "CUT_MISMATCH",
        }
    )

    bonus, reason = manager.score_candidate(source_4k="AMZN.WEBDL", source_1080p="AMZN.WEBDL", group="sf")

    assert bonus == 0
    assert reason == "history:none"
