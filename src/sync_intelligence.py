import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config
from src.notifier import warning

config = get_config()

_GROUP_SUFFIX_RE = re.compile(r"-([A-Za-z0-9][A-Za-z0-9._]{1,31})$")
_GROUP_STOPWORDS = {
    "dl",
    "br",
    "rip",
    "webrip",
    "webdl",
    "remux",
    "bluray",
    "bdrip",
    "dual",
    "multi",
    "pt",
    "ptbr",
    "amzn",
    "nf",
    "dsnp",
    "hmax",
    "atvp",
}
_GENERIC_SOURCES = {
    "unknown",
    "WEBDL",
    "WEBRIP",
    "BLURAY",
    "REMUX",
    "BDREMUX",
    "HDTV",
}
_PROVIDER_PATTERNS = [
    ("AMZN", ("AMZN", "AMAZON")),
    ("NETFLIX", ("NETFLIX", ".NF.", "[NF]", " NF ")),
    ("DSNP", ("DSNP", "DISNEY", "DISNEYPLUS")),
    ("HMAX", ("HMAX", " MAX ", "[MAX]", ".MAX.")),
    ("ATVP", ("ATVP", "APPLETV", "APPLE TV", "ITUNES", " MA ")),
    ("MA", ("MOVIESANYWHERE", "[MA]", ".MA.")),
]
_MEDIUM_PATTERNS = [
    ("BDREMUX", ("BDREMUX",)),
    ("REMUX", ("REMUX",)),
    ("BLURAY", ("BLURAY", "BDRIP", "BD-RIP", "BDREMUX")),
    ("WEBDL", ("WEB-DL", "WEBDL")),
    ("WEBRIP", ("WEBRIP",)),
    ("HDTV", ("HDTV",)),
]
_SUCCESS_RESULTS = {"SUCCESS", "MANUAL_RECOVERY_SUCCESS", "FINGERPRINT_SYNC_OK", "FINGERPRINT_OFFSET_OK"}
_CUT_FAILURE_RESULTS = {"CUT_MISMATCH", "FINGERPRINT_CUT_MISMATCH", "FINGERPRINT_DRIFT_SUSPECTED"}
_RUNTIME_FAILURE_RESULTS = {"RUNTIME_INCOMPATIBLE"}
_RECOVERABLE_RESULTS = {"INTRO_OUTRO_DIVERGENCE", "AMBIGUOUS_RECOVERABLE", "OFFSET_SUSPECTED", "FINGERPRINT_LOW_CONFIDENCE"}
_RECOVERY_FAILED_RESULTS = {"OFFSET_SUSPECTED_FAILED", "AUTO_RECOVERY_FAILED", "MANUAL_RECOVERY_FAILED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_title(value: str | None) -> str:
    return str(value or "").strip()


def parse_release_metadata(title: str) -> dict:
    normalized_title = _canonical_title(title)
    upper_title = normalized_title.upper()

    group = "unknown"
    match = _GROUP_SUFFIX_RE.search(normalized_title)
    if match:
        candidate_group = match.group(1).strip(" ._").lower()
        group_tokens = [token for token in re.split(r"[._]+", candidate_group) if token]
        fake_group = bool(group_tokens) and all(token in _GROUP_STOPWORDS or token.isdigit() for token in group_tokens)
        if candidate_group and candidate_group not in _GROUP_STOPWORDS and not fake_group:
            group = candidate_group

    provider = None
    for canonical, patterns in _PROVIDER_PATTERNS:
        if any(pattern in upper_title for pattern in patterns):
            provider = canonical
            break

    medium = None
    for canonical, patterns in _MEDIUM_PATTERNS:
        if any(pattern in upper_title for pattern in patterns):
            medium = canonical
            break

    if provider and medium:
        source = f"{provider}.{medium}"
    elif provider:
        source = provider
    elif medium:
        source = medium
    else:
        source = "unknown"

    return {
        "group": group,
        "source": source,
        "normalized_title": normalized_title,
    }


class GroupHistoryManager:
    def __init__(self, history_file: Path, max_entries: int = 1000) -> None:
        self.history_file = Path(history_file)
        self.max_entries = max_entries
        if not self.history_file.exists():
            self._write([])

    def _read(self) -> list[dict]:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as file:
                data = json.load(file) or []
        except json.JSONDecodeError as exc:
            warning(f"group_history.json inválido ou corrompido em {self.history_file}: {exc}. Reiniciando histórico em memória.")
            return []
        return data if isinstance(data, list) else []

    def _write(self, payload: list[dict]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as file:
            json.dump(payload[-self.max_entries :], file, ensure_ascii=False, indent=2)

    def append_attempt(self, event: dict) -> dict:
        events = self._read()
        payload = {"timestamp": _utc_now(), **event}
        events.append(payload)
        self._write(events)
        return payload

    def _matching_events(self, *, source_4k: str | None = None, source_1080p: str | None = None, group: str | None = None) -> list[dict]:
        events = self._read()
        matched = []
        for event in events:
            release_title = str(event.get("release_title") or "").strip().lower()
            if release_title.startswith("candidate "):
                continue
            if source_4k and event.get("source_4k") != source_4k:
                continue
            if source_1080p and event.get("source_1080p") != source_1080p:
                continue
            if group and event.get("group") != group:
                continue
            matched.append(event)
        return matched

    def score_candidate(self, *, source_4k: str, source_1080p: str, group: str) -> tuple[int, str]:
        if not any(value and value != "unknown" for value in (source_4k, source_1080p, group)):
            return 0, "history:none"

        score = 0
        reasons: list[str] = []
        bonus_success = getattr(config.scoring, "history_bonus_success", 8)
        penalty_cut = getattr(config.scoring, "history_penalty_cut_mismatch", 18)
        penalty_runtime = getattr(config.scoring, "history_penalty_runtime_incompatible", 14)
        min_group_samples = getattr(config.scoring, "history_min_group_samples", 2)
        min_source_samples = getattr(config.scoring, "history_min_source_samples", 2)
        generic_combo = source_4k in _GENERIC_SOURCES and source_1080p in _GENERIC_SOURCES

        combo_events = self._matching_events(source_4k=source_4k, source_1080p=source_1080p)
        combo_results = Counter(event.get("result") for event in combo_events)
        combo_success = sum(combo_results[result] for result in _SUCCESS_RESULTS)
        combo_cut_failures = sum(combo_results[result] for result in _CUT_FAILURE_RESULTS)
        combo_runtime_failures = sum(combo_results[result] for result in _RUNTIME_FAILURE_RESULTS)
        combo_recoverable = sum(combo_results[result] for result in _RECOVERABLE_RESULTS)
        combo_recovery_failed = sum(combo_results[result] for result in _RECOVERY_FAILED_RESULTS)

        if combo_success and not generic_combo:
            delta = bonus_success * min(combo_success, 2)
            score += delta
            reasons.append(f"combo-success:+{delta}")
        if combo_cut_failures and not generic_combo:
            delta = penalty_cut * min(combo_cut_failures, 2)
            score -= delta
            reasons.append(f"combo-cut:-{delta}")
        if combo_runtime_failures and not generic_combo:
            delta = penalty_runtime * min(combo_runtime_failures, 2)
            score -= delta
            reasons.append(f"combo-runtime:-{delta}")
        if combo_recoverable and not generic_combo:
            reasons.append(f"combo-recoverable:{combo_recoverable}")
        if combo_recovery_failed and not generic_combo:
            reasons.append(f"combo-recovery-failed:{combo_recovery_failed}")

        if group and group != "unknown":
            group_events = self._matching_events(group=group)
            group_results = Counter(event.get("result") for event in group_events)
            group_success = sum(group_results[result] for result in _SUCCESS_RESULTS)
            group_failures = sum(group_results[result] for result in _CUT_FAILURE_RESULTS | _RUNTIME_FAILURE_RESULTS)
            if group_success > group_failures and group_success >= min_group_samples:
                delta = max(2, bonus_success // 2)
                score += delta
                reasons.append(f"group-good:+{delta}")
            elif group_failures > group_success and group_failures >= min_group_samples:
                delta = max(2, penalty_cut // 3)
                score -= delta
                reasons.append(f"group-bad:-{delta}")

        if source_1080p and source_1080p not in _GENERIC_SOURCES:
            source_events = self._matching_events(source_1080p=source_1080p)
            source_results = Counter(event.get("result") for event in source_events)
            source_success = sum(source_results[result] for result in _SUCCESS_RESULTS)
            source_failures = sum(source_results[result] for result in _CUT_FAILURE_RESULTS | _RUNTIME_FAILURE_RESULTS)
            if source_success > source_failures and source_success >= min_source_samples:
                delta = max(1, bonus_success // 3)
                score += delta
                reasons.append(f"source-good:+{delta}")
            elif source_failures > source_success and source_failures >= min_source_samples:
                delta = max(1, penalty_runtime // 3)
                score -= delta
                reasons.append(f"source-bad:-{delta}")

        return score, ", ".join(reasons) if reasons else "history:none"

    def summarize(self, limit: int = 5) -> dict:
        events = self._read()
        groups = Counter()
        combos = Counter()
        for event in events:
            if event.get("group") and event.get("group") != "unknown":
                groups[(event["group"], event.get("result", "unknown"))] += 1
            if event.get("source_4k") and event.get("source_1080p"):
                combos[(event["source_4k"], event["source_1080p"], event.get("result", "unknown"))] += 1
        return {
            "recent_attempts": events[-limit:],
            "top_groups": [
                {"group": group, "result": result, "count": count}
                for (group, result), count in groups.most_common(limit)
            ],
            "top_combos": [
                {"source_4k": source_4k, "source_1080p": source_1080p, "result": result, "count": count}
                for (source_4k, source_1080p, result), count in combos.most_common(limit)
            ],
        }
