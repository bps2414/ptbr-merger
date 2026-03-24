import argparse
import time
from pathlib import Path

from src.config import get_config


def read_last_lines(log_file: Path, lines: int = 50) -> list[str]:
    path = Path(log_file)
    if not path.exists():
        return []
    contents = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return contents[-max(0, lines) :]


def parse_args() -> argparse.Namespace:
    config = get_config()
    parser = argparse.ArgumentParser(description="Tail simples do log do PTBRMerger.")
    parser.add_argument("--file", default=config.logging.file, help="Arquivo de log")
    parser.add_argument("--lines", type=int, default=50, help="Quantidade inicial de linhas")
    parser.add_argument("--follow", action="store_true", help="Seguir novas linhas em tempo real")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_file = Path(args.file)
    last_lines = read_last_lines(log_file, lines=args.lines)
    for line in last_lines:
        print(line)

    if not args.follow:
        return

    last_size = log_file.stat().st_size if log_file.exists() else 0
    while True:
        time.sleep(1)
        if not log_file.exists():
            continue
        current_size = log_file.stat().st_size
        if current_size < last_size:
            last_size = 0
        if current_size == last_size:
            continue
        with open(log_file, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(last_size)
            chunk = handle.read()
        for line in chunk.splitlines():
            print(line)
        last_size = current_size


if __name__ == "__main__":
    main()
