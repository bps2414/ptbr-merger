#!/usr/bin/env python3
"""
Seed Guard - Conscious Seeding & Storage I/O Protection Daemon
Automates I/O protection for media storage (/srv/data) by monitoring:
- Active downloads & download speed in qBittorrent
- Active playback sessions in Plex Media Server
- Real-time disk %util of the underlying block device

Rules:
- Fast cut: Immediately stop all seeding/uploading torrents if:
    * active downloads > 0
    * dl_info_speed > 100 KB/s
    * active Plex sessions > 0
    * disk %util > 30.0%
- Hysteresis (300s): Seeding is only resumed (via start) after 300 consecutive seconds
  with 0 active downloads, dl_info_speed <= 100 KB/s, 0 Plex sessions,
  and disk %util < 15.0%.
- API v5+: Uses /api/v2/torrents/stop and /api/v2/torrents/start (never pause/resume).
"""

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Defaults & Thresholds
QBIT_BASE_URL = os.environ.get("QBIT_URL", "http://127.0.0.1:8080")
PLEX_BASE_URL = os.environ.get("PLEX_URL", "http://localhost:32400")
PLEX_PREF_PATH = Path(os.environ.get(
    "PLEX_PREF_PATH",
    "/srv/appdata/plex/Library/Application Support/Plex Media Server/Preferences.xml"
))
MOUNT_POINT = os.environ.get("DATA_MOUNT", "/srv/data")

FAST_CUT_DL_SPEED = 100 * 1024  # 100 KB/s in bytes/sec
FAST_CUT_DISK_UTIL = 30.0       # > 30% triggers fast cut
RESUME_DISK_UTIL = 15.0         # < 15% required for quiet period
QUIET_DURATION_SEC = 180        # 3 minutes (180 seconds)
CHECK_INTERVAL_SEC = 5          # Loop interval in seconds

STATE_FILE = Path("/home/servidorcasa/server/ops/seed_guard_state.json")
LOG_FILE = Path("/home/servidorcasa/server/ops/seed_guard.log")

# Setup Logging
logger = logging.getLogger("seed_guard")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

try:
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    logger.warning(f"Could not open log file {LOG_FILE}: {e}")

running = True


def handle_shutdown(signum, frame):
    global running
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def resolve_parent_block_device(mount_path: str) -> str:
    """Dynamically resolve parent block device of mount_path (e.g. sdb for /srv/data)."""
    try:
        out = subprocess.check_output(["df", "-P", mount_path], text=True).strip().splitlines()
        if len(out) < 2:
            raise RuntimeError(f"Could not parse df output for {mount_path}")
        fs_dev = out[1].split()[0]

        pkname = subprocess.check_output(["lsblk", "-no", "PKNAME", fs_dev], text=True).strip()
        if not pkname:
            pkname = subprocess.check_output(["lsblk", "-no", "KNAME", fs_dev], text=True).strip()
        return pkname
    except Exception as e:
        logger.error(f"Error resolving parent block device for {mount_path}: {e}")
        return "sdb"


def read_io_ticks(dev_name: str) -> int:
    """Read field 10 (io_ticks in ms) from /sys/block/<dev>/stat."""
    stat_file = f"/sys/block/{dev_name}/stat"
    try:
        with open(stat_file, "r") as f:
            fields = f.read().split()
            return int(fields[9])  # Field 10 is index 9
    except Exception as e:
        logger.warning(f"Could not read {stat_file}: {e}")
        return -1


def measure_disk_util_iostat(dev_name: str) -> float:
    """Measure real-time %util using iostat -x -y 1 1 <dev> as fallback or single-shot."""
    try:
        cmd = ["iostat", "-x", "-y", "1", "1", dev_name]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        for line in lines:
            parts = line.split()
            if parts and parts[0] == dev_name:
                return float(parts[-1].replace(",", "."))
    except Exception as e:
        logger.warning(f"iostat measurement failed for {dev_name}: {e}")
    return 0.0


