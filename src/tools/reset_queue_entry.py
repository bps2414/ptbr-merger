import argparse
import json
from pathlib import Path

from src.config import get_config


def reset_queue_entry(queue_file: Path, tmdb_id: str) -> bool:
    path = Path(queue_file)
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(tmdb_id) not in payload:
        return False
    payload.pop(str(tmdb_id), None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def parse_args() -> argparse.Namespace:
    config = get_config()
    parser = argparse.ArgumentParser(description="Remove uma entrada do queue.json por TMDB ID.")
    parser.add_argument("--tmdb", required=True, help="TMDB ID a remover")
    parser.add_argument("--queue-file", default=config.processing.queue_file, help="Arquivo queue.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    removed = reset_queue_entry(Path(args.queue_file), args.tmdb)
    if removed:
        print(f"TMDB {args.tmdb} removido do ledger.")
    else:
        print(f"TMDB {args.tmdb} não estava presente no ledger.")


if __name__ == "__main__":
    main()
