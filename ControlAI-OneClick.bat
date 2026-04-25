@echo off
setlocal
cd /d "%~dp0"

if not exist dist (
  echo Instalador ainda nao foi gerado. Executando instalacao automatica...
  call "%~dp0Install-ControlAI-Automatico.bat"
  exit /b %errorlevel%
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-ChildItem -Path '.\\dist' -Filter 'ControlAI-Setup-*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "INSTALLER=%%I"

if not defined INSTALLER (
  echo Nenhum instalador encontrado em dist. Executando instalacao automatica...
  call "%~dp0Install-ControlAI-Automatico.bat"
  exit /b %errorlevel%
)

echo Abrindo instalador existente:
echo %INSTALLER%
start "" "%INSTALLER%"
