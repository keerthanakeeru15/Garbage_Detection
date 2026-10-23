import streamlit as st
import cv2
import time
import os
import json
import threading
import pandas as pd
import re
from queue import Queue
from datetime import datetime
from PIL import Image

import config
import importlib
importlib.reload(config)

from detector import yolo_detect
from location_tracker import get_full_location
from notifier import send_email

st.set_page_config(page_title=" Garbage Throwing Notification Alert System", layout="wide")

# Ensure directories exist
for d in ['temp', 'evidence', 'logs']:
    os.makedirs(d, exist_ok=True)

if "RES_QUEUE" not in st.session_state:
    st.session_state.RES_QUEUE = Queue()

USER_POINTS_FILE = "logs/user_points.json"

def is_valid_gmail(email):
    if not email:
        return False
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@gmail\.com$", email.strip(), re.IGNORECASE))

def load_points_db():
    if not os.path.exists(USER_POINTS_FILE):
        return {}
    try:
        with open(USER_POINTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_points_db(db):
    with open(USER_POINTS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)

def get_user_points(email):
    db = load_points_db()
    record = db.get(email.lower(), {"points": 0, "history": []})
    return record

def add_user_points(email, points, outcome_label, source_label):
    db = load_points_db()
    key = email.lower()
    if key not in db:
        db[key] = {"points": 0, "history": []}
    db[key]["points"] += int(points)
    db[key]["history"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "points_added": int(points),
        "outcome": outcome_label,
        "source": source_label,
        "total_points": db[key]["points"]
    })
    # Keep only latest 50 transactions to avoid unbounded growth
    db[key]["history"] = db[key]["history"][-50:]
    save_points_db(db)
    return db[key]["points"]

def redeem_user_reward(email, reward_name, required_points):
    db = load_points_db()
    key = email.lower()
    if key not in db:
        return False, 0

    current_points = int(db[key].get("points", 0))
    required_points = int(required_points)
    if current_points < required_points:
        return False, current_points

    db[key]["points"] = current_points - required_points
    db[key]["history"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "points_added": -required_points,
        "outcome": "Reward Redeemed",
        "source": reward_name,
        "total_points": db[key]["points"]
    })
    db[key]["history"] = db[key]["history"][-50:]
    save_points_db(db)
    return True, db[key]["points"]

def get_rewards_for_points(total_points):
    rewards = [
        {"name": "Mobile Recharge", "required": 25},
        {"name": "Food Voucher", "required": 50},
        {"name": "Shopping Offer", "required": 80},
    ]
    unlocked = [r for r in rewards if total_points >= r["required"]]
    locked = [r for r in rewards if total_points < r["required"]]
    return unlocked, locked

def format_location_dict(loc):
    if not isinstance(loc, dict):
        return str(loc)
    parts = [loc.get('area'), loc.get('city'), loc.get('state')]
    valid_parts = [p for p in parts if p and p != "None"]
    if not valid_parts:
        return "Unknown Area"
    return ", ".join(valid_parts)

