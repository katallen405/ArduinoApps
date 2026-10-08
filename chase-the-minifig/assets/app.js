const connStatus = document.querySelector('#conn-status');
const gaugeMarker = document.querySelector('#gauge-marker');
const actionLabel = document.querySelector('#action-label');
const tileFps = document.querySelector('#tile-fps');
const tileFrameMs = document.querySelector('#tile-frame-ms');
const tileConfidence = document.querySelector('#tile-confidence');
const tileError = document.querySelector('#tile-error');
const tileCount = document.querySelector('#tile-count');
const tileDistance = document.querySelector('#tile-distance');
const targetLabel = document.querySelector('#target-label');

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
  targetLabel.textContent = data.label ?? '-';
  actionLabel.textContent = data.action ?? '-';
  tileFps.textContent = data.fps != null ? data.fps.toFixed(1) : '-';
  tileFrameMs.textContent = data.frame_ms != null ? `${data.frame_ms.toFixed(0)} ms` : '-';
  tileConfidence.textContent = data.confidence != null ? `${data.confidence.toFixed(1)}%` : '-';
  tileError.textContent = data.error_px != null ? data.error_px.toFixed(0) : '-';
  tileCount.textContent = data.minifig_count ?? '-';
  tileDistance.textContent = data.box_height_frac != null ? `${(data.box_height_frac * 100).toFixed(0)}%` : '-';

  // Map normalized error (-1..1) to marker position (0%..100%), clamped.
  const norm = data.error_norm != null ? Math.max(-1, Math.min(1, data.error_norm)) : 0;
  const percent = 50 + norm * 50;
  gaugeMarker.style.left = `${percent}%`;
}
