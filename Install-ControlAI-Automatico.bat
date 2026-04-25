@echo off
setlocal
cd /d "%~dp0"

echo [1/6] Preparando ambiente Python...
if not exist .venv (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Falha ao criar .venv
    exit /b 1
  )
)

call .venv\Scripts\activate
if errorlevel 1 (
  echo Falha ao ativar .venv
  exit /b 1
)

echo [2/6] Instalando dependencias Python...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1

echo [3/6] Instalando dependencias Node...
if not exist node_modules (
  call npm install
  if errorlevel 1 exit /b 1
)

echo [4/6] Limpando build antigo...
if exist dist rmdir /s /q dist
mkdir dist

echo [5/6] Gerando instalador...
call npm run build:installer
if errorlevel 1 (
  echo Falha ao gerar instalador.
  exit /b 1
)

echo [6/6] Executando instalador...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-ChildItem -Path '.\\dist' -Filter 'ControlAI-Setup-*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "INSTALLER=%%I"

if not defined INSTALLER (
  echo Instalador nao encontrado em dist.
  exit /b 1
)

start "" "%INSTALLER%"
echo Instalador aberto. No final da instalacao, o app abre automaticamente.
