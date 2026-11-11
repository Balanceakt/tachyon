#!/usr/bin/env bash
# ==========================================================================
#  Tachyon bauen (Linux / macOS)
#
#  Baut tachyon-26.3.jar lokal:
#   1. laedt BuildTools (offizielles Spigot-Werkzeug)
#   2. baut Spigot 26.3 (Build 4664) aus dem Quellcode
#   3. spielt die Tachyon-Patches ein
#   4. baut tachyon-26.3.jar
#
#  Voraussetzungen: Java 25+, Git, curl. Dauer: ca. 5-10 Minuten.
# ==========================================================================
set -euo pipefail

REV=4664
ROOT="$(cd "$(dirname "$0")" && pwd)"
JAVA="${JAVA_HOME:+$JAVA_HOME/bin/}java"

command -v "$JAVA" >/dev/null || { echo "[FEHLER] Java 25+ nicht gefunden."; exit 1; }
command -v git >/dev/null || { echo "[FEHLER] Git nicht gefunden."; exit 1; }

mkdir -p "$ROOT/build"
cd "$ROOT/build"

echo "[1/4] Lade BuildTools..."
curl -fsSL -o BuildTools.jar https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar

echo "[2/4] Baue Spigot 26.3 (Build $REV) - das dauert ein paar Minuten..."
"$JAVA" -jar BuildTools.jar --rev "$REV" --compile spigot --disable-java-check > buildtools.log 2>&1 \
  || { echo "[FEHLER] BuildTools fehlgeschlagen - siehe build/buildtools.log"; exit 1; }

echo "[3/4] Spiele Tachyon-Patches ein..."
for part in API:tachyon-api.patch Server:tachyon-server.patch; do
  dir="Spigot/Spigot-${part%%:*}"
  ( cd "$dir" && git clean -fdq src && git checkout -q -- . && git apply --ignore-whitespace "$ROOT/patches/${part##*:}" )
done

MVN="$(ls -d "$ROOT"/build/apache-maven-*/ | head -1)bin/mvn"
echo "[4/4] Baue tachyon-26.3.jar..."
( cd Spigot/Spigot-API && "$MVN" -q -DskipTests install )
( cd Spigot/Spigot-Server && "$MVN" -q -DskipTests package )
cp Spigot/Spigot-Server/target/spigot-26.3-R0.1-SNAPSHOT-bootstrap.jar "$ROOT/tachyon-26.3.jar"

echo
echo "Fertig: tachyon-26.3.jar  -  starten mit ./start-tachyon.sh"
