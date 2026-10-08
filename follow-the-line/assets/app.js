const ACTION_NAMES = ['SPRINT', 'SOFT_LEFT', 'HARD_LEFT', 'SOFT_RIGHT', 'HARD_RIGHT'];
const MAX_LOG_ENTRIES = 50;

const modeEl = document.getElementById('mode');
const linePosEl = document.getElementById('linePos');
const lastActionEl = document.getElementById('lastAction');
const eventLogEl = document.getElementById('eventLog');

function logEvent(text) {
  const li = document.createElement('li');
  const time = new Date().toLocaleTimeString();
  li.textContent = `[${time}] ${text}`;
  eventLogEl.prepend(li);
  while (eventLogEl.children.length > MAX_LOG_ENTRIES) {
    eventLogEl.removeChild(eventLogEl.lastChild);
  }
}

const ui = new WebUI();

ui.on_connect(() => logEvent('Connected to robot'));
ui.on_disconnect(() => logEvent('Disconnected from robot'));

let lastMode = null;

ui.on_message('state', (data) => {
  const { mode, x, action } = data;

  modeEl.textContent = mode ?? '-';
  linePosEl.textContent = typeof x === 'number' ? x.toFixed(2) : '-';
  lastActionEl.textContent = typeof action === 'number' ? ACTION_NAMES[action] ?? action : '-';

  if (mode !== lastMode) {
    logEvent(`Mode changed to ${mode}`);
    lastMode = mode;
  }
});