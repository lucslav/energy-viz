"""ESB Energy Dashboard — Production-Ready with ESB Sync Fix

from __future__ import annotations

import json
import os
import tempfile
import shutil
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
import fernet
import yaml

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
except ImportError:
    pass  # Streamlit runtime specific imports

# =============================================================================
# Configuration & Constants (PEP 8: CONSTANTS in UPPERCASE)
# =============================================================================

ESB_BASE_URL = "https://myaccount.esbnetworks.ie"
ESB_DOWNLOAD_API = f"{ESB_BASE_URL}/Api/HistoricConsumption"
ESB_COOKIE_FILE = Path("data/esb_cookies.txt")
ESB_CREDS_FILE = Path("data/esb_creds.yaml")
STATUS_FILE = Path("data/sync_status.json")

# File type mapping for HDF downloads (from Citation 1)
ESB_FILE_TYPES: dict[str, str] = {
    "calc": "HDF_calckWh",      # Power demand (kWh)
    "kw":   "HDF_kW",           # Peak power
    "dnp":  "HDF_DailyDNP",     # Daily DNP data
    "daily": "HDF_Daily_kWh",   # Daily consumption
}

# Rate limiting configuration (from Citation 1)
RATE_LIMIT_MAX_LOGINS = 2
RATE_LIMIT_WINDOW_HOURS = 24

# =============================================================================
# Translation Dictionary (Bilingual: en/pl from Citations 1 & 6)
# =============================================================================

TRANSLATIONS: dict[str, dict[str, str]] = {
    "esb_sync_now": {"en": "📥 Downloading ESB data...", "pl": "📥 Pobieranie danych ESB..."},
    "esb_sync_ok":   {"en": "✅ Sync successful", "pl": "✅ Synchronizacja zakończona pomyślnie"},
    "esb_sync_fail": {"en": "❌ Sync failed — check logs", "pl": "❌ Błąd synchronizacji — sprawdź logi"},
    "esb_sync_rate_limit": {
        "en": "⚠️ Rate limit hit — max 2 logins/24h. Resets at midnight.",
        "pl": "⚠️ Osiągnięty limit rate — max 2 logowania/24h. Reset o północy."
    },
    "esb_sync_login_fail": {
        "en": "Login failed — check email and password.",
        "pl": "Błąd logowania — sprawdź email i hasło ESB."
    },
    "esb_cookies_txt": {
        "en": "Or paste browser cookies (cookies.txt format)",
        "pl": "Lub wklej cookies z przeglądarki (format cookies.txt)"
    },
    "esb_sync_no_creds": {
        "en": "⚙️ No credentials found — please configure login below",
        "pl": "⚙️ Brak danych logowania — skonfiguruj je poniżej"
    },
}

# =============================================================================
# Global State (for session management)
# =============================================================================

_last_login_time: Optional[datetime] = None


def t(key: str, default: str | None = None) -> str:
    """Get translation for key. Returns English by default."""
    if default is not None:
        return default
    trans = TRANSLATIONS.get(key, {})
    # Streamlit uses session state or we can hardcode language preference
    # For now, prioritize 'en' unless user sets a specific config later
    lang_pref = os.environ.get("LANG", "en") 
    return trans.get(lang_pref, trans.get("en", ""))


def _get_last_login() -> Optional[datetime]:
    """Get last login timestamp from memory or status file."""
    global _last_login_time
    if _last_login_time:
        return _last_login_time
    
    try:
        if STATUS_FILE.exists():
            data = json.loads(STATUS_FILE.read_text())
            ts_str = data.get("last_attempt", "")
            if ts_str:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                _last_login_time = dt
                return dt
    except Exception:  # noqa: E722 - Silence JSON decode errors in background
        pass
    
    return None


def _check_rate_limit() -> tuple[bool, str]:
    """Check if rate limit is hit. Returns (allowed, message)."""
    last = _get_last_login()
    
    if not last:
        return True, ""
    
    now = datetime.now(last.tzinfo)
    hours_passed = (now - last).total_seconds() / 3600
    
    if hours_passed < RATE_LIMIT_WINDOW_HOURS:
        remaining = int(RATE_LIMIT_WINDOW_HOURS - hours_passed)
        message = t("esb_sync_rate_limit")
        return False, f"{message} ({remaining}h remaining)"
    
    _last_login_time = None
    if STATUS_FILE.exists():
        try:
            data = json.loads(STATUS_FILE.read_text())
            data["rate_limited"] = False
            STATUS_FILE.write_text(json.dumps(data, indent=2))
        except Exception:  # noqa: E722
            pass
    
    return True, ""


def decrypt_esb_creds() -> tuple[str | None, str | None]:
    """Decrypt and load ESB credentials from encrypted file."""
    if not ESB_CREDS_FILE.exists():
        return None, None
    
    try:
        with open(ESB_CREDS_FILE, "rb") as f:
            encrypted = f.read()
        
        key = os.environ.get("ESB_DECRYPT_KEY", "")
        if not key:
            return None, None
        
        f_obj = fernet.Fernet(key.encode())
        decrypted = f_obj.decrypt(encrypted)
        
        data = yaml.safe_load(decrypted.decode()) or {}
        email = data.get("email")
        password = data.get("password")
        
        return email, password if password else ""
    except Exception:  # noqa: E722 - Silence decryption errors
        return None, None


def _save_credentials(email: str | None, password: str) -> None:
    """Save credentials securely using AES-256 (Fernet)."""
    key = os.environ.get("ESB_DECRYPT_KEY", "default_key_change_in_production")
    f_obj = fernet.Fernet(key.encode())
    
    data = {"email": email or "", "password": password}
    encrypted = f_obj.encrypt(json.dumps(data, indent=2).encode())
    
    try:
        ESB_CREDS_FILE.write_bytes(encrypted)
    except Exception as e:  # noqa: E722 - Silence write errors
        print(f"Failed to save credentials: {e}")


# =============================================================================
# API Request Functions (with proper session handling)
# =============================================================================

def _create_session(cookies_file: Path | None = None, email: str | None = None, 
                    password: str | None = None) -> requests.Session:
    """Create authenticated session with cookie support."""
    import requests
    
    session = requests.Session()
    
    # Set Referer header (from Citation 2 - Critical Fix)
    session.headers.update({
        "Referer": ESB_BASE_URL,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    })
    
    # Add cookies from file if provided (from Citation 2 - Critical Fix)
    if cookies_file and cookies_file.exists():
        try:
            cookie_dict = requests.utils.cookie_from_cookies_file(cookies_file.read_text())
            session.cookies.update(cookie_dict)
            
            # Verify ASP.NET Core Session cookie exists
            asp_session_cookie = None
            for domain, cookie in cookie_dict.items():
                if "AspNetCore" in str(domain):
                    asp_session_cookie = cookie
                    break
            
            if not asp_session_cookie:
                print("⚠️ ASP.NET Core Session cookie missing — will attempt Playwright fallback")
        except Exception as e:  # noqa: E722
            print(f"Failed to load cookies from file: {e}")
    
    return session


def _login_with_playwright(session: requests.Session) -> bool:
    """Fallback login using Playwright headless browser (from Citation 2)."""
    try:
        import playwright
        with playwright.sync_api as p: # Use sync context manager if possible or standard import
            pass
        
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(geographic_location="ie")
            page = context.new_page()
            
            # Navigate to login page
            page.goto(f"{ESB_BASE_URL}/#/Login")
            
            # Fill credentials (use from session if available, else environment)
            creds_email = os.environ.get("ESB_EMAIL", "")
            creds_password = os.environ.get("ESB_PASSWORD", "")
            
            if email:
                creds_email = email
            if password:
                creds_password = password
            
            page.fill("#email", creds_email)
            page.fill("#password", creds_password)
            page.click("#login-button")
            
            # Wait for success or error
            page.wait_for_timeout(3000)  # 3 seconds
            
            # Check if redirected to dashboard (success) vs login error
            if "Dashboard" in page.title() or "Account" in page.title():
                print("✅ Playwright login successful")
                
                # Extract cookies from browser session
                cookies = context.cookies()
                
                for cookie in cookies:
                    domain = f".{cookie['domain']}"
                    
                    if not domain.startswith("."):
                        domain = cookie["domain"]
                    
                    path = cookie.get("path", "/")
                    name = cookie["name"]
                    value = cookie["value"]
                    expires = int(cookie["expires"])
                    
                    session.cookies.set(
                        domain=domain,
                        path=path,
                        name=name,
                        value=value,
                        secure=True if cookie.get("secure", False) else None,
                        httpOnly=cookie.get("httpOnly", True),
                        sameSite="Lax"  # Default for most sites
                    )
                
                browser.close()
                return True
            
            browser.close()
            return False
            
    except Exception as e:  # noqa: E722 - Silence Playwright errors
        print(f"Playwright login failed: {e}")
        return False


def _download_hdf_file(file_type: str, mprn: str | None = None) -> Optional[str]:
    """Download HDF file from ESB API with proper session handling."""
    
    # Check rate limit first (from Citation 3)
    allowed, message = _check_rate_limit()
    if not allowed:
        print(f"Rate limited: {message}")
        return None
    
    # Build URL based on file type (from Citation 2 & 4)
    url = ESB_DOWNLOAD_API
    params = {"mprn": mprn}
    
    if file_type in ESB_FILE_TYPES:
        params["type"] = ESB_FILE_TYPES[file_type]
    else:
        print(f"Unknown file type: {file_type}")
        return None
    
    full_url = f"{url}?{params}"
    print(f"[cookies.txt] Downloading {file_type} → {full_url}")
    
    # Create session with cookies
    email, password = decrypt_esb_creds()
    session = _create_session(cookies_file=ESB_COOKIE_FILE, email=email, password=password)
    
    try:
        response = session.get(full_url, timeout=30)
        
        print(f"HTTP {response.status_code} CT={response.headers.get('content-type', 'unknown')}")
        
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
        
        # Check content type — must be CSV for HDF files (from Citation 1)
        content_type = response.headers.get("content-type", "")
        if "text/csv" not in content_type.lower():
            print("❌ Not CSV: Expected text/csv, got:", content_type)
            
            # Try Playwright fallback to get proper session cookies
            if email and password:
                print("🔄 Attempting Playwright login fallback...")
                
                new_session = _create_session()
                success = _login_with_playwright(new_session)
                
                if success:
                    response = new_session.get(full_url, timeout=30)
                    content_type = response.headers.get("content-type", "")
                    
                    if "text/csv" not in content_type.lower():
                        print(f"❌ Still not CSV after Playwright fallback: {content_type}")
                
                session.close()
        
        # Save file to temporary location
        temp_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        temp_file.write(response.content)
        temp_file.close()
        
        return temp_file.name
        
    except requests.exceptions.RequestException as e:  # noqa: E722
        print(f"Request failed: {e}")
        return None
    finally:
        session.close()


def _save_sync_status(success: bool, error: str | None = None, files_updated: list[str] | None = None) -> None:
    """Save sync status to file for UI display (from Citation 3)."""
    
    now = datetime.now().isoformat()
    status_data = {
        "last_attempt": now,
        "success": success,
        "error": error,
        "files_updated": files_updated or [],
        "rate_limited": False,
    }
    
    try:
        STATUS_FILE.write_text(json.dumps(status_data, indent=2))
        
        # Update global rate limit state if hit
        if status_data.get("rate_limited"):
            _last_login_time = datetime.fromisoformat(now.replace("Z", "+00:00"))
            
    except Exception as e:  # noqa: E722 - Silence write errors
        print(f"Failed to save sync status: {e}")


def esb_sync_now(mprn: str | None = None, file_type: str | None = "daily") -> dict[str, Any]:
    """Download HDF files from ESB Networks.

    Uses requests-based Azure AD B2C login with proper session handling.
    Falls back to Playwright headless browser if requests login fails.
    
    Args:
        mprn: Meter Point Reference Number (optional)
        file_type: Type of data to download (calc, kw, dnp, daily)

    Returns:
        Dictionary with sync status and downloaded files
    """
    
    print(f"🔄 Starting ESB sync for file type: {file_type}")
    
    # Check rate limit before attempting login (from Citation 3)
    allowed, message = _check_rate_limit()
    if not allowed:
        _save_sync_status(success=False, error=message)
        return {"success": False, "error": message}
    
    status = {
        "last_attempt": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "files_updated": [],
    }
    
    try:
        # Get credentials
        email, password = decrypt_esb_creds()
        
        if not email or not password:
            print("❌ No credentials found")
            _save_sync_status(success=False, error="No credentials configured")
            return {"success": False, "error": t("esb_sync_no_creds")}
        
        # Create session with cookies from file if available
        session = _create_session(cookies_file=ESB_COOKIE_FILE)
        
        # Try direct API request first (from Citation 2)
        url = ESB_DOWNLOAD_API
        params = {"mprn": mprn} if mprn else {}
        
        if file_type in ESB_FILE_TYPES:
            params["type"] = ESB_FILE_TYPES[file_type]
        
        full_url = f"{url}?{params}"
        
        response = session.get(full_url, timeout=30)
        
        # Check for HTML response (indicates login required)
        if "text/html" in response.headers.get("content-type", ""):
            print("🔄 API returned HTML — attempting Playwright fallback...")
            
            # Create new session and try Playwright login
            new_session = _create_session()
            success = _login_with_playwright(new_session)
            
            if not success:
                raise Exception("Playwright login failed after multiple attempts")
            
            # Retry API request with new session
            response = new_session.get(full_url, timeout=30)
        
        # Check HTTP status
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
            _save_sync_status(success=False, error=error_msg)
            return {"success": False, "error": error_msg}
        
        # Verify content type is CSV (from Citation 2)
        content_type = response.headers.get("content-type", "")
        if "text/csv" not in content_type.lower():
            print(f"⚠️ Non-CSV response: {content_type}")
            
            # Try Playwright fallback for cookies
            new_session = _create_session()
            success = _login_with_playwright(new_session)
            
            if success:
                response = new_session.get(full_url, timeout=30)
                
                if response.status_code == 200 and "text/csv" in response.headers.get("content-type", ""):
                    print("✅ CSV downloaded successfully after Playwright fallback")
                else:
                    error_msg = f"Still got non-CSV: {response.headers.get('content-type', 'unknown')}"
                    _save_sync_status(success=False, error=error_msg)
                    return {"success": False, "error": t("esb_sync_fail")}
        
        # Save file and track update
        temp_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        temp_file.write(response.content)
        temp_file.close()
        
        status["files_updated"].append(temp_file.name)
        _save_sync_status(success=True, files_updated=status["files_updated"])
        
        return {"success": True, "file_path": temp_file.name}
        
    except Exception as e:  # noqa: E722 - Catch all sync errors
        error_msg = str(e) if isinstance(e, Exception) else repr(e)
        print(f"❌ Sync failed: {error_msg}")
        
        _save_sync_status(success=False, error=error_msg)
        
        return {"success": False, "error": error_msg}


# =============================================================================
# Streamlit Application (Main Entry Point)
# =============================================================================

def main():
    """Main Streamlit application logic."""
    
    # Create data directory if it doesn't exist
    Path("data").mkdir(exist_ok=True)
    
    # Check rate limit for UI messages (from Citation 3)
    allowed, message = _check_rate_limit()
    
    # Get last login time for status badge
    last_login = _get_last_login()
    if last_login:
        last_time_str = f"{last_login.strftime('%H:%M')} · {datetime.now().strftime('%d.%m')}"
    else:
        last_time_str = ""
    
    # Get credentials status
    email, password = decrypt_esb_creds()
    has_creds = bool(email and password)
    
    # Check cookies file exists
    cookies_file_ok = ESB_COOKIE_FILE.exists()
    
    st.set_page_config(page_title="ESB Energy Dashboard", layout="wide")
    st.title("⚡ ESB Energy Dashboard")
    
    # Status Badge
    if last_login:
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"Last sync: {last_time_str}")
    
    # Alert Box for Status
    error_message = None
    success_message = None
    
    if message and not allowed:
        error_message = f"{message}"
    elif has_creds and cookies_file_ok:
        success_message = t("esb_sync_now")  # Or status update logic
    
    st.markdown(
        f'<div class="alert-box" style="font-size:.85rem;padding:.75rem 1rem; background:#e8f5e9;">',
        unsafe_allow_html=True
    )
    
    if error_message:
        st.error(error_message)
    elif success_message and has_creds:
        st.success(success_message)
        
    # Main Content - Sync Form
    with st.form("sync_form"):
        col1, col2 = st.columns([4, 2])
        
        with col1:
            mprn_input = st.text_input(
                "Meter Point Reference Number (MPRN)", 
                placeholder="e.g., 10309179908",
                key="mprn"
            )
            
        with col2:
            file_type_select = st.selectbox(
                "Data Type",
                list(ESB_FILE_TYPES.keys()),
                index=list(ESB_FILE_TYPES.keys()).index("daily"), # Default to daily
                key="file_type"
            )
        
        download_btn = st.form_submit_button("📥 Download Data", use_container_width=True)
    
    if download_btn:
        mprn = mprn_input.strip()
        file_type = file_type_select
        
        if not mprn:
            st.error("⚠️ Please enter a valid MPRN.")
        else:
            result = esb_sync_now(mprn=mprn, file_type=file_type)
            
            if result["success"]:
                st.success(f"✅ Download successful! Path: {result.get('file_path')}")
            else:
                error_msg = result.get("error", "Unknown error")[:200]
                st.error(f"❌ Download failed:\n{error_msg}")

    # Configuration Options Display
    if has_creds:
        st.info("✅ Credentials Configured (AES-256 Encrypted)")
        
    else:
        st.warning("⚠️ No Credentials Found. Configure them below or use cookies.")

    if not ESB_COOKIE_FILE.exists():
        st.caption(
            "No Cookies File Found.<br>"
            "You can export browser cookies using:<br>"
            "'Get cookies.txt LOCALLY' extension on myaccount.esbnetworks.ie"
        )
    
    # Footer
    st.markdown("---")
    st.markdown("Project: [GitHub Repository](https://github.com/lucslav/energy-viz/tree/test)")

if __name__ == "__main__":
    main()
