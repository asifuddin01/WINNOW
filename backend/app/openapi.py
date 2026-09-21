"""Print the OpenAPI schema as JSON: `python -m app.openapi` (used by `make api-types`)."""

import json
import sys

from app.main import create_app


def main() -> None:
    schema = create_app().openapi()
    sys.stdout.write(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
