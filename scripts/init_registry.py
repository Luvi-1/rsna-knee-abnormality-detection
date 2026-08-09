"""Initialize an ignored local experiment registry."""

from __future__ import annotations

import argparse
from pathlib import Path

from rsna_knee.registry import initialize_registry, schema_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    initialize_registry(args.path)
    print(f"registry_schema={schema_version(args.path)}")


if __name__ == "__main__":
    main()
