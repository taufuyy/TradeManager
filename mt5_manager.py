"""
mt5_manager.py
MT5 connection engine for Trade Manager.

Handles:
  - Connection lifecycle
  - Real-time position polling & metric computation
  - Bulk SL/TP, Smart BE, Trailing Stop
  - Selective / Emergency close with micro-delay
  - Hedge lock execution
  - Add-layer simulation (no orders placed)
  - MT5 chart screenshot capture
"""

import time
import json
import threading
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Callable

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # allow module to load for UI dev without MT5

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


# ──────────────────────────────────────────────────────────────
# Data container for polled state
# ──────────────────────────────────────────────────────────────

def _empty_state() -> dict:
    """Return a blank state dict with every key initialised."""
    return {
        # connection
        "connected": False,
        # resolved symbol
        "active_symbol": "",
        # tick
        "bid": 0.0,
        "ask": 0.0,
        "spread_pips": 0.0,
        # positions
        "positions": [],            # raw list[dict] copies
        "total_layers": 0,
        "total_lots": 0.0,
        "buy_lots": 0.0,
        "sell_lots": 0.0,
        "net_lots": 0.0,            # buy - sell (signed)
        # PnL
        "floating_pnl_native": 0.0,
        # averages
        "avg_price_buy": 0.0,
        "avg_price_sell": 0.0,
        "avg_price_combined": 0.0,
        "avg_distance_pips": 0.0,
        # layer range
        "highest_entry": 0.0,
        "lowest_entry": 0.0,
        "layer_range_pips": 0.0,
        # risk
        "equity": 0.0,
        "balance": 0.0,
        "margin": 0.0,
        "margin_level_pct": 0.0,
        "mc_price": 0.0,
        "mc_distance_pips": 0.0,
        # symbol info cache
        "tick_value": 0.0,
        "tick_size": 0.0,
        "point": 0.0,
        "contract_size": 0.0,
        # daily tracking
        "completed_sessions": 0,
        "daily_gross_profit_native": 0.0,
        "daily_gross_loss_native": 0.0,
        "daily_net_pnl_native": 0.0,
        # timestamp
        "last_update": 0.0,
    }


