"""
config_manager.py
Thread-safe configuration manager for Trade Manager.
Loads/saves parameters to config.json with auto-persist on every change.
"""

import json
import os
import threading
import copy

_DEFAULT_CONFIG = {
    "account_currency": "USC",
    "spread_limit_pips": 5.0,
    "mc_threshold_pct": 50,
    "trailing_stop_pips": 10.0,
    "bulk_sl": 0.0,
    "bulk_tp": 0.0,
    "be_offset_pips": 0.5,
    "target_profit_native": 0,
    "target_profit_idr": 0,
    "target_profit_armed": False,
    "equity_protection_pct": 30,
    "equity_alarm_armed": True,
    "usd_idr_rate": 16250.0,
    "usd_idr_auto": True,
    "hotkeys_enabled": False,
    "micro_delay_ms": 75,
    "selective_close_qty": 1,
    "selective_close_direction": "ALL",
    "selective_close_sort": "Most Loss",
    "symbol": "XAUUSDc",
    "magic_number": 0,
    "poll_interval_ms": 200,
    "daily_history_refresh_seconds": 3.0,
    "currency_api_url": "https://open.er-api.com/v6/latest/USD",
    "currency_refresh_seconds": 300,
    "screenshot_dir": "screenshots",
    "known_servers": [
        "HFMarketsGlobal-Demo",
        "HFMarketsGlobal-Demo3",
        "HFMarketsGlobal-Demo4",
        "HFMarketsGlobal-Live1",
        "HFMarketsGlobal-Live2",
        "HFMarketsGlobal-Live3",
        "HFMarketsGlobal-Live4",
        "HFMarketsGlobal-Live5",
        "HFMarketsGlobal-Live6",
        "HFMarketsGlobal-Live7",
        "HFMarketsGlobal-Live8",
        "HFMarketsGlobal-Live9",
        "HFMarketsGlobal-Live10",
        "HFMarketsGlobal-Live11",
        "HFMarketsGlobal-Live12",
        "HFMarketsGlobal-Live13",
        "HFMarketsGlobal-Live14",
        "HFMarketsGlobal-Live15",
        "HFMarketsGlobal-Live16",
        "HFMarketsGlobal-Live17",
        "HFMarketsGlobal-Live18",
        "HFMarketsGlobal-Live19",
    ],
    "last_login_id": "",
    "last_login_server": "",
}


class ConfigManager:
    """Thread-safe JSON configuration manager with auto-save."""

    def __init__(self, filepath: str = "config.json"):
        self._filepath = filepath
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        """Return the value for *key*, falling back to *default*."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        """Set *key* to *value* and auto-save to disk."""
        with self._lock:
            self._data[key] = value
            self._save_locked()

    def set_many(self, mapping: dict):
        """Batch-update multiple keys and save once."""
        with self._lock:
            self._data.update(mapping)
            self._save_locked()

    def snapshot(self) -> dict:
        """Return a deep copy of the current config dict."""
        with self._lock:
            return copy.deepcopy(self._data)

    def reload(self):
        """Re-read config.json from disk (e.g. after external edit)."""
        self._load()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load(self):
        """Load config from disk, creating with defaults if missing."""
        with self._lock:
            if os.path.exists(self._filepath):
                try:
                    with open(self._filepath, "r", encoding="utf-8") as fh:
                        disk_data = json.load(fh)
                    
                    # Remove dead keys if they exist
                    disk_data.pop("be_offset_points", None)
                    disk_data.pop("trailing_stop_points", None)
                    
                    # Merge: defaults first, disk overrides
                    merged = {**_DEFAULT_CONFIG, **disk_data}
                    self._data = merged
                    self._save_locked()  # Auto-scrub from disk
                except (json.JSONDecodeError, IOError):
                    self._data = dict(_DEFAULT_CONFIG)
                    self._save_locked()
            else:
                self._data = dict(_DEFAULT_CONFIG)
                self._save_locked()

    def _save_locked(self):
        """Write current data to disk.  Caller MUST hold self._lock."""
        try:
            with open(self._filepath, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=4, ensure_ascii=False)
        except IOError as exc:
            print(f"[ConfigManager] Save error: {exc}")
