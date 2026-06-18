# HazariTracker Facio

Premium face recognition desktop client for the HazariTracker Laravel attendance platform.

## Features

- **SSO Authentication**: Zero configuration login using standard Authorization Code flow capturing Laravel Sanctum tokens on port `5005`.
- **64-bit Python Support**: High-performance image processing using OpenCV, NumPy, and the dlib-powered `face_recognition` library.
- **Biometric Matching**: Dynamic 128-D face encoding matching with dual average-descriptor and individual multi-sample validation.
- **Continuous Scanner**: Automated, thread-safe camera recognition loop that overlays green/red/orange boxes in real-time.
- **Photographic Proof**: Base64 frame capture uploaded automatically to the Laravel API for visual check-in validation.
- **Robust Cache**: SQLite persistence for local logs and precomputed templates to enable fast offline initialization and verification.

---

## Directory Structure

```
HazariTrackerFacio/
├── app.py              Main window runner with routing, navigation sidebar, and tray minimization
├── db.py               SQLite database layer (employees, attendance logs, settings key-value store)
├── sso_client.py       SSO local server, code token exchanger, employee sync, and punch uploads
├── theme.py            Orange/dark design tokens and typography matching HazariTracker Bio
├── version.py          Application version details
├── updater.py          Background updater checking GitHub releases
├── requirements.txt    Python dependencies file
└── pages/
    ├── __init__.py     Package definition
    ├── scanner.py      Live camera view, face detection/bounding boxes, and punch execution
    ├── enroll.py       Employee details form and interactive multi-pose Toplevel camera dialog
    ├── reports.py      Local date-wise reports, summaries, and CSV exporting
    └── sso.py          SSO connection settings and login cards
```

---

## Getting Started

### 1. Requirements

- **Python 3.11+ (64-bit)** (Required for face_recognition/dlib performance).
- Integrated or USB Webcam.

### 2. Installation

Install dependencies from requirements file:
```bash
pip install -r requirements.txt
```

### 3. Running the App

```bash
python app.py
```

---

## Biometric Enrollment Workflow

1. In the **Employees** tab, enter the Employee ID, Full Name, and Department.
2. Click **Start Face Scan** to open the capture dialog.
3. The dialog guides the user through **3 distinct poses**:
   - **Pose 1**: Look straight.
   - **Pose 2**: Tilt head slightly left/right.
   - **Pose 3**: Position closer/tilt head up/down.
4. On success, the 128-D vector coordinates are averaged and saved along with individual samples in SQLite and synced up to `/api/employees/face`.
