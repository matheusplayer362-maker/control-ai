const chatHistoryEl = document.getElementById('chatHistory');
const chatForm = document.getElementById('chatForm');
const messageInput = document.getElementById('messageInput');
const statusText = document.getElementById('statusText');
const statusDot = document.getElementById('statusDot');
const confidenceEl = document.getElementById('confidence');
const modeEl = document.getElementById('mode');
const sourcesEl = document.getElementById('sources');
const newChatBtn = document.getElementById('newChatBtn');
const reloadSkillsBtn = document.getElementById('reloadSkillsBtn');
const healthBtn = document.getElementById('healthBtn');

const sessionId = 'default';
let baseUrl = '';

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = content;
  chatHistoryEl.appendChild(div);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

function setStatus(text, ok = false) {
  statusText.textContent = text;
  statusDot.classList.toggle('ok', ok);
}

function renderSources(sources) {
  if (!sources || !sources.length) {
    sourcesEl.innerHTML = '<i>Sem fontes externas nesta resposta.</i>';
    return;
  }
  sourcesEl.innerHTML = sources
    .map(
      (s) =>
        `<div><b>${s.title}</b> | confiabilidade-fonte: ${s.reliability}<br/><a href="${s.url}">${s.url}</a><br/>${s.excerpt}</div><hr/>`
    )
    .join('');
}

async function loadHistory() {
  const res = await fetch(`${baseUrl}/history/${sessionId}`);
  const data = await res.json();
  chatHistoryEl.innerHTML = '';
  for (const item of data) {
    addMessage(item.role, item.content);
  }
}

async function sendMessage(message) {
  addMessage('user', message);
  setStatus('Processando...', false);

  const res = await fetch(`${baseUrl}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId })
  });

  if (!res.ok) {
    addMessage('assistant', 'Erro ao processar mensagem.');
    setStatus('Falha', false);
    return;
  }

  const data = await res.json();
  addMessage('assistant', data.answer);
  confidenceEl.textContent = `${Math.round(data.confidence * 100)}%`;
  modeEl.textContent = data.mode;
  renderSources(data.sources);
  setStatus('Pronto', true);
}

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = '';
  await sendMessage(message);
});

newChatBtn.addEventListener('click', async () => {
  await fetch(`${baseUrl}/history/${sessionId}`, { method: 'DELETE' });
  chatHistoryEl.innerHTML = '';
  sourcesEl.innerHTML = '';
});

reloadSkillsBtn.addEventListener('click', async () => {
  const res = await fetch(`${baseUrl}/skills`);
  const data = await res.json();
  addMessage('assistant', `Skills carregadas: ${data.skills.join(', ') || 'nenhuma'}`);
});

healthBtn.addEventListener('click', async () => {
  const res = await fetch(`${baseUrl}/health`);
  const data = await res.json();
  addMessage('assistant', `Saude: ${data.status} | modelo: ${data.model_ready ? 'ativo' : 'fallback'} | uptime: ${Math.round(data.uptime_seconds)}s`);
});

(async () => {
  setStatus('Conectando backend...', false);
  baseUrl = await window.controlAI.getBaseUrl();
  await loadHistory();
  setStatus('Pronto', true);
})();
