"""Write the API's OpenAPI schema to a file so the web app can generate its
TypeScript types from it (web: `npm run api:types`). Needs no database."""

import json
import sys
from pathlib import Path

from api.app import create_app


def main(out: str) -> None:
    schema = create_app("export-only", session_factory=lambda: None, session_timeout_hours=1).openapi()
    Path(out).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
