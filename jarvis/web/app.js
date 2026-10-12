/* Credentials stay in tab memory. Provider keys are never used by this client. */
const $ = (id) => document.getElementById(id);
let token = '', socket = null, busy = false, connected = false, assistantMessage = null;
let session = localStorage.getItem('jarvis-session');
if (!session || !/^[0-9a-f-]{36}$/i.test(session)) session = crypto.randomUUID();
let generation = 0;
const dialog = $('connection-dialog');
function notice(text = '') { $('notice').textContent = text; }
function state(label) { $('assistant-state').textContent = label; }
function setBusy(value) {
  busy = value; $('core').classList.toggle('busy', value);
  $('send-button').disabled = !connected || value;
  $('stop-button').hidden = !value;
  $('new-session').disabled = value; $('delete-session').disabled = value;
}
function controls(value) {
  connected = value; $('prompt').disabled = !value; $('send-button').disabled = !value || busy;
  $('connection-label').textContent = value ? 'CONNECTED' : 'STANDBY';
}
function addMessage(role, text = '') {
  $('welcome')?.remove();
  const row = document.createElement('div'); row.className = `message ${role}`;
  const avatar = document.createElement('span'); avatar.className = 'message-avatar'; avatar.textContent = role === 'user' ? 'U' : 'J';
  const content = document.createElement('div'), name = document.createElement('div'), paragraph = document.createElement('p');
  name.className = 'message-name'; name.textContent = role === 'user' ? 'YOU' : 'J.A.R.V.I.S.';
  paragraph.textContent = text; content.append(name, paragraph); row.append(avatar, content); $('messages').append(row);
  scrollMessages(); return paragraph;
}
function scrollMessages() { $('messages').scrollTop = $('messages').scrollHeight; }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...options.headers, Authorization: `Bearer ${token}`}});
  if (!response.ok) {
    if (response.status === 401 || response.status === 503) throw new Error('Check your backend access token and server configuration.');
    throw new Error(`Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}
async function telemetry() {
  if (!token || !connected) return;
  try {
    const data = await api('/api/diagnostics');
    for (const [id, key] of [['cpu', 'cpu_percent'], ['memory', 'memory_percent']]) {
      $(id).textContent = `${data.metrics[key].toFixed(1)}%`;
      $(`${id}-bar`).style.width = `${Math.min(100, Math.max(0, data.metrics[key]))}%`;
    }
    $('disk').textContent = `${(data.metrics.disk_free_bytes / 1024 ** 3).toFixed(1)} GB`;
    $('database').textContent = `DATABASE ${data.database === 'ok' ? 'CONNECTED' : 'FAILED'}`;
    $('storage-badge').textContent = data.database === 'ok' ? 'ONLINE' : 'FAILED';
    $('storage-badge').classList.toggle('online', data.database === 'ok');
  } catch { $('database').textContent = 'TELEMETRY UNAVAILABLE'; $('storage-badge').textContent = 'UNKNOWN'; $('storage-badge').classList.remove('online'); }
}
async function loadHistory() {
  const data = await api(`/api/sessions/${session}`);
  $('messages').replaceChildren();
  for (const message of data.messages) addMessage(message.role, message.content);
  if (!data.messages.length) addMessage('assistant', 'At your service. What shall we work on?');
  $('session-label').textContent = `SESSION / ${session.slice(0, 8).toUpperCase()}`;
}
function openSocket() {
  const current = ++generation;
  if (socket) socket.close();
  controls(false); setBusy(false);
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/assistant`);
  socket = ws;
  ws.onopen = () => ws.send(JSON.stringify({type: 'auth', token}));
  ws.onmessage = (event) => {
    if (current !== generation) return;
    const data = JSON.parse(event.data);
    if (data.type === 'system.status' && data.payload.status === 'authenticated') {
      controls(true); state('READY TO ASSIST'); notice(); telemetry();
      $('prompt').focus(); return;
    }
    if (data.type === 'assistant.thinking') state('PROCESSING REQUEST');
    if (data.type === 'message.delta') {
      state('RESPONSE STREAMING'); assistantMessage.textContent += data.payload.text; scrollMessages();
    }
    if (data.type === 'message.assistant') { assistantMessage.textContent = data.payload.text; localStorage.setItem('jarvis-session', session); }
    if (data.type === 'system.error') {
      notice(data.payload.message); if (assistantMessage) { assistantMessage.parentElement.parentElement.classList.add('failed'); if (!assistantMessage.textContent) assistantMessage.textContent = 'The request could not be completed.'; }
    }
    if (data.type === 'system.warning') notice(data.payload.message);
    if (data.type === 'system.status' && data.payload.status === 'cancelled') notice('Response stopped. This exchange was not saved.');
    if (data.type === 'assistant.idle') { setBusy(false); state('READY TO ASSIST'); scrollMessages(); $('prompt').focus(); }
  };
  ws.onclose = () => {
    if (current !== generation) return;
    const interrupted = busy;
    controls(false); setBusy(false); state('CONNECTION CLOSED');
    $('chat-badge').textContent = 'OFFLINE'; $('chat-badge').classList.remove('online');
    notice(interrupted ? 'Connection lost during the response. Reconnect to check the saved conversation.' : 'Connection closed. Open settings to reconnect.');
  };
  ws.onerror = () => { if (current === generation) notice('Unable to connect. Check that the backend is running.'); };
}
$('settings-button').onclick = () => dialog.showModal();
$('close-dialog').onclick = () => dialog.close();
$('connect-form').onsubmit = async (event) => {
  event.preventDefault(); $('connection-error').textContent = ''; $('connect-button').disabled = true;
  token = $('token').value.trim();
  try {
    const data = await api('/api/status');
    if (!data.chat_configured) throw new Error(data.configuration_issue || 'Configure a provider on the backend first.');
    $('model-label').textContent = data.model.toUpperCase();
    $('chat-badge').textContent = 'CONFIGURED'; $('chat-badge').classList.add('online');
    await loadHistory(); $('token').value = ''; dialog.close(); openSocket();
  } catch (error) { $('connection-error').textContent = error.message; token = ''; }
  finally { $('connect-button').disabled = false; }
};
$('chat-form').onsubmit = (event) => {
  event.preventDefault(); const text = $('prompt').value.trim();
  if (!text || !connected || busy || socket.readyState !== WebSocket.OPEN) return;
  notice(); addMessage('user', text); assistantMessage = addMessage('assistant'); setBusy(true);
  socket.send(JSON.stringify({type: 'message.user', payload: {message: text, session_id: session}}));
  $('prompt').value = ''; $('prompt').style.height = 'auto';
};
$('prompt').onkeydown = (event) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); } };
$('prompt').oninput = () => { $('prompt').style.height = 'auto'; $('prompt').style.height = `${Math.min($('prompt').scrollHeight, 120)}px`; };
$('stop-button').onclick = () => { if (busy && socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type: 'cancel'})); };
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { if (!connected) { dialog.showModal(); return; } $('prompt').value = button.dataset.prompt; $('prompt').focus(); });
async function systemCheck() { if (!connected) { dialog.showModal(); return; } await telemetry(); notice('Telemetry refreshed. Provider connectivity is established only by a successful chat request.'); }
$('system-check').onclick = systemCheck; $('diagnostics-button').onclick = systemCheck;
$('assistant-tab').onclick = () => $('prompt').focus();
$('new-session').onclick = () => { if (busy) return; session = crypto.randomUUID(); localStorage.setItem('jarvis-session', session); $('messages').replaceChildren(); addMessage('assistant', 'A fresh start. What shall we work on?'); $('session-label').textContent = `SESSION / ${session.slice(0, 8).toUpperCase()}`; notice(); };
$('delete-session').onclick = async () => {
  if (!connected) { dialog.showModal(); return; }
  if (busy || !confirm('Permanently delete this saved conversation?')) return;
  try { await api(`/api/sessions/${session}`, {method: 'DELETE'}); $('new-session').click(); notice('Conversation deleted.'); } catch (error) { notice(error.message); }
};
function clock() { $('clock').textContent = new Date().toLocaleTimeString('en-GB', {hour12: false}); }
clock(); setInterval(clock, 1000); setInterval(telemetry, 30000);
const hour = new Date().getHours(); $('welcome').querySelector('p').textContent = `Good ${hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'}. What shall we work on?`;
