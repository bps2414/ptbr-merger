import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from src.config import get_config

ROOT_DIR = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT_DIR / "tests" / "test_data" / "media_fixtures" / "manifest.json"
_SAMPLE_RATE = 8000


def load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_media_tooling_available() -> None:
    config = get_config()
    ffmpeg_path = _resolve_tool_path(config.ffmpeg.ffmpeg_path)
    ffprobe_path = _resolve_tool_path(config.ffmpeg.ffprobe_path)
    if ffmpeg_path is None:
        raise FileNotFoundError(f"ffmpeg path not found for media fixtures: {config.ffmpeg.ffmpeg_path}")
    if ffprobe_path is None:
        raise FileNotFoundError(f"ffprobe path not found for media fixtures: {config.ffmpeg.ffprobe_path}")


def _resolve_tool_path(tool: str) -> Path | None:
    candidate = Path(tool)
    if candidate.exists():
        return candidate
    resolved = shutil.which(tool)
    return Path(resolved) if resolved else None


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg_path = Path(get_config().ffmpeg.ffmpeg_path)
    cmd = [str(ffmpeg_path), "-y", *args]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"ffmpeg fixture generation failed: {' '.join(cmd)}\n{stderr}") from exc


def probe_media(file_path: Path, include_chapters: bool = False) -> dict:
    ffprobe_path = Path(get_config().ffmpeg.ffprobe_path)
    cmd = [
        str(ffprobe_path),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
    ]
    if include_chapters:
        cmd.append("-show_chapters")
    cmd.append(str(file_path))
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _write_wave(file_path: Path, samples: np.ndarray, sample_rate: int = _SAMPLE_RATE) -> Path:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(file_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return file_path


def _base_pattern(duration_seconds: float, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    total_samples = int(duration_seconds * sample_rate)
    t = np.arange(total_samples, dtype=np.float32) / float(sample_rate)
    rng = np.random.default_rng(12345)
    noise = rng.normal(0.0, 1.0, total_samples).astype(np.float32)
    kernel = np.array([0.05, 0.12, 0.18, 0.30, 0.18, 0.12, 0.05], dtype=np.float32)
    smoothed = np.convolve(noise, kernel, mode="same")
    gate = 0.35 + (np.sin(2.0 * np.pi * 0.29 * t) ** 2) * 0.65
    pulses = np.zeros(total_samples, dtype=np.float32)
    for index, start in enumerate(range(0, total_samples, int(sample_rate * 0.75))):
        end = min(total_samples, start + int(sample_rate * 0.03))
        pulses[start:end] = 0.55 if index % 2 == 0 else -0.45
    return (smoothed * gate * 0.65) + pulses


def _alternate_pattern(duration_seconds: float, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    total_samples = int(duration_seconds * sample_rate)
    t = np.arange(total_samples, dtype=np.float32) / float(sample_rate)
    rng = np.random.default_rng(67890)
    noise = rng.normal(0.0, 1.0, total_samples).astype(np.float32)
    kernel = np.array([0.08, 0.16, 0.24, 0.16, 0.08], dtype=np.float32)
    smoothed = np.convolve(noise, kernel, mode="same")
    gate = 0.25 + (np.sin(2.0 * np.pi * 0.41 * t + 0.7) ** 2) * 0.75
    pulses = np.zeros(total_samples, dtype=np.float32)
    for index, start in enumerate(range(0, total_samples, int(sample_rate * 0.58))):
        end = min(total_samples, start + int(sample_rate * 0.02))
        pulses[start:end] = -0.5 if index % 3 == 0 else 0.4
    return (smoothed * gate * 0.55) + pulses


def _prepend_silence(samples: np.ndarray, silence_seconds: float, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    silence = np.zeros(int(silence_seconds * sample_rate), dtype=np.float32)
    return np.concatenate([silence, samples])


def _cut_mismatch_pattern(base_samples: np.ndarray, sample_rate: int = _SAMPLE_RATE) -> np.ndarray:
    six = int(sample_rate * 6.0)
    seven_half = int(sample_rate * 7.5)
    thirteen_half = int(sample_rate * 13.5)
    tail_alt = _alternate_pattern(6.0, sample_rate)
    return np.concatenate([base_samples[:six], base_samples[seven_half:thirteen_half], tail_alt])


def _write_srt(file_path: Path, entries: list[tuple[str, str]]) -> Path:
    lines = []
    for index, (timespan, text) in enumerate(entries, start=1):
        lines.extend([str(index), timespan, text, ""])
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def _write_ffmetadata(file_path: Path, chapters: list[tuple[int, int, str]]) -> Path:
    lines = [";FFMETADATA1"]
    for start_ms, end_ms, title in chapters:
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={title}",
            ]
        )
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def _build_container(
    *,
    output_path: Path,
    duration_seconds: float,
    audio_tracks: list[dict],
    subtitle_path: Path | None = None,
    metadata_path: Path | None = None,
) -> Path:
    args = [
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=320x180:rate=24:duration={duration_seconds:.3f}",
    ]

    for track in audio_tracks:
        args.extend(["-i", str(track["path"])])

    subtitle_input_index = None
    metadata_input_index = None
    if subtitle_path is not None:
        subtitle_input_index = len(audio_tracks) + 1
        args.extend(["-i", str(subtitle_path)])

    if metadata_path is not None:
        metadata_input_index = len(audio_tracks) + 1 + (1 if subtitle_path is not None else 0)
        args.extend(["-f", "ffmetadata", "-i", str(metadata_path)])

    args.extend(["-map", "0:v:0"])
    for index in range(len(audio_tracks)):
        args.extend(["-map", f"{index + 1}:a:0"])
    if subtitle_input_index is not None:
        args.extend(["-map", f"{subtitle_input_index}:0"])

    args.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
        ]
    )

    if subtitle_input_index is not None:
        args.extend(["-c:s", "srt"])

    if metadata_input_index is not None:
        args.extend(["-map_metadata", str(metadata_input_index)])

    for track_index, track in enumerate(audio_tracks):
        args.extend(["-metadata:s:a:" + str(track_index), f"language={track['language']}"])
        args.extend(["-metadata:s:a:" + str(track_index), f"title={track['title']}"])
        if track.get("default"):
            args.extend(["-disposition:a:" + str(track_index), "default"])

    if subtitle_input_index is not None:
        args.extend(["-metadata:s:s:0", "language=eng"])
        args.extend(["-metadata:s:s:0", "title=English"])

    args.append(str(output_path))
    _run_ffmpeg(args)
    return output_path


