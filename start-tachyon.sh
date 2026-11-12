#!/usr/bin/env bash
# ==========================================================================
#  Tachyon Server - Startskript fuer Linux / start script for Linux
#
#  - AOT-Start-Cache: Start in ca. 3 s. Nach einem Update startet Tachyon sofort
#    ohne Cache (ca. 7 s) und erstellt ihn im Hintergrund neu
#  - dynamischer RAM: startet mit RAM_MIN, holt sich bei Bedarf bis RAM_MAX
#    und gibt freien Speicher im Leerlauf wieder ans System zurueck
#  - Schlafmodus: ohne Spieler legt sich der Server schlafen (RAM komplett frei)
#    und wacht auf, sobald jemand joint (tachyon.yml: sleep-mode)
#  - Sprache, EULA usw. fragt Tachyon beim ersten Start selbst
#
#  Beispiel: RAM_MAX=8G CPU_MAX=4 ./start-tachyon.sh
# ==========================================================================
set -uo pipefail

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
# Schlafmodus: nur mit diesem Skript kann der Server wieder geweckt werden
SLEEP=(-Dtachyon.sleepLauncher=true)
# Waechter waehrend des Schlafs: winziges Java ohne JIT, ca. 30-40 MB RAM
WATCH=(-Xms4m -Xmx16m -XX:+UseSerialGC -Xint -XX:-UsePerfData -Xss256k -XX:MaxMetaspaceSize=24m)

command -v "$JAVA" >/dev/null || { msg "[FEHLER] Java 25+ nicht gefunden." "[ERROR] Java 25+ not found."; exit 1; }
[[ -f "$JAR" ]] || { msg "[FEHLER] $JAR nicht gefunden." "[ERROR] $JAR not found."; exit 1; }

# Bibliotheken entpacken, wenn die Jar neu/aktualisiert ist
if [[ ! -f tachyon-libs/tachyon-launch.args || "$JAR" -nt tachyon-libs/tachyon-launch.args ]]; then
  msg "[INFO] Entpacke Bibliotheken..." "[INFO] Unpacking libraries..."
  "$JAVA" -Xmx512m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -DbundlerMainClass= -jar "$JAR"
fi
if [[ ! -f tachyon-libs/tachyon-launch.args ]]; then
  exec "$JAVA" "${FLAGS[@]}" -jar "$JAR" nogui
fi

# Java im Vordergrund laufen lassen, aber Stop-Signale (Docker, Panels, systemd) sauber weiterreichen
CHILD=0; STOPPING=0
trap 'STOPPING=1; [[ $CHILD != 0 ]] && kill -TERM "$CHILD" 2>/dev/null' TERM INT
run() {
  "$@" <&0 &
  CHILD=$!
  local rc
  while :; do
    wait "$CHILD"; rc=$?
    kill -0 "$CHILD" 2>/dev/null || break
  done
  CHILD=0
  return $rc
}

while :; do
  # Start-Cache (AOT) gueltig, solange Jar und JVM-Einstellungen gleich bleiben.
  # Sonst startet Tachyon sofort ohne Cache und erstellt ihn danach im Hintergrund.
  AOTSIG="$(stat -c '%s %Y' "$JAR" 2>/dev/null || stat -f '%z %m' "$JAR") ${FLAGS[*]}"
  if [[ -s tachyon.aot && "$(cat tachyon.aot.sig 2>/dev/null)" == "$AOTSIG" ]]; then
    run "$JAVA" "${FLAGS[@]}" "${SLEEP[@]}" -XX:AOTCache=tachyon.aot @tachyon-libs/tachyon-launch.args nogui
  else
    echo "$AOTSIG" > tachyon-libs/aot.wanted
    run "$JAVA" "${FLAGS[@]}" "${SLEEP[@]}" -Dtachyon.aotTrain=true @tachyon-libs/tachyon-launch.args nogui
  fi
  RC=$?
  # 75 = Server hat sich schlafen gelegt -> Waechter starten, beim Join wieder hochfahren
  [[ $RC == 75 && $STOPPING == 0 ]] || exit $RC
  run "$JAVA" "${WATCH[@]}" -jar "$JAR" --tachyon-sleep
  [[ $? == 10 && $STOPPING == 0 ]] || exit 0
done
