const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('controlAI', {
  getBaseUrl: () => ipcRenderer.invoke('app:getBaseUrl')
});
