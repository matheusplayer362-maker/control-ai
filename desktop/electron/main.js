const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const http = require('http');

const PORT = process.env.CONTROL_AI_PORT || '8765';
const LOCAL_BASE_URL = `http://127.0.0.1:${PORT}`;
const DEFAULT_REMOTE_BASE_URL = 'https://control-ai.onrender.com';
const REMOTE_BASE_URL = (process.env.CONTROL_AI_API_BASE_URL || '').trim().replace(/\/$/, '');
const BASE_URL = REMOTE_BASE_URL || (app.isPackaged ? DEFAULT_REMOTE_BASE_URL : LOCAL_BASE_URL);
const USE_REMOTE_BACKEND = BASE_URL !== LOCAL_BASE_URL;
const STARTUP_TIMEOUT_MS = 120000;
let backendProcess = null;

function getBackendRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app.asar.unpacked');
  }
  return app.getAppPath();
}

function getRuntimeDir() {
  return path.join(app.getPath('userData'), 'runtime');
}

function getDataDir() {
  return path.join(app.getPath('userData'), 'data');
}

function getBootstrapScriptPath() {
  return path.join(getBackendRoot(), 'scripts', 'bootstrap_backend.py');
}

function getBackendScriptPath() {
  return path.join(getBackendRoot(), 'scripts', 'start_backend.py');
}

function getStartupLogPath() {
  return path.join(app.getPath('userData'), 'startup.log');
}

function appendStartupLog(message) {
  try {
    fs.mkdirSync(app.getPath('userData'), { recursive: true });
    fs.appendFileSync(getStartupLogPath(), `[${new Date().toISOString()}] ${message}\n`);
  } catch (_err) {
    // Logging should never block app startup.
  }
}

function getPythonCandidates() {
  if (process.platform === 'win32') {
    return [
      { command: 'py', args: ['-3'] },
      { command: 'python', args: [] },
      { command: 'python3', args: [] }
    ];
  }

  return [
    { command: 'python3', args: [] },
    { command: 'python', args: [] }
  ];
}

function runBootstrap() {
  const bootstrapScript = getBootstrapScriptPath();
  const env = {
    ...process.env,
    CONTROL_AI_PORT: PORT,
    CONTROL_AI_DATA_DIR: getDataDir(),
    CONTROL_AI_RUNTIME_DIR: getRuntimeDir(),
    PYTHONPATH: getBackendRoot()
  };

  let lastError = null;

  for (const candidate of getPythonCandidates()) {
    const commandLabel = `${candidate.command}${candidate.args.length ? ` ${candidate.args.join(' ')}` : ''}`;
    appendStartupLog(`Tentando bootstrap com ${commandLabel}`);
    const result = spawnSync(candidate.command, [...candidate.args, bootstrapScript], {
      cwd: getBackendRoot(),
      env,
      encoding: 'utf8',
      windowsHide: true,
      shell: false
    });

    if (result.error) {
      lastError = result.error;
      appendStartupLog(`Bootstrap falhou com ${commandLabel}: ${result.error.message}`);
      continue;
    }

    if (result.status !== 0) {
      const message = [
        `Bootstrap falhou com ${commandLabel} (codigo ${result.status})`,
        result.stderr || result.stdout || ''
      ].join('\n');
      lastError = new Error(message);
      appendStartupLog(message);
      continue;
    }

    const lines = String(result.stdout || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const runtimePython = lines.length > 0 ? lines[lines.length - 1] : '';

    if (runtimePython) {
      appendStartupLog(`Runtime Python preparado em ${runtimePython}`);
      return runtimePython;
    }

    lastError = new Error('Bootstrap nao retornou o caminho do Python runtime');
    appendStartupLog(lastError.message);
  }

  throw lastError || new Error('Nao foi possivel preparar o runtime do backend');
}

function waitForBackend(child, timeoutMs = STARTUP_TIMEOUT_MS) {
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    let settled = false;
    let timeoutHandle = null;

    const finishSuccess = () => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      if (child) {
        child.off('exit', handleExit);
      }
      resolve(true);
    };

    const finishFailure = (message) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      if (child) {
        child.off('exit', handleExit);
      }
      reject(new Error(message));
    };

    const handleExit = (code, signal) => {
      if (settled) {
        return;
      }
      const signalText = signal ? `, sinal ${signal}` : '';
      finishFailure(`Backend encerrou antes de ficar pronto (codigo ${code}${signalText})`);
    };

    const check = () => {
      if (settled) {
        return;
      }

      const request = http.get(`${BASE_URL}/health`, (res) => {
        res.resume();

        if (res.statusCode === 200) {
          finishSuccess();
          return;
        }

        if (Date.now() - startedAt > timeoutMs) {
          finishFailure('Backend nao iniciou a tempo');
          return;
        }

        setTimeout(check, 600);
      });

      request.on('error', () => {
        if (Date.now() - startedAt > timeoutMs) {
          finishFailure('Backend indisponivel');
          return;
        }

        setTimeout(check, 600);
      });
    };

    timeoutHandle = setTimeout(() => {
      finishFailure('Backend nao iniciou a tempo');
    }, timeoutMs);

    if (child) {
      child.once('exit', handleExit);
    }

    check();
  });
}

function startBackend() {
  const runtimePython = runBootstrap();
  const backendRoot = getBackendRoot();
  const backendScript = getBackendScriptPath();
  const env = {
    ...process.env,
    CONTROL_AI_PORT: PORT,
    CONTROL_AI_DATA_DIR: getDataDir(),
    CONTROL_AI_RUNTIME_DIR: getRuntimeDir(),
    PYTHONPATH: backendRoot
  };

  appendStartupLog(`Backend root: ${backendRoot}`);
  appendStartupLog(`Script backend: ${backendScript}`);
  appendStartupLog(`Python runtime: ${runtimePython}`);

  const child = spawn(runtimePython, [backendScript], {
    cwd: backendRoot,
    env,
    windowsHide: true,
    shell: false
  });

  child.stdout.on('data', (chunk) => {
    appendStartupLog(`stdout: ${chunk.toString().trim()}`);
  });

  child.stderr.on('data', (chunk) => {
    appendStartupLog(`stderr: ${chunk.toString().trim()}`);
  });

  child.once('spawn', () => {
    appendStartupLog('Backend process iniciado');
  });

  child.once('error', (err) => {
    appendStartupLog(`Erro ao iniciar backend: ${err.message}`);
  });

  child.once('exit', (code, signal) => {
    const signalText = signal ? `, sinal ${signal}` : '';
    appendStartupLog(`Backend encerrou com codigo ${code}${signalText}`);
  });

  backendProcess = child;
  return child;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 880,
    minHeight: 640,
    backgroundColor: '#0c1618',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });

  win.loadFile(path.join(__dirname, '../src/index.html'));
}

app.whenReady().then(async () => {
  try {
    if (USE_REMOTE_BACKEND) {
      appendStartupLog(`Usando backend remoto em ${BASE_URL}`);
    } else {
      const child = startBackend();
      await waitForBackend(child);
    }
    createWindow();
  } catch (error) {
    appendStartupLog(`Falha no startup: ${error.message}`);
    dialog.showErrorBox(
      'Control AI nao conseguiu abrir',
      `O aplicativo falhou ao iniciar.\n\nMotivo: ${error.message}\n\nLog: ${getStartupLogPath()}`
    );
    app.quit();
    return;
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle('app:getBaseUrl', async () => BASE_URL);
