from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_imageclassification import VideoImageClassification
import json

ui = WebUI()

EMOJI_MAP = {
    "Brown":  "🟤",
    "Blue":   "🔵",
    "Green":  "🟢",
    "Yellow": "🟡",
    "White":  "⚪",
}

COLOR_MAP = {
    "Brown":  "#8B4513",
    "Blue":   "#3498db",
    "Green":  "#2ecc71",
    "Yellow": "#f1c40f",
    "White":  "#f0f0f0",
}

detection_stream = VideoImageClassification(confidence=0.3, debounce_sec=0.0)

def send_detections_to_ui(classifications: dict):
    if not classifications:
        return

    sorted_results = sorted(classifications.items(), key=lambda x: x[1], reverse=True)
    top_label, top_confidence = sorted_results[0]

    emoji = EMOJI_MAP.get(top_label, "🔲")
    print(f"{emoji} {top_label.upper()} detected ({top_confidence:.2%})")

    all_results = [
        {"label": label, "confidence": conf}
        for label, conf in sorted_results
    ]

    ui.send_message("classification_result", {
        "success": True,
        "label": top_label,
        "confidence": top_confidence,
        "all_results": all_results,
    })

detection_stream.on_detect_all(send_detections_to_ui)

App.run()