def get_plex_token() -> str:
    """Extract PlexOnlineToken dynamically from Preferences.xml."""
    if PLEX_PREF_PATH.exists():
        try:
            with open(PLEX_PREF_PATH, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                m = re.search(r'PlexOnlineToken="([^"]+)"', content)
                if m:
                    return m.group(1)
        except Exception as e:
            logger.warning(f"Could not read Plex token from {PLEX_PREF_PATH}: {e}")
    return ""


def get_plex_sessions(token: str) -> int:
    """Query Plex /status/sessions endpoint to get active streaming sessions."""
    url = f"{PLEX_BASE_URL}/status/sessions"
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Plex-Token"] = token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return int(data.get("MediaContainer", {}).get("size", 0))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            logger.warning("Plex returned 401 Unauthorized. Check Plex token.")
        else:
            logger.warning(f"Plex HTTP error {e.code}: {e.reason}")
    except Exception as e:
        logger.debug(f"Plex not reachable or error querying sessions: {e}")
    return 0


def qbit_request(path: str, data: dict = None, timeout: float = 4.0):
    """Perform request to qBittorrent Web API v2."""
    url = f"{QBIT_BASE_URL}{path}"
    post_data = None
    if data is not None:
        post_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=post_data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        if content:
            try:
                return json.loads(content.decode("utf-8"))
            except Exception:
                return content.decode("utf-8")
        return None


def get_qbit_status():
    """Retrieve torrent list and transfer metrics from qBittorrent."""
    torrents = qbit_request("/api/v2/torrents/info") or []
    transfer = qbit_request("/api/v2/transfer/info") or {}

    dl_speed = int(transfer.get("dl_info_speed", 0))

    active_download_states = {
        "downloading", "stalledDL", "queuedDL", "metaDL",
        "forcedDL", "checkingDL", "allocating"
    }
    seeding_states = {
        "uploading", "stalledUP", "queuedUP", "forcedUP"
    }

    active_downloads = []
    seeding_torrents = []
    stopped_seeders = []

    for t in torrents:
        state = t.get("state", "")
        progress = float(t.get("progress", 0))

        if state in active_download_states:
            active_downloads.append(t)
        elif state in seeding_states:
            seeding_torrents.append(t)
        elif state in ("stoppedUP", "pausedUP") and progress >= 1.0:
            # Check if torrent has hit share ratio or seeding time limits
            max_ratio = float(t.get("max_ratio", -1))
            ratio = float(t.get("ratio", 0))
            max_time = int(t.get("max_seeding_time", -1))
            seeding_time = int(t.get("seeding_time", 0))

            ratio_reached = (max_ratio > 0 and ratio >= max_ratio)
            time_reached = (max_time > 0 and seeding_time >= (max_time * 60))

            if not (ratio_reached or time_reached):
                stopped_seeders.append(t)

    return {
        "dl_info_speed": dl_speed,
        "active_downloads": active_downloads,
        "seeding_torrents": seeding_torrents,
        "stopped_seeders": stopped_seeders,
        "total_torrents": len(torrents)
    }


def stop_torrents(hashes: list):
    """Stop torrents via POST /api/v2/torrents/stop (API v5+)."""
    if not hashes:
        return
    pipe_hashes = "|".join(hashes)
    qbit_request("/api/v2/torrents/stop", {"hashes": pipe_hashes})


def start_torrents(hashes: list):
    """Start torrents via POST /api/v2/torrents/start (API v5+)."""
    if not hashes:
        return
    pipe_hashes = "|".join(hashes)
    qbit_request("/api/v2/torrents/start", {"hashes": pipe_hashes})


def save_state(state: dict):
    """Atomically save runtime state to json file."""
    try:
        tmp_file = STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        tmp_file.replace(STATE_FILE)
    except Exception as e:
        logger.warning(f"Could not write state file: {e}")


def load_state() -> dict:
    """Load runtime state if available."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def run_guard(once: bool = False, interval: int = CHECK_INTERVAL_SEC):
    global running

    dev = resolve_parent_block_device(MOUNT_POINT)
    logger.info(f"Seed Guard started. Target mount: {MOUNT_POINT} -> Block Device: {dev}")
    plex_token = get_plex_token()
    if plex_token:
        logger.info("Plex online token detected for session inspection.")
    else:
        logger.warning("No Plex online token found; Plex session calls might fail if unauthorized.")

    prev_ticks = read_io_ticks(dev)
    prev_time = time.time()

    state = load_state()
    quiet_since = state.get("quiet_since")
    seeding_active = state.get("seeding_active", False)
    managed_hashes = set(state.get("managed_stopped_hashes", []))

    # Initial single sample for disk util if starting up
    if once or prev_ticks < 0:
        disk_util = measure_disk_util_iostat(dev)
    else:
        time.sleep(1.0)
        curr_ticks = read_io_ticks(dev)
        curr_time = time.time()
        elapsed_ms = (curr_time - prev_time) * 1000.0
        delta_ticks = curr_ticks - prev_ticks
        disk_util = max(0.0, min(100.0, (delta_ticks / elapsed_ms) * 100.0)) if elapsed_ms > 0 else 0.0
        prev_ticks = curr_ticks
        prev_time = curr_time

    while running:
        loop_start = time.time()
        try:
            # 1. Query qBittorrent & Plex
            q_status = get_qbit_status()
            plex_sessions = get_plex_sessions(plex_token)

            active_dl_count = len(q_status["active_downloads"])
            dl_speed = q_status["dl_info_speed"]
            seeding_torrents = q_status["seeding_torrents"]
            stopped_seeders = q_status["stopped_seeders"]

            # 2. Measure Disk Util
            curr_ticks = read_io_ticks(dev)
            now = time.time()
            elapsed_ms = (now - prev_time) * 1000.0
            if prev_ticks >= 0 and curr_ticks >= prev_ticks and elapsed_ms > 0:
                delta_ticks = curr_ticks - prev_ticks
                disk_util = max(0.0, min(100.0, (delta_ticks / elapsed_ms) * 100.0))
            else:
                disk_util = measure_disk_util_iostat(dev)

            prev_ticks = curr_ticks
            prev_time = now

            dl_speed_kb = dl_speed / 1024.0

            # 3. Evaluate Fast Cut Condition
            fast_cut_triggers = []
            if active_dl_count > 0:
                fast_cut_triggers.append(f"downloads={active_dl_count}")
            if dl_speed > FAST_CUT_DL_SPEED:
                fast_cut_triggers.append(f"speed={dl_speed_kb:.1f}KB/s")
            if plex_sessions > 0:
                fast_cut_triggers.append(f"plex_sessions={plex_sessions}")
            if disk_util > FAST_CUT_DISK_UTIL:
                fast_cut_triggers.append(f"disk_util={disk_util:.1f}%")

            is_fast_cut = len(fast_cut_triggers) > 0

            # 4. Evaluate Quiet / Idle Condition for Hysteresis
            is_idle = (
                active_dl_count == 0 and
                dl_speed <= FAST_CUT_DL_SPEED and
                plex_sessions == 0 and
                disk_util < RESUME_DISK_UTIL
            )

            current_action = "monitoring"

            if is_fast_cut:
                # Fast cut: stop any actively seeding torrents immediately
                seeding_active = False
                quiet_since = None
                if seeding_torrents:
                    cut_hashes = [t["hash"] for t in seeding_torrents]
                    cut_names = [t.get("name", t["hash"][:8]) for t in seeding_torrents]
                    logger.warning(
                        f"[FAST CUT] Stopping {len(cut_hashes)} seeding torrents: "
                        f"{', '.join(cut_names)} | Triggers: {', '.join(fast_cut_triggers)}"
                    )
                    stop_torrents(cut_hashes)
                    managed_hashes.update(cut_hashes)
                    current_action = f"fast_cut_stopped_{len(cut_hashes)}"
                else:
                    current_action = f"fast_cut_active_{','.join(fast_cut_triggers)}"
                    logger.debug(f"Fast cut conditions present ({', '.join(fast_cut_triggers)}), no seeding torrents to cut.")

            elif is_idle:
                # Idle state: downloads=0, plex=0, disk < 15%
                if seeding_active:
                    # Seeding was already re-activated after 300s quiet period; continue seeding
                    current_action = f"seeding_active_idle (disk={disk_util:.1f}%)"
                else:
                    # Seeding not yet active: ensure all seeding torrents remain stopped during the 300s quiet wait
                    if seeding_torrents:
                        cut_hashes = [t["hash"] for t in seeding_torrents]
                        cut_names = [t.get("name", t["hash"][:8]) for t in seeding_torrents]
                        logger.info(
                            f"[QUIET PREPARATION] Stopping {len(cut_hashes)} newly active seeding torrents: "
                            f"{', '.join(cut_names)} to allow quiet hysteresis countdown."
                        )
                        stop_torrents(cut_hashes)
                        managed_hashes.update(cut_hashes)

                    if quiet_since is None:
                        quiet_since = now
                        logger.info(
                            f"[QUIET] System entered idle state (downloads=0, Plex=0, disk={disk_util:.1f}%). "
                            f"Starting {QUIET_DURATION_SEC}s hysteresis timer..."
                        )

                    quiet_elapsed = now - quiet_since
                    remaining_sec = max(0, QUIET_DURATION_SEC - int(quiet_elapsed))

                    if quiet_elapsed >= QUIET_DURATION_SEC:
                        # 300s quiet period completed! Re-activate seeding
                        eligible_hashes = [t["hash"] for t in stopped_seeders]
                        if eligible_hashes:
                            names = [t.get("name", t["hash"][:8]) for t in stopped_seeders]
                            logger.info(
                                f"[RESUME] {QUIET_DURATION_SEC}s quiet period satisfied! Resuming seeding for {len(eligible_hashes)} torrents: "
                                f"{', '.join(names)} | Disk util: {disk_util:.1f}%"
                            )
                            start_torrents(eligible_hashes)
                            managed_hashes.clear()
                            seeding_active = True
                            current_action = f"resumed_{len(eligible_hashes)}_torrents"
                        else:
                            seeding_active = True
                            current_action = "quiet_satisfied_no_torrents_to_resume"
                    else:
                        current_action = f"quiet_timer_{int(quiet_elapsed)}s_remaining_{remaining_sec}s"
                        logger.debug(f"Quiet period in progress: {int(quiet_elapsed)}s/{QUIET_DURATION_SEC}s (disk={disk_util:.1f}%)")

            else:
                # Transitional state: e.g. 15% <= disk_util <= 30% without downloads or Plex
                if seeding_active:
                    # Moderate disk load but < 30% fast cut threshold: allow seeding to continue
                    current_action = f"seeding_active_moderate_disk_{disk_util:.1f}%"
                else:
                    # Seeding not active and disk is not idle (<15%): reset quiet period timer
                    if quiet_since is not None:
                        logger.info(
                            f"[HYSTERESIS RESET] Disk util rose to {disk_util:.1f}% (>= {RESUME_DISK_UTIL}%). "
                            f"Resetting quiet period timer."
                        )
                        quiet_since = None
                    if seeding_torrents:
                        cut_hashes = [t["hash"] for t in seeding_torrents]
                        stop_torrents(cut_hashes)
                        managed_hashes.update(cut_hashes)
                    current_action = f"transitional_disk_util_{disk_util:.1f}%"

            # 5. Persist State
            state_data = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "device": dev,
                "disk_util_pct": round(disk_util, 2),
                "active_downloads": active_dl_count,
                "dl_speed_bytes": dl_speed,
                "dl_speed_kb": round(dl_speed_kb, 1),
                "plex_sessions": plex_sessions,
                "seeding_torrents": len(seeding_torrents),
                "stopped_seeders": len(stopped_seeders),
                "seeding_active": seeding_active,
                "is_fast_cut": is_fast_cut,
                "is_idle": is_idle,
                "quiet_since": quiet_since,
                "quiet_elapsed_sec": int(now - quiet_since) if quiet_since else 0,
                "current_action": current_action,
                "managed_stopped_hashes": list(managed_hashes)
            }
            save_state(state_data)

            if once:
                print(json.dumps(state_data, indent=2))
                break

        except Exception as e:
            logger.error(f"Unexpected error in guard loop: {e}", exc_info=True)
            if once:
                break

        # Sleep remaining interval
        elapsed_loop = time.time() - loop_start
        sleep_time = max(0.5, interval - elapsed_loop)
        time.sleep(sleep_time)

    logger.info("Seed Guard stopped.")


def main():
    parser = argparse.ArgumentParser(description="Seed Guard - Conscious Seeding & I/O Protection")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL_SEC, help=f"Check interval in seconds (default: {CHECK_INTERVAL_SEC})")
    args = parser.parse_args()

    run_guard(once=args.once, interval=args.interval)


if __name__ == "__main__":
    main()
