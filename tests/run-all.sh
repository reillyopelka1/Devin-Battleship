#!/usr/bin/env bash
# Logic + 30 simulated games, then UI tests driven through Chrome via CDP (localhost:29229).
set -e
cd "$(dirname "$0")/.."
node tests/run-tests.js
python3 tests/ui-test.py
