// Goalkeeper web UI — talks to main.py via the arduino:web_ui brick.

const connStatus = document.querySelector('#conn-status');
const gaugeMarker = document.querySelector('#gauge-marker');
const actionLabel = document.querySelector('#action-label');
const tileFound = document.querySelector('#tile-found');
const tileDir = document.querySelector('#tile-dir');
const tilePos = document.querySelector('#tile-pos');
const tileCmd = document.querySelector('#tile-cmd');
const tileVx = document.querySelector('#tile-vx');
const tileFps = document.querySelector('#tile-fps');
const cam = document.querySelector('#camera-preview');

const ui = new WebUI();
ui.on_connect(onConnected);
ui.on_disconnect(onDisconnected);
ui.on_message('status', onStatus);
ui.on_message('frame', (b64) => { cam.src = 'data:image/jpeg;base64,' + b64; });

function onConnected() {
  connStatus.textContent = 'connected';
  connStatus.className = 'status status-on';
}

function onDisconnected() {
  connStatus.textContent = 'disconnected';
  connStatus.className = 'status status-off';
}

function onStatus(data) {
  actionLabel.textContent = data.mode ?? '-';
  tileFound.textContent = data.found ? 'FOUND' : 'lost';
  tileFound.style.color = data.found ? '#2e9e5b' : '#c07a00';
  tileDir.textContent = data.dir ?? '-';
  tilePos.textContent = data.pos ?? '-';
  tileCmd.textContent = data.cmd ?? '-';
  tileVx.textContent = data.vx != null ? data.vx.toFixed(1) : '-';
  tileFps.textContent = data.fps != null ? data.fps.toFixed(1) : '-';

  const limit = data.limit || 200;
  const norm = Math.max(-1, Math.min(1, (data.pos || 0) / limit));
  gaugeMarker.style.left = `${50 + norm * 50}%`;
}