#!/usr/bin/env python3
"""Export shared Markdown courses without management metadata."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketing_diagnosis.knowledge_corpus import export_courses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_courses(args.source, args.target)))


if __name__ == "__main__":
    main()
