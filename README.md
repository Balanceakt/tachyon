<p align="center">
  <img src="assets/banner.jpg" alt="Tachyon" width="100%">
</p>

<h1 align="center">⚡ Tachyon</h1>

<p align="center">
  <b>Minecraft-Server für 26.3 – ohne Lags, mit Turbo-Start und eingebautem World-Manager.</b><br>
  Ein Fork von Spigot, der die Stellen umbaut, an denen der Server dich warten lässt.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Minecraft-26.3-7ee0c3?style=for-the-badge">
  <img src="https://img.shields.io/badge/Java-25%2B-c9a7ff?style=for-the-badge">
  <img src="https://img.shields.io/badge/Basis-Spigot-8a8fa3?style=for-the-badge">
  <img src="https://img.shields.io/badge/Plugins-kompatibel-7ee0c3?style=for-the-badge">
</p>

---

## Warum Tachyon?

Du kennst das: Jemand erstellt eine neue Welt und **der komplette Server friert ein**. Alle Spieler stehen still, Chat hängt, Mobs bleiben stehen. Oder du startest neu und wartest, während in der Konsole hunderte Zeilen durchrattern.

Tachyon räumt damit auf – gemessen, nicht geschätzt:

<p align="center">
  <img src="assets/benchmark.png" alt="Benchmark Tachyon vs Spigot" width="100%">
</p>

| | Spigot 26.3 | **Tachyon** | |
|---|---:|---:|---|
| Server-Hänger beim Erstellen einer Welt | 545 ms | **52 ms** | **10× weniger** |
| Neustart bis „Done“ | 7,5 s | **2,4 s** | **3× schneller** |
| Erster Start bis „Done“ | 10,4 s | **6,5 s** | **1,6× schneller** |
| TPS während eine Welt erstellt wird | 20 | **20** | Server läuft einfach weiter |

> Die Zahlen kommen aus [`benchmark/benchmark.py`](benchmark/benchmark.py) – lass es auf deinem Rechner laufen und überzeug dich selbst.

---

## Was Tachyon besser macht

### 🌍 Welten erstellen ohne Freeze
Spigot sucht beim Erstellen einer Welt den Spawnpunkt, indem es **bis zu 121 Chunks direkt auf dem Haupt-Thread generiert**. Solange das läuft, tickt der Server nicht – für alle Spieler.

Tachyon legt die Welt sofort an und sucht den Spawn **im Hintergrund** über Chunk-Tickets. Die eigentliche Generierung läuft auf den Worldgen-Threads, der Server tickt währenddessen ganz normal mit 20 TPS weiter. Sobald der Spawnbereich fertig ist, gilt die Welt als bereit.

### 🧭 World-Manager eingebaut – ohne Plugin
Kein Multiverse nötig. Alles direkt im Server:

| Befehl | Was passiert |
|---|---|
| `/wm create <name> [normal\|flat\|amplified\|large_biomes\|void\|nether\|end] [seed]` | Neue Welt erstellen – ohne Lag |
| `/wm load <name>` | Vorhandenen Weltordner laden |
| `/wm unload <name> [nosave]` | Welt entladen (Spieler werden sicher rausgebracht) |
| `/wm delete <name> confirm` | Welt löschen – die Dateiarbeit läuft im Hintergrund |
| `/wm clone <quelle> <ziel>` | Welt kopieren, perfekt für Minigame-Vorlagen |
| `/wm tp <name> [spieler]` | Teleport – lädt die Welt bei Bedarf und wartet, bis sie bereit ist |
| `/wm pregen <welt> <radius>` | Welt im Hintergrund **vorgenerieren** |
| `/wm list` · `/wm info <name>` · `/wm setspawn` · `/wm autoload <name> <true\|false>` | Übersicht und Verwaltung |

Geladene Welten merkt sich Tachyon in `tachyon.yml` und lädt sie nach einem Neustart automatisch – gestaffelt, nicht alle auf einmal.

### 🗺️ Pregenerator, der sich selbst bremst
`/wm pregen world 5000` generiert die Welt im Voraus, damit beim Erkunden nichts mehr ruckelt. Der Pregenerator **pausiert automatisch**, sobald ein Tick länger als 50 ms dauert – Spieler haben immer Vorrang.

