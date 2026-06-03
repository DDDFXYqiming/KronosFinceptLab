#!/usr/bin/env python3
"""Pre-generate suggestion questions for the KronosFinceptLab web UI.

Run daily via cron. Generates 4 time-slot batches (6h each) for each
type × language combination and writes to a JSON file that the API
route reads from.

Usage:
    python scripts/suggestions_pregen.py [--slots 4] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project src is on the path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from kronos_fincept.api.routes.suggestions import (
    _ANALYSIS_FALLBACKS,
    _ANALYSIS_FALLBACKS_EN,
    _MACRO_FALLBACKS,
    _MACRO_FALLBACKS_EN,
    _call_llm_for_suggestions,
    _ANALYSIS_SYSTEM,
    _MACRO_SYSTEM,
    _ANALYSIS_SYSTEM_EN,
    _MACRO_SYSTEM_EN,
    _ANALYSIS_FLAVORS,
    _MACRO_FLAVORS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("suggestions_pregen")

_DEFAULT_OUTPUT = str(_PROJECT_ROOT / "data" / "suggestions_pregen.json")

_TYPES = [
    ("analysis", "zh-CN"),
    ("analysis", "en-US"),
    ("macro", "zh-CN"),
    ("macro", "en-US"),
]

_FALLBACKS = {
    ("analysis", "zh-CN"): _ANALYSIS_FALLBACKS,
    ("analysis", "en-US"): _ANALYSIS_FALLBACKS_EN,
    ("macro", "zh-CN"): _MACRO_FALLBACKS,
    ("macro", "en-US"): _MACRO_FALLBACKS_EN,
}


def _generate_one_set(
    question_type: str,
    language: str,
) -> list[str]:
    """Generate one set of suggestions for the given type and language."""
    if question_type == "analysis":
        system_prompt = _ANALYSIS_SYSTEM_EN if language == "en-US" else _ANALYSIS_SYSTEM
        user_prompt = (
            "Generate 3 English single-stock research questions as JSON."
            if language == "en-US"
            else "请生成 3 个中文金融投资分析建议问题，以 JSON 格式输出。"
        )
        flavors = [
            "China A-share technology leaders",
            "China A-share consumer blue chips",
            "China A-share bank and finance stocks",
            "Hong Kong technology stocks",
            "US mega-cap technology stocks",
            "cross-market stock comparisons",
        ] if language == "en-US" else _ANALYSIS_FLAVORS
        expected_count = 3
    else:
        system_prompt = _MACRO_SYSTEM_EN if language == "en-US" else _MACRO_SYSTEM
        user_prompt = (
            "Generate 4 English macro or cross-market research questions as JSON."
            if language == "en-US"
            else "请生成 4 个中文宏观经济/市场洞察问题，以 JSON 格式输出。"
        )
        flavors = [
            "rates and central banks",
            "geopolitical risk",
            "commodity prices and inflation",
            "crypto and digital assets",
            "global market valuation",
            "risk appetite and liquidity",
        ] if language == "en-US" else _MACRO_FLAVORS
        expected_count = 4

    questions = _call_llm_for_suggestions(
        system_prompt,
        user_prompt,
        flavors,
        expected_count,
        question_type,
        language,
        history_key=f"pregen:{question_type}:{language}",
    )
    return questions or _FALLBACKS[(question_type, language)]


def pregenerate(slots: int = 4, output_path: str = _DEFAULT_OUTPUT) -> dict:
    """Generate all suggestion sets and write to JSON file.

    Returns the generated payload dict.
    """
    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_ts": time.time(),
        "slots_count": slots,
        "slots": {},
    }

    for qtype, lang in _TYPES:
        cache_key = qtype if lang == "zh-CN" else f"{qtype}:{lang}"
        slot_results: list[list[str]] = []
        for slot_idx in range(slots):
            logger.info("Generating slot %d/%d for %s ...", slot_idx + 1, slots, cache_key)
            try:
                questions = _generate_one_set(qtype, lang)
                slot_results.append(questions)
                logger.info("  -> %d questions: %s", len(questions), questions)
            except Exception as exc:
                logger.warning("  -> Failed: %s, using fallback", exc)
                slot_results.append(_FALLBACKS[(qtype, lang)])
        payload["slots"][cache_key] = slot_results

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write atomically (write to tmp then rename)
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)

    logger.info("Wrote pregenerated suggestions to %s", output_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate suggestion questions")
    parser.add_argument(
        "--slots", type=int, default=4,
        help="Number of time-slot batches per type (default: 4, one per 6h)",
    )
    parser.add_argument(
        "--output", type=str, default=_DEFAULT_OUTPUT,
        help=f"Output JSON file path (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    start = time.time()
    payload = pregenerate(slots=args.slots, output_path=args.output)
    elapsed = time.time() - start

    total_sets = sum(len(v) for v in payload["slots"].values())
    logger.info(
        "Done in %.1fs — %d types × %d slots = %d sets total",
        elapsed, len(payload["slots"]), args.slots, total_sets,
    )


if __name__ == "__main__":
    main()
