"""Run the local dry-run forecast example."""

from __future__ import annotations

import json
from pathlib import Path

from kronos_fincept.cli import run

ROOT = Path(__file__).resolve().parents[1]

payload = json.loads((ROOT / "examples" / "request.forecast.json").read_text(encoding="utf-8"))
print(json.dumps(run(payload), ensure_ascii=False, indent=2))
