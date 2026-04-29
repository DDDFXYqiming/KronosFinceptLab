#!/usr/bin/env python3
"""FinceptTerminal-compatible bridge script.

Copy or symlink this file into FinceptTerminal's fincept-qt/scripts directory.
It delegates to kronos_fincept.cli and preserves the stdout JSON contract.
"""

from __future__ import annotations

from kronos_fincept.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
