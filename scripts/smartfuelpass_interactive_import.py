from __future__ import annotations

import json

from moduly.apps.smartfuelpass.interactive_import import run_interactive_import


def main() -> int:
    result = run_interactive_import()
    print(json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0 if result.state == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
