"""
pages/scanner.py
────────────────
Live continuous face recognition scanner dashboard.

Features
────────
  • Dual-column layout: Camera view (left) and Real-time Status + Recent logs (right)
  • Thread-safe camera capture and background face recognition matching
  • Custom bounding boxes around detected faces (Green: recognized, Orange: verifying, Red: unknown)
  • Automated punch execution on match with cooldown limits (5 minutes)
  • Webcam frame base64 encoding and submission to Laravel API as photographic proof
  • Sound confirmation (beeps) on matches and errors
"""

import threading
import time
import base64
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import face_recognition
from PIL import Image, ImageTk
import winsound

import db
import sso_client
from theme import *

PUNCH_COOLDOWN_SECONDS = 300  # 5 minutes
MATCH_TOLERANCE = 0.48        # Biometric matching distance threshold


def play_beep_success():
    try:
        winsound.Beep(1800, 150)
        winsound.Beep(2200, 150)
    except Exception:
        pass


def play_beep_warning():
    try:
        winsound.Beep(1200, 300)
    except Exception:
        pass


def play_beep_error():
    try:
        winsound.Beep(440, 500)
    except Exception:
        pass


class ScannerPage(tk.Frame):

    def __init__(self, master, **kw):
        super().__init__(master, bg=BG_BASE, **kw)
        self._running = False
        self._camera = None
        self._lock = threading.Lock()
        
        # Thread handles
        self._camera_thread = None
        self._rec_thread = None
        
        # Data caches
        self._templates = []
        self._last_punch_time = {}
        
        # Verification timer states
        self._verifying_emp_id = None
        self._verifying_start_time = 0.0
        self._verifying_last_seen = 0.0
        
        # Frame exchanges
        self._current_frame = None       # Latest raw frame
        self._display_frame = None       # BGR frame processed for display (boxes drawn)
        self._detections = []            # Current active face detections
        self._detections_lock = threading.Lock()

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Left Column: Video View ───────────────────────────────────────────
        left_col = tk.Frame(self, bg=BG_BASE)
        left_col.pack(side="left", fill="both", expand=True, padx=(PAD_LG, PAD_MD), pady=PAD_LG)

        hdr = tk.Frame(left_col, bg=BG_SURFACE, pady=PAD_MD, padx=PAD_MD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="● LIVE FACE SCANNER", font=FONT_H3, bg=BG_SURFACE, fg=ACCENT).pack(anchor="w")
        tk.Label(hdr, text="Look directly at the camera to record your attendance", font=FONT_SMALL, bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(anchor="w")

        # Border wrapper for video element
        video_border = tk.Frame(left_col, bg=BORDER, bd=0, padx=1, pady=1)
        video_border.pack(fill="both", expand=True, pady=(PAD_MD, 0))
        video_border.pack_propagate(False)

        self._video_lbl = tk.Label(video_border, bg="black", text="Initializing camera...")
        self._video_lbl.pack(fill="both", expand=True)

        # ── Right Column: Status Cards & Logs ─────────────────────────────────
        right_col = tk.Frame(self, bg=BG_BASE, width=380)
        right_col.pack(side="right", fill="y", padx=(PAD_MD, PAD_LG), pady=PAD_LG)
        right_col.pack_propagate(False)

        # Status Display card
        status_card = tk.Frame(right_col, bg=BG_SURFACE, padx=PAD_MD, pady=PAD_MD, bd=1, relief="solid", highlightbackground=BORDER)
        status_card.pack(fill="x")

        tk.Label(status_card, text="Biometric Verification", font=FONT_H3, bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(anchor="w")
        
        self._status_val = tk.StringVar(value="Camera Off")
        self._status_lbl = tk.Label(status_card, textvariable=self._status_val, font=FONT_H2, bg=BG_SURFACE, fg=TEXT_DISABLED)
        self._status_lbl.pack(anchor="w", pady=(PAD_XS, PAD_SM))

        self._name_var = tk.StringVar(value="Waiting...")
        self._name_lbl = tk.Label(status_card, textvariable=self._name_var, font=FONT_H1, bg=BG_SURFACE, fg=TEXT_PRIMARY)
        self._name_lbl.pack(anchor="w")

        self._badge_var = tk.StringVar(value="")
        self._badge_lbl = tk.Label(status_card, textvariable=self._badge_var, font=FONT_H3, bg=BG_SURFACE, fg=ACCENT)
        self._badge_lbl.pack(anchor="w", pady=(PAD_XS, 0))

        # Recent Logs Table
        logs_title_row = tk.Frame(right_col, bg=BG_BASE)
        logs_title_row.pack(fill="x", pady=(PAD_LG, PAD_SM))
        tk.Label(logs_title_row, text="Recent Attendance Punches", font=FONT_H3, bg=BG_BASE, fg=TEXT_SECONDARY).pack(side="left")

        tree_border = tk.Frame(right_col, bg=BORDER, bd=0, padx=1, pady=1)
        tree_border.pack(fill="both", expand=True)
        
        tree_frame = tk.Frame(tree_border, bg=BG_SURFACE)
        tree_frame.pack(fill="both", expand=True)

        cols = ("time", "name", "id", "cloud")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        for col, w, label in [
            ("time",  65,  "Time"),
            ("name",  140, "Name"),
            ("id",    70,  "ID"),
            ("cloud", 55,  "Sync"),
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Bottom connection status
        self._conn_lbl = tk.Label(right_col, text="● Cloud Connection: Offline", font=FONT_SMALL, bg=BG_BASE, fg=DANGER, pady=PAD_SM)
        self._conn_lbl.pack(anchor="w")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Starts camera stream and background match workers."""
        if self._running:
            return

        self._running = True
        
        # Load local face templates into memory
        self._load_templates()
        self._load_recent_punches()

        # Update server connection visual indicator
        self._update_connection_status()

        # Show initial starting status
        self._video_lbl.config(image="", text="⚡ Starting camera stream...", font=FONT_H2, fg=TEXT_SECONDARY)

        self._status_val.set("Connecting webcam...")
        self._status_lbl.config(fg=TEXT_SECONDARY)
        self._name_var.set("Scanning...")

        # Launch thread loops
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()

        self._rec_thread = threading.Thread(target=self._recognition_loop, daemon=True)
        self._rec_thread.start()

        # Start UI render loop
        self.after(50, self._ui_render_loop)

    def stop(self):
        """Stops the loops and releases the camera device."""
        print("[Scanner] Stopping scanner and releasing camera...")
        self._running = False
        
        with self._lock:
            if self._camera:
                self._camera.release()
                self._camera = None
        print("[Scanner] Camera released.")

        # Give threads time to exit
        if self._camera_thread:
            self._camera_thread.join(timeout=1.0)
        if self._rec_thread:
            self._rec_thread.join(timeout=1.0)
        print("[Scanner] Threads stopped.")

        self._video_lbl.config(image="", text="Camera stopped")
        self._status_val.set("Camera Off")
        self._status_lbl.config(fg=TEXT_DISABLED)
        self._name_var.set("Paused")
        self._badge_var.set("")

    # ── Database Sync / Load ──────────────────────────────────────────────────

    def _load_templates(self):
        """Preloads enrolled face descriptors from the local database."""
        self._templates = db.get_all_templates()
        print(f"[Scanner] Loaded {len(self._templates)} face templates from SQLite database.")

    def _load_recent_punches(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        today_str = date.today().isoformat()
        records = db.get_attendance(date_filter=today_str, limit=10)
        for r in records:
            ts = r["timestamp"] or ""
            time_str = ts[11:19] if len(ts) >= 19 else ts
            self._tree.insert("", "end", values=(
                time_str,
                r["emp_name"],
                r["emp_id"],
                "✅" if r["event_type"] in ("check_in", "check_out") else "⚠️"
            ))

    def _update_connection_status(self):
        if sso_client.is_authenticated():
            self._conn_lbl.config(text="● Cloud Connection: Active", fg=SUCCESS)
        else:
            self._conn_lbl.config(text="● Cloud Connection: Offline (Local Logs Only)", fg=WARNING)

    # ── Thread Loops ──────────────────────────────────────────────────────────

    def _camera_loop(self):
        """Constantly captures raw webcam frames."""
        try:
            cam_idx_str = db.get_setting("camera_index")
            cam_idx = int(cam_idx_str) if cam_idx_str is not None else 0
        except Exception:
            cam_idx = 0

        # Initialize VideoCapture in the background thread
        cam = cv2.VideoCapture(cam_idx)
        if not cam.isOpened():
            # Update UI on main thread if webcam fails to load
            self.after(0, lambda: self._video_lbl.config(
                text="⚠️ Camera Not Found\n\nPlease connect a webcam and retry.", 
                font=FONT_H2, fg=DANGER
            ))
            self.after(0, lambda: self._status_val.set("Webcam Error"))
            self._running = False
            return

        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        with self._lock:
            self._camera = cam

        self.after(0, lambda: self._status_val.set("Waiting for face..."))

        while self._running:
            cam_ref = None
            with self._lock:
                cam_ref = self._camera
            if not cam_ref:
                break

            ret, frame = cam_ref.read()

            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)  # mirror image
            
            with self._lock:
                self._current_frame = frame.copy()
            
            time.sleep(0.03)

    def _recognition_loop(self):
        """Processes captures in the background to match faces without stalling UI."""
        process_interval = 0.35  # only process recognition every 350ms to save CPU
        last_process_time = 0.0

        while self._running:
            now = time.time()
            if now - last_process_time < process_interval:
                time.sleep(0.02)
                continue

            frame = None
            with self._lock:
                if self._current_frame is not None:
                    frame = self._current_frame.copy()

            if frame is None:
                time.sleep(0.02)
                continue

            last_process_time = now
            
            # 1. Resize frame to 1/4 size for fast processing
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            # 2. Run face detection
            locations = face_recognition.face_locations(rgb_small, model="hog")
            
            detections = []
            if locations:
                # 3. Compute encodings
                encodings = face_recognition.face_encodings(rgb_small, locations)
                
                for loc, enc in zip(locations, encodings):
                    # Scale face location back to original image coordinates
                    top, right, bottom, left = loc
                    orig_loc = (top * 4, right * 4, bottom * 4, left * 4)

                    match_emp = self._find_match(enc)
                    
                    if match_emp:
                        emp_id = match_emp["emp_id"]
                        name = match_emp["name"]

                        # Check if this person is already under punch cooldown
                        last_punch = self._last_punch_time.get(emp_id, 0.0)
                        if now - last_punch < PUNCH_COOLDOWN_SECONDS:
                            # Skip recognition timer if under cooldown, but still show normal green box
                            detections.append({
                                "location": orig_loc,
                                "name": name,
                                "emp_id": emp_id,
                                "confidence": match_emp["confidence"],
                                "status": "recognized"
                            })
                            continue

                        # If this matches our currently verifying employee
                        if self._verifying_emp_id == emp_id:
                            self._verifying_last_seen = now
                            duration = now - self._verifying_start_time
                            remaining = max(0.0, 3.0 - duration)
                            
                            if duration >= 3.0:
                                # Reset verification tracking so it doesn't trigger again immediately
                                self._verifying_emp_id = None
                                self._verifying_start_time = 0.0
                                self._verifying_last_seen = 0.0
                                
                                # Trigger the punch!
                                self._handle_matched_punch(match_emp, frame)
                            else:
                                # Update UI with verification progress
                                self.after(0, lambda n=name, r=remaining: self._update_verifying_status(n, r))
                        else:
                            # Start verification for this new employee
                            self._verifying_emp_id = emp_id
                            self._verifying_start_time = now
                            self._verifying_last_seen = now
                            self.after(0, lambda n=name: self._update_verifying_status(n, 3.0))

                        duration = now - self._verifying_start_time
                        remaining_seconds = max(0, int(3.99 - duration))

                        detections.append({
                            "location": orig_loc,
                            "name": f"{name} (Hold {remaining_seconds}s)",
                            "emp_id": emp_id,
                            "confidence": match_emp["confidence"],
                            "status": "recognized"
                        })
                    else:
                        detections.append({
                            "location": orig_loc,
                            "name": "Unknown",
                            "emp_id": None,
                            "confidence": 0,
                            "status": "unknown"
                        })

            # Check if the verifying employee has vanished
            if self._verifying_emp_id:
                emp_in_frame = any(d.get("emp_id") == self._verifying_emp_id for d in detections)
                if not emp_in_frame and (now - self._verifying_last_seen > 1.0):
                    self._verifying_emp_id = None
                    self._verifying_start_time = 0.0
                    self._verifying_last_seen = 0.0
                    self.after(0, self._clear_verifying_status)

            with self._detections_lock:
                self._detections = detections

    def _find_match(self, enc):
        """Compares face vector against loaded memory cache templates."""
        if not self._templates:
            return None

        best_match = None
        min_dist = 1.0

        # Iterate employees in template cache
        for temp in self._templates:
            samples = temp["face_samples"] or [temp["face_descriptor"]]
            
            # Compute Euclidean distance to all sample vectors
            distances = face_recognition.face_distance(samples, enc)
            local_min = np.min(distances) if len(distances) > 0 else 1.0
            
            if local_min < min_dist:
                min_dist = local_min
                best_match = temp

        if min_dist <= MATCH_TOLERANCE:
            confidence = int((1.0 - min_dist) * 100)
            return {
                "emp_id": best_match["emp_id"],
                "name": best_match["name"],
                "confidence": confidence,
                "distance": min_dist
            }
        return None

    # ── Punch Handling ────────────────────────────────────────────────────────

    def _handle_matched_punch(self, emp, matched_frame):
        """Processes punch events for recognized employees, including cooldowns and base64 upload."""
        emp_id = emp["emp_id"]
        name = emp["name"]
        now_ts = time.time()

        # Cooldown check
        last_punch = self._last_punch_time.get(emp_id, 0.0)
        if now_ts - last_punch < PUNCH_COOLDOWN_SECONDS:
            # Under cooldown, ignore match
            return

        # Trigger immediate punch locking
        self._last_punch_time[emp_id] = now_ts

        # Play warning beep if it was a recent duplicate or something else, but here we process punch
        # Convert matched webcam frame to base64 jpeg for photographic validation
        punch_photo_b64 = None
        try:
            # Resize matched frame to 320x240 for fast upload
            small_match = cv2.resize(matched_frame, (320, 240))
            _, buffer = cv2.imencode('.jpg', small_match)
            b64_str = base64.b64encode(buffer).decode('utf-8')
            punch_photo_b64 = f"data:image/jpeg;base64,{b64_str}"
        except Exception as e:
            print(f"[Scanner] Error encoding punch photo: {e}")

        # Post punch in background thread
        def punch_worker():
            success, res = sso_client.send_punch_to_server(emp_id, location="Face Recognition Terminal", punch_photo=punch_photo_b64)
            
            event_type = "check_in"
            api_msg = ""
            if success and isinstance(res, dict):
                server_type = res.get("punch_type")
                api_msg = res.get("message", "")
                if server_type == "out":
                    event_type = "check_out"
                elif server_type == "in":
                    event_type = "check_in"
                elif server_type == "already":
                    event_type = "already"
            else:
                # Fallback to local DB rules if offline
                if db.already_checked_in_today(emp_id) and not db.already_checked_out_today(emp_id):
                    event_type = "check_out"
                else:
                    event_type = "check_in"
                
                if not success:
                    api_msg = str(res)
                    if res == "Unauthorized":
                        self.after(0, self._handle_unauthorized)

            # Record locally in SQLite
            if event_type in ("check_in", "check_out"):
                db.log_attendance(emp_id, name, event_type, emp["confidence"])

            # Sound feedback
            if event_type == "already" or (success and isinstance(res, dict) and res.get("punch_type") == "already"):
                play_beep_warning()
            elif success:
                play_beep_success()
            else:
                play_beep_warning()

            # Schedule UI updates
            self.after(0, lambda: self._show_punch_card(emp, event_type, api_msg))

        threading.Thread(target=punch_worker, daemon=True).start()

    def _handle_unauthorized(self):
        try:
            self.master.master.check_auth()
        except Exception:
            pass

    def _show_punch_card(self, emp, event_type, api_msg):
        # Refresh logs list immediately
        self._load_recent_punches()

        # Display details in cards
        ts_now = datetime.now().strftime("%H:%M:%S")
        self._status_val.set("Biometrics Match Found!")
        self._status_lbl.config(fg=SUCCESS)
        self._name_var.set(emp["name"])

        if event_type == "check_in":
            status_text = "PUNCHED IN"
            fg_col = SUCCESS
        elif event_type == "check_out":
            status_text = "PUNCHED OUT"
            fg_col = SUCCESS
        elif event_type == "already":
            status_text = "ALREADY RECORDED"
            fg_col = WARNING
        else:
            status_text = "SUCCESS"
            fg_col = SUCCESS

        self._badge_var.set(f"✓  {status_text}   {ts_now}\n{api_msg}")
        self._badge_lbl.config(fg=fg_col)

        # Clear punch alert after 3 seconds
        self.after(3000, self._clear_punch_card)

    def _clear_punch_card(self):
        if self._running:
            self._status_val.set("Waiting for face...")
            self._status_lbl.config(fg=TEXT_SECONDARY)
            self._name_var.set("Scanning...")
            self._badge_var.set("")

    def _update_verifying_status(self, name, remaining):
        if not self._running:
            return
        if "✓" in self._badge_var.get() or "ALREADY" in self._badge_var.get():
            return
        self._status_val.set(f"Verifying face... {remaining:.1f}s")
        self._status_lbl.config(fg=ACCENT)
        self._name_var.set(name)

    def _clear_verifying_status(self):
        if not self._running:
            return
        if "✓" in self._badge_var.get() or "ALREADY" in self._badge_var.get():
            return
        self._status_val.set("Waiting for face...")
        self._status_lbl.config(fg=TEXT_SECONDARY)
        self._name_var.set("Scanning...")

    # ── UI Render Loop ────────────────────────────────────────────────────────

    def _ui_render_loop(self):
        """Runs on the Main UI thread. Renders webcam feed and overlays bounding boxes."""
        if not self._running:
            return

        frame = None
        with self._lock:
            if self._current_frame is not None:
                frame = self._current_frame.copy()

        if frame is not None:
            # Draw bounding boxes from active detections
            with self._detections_lock:
                active_detections = list(self._detections)

            for d in active_detections:
                top, right, bottom, left = d["location"]
                
                # Determine colors
                if d["status"] == "recognized":
                    color = (34, 197, 94)    # Green (BGR: 94, 197, 34)
                elif d["status"] == "unknown":
                    color = (239, 68, 68)    # Red (BGR: 68, 68, 239)
                else:
                    color = (245, 158, 11)   # Orange (BGR: 11, 158, 245)

                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                
                # Display tag label
                lbl_text = d["name"]
                if d["confidence"] > 0:
                    lbl_text += f" ({d['confidence']}%)"

                # Draw label banner
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                thickness = 1
                text_size = cv2.getTextSize(lbl_text, font, font_scale, thickness)[0]
                
                cv2.rectangle(frame, (left, bottom - text_size[1] - 8), (left + text_size[0] + 10, bottom), color, -1)
                cv2.putText(frame, lbl_text, (left + 5, bottom - 4), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

            # Convert to PIL Image for Tkinter rendering
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            
            self._video_lbl.imgtk = imgtk
            self._video_lbl.config(image=imgtk)

        # Loop the render
        self.after(33, self._ui_render_loop)
