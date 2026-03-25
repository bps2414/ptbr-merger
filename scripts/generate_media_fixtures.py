from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.support.media_fixtures import generate_media_corpus


def main() -> None:
    parser = ArgumentParser(description="Generate deterministic local media fixtures for integration tests.")
    parser.add_argument(
        "--output-dir",
        default="tmp/media-fixtures",
        help="Output directory for generated MKV/WAV fixture files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    corpus = generate_media_corpus(output_dir)
    print(f"fixtures_generated={len(corpus)} output_dir={output_dir}")


if __name__ == "__main__":
    main()
