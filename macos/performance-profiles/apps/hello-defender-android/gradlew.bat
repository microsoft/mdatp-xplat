@echo off
setlocal

set APP_HOME=%~dp0
set WRAPPER_PROPERTIES=%APP_HOME%gradle\wrapper\gradle-wrapper.properties

if not exist "%WRAPPER_PROPERTIES%" (
  echo Missing gradle-wrapper.properties at %WRAPPER_PROPERTIES%
  exit /b 1
)

for /f "tokens=1,* delims==" %%A in (%WRAPPER_PROPERTIES%) do (
  if "%%A"=="distributionUrl" set DIST_URL=%%B
)

if "%DIST_URL%"=="" (
  echo distributionUrl is missing in gradle-wrapper.properties
  exit /b 1
)

for %%F in (%DIST_URL%) do set DIST_FILE=%%~nxF
set DIST_NAME=%DIST_FILE:.zip=%
set DIST_ROOT=%APP_HOME%.gradle\wrapper\dists
set DIST_DIR=%DIST_ROOT%\%DIST_NAME%
set GRADLE_BIN=%DIST_DIR%\bin\gradle.bat

if not exist "%GRADLE_BIN%" (
  echo Gradle distribution not bootstrapped on Windows in this repo clone.
  echo Please run this project from Android Studio once to initialize wrapper files.
  exit /b 1
)

call "%GRADLE_BIN%" %*
