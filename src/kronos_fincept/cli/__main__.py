"""JSON bridge entry point for `python -m kronos_fincept.cli`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kronos_fincept.schemas import ForecastRequest, build_error_response
from kronos_fincept.service import forecast_from_request


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.input:
        return json.loads(Path(args.input).read_text(encoding="utf-8"))
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("expected JSON from stdin or --input")
    return json.loads(raw)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and execute one forecast payload."""
    symbol = payload.get("symbol") if isinstance(payload, dict) else None
    try:
        request = ForecastRequest.from_dict(payload)
        return forecast_from_request(request)
    except Exception as exc:
        return build_error_response(str(exc), symbol=str(symbol) if symbol is not None else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KronosFinceptLab forecast JSON bridge")
    parser.add_argument("--input", help="Path to request JSON. Defaults to stdin.")
    parser.add_argument("--output", help="Optional path to write response JSON.")
    args = parser.parse_args(argv)

    response = run(_load_payload(args))
    output = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        sys.stdout.write(output + "\n")
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
