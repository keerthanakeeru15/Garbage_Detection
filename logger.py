import json
import os
from datetime import datetime

LOG_FILE = "logs/log.json"

def log_detection(is_littering, confidence, description, location="Unknown Location"):
    os.makedirs("logs", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "YOLO Detected Littering" if is_littering else "No Littering Detected"
    
    log_entry = {
        "timestamp": timestamp,
        "location": location,
        "status": status,
        "confidence": confidence,
        "description": description
    }
    
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
        
    return log_entry

def get_recent_logs(limit=10):
    if not os.path.exists(LOG_FILE):
        return []
    logs = []
    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                logs.append(json.loads(line.strip()))
            except:
                pass
    return logs[-limit:]
