const socket = io();

const COLOR_MAP = {
    "Brown":  "#8B4513",
    "Blue":   "#3498db",
    "Green":  "#2ecc71",
    "Yellow": "#f1c40f",
    "White":  "#f0f0f0",
};

const cameraFeed       = document.getElementById("cameraFeed");
const cameraPlaceholder= document.getElementById("cameraPlaceholder");
const liveBadge        = document.getElementById("liveBadge");
const colorLabel       = document.getElementById("colorLabel");
const colorDot         = document.getElementById("colorDot");
const confidenceLabelEl= document.getElementById("confidenceLabel");
const statusMessage    = document.getElementById("statusMessage");
const errorContainer   = document.getElementById("errorContainer");
const resultsTable     = document.getElementById("resultsTable");

socket.on("connect", () => setStatus("Connected — waiting for webcam frames..."));
socket.on("disconnect", () => setStatus("Disconnected."));

// Live frame without classification result
socket.on("live_frame", (data) => {
    if (data && data.image) showFrame(data.image);
});

// Classification result (includes frame)
socket.on("classification_result", (data) => {
    hideError();
    if (data && data.image) showFrame(data.image);
    if (!data || !data.success) { showError("No valid result."); return; }

    const label      = data.label || "Unknown";
    const confidence = data.confidence || 0;
    const hex = COLOR_MAP[label] || "#008184";

    colorLabel.textContent = label.toUpperCase();
    colorLabel.style.color = hex;
    colorDot.style.background  = hex;
    colorDot.style.borderColor = hex;
    confidenceLabelEl.textContent = (confidence * 100).toFixed(1) + "% confidence";
    setStatus("Classifying live...");

    const rows = data.all_results && Array.isArray(data.all_results) ? data.all_results : [{ label, confidence }];
    renderTable(rows, label);
});

socket.on("classification_error", (data) => {
    showError(data.error || "Classification failed.");
});

function showFrame(b64) {
    cameraFeed.src = "data:image/jpeg;base64," + b64;
    cameraFeed.style.display = "block";
    cameraPlaceholder.style.display = "none";
    liveBadge.style.display = "block";
}

function renderTable(results, topLabel) {
    const sorted = [...results].sort((a, b) => b.confidence - a.confidence);
    let html = `<table><thead><tr><th>Color</th><th>Confidence</th><th></th></tr></thead><tbody>`;
    sorted.forEach(r => {
        const pct = (r.confidence * 100).toFixed(1);
        const hex = COLOR_MAP[r.label] || "#008184";
        html += `<tr class="${r.label === topLabel ? "top-row" : ""}">
            <td>${r.label}</td>
            <td>${pct}%</td>
            <td><div class="bar-bg"><div class="bar-fill" style="width:${pct}%;background:${hex};"></div></div></td>
        </tr>`;
    });
    html += "</tbody></table>";
    resultsTable.innerHTML = html;
}

function setStatus(msg) { statusMessage.textContent = msg; }
function showError(msg) { errorContainer.style.display = "block"; errorContainer.textContent = "⚠ " + msg; }
function hideError() { errorContainer.style.display = "none"; }
