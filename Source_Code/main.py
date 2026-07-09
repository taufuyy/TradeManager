"""
main.py
Entry point for Trade Manager.

Responsibilities:
  1. Load configuration.
  2. Connect to MT5 and start the background polling thread.
  3. Start the currency-rate refresh thread.
  4. Register global hotkeys (pynput).
  5. Launch the CustomTkinter GUI main loop.
  6. Graceful shutdown on window close.
"""

import os
import sys
import ctypes

try:
    myappid = 'trademanager.app.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import threading
import winsound

import requests

from config_manager import ConfigManager
from mt5_manager import MT5Manager
from gui_dashboard import Dashboard

# ──────────────────────────────────────────────────────────────
# Resolve paths relative to this script or executable
# ──────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running in normal Python environment
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


# ──────────────────────────────────────────────────────────────
# Currency Rate Fetcher
# ──────────────────────────────────────────────────────────────

def currency_fetch_loop(cfg: ConfigManager, stop_event: threading.Event):
    """Periodically fetch USD/IDR exchange rate from a free API."""
    while not stop_event.is_set():
        if cfg.get("usd_idr_auto", True):
            url = cfg.get("currency_api_url",
                          "https://open.er-api.com/v6/latest/USD")
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    idr = data.get("rates", {}).get("IDR")
                    if idr:
                        cfg.set("usd_idr_rate", float(idr))
                        print(f"[Currency] USD/IDR updated: {idr}")
            except Exception as exc:
                print(f"[Currency] Fetch error: {exc}")
        interval = cfg.get("currency_refresh_seconds", 300)
        stop_event.wait(interval)


# ──────────────────────────────────────────────────────────────
# Global Hotkeys
# ──────────────────────────────────────────────────────────────

def setup_hotkeys(cfg: ConfigManager, dashboard: Dashboard):
    """Register global hotkeys using pynput.  Returns the listener."""
    try:
        from pynput.keyboard import GlobalHotKeys
    except ImportError:
        print("[Hotkeys] pynput not installed — hotkeys disabled.")
        return None

    def _beep():
        try:
            winsound.Beep(600, 80)
        except Exception:
            pass

    def on_emergency():
        if cfg.get("hotkeys_enabled", False):
            _beep()
            dashboard.trigger_emergency_close()

    def on_smart_be():
        if cfg.get("hotkeys_enabled", False):
            _beep()
            dashboard.trigger_smart_be()

    def on_hedge():
        if cfg.get("hotkeys_enabled", False):
            _beep()
            dashboard.trigger_hedge()

    def on_screenshot():
        if cfg.get("hotkeys_enabled", False):
            _beep()
            dashboard.trigger_screenshot()

    hotkeys = GlobalHotKeys({
        "<ctrl>+<shift>+x": on_emergency,
        "<ctrl>+<shift>+b": on_smart_be,
        "<ctrl>+<shift>+h": on_hedge,
        "<ctrl>+<shift>+s": on_screenshot,
    })
    hotkeys.daemon = True
    hotkeys.start()
    print("[Hotkeys] Global hotkeys registered.")
    return hotkeys


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=========================================================")
    print("  Trade Manager")
    print("=========================================================")

    # 1. Config
    cfg = ConfigManager(CONFIG_PATH)
    print(f"[Config] Loaded from {CONFIG_PATH}")
    
    if cfg.get("target_profit_armed", False):
        cfg.set("target_profit_armed", False)
        print("[Startup] Target profit was armed from previous session — reset to disarmed for safety.")

    # 2. Screenshots dir
    ss_dir = os.path.join(BASE_DIR, cfg.get("screenshot_dir", "screenshots"))
    os.makedirs(ss_dir, exist_ok=True)
    cfg.set("screenshot_dir", ss_dir)

    # 3. MT5 connection
    mt5_mgr = MT5Manager(cfg)
    connected = mt5_mgr.connect()
    if connected:
        print("[MT5] Connected to terminal.")
    else:
        print("[MT5] [WARNING] Could not connect — is MetaTrader 5 running?")
        print("[MT5]    The dashboard will launch anyway (offline mode).")

    # Clear armed status on startup for safety
    cfg.set_many({
        "target_profit_armed": False,
        "target_loss_armed": False
    })

    # 4. Start MT5 polling thread
    mt5_mgr.start_polling()
    print(f"[MT5] Polling started ({cfg.get('poll_interval_ms', 200)}ms interval).")

    # 5. Start currency fetch thread
    stop_event = threading.Event()
    currency_thread = threading.Thread(
        target=currency_fetch_loop, args=(cfg, stop_event), daemon=True)
    currency_thread.start()
    print("[Currency] Rate fetch thread started.")

    # 6. Create GUI
    dashboard = Dashboard(mt5_mgr, cfg)

    # 7. Register global hotkeys
    # Use after to prevent pynput hook from messing with CustomTkinter's window setup on Windows
    hotkey_listener = None
    def _start_hotkeys():
        nonlocal hotkey_listener
        hotkey_listener = setup_hotkeys(cfg, dashboard)
        
    dashboard.after(500, _start_hotkeys)

    # 8. Run GUI main loop (blocks until window is closed)
    print("[GUI] Launching dashboard…")
    dashboard.mainloop()

    # ── Shutdown ─────────────────────────────────────────────
    print("\n[Shutdown] Cleaning up…")
    stop_event.set()
    mt5_mgr.stop_polling()
    mt5_mgr.disconnect()
    if hotkey_listener:
        hotkey_listener.stop()
    print("[Shutdown] Done. Goodbye.")


if __name__ == "__main__":
    main()
