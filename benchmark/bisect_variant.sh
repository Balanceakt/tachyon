#!/usr/bin/env bash
# Baut eine Tachyon-Variante: kompletter Tachyon-Patch, aber die angegebenen Dateien auf Spigot-Original zurueckgesetzt,
# und misst sie mit bisect_run.py.   Benutzung: bisect_variant.sh <name> <datei> [datei ...]
set -e
NAME="$1"; shift
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
W="${BISECT_DIR:?BISECT_DIR auf eine git worktree von Spigot-Server setzen}"
PATCH="$SCRIPT_DIR/../patches/tachyon-server.patch"

cd "$W"
git checkout -q -- . && git clean -fdq src
git apply --ignore-whitespace "$PATCH"
for f in "$@"; do git checkout -q -- "$f"; done
if [ -n "$EXTRA_CMD" ]; then eval "$EXTRA_CMD"; fi
${MVN:-mvn} -o -q -DskipTests package 2>&1 | grep ERROR | head -5 || true
cp target/spigot-26.3-R0.1-SNAPSHOT-bootstrap.jar "$NAME.jar"
cd "$SCRIPT_DIR"
PYTHONIOENCODING=utf-8 python -u bisect_run.py "$(cygpath -w "$W/$NAME.jar")" "$NAME" 2 2>&1 | grep RESULTAT