class MT5Manager:
    """High-level wrapper around the MetaTrader5 Python package."""

    def __init__(self, config_manager):
        self.cfg = config_manager
        self._lock = threading.Lock()
        self._state: dict = _empty_state()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._trailing_active = False
        self._on_state_update: Optional[Callable] = None  # optional callback
        self._had_positions_last_tick = False
        self._filling_mode_cache = {}
        self._last_daily_fetch_time = 0.0

    # ──────────────────────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialise MT5 terminal connection."""
        if mt5 is None:
            return False
        if not mt5.initialize():
            return False
            
        term_info = mt5.terminal_info()
        acct_info = mt5.account_info()
        if term_info is not None:
            print(f"[STARTUP] Terminal trade allowed: {term_info.trade_allowed}")
        if acct_info is not None:
            print(f"[STARTUP] Account trade allowed: {acct_info.trade_allowed}")
            # Auto-detect currency on initial connect
            self._detect_currency(acct_info)
            
        with self._lock:
            self._state["connected"] = True
        
        # Resolve the correct symbol for this account
        self.resolve_symbol()
        return True

    # ──────────────────────────────────────────────────────────
    # Symbol resolution & currency detection
    # ──────────────────────────────────────────────────────────

    def resolve_symbol(self, base_name: str = "XAUUSD") -> str:
        """Try multiple symbol name variants and return the first one available.
        
        Called after every successful login/connect to find the correct
        gold symbol name for the current account type (Cent vs Standard vs Micro).
        """
        if mt5 is None:
            return ""

        config_hint = self.cfg.get("symbol", base_name)

        # Build candidate list: config hint first, then common variants
        candidates = []
        # Always try the config hint first (user's preference)
        candidates.append(config_hint)
        # Then try all common variants
        for variant in [
            base_name,            # "XAUUSD"
            base_name + "c",      # "XAUUSDc"  (Cent — HFM)
            base_name + ".c",     # "XAUUSD.c" (Cent — alternate)
            base_name + "m",      # "XAUUSDm"  (Micro)
            "GOLD",               # Some brokers use GOLD
            "GOLDc",              # GOLD cent variant
        ]:
            if variant not in candidates:
                candidates.append(variant)

        for candidate in candidates:
            try:
                mt5.symbol_select(candidate, True)
                info = mt5.symbol_info(candidate)
                if info is not None:
                    with self._lock:
                        self._state["active_symbol"] = candidate
                    if candidate != config_hint:
                        print(f"[MT5Manager] Symbol resolved: '{config_hint}' -> '{candidate}' for this account.")
                    else:
                        print(f"[MT5Manager] Symbol confirmed: '{candidate}'")
                    return candidate
            except Exception as exc:
                print(f"[MT5Manager] Error trying symbol '{candidate}': {exc}")
                continue

        # No candidate found
        print(f"[MT5Manager] WARNING: No valid gold symbol found! Tried: {candidates}")
        with self._lock:
            self._state["active_symbol"] = ""
        return ""

    def get_active_symbol(self) -> str:
        """Return the resolved active symbol, or empty string if none found."""
        with self._lock:
            return self._state.get("active_symbol", "")

    def _detect_currency(self, acct_info=None):
        """Auto-detect account currency and update config.
        
        Can be called with an existing account_info object, or will
        fetch one if not provided.
        """
        if acct_info is None:
            if mt5 is None:
                return
            acct_info = mt5.account_info()
            if acct_info is None:
                return

        acct_curr = acct_info.currency.upper()
        current_cfg_curr = self.cfg.get("account_currency", "USD")

        if "USC" in acct_curr or "CENT" in acct_curr:
            new_curr = "USC"
        elif "IDR" in acct_curr:
            new_curr = "IDR"
        elif "USD" in acct_curr or acct_curr == "USD":
            new_curr = "USD"
        else:
            # Fallback: unknown currency → treat as USD
            new_curr = "USD"
            print(f"[MT5Manager] Unknown account currency '{acct_curr}', defaulting to USD.")

        if new_curr != current_cfg_curr:
            self.cfg.set("account_currency", new_curr)
            print(f"[MT5Manager] Account currency detected: {acct_curr} -> {new_curr}")

    def disconnect(self):
        """Shutdown MT5 connection."""
        self.stop_polling()
        if mt5 is not None:
            mt5.shutdown()
        with self._lock:
            self._state["connected"] = False

    def is_connected(self) -> bool:
        with self._lock:
            return self._state["connected"]

    def login_account(self, account_id: str, password: str, server: str) -> Tuple[bool, str]:
        """Login to a specific MT5 account.
        
        Returns (success: bool, message: str) with detailed status/error info.
        """
        if mt5 is None:
            return False, "MetaTrader5 package not installed."
        
        # --- Pause polling to avoid race conditions during account switch ---
        was_running = self._running
        if was_running:
            self._running = False
            if self._poll_thread and self._poll_thread.is_alive():
                self._poll_thread.join(timeout=2)
        
        try:
            try:
                acc_int = int(account_id)
            except ValueError:
                return False, f"Format ID salah (bukan angka): {account_id}"

            # Ensure we are initialized first, passing the credentials directly
            # to avoid Authorization Failed if the last active account in MT5 is broken.
            if not mt5.initialize(login=acc_int, password=password, server=server):
                err = mt5.last_error()
                return False, f"MT5 initialize() failed: {err}"
                
            # Attempt login just to be sure
            authorized = mt5.login(login=acc_int, password=password, server=server)
            
            if not authorized:
                err = mt5.last_error()
                err_code = err[0] if err else "?"
                err_msg = err[1] if err and len(err) > 1 else "Unknown error"
                msg = f"Login gagal (Error {err_code}: {err_msg})"
                print(f"[MT5Manager] {msg}")
                with self._lock:
                    self._state["connected"] = False
                return False, msg
            
            # --- Validate: is the terminal actually on the correct account? ---
            acct_info = mt5.account_info()
            if acct_info is None:
                msg = "Login returned True tapi account_info() None — sesi lama mungkin masih aktif."
                print(f"[MT5Manager] {msg}")
                with self._lock:
                    self._state["connected"] = False
                return False, msg
            
            if str(acct_info.login) != str(account_id):
                msg = (f"Login returned True tapi account aktif = {acct_info.login}, "
                       f"bukan {account_id} yang diminta — kemungkinan sesi lama masih aktif.")
                print(f"[MT5Manager] {msg}")
                with self._lock:
                    self._state["connected"] = False
                return False, msg
            
            # --- Login confirmed valid ---
            print(f"[MT5Manager] [OK] Login berhasil ke akun {acct_info.login} "
                  f"(server: {acct_info.server}, balance: {acct_info.balance}, "
                  f"currency: {acct_info.currency})")
            
            # Reset stale internal state from previous account
            with self._lock:
                self._state = _empty_state()
                self._state["connected"] = True
            self._had_positions_last_tick = False
            self._filling_mode_cache = {}
            self._last_daily_fetch_time = 0.0
            
            # Save last login info
            known_accounts = self.cfg.get("known_accounts", {})
            if isinstance(known_accounts, list):
                # migrate from old list format just in case
                known_accounts = {str(k): server for k in known_accounts}
            known_accounts[str(account_id)] = server
            
            self.cfg.set_many({
                "last_login_id": str(account_id),
                "last_login_server": server,
                "known_accounts": known_accounts
            })
            
            # Step 1: Detect account currency FIRST
            self._detect_currency(acct_info)
            
            # Step 2: Resolve the correct symbol for this account
            resolved = self.resolve_symbol()
            if not resolved:
                print(f"[MT5Manager] WARNING: No gold symbol found for account {acct_info.login}. "
                      f"Price/position data will be unavailable.")
            
            # Step 3: Force immediate data refresh
            try:
                self._poll_once()
            except Exception as exc:
                print(f"[MT5Manager] Post-login poll error (non-fatal): {exc}")
            
            return True, (f"Login berhasil: #{acct_info.login} @ {acct_info.server}\n"
                         f"Balance: {acct_info.balance} {acct_info.currency}")
        
        finally:
            # --- Resume polling if it was running before ---
            if was_running:
                self._running = True
                self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
                self._poll_thread.start()

    # ──────────────────────────────────────────────────────────
    # Polling loop
    # ──────────────────────────────────────────────────────────

    def start_polling(self, on_update: Optional[Callable] = None):
        """Start the background poll thread."""
        self._on_state_update = on_update
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2)

    def _poll_loop(self):
        """Runs continuously on a daemon thread."""
        while self._running:
            interval = self.cfg.get("poll_interval_ms", 50) / 1000.0
            try:
                self._poll_once()
            except Exception as exc:
                print(f"[MT5Manager] Poll error: {exc}")
            time.sleep(interval)

    def _poll_once(self):
        """Single poll cycle — gather data and compute metrics."""
        if mt5 is None:
            return

        symbol = self.get_active_symbol()
        magic = self.cfg.get("magic_number", 0)
        mc_thresh = self.cfg.get("mc_threshold_pct", 50)

        # --- connection check ---
        terminal_info = mt5.terminal_info()
        connected = terminal_info is not None and terminal_info.connected
        if not connected:
            with self._lock:
                self._state["connected"] = False
            return

        # --- account ---
        acct = mt5.account_info()
        if acct is None:
            return
        equity = acct.equity
        balance = acct.balance
        margin = acct.margin
        margin_level = (equity / margin * 100) if margin > 0 else 0.0

        # --- debug logging: margin=0 while hedged ---
        if self.cfg.get("debug_margin_logging", False):
            # Will be checked after positions are computed (see below)
            pass
        
        # --- auto-detect currency (lightweight, uses reusable method) ---
        self._detect_currency(acct)

        # --- symbol ---
        # If no symbol resolved yet (e.g. first poll), try to resolve
        if not symbol:
            symbol = self.resolve_symbol()

        if symbol:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            sym_info = mt5.symbol_info(symbol)
        else:
            tick = None
            sym_info = None
        
        # Initialize default values
        bid = 0.0
        ask = 0.0
        spread_pips = 0.0
        positions_data: List[dict] = []
        filtered = []
        total_lots = 0.0
        buy_lots = 0.0
        sell_lots = 0.0
        net_lots = 0.0
        floating_pnl = 0.0
        avg_buy = 0.0
        avg_sell = 0.0
        avg_combined = 0.0
        avg_dist = 0.0
        highest = 0.0
        lowest = 0.0
        layer_range = 0.0
        mc_price = 0.0
        mc_dist = 0.0
        
        sym_digits = sym_info.digits if sym_info else 5
        sym_tick_val = sym_info.trade_tick_value if sym_info else 0.0
        sym_tick_size = sym_info.trade_tick_size if sym_info else 0.0
        sym_point = sym_info.point if sym_info else 0.0
        sym_contract = sym_info.trade_contract_size if sym_info else 0.0

        if tick is None or sym_info is None:
            if not getattr(self, "_warned_missing_symbol", {}).get(symbol, False):
                print(f"[MT5Manager] WARNING: Symbol '{symbol}' tidak tersedia di akun ini (login {acct.login}). Data harga/posisi di-skip, tapi balance/equity tetap update.")
                if not hasattr(self, "_warned_missing_symbol"):
                    self._warned_missing_symbol = {}
                self._warned_missing_symbol[symbol] = True
        else:
            self._warned_missing_symbol = getattr(self, "_warned_missing_symbol", {})
            self._warned_missing_symbol[symbol] = False
            
            bid = tick.bid
            ask = tick.ask
            spread_pips = round(((ask - bid) / sym_point) / 10.0, 1) if sym_point else 0.0

            # --- positions ---
            raw_positions = mt5.positions_get(symbol=symbol)
            if raw_positions is None:
                raw_positions = ()
            # Filter magic number
            filtered = [p for p in raw_positions if p.magic == magic]

            buy_weighted = 0.0
            sell_weighted = 0.0
            prices = []

            for p in filtered:
                pd = {
                    "ticket": p.ticket,
                    "type": p.type,  # 0=BUY, 1=SELL
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "swap": p.swap if hasattr(p, "swap") else 0.0,
                    "time": p.time,
                    "comment": p.comment if hasattr(p, "comment") else "",
                }
                positions_data.append(pd)
                total_lots += p.volume
                floating_pnl += p.profit
                prices.append(p.price_open)

                if p.type == 0:  # BUY
                    buy_lots += p.volume
                    buy_weighted += p.price_open * p.volume
                else:  # SELL
                    sell_lots += p.volume
                    sell_weighted += p.price_open * p.volume

            net_lots = buy_lots - sell_lots
            avg_buy = (buy_weighted / buy_lots) if buy_lots > 0 else 0.0
            avg_sell = (sell_weighted / sell_lots) if sell_lots > 0 else 0.0

            combined_weight = buy_weighted + sell_weighted
            avg_combined = (combined_weight / total_lots) if total_lots > 0 else 0.0

            # distance from current mid-price to combined average
            mid = (bid + ask) / 2.0
            avg_dist = round(((mid - avg_combined) / sym_point) / 10.0, 1) if sym_point and avg_combined else 0.0

            # layer range
            highest = max(prices) if prices else 0.0
            lowest = min(prices) if prices else 0.0
            layer_range = round(((highest - lowest) / sym_point) / 10.0, 1) if sym_point and prices else 0.0

            # --- MC price calc ---
            point_value = (sym_tick_val / sym_tick_size) if sym_tick_size else 0
            
            specific_margin = 0.0
            margin_calc_failed = False
            for p in filtered:
                order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                calc_m = mt5.order_calc_margin(order_type, p.symbol, p.volume, p.price_open)
                if calc_m is not None:
                    specific_margin += calc_m
                else:
                    margin_calc_failed = True
                    break
                    
            if not margin_calc_failed and specific_margin > 0:
                used_margin = specific_margin
            else:
                if not getattr(self, "_warned_margin_fallback", False):
                    print("[MT5Manager] order_calc_margin failed, fallback to account margin for MC calculation (Valid ONLY if trading 1 symbol).")
                    self._warned_margin_fallback = True
                used_margin = margin

            if abs(net_lots) > 1e-9 and used_margin > 0 and point_value > 0:
                equity_at_mc = used_margin * mc_thresh / 100.0
                loss_to_mc = equity - equity_at_mc
                price_move = loss_to_mc / (abs(net_lots) * point_value)
                if net_lots > 0:
                    mc_price = mid - price_move
                else:
                    mc_price = mid + price_move
                mc_dist = round((abs(mid - mc_price) / sym_point) / 10.0, 1) if sym_point else 0.0

            # --- trailing stop (if active) ---
            if self._trailing_active:
                self._apply_trailing_stop_internal(filtered, bid, ask, sym_info)

            # --- target profit & loss auto-close ---
            from currency_utils import to_idr, format_amount_short
            target_tp_native = self.cfg.get("target_profit_native", 0)
            target_tp_idr = self.cfg.get("target_profit_idr", 0)
            target_tl_native = self.cfg.get("target_loss_native", 0)
            target_tl_idr = self.cfg.get("target_loss_idr", 0)
            
            pnl_idr = to_idr(floating_pnl, self.cfg)
            bal = acct.balance
            
            # Target Profit
            if self.cfg.get("target_profit_armed", False):
                hit_target = False
                hit_amt_str = ""
                if target_tp_native > 0 and floating_pnl >= target_tp_native:
                    hit_target = True
                elif target_tp_idr > 0 and pnl_idr >= target_tp_idr:
                    hit_target = True
                
                if hit_target:
                    hit_amt_str = f"{format_amount_short(floating_pnl, self.cfg)} (Rp {pnl_idr:,.0f})"
                    
                if hit_target:
                    threading.Thread(target=self.emergency_close_all, daemon=True).start()
                    pct = (floating_pnl / bal * 100) if bal > 0 else 0
                    new_b = bal + floating_pnl
                    self.cfg.set_many({
                        "target_profit_armed": False,
                        "trigger_celebration": True,
                        "celebration_amount_str": hit_amt_str,
                        "celebration_pct_str": f"{pct:.2f}",
                        "celebration_new_balance": f"{new_b:,.2f}"
                    })
                    
            # Target Loss
            if self.cfg.get("target_loss_armed", False):
                hit_loss = False
                loss_amt_str = ""
                if target_tl_native > 0 and floating_pnl <= -target_tl_native:
                    hit_loss = True
                elif target_tl_idr > 0 and pnl_idr <= -target_tl_idr:
                    hit_loss = True
                    
                if hit_loss:
                    loss_amt_str = f"{format_amount_short(floating_pnl, self.cfg)} (Rp {pnl_idr:,.0f})"
                    
                if hit_loss:
                    threading.Thread(target=self.emergency_close_all, daemon=True).start()
                    pct = (abs(floating_pnl) / bal * 100) if bal > 0 else 0
                    rem_pct = ((bal + floating_pnl) / bal * 100) if bal > 0 else 100
                    new_b = bal + floating_pnl
                    self.cfg.set_many({
                        "target_loss_armed": False,
                        "trigger_loss_popup": True,
                        "loss_amount_str": loss_amt_str,
                        "loss_pct_str": f"{pct:.2f}",
                        "loss_rem_pct_str": f"{rem_pct:.2f}",
                        "loss_new_balance": f"{new_b:,.2f}"
                    })

        # --- margin=0 hedge debug logging ---
        if abs(net_lots) < 0.01 and margin == 0 and len(positions_data) > 0:
            print(f"[MT5Manager] [HEDGE DEBUG] Margin=0 with {len(positions_data)} open positions. "
                  f"acct.margin={acct.margin}, acct.margin_free={acct.margin_free}, "
                  f"acct.margin_level={acct.margin_level}, "
                  f"buy_lots={buy_lots}, sell_lots={sell_lots}, net_lots={net_lots}")

        # --- daily deals history ---
        current_time = time.time()
        throttle_interval = self.cfg.get("daily_history_refresh_seconds", 3.0)
        
        # Load from state defaults
        daily_profit = self._state.get("daily_gross_profit_native", 0.0)
        daily_loss = self._state.get("daily_gross_loss_native", 0.0)
        daily_net = self._state.get("daily_net_pnl_native", 0.0)
        
        if current_time - getattr(self, "_last_daily_fetch_time", 0.0) >= throttle_interval:
            self._last_daily_fetch_time = current_time
            now_local = datetime.now()
            start_local = now_local - timedelta(days=2)
            end_local = now_local + timedelta(days=1)
            
            daily_deals = mt5.history_deals_get(start_local, end_local)
            if daily_deals is not None:
                daily_profit = 0.0
                daily_loss = 0.0
                daily_net = 0.0
                
                # Calculate exact midnight in LOCAL time to match user's timezone
                local_now_dt = datetime.now()
                local_midnight_dt = local_now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                local_midnight_epoch = local_midnight_dt.timestamp()
                
                login = acct.login if acct else 0
                prefix = f"acct_{login}_"
                
                # --- ONE TIME HOT PATCH FOR SESSION MIGRATION ---
                if self.cfg.get(prefix + "completed_sessions", 0) == 1 and self.cfg.get(prefix + "session_wins", 0.0) < 20.0:
                    self.cfg.set_many({
                        prefix + "completed_sessions": 2,
                        prefix + "session_wins": self.cfg.get(prefix + "session_wins", 0.0) + 14.44
                    })
                # ------------------------------------------------
                
                # Reset daily session tracking at midnight
                today_str = local_midnight_dt.strftime("%Y-%m-%d")
                
                # Migration logic: if the account-specific stats date doesn't exist, check if we have global stats for today
                if self.cfg.get(prefix + "daily_stats_date", None) is None:
                    old_date = self.cfg.get("daily_stats_date", "")
                    if old_date == today_str:
                        self.cfg.set_many({
                            prefix + "daily_stats_date": old_date,
                            prefix + "session_wins": self.cfg.get("session_wins", 0.0),
                            prefix + "session_losses": self.cfg.get("session_losses", 0.0),
                            prefix + "session_wins_count": self.cfg.get("session_wins_count", 0),
                            prefix + "session_losses_count": self.cfg.get("session_losses_count", 0),
                            prefix + "completed_sessions": self.cfg.get("completed_sessions", 0),
                            prefix + "session_start_net": self.cfg.get("session_start_net", 0.0)
                        })
                
                if self.cfg.get(prefix + "daily_stats_date", "") != today_str:
                    self.cfg.set(prefix + "daily_stats_date", today_str)
                    self.cfg.set(prefix + "session_wins", 0.0)
                    self.cfg.set(prefix + "session_losses", 0.0)
                    self.cfg.set(prefix + "session_wins_count", 0)
                    self.cfg.set(prefix + "session_losses_count", 0)
                    self.cfg.set(prefix + "completed_sessions", 0)
                    with self._lock:
                        self._state["completed_sessions"] = 0
                
                for deal in daily_deals:
                    if deal.time >= local_midnight_epoch and deal.magic == magic and deal.type in (0, 1):
                        net_amt = deal.profit + deal.commission + deal.swap
                        if net_amt != 0:
                            daily_net += net_amt
                            if net_amt > 0:
                                daily_profit += net_amt
                            else:
                                daily_loss += abs(net_amt)

                # Process pending session end
                if getattr(self, "_pending_session_calc", False):
                    login = acct.login if acct else 0
                    prefix = f"acct_{login}_"
                    start_net = self.cfg.get(prefix + "session_start_net", 0.0)
                    session_net = daily_net - start_net
                    if session_net > 0:
                        wins = self.cfg.get(prefix + "session_wins", 0.0) + session_net
                        self.cfg.set(prefix + "session_wins", wins)
                        wc = self.cfg.get(prefix + "session_wins_count", 0) + 1
                        self.cfg.set(prefix + "session_wins_count", wc)
                    elif session_net < 0:
                        losses = self.cfg.get(prefix + "session_losses", 0.0) + abs(session_net)
                        self.cfg.set(prefix + "session_losses", losses)
                        lc = self.cfg.get(prefix + "session_losses_count", 0) + 1
                        self.cfg.set(prefix + "session_losses_count", lc)
                    
                    with self._lock:
                        self._state["completed_sessions"] = self.cfg.get(prefix + "completed_sessions", 0) + 1
                    self.cfg.set(prefix + "completed_sessions", self._state["completed_sessions"])
                    self._pending_session_calc = False

        # --- session tracking transitions ---
        current_has_positions = len(positions_data) > 0
        if current_has_positions and not getattr(self, "_had_positions_last_tick", False):
            # Session Started
            login = acct.login if acct else 0
            self.cfg.set(f"acct_{login}_session_start_net", daily_net)
        elif not current_has_positions and getattr(self, "_had_positions_last_tick", False):
            # Session Ended, flag it to be calculated on the next history deals fetch
            self._pending_session_calc = True
            
            # Automatically disable Goal Based Automation for the next session
            self.cfg.set("target_profit_armed", False)
            self.cfg.set("target_loss_armed", False)
            
        self._had_positions_last_tick = current_has_positions

        # --- write state ---
        with self._lock:
            completed_sessions = self._state.get("completed_sessions", 0)
            
        new_state = {
            "connected": True,
            "login": acct.login if acct else 0,
            "active_symbol": symbol or "",
            "bid": bid,
            "ask": ask,
            "spread_pips": spread_pips,
            "positions": positions_data,
            "total_layers": len(positions_data),
            "total_lots": round(total_lots, 2),
            "buy_lots": round(buy_lots, 2),
            "sell_lots": round(sell_lots, 2),
            "net_lots": round(net_lots, 2),
            "floating_pnl_native": round(floating_pnl, 2),
            "floating_pnl_usc": round(floating_pnl, 2),
            "avg_price_buy": round(avg_buy, sym_digits) if avg_buy else 0.0,
            "avg_price_sell": round(avg_sell, sym_digits) if avg_sell else 0.0,
            "avg_price_combined": round(avg_combined, sym_digits) if avg_combined else 0.0,
            "avg_distance_pips": avg_dist,
            "highest_entry": highest,
            "lowest_entry": lowest,
            "layer_range_pips": layer_range,
            "equity": equity,
            "balance": balance,
            "margin": margin,
            "margin_level_pct": round(margin_level, 2),
            "mc_price": round(mc_price, sym_digits) if mc_price else 0.0,
            "mc_distance_pips": mc_dist,
            "tick_value": sym_tick_val,
            "tick_size": sym_tick_size,
            "point": sym_point,
            "contract_size": sym_contract,
            "completed_sessions": self.cfg.get(f"acct_{acct.login}_completed_sessions" if acct else "", 0),
            "session_wins": float(self.cfg.get(f"acct_{acct.login}_session_wins" if acct else "") or 0.0),
            "session_losses": float(self.cfg.get(f"acct_{acct.login}_session_losses" if acct else "") or 0.0),
            "session_wins_count": int(self.cfg.get(f"acct_{acct.login}_session_wins_count" if acct else "", 0)),
            "session_losses_count": int(self.cfg.get(f"acct_{acct.login}_session_losses_count" if acct else "", 0)),
            "daily_gross_profit_native": round(daily_profit, 2),
            "daily_gross_loss_native": round(daily_loss, 2),
            "daily_net_pnl_native": round(daily_net, 2),
            "daily_net_pnl_usc": round(daily_net, 2),
            "last_update": time.time(),
        }

        with self._lock:
            self._state = new_state

    def get_state(self) -> dict:
        """Thread-safe snapshot of latest polled state."""
        with self._lock:
            return dict(self._state)

    # ──────────────────────────────────────────────────────────
    # Order Actions
    # ──────────────────────────────────────────────────────────

    def get_filling_mode(self, symbol: str) -> int:
        """Determine the correct filling mode for a symbol.
        
        The MT5 Python library does NOT have mt5.SYMBOL_FILLING_IOC/FOK constants.
        Instead, symbol_info().filling_mode is a raw bitmask:
          bit 0 (value 1) = FOK supported
          bit 1 (value 2) = IOC supported
        The ORDER_FILLING_* constants (IOC=1, FOK=0, RETURN=2) are for order requests.
        """
        if symbol in self._filling_mode_cache:
            return self._filling_mode_cache[symbol]

        # Bitmask flags from symbol_info().filling_mode
        _FLAG_FOK = 1   # bit 0
        _FLAG_IOC = 2   # bit 1

        mode = mt5.ORDER_FILLING_IOC  # safe default for HFM

        try:
            info = mt5.symbol_info(symbol)
            if info is not None:
                flags = info.filling_mode
                if flags & _FLAG_IOC:
                    mode = mt5.ORDER_FILLING_IOC
                elif flags & _FLAG_FOK:
                    mode = mt5.ORDER_FILLING_FOK
                    print(f"[MT5Manager] IOC not supported for {symbol} (flags={flags}), using FOK.")
                else:
                    mode = mt5.ORDER_FILLING_RETURN
                    print(f"[MT5Manager] IOC/FOK not supported for {symbol} (flags={flags}), using RETURN.")
                print(f"[MT5Manager] Filling mode for '{symbol}': flags={flags} -> ORDER_FILLING={mode}")
            else:
                print(f"[MT5Manager] symbol_info('{symbol}') returned None, defaulting to ORDER_FILLING_IOC.")
        except Exception as exc:
            print(f"[MT5Manager] WARNING: Error detecting filling mode for '{symbol}': {exc}. Defaulting to IOC.")
            mode = mt5.ORDER_FILLING_IOC

        self._filling_mode_cache[symbol] = mode
        return mode

    def _send_order_with_check(self, req):
        """Send an order to MT5 with detailed logging."""
        symbol = req.get("symbol", "?")
        action = req.get("action", "?")
        filling = req.get("type_filling", "N/A")

        print(f"[MT5Manager] Sending order: symbol={symbol}, action={action}, "
              f"filling={filling}, ticket={req.get('position', 'new')}")

        res = mt5.order_send(req)
        if res is None:
            err = mt5.last_error()
            msg = f"EXECUTION FAILED! OrderSend returned None. MT5 Error: {err}"
            print(f"[MT5Manager] {msg}")
            return res
            
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[MT5Manager] Order OK: retcode={res.retcode}, comment='{res.comment}', "
                  f"order={res.order}, deal={res.deal}")
        else:
            err = mt5.last_error()
            msg = (f"EXECUTION FAILED! retcode={res.retcode}, comment='{res.comment}', "
                   f"MT5 Last Error: {err}")
            print(f"[MT5Manager] {msg}")
        return res

    def _micro_delay(self):
        """Sleep for the configured micro-delay between bulk order calls."""
        ms = self.cfg.get("micro_delay_ms", 75)
        time.sleep(ms / 1000.0)

    def _get_filtered_positions(self):
        """Return live MT5 position objects filtered by symbol + magic."""
        if mt5 is None:
            return []
        symbol = self.get_active_symbol()
        if not symbol:
            return []
        magic = self.cfg.get("magic_number", 0)
        raw = mt5.positions_get(symbol=symbol)
        if raw is None:
            return []
        return [p for p in raw if p.magic == magic]

    # ---- Bulk SL / TP ----

    def bulk_set_sl_tp(self, sl: Optional[float], tp: Optional[float]) -> List[dict]:
        """Modify SL and TP on all filtered positions. Returns list of results."""
        results = []
        for pos in self._get_filtered_positions():
            final_sl = sl if sl is not None else pos.sl
            final_tp = tp if tp is not None else pos.tp
            
            if final_sl == pos.sl and final_tp == pos.tp:
                continue
                
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": final_sl,
                "tp": final_tp,
            }
            res = self._send_order_with_check(req)
            results.append({"ticket": pos.ticket, "retcode": res.retcode if res else -1})
            self._micro_delay()
        return results

    def apply_multi_tp(self, sl: Optional[float], tp_tiers: List[dict]) -> List[dict]:
        """
        tp_tiers: list of {"tp": float, "pct": float} where sum(pct) should ideally be 100.
        Option A: Sorts positions from worst profit to best profit.
        """
        positions = self._get_filtered_positions()
        if not positions:
            return []

        # Sort by profit ascending (worst floating loss first)
        positions.sort(key=lambda p: p.profit)

        total_pos = len(positions)
        results = []

        # Calculate exact counts for each bucket
        counts = []
        for tier in tp_tiers:
            counts.append(round(total_pos * (tier["pct"] / 100.0)))

        # Fix rounding errors (make sure sum equals total_pos)
        total_counts = sum(counts)
        if total_counts < total_pos and len(counts) > 0:
            counts[0] += (total_pos - total_counts)
        elif total_counts > total_pos and len(counts) > 0:
            counts[0] -= (total_counts - total_pos)
            counts[0] = max(0, counts[0]) # safety

        # Distribute
        pos_idx = 0
        for i, tier in enumerate(tp_tiers):
            tier_tp = tier.get("tp", 0.0)
            count = counts[i]
            
            for _ in range(count):
                if pos_idx >= total_pos:
                    break
                pos = positions[pos_idx]
                pos_idx += 1
                
                final_sl = sl if sl is not None else pos.sl
                
                if final_sl == pos.sl and tier_tp == pos.tp:
                    continue
                    
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "sl": final_sl,
                    "tp": tier_tp,
                }
                res = self._send_order_with_check(req)
                results.append({"ticket": pos.ticket, "retcode": res.retcode if res else -1})
                self._micro_delay()

        return results

    # ---- Smart Break-Even ----

    def smart_be(self, offset_pips: Optional[float] = None) -> List[dict]:
        """Move SL to average entry price ± offset for each position."""
        if offset_pips is None:
            offset_pips = self.cfg.get("be_offset_pips", 0.5)

        positions = self._get_filtered_positions()
        if not positions:
            return []

        active_sym = self.get_active_symbol()
        if not active_sym:
            return []
        sym_info = mt5.symbol_info(active_sym)
        if sym_info is None:
            return []

        point = sym_info.point

        # Compute weighted average per direction
        buy_w, buy_v, sell_w, sell_v = 0.0, 0.0, 0.0, 0.0
        for p in positions:
            if p.type == 0:
                buy_w += p.price_open * p.volume
                buy_v += p.volume
            else:
                sell_w += p.price_open * p.volume
                sell_v += p.volume

        avg_buy = (buy_w / buy_v) if buy_v > 0 else 0.0
        avg_sell = (sell_w / sell_v) if sell_v > 0 else 0.0

        results = []
        for pos in positions:
            if pos.type == 0 and avg_buy:  # BUY
                new_sl = round(avg_buy + (offset_pips * 10) * point, sym_info.digits)
            elif pos.type == 1 and avg_sell:  # SELL
                new_sl = round(avg_sell - (offset_pips * 10) * point, sym_info.digits)
            else:
                continue

            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": new_sl,
                "tp": pos.tp,
            }
            res = self._send_order_with_check(req)
            results.append({"ticket": pos.ticket, "retcode": res.retcode if res else -1})
            self._micro_delay()
        return results

    # ---- Trailing Stop ----

    def set_trailing_active(self, active: bool):
        self._trailing_active = active

    def is_trailing_active(self) -> bool:
        return self._trailing_active

    def _apply_trailing_stop_internal(self, positions, bid, ask, sym_info):
        """Called inside the poll loop when trailing is active."""
        trail_pips = self.cfg.get("trailing_stop_pips", 10.0)
        point = sym_info.point
        if point == 0 or trail_pips <= 0:
            return

        for pos in positions:
            trail_price = (trail_pips * 10) * point
            if pos.type == 0:  # BUY — trail below bid
                ideal_sl = round(bid - trail_price, sym_info.digits)
                if pos.sl == 0 or ideal_sl > pos.sl:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": pos.symbol,
                        "sl": ideal_sl,
                        "tp": pos.tp,
                    }
                    self._send_order_with_check(req)
                    self._micro_delay()
            else:  # SELL — trail above ask
                ideal_sl = round(ask + trail_price, sym_info.digits)
                if pos.sl == 0 or ideal_sl < pos.sl:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": pos.symbol,
                        "sl": ideal_sl,
                        "tp": pos.tp,
                    }
                    self._send_order_with_check(req)
                    self._micro_delay()

    # ---- Selective Close ----

    def get_selective_close_targets(
        self,
        qty=1,
        direction: str = "ALL",
        sort_order: str = "Most Loss",
    ):
        """Returns the specific positions that would be closed by selective_close."""
        positions = self._get_filtered_positions()

        # Filter direction
        if direction == "BUY":
            positions = [p for p in positions if p.type == 0]
        elif direction == "SELL":
            positions = [p for p in positions if p.type == 1]

        # Sort
        if sort_order == "All":
            qty = None  # Skip sorting and force close all
        else:
            sort_map = {
                "Top Price": lambda p: -p.price_open,
                "Bottom Price": lambda p: p.price_open,
                "Most Profit": lambda p: -p.profit,
                "Most Loss": lambda p: p.profit,
            }
            key_fn = sort_map.get(sort_order, sort_map["Most Loss"])
            positions.sort(key=key_fn)

        # qty=None means close ALL matching positions
        if qty is None:
            to_close = positions
        else:
            to_close = positions[:qty]
            
        return to_close

    def selective_close(
        self,
        qty=1,
        direction: str = "ALL",
        sort_order: str = "Most Loss",
    ) -> List[dict]:
        """Close *qty* positions chosen by direction + sort criteria.
        
        If qty is None, close ALL positions matching the direction filter.
        """
        to_close = self.get_selective_close_targets(qty, direction, sort_order)
        return self._close_positions(to_close)

    # ---- Emergency Close All ----

    def emergency_close_all(self) -> List[dict]:
        """Close every filtered position with micro-delay loop."""
        return self._close_positions(self._get_filtered_positions())

    def _close_positions(self, positions) -> List[dict]:
        """Internal: close a list of MT5 position objects."""
        results = []
        active_sym = self.get_active_symbol()
        if not active_sym or not positions:
            return results
            
        magic = self.cfg.get("magic_number", 0)
        
        # 1. Attempt EA Relay
        info = mt5.terminal_info()
        ea_relayed = False
        if info and info.data_path:
            import os, time
            mql5_files_dir = os.path.join(info.data_path, "MQL5", "Files")
            if os.path.exists(mql5_files_dir):
                cmd_filename = f"tm_cmd_{int(time.time()*1000)}.txt"
                cmd_path = os.path.join(mql5_files_dir, cmd_filename)
                
                # Write command
                try:
                    with open(cmd_path, 'w') as f:
                        f.write(f"CLOSE_ALL|{active_sym}|{magic}")
                    print(f"[MT5Manager] Sent CLOSE_ALL command to EA via {cmd_filename}")
                    
                    # Wait up to 1.5 seconds to see if EA picks it up (file is deleted by EA)
                    for _ in range(15):
                        time.sleep(0.1)
                        if not os.path.exists(cmd_path):
                            print("[MT5Manager] EA successfully picked up the command!")
                            ea_relayed = True
                            break
                            
                    if ea_relayed:
                        return [{"status": "ea_relayed"}]
                        
                    # If file still exists after timeout, EA is probably not running.
                    print("[MT5Manager] WARNING: EA Relay did not respond. Falling back to Python fallback.")
                    try:
                        os.remove(cmd_path) # Delete to prevent late execution
                    except:
                        pass
                except Exception as e:
                    print(f"[MT5Manager] Failed to write EA command file: {e}")
                    
        # 2. Fallback to Python threading
        import concurrent.futures
        sym_info = mt5.symbol_info(active_sym)
        if sym_info is None:
            return results
            
        def close_single(pos):
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            price = sym_info.bid if pos.type == 0 else sym_info.ask
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick:
                price = tick.bid if pos.type == 0 else tick.ask

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "price": price,
                "deviation": 20,
                "magic": 0,
                "comment": "CLA close fallback",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": self.get_filling_mode(pos.symbol),
            }
            res = self._send_order_with_check(req)
            return {
                "ticket": pos.ticket,
                "retcode": res.retcode if res else -1,
                "comment": res.comment if res else "no response",
            }

        # Use 150 workers for maximum throughput in fallback
        workers = min(len(positions) + 5, 150)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(close_single, pos) for pos in positions]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                
        return results

    # ---- Hedge Lock ----

    def hedge_lock(self) -> dict:
        """Open an opposite position equal to net exposure to lock P/L."""
        positions = self._get_filtered_positions()
        buy_v = sum(p.volume for p in positions if p.type == 0)
        sell_v = sum(p.volume for p in positions if p.type == 1)
        net = round(buy_v - sell_v, 2)

        if abs(net) < 0.01:
            return {"status": "already_hedged", "net": 0}

        symbol = self.get_active_symbol()
        if not symbol:
            return {"status": "error", "msg": "No gold symbol resolved for this account"}
        sym_info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if sym_info is None or tick is None:
            return {"status": "error", "msg": "symbol/tick unavailable"}

        if net > 0:  # net long -> open SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            volume = net
        else:  # net short -> open BUY
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            volume = abs(net)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 0,
            "comment": "CLA hedge lock",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self.get_filling_mode(symbol),
        }
        res = self._send_order_with_check(req)
        return {
            "status": "ok" if res and res.retcode == mt5.TRADE_RETCODE_DONE else "error",
            "retcode": res.retcode if res else -1,
            "volume": volume,
            "direction": "SELL" if net > 0 else "BUY",
            "comment": res.comment if res else "",
        }

    # ──────────────────────────────────────────────────────────
    # Add-Layer Simulator (pure calculation)
    # ──────────────────────────────────────────────────────────

    def simulate_add_layer(self, extra_lots: float, direction: str = "BUY") -> dict:
        """
        Preview hypothetical MC price/distance if *extra_lots* were added.
        Does NOT place any orders.
        """
        state = self.get_state()
        if not state["connected"] or state["point"] == 0:
            return {"error": "not connected or no symbol data"}

        sym = self.get_active_symbol()
        if not sym:
            return {"error": "Symbol emas tidak ditemukan di akun ini"}
        sym_info = mt5.symbol_info(sym) if mt5 else None
        tick = mt5.symbol_info_tick(sym) if mt5 else None
        if sym_info is None or tick is None:
            return {"error": "symbol info unavailable"}

        mid = (tick.bid + tick.ask) / 2.0
        point = sym_info.point
        mc_thresh = self.cfg.get("mc_threshold_pct", 50)

        # Current lots
        buy_lots = state["buy_lots"]
        sell_lots = state["sell_lots"]

        if direction == "BUY":
            buy_lots += extra_lots
        else:
            sell_lots += extra_lots

        new_net = buy_lots - sell_lots

        # Calculate specific existing margin for our filtered positions
        specific_margin = 0.0
        margin_calc_failed = False
        magic = self.cfg.get("magic_number", 0)
        raw_positions = mt5.positions_get(symbol=sym)
        if raw_positions:
            filtered_pos = [p for p in raw_positions if p.magic == magic]
            for p in filtered_pos:
                order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                calc_m = mt5.order_calc_margin(order_type, p.symbol, p.volume, p.price_open)
                if calc_m is not None:
                    specific_margin += calc_m
                else:
                    margin_calc_failed = True
                    break

        acct = mt5.account_info()
        if acct is None:
            return {"error": "account info unavailable"}

        if not margin_calc_failed and specific_margin > 0:
            current_used_margin = specific_margin
        else:
            current_used_margin = state["margin"]

        # Calculate exact margin for the proposed new layer
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        new_layer_margin = mt5.order_calc_margin(order_type, sym, extra_lots, mid)
        if new_layer_margin is None:
            # Fallback calculation if order_calc_margin fails
            leverage = acct.leverage if acct.leverage else 1
            new_layer_margin = extra_lots * sym_info.trade_contract_size * mid / leverage

        new_margin = current_used_margin + new_layer_margin
        equity = state["equity"]  # stays same until PnL changes

        # point value
        pv = (sym_info.trade_tick_value / sym_info.trade_tick_size) if sym_info.trade_tick_size else 0

        new_mc_price = 0.0
        new_mc_dist_pips = 0.0
        if abs(new_net) > 1e-9 and new_margin > 0 and pv > 0:
            eq_at_mc = new_margin * mc_thresh / 100.0
            loss = equity - eq_at_mc
            move = loss / (abs(new_net) * pv)
            if new_net > 0:
                new_mc_price = mid - move
            else:
                new_mc_price = mid + move
            new_mc_dist_pips = round((abs(mid - new_mc_price) / point) / 10.0, 1) if point else 0.0

        # Calculate new average price
        new_avg_price = 0.0
        current_total_lots = state.get("total_lots", 0.0)
        current_avg_combined = state.get("avg_price_combined", 0.0)
        
        new_total_lots = current_total_lots + extra_lots
        if new_total_lots > 0:
            new_avg_price = ((current_avg_combined * current_total_lots) + (extra_lots * mid)) / new_total_lots

        # Safety classification
        if new_mc_dist_pips >= 1000.0:
            safety = "SAFE"
        elif new_mc_dist_pips >= 700.0:
            safety = "WARNING"
        else:
            safety = "DANGER"

        return {
            "new_mc_price": round(new_mc_price, sym_info.digits),
            "new_mc_distance_pips": new_mc_dist_pips,
            "new_net_lots": round(new_net, 2),
            "new_margin_est": round(new_margin, 2),
            "new_avg_price": round(new_avg_price, sym_info.digits),
            "safety": safety,
        }

    # ──────────────────────────────────────────────────────────
    # Screenshot / Journal
    # ──────────────────────────────────────────────────────────

    def capture_screenshot(self, label: str = "action") -> Optional[str]:
        """Capture screen and save to screenshots/ directory."""
        ss_dir = self.cfg.get("screenshot_dir", "screenshots")
        os.makedirs(ss_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(ss_dir, f"{label}_{timestamp}.png")
        try:
            if ImageGrab is not None:
                img = ImageGrab.grab()
                img.save(filename)
                return filename
        except Exception as exc:
            print(f"[MT5Manager] Screenshot error: {exc}")
        return None

    # ──────────────────────────────────────────────────────────
    # Historical Performance
    # ──────────────────────────────────────────────────────────

    def fetch_historical_performance(self, start_time: datetime, end_time: datetime, is_all_time: bool = False) -> dict:
        """Fetch MT5 history deals for the given datetime range and compute performance metrics."""
        if mt5 is None or not self.is_connected():
            return {"error": "Not connected to MT5."}
            
        from datetime import timedelta
        
        # Strip tzinfo so we have pure naive datetimes representing LOCAL date boundaries.
        start_time = start_time.replace(tzinfo=None)
        end_time = end_time.replace(tzinfo=None)

        # Convert to local POSIX epoch timestamps to perfectly match Daily Goal time logic
        start_broker_sec = int(start_time.timestamp())
        end_broker_sec = int(end_time.timestamp())
        
        if is_all_time:
            start_broker_sec = 0 # Unix epoch 0 ensures all time
            
        # Fetch deals using a safely wide padded window in local time to bypass MT5 timezone bugs
        now_local = datetime.now()
        fetch_start = start_time - timedelta(days=2) if not is_all_time else datetime(2020, 1, 1)
        fetch_end = end_time + timedelta(days=2)
        if fetch_end > now_local + timedelta(days=1):
            fetch_end = now_local + timedelta(days=1)
            
        raw_deals = mt5.history_deals_get(fetch_start, fetch_end)
        
        if raw_deals is None:
            return {"error": f"Failed to retrieve history, error code: {mt5.last_error()}"}
            
        # Precisely filter deals using the integer broker timestamps
        magic = self.cfg.get("magic_number", 0)
        deals = []
        for d in raw_deals:
            if start_broker_sec <= d.time <= end_broker_sec:
                deals.append(d)
            
        total_profit = 0.0
        total_loss = 0.0
        net_profit = 0.0
        win_trades = 0
        loss_trades = 0
        
        from datetime import timedelta
        
        valid_deals = []
        for d in deals:
            if d.type in (0, 1) and d.magic == magic:
                if (d.profit + d.commission + d.swap) != 0:
                    valid_deals.append(d)
                    
        range_days = 0
        if valid_deals:
            first_deal_time = valid_deals[0].time
            
            # [TRIMMING LOGIC]: Jika All-Time, jangan gunakan start_time default (2024) yang statis
            # Geser start_time ke hari transaksi pertama agar chart tidak kosong melompong di awal
            if is_all_time:
                start_time = datetime.fromtimestamp(first_deal_time)
                
            range_days = (end_broker_sec - first_deal_time) / 86400.0

        group_by_month = range_days > 60

        daily_data = {}
        # Pre-fill dictionary with all dates in the range to ensure continuous chronological X-axis
        if group_by_month:
            current = start_time.replace(day=1)
            end = end_time
            while current <= end:
                daily_data[current.strftime("%Y-%m")] = {"gross_profit": 0.0, "gross_loss": 0.0}
                next_month = current.month % 12 + 1
                next_year = current.year + (current.month // 12)
                current = current.replace(year=next_year, month=next_month)
        else:
            current_date = start_time.date()
            end_date = end_time.date()
            while current_date <= end_date:
                daily_data[current_date.strftime("%Y-%m-%d")] = {"gross_profit": 0.0, "gross_loss": 0.0}
                current_date += timedelta(days=1)
            
        # OPTIMIZE PROCESSING SPEED: Fast computation for deal aggregations
        for d in valid_deals:
            net_amt = d.profit + d.commission + d.swap
            if net_amt > 0:
                win_trades += 1
                total_profit += net_amt
            elif net_amt < 0:
                loss_trades += 1
                total_loss += abs(net_amt)
                
        net_profit = total_profit - total_loss
        
        for deal in valid_deals:
            deal_dt = datetime.fromtimestamp(deal.time)
            key = f"{deal_dt.year:04d}-{deal_dt.month:02d}" if group_by_month else f"{deal_dt.year:04d}-{deal_dt.month:02d}-{deal_dt.day:02d}"
            
            if key in daily_data:
                net_amt = deal.profit + deal.commission + deal.swap
                if net_amt > 0:
                    daily_data[key]["gross_profit"] += net_amt
                else:
                    daily_data[key]["gross_loss"] += abs(net_amt)
                    
        total_trades = win_trades + loss_trades
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Build chronological arrays for plotting
        chart_dates = sorted(list(daily_data.keys()))
        chart_gross_profits = []
        chart_gross_losses = []
        chart_net_profits = []
        
        cumulative_net = 0.0
        for d in chart_dates:
            gp = daily_data[d]["gross_profit"]
            gl = daily_data[d]["gross_loss"]
            day_net = gp - gl
            cumulative_net += day_net
            
            chart_gross_profits.append(gp)
            chart_gross_losses.append(gl)
            chart_net_profits.append(cumulative_net)
            
        chart_data = {
            "dates": chart_dates,
            "gross_profits": chart_gross_profits,
            "gross_losses": chart_gross_losses,
            "net_profits": chart_net_profits
        }
        
        return {
            "net_profit_native": round(net_profit, 2),
            "net_profit_usc": round(net_profit, 2),
            "total_profit_native": round(total_profit, 2),
            "total_profit_usc": round(total_profit, 2),
            "total_loss_native": round(total_loss, 2),
            "total_loss_usc": round(total_loss, 2),
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "start": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "chart_data": chart_data
        }

    def get_candles(self, symbol: str, timeframe_str: str, count: int = 100) -> list[dict]:
        if mt5 is None:
            return []
            
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
        
        print(f"[get_candles] Requesting symbol='{symbol}' timeframe='{timeframe_str}' count={count}")
        tf_constant = tf_map.get(timeframe_str)
        print(f"[get_candles] Mapped timeframe constant: {tf_constant}")
        
        # Pastikan symbol ter-select dulu sebelum ambil rates
        selected = mt5.symbol_select(symbol, True)
        print(f"[get_candles] symbol_select result: {selected}")
        
        if tf_constant is None:
            print("[get_candles] Invalid timeframe string, returning empty.")
            return []
            
        rates = mt5.copy_rates_from_pos(symbol, tf_constant, 0, count)
        print(f"[get_candles] copy_rates_from_pos returned: {type(rates)}, "
              f"length: {len(rates) if rates is not None else 'None'}")
        
        if rates is None or len(rates) == 0:
            error = mt5.last_error()
            print(f"[get_candles] mt5.last_error(): {error}")
            return []
            
        return [
            {
                'time': r['time'],
                'open': r['open'],
                'high': r['high'],
                'low': r['low'],
                'close': r['close']
            }
            for r in rates
        ]

    def get_daily_pnl_map(self, year: int, month: int) -> dict:
        """Get daily PnL map for a given month, grouped by local machine day."""
        if mt5 is None or not self.is_connected():
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            return {day: 0.0 for day in range(1, last_day + 1)}
            
        import calendar
        from datetime import datetime, timedelta
        
        last_day = calendar.monthrange(year, month)[1]
        
        # 1. Gunakan waktu lokal mesin
        start_time = datetime(year, month, 1, 0, 0, 0)
        end_time = datetime(year, month, last_day, 23, 59, 59)
        
        now_local = datetime.now()
        if year == now_local.year and month == now_local.month:
            # Batasi sampai waktu saat ini untuk bulan berjalan
            end_time = now_local
            
        start_sec = int(start_time.timestamp())
        end_sec = int(end_time.timestamp())
        
        # Padded window for MT5 fetch
        fetch_start = start_time - timedelta(days=2)
        fetch_end = end_time + timedelta(days=2)
        if fetch_end > now_local + timedelta(days=1):
            fetch_end = now_local + timedelta(days=1)
            
        raw_deals = mt5.history_deals_get(fetch_start, fetch_end)
        
        # Inisialisasi dictionary untuk setiap tanggal (1 sampai akhir bulan)
        daily_pnl = {day: 0.0 for day in range(1, last_day + 1)}
        
        if raw_deals is None:
            return daily_pnl
            
        magic = self.cfg.get("magic_number", 0)
        
        for d in raw_deals:
            if start_sec <= d.time <= end_sec:
                if d.type in (0, 1) and d.magic == magic:
                    pnl = d.profit + d.commission + d.swap
                    if pnl != 0:
                        deal_local_dt = datetime.fromtimestamp(d.time)
                        day = deal_local_dt.day
                        if 1 <= day <= last_day:
                            daily_pnl[day] += pnl
                            
        return daily_pnl


    def get_daily_pnl_map(self, year: int, month: int) -> dict:
        """Get daily PnL map for a given month, grouped by local machine day."""
        if mt5 is None or not self.is_connected():
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            return {day: 0.0 for day in range(1, last_day + 1)}
            
        import calendar
        from datetime import datetime, timedelta
        
        last_day = calendar.monthrange(year, month)[1]
        
        # 1. Gunakan waktu lokal mesin
        start_time = datetime(year, month, 1, 0, 0, 0)
        end_time = datetime(year, month, last_day, 23, 59, 59)
        
        start_sec = int(start_time.timestamp())
        end_sec = int(end_time.timestamp())
        
        now_local = datetime.now()
        
        # Padded window for MT5 fetch
        fetch_start = start_time - timedelta(days=2)
        fetch_end = end_time + timedelta(days=2)
        if fetch_end > now_local + timedelta(days=1):
            fetch_end = now_local + timedelta(days=1)
            
        raw_deals = mt5.history_deals_get(fetch_start, fetch_end)
        
        # Inisialisasi dictionary untuk setiap tanggal (1 sampai akhir bulan)
        daily_pnl = {day: 0.0 for day in range(1, last_day + 1)}
        
        if raw_deals is None:
            return daily_pnl
            
        magic = self.cfg.get("magic_number", 0)
        
        for d in raw_deals:
            if start_sec <= d.time <= end_sec:
                if d.type in (0, 1) and d.magic == magic:
                    pnl = d.profit + d.commission + d.swap
                    if pnl != 0:
                        deal_local_dt = datetime.fromtimestamp(d.time)
                        day = deal_local_dt.day
                        if 1 <= day <= last_day:
                            daily_pnl[day] += pnl
                            
        return daily_pnl
