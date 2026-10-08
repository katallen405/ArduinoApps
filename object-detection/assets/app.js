const logEl = document.getElementById('eventLog');
const statusBadge = document.getElementById('statusBadge');

const tLabel = document.getElementById('t-label');
const tConfidence = document.getElementById('t-confidence');
const tXY = document.getElementById('t-xy');
const tWH = document.getElementById('t-wh');
const tCentroid = document.getElementById('t-centroid');
const tArea = document.getElementById('t-area');
const tDistance = document.getElementById('t-distance');
const tSpeeds = document.getElementById('t-speeds');
const steerIndicator = document.getElementById('steerIndicator');
const calibStatus = document.getElementById('calib-status');
const overlay = document.getElementById('detectionOverlay');
const overlayBox = document.getElementById('overlayBox');
const overlayLabel = document.getElementById('overlayLabel');
const searchDirectionIndicator = document.getElementById('searchDirectionIndicator');
const searchDirectionArrow = searchDirectionIndicator.querySelector('.arrow');
const searchDirectionText = searchDirectionIndicator.querySelector('.text');
const fpsBadge = document.getElementById('fpsBadge');

// The detection model reports coordinates in its own input resolution
// (MODEL_WIDTH x MODEL_HEIGHT - must match FRAME_WIDTH/FRAME_HEIGHT in
// main.py), which is NOT the same as the displayed video size. The video
// panel is responsive now, so instead of a fixed scale factor we look up
// the container's actual rendered size each time and scale from that.
const MODEL_WIDTH = 640;
const MODEL_HEIGHT = 480;
const videoContainer = document.getElementById('videoFeedContainer');

function getScale() {
  const rect = videoContainer.getBoundingClientRect();
  return { x: rect.width / MODEL_WIDTH, y: rect.height / MODEL_HEIGHT };
}