def log_detection(is_littering, confidence, description, location_str="Unknown"):
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Detected Littering" if is_littering else "Clean",
        "confidence": confidence,
        "description": description,
        "location": location_str
    }
    with open("logs/log.json", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    return log_entry

def load_detection_logs():
    logs = []
    if not os.path.exists("logs/log.json"):
        return logs

    with open("logs/log.json", "r") as f:
        for line in f:
            if line.strip():
                try:
                    parsed = json.loads(line)
                    parsed["location_formatted"] = format_location_dict(parsed.get("location"))
                    logs.append(parsed)
                except Exception:
                    pass
    return logs

def trigger_alerts_sync(image_path, description, location_str):
    """Synchronous alert sending for manual upload"""
    loc_text = f"Location: {format_location_dict(location_str)}"
        
    msg = f"Littering detected!\n{loc_text}\nDescription: {description}"
    
    # Email
    if st.session_state.get('email_enabled', False):
        sender = st.session_state.get('email_sender') or config.EMAIL_SENDER
        pwd = st.session_state.get('email_pwd') or config.EMAIL_PASSWORD
        receiver = st.session_state.get('email_receiver') or config.EMAIL_RECEIVER
        if sender and pwd and receiver:
            success = send_email(sender, pwd, receiver, "Littering Alert", msg, image_path)
            if success:
                st.success("Email Notification sent successfully!")
            else:
                st.error("Failed to send Email Notification. Check credentials.")
                

def background_detection_task(frame, res_queue, alert_config):
    # Save frame to disk first
    import os, time
    path = f"temp/cap_{int(time.time())}.jpg"
    import cv2
    cv2.imwrite(path, frame)
    
    res = yolo_detect(path, config.GEMINI_API_KEYS)
    if res and res.get('littering') and res.get('confidence', 0) > config.CONFIDENCE_THRESHOLD:
        import shutil
        fname = os.path.basename(path)
        ev_path = os.path.join('evidence', fname)
        if os.path.exists(path):
            shutil.copy(path, ev_path)
        
        # Get Location
        loc = get_full_location()
        if not loc: loc = alert_config.get('camera_location', 'Unknown Location')
        
        log_entry = log_detection(True, res.get('confidence'), res.get('description'), loc)
        
        # Alerts
        loc_text = f"Location: {format_location_dict(loc)}"
        msg = f"Littering detected!\n{loc_text}\nDescription: {res.get('description')}"
        
        if alert_config.get('email_en') and alert_config.get('sender') and alert_config.get('pwd') and alert_config.get('receiver'):
            send_email(alert_config['sender'], alert_config['pwd'], alert_config['receiver'], "Littering Alert", msg, ev_path)
            
            
        res_queue.put({"status": "alert", "log": log_entry, "image": ev_path})
    elif res:
        res_queue.put({"status": "clean", "result": res, "image": path})
    else:
        res_queue.put({"status": "error", "error": "Detection failed"})

def detect_motion(background, current_gray, min_area=5000):
    if background is None:
        return False, 0
    frame_delta = cv2.absdiff(background, current_gray)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    motion_detected = False
    max_area = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area > min_area:
            motion_detected = True
            if area > max_area:
                max_area = area
    return motion_detected, max_area

def select_best_frame(burst_frames):
    if not burst_frames:
        return None
    burst_frames.sort(key=lambda x: x[1], reverse=True)
    return burst_frames[0]

def process_video_smart(vid_path):
    cap = cv2.VideoCapture(vid_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0: fps = 30
    duration = total_frames / fps
    
    if duration > 15.5:
        st.error(f"Video is too long ({duration:.1f}s). Maximum allowed length is 15 seconds.")
        cap.release()
        return
        
    st.write(f"Processing {duration:.1f}s video with Smart Motion Detection...")
    
    background = None
    consecutive_motion = 0
    in_burst = False
    burst_frames = []
    last_api_call_time = -20
    detected_littering_in_video = False
    
    frame_idx = 0
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        current_sec = frame_idx / fps
        progress_bar.progress(min(1.0, frame_idx / total_frames))
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        if background is None:
            background = gray.copy().astype("float")
            frame_idx += 1
            continue
            
        bg_8u = cv2.convertScaleAbs(background)
        motion_detected, motion_score = detect_motion(bg_8u, gray, min_area=5000)
        
        cv2.accumulateWeighted(gray, background, 0.1)
        
        if motion_detected:
            consecutive_motion += 1
        else:
            consecutive_motion = 0
            
        if current_sec - last_api_call_time < 20:
            frame_idx += 1
            continue
            
        if consecutive_motion >= 2 and not in_burst:
            in_burst = True
            burst_frames = []
            status_text.info(f"Motion detected at {current_sec:.1f}s. Capturing burst...")
            
        if in_burst:
            burst_frames.append((frame.copy(), motion_score, current_sec))
            if len(burst_frames) >= 5:
                best_frame, best_score, best_sec = select_best_frame(burst_frames)
                
                st.write(f"### Best Frame selected at {best_sec:.1f}s (Score: {best_score:.0f})")
                frame_path = f"temp/smart_vid_{int(time.time())}.jpg"
                cv2.imwrite(frame_path, best_frame)
                st.image(frame_path)
                
                with st.spinner("Analyzing with AI..."):
                    res = yolo_detect(frame_path, config.GEMINI_API_KEYS)
                    
                    def process_yolo_result(result, f_path, f_sec):
                        if not result:
                            st.error(f"Detection failed at {f_sec:.1f}s.")
                            return False
                        st.json(result)
                        if result.get('littering') and result.get('confidence', 0) > config.CONFIDENCE_THRESHOLD:
                            st.error(f"Littering Detected at {f_sec:.1f}s!")
                            import shutil
                            ev_path = os.path.join('evidence', os.path.basename(f_path))
                            if os.path.exists(f_path): shutil.copy(f_path, ev_path)
                            loc = get_full_location() or st.session_state.get('camera_location', 'Unknown')
                            log_detection(True, result.get('confidence'), result.get('description'), loc)
                            trigger_alerts_sync(ev_path, result.get('description'), loc)
                            return True
                        else:
                            st.success(f"No littering detected at {f_sec:.1f}s.")
                            log_detection(False, result.get('confidence', 0), result.get('description', 'Clean'))
                            return False
                            
                    success = process_yolo_result(res, frame_path, best_sec)
                    if success:
                        detected_littering_in_video = True
                    
                    if res and not success and res.get('confidence', 0) < 0.5 and len(burst_frames) > 1:
                        st.warning("Low confidence on best frame. Retrying with second best frame...")
                        retry_frame, retry_score, retry_sec = burst_frames[1]
                        retry_path = f"temp/smart_vid_retry_{int(time.time())}.jpg"
                        cv2.imwrite(retry_path, retry_frame)
                        st.image(retry_path, caption=f"Retry Frame at {retry_sec:.1f}s")
                        res2 = yolo_detect(retry_path, config.GEMINI_API_KEYS)
                        retry_success = process_yolo_result(res2, retry_path, retry_sec)
                        if retry_success:
                            detected_littering_in_video = True

                last_api_call_time = current_sec
                in_burst = False
                consecutive_motion = 0
                status_text.empty()
                
        frame_idx += 1
        
    progress_bar.empty()
    status_text.success("Video processing complete.")
    cap.release()
    return detected_littering_in_video

st.title("Garbage Throwing Notification Alert System")

st.header("User Login")
login_col1, login_col2, login_col3 = st.columns([2, 2, 1])
with login_col1:
    gmail_input = st.text_input(
        "Login with Gmail",
        value=st.session_state.get("gmail_input", ""),
        placeholder="example@gmail.com"
    )
with login_col2:
    password_input = st.text_input(
        "Password",
        value=st.session_state.get("login_password", ""),
        type="password",
        placeholder="Enter password"
    )
with login_col3:
    st.write("")
    st.write("")
    login_clicked = st.button("Login", use_container_width=True)

st.session_state.gmail_input = gmail_input
st.session_state.login_password = password_input
if login_clicked:
    if not is_valid_gmail(gmail_input):
        st.error("Enter a valid Gmail address.")
    elif not password_input or len(password_input.strip()) < 4:
        st.error("Enter a valid password (minimum 4 characters).")
    else:
        st.session_state.logged_in_email = gmail_input.strip().lower()
        st.success(f"Logged in as {st.session_state.logged_in_email}")

active_email = st.session_state.get("logged_in_email")
if active_email:
    user_record = get_user_points(active_email)
    status_col1, status_col2 = st.columns([4, 1])
    with status_col1:
        st.info(f"Logged Gmail: {active_email} | Total Points: {user_record.get('points', 0)}")
    with status_col2:
        if st.button("Logout", use_container_width=True):
            st.session_state.pop("logged_in_email", None)
            st.session_state.pop("gmail_input", None)
            st.session_state.pop("login_password", None)
            st.success("Logged out successfully.")
            st.rerun()

st.markdown("---")

with st.sidebar:
    st.header("Configuration")
    
    interval = st.number_input("Capture Interval (seconds)", value=getattr(config, 'CAPTURE_INTERVAL_SECONDS', 10), min_value=1)
    st.session_state.interval = interval
    
    camera_location = st.text_input("Camera Location", value=getattr(config, 'CAMERA_LOCATION', 'Main Entrance'))
    st.session_state.camera_location = camera_location
    
    st.subheader("Alerts Configuration")
    email_enabled = st.toggle("Enable Email Alerts", value=getattr(config, 'ENABLE_EMAIL_ALERTS', True))
    st.session_state.email_enabled = email_enabled

st.markdown("---")

st.header("Live Camera")
col1, col2 = st.columns(2)
with col1:
    if st.button("Start Detection", type="primary"):
        st.session_state.running = True
        st.rerun()
with col2:
    if st.button("Stop Detection"):
        st.session_state.running = False
        st.rerun()
        
cam_placeholder = st.empty()
live_res_placeholder = st.empty()

if st.session_state.get("running", False):
    cap = cv2.VideoCapture(0)
    last_cap = time.time()
    
    try:
        while st.session_state.running:
            ret, frame = cap.read()
            if not ret:
                st.error("Failed to read camera")
                break
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # Resize preview frame for performance
            h, w = frame_rgb.shape[:2]
            preview = cv2.resize(frame_rgb, (640, int(640 * h / w)))
            cam_placeholder.image(preview, channels="RGB")
            
            # Check for results from background thread
            if not st.session_state.RES_QUEUE.empty():
                queue_data = st.session_state.RES_QUEUE.get()
                with live_res_placeholder.container():
                    if queue_data["status"] == "alert":
                        st.error("Littering Detected!")
                        log_data = queue_data["log"]
                        loc = log_data.get("location", {})
                        st.write(f"📍 {format_location_dict(loc)}")
                        st.write(f"Description: {log_data.get('description')}")
                        if isinstance(loc, dict) and loc.get("lat") and loc.get("lon"):
                            st.map(pd.DataFrame([{"lat": loc['lat'], "lon": loc['lon']}]))
                    elif queue_data["status"] == "clean":
                        st.success("No littering detected. Area is clean.")
                    elif queue_data["status"] == "error":
                        st.warning("Detection frame dropped or failed.")
                        
            # Trigger background capture every N seconds
            if time.time() - last_cap > st.session_state.interval:
                last_cap = time.time()
                
                # Prepare alert config so thread doesn't touch st.session_state
                alert_config = {
                    'email_en': st.session_state.get('email_enabled', False),
                    'sender': st.session_state.get('email_sender', '') or config.EMAIL_SENDER,
                    'pwd': st.session_state.get('email_pwd', '') or config.EMAIL_PASSWORD,
                    'receiver': st.session_state.get('email_receiver', '') or config.EMAIL_RECEIVER,
                    'camera_location': st.session_state.get('camera_location', getattr(config, 'CAMERA_LOCATION', 'Unknown'))
                }
                
                # Start background thread (daemon=False ensures it finishes sending email even if user stops detection)
                threading.Thread(target=background_detection_task, args=(frame.copy(), st.session_state.RES_QUEUE, alert_config), daemon=False).start()
            
            time.sleep(0.05)
    finally:
        cap.release()

st.markdown("---")

st.header("Upload Image")
uploaded_file = st.file_uploader("Upload an Image to check manually", type=["jpg", "png", "jpeg"])
if uploaded_file and st.button("Run Manual Detection"):
    user_email = st.session_state.get("logged_in_email")
    if not user_email:
        st.warning("Please login with your Gmail in the sidebar to earn points.")
        st.stop()

    path = f"temp/up_{int(time.time())}.jpg"
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.image(path)
    with st.spinner("Analyzing with AI..."):
        res = yolo_detect(path, config.GEMINI_API_KEYS)
        if res:
            st.json(res)
            if res.get('littering') and res.get('confidence', 0) > config.CONFIDENCE_THRESHOLD:
                st.error("Littering Detected!")
                new_total = add_user_points(user_email, 5, "Detected", "Image Upload")
                st.info(f"+5 points added to {user_email}. Total: {new_total}")
                # Get location
                loc = get_full_location()
                if not loc: loc = st.session_state.camera_location
                
                if isinstance(loc, dict) and loc.get("lat") and loc.get("lon"):
                    st.write(f"📍 {format_location_dict(loc)}")
                    st.map(pd.DataFrame([{"lat": loc['lat'], "lon": loc['lon']}]))
                else:
                    st.write(f"📍 {loc}")
                
                log_detection(True, res.get('confidence'), res.get('description'), loc)
                trigger_alerts_sync(path, res.get('description'), loc)
            else:
                st.success("No littering detected. Clean area!")
                new_total = add_user_points(user_email, 2, "Not Detected", "Image Upload")
                st.info(f"+2 points added to {user_email}. Total: {new_total}")
                log_detection(False, res.get('confidence', 0), res.get('description', 'Clean'))
        else:
            st.error("Detection failed.")

st.markdown("---")

st.header("Upload Video")
uploaded_video = st.file_uploader("Upload a Video to check manually (Max 15s)", type=["mp4", "avi", "mov", "mkv"])
if uploaded_video and st.button("Run Video Detection"):
    user_email = st.session_state.get("logged_in_email")
    if not user_email:
        st.warning("Please login with your Gmail in the sidebar to earn points.")
        st.stop()

    vid_path = f"temp/up_vid_{int(time.time())}.mp4"
    with open(vid_path, "wb") as f:
        f.write(uploaded_video.getbuffer())
    
    st.video(vid_path)
    
    littering_detected_video = process_video_smart(vid_path)
    if littering_detected_video:
        new_total = add_user_points(user_email, 5, "Detected", "Video Upload")
        st.info(f"+5 points added to {user_email}. Total: {new_total}")
    else:
        new_total = add_user_points(user_email, 2, "Not Detected", "Video Upload")
        st.info(f"+2 points added to {user_email}. Total: {new_total}")

st.markdown("---")
st.header("Rewards")
active_email = st.session_state.get("logged_in_email")
if active_email:
    record = get_user_points(active_email)
    total_points = record.get("points", 0)
    unlocked_rewards, locked_rewards = get_rewards_for_points(total_points)
    all_rewards = unlocked_rewards + locked_rewards

    st.write(f"Current User: `{active_email}`")
    st.write(f"Points Balance: **{total_points}**")

    st.subheader("Reward Sections")
    sorted_rewards = sorted(all_rewards, key=lambda r: r["required"])
    reward_columns = st.columns(len(sorted_rewards)) if sorted_rewards else []

    for col, reward in zip(reward_columns, sorted_rewards):
        is_unlocked = total_points >= reward["required"]
        remaining = max(0, reward["required"] - total_points)
        progress_ratio = min(total_points / reward["required"], 1.0)

        with col:
            with st.container(border=True):
                st.markdown(f"### {reward['name']}")
                st.write(f"Required Points: **{reward['required']}**")
                st.progress(progress_ratio)
                if is_unlocked:
                    st.success("Status: Unlocked")
                    if st.button(f"Redeem {reward['name']}", key=f"redeem_{reward['name']}"):
                        redeemed, updated_total = redeem_user_reward(active_email, reward["name"], reward["required"])
                        if redeemed:
                            st.success(f"{reward['name']} redeemed successfully. Remaining points: {updated_total}")
                            st.rerun()
                        else:
                            st.error("Not enough points to redeem this reward.")
                else:
                    st.warning(f"Status: Locked - need **{remaining}** more points")
                    st.button(
                        f"Redeem {reward['name']}",
                        key=f"redeem_{reward['name']}",
                        disabled=True
                    )

else:
    st.info("Login with your Gmail on the main page to track points and rewards.")

st.markdown("---")

st.header("Points History")
active_email = st.session_state.get("logged_in_email")
if active_email:
    record = get_user_points(active_email)
    history = record.get("history", [])
    if history:
        hist_df = pd.DataFrame(history[::-1])
        st.dataframe(hist_df, use_container_width=True)
    else:
        st.info("No points history yet. Run detections or redeem rewards to see activity.")
else:
    st.info("Login with your Gmail in the sidebar to view points history.")

st.markdown("---")

st.header("System Dashboard")
logs = load_detection_logs()
total_detections = len(logs)
littering_detected = sum(1 for entry in logs if entry.get("status") == "Detected Littering")
clean_count = sum(1 for entry in logs if entry.get("status") == "Clean")

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Total Detection", total_detections)
metric_col2.metric("Littering Detected", littering_detected)
metric_col3.metric("Clean", clean_count)

st.markdown("---")

st.header("Event Logs")
if logs:
    df = pd.DataFrame(logs[::-1])
    st.dataframe(df.drop(columns=["location"], errors='ignore')) # Show newest first, dropping raw dict
else:
    st.write("No logs yet.")
