#!/bin/bash
# Install pre-commit hook: run this once after cloning
cp scripts/pre-commit-hook .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
echo "Pre-commit hook installed."