### 🚀 Turbo-Start mit Java-AOT-Cache
`Start-Tachyon.bat` / `start-tachyon.sh` nutzen den **AOT-Cache von Java 25+** (Project Leyden). Beim ersten Mal trainiert Tachyon den Cache einmalig (~40 s), danach lädt Java alle Server-Klassen fertig gelinkt aus dem Cache: **Neustart in ~2,5 s statt ~7,5 s**.

Damit das überhaupt geht, startet Tachyon den Server direkt über den Classpath statt über den Spigot-Bootstrap-Classloader – den kann Javas Cache nämlich nicht cachen.

### ⏱️ Kein Warten beim Hochfahren
- **Schnellstart:** Der Server wartet beim Start nicht mehr auf die synchrone Spawnsuche, sondern erledigt sie in den ersten Sekunden nach „Done“ im Hintergrund.
- **Kein Hashen bei jedem Start:** Spigot prüft bei jedem Start sämtliche Bibliotheken per SHA-256. Tachyon merkt sich Größe und Datum und prüft nur, was sich geändert hat.
- **Paralleler Crash-Report-Preload:** Minecraft baut beim Start einen Vorrats-Absturzbericht inklusive langsamer Hardware-Abfrage. Läuft bei Tachyon parallel zum restlichen Start.
- **Kein 20-Sekunden-Zwangswarten:** Spigot wartet bei Builds, die älter als 4 Wochen sind, bei jedem Start 20 Sekunden. Tachyon gibt nur einen Hinweis aus.

### 🔌 Schnelleres Plugin-Laden
- Die `plugin.yml` aller Plugins wird **parallel** gelesen.
- Bibliotheken aus `libraries:` werden für **alle Plugins gleichzeitig** aufgelöst und heruntergeladen – statt Plugin für Plugin nacheinander.
- Reihenfolge, Abhängigkeiten und Fehlermeldungen bleiben exakt wie bei Spigot. Klappt das parallele Laden mal nicht, fällt Tachyon auf den normalen Weg zurück.

### 🖥️ Konsole, die Spaß macht
- Farbiges Banner und **ein einziger Ladebalken**, der sich live aktualisiert – statt hunderter Log-Zeilen.
- Beim Start erscheinen nur **Warnungen und Fehler**. Alles andere landet wie gewohnt vollständig in `logs/latest.log`.
- Am Ende eine **Zusammenfassung**: Startzeit, Port, Slots, Whitelist, Welten, Plugins, RAM und ob es Probleme gab.
- Danach eingefärbte Logs: Joins grün, Leaves gelb, Befehle lila, Warnungen gelb, Fehler rot.
- In Hosting-Panels (keine echte Konsole) automatisch schlichter Text. `-Dtachyon.verboseStartup=true` bringt das klassische Log zurück.

### 🛠️ Fixes und Aufräumarbeiten
- **Bugfix:** Spigot wirft beim Stoppen `AsyncStructureSpawnEvent cannot be triggered asynchronously from primary server thread`, wenn gerade noch Chunks generiert werden – das Herunterfahren schlägt dann fehl. Behoben.
- **Whitelist standardmäßig aus:** Minecraft 26.x schaltet sie bei neuen Servern ein – dann kommt erstmal niemand rein.
- **Sinnvolle Standards:** 100 Slots, MOTD „Powered by Tachyon“, eigenes Server-Icon.
- **MCStats raus:** Das uralte Statistik-System von 2013 meldet sich nicht mehr im Hintergrund.
- **Startdateien ohne veraltete JVM-Flags:** `ParallelRefProcEnabled` (in Java 26 abgekündigt) entfernt, dafür **Compact Object Headers** aus Java 25 für weniger RAM pro Objekt.

---

## Ehrlich gesagt: was *nicht* schneller wurde

Tachyon soll nicht mehr versprechen, als es hält:

- **Tick-Zeit (MSPT), TPS und RAM im normalen Betrieb** sind praktisch gleich wie bei Spigot. Der Main-Thread macht dieselbe Arbeit – Tachyon nimmt ihm nur die blockierenden Brocken ab.
- **Event-System:** Ein Umbau ohne Reflection brachte auf Java 26 nichts Messbares und wurde deshalb wieder entfernt.
- **„Welt bereit“** dauert bei Tachyon etwas länger (1,5–2 s statt 0,5 s), weil der Spawnbereich vorgeladen wird – dafür läuft der Server währenddessen ohne Hänger weiter.

