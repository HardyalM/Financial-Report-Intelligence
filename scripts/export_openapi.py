"""Export the HTTP API's OpenAPI document to schemas/openapi.json (M6.2).

    python scripts/export_openapi.py           # write
    python scripts/export_openapi.py --check   # exit 1 if the committed file is stale

The document is generated from the pydantic models in finintel/api/models.py, so the API contract
and the code cannot drift: `make contracts-check` fails when they do.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finintel.api import create_app

TARGET = Path(__file__).resolve().parent.parent / "schemas" / "openapi.json"


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != text:
            print("schemas/openapi.json is stale: run `make contracts`", file=sys.stderr)
            return 1
        print("schemas/openapi.json up to date")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(TARGET.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
