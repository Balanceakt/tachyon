@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  Tachyon Server - Startdatei (Start-Tachyon.bat)
REM
REM  - startet Tachyon mit Javas AOT-Cache (Neustarts ca. 2,5x schneller)
REM  - der Cache wird ab dem 2. Start einmalig automatisch trainiert
REM    (ca. 40 s, der Server faehrt dabei kurz hoch und beendet sich wieder)
REM  - nach einem Jar-Update oder geaenderten Einstellungen wird neu trainiert
REM  - optimierte G1-Garbage-Collector-Einstellungen gegen Lag-Spitzen
REM ==========================================================================

REM ---- Einstellungen -------------------------------------------------------
set JAR=tachyon-26.3.jar
set RAM=4G
REM Java 25 oder neuer wird benoetigt (JAVA_HOME oder java im PATH)
set JAVA=java
if defined JAVA_HOME set "JAVA=%JAVA_HOME%\bin\java.exe"
REM ---------------------------------------------------------------------------

cd /d "%~dp0"
title Tachyon Server

if not exist "%JAVA%" (
    where java >nul 2>nul && (set JAVA=java) || (
        echo [FEHLER] Kein Java gefunden. Bitte Java 25+ installieren oder JAVA in start.bat anpassen.
        pause
        exit /b 1
    )
)
if not exist "%JAR%" (
    echo [FEHLER] %JAR% nicht gefunden.
    pause
    exit /b 1
)

REM Speicher: Xms = Xmx, damit Java den Heap nicht staendig vergroessert/verkleinert
set MEM=-Xms%RAM% -Xmx%RAM%
REM G1-Tuning (bewaehrte Server-Flags) + Compact Object Headers (Java 25: weniger RAM pro Objekt)
set GC=-XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -XX:+UseCompactObjectHeaders
set FLAGS=%MEM% %GC% --enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow
REM Nur fuers AOT-Training: Objekte streamen statt mappen - noetig, damit das Training zuverlaessig klappt
set AOTTRAIN=-Xlog:aot*=error -Xlog:cds*=error -XX:+UnlockDiagnosticVMOptions -XX:+AOTStreamableObjects -Dtachyon.aotTraining=true -XX:AOTCacheOutput=tachyon.aot

REM Signatur der Jar (Groesse + Datum) - erkennt Updates ohne langsame Hilfsprogramme
for %%F in ("%JAR%") do set "JARSIG=%%~zF %%~tF"

REM ---- EULA ------------------------------------------------------------------
findstr /i /c:"eula=true" eula.txt >nul 2>nul
if errorlevel 1 (
    echo [INFO] Erster Start: Server legt eula.txt und Konfiguration an...
    "%JAVA%" %FLAGS% -jar "%JAR%" nogui
    findstr /i /c:"eula=true" eula.txt >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [INFO] Bitte die Minecraft-EULA lesen ^(https://aka.ms/MinecraftEULA^),
        echo        in eula.txt "eula=true" setzen und start.bat erneut starten.
        pause
        exit /b 0
    )
)

REM ---- Bibliotheken entpacken (nur wenn die Jar neu/aktualisiert ist) -------
set OLDSIG=
if exist "tachyon-libs\tachyon.jarsig" set /p OLDSIG=<"tachyon-libs\tachyon.jarsig"
if not exist "tachyon-libs\tachyon-launch.args" set OLDSIG=
if not "%OLDSIG%"=="%JARSIG%" (
    echo [INFO] Entpacke Bibliotheken...
    "%JAVA%" %FLAGS% -DbundlerMainClass= -jar "%JAR%"
    if not exist "tachyon-libs\tachyon-launch.args" (
        echo [WARNUNG] Schnellstart nicht moeglich - starte klassisch.
        goto classic
    )
    > "tachyon-libs\tachyon.jarsig" echo %JARSIG%
)

REM ---- AOT-Cache trainieren ---------------------------------------------------
REM Erst wenn die Welt existiert, erneut nach Jar-Update oder geaenderten JVM-Einstellungen.
set LEVEL=world
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"level-name=" server.properties 2^>nul') do set "LEVEL=%%b"
if not exist "%LEVEL%\level.dat" goto start

set "AOTSIG=%JARSIG% %FLAGS%"
set OLDAOT=
if exist tachyon.aot.sig set /p OLDAOT=<tachyon.aot.sig
call :validaot
if not exist tachyon.aot set OLDAOT=
if not "%OLDAOT%"=="%AOTSIG%" (
    echo ==========================================
    echo [INFO] Einmaliges Training des Start-Caches ^(AOT^), ca. 40 s...
    echo        Der Server faehrt kurz hoch und beendet sich wieder.
    echo ==========================================
    if exist tachyon.aot del /q tachyon.aot
    "%JAVA%" %FLAGS% %AOTTRAIN% @tachyon-libs\tachyon-launch.args nogui 2>"tachyon-libs\aot-training.log"
    call :validaot
    if not exist tachyon.aot (
        echo [INFO] Volles Training nicht moeglich - nutze sichere Variante...
        "%JAVA%" %FLAGS% %AOTTRAIN% -XX:-AOTClassLinking @tachyon-libs\tachyon-launch.args nogui 2>"tachyon-libs\aot-training.log"
        call :validaot
    )
    if exist tachyon.aot (
        > tachyon.aot.sig echo %AOTSIG%
    ) else (
        echo [WARNUNG] Start-Cache konnte nicht erstellt werden - Server startet ohne.
        if exist tachyon.aot.sig del /q tachyon.aot.sig
    )
)

:start
echo ==========================================
echo [INFO] Tachyon startet...
echo ==========================================
if exist tachyon.aot (
    "%JAVA%" %FLAGS% -XX:AOTCache=tachyon.aot @tachyon-libs\tachyon-launch.args nogui
) else (
    "%JAVA%" %FLAGS% @tachyon-libs\tachyon-launch.args nogui
)
goto end

:classic
"%JAVA%" %FLAGS% -jar "%JAR%" nogui

:end
echo.
echo [INFO] Server wurde beendet.
pause
exit /b 0

REM Loescht einen leeren/kaputten AOT-Cache
:validaot
if exist tachyon.aot for %%F in (tachyon.aot) do if %%~zF==0 del /q tachyon.aot
exit /b 0