---

## Installation

> **Warum gibt es keine fertige Jar zum Download?**
> Die Server-Jar enthält den Minecraft-Server-Code von Mojang, und den darf niemand weiterverbreiten. Genau deshalb gibt es bei Spigot BuildTools. Tachyon macht es genauso: Du baust die Jar mit einem Doppelklick selbst – das Ergebnis ist identisch.

### Voraussetzungen
- **Java 25 oder neuer** (z. B. [Adoptium](https://adoptium.net))
- **Git** ([git-scm.com](https://git-scm.com))
- ca. 5–10 Minuten und Internet

### Bauen
```bash
git clone https://github.com/Balanceakt/tachyon.git
cd tachyon
```
- **Windows:** `build-tachyon.bat` doppelklicken
- **Linux/macOS:** `./build-tachyon.sh`

Das Skript lädt BuildTools, baut Spigot 26.3 (Build 4664), spielt die Tachyon-Patches ein und legt `tachyon-26.3.jar` daneben.

### Starten
1. `tachyon-26.3.jar` und `Start-Tachyon.bat` (bzw. `start-tachyon.sh`) in deinen Server-Ordner legen.
2. Starten. Beim ersten Start wird `eula.txt` angelegt: Minecraft-EULA lesen, `eula=true` setzen, nochmal starten.
3. Ab dem zweiten Start trainiert Tachyon einmalig den Start-Cache – danach geht's in Sekunden.

RAM einstellen: oben in `Start-Tachyon.bat` die Zeile `set RAM=4G` anpassen (bei `start-tachyon.sh`: `RAM=8G ./start-tachyon.sh`).

**Plugins:** Tachyon ist ein Spigot-Fork – Bukkit- und Spigot-Plugins laufen wie gewohnt.

---

## Konfiguration (`tachyon.yml`)

```yaml
startup:
  fast-start: true                          # nicht auf die Spawnsuche warten
world-manager:
  fast-world-creation-for-plugins: false    # true = auch Plugin-Welten (z.B. Multiverse) ohne Hänger
  spawn-preload-radius: 2                   # Chunks um den Spawn, die vor "bereit" geladen werden
  autoload-interval-ticks: 20               # Abstand beim automatischen Laden nach dem Start
  pregen-parallel-chunks: 40                # gleichzeitige Chunks bei /wm pregen
```

---

## Benchmark selbst ausführen

```bash
cd benchmark
python benchmark.py --original pfad/zu/spigot-26.3.jar --tachyon pfad/zu/tachyon-26.3.jar
```

Startet beide Server nacheinander in eigenen Testordnern (gleicher Seed, gleiche Einstellungen) und misst Startzeiten, Hänger beim Welterstellen, Tick-Zeiten, Events und RAM. Am Ende gibt es eine Tabelle und einen Bericht in `benchmark/ergebnisse/`.

---

## Aufbau des Repos

| Pfad | Inhalt |
|---|---|
| `patches/tachyon-server.patch` | Alle Änderungen am Server (World-Manager, Konsole, Start, Fixes) |
| `patches/tachyon-api.patch` | Änderungen an der Spigot-API (paralleles Plugin-Laden, Event-Fix) |
| `build-tachyon.bat` / `.sh` | Baut die Jar lokal |
| `Start-Tachyon.bat` / `start-tachyon.sh` | Startdateien mit AOT-Cache und G1-Tuning |
| `benchmark/` | Vergleichs-Benchmark inkl. Mess-Plugin |

---

## Lizenz & Hinweise

Die Patches bauen auf [Spigot](https://www.spigotmc.org) / CraftBukkit / Bukkit auf und stehen wie diese unter der **GPL-3.0** (siehe [LICENSE](LICENSE)).
Tachyon ist kein offizielles Produkt von Mojang, Microsoft oder SpigotMC und steht mit ihnen in keiner Verbindung. Minecraft ist eine Marke von Mojang AB.