function clip(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

let lastMode = null;

const MODE_DISPLAY = {
  following: { text: 'FOLLOWING MINIFIG', className: 'status-tracking' },
  searching: { text: 'SEARCHING — SWEEPING FORWARD', className: 'status-searching' },
  lost: { text: 'NO TARGET', className: 'status-lost' },
};

const ui = new WebUI();
ui.on_connect(() => console.log('Connected to board'));
ui.on_disconnect(() => console.log('Disconnected from board'));

function clearTelemetry() {
  tLabel.textContent = '-';
  tConfidence.textContent = '-';
  tXY.textContent = '-';
  tWH.textContent = '-';
  tCentroid.textContent = '-';
  tArea.textContent = '-';
  tDistance.textContent = '-';
  tSpeeds.textContent = '-';
}

ui.on_message('telemetry', entry => {
  const display = MODE_DISPLAY[entry.mode] || MODE_DISPLAY.lost;
  statusBadge.textContent = display.text;
  statusBadge.className = display.className;

  if (entry.mode === 'following') {
    tLabel.textContent = entry.label;
    tConfidence.textContent = (entry.confidence * 100).toFixed(1) + '%';
    tXY.textContent = `${entry.x}, ${entry.y}`;
    tWH.textContent = `${entry.width} x ${entry.height}`;
    tCentroid.textContent = `${entry.cx}, ${entry.cy}`;
    tArea.textContent = entry.area_ratio;
    tDistance.textContent = entry.distance_cm != null ? `${entry.distance_cm} cm` : 'not calibrated';
    tSpeeds.textContent = `${entry.left_speed} / ${entry.right_speed}`;

    // Draw our own box + label directly at the detection's actual pixel
    // position, since the brick's built-in overlay label doesn't track it.
    // Scale from the model's coordinate space up to the current rendered
    // video size (looked up fresh each time since the panel is responsive).
    const scale = getScale();
    const panelWidth = MODEL_WIDTH * scale.x;
    const panelHeight = MODEL_HEIGHT * scale.y;

    // The FOMO model's boxes are quantized to its 40px grid cells and can
    // extend past its own 320x320 coordinate space when the minifig is
    // partly out of frame - clip so the drawn box never spills past the
    // video panel's visible edge, even though that doesn't make the
    // underlying detection itself any more precise.
    const boxLeft = clip(entry.x * scale.x, 0, panelWidth);
    const boxTop = clip(entry.y * scale.y, 0, panelHeight);
    const boxWidth = clip(entry.width * scale.x, 0, panelWidth - boxLeft);
    const boxHeight = clip(entry.height * scale.y, 0, panelHeight - boxTop);

    overlay.style.display = 'block';
    overlayBox.style.left = `${boxLeft}px`;
    overlayBox.style.top = `${boxTop}px`;
    overlayBox.style.width = `${boxWidth}px`;
    overlayBox.style.height = `${boxHeight}px`;
    overlayLabel.style.left = `${boxLeft}px`;
    overlayLabel.style.top = `${boxTop}px`;
    overlayLabel.textContent = `${entry.label} ${(entry.confidence * 100).toFixed(0)}%`;

    const arrivedText = entry.arrived ? ' (REACHED - STOPPED)' : ' (APPROACHING)';
    statusBadge.textContent = display.text + arrivedText;
    // cx_norm ranges -1 (left) .. +1 (right) -> map to 0%..100%
    const pct = ((entry.cx_norm + 1) / 2) * 100;
    steerIndicator.style.left = `calc(${pct}% - 6px)`;
    searchDirectionIndicator.classList.remove('visible');
  } else if (entry.mode === 'searching') {
    clearTelemetry();
    overlay.style.display = 'none';
    tDistance.textContent = entry.last_distance_cm != null ? `~${entry.last_distance_cm} cm (last seen)` : '-';
    tSpeeds.textContent = `${entry.left_speed} / ${entry.right_speed}`;

    // Mirrors the phase-biased search sweep in main.py: show which side the
    // robot is leaning toward first, based on where the minifig was last seen.
    const lastCx = entry.last_cx_norm || 0;
    const goingRight = lastCx > 0;
    searchDirectionIndicator.classList.add('visible');
    searchDirectionIndicator.classList.toggle('dir-right', goingRight);
    searchDirectionIndicator.classList.toggle('dir-left', !goingRight);
    searchDirectionArrow.textContent = goingRight ? '→' : '←';
    searchDirectionText.textContent = `last seen ${goingRight ? 'right' : 'left'}`;
  } else {
    clearTelemetry();
    overlay.style.display = 'none';
    searchDirectionIndicator.classList.remove('visible');
  }

  if (lastMode !== entry.mode) {
    const li = document.createElement('li');
    li.textContent = `${new Date().toLocaleTimeString()} — ${display.text.toLowerCase()}`;
    logEl.prepend(li);
    lastMode = entry.mode;
  }
});

ui.on_message('fps', entry => {
  fpsBadge.textContent = `${entry.fps.toFixed(1)} FPS`;
});

ui.on_message('calibration_result', result => {
  if (result.ok) {
    calibStatus.textContent = `Calibrated at ${result.at_distance_cm} cm (pixel height ${result.height_px}px, focal length ${result.focal_length_px}px). Saved.`;
    calibStatus.style.color = '#146c14';
  } else {
    calibStatus.textContent = `Calibration failed: ${result.reason}`;
    calibStatus.style.color = '#7a1414';
  }
});

// Tuning sliders -> backend
const confSlider = document.getElementById('s-conf');
const gainSlider = document.getElementById('s-gain');
const areaSlider = document.getElementById('s-area');
const targetDistSlider = document.getElementById('s-target-dist');
const vConf = document.getElementById('v-conf');
const vGain = document.getElementById('v-gain');
const vArea = document.getElementById('v-area');
const vTargetDist = document.getElementById('v-target-dist');

confSlider.addEventListener('input', () => {
  vConf.textContent = confSlider.value;
  ui.send_message('override_th', parseFloat(confSlider.value));
});
gainSlider.addEventListener('input', () => {
  vGain.textContent = gainSlider.value;
  ui.send_message('set_steer_gain', parseFloat(gainSlider.value));
});
areaSlider.addEventListener('input', () => {
  vArea.textContent = areaSlider.value;
  ui.send_message('set_target_area', parseFloat(areaSlider.value));
});
targetDistSlider.addEventListener('input', () => {
  vTargetDist.textContent = targetDistSlider.value;
  ui.send_message('set_target_distance_cm', parseFloat(targetDistSlider.value));
});

// Calibration button
document.getElementById('calib-btn').addEventListener('click', () => {
  const distance = parseFloat(document.getElementById('calib-distance').value);
  calibStatus.textContent = 'Calibrating...';
  calibStatus.style.color = '#666';
  ui.send_message('calibrate_distance', distance);
});