#!/usr/bin/env bash
# ==========================================================================
#  Tachyon Server - Startskript fuer Linux / start script for Linux
#
#  - AOT-Cache (Neustarts ca. 3x schneller), G1-Tuning
#  - dynamischer RAM: startet mit RAM_MIN, holt sich bei Bedarf bis RAM_MAX
#    und gibt freien Speicher im Leerlauf wieder ans System zurueck
#  - Sprache, EULA usw. fragt Tachyon beim ersten Start selbst
#
#  Beispiel: RAM_MAX=8G CPU_MAX=4 ./start-tachyon.sh
# ==========================================================================
set -euo pipefail

JAR="${JAR:-tachyon-26.3.jar}"
RAM_MIN="${RAM_MIN:-1G}"
RAM_MAX="${RAM_MAX:-4G}"
CPU_MAX="${CPU_MAX:-0}"          # 0 = alle Kerne
JAVA="${JAVA:-${JAVA_HOME:+$JAVA_HOME/bin/}java}"   # Java 25 oder neuer

cd "$(dirname "$0")"
L=de; grep -qx "language: en" tachyon.yml 2>/dev/null && L=en
msg() { if [[ "$L" == en ]]; then echo "$2"; else echo "$1"; fi; }

FLAGS=(-Xms"$RAM_MIN" -Xmx"$RAM_MAX" -XX:G1PeriodicGCInterval=30000 -XX:MinHeapFreeRatio=10 -XX:MaxHeapFreeRatio=30
  -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions
  -XX:+DisableExplicitGC -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M
  -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4
  -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90
  -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem
  -XX:MaxTenuringThreshold=1 -XX:+UseCompactObjectHeaders
  --enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow)
[[ "$CPU_MAX" != 0 ]] && FLAGS+=(-XX:ActiveProcessorCount="$CPU_MAX")

# Nur fuers AOT-Training: Objekte streamen statt mappen (sonst scheitert das Training manchmal)
AOTTRAIN=(-Xlog:aot*=error -Xlog:cds*=error -XX:+UnlockDiagnosticVMOptions -XX:+AOTStreamableObjects -Dtachyon.aotTraining=true -XX:AOTCacheOutput=tachyon.aot)

command -v "$JAVA" >/dev/null || { msg "[FEHLER] Java 25+ nicht gefunden." "[ERROR] Java 25+ not found."; exit 1; }
[[ -f "$JAR" ]] || { msg "[FEHLER] $JAR nicht gefunden." "[ERROR] $JAR not found."; exit 1; }

# Bibliotheken entpacken, wenn die Jar neu/aktualisiert ist
if [[ ! -f tachyon-libs/tachyon-launch.args || "$JAR" -nt tachyon-libs/tachyon-launch.args ]]; then
  msg "[INFO] Entpacke Bibliotheken..." "[INFO] Unpacking libraries..."
  "$JAVA" "${FLAGS[@]}" -DbundlerMainClass= -jar "$JAR"
fi
if [[ ! -f tachyon-libs/tachyon-launch.args ]]; then
  exec "$JAVA" "${FLAGS[@]}" -jar "$JAR" nogui
fi

# AOT-Cache trainieren: erst wenn die Welt existiert, erneut nach Jar-Update oder geaenderten JVM-Flags
LEVEL="$(grep -E '^level-name=' server.properties 2>/dev/null | cut -d= -f2- || true)"
LEVEL="${LEVEL:-world}"
if [[ -f "$LEVEL/level.dat" ]]; then
  if [[ ! -s tachyon.aot || "$JAR" -nt tachyon.aot || "$(cat tachyon.aot.flags 2>/dev/null)" != "${FLAGS[*]}" ]]; then
    msg "[INFO] Einmaliges Training des Start-Caches (AOT), ca. 40 s - der Server faehrt kurz hoch und beendet sich wieder..." \
        "[INFO] One-time training of the startup cache (AOT), about 40 s - the server starts briefly and stops again..."
    rm -f tachyon.aot
    "$JAVA" "${FLAGS[@]}" "${AOTTRAIN[@]}" @tachyon-libs/tachyon-launch.args nogui </dev/null 2>tachyon-libs/aot-training.log || true
    if [[ ! -s tachyon.aot ]]; then
      msg "[INFO] Volles Training nicht moeglich - nutze sichere Variante..." "[INFO] Full training not possible - using the safe variant..."
      rm -f tachyon.aot
      "$JAVA" "${FLAGS[@]}" "${AOTTRAIN[@]}" -XX:-AOTClassLinking @tachyon-libs/tachyon-launch.args nogui </dev/null 2>tachyon-libs/aot-training.log || true
    fi
    if [[ -s tachyon.aot ]]; then echo "${FLAGS[*]}" > tachyon.aot.flags; else rm -f tachyon.aot; fi
  fi
fi

if [[ -s tachyon.aot ]]; then
  exec "$JAVA" "${FLAGS[@]}" -XX:AOTCache=tachyon.aot @tachyon-libs/tachyon-launch.args nogui
else
  exec "$JAVA" "${FLAGS[@]}" @tachyon-libs/tachyon-launch.args nogui
fi
