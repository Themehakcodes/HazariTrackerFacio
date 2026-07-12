import http.server
import json
import secrets
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from threading import Thread
import db

# Port and redirect URI configured for local SSO callback
PORT = 5005
REDIRECT_URI = f"http://localhost:{PORT}/callback"
CLIENT_ID = "hazari_python_app"

# Module-level variables for thread communication
captured_code = None
captured_state = None
server_instance = None
expected_state = None
sso_thread = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles callback requests from the browser redirect."""
    
    def log_message(self, format, *args):
        # Suppress logging console noise
        return

    def do_GET(self):
        global captured_code, captured_state
        parsed_url = urllib.parse.urlparse(self.path)
        
        # Check if the request path matches the redirect URI callback path
        if parsed_url.path == "/callback":
            query_params = urllib.parse.parse_qs(parsed_url.query)
            captured_code = query_params.get("code", [None])[0]
            captured_state = query_params.get("state", [None])[0]

            # Return a clean authorization confirmation response page
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>HazariTracker Authentication</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        background-color: #f9fafb;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .card {
                        background-color: white;
                        padding: 2.5rem;
                        border-radius: 1.5rem;
                        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
                        text-align: center;
                        max-width: 400px;
                        border: 1px solid #f3f4f6;
                    }
                    .icon {
                        background-color: #f0fdf4;
                        color: #16a34a;
                        width: 3.5rem;
                        height: 3.5rem;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin: 0 auto 1.5rem;
                    }
                    h1 { color: #111827; font-size: 1.5rem; margin-bottom: 0.5rem; }
                    p { color: #4b5563; font-size: 0.95rem; line-height: 1.5; margin-bottom: 1.5rem; }
                    .close-msg { font-size: 0.85rem; color: #9ca3af; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="icon">
                        <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path>
                        </svg>
                    </div>
                    <h1>Sign In Successful!</h1>
                    <p>The Python desktop app has been authorized. You can safely close this browser window and return to the application.</p>
                    <div class="close-msg">This window will close automatically soon.</div>
                </div>
                <script>
                    setTimeout(function() { window.close(); }, 5000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode("utf-8"))
            
            # Start clean server shutdown in a separate thread to prevent lockup
            Thread(target=shutdown_server).start()
        else:
            self.send_response(404)
            self.end_headers()


def start_local_server():
    """Starts the temporary HTTP server to capture the callback."""
    global server_instance
    try:
        server_address = ("", PORT)
        server_instance = http.server.HTTPServer(server_address, CallbackHandler)
        server_instance.serve_forever()
    except Exception as e:
        print(f"[SSO] Local server error: {e}")


def shutdown_server():
    """Stops the local server."""
    global server_instance
    if server_instance:
        server_instance.shutdown()
        server_instance = None


def get_server_url():
    """Gets the configured base URL of the HazariTracker server."""
    url = db.get_setting("server_url")
    return url if url else "http://127.0.0.1:8000"


def set_server_url(url):
    """Sets the base URL of the HazariTracker server."""
    db.set_setting("server_url", url.strip().rstrip("/"))


def get_token():
    """Returns the stored Sanctum access token, or None if not authenticated."""
    return db.get_setting("sso_token")


def get_user_info():
    """Returns the stored user dictionary, or None."""
    user_str = db.get_setting("sso_user")
    if user_str:
        try:
            return json.loads(user_str)
        except Exception:
            return None
    return None


def is_authenticated():
    """Checks if the user has a stored authentication token."""
    return get_token() is not None


def sign_out():
    """Removes stored tokens and user details from the database, and clears cached data."""
    db.delete_setting("sso_token")
    db.delete_setting("sso_user")
    db.clear_all_data()


def start_sso_flow(on_success, on_error):
    """Starts the asynchronous SSO authentication flow in a background thread."""
    global sso_thread
    sso_thread = Thread(target=_run_sso_flow, args=(on_success, on_error), daemon=True)
    sso_thread.start()


def _run_sso_flow(on_success, on_error):
    global captured_code, captured_state, expected_state
    
    captured_code = None
    captured_state = None
    expected_state = secrets.token_hex(16)
    
    # 1. Start the local server
    server_thread = Thread(target=start_local_server, daemon=True)
    server_thread.start()
    
    # 2. Formulate authorize URL
    base_url = get_server_url()
    query_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": expected_state
    }
    authorize_url = f"{base_url}/sso/authorize?{urllib.parse.urlencode(query_params)}"
    
    # 3. Open system web browser
    try:
        webbrowser.open(authorize_url)
    except Exception as e:
        on_error(f"Failed to open web browser: {e}")
        shutdown_server()
        return

    # 4. Wait for local server to capture redirect
    # Wait for the server thread to finish (which happens when server_instance is shut down)
    server_thread.join(timeout=120)  # 2 minute timeout
    
    # Clean up server just in case
    shutdown_server()
    
    if captured_state != expected_state:
        on_error("CSRF State mismatch! The authentication request was rejected for security reasons.")
        return
        
    if not captured_code:
        on_error("Authentication timed out or was cancelled.")
        return
        
    # 5. Exchange code for token
    token_url = f"{base_url}/api/sso/token"
    payload = {
        "code": captured_code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            token_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
            if "access_token" in res_data:
                token = res_data["access_token"]
                user = res_data["user"]
                
                # Save to database
                db.set_setting("sso_token", token)
                db.set_setting("sso_user", json.dumps(user))
                
                on_success(user)
            else:
                on_error(res_data.get("error_description", "Failed to retrieve access token."))
                
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            res_err = json.loads(err_msg)
            on_error(res_err.get("error_description", f"HTTP Error {e.code}"))
        except Exception:
            on_error(f"Server returned error status {e.code}")
    except Exception as e:
        on_error(f"Network error connecting to server: {e}")


def send_punch_to_server(employee_id, location="Face Recognition Terminal", punch_photo=None):
    """Sends a face punch record to the Laravel server using the stored SSO token."""
    token = get_token()
    if not token:
        return False, "Not authenticated"
        
    base_url = get_server_url()
    punch_url = f"{base_url}/api/attendance/punch"
    
    payload = {
        "employee_id": str(employee_id),
        "location": location,
    }
    
    if punch_photo:
        payload["punch_photo"] = punch_photo
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            punch_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("success"):
                return True, res_data
            return False, res_data.get("message", "Unknown server error")
            
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token invalid/expired - sign out!
            sign_out()
            return False, "Unauthorized"
        err_msg = e.read().decode("utf-8")
        try:
            res_err = json.loads(err_msg)
            error_text = res_err.get("message") or res_err.get("error_description") or f"Server error: {e.code}"
            return False, error_text
        except Exception:
            return False, f"Server returned error code {e.code}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def sync_employees_from_server():
    """Fetches employees and face biometric templates from the server and updates local DB."""
    token = get_token()
    if not token:
        return False, "Not authenticated"

    base_url = get_server_url()
    url = f"{base_url}/api/employees"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if not res_data.get("success"):
                return False, res_data.get("message", "Failed to fetch employees")

            employees = res_data.get("employees", [])
            synced_count = 0
            
            for emp in employees:
                emp_id = str(emp.get("employee_id") or "").strip()
                name = str(emp.get("name") or "").strip()
                dept = str(emp.get("department") or "").strip()
                
                # Fetch face_registered and biometric details
                face_registered = emp.get("face_registered", False)
                face_descriptor = emp.get("face_descriptor")  # 128-D list of floats
                face_samples = emp.get("face_samples")        # list of 128-D float lists

                if not emp_id or not name:
                    continue

                # Serialize templates to JSON strings for SQLite storage
                desc_str = json.dumps(face_descriptor) if (face_registered and face_descriptor) else None
                samples_str = json.dumps(face_samples) if (face_registered and face_samples) else None

                existing = db.get_employee(emp_id)
                if existing:
                    db.update_employee_details(emp_id, name, dept)
                    if desc_str and samples_str:
                        db.update_face_template(emp_id, desc_str, samples_str)
                else:
                    db.add_employee(emp_id, name, dept, desc_str, samples_str)
                synced_count += 1

            return True, f"Successfully synced {synced_count} employee profiles"

    except urllib.error.HTTPError as e:
        if e.code == 401:
            sign_out()
            return False, "Unauthorized"
        return False, f"Server returned error code {e.code}"
    except Exception as e:
        return False, f"Sync connection failed: {e}"


def upload_face_template(employee_id, face_descriptor, face_samples=None, face_photos=None):
    """
    Uploads face biometric vectors and optional base64 captured photos to the server.
    
    Parameters:
      - employee_id: str
      - face_descriptor: list of 128 floats
      - face_samples: list of float lists (up to 5 samples)
      - face_photos: list of base64 dataUrls (e.g. data:image/jpeg;base64,...)
    """
    token = get_token()
    if not token:
        return False, "Not authenticated"

    base_url = get_server_url()
    url = f"{base_url}/api/employees/face"

    payload = {
        "employee_id": str(employee_id),
        "face_descriptor": face_descriptor
    }
    
    if face_samples:
        payload["face_samples"] = face_samples
        
    if face_photos:
        payload["face_photos"] = face_photos

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("success"):
                return True, res_data.get("message", "Success")
            return False, res_data.get("message", "Server error")

    except urllib.error.HTTPError as e:
        if e.code == 401:
            sign_out()
            return False, "Unauthorized"
        err_msg = e.read().decode("utf-8")
        try:
            res_err = json.loads(err_msg)
            return False, res_err.get("message", f"Server error: {e.code}")
        except Exception:
            return False, f"Server returned error code {e.code}"
    except Exception as e:
        return False, f"Connection failed: {e}"
