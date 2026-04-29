#!/usr/bin/env bash
# install_bridge.sh — Install KronosFinceptLab bridge into FinceptTerminal
#
# Usage:
#   ./scripts/install_bridge.sh /path/to/FinceptTerminal
#   ./scripts/install_bridge.sh /path/to/FinceptTerminal --symlink
#
# What it does:
#   1. Copies (or symlinks) kronos_forecast.py into FinceptTerminal's scripts dir
#   2. Installs the kronos_fincept Python package into the active environment
#   3. Optionally configures KRONOS_REPO_PATH

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FINCEPT_ROOT="${1:-}"
MODE="${2:---copy}"

if [[ -z "$FINCEPT_ROOT" ]]; then
    echo "Usage: $0 /path/to/FinceptTerminal [--copy|--symlink]"
    exit 1
fi

FINCEPT_SCRIPTS="$FINCEPT_ROOT/fincept-qt/scripts"
if [[ ! -d "$FINCEPT_SCRIPTS" ]]; then
    echo "Error: FinceptTerminal scripts directory not found at: $FINCEPT_SCRIPTS"
    echo "Make sure you point to the FinceptTerminal repository root."
    exit 1
fi

BRIDGE_SRC="$SCRIPT_DIR/integrations/fincept_terminal/scripts/kronos_forecast.py"
BRIDGE_DST="$FINCEPT_SCRIPTS/kronos_forecast.py"

echo "=== KronosFinceptLab Bridge Installer ==="
echo ""

# Step 1: Copy or symlink bridge script
if [[ "$MODE" == "--symlink" ]]; then
    ln -sf "$BRIDGE_SRC" "$BRIDGE_DST"
    echo "[OK] Symlinked bridge script: $BRIDGE_DST -> $BRIDGE_SRC"
else
    cp "$BRIDGE_SRC" "$BRIDGE_DST"
    echo "[OK] Copied bridge script to: $BRIDGE_DST"
fi

# Step 2: Install the Python package
echo "[..] Installing kronos_fincept package..."
pip install -e "$SCRIPT_DIR" -q 2>/dev/null || pip install -e "$SCRIPT_DIR"
echo "[OK] Package installed."

# Step 3: Check Kronos upstream
KRONOS_LOCAL="$SCRIPT_DIR/external/Kronos"
if [[ -d "$KRONOS_LOCAL/model" ]]; then
    echo "[OK] Kronos upstream found at: $KRONOS_LOCAL"
    echo "     Set KRONOS_REPO_PATH=$KRONOS_LOCAL for real inference."
else
    echo "[--] Kronos upstream not found at $KRONOS_LOCAL"
    echo "     Clone it: git clone https://github.com/shiyu-coder/Kronos.git $KRONOS_LOCAL"
    echo "     Or set KRONOS_REPO_PATH to your existing Kronos checkout."
fi

# Step 4: Verify bridge script is callable
echo ""
echo "[..] Verifying bridge script..."
TEST_INPUT='{"symbol":"TEST/USDT","timeframe":"1h","pred_len":1,"dry_run":true,"rows":[{"timestamp":"2026-01-01T00:00:00Z","open":100,"high":110,"low":90,"close":105}]}'
RESULT=$(echo "$TEST_INPUT" | python3 "$BRIDGE_DST" 2>/dev/null)
if echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['ok']==True" 2>/dev/null; then
    echo "[OK] Bridge script verified — returns valid JSON."
else
    echo "[FAIL] Bridge script verification failed."
    echo "       Output: $RESULT"
    exit 1
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "The bridge script is now available in FinceptTerminal at:"
echo "  $BRIDGE_DST"
echo ""
echo "FinceptTerminal's PythonRunner can call it as:"
echo "  PythonRunner::instance().run(\"kronos_forecast.py\", {\"--input\", \"request.json\"}, cb)"
echo ""
echo "For real Kronos inference, ensure KRONOS_REPO_PATH is set and torch is installed."
