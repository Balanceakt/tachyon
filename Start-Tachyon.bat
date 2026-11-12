@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  Tachyon Server - Startdatei / start script (Start-Tachyon.bat)
REM
REM  - startet Tachyon mit Javas AOT-Cache (Start in ca. 3 s). Nach einem Update
REM    startet er sofort ohne Cache (ca. 7 s) und erstellt ihn im Hintergrund neu
REM  - dynamischer RAM: startet mit RAM_MIN, holt sich bei Bedarf bis RAM_MAX
REM    und gibt freien Speicher im Leerlauf wieder ans System zurueck
REM  - Schlafmodus: ohne Spieler legt sich der Server schlafen (RAM komplett frei)
REM    und wacht auf, sobald jemand joint (Einstellung in tachyon.yml: sleep-mode)
REM  - Sprache, EULA und alles Weitere fragt Tachyon beim ersten Start selbst
REM ==========================================================================

REM ---- Einstellungen / settings ----------------------------------------------
set JAR=tachyon-26.3.jar
REM RAM-Bereich: so wenig wie moeglich, so viel wie noetig
set RAM_MIN=1G
set RAM_MAX=4G
REM Maximal genutzte CPU-Kerne (0 = alle)
set CPU_MAX=0
REM ---------------------------------------------------------------------------

cd /d "%~dp0"
title Tachyon Server

REM Sprache aus tachyon.yml (wird beim ersten Start gewaehlt)
set L=de
findstr /b /c:"language: en" tachyon.yml >nul 2>nul && set L=en

REM Java 25+ suchen: JAVA_HOME, sonst ~/.jdks, sonst PATH
set JAVA=java
if exist "%USERPROFILE%\.jdks\openjdk-26\bin\java.exe" set "JAVA=%USERPROFILE%\.jdks\openjdk-26\bin\java.exe"
if defined JAVA_HOME set "JAVA=%JAVA_HOME%\bin\java.exe"
"%JAVA%" -version >nul 2>nul || (
    if "%L%"=="en" (echo [ERROR] Java not found. Please install Java 25+ or set JAVA_HOME.) else (echo [FEHLER] Kein Java gefunden. Bitte Java 25+ installieren oder JAVA_HOME setzen.)
    pause
    exit /b 1
)
if not exist "%JAR%" (
    if "%L%"=="en" (echo [ERROR] %JAR% not found.) else (echo [FEHLER] %JAR% nicht gefunden.)
    pause
    exit /b 1
)

REM Speicher: dynamisch zwischen RAM_MIN und RAM_MAX. Periodische, nebenlaeufige GC gibt
REM ungenutzten Speicher im Leerlauf zurueck - ohne Pausen im Spiel.
set MEM=-Xms%RAM_MIN% -Xmx%RAM_MAX% -XX:G1PeriodicGCInterval=30000 -XX:MinHeapFreeRatio=10 -XX:MaxHeapFreeRatio=30
set CPU=
if not "%CPU_MAX%"=="0" set CPU=-XX:ActiveProcessorCount=%CPU_MAX%
REM G1-Tuning (bewaehrte Server-Flags) + Compact Object Headers (Java 25: weniger RAM pro Objekt)
set GC=-XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -XX:+UseCompactObjectHeaders
set FLAGS=%MEM% %CPU% %GC% --enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow
REM Schlafmodus: nur mit diesem Skript kann der Server wieder geweckt werden
set SLEEP=-Dtachyon.sleepLauncher=true
REM Waechter waehrend des Schlafs: winziges Java ohne JIT, ca. 30-40 MB RAM
set WATCH=-Xms4m -Xmx16m -XX:+UseSerialGC -Xint -XX:-UsePerfData -Xss256k -XX:MaxMetaspaceSize=24m

REM Signatur der Jar (Groesse + Datum) - erkennt Updates ohne langsame Hilfsprogramme
for %%F in ("%JAR%") do set "JARSIG=%%~zF %%~tF"

REM ---- Bibliotheken entpacken (nur wenn die Jar neu/aktualisiert ist) -------
set OLDSIG=
if exist "tachyon-libs\tachyon.jarsig" set /p OLDSIG=<"tachyon-libs\tachyon.jarsig"
if not exist "tachyon-libs\tachyon-launch.args" set OLDSIG=
if not "%OLDSIG%"=="%JARSIG%" (
    if "%L%"=="en" (echo [INFO] Unpacking libraries...) else (echo [INFO] Entpacke Bibliotheken...)
    "%JAVA%" -Xmx512m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -DbundlerMainClass= -jar "%JAR%"
    if not exist "tachyon-libs\tachyon-launch.args" goto classic
    > "tachyon-libs\tachyon.jarsig" echo %JARSIG%
)

REM ---- Server starten --------------------------------------------------------
REM Start-Cache (AOT) gueltig, solange Jar und JVM-Einstellungen gleich bleiben.
REM Sonst startet Tachyon sofort ohne Cache und erstellt ihn danach im Hintergrund.
:start
set "AOTSIG=%JARSIG% %FLAGS%"
set OLDAOT=
if exist tachyon.aot.sig set /p OLDAOT=<tachyon.aot.sig
call :validaot
if not exist tachyon.aot set OLDAOT=
if "%OLDAOT%"=="%AOTSIG%" goto withcache
> "tachyon-libs\aot.wanted" echo %AOTSIG%
"%JAVA%" %FLAGS% %SLEEP% -Dtachyon.aotTrain=true @tachyon-libs\tachyon-launch.args nogui
set RC=%ERRORLEVEL%
goto stopped

:withcache
"%JAVA%" %FLAGS% %SLEEP% -XX:AOTCache=tachyon.aot @tachyon-libs\tachyon-launch.args nogui
set RC=%ERRORLEVEL%

:stopped
REM 75 = Server hat sich schlafen gelegt -> Waechter starten, beim Join wieder hochfahren
if not "%RC%"=="75" goto end
"%JAVA%" %WATCH% -jar "%JAR%" --tachyon-sleep
if "%ERRORLEVEL%"=="10" goto start
goto end

:classic
"%JAVA%" %FLAGS% -jar "%JAR%" nogui

:end
echo.
set L=de
findstr /b /c:"language: en" tachyon.yml >nul 2>nul && set L=en
if "%L%"=="en" (echo [INFO] Server stopped.) else (echo [INFO] Server wurde beendet.)
pause
exit /b 0

REM Loescht einen leeren/kaputten AOT-Cache
:validaot
if exist tachyon.aot for %%F in (tachyon.aot) do if %%~zF==0 del /q tachyon.aot
exit /b 0
