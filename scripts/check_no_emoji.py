#!/usr/bin/env python3
"""Check for emoji characters in CLI output code paths.

Fails if any print()/click.echo()/format() output contains emoji characters.
This prevents GBK UnicodeEncodeError on Windows terminals.

Run: python scripts/check_no_emoji.py
Exit code 0 = clean, 1 = emojis found.
"""
import re
import sys
from pathlib import Path

# Emoji ranges (covers all common emoji blocks)
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001F9FF"   # Misc Symbols and Pictographs
    "\U00002600-\U000027BF"   # Misc Symbols, Dingbats
    "\U0000FE00-\U0000FE0F"   # Variation Selectors
    "\U0000200D"              # Zero Width Joiner
    "\U00002300-\U000023FF"   # Misc Technical
    "\U00002B50\U00002B55"    # Star, Circle
    "\U000025AA-\U000025FE"   # Geometric Shapes
    "\U00002194-\U000021AA"   # Arrows
    "\U000020E3"              # Combining Enclosing Keycap
    "\U00002702-\U000027B0"   # Dingbats
    "]+",
    re.UNICODE,
)

# Patterns that produce console output
OUTPUT_PATTERNS = re.compile(
    r"(?:print|click\.echo)\s*\("  # print() or click.echo()
    r"|f['\"]"                      # f-strings
    r"|\+.*['\"]"                   # string concat
    r"|format\s*\("                 # .format()
)

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def scan() -> list[tuple[str, int, str, list[str]]]:
    """Scan source files for emojis in output code."""
    hits: list[tuple[str, int, str, list[str]]] = []
    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file) or "venv" in str(py_file):
            continue
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            # Only check lines that look like they produce output
            if not OUTPUT_PATTERNS.search(stripped):
                continue
            emojis = EMOJI_RE.findall(stripped)
            if emojis:
                rel = py_file.relative_to(SRC_DIR.parent)
                hits.append((str(rel), lineno, stripped[:120], emojis))
    return hits


def main() -> int:
    hits = scan()
    if not hits:
        print("OK: No emoji in output code.")
        return 0
    print(f"FAIL: Found {len(hits)} emoji(s) in output code:")
    for path, lineno, code, emojis in hits:
        print(f"  {path}:{lineno}")
        print(f"    {code}")
        print(f"    -> {emojis}")
    print("\nWindows GBK terminals cannot encode emoji. Use ASCII alternatives.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
