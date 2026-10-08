const connStatus = document.querySelector('#conn-status');
const tileStatus = document.querySelector('#tile-status');
const tileDetection = document.querySelector('#tile-detection');
const tileStamp = document.querySelector('#tile-stamp');
const log = document.querySelector('#log');

const MAX_LOG_ENTRIES = 50;

const ui = new WebUI();
ui.on_connect(onConnected);
ui.on_disconnect(onDisconnected);
ui.on_message('status', onStatus);

function onConnected() {
  connStatus.textContent = 'connected';
  connStatus.className = 'status status-on';
}

function onDisconnected() {
  connStatus.textContent = 'disconnected';
  connStatus.className = 'status status-off';
}

function onStatus(data) {
  const status = data.status ?? '-';
  const detection = data.last_detection ?? '-';
  const stamp = data.last_stamp ?? '-';

  tileStatus.textContent = status;
  tileDetection.textContent = detection;
  tileStamp.textContent = stamp;

  appendLogLine(status);
}

function appendLogLine(status) {
  const time = new Date().toLocaleTimeString();

  const line = document.createElement('div');
  line.className = 'log-line';
  line.textContent = `[${time}] ${status}`;
  log.prepend(line);

  while (log.childElementCount > MAX_LOG_ENTRIES) {
    log.removeChild(log.lastChild);
  }
}
