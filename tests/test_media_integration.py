import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import analyzer, audio_fingerprint, merger
from tests.support.media_fixtures import ensure_media_tooling_available, generate_media_corpus, load_manifest, probe_media


@pytest.fixture(scope="session")
def media_corpus(tmp_path_factory: pytest.TempPathFactory) -> dict:
    try:
        ensure_media_tooling_available()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    output_dir = tmp_path_factory.mktemp("media-fixtures")
    return generate_media_corpus(output_dir)


@pytest.fixture(autouse=True)
def fingerprint_test_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_fingerprint.config.fingerprint, "sample_rate", 1000)
    monkeypatch.setattr(audio_fingerprint.config.fingerprint, "window_seconds", 2)
    monkeypatch.setattr(audio_fingerprint.config.fingerprint, "max_offset_seconds", 3)
    monkeypatch.setattr(audio_fingerprint.config.fingerprint, "min_confidence", 0.55)
    monkeypatch.setattr(audio_fingerprint.config.fingerprint, "consistency_tolerance_seconds", 0.45)
    monkeypatch.setattr(analyzer.config.sync, "max_duration_diff_seconds", 3)


def test_native_ptbr_fixture_supports_optimize_only(media_corpus: dict, tmp_path: Path) -> None:
    native = media_corpus["native_ptbr_ok"]["files"]["original"]

    assert analyzer.has_ptbr_audio(native) is True

    output_file = tmp_path / "optimized-native.mkv"
    merger.mux_audio(native, None, output_file)

    validation = analyzer.validate_final_file(output_file, native)
    assert validation["valid"] is True


def test_mistagged_ptbr_fixture_is_detected(media_corpus: dict) -> None:
    mistagged = media_corpus["ptbr_mistagged"]["files"]["original"]

    assert analyzer.has_ptbr_audio(mistagged) is True


def test_sync_ok_fixture_can_merge_real_audio(media_corpus: dict, tmp_path: Path) -> None:
    original = media_corpus["dual_sync_ok"]["files"]["original"]
    candidate = media_corpus["dual_sync_ok"]["files"]["candidate"]

    stream_index = analyzer.get_ptbr_stream_index(candidate)
    assert stream_index is not None

    extracted_audio = tmp_path / "ptbr-sync-ok.aac"
    merger.extract_audio(candidate, stream_index, extracted_audio)

    output_file = tmp_path / "merged-sync-ok.mkv"
    merger.mux_audio(original, extracted_audio, output_file)

    validation = analyzer.validate_final_file(output_file, original)
    assert validation["valid"] is True


def test_fingerprint_detects_offset_in_real_fixture(media_corpus: dict) -> None:
    original = media_corpus["dual_offset_ok"]["files"]["original"]
    candidate = media_corpus["dual_offset_ok"]["files"]["candidate"]

    result = audio_fingerprint.fingerprint_sync(
        file_4k=original,
        file_1080p=candidate,
        duration_4k=analyzer.get_duration(original),
    )

    assert result["category"] == "FINGERPRINT_OFFSET_OK"
    assert abs(float(result["best_offset_seconds"])) > 0.5


def test_fingerprint_rejects_structural_mismatch_fixture(media_corpus: dict) -> None:
    original = media_corpus["dual_cut_mismatch"]["files"]["original"]
    candidate = media_corpus["dual_cut_mismatch"]["files"]["candidate"]

    result = audio_fingerprint.fingerprint_sync(
        file_4k=original,
        file_1080p=candidate,
        duration_4k=analyzer.get_duration(original),
    )

    assert result["category"] in {"FINGERPRINT_DRIFT_SUSPECTED", "FINGERPRINT_CUT_MISMATCH"}


def test_optimize_only_preserves_chapters_and_subtitles(media_corpus: dict, tmp_path: Path) -> None:
    original = media_corpus["chapters_and_subs"]["files"]["original"]
    output_file = tmp_path / "optimized-chapters.mkv"

    merger.mux_audio(original, None, output_file)

    probe = probe_media(output_file, include_chapters=True)
    subtitle_streams = [stream for stream in probe["streams"] if stream.get("codec_type") == "subtitle"]

    assert probe["chapters"]
    assert subtitle_streams


def test_validate_final_file_rejects_real_media_without_ptbr(media_corpus: dict) -> None:
    original_without_ptbr = media_corpus["dual_sync_ok"]["files"]["original"]

    validation = analyzer.validate_final_file(original_without_ptbr, original_without_ptbr)

    assert validation["valid"] is False
    assert validation["reason"] == "MISSING_PTBR"


def test_generated_media_corpus_matches_manifest(media_corpus: dict) -> None:
    manifest = load_manifest()

    assert set(media_corpus) == set(manifest["fixtures"])
    for fixture_name, fixture in media_corpus.items():
        assert fixture["manifest"] == manifest["fixtures"][fixture_name]
        for file_path in fixture["files"].values():
            assert Path(file_path).exists()


@patch("tests.support.media_fixtures.shutil.which")
def test_media_tooling_accepts_ffmpeg_binaries_from_path(mock_which) -> None:
    mock_which.side_effect = lambda name: f"C:/tools/{name}.exe"

    with patch.object(audio_fingerprint.config.ffmpeg, "ffmpeg_path", "ffmpeg"), patch.object(
        audio_fingerprint.config.ffmpeg, "ffprobe_path", "ffprobe"
    ):
        ensure_media_tooling_available()


@patch("tests.support.media_fixtures.shutil.which", return_value=None)
def test_media_tooling_raises_for_missing_binaries(_mock_which) -> None:
    with patch.object(audio_fingerprint.config.ffmpeg, "ffmpeg_path", "missing-ffmpeg"), patch.object(
        audio_fingerprint.config.ffmpeg, "ffprobe_path", "missing-ffprobe"
    ):
        with pytest.raises(FileNotFoundError):
            ensure_media_tooling_available()