def generate_media_corpus(output_dir: Path) -> dict:
    ensure_media_tooling_available()
    manifest = load_manifest()
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures = {}
    base_samples = _base_pattern(18.0)
    offset_samples = _prepend_silence(base_samples, 1.5)
    cut_samples = _cut_mismatch_pattern(base_samples)
    alt_samples = _alternate_pattern(18.0)
    edge_outro_samples = _alternate_pattern(4.0)
    edge_samples = np.concatenate([base_samples, edge_outro_samples])

    wav_dir = output_dir / "wav"
    wav_dir.mkdir(exist_ok=True)
    base_wav = _write_wave(wav_dir / "base.wav", base_samples)
    offset_wav = _write_wave(wav_dir / "offset.wav", offset_samples)
    edge_wav = _write_wave(wav_dir / "edge.wav", edge_samples)
    cut_wav = _write_wave(wav_dir / "cut.wav", cut_samples)
    alt_wav = _write_wave(wav_dir / "alt.wav", alt_samples)

    native_file = _build_container(
        output_path=output_dir / "native_ptbr_ok.mkv",
        duration_seconds=18.0,
        audio_tracks=[
            {"path": alt_wav, "language": "eng", "title": "English", "default": True},
            {"path": base_wav, "language": "por", "title": "Português (Brasil)"},
            {"path": alt_wav, "language": "jpn", "title": "Japanese"},
        ],
    )
    fixtures["native_ptbr_ok"] = {
        "manifest": manifest["fixtures"]["native_ptbr_ok"],
        "files": {"original": native_file},
    }

    mistagged_file = _build_container(
        output_path=output_dir / "ptbr_mistagged.mkv",
        duration_seconds=18.0,
        audio_tracks=[
            {"path": base_wav, "language": "und", "title": "PT-BR Dub", "default": True},
            {"path": alt_wav, "language": "eng", "title": "English"},
        ],
    )
    fixtures["ptbr_mistagged"] = {
        "manifest": manifest["fixtures"]["ptbr_mistagged"],
        "files": {"original": mistagged_file},
    }

    sync_original = _build_container(
        output_path=output_dir / "dual_sync_ok_4k.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": alt_wav, "language": "eng", "title": "English", "default": True}],
    )
    sync_candidate = _build_container(
        output_path=output_dir / "dual_sync_ok_1080p.mkv",
        duration_seconds=18.0,
        audio_tracks=[
            {"path": base_wav, "language": "por", "title": "Português (Brasil)", "default": True},
            {"path": alt_wav, "language": "jpn", "title": "Japanese"},
        ],
    )
    fixtures["dual_sync_ok"] = {
        "manifest": manifest["fixtures"]["dual_sync_ok"],
        "files": {"original": sync_original, "candidate": sync_candidate},
    }

    offset_original = _build_container(
        output_path=output_dir / "dual_offset_ok_4k.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": base_wav, "language": "eng", "title": "English", "default": True}],
    )
    offset_candidate = _build_container(
        output_path=output_dir / "dual_offset_ok_1080p.mkv",
        duration_seconds=19.5,
        audio_tracks=[{"path": offset_wav, "language": "por", "title": "Português (Brasil)", "default": True}],
    )
    fixtures["dual_offset_ok"] = {
        "manifest": manifest["fixtures"]["dual_offset_ok"],
        "files": {"original": offset_original, "candidate": offset_candidate},
    }

    edge_original = _build_container(
        output_path=output_dir / "dual_edge_recoverable_4k.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": base_wav, "language": "eng", "title": "English", "default": True}],
    )
    edge_candidate = _build_container(
        output_path=output_dir / "dual_edge_recoverable_1080p.mkv",
        duration_seconds=22.0,
        audio_tracks=[{"path": edge_wav, "language": "por", "title": "Português (Brasil)", "default": True}],
    )
    fixtures["dual_edge_recoverable"] = {
        "manifest": manifest["fixtures"]["dual_edge_recoverable"],
        "files": {"original": edge_original, "candidate": edge_candidate},
    }

    cut_original = _build_container(
        output_path=output_dir / "dual_cut_mismatch_4k.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": base_wav, "language": "eng", "title": "English", "default": True}],
    )
    cut_candidate = _build_container(
        output_path=output_dir / "dual_cut_mismatch_1080p.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": cut_wav, "language": "por", "title": "Português (Brasil)", "default": True}],
    )
    fixtures["dual_cut_mismatch"] = {
        "manifest": manifest["fixtures"]["dual_cut_mismatch"],
        "files": {"original": cut_original, "candidate": cut_candidate},
    }

    subtitle_path = _write_srt(
        output_dir / "chapters_and_subs.srt",
        [
            ("00:00:01,000 --> 00:00:03,000", "Fixture subtitle line 1"),
            ("00:00:10,000 --> 00:00:12,000", "Fixture subtitle line 2"),
        ],
    )
    metadata_path = _write_ffmetadata(
        output_dir / "chapters_and_subs.ffmeta",
        [
            (0, 9000, "Opening"),
            (9000, 18000, "Finale"),
        ],
    )
    chapters_file = _build_container(
        output_path=output_dir / "chapters_and_subs.mkv",
        duration_seconds=18.0,
        audio_tracks=[{"path": base_wav, "language": "por", "title": "Português (Brasil)", "default": True}],
        subtitle_path=subtitle_path,
        metadata_path=metadata_path,
    )
    fixtures["chapters_and_subs"] = {
        "manifest": manifest["fixtures"]["chapters_and_subs"],
        "files": {"original": chapters_file},
    }

    return fixtures
