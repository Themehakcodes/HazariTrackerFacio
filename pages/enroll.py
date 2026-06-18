"""
pages/enroll.py
───────────────
Add New Employee — form + face scan dialog + employee list.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import base64
import cv2
import numpy as np
import face_recognition
from PIL import Image, ImageTk

import db
import sso_client
from theme import *


class EnrollPage(tk.Frame):

    def __init__(self, master, **kw):
        super().__init__(master, bg=BG_BASE, **kw)
        self._sync_in_progress = False
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Left: form ───────────────────────────────────────────────────────
        left = tk.Frame(self, bg=BG_SURFACE, padx=PAD_LG, pady=PAD_LG)
        left.pack(side="left", fill="both", expand=True,
                  padx=(PAD_MD, PAD_SM), pady=PAD_MD)

        tk.Label(left, text="Register Employee Face",
                 font=FONT_H2, bg=BG_SURFACE,
                 fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(left, text="Fill in details and scan face",
                 font=FONT_SMALL, bg=BG_SURFACE,
                 fg=TEXT_SECONDARY).pack(anchor="w")
        tk.Frame(left, bg=ACCENT, height=2).pack(fill="x", pady=(PAD_SM, PAD_LG))

        self._emp_id = self._field(left, "Employee ID  *", "e.g. EMP001")
        self._name   = self._field(left, "Full Name  *",   "e.g. Rahul Sharma")
        self._dept   = self._field(left, "Department",     "e.g. IT / Sales / HR")

        # Re-enroll checkbox
        self._re_enroll = tk.BooleanVar()
        tk.Checkbutton(left, text="Re-enroll (overwrite existing face template)",
                       variable=self._re_enroll,
                       bg=BG_SURFACE, fg=TEXT_SECONDARY,
                       selectcolor=BG_INPUT,
                       activebackground=BG_SURFACE,
                       activeforeground=TEXT_SECONDARY,
                       font=FONT_SMALL, cursor="hand2").pack(anchor="w", pady=(PAD_SM, 0))

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=PAD_MD)

        # Buttons
        row = tk.Frame(left, bg=BG_SURFACE)
        row.pack(fill="x")
        
        self._btn = self._create_hover_btn(row, "📸  Start Face Scan",
                                           ACCENT, TEXT_PRIMARY, self._start_face_capture,
                                           hover_bg=ACCENT_HOVER)
        self._btn.pack(side="left", padx=(0, PAD_SM))
        
        clear_btn = self._create_hover_btn(row, "Clear",
                                            BG_ELEVATED, TEXT_PRIMARY, self._clear,
                                            hover_bg="#2F2F2F")
        clear_btn.pack(side="left")

        # Status
        self._status_var = tk.StringVar(value="")
        self._status_lbl = tk.Label(left, textvariable=self._status_var,
                                    font=FONT_BODY, bg=BG_SURFACE,
                                    fg=TEXT_SECONDARY)
        self._status_lbl.pack(anchor="w", pady=(PAD_MD, 0))

        # ── Right: employee list ──────────────────────────────────────────────
        right = tk.Frame(self, bg=BG_BASE, padx=PAD_MD, pady=PAD_MD)
        right.pack(side="right", fill="both", expand=True,
                   padx=(PAD_SM, PAD_MD), pady=PAD_MD)

        # Header for Enrolled Employees with title and refresh button
        header_row = tk.Frame(right, bg=BG_BASE)
        header_row.pack(fill="x", anchor="w", pady=(PAD_SM, 0))
        
        tk.Label(header_row, text="Enrolled Employees",
                 font=FONT_H3, bg=BG_BASE,
                 fg=TEXT_SECONDARY).pack(side="left")
                 
        self._refresh_btn = tk.Button(header_row, text=" ⟳ ", font=FONT_BODY,
                                      bg=BG_BASE, fg=TEXT_SECONDARY,
                                      activebackground=BG_ELEVATED,
                                      activeforeground=TEXT_PRIMARY,
                                      relief="flat", bd=0, cursor="hand2",
                                      command=self._manual_local_refresh)
        self._refresh_btn.pack(side="left", padx=(PAD_SM, 0))
        self._refresh_btn.bind("<Enter>", lambda e: self._refresh_btn.config(fg=ACCENT))
        self._refresh_btn.bind("<Leave>", lambda e: self._refresh_btn.config(fg=TEXT_SECONDARY))

        # Status label for animated spinner next to the refresh icon
        self._refresh_status_lbl = tk.Label(header_row, text="", font=FONT_SMALL,
                                            bg=BG_BASE, fg=ACCENT)
        self._refresh_status_lbl.pack(side="left", padx=(PAD_MD, 0))

        # Create a frame with 1px border to wrap Treeview
        tree_border = tk.Frame(right, bg=BORDER, bd=0, padx=1, pady=1)
        tree_border.pack(fill="both", expand=True, pady=(PAD_SM, PAD_SM))

        tree_frame = tk.Frame(tree_border, bg=BG_SURFACE)
        tree_frame.pack(fill="both", expand=True)

        cols = ("emp_id", "name", "dept", "enrolled")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  height=10, selectmode="browse")
        for col, w, label in [
            ("emp_id",   70,  "ID"),
            ("name",    160,  "Name"),
            ("dept",    100,  "Department"),
            ("enrolled", 100, "Enrolled At"),
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Action buttons row
        btn_row = tk.Frame(right, bg=BG_BASE)
        btn_row.pack(fill="x", pady=(PAD_SM, 0))

        self._sync_btn = self._create_hover_btn(btn_row, "🔄  Sync from Cloud",
                                                 ACCENT, TEXT_PRIMARY, self._sync_from_cloud,
                                                 hover_bg=ACCENT_HOVER, font=FONT_SMALL,
                                                 padx=PAD_SM, pady=6)
        self._sync_btn.pack(side="left")

        remove_btn = self._create_hover_btn(btn_row, "✕  Remove Selected",
                                             DANGER, TEXT_PRIMARY, self._delete_selected,
                                             hover_bg="#EF5F5F", font=FONT_SMALL,
                                             padx=PAD_SM, pady=6)
        remove_btn.pack(side="right")

        self.refresh()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _create_hover_btn(self, parent, text, bg, fg, command, hover_bg=None, font=FONT_H3, padx=PAD_MD, pady=PAD_SM) -> tk.Button:
        btn = tk.Button(parent, text=text, bg=bg, fg=fg, font=font,
                        activebackground=hover_bg or bg,
                        activeforeground=fg,
                        relief="flat", bd=0, padx=padx, pady=pady,
                        cursor="hand2", command=command)
        
        h_bg = hover_bg or bg
        if not hover_bg:
            if bg == ACCENT:
                h_bg = ACCENT_HOVER
            elif bg == DANGER:
                h_bg = "#EF5F5F"
            elif bg == BG_ELEVATED:
                h_bg = "#2F2F2F"
            elif bg == BG_SURFACE:
                h_bg = BG_ELEVATED
            else:
                h_bg = bg
                
        btn.bind("<Enter>", lambda e: btn.config(bg=h_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _on_tree_select(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        vals = self._tree.item(sel[0])["values"]
        if vals:
            self._emp_id.config(foreground=TEXT_PRIMARY)
            self._emp_id.delete(0, "end")
            self._emp_id.insert(0, vals[0])

            self._name.config(foreground=TEXT_PRIMARY)
            self._name.delete(0, "end")
            self._name.insert(0, vals[1])

            self._dept.config(foreground=TEXT_PRIMARY)
            self._dept.delete(0, "end")
            self._dept.insert(0, vals[2] if vals[2] != "—" else "")

            is_enrolled = (vals[3] != "No")
            self._re_enroll.set(is_enrolled)

    def refresh(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for emp in db.get_all_employees():
            enrolled_status = (emp["enrolled_at"] or "")[:10] if emp["is_enrolled"] else "No"
            self._tree.insert("", "end", values=(
                emp["emp_id"], emp["name"],
                emp["department"] or "—",
                enrolled_status,
            ))

    def _manual_local_refresh(self):
        self.refresh()
        if sso_client.is_authenticated():
            if self._sync_in_progress:
                return
                
            self._sync_in_progress = True
            self._refresh_btn.config(state="disabled", text=" ⏳ ")
            self._animate_spinner()
            
            def run_sync():
                ok, _ = sso_client.sync_employees_from_server()
                def on_sync_done():
                    self._sync_in_progress = False
                    self.refresh()
                self.after(0, on_sync_done)
            threading.Thread(target=run_sync, daemon=True).start()

    def _field(self, parent, label: str, ph: str = "") -> tk.Entry:
        tk.Label(parent, text=label, font=FONT_SMALL,
                 bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(anchor="w", pady=(PAD_SM, 4))
        
        wrapper = tk.Frame(parent, bg=BORDER, bd=0, padx=1, pady=1)
        wrapper.pack(fill="x", pady=(0, PAD_MD))
        
        inner = tk.Frame(wrapper, bg=BG_INPUT, bd=0, padx=8, pady=6)
        inner.pack(fill="x")
        
        e = tk.Entry(inner, font=FONT_BODY, bg=BG_INPUT, fg=TEXT_PRIMARY,
                     insertbackground=TEXT_PRIMARY, bd=0, relief="flat",
                     highlightthickness=0)
        e.pack(fill="x")
        
        def on_focus_in(event, w=wrapper, entry=e):
            w.config(bg=ACCENT)
            if entry.get() == ph:
                entry.delete(0, "end")
                entry.config(foreground=TEXT_PRIMARY)
                
        def on_focus_out(event, w=wrapper, entry=e):
            w.config(bg=BORDER)
            if not entry.get():
                entry.insert(0, ph)
                entry.config(foreground=TEXT_DISABLED)

        e.bind("<FocusIn>", on_focus_in)
        e.bind("<FocusOut>", on_focus_out)
        
        if ph:
            e.insert(0, ph)
            e.config(foreground=TEXT_DISABLED)
            
        return e

    def _get(self, e: tk.Entry, ph: str) -> str:
        v = e.get().strip()
        return "" if v == ph else v

    def _clear(self):
        for e, ph in [(self._emp_id, "e.g. EMP001"),
                      (self._name,   "e.g. Rahul Sharma"),
                      (self._dept,   "e.g. IT / Sales / HR")]:
            e.delete(0, "end")
            e.insert(0, ph)
            e.config(foreground=TEXT_DISABLED)
        self._status_var.set("")
        self._btn.config(state="normal", text="📸  Start Face Scan")

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        emp_id = self._tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Remove Employee",
                               f"Remove employee {emp_id}? This cannot be undone."):
            db.delete_employee(emp_id)
            self.refresh()

    def _sync_from_cloud(self):
        if not sso_client.is_authenticated():
            messagebox.showwarning("Sync Warning", "Please configure Cloud Sync first.")
            return

        if self._sync_in_progress:
            return

        self._sync_in_progress = True
        self._sync_btn.config(state="disabled", text="⏳  Syncing…")
        self._refresh_btn.config(state="disabled", text=" ⏳ ")
        self._animate_spinner()
        
        def run_sync():
            ok, msg = sso_client.sync_employees_from_server()
            def on_sync_done():
                self._sync_in_progress = False
                self._sync_btn.config(state="normal", text="🔄  Sync from Cloud")
                if ok:
                    messagebox.showinfo("Sync Success", msg)
                    self.refresh()
                else:
                    messagebox.showerror("Sync Error", msg)
            self.after(0, on_sync_done)

        threading.Thread(target=run_sync, daemon=True).start()

    def _animate_spinner(self, frame_idx=0):
        if not self._sync_in_progress:
            self._refresh_btn.config(state="normal", text=" ⟳ ")
            self._refresh_status_lbl.config(text="")
            return
            
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        char = spinner_chars[frame_idx % len(spinner_chars)]
        self._refresh_status_lbl.config(text=f"{char} Syncing cloud templates...")
        
        self.after(80, lambda: self._animate_spinner(frame_idx + 1))

    # ── Face Capture Dialog ───────────────────────────────────────────────────

    def _start_face_capture(self):
        emp_id = self._get(self._emp_id, "e.g. EMP001")
        name   = self._get(self._name,   "e.g. Rahul Sharma")
        dept   = self._get(self._dept,   "e.g. IT / Sales / HR")

        if not emp_id or not name:
            messagebox.showwarning("Missing Fields",
                                   "Employee ID and Full Name are required.")
            return

        if not self._re_enroll.get() and db.get_employee(emp_id):
            messagebox.showwarning("Already Enrolled",
                                   f"{emp_id} already exists. Tick Re-enroll to overwrite.")
            return

        # Open Face Scan Toplevel Dialog!
        FaceCaptureDialog(self, emp_id, name, dept, self._re_enroll.get())


class FaceCaptureDialog(tk.Toplevel):
    def __init__(self, parent, emp_id, name, department, overwrite):
        super().__init__(parent)
        self.parent = parent
        self.emp_id = emp_id
        self.name = name
        self.department = department
        self.overwrite = overwrite

        self.title("Face Biometric Capture")
        self.geometry("740x620")
        self.resizable(False, False)
        self.configure(bg=BG_BASE)
        self.transient(parent)
        self.grab_set()

        # Capture steps
        self.step = 0
        self.encodings = []
        self.photos_base64 = []
        self.is_running = True
        self.camera = None
        self.auto_scan_active = False
        self.last_capture_time = 0

        self._build_ui()
        self._start_camera()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG_SURFACE, pady=PAD_MD, padx=PAD_LG)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Scanning Face: {self.name} ({self.emp_id})", font=FONT_H2, bg=BG_SURFACE, fg=TEXT_PRIMARY).pack(anchor="w")
        
        self.step_label = tk.Label(hdr, text="Pose 1: Look directly into the camera.", font=FONT_BODY, bg=BG_SURFACE, fg=ACCENT)
        self.step_label.pack(anchor="w", pady=(PAD_XS, 0))

        # Camera view label
        self.video_container = tk.Frame(self, bg="black", bd=1, relief="solid", width=640, height=400)
        self.video_container.pack(pady=PAD_MD)
        self.video_container.pack_propagate(False)

        self.video_lbl = tk.Label(self.video_container, bg="black", text="Starting camera...")
        self.video_lbl.pack(fill="both", expand=True)

        # Controls row
        ctrl = tk.Frame(self, bg=BG_BASE)
        ctrl.pack(fill="x", padx=PAD_LG, pady=PAD_SM)

        self.status_lbl = tk.Label(ctrl, text="Position your face inside the screen...", font=FONT_BODY, bg=BG_BASE, fg=TEXT_SECONDARY)
        self.status_lbl.pack(side="left")

        self.btn_capture = tk.Button(ctrl, text="📸  Start Auto Scan", font=FONT_H3, bg=ACCENT, fg=TEXT_PRIMARY,
                                     activebackground=ACCENT_HOVER, activeforeground=TEXT_PRIMARY,
                                     relief="flat", bd=0, padx=PAD_LG, pady=8, cursor="hand2", command=self._start_auto_scan)
        self.btn_capture.pack(side="right")

    def _start_camera(self):
        print("[Enroll] Initialising camera capture...")
        try:
            cam_idx_str = db.get_setting("camera_index")
            cam_idx = int(cam_idx_str) if cam_idx_str is not None else 0
        except Exception:
            cam_idx = 0
        print(f"[Enroll] Requesting camera index: {cam_idx}")
        self.camera = cv2.VideoCapture(cam_idx)
        if not self.camera.isOpened():
            print(f"[Enroll] Error: Could not open camera at index {cam_idx}")
            self.video_lbl.config(text="⚠️ Failed to open webcam.\nPlease check connection.")
            self.btn_capture.config(state="disabled")
            return
        print(f"[Enroll] Camera index {cam_idx} opened successfully.")

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Start capture update thread loop
        threading.Thread(target=self._camera_loop, daemon=True).start()

    def _play_beep(self):
        try:
            import winsound
            winsound.Beep(2000, 150)
        except Exception:
            pass

    def _start_auto_scan(self):
        self.auto_scan_active = True
        self.step = 0
        self.encodings = []
        self.photos_base64 = []
        self.last_capture_time = 0
        self.btn_capture.config(state="disabled", text="⚡ Auto-Scanning...")
        self.step_label.config(text="Pose 1: Look directly into the camera.")

    def _camera_loop(self):
        poses_instr = [
            "Pose 1: Look directly into the camera.",
            "Pose 2: Tilt your head slightly to the left/right.",
            "Pose 3: Move closer / tilt head up or down."
        ]
        
        while self.is_running and self.camera:
            ret, frame = self.camera.read()
            if not ret:
                time.sleep(0.03)
                continue

            # Mirror frame for intuitive view
            frame = cv2.flip(frame, 1)
            self.current_frame = frame.copy()

            # Process frame for UI
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Detect face locally for live bounding box
            small_rgb = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
            locations = face_recognition.face_locations(small_rgb, model="hog")

            # Draw box if face detected
            if locations:
                top, right, bottom, left = locations[0]
                # Scale back up
                top, right, bottom, left = top * 2, right * 2, bottom * 2, left * 2
                
                # Check if we should capture this frame
                now = time.time()
                if self.auto_scan_active and (now - self.last_capture_time > 2.0):
                    # We have a face, let's encode it
                    full_loc = [(top, right, bottom, left)]
                    encs = face_recognition.face_encodings(rgb, full_loc, num_jitters=3)
                    if encs:
                        self.encodings.append(encs[0].tolist())
                        
                        # Save photo
                        _, buffer = cv2.imencode('.jpg', frame)
                        b64_str = base64.b64encode(buffer).decode('utf-8')
                        self.photos_base64.append(f"data:image/jpeg;base64,{b64_str}")
                        
                        self.last_capture_time = now
                        self.step += 1
                        
                        # Play beep sound
                        self._play_beep()
                        
                        # Update UI
                        if self.step >= 3:
                            self.auto_scan_active = False
                            self._update_status_thread(f"Pose {self.step}/3 captured! Finalising...", SUCCESS)
                            self.after(0, self._finalize_registration)
                        else:
                            next_instr = poses_instr[self.step]
                            self._update_status_thread(f"Pose {self.step}/3 captured! Prepare for next pose.", SUCCESS)
                            self.after(0, lambda s=self.step, instr=next_instr: self.step_label.config(text=f"Pose {s+1}: {instr}"))
                
                if self.auto_scan_active:
                    self._update_status_thread(f"Auto-scanning: Keep position (Pose {self.step+1}/3)...", SUCCESS)
                else:
                    self._update_status_thread("Face detected. Ready to scan.", SUCCESS)
                
                cv2.rectangle(rgb, (left, top), (right, bottom), (255, 107, 0), 2)
            else:
                if self.auto_scan_active:
                    self._update_status_thread(f"Awaiting face detection for Pose {self.step+1}/3...", WARNING)
                else:
                    self._update_status_thread("Adjust position until face is detected...", TEXT_SECONDARY)

            # Render in label
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            
            if self.is_running:
                self.video_lbl.imgtk = imgtk
                self.video_lbl.config(image=imgtk)
            
            time.sleep(0.03)

    def _update_status_thread(self, text, color):
        if self.is_running:
            self.after(0, lambda: self.status_lbl.config(text=text, fg=color))

    def _finalize_registration(self):
        self.is_running = False
        if self.camera:
            self.camera.release()
            self.camera = None

        self.step_label.config(text="Processing and uploading biometric models...")
        self.status_lbl.config(text="Syncing with portal...", fg=INFO)

        def sync_worker():
            # 1. Compute average descriptor vector
            avg_descriptor = np.mean(self.encodings, axis=0).tolist()
            
            # 2. Upload template to Laravel Server
            upload_ok = True
            upload_msg = ""
            if sso_client.is_authenticated():
                upload_ok, upload_msg = sso_client.upload_face_template(
                    employee_id=self.emp_id,
                    face_descriptor=avg_descriptor,
                    face_samples=self.encodings,
                    face_photos=self.photos_base64
                )

            # 3. Save to local SQLite database
            db_ok = True
            if upload_ok:
                desc_str = json.dumps(avg_descriptor)
                samples_str = json.dumps(self.encodings)
                
                if self.overwrite and db.get_employee(self.emp_id):
                    db.update_face_template(self.emp_id, desc_str, samples_str)
                else:
                    db_ok = db.add_employee(self.emp_id, self.name, self.department, desc_str, samples_str)

            def done():
                self.grab_release()
                self.destroy()
                
                if not upload_ok:
                    self.parent._status_var.set(f"Cloud upload failed: {upload_msg}")
                    self.parent._status_lbl.config(fg=DANGER)
                    messagebox.showerror("Cloud Sync Error", f"Failed to upload face to cloud:\n{upload_msg}")
                elif not db_ok:
                    self.parent._status_var.set("Local DB error: Employee ID already exists.")
                    self.parent._status_lbl.config(fg=DANGER)
                    messagebox.showerror("DB Error", "Employee ID already exists. Tick Re-enroll to overwrite.")
                else:
                    self.parent._status_var.set(f"✓ {self.name} enrolled successfully!")
                    self.parent._status_lbl.config(fg=SUCCESS)
                    self.parent.refresh()
                    messagebox.showinfo("Success", f"Face template for {self.name} registered and synced successfully!")

            self.after(0, done)

        threading.Thread(target=sync_worker, daemon=True).start()

    def _on_close(self):
        self.is_running = False
        if self.camera:
            self.camera.release()
            self.camera = None
        self.grab_release()
        self.destroy()
