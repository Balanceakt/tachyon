#!/usr/bin/env bash
# ==========================================================================
#  Tachyon Server - Startskript fuer Linux-Server
#  Gleiche Logik wie start.bat: AOT-Cache (schnelle Neustarts), G1-Tuning.
# ==========================================================================
set -euo pipefail

JAR="${JAR:-tachyon-26.3.jar}"
RAM="${RAM:-4G}"
JAVA="${JAVA:-java}"   # Java 25 oder neuer

cd "$(dirname "$0")"

FLAGS=(-Xms"$RAM" -Xmx"$RAM"
  -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions
  -XX:+DisableExplicitGC -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M
  -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4
  -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90
  -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem
  -XX:MaxTenuringThreshold=1 -XX:+UseCompactObjectHeaders
  --enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow)

# Nur fuers AOT-Training: Objekte streamen statt mappen (sonst scheitert das Training manchmal)
AOTTRAIN=(-Xlog:aot*=error -Xlog:cds*=error -XX:+UnlockDiagnosticVMOptions -XX:+AOTStreamableObjects -Dtachyon.aotTraining=true -XX:AOTCacheOutput=tachyon.aot)

if ! grep -qi "eula=true" eula.txt 2>/dev/null; then
  echo "[INFO] Erster Start: Server legt eula.txt und Konfiguration an..."
  "$JAVA" "${FLAGS[@]}" -jar "$JAR" nogui || true
  if ! grep -qi "eula=true" eula.txt 2>/dev/null; then
    echo "[INFO] Bitte die Minecraft-EULA lesen (https://aka.ms/MinecraftEULA), in eula.txt 'eula=true' setzen und erneut starten."
    exit 0
  fi
fi

# Bibliotheken entpacken, wenn die Jar neu/aktualisiert ist
if [[ ! -f tachyon-libs/tachyon-launch.args || "$JAR" -nt tachyon-libs/tachyon-launch.args ]]; then
  echo "[INFO] Entpacke Bibliotheken..."
  "$JAVA" "${FLAGS[@]}" -DbundlerMainClass= -jar "$JAR"
fi

if [[ ! -f tachyon-libs/tachyon-launch.args ]]; then
  echo "[WARNUNG] Schnellstart nicht moeglich - starte klassisch."
  exec "$JAVA" "${FLAGS[@]}" -jar "$JAR" nogui
fi

# AOT-Cache trainieren: erst wenn die Welt existiert, erneut nach Jar-Update oder geaenderten JVM-Flags
LEVEL="$(grep -E '^level-name=' server.properties 2>/dev/null | cut -d= -f2- || true)"
LEVEL="${LEVEL:-world}"
if [[ -f "$LEVEL/level.dat" ]]; then
  if [[ ! -s tachyon.aot || "$JAR" -nt tachyon.aot || "$(cat tachyon.aot.flags 2>/dev/null)" != "${FLAGS[*]}" ]]; then
    echo "[INFO] Einmaliges Training des Start-Caches (AOT), ca. 30-60 s - der Server faehrt kurz hoch und beendet sich wieder..."
    rm -f tachyon.aot
    "$JAVA" "${FLAGS[@]}" "${AOTTRAIN[@]}" @tachyon-libs/tachyon-launch.args nogui </dev/null || true
    if [[ ! -s tachyon.aot ]]; then
      echo "[INFO] Volles Training nicht moeglich - nutze sichere Variante..."
      rm -f tachyon.aot
      "$JAVA" "${FLAGS[@]}" "${AOTTRAIN[@]}" -XX:-AOTClassLinking @tachyon-libs/tachyon-launch.args nogui </dev/null || true
    fi
    if [[ -s tachyon.aot ]]; then echo "${FLAGS[*]}" > tachyon.aot.flags; else rm -f tachyon.aot; fi
  fi
fi

echo "[INFO] Tachyon startet..."
if [[ -s tachyon.aot ]]; then
  exec "$JAVA" "${FLAGS[@]}" -XX:AOTCache=tachyon.aot @tachyon-libs/tachyon-launch.args nogui
else
  exec "$JAVA" "${FLAGS[@]}" @tachyon-libs/tachyon-launch.args nogui
fi
