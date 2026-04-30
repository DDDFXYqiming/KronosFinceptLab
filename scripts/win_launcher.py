"""Windows-side forecast launcher.

Sets up the correct Windows paths for Kronos model resolution,
then delegates to the CLI forecast command.

Usage (from WSL):
    /mnt/c/Users/39795/AppData/Local/Programs/Python/Python313/python.exe \\
        scripts/win_launcher.py forecast --symbol 601398 --pred-len 5
"""
import os
import sys

# ── Resolve Windows-style project root ──
# __file__ = E:\AI_Projects\KronosFinceptLab\scripts\win_launcher.py
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_kronos_repo = os.path.join(_project_root, "external", "Kronos")
_src_dir = os.path.join(_project_root, "src")

# ── Set environment variables (Windows paths) ──
os.environ["KRONOS_REPO_PATH"] = _kronos_repo
os.environ["HF_HOME"] = os.path.join(_project_root, "external")

# ── Ensure paths are on sys.path ──
for p in [_kronos_repo, _src_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Delegate to CLI ──
from kronos_fincept.cli.main import cli

if __name__ == "__main__":
    sys.exit(cli())
