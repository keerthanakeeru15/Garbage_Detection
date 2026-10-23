import threading
import shutil
import os
import json
from datetime import datetime
from detector import yolo_detect
from location_tracker import get_full_location
from notifier import send_email, send_telegram

def process_task(task, res_queue):
    img_path = task['path']
    keys = task['keys']
    config = task['config']
    
    res = yolo_detect(img_path, keys)
    if res and res.get('littering') and res.get('confidence', 0) > 0.6:
        fname = os.path.basename(img_path)
        ev_path = os.path.join('evidence', fname)
        if os.path.exists(img_path):
            shutil.move(img_path, ev_path)
        else:
            ev_path = img_path
            
        loc = get_full_location()
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "status": "YOLO Detected Littering",
            "confidence": res.get("confidence"),
            "description": res.get("description"),
            "location": loc,
            "image": ev_path
        }
        with open("logs/log.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        if config.get('email_enabled'):
            send_email(config['email_sender'], config['email_pwd'], config['email_receiver'], 
                       "Littering Alert", f"Littering detected!\nLocation: {loc}\nDescription: {res.get('description')}", ev_path)
        if config.get('tg_enabled'):
            send_telegram(config['tg_token'], config['tg_chat'], 
                          f"Littering detected!\nLocation: {loc}\nDescription: {res.get('description')}", ev_path)
        
        res_queue.put({"status": "alert", "log": log_entry, "image": ev_path, "raw": res})
    else:
        res_queue.put({"status": "clear", "result": res, "image": img_path, "raw": res})

def worker_loop(det_queue, res_queue):
    while True:
        task = det_queue.get()
        if task is None:
            break
        try:
            process_task(task, res_queue)
        except:
            pass

def start_worker(det_queue, res_queue):
    t = threading.Thread(target=worker_loop, args=(det_queue, res_queue), daemon=True)
    t.start()
    return t
