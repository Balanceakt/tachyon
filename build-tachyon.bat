@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  Tachyon bauen (Windows)
REM
REM  Baut tachyon-26.3.jar lokal auf deinem Rechner:
REM   1. laedt BuildTools (offizielles Spigot-Werkzeug)
REM   2. baut Spigot 26.3 (Build 4664) aus dem Quellcode
REM   3. spielt die Tachyon-Patches ein
REM   4. baut tachyon-26.3.jar
REM
REM  Voraussetzungen: Java 25 oder neuer, Git, Internet. Dauer: ca. 5-10 Minuten.
REM ==========================================================================

set REV=4664
cd /d "%~dp0"

set JAVA=java
if defined JAVA_HOME set "JAVA=%JAVA_HOME%\bin\java.exe"

"%JAVA%" -version >nul 2>nul || (
    echo [FEHLER] Java nicht gefunden. Bitte Java 25+ installieren ^(z.B. https://adoptium.net^).
    pause
    exit /b 1
)
where git >nul 2>nul || (
    echo [FEHLER] Git nicht gefunden. Bitte Git installieren ^(https://git-scm.com^).
    pause
    exit /b 1
)

if not exist build mkdir build
cd build

echo [1/4] Lade BuildTools...
curl -fsSL -o BuildTools.jar https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar || (
    echo [FEHLER] Download von BuildTools fehlgeschlagen.
    pause
    exit /b 1
)

echo [2/4] Baue Spigot 26.3 ^(Build %REV%^) - das dauert ein paar Minuten...
"%JAVA%" -jar BuildTools.jar --rev %REV% --compile spigot --disable-java-check > buildtools.log 2>&1 || (
    echo [FEHLER] BuildTools ist fehlgeschlagen - siehe build\buildtools.log
    pause
    exit /b 1
)

echo [3/4] Spiele Tachyon-Patches ein...
cd Spigot\Spigot-API
git clean -fdq src >nul 2>nul
git checkout -q -- .
git apply --ignore-whitespace ..\..\..\patches\tachyon-api.patch || goto patchfail
cd ..\Spigot-Server
git clean -fdq src >nul 2>nul
git checkout -q -- .
git apply --ignore-whitespace ..\..\..\patches\tachyon-server.patch || goto patchfail
cd ..\..

set MVN=
for /d %%M in (apache-maven-*) do set "MVN=%%~fM\bin\mvn.cmd"
if not defined MVN (
    echo [FEHLER] Maven aus BuildTools nicht gefunden.
    pause
    exit /b 1
)

echo [4/4] Baue tachyon-26.3.jar...
cd Spigot\Spigot-API
call "%MVN%" -q -DskipTests install || goto buildfail
cd ..\Spigot-Server
call "%MVN%" -q -DskipTests package || goto buildfail
copy /y target\spigot-26.3-R0.1-SNAPSHOT-bootstrap.jar ..\..\..\tachyon-26.3.jar >nul
cd ..\..\..

echo.
echo ==========================================
echo  Fertig: tachyon-26.3.jar
echo  Starten mit Start-Tachyon.bat
echo ==========================================
pause
exit /b 0

:patchfail
echo [FEHLER] Patches liessen sich nicht anwenden.
pause
exit /b 1

:buildfail
echo [FEHLER] Kompilieren fehlgeschlagen.
pause
exit /b 1
