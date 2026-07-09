"""
gui_dashboard.py
Modern CustomTkinter dashboard for Cent Layering Assistant - Mission Control.

Layout:
  Panel A  – Header & System (top bar)
  Panel B  – Live Monitor (center-left)
  Panel C  – Risk & MC Calculator (center-right)
  Panel D  – Action Panel (lower section)
  Panel E  – Emergency & Safety (bottom bar)
"""

import threading
import winsound
import customtkinter as ctk
from collections import deque
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from currency_utils import (
    get_currency_label, to_usd, to_idr, from_idr_to_account,
    format_amount, format_amount_short, format_with_idr,
    format_perf_card_primary, format_perf_card_secondary,
)
from candle_chart import CandleChart

# ── Theme colours ────────────────────────────────────────────
BG_DARK       = "#0d1117"
CARD_BG       = "#161b22"
CARD_BORDER   = "#30363d"
GOLD          = "#f0b90b"
GOLD_DIM      = "#a07d08"
TEXT_PRIMARY   = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
GREEN         = "#2ea043"
GREEN_BRIGHT  = "#3fb950"
RED           = "#f85149"
RED_DIM       = "#da3633"
ORANGE        = "#d29922"
YELLOW        = "#e3b341"
BLUE          = "#58a6ff"

FONT_FAMILY   = "Segoe UI"
FONT_MONO     = "Consolas"


class Dashboard(ctk.CTk):
    """Main application window."""

    def __init__(self, mt5_mgr, cfg_mgr):
        super().__init__()

        self.mt5 = mt5_mgr
        self.cfg = cfg_mgr

        # ── window setup ─────────────────────────────────────
        self.title("Cent Layering Assistant – Mission Control")
        self.geometry("1120x820")
        self.update_idletasks()
        self.minsize(1050, 750)
        self.configure(fg_color=BG_DARK)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        # Override TCombobox and DateEntry ttk styles to match CTk blue perfectly across all states
        from tkinter import ttk
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('TCombobox', 
                        fieldbackground='#1f538d', 
                        foreground='white', 
                        background='#1f538d', 
                        arrowcolor='white',
                        bordercolor='#1f538d')

        style.configure('DateEntry', 
                        fieldbackground='#1f538d', 
                        foreground='white', 
                        background='#1f538d', 
                        arrowcolor='white',
                        bordercolor='#1f538d',
                        lightcolor='#1f538d',
                        darkcolor='#1f538d')

        state_maps = {
            'fieldbackground': [('readonly', '#1f538d'), ('focus', '#1f538d'), ('active', '#245fa2'), ('pressed', '#183e6d')],
            'background': [('readonly', '#1f538d'), ('focus', '#1f538d'), ('active', '#245fa2'), ('pressed', '#183e6d')],
            'foreground': [('readonly', 'white'), ('focus', 'white'), ('active', 'white'), ('pressed', 'white')],
            'arrowcolor': [('readonly', 'white'), ('focus', 'white'), ('active', 'white'), ('pressed', 'white')],
            'bordercolor': [('readonly', '#1f538d'), ('focus', '#1f538d'), ('active', '#245fa2'), ('pressed', '#183e6d')]
        }

        style.map('TCombobox', **state_maps)
        style.map('DateEntry', **state_maps)

        # flash state
        self._pnl_flash = False
        self._equity_alarm_flashing = False
        self._prev_connected = True
        
        # pnl calendar state
        self._pnl_calendar_cache = {}  # (year, month) -> dict of pnl
        self._last_calendar_refresh_day = None
        # chart state
        self._price_history = deque(maxlen=80)
        self._simulated_mc_price = 0.0

        # configure root grid responsiveness
        self.grid_columnconfigure(0, weight=1, uniform="A")
        self.grid_columnconfigure(1, weight=1, uniform="A")
        self.grid_rowconfigure(0, weight=0) # Header – fixed
        self.grid_rowconfigure(1, weight=1) # Monitors – stretches
        self.grid_rowconfigure(2, weight=0) # Action grid – FIXED, never squishes

        # build panels
        self._build_panel_a()
        
        # main tabview
        self.tabview = ctk.CTkTabview(self, fg_color=BG_DARK, corner_radius=10, text_color=TEXT_PRIMARY, segmented_button_selected_color=GREEN_BRIGHT, segmented_button_selected_hover_color=GREEN)
        self.tabview.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=4)
        
        self.tab_live = self.tabview.add("Live Trading")
        self.tab_live.grid_columnconfigure(0, weight=1, uniform="B")
        self.tab_live.grid_columnconfigure(1, weight=1, uniform="B")
        self.tab_live.grid_rowconfigure(0, weight=1)
        
        self.tab_perf = self.tabview.add("PERFORMANCE ANALYTICS")
        self.tab_perf.grid_columnconfigure(0, weight=1)
        self.tab_perf.grid_rowconfigure(0, weight=1)
        
        self._build_panel_b(self.tab_live)
        self._build_panel_c(self.tab_live)
        self._build_performance_tab(self.tab_perf)

        self.tab_live.grid_rowconfigure(1, weight=0)
        self._build_action_grid(self.tab_live)

        # start UI refresh loop
        self.after(200, self._refresh_ui)

        # on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────────────────────────────────────
    # PANEL A – Header & System
    # ──────────────────────────────────────────────────────────

    def _build_panel_a(self):
        frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10,
                             border_width=1, border_color=CARD_BORDER)
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=12, pady=(10, 4))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        # -- heartbeat --
        self._heartbeat_canvas = ctk.CTkCanvas(inner, width=18, height=18,
                                                bg=CARD_BG, highlightthickness=0)
        self._heartbeat_canvas.pack(side="left")
        self._hb_dot = self._heartbeat_canvas.create_oval(3, 3, 15, 15, fill=RED, outline="")

        self._lbl_conn = ctk.CTkLabel(inner, text="Disconnected",
                                       font=(FONT_FAMILY, 13, "bold"),
                                       text_color=RED)
        self._lbl_conn.pack(side="left", padx=(6, 20))

        # ADD LOGIN BUTTON HERE
        self._btn_login = ctk.CTkButton(inner, text="Login MT5", width=80, height=28,
                                        font=(FONT_FAMILY, 11, "bold"),
                                        fg_color=BLUE, hover_color="#79c0ff", text_color=BG_DARK,
                                        command=self._open_login_popup)
        self._btn_login.pack(side="left", padx=(0, 20))

        # -- spread --
        ctk.CTkLabel(inner, text="Spread:", font=(FONT_FAMILY, 12),
                     text_color=TEXT_SECONDARY).pack(side="left")
        self._lbl_spread = ctk.CTkLabel(inner, text="--",
                                         font=(FONT_MONO, 13, "bold"),
                                         text_color=TEXT_PRIMARY)
        self._lbl_spread.pack(side="left", padx=(4, 20))

        # -- IDR rate --
        ctk.CTkLabel(inner, text="USD/IDR:", font=(FONT_FAMILY, 12),
                     text_color=TEXT_SECONDARY).pack(side="left")
        self._lbl_idr = ctk.CTkLabel(inner, text="--",
                                      font=(FONT_MONO, 13, "bold"),
                                      text_color=GOLD)
        self._lbl_idr.pack(side="left", padx=(4, 8))

        self._entry_idr = ctk.CTkEntry(inner, width=90, height=28,
                                        font=(FONT_MONO, 12),
                                        placeholder_text="manual rate")
        self._entry_idr.pack(side="left", padx=(0, 4))
        self._btn_idr_set = ctk.CTkButton(inner, text="Set", width=40, height=28,
                                           font=(FONT_FAMILY, 11),
                                           fg_color=GOLD_DIM, hover_color=GOLD,
                                           text_color=BG_DARK,
                                           command=self._on_set_idr_manual)
        self._btn_idr_set.pack(side="left", padx=(0, 20))

        # -- account currency selector --
        ctk.CTkLabel(inner, text="Acct:", font=(FONT_FAMILY, 12),
                     text_color=TEXT_SECONDARY).pack(side="left")
        self._opt_acct_currency = ctk.CTkOptionMenu(
            inner, values=["USC", "USD", "IDR"],
            width=70, height=28, font=(FONT_FAMILY, 11),
            fg_color=CARD_BORDER, button_color=GOLD_DIM, button_hover_color=GOLD,
            command=self._on_acct_currency_change)
        self._opt_acct_currency.set(self.cfg.get("account_currency", "USC"))
        self._opt_acct_currency.pack(side="left", padx=(4, 20))

        # -- hotkey switch & info --
        hotkey_frame = ctk.CTkFrame(inner, fg_color="transparent")
        hotkey_frame.pack(side="right")
        
        self._btn_hotkey_info = ctk.CTkButton(hotkey_frame, text="ℹ", width=24, height=24,
                                              fg_color="transparent", hover_color=CARD_BORDER,
                                              text_color=GOLD, font=(FONT_FAMILY, 16, "bold"),
                                              command=self._show_hotkey_info)
        self._btn_hotkey_info.pack(side="right", padx=(4, 0))
        
        self._hotkey_var = ctk.BooleanVar(value=self.cfg.get("hotkeys_enabled", False))
        self._switch_hotkey = ctk.CTkSwitch(hotkey_frame, text="Hotkeys",
                                             variable=self._hotkey_var,
                                             font=(FONT_FAMILY, 12),
                                             text_color=TEXT_SECONDARY,
                                             progress_color=GOLD,
                                             command=self._on_hotkey_toggle)
        self._switch_hotkey.pack(side="right")

    def _open_login_popup(self):
        popup = ctk.CTkToplevel(self, fg_color=BG_DARK)
        popup.title("Login to MT5")
        popup.geometry("380x280")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        # Center popup
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 280) // 2
        popup.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(popup, fg_color=CARD_BG, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="Account ID:", font=(FONT_FAMILY, 12)).grid(row=0, column=0, sticky="w", pady=10, padx=10)
        
        known_accounts = self.cfg.get("known_accounts", {})
        saved_ids = list(known_accounts.keys())
        account_labels = self.cfg.get("account_labels", {})
        
        display_values = []
        for acc_id in saved_ids:
            lbl = account_labels.get(acc_id, "")
            if lbl:
                display_values.append(f"{acc_id} - {lbl}")
            else:
                display_values.append(acc_id)
        
        entry_account = ctk.CTkComboBox(frame, width=180, values=display_values if display_values else [""],
                                        button_color="#1f538d", button_hover_color="#14375e")
        entry_account.grid(row=0, column=1, pady=10, padx=10, sticky="w")
        
        last_id = self.cfg.get("last_login_id", "")
        if last_id:
            lbl = account_labels.get(last_id, "")
            if lbl:
                entry_account.set(f"{last_id} - {lbl}")
            else:
                entry_account.set(last_id)
        elif not display_values:
            entry_account.set("")

        ctk.CTkLabel(frame, text="Password:", font=(FONT_FAMILY, 12)).grid(row=1, column=0, sticky="w", pady=10, padx=10)
        entry_password = ctk.CTkEntry(frame, width=180, show="*")
        entry_password.grid(row=1, column=1, pady=10, padx=10, sticky="w")

        ctk.CTkLabel(frame, text="Server:", font=(FONT_FAMILY, 12)).grid(row=2, column=0, sticky="w", pady=10, padx=10)
        
        # Server selection frame
        srv_frame = ctk.CTkFrame(frame, fg_color="transparent")
        srv_frame.grid(row=2, column=1, pady=10, padx=10, sticky="w")
        
        known_servers = self.cfg.get("known_servers", [])
        if not known_servers:
            known_servers = ["HFMarketsGlobal-Live19"]
            
        opt_values = known_servers + ["Custom..."]
        
        server_var = ctk.StringVar()
        opt_server = ctk.CTkOptionMenu(srv_frame, values=opt_values, variable=server_var, width=145)
        opt_server.pack(side="left")
        
        entry_custom_server = ctk.CTkEntry(srv_frame, width=145)
        
        last_srv = self.cfg.get("last_login_server", "")
        if last_srv in known_servers:
            server_var.set(last_srv)
        elif last_srv:
            server_var.set("Custom...")
            opt_server.pack_forget()
            entry_custom_server.pack(side="left")
            entry_custom_server.insert(0, last_srv)
        else:
            server_var.set(known_servers[0])
                
        def on_server_change(choice):
            if choice == "Custom...":
                opt_server.pack_forget()
                entry_custom_server.pack(side="left")
            else:
                entry_custom_server.pack_forget()
                opt_server.pack(side="left")
                
        opt_server.configure(command=on_server_change)
        
        def on_account_select(choice):
            actual_id = choice.split(" - ")[0].strip() if " - " in choice else choice.strip()
            if actual_id in known_accounts:
                srv = known_accounts[actual_id]
                if srv in known_servers:
                    server_var.set(srv)
                    on_server_change(srv)
                else:
                    server_var.set("Custom...")
                    entry_custom_server.delete(0, 'end')
                    entry_custom_server.insert(0, srv)
                    on_server_change("Custom...")
                    
        entry_account.configure(command=on_account_select)
        
        def add_custom_server():
            if server_var.get() == "Custom...":
                new_srv = entry_custom_server.get().strip()
                if new_srv and new_srv not in known_servers:
                    known_servers.append(new_srv)
                    self.cfg.set("known_servers", known_servers)
                    opt_server.configure(values=known_servers + ["Custom..."])
                    server_var.set(new_srv)
                    on_server_change(new_srv)
                    import tkinter.messagebox as mb
                    mb.showinfo("Server Added", f"Server '{new_srv}' added to known servers.")
        
        btn_add_srv = ctk.CTkButton(srv_frame, text="+", width=25, command=add_custom_server)
        btn_add_srv.pack(side="left", padx=(5, 0))

        def perform_login():
            raw_acc = entry_account.get().strip()
            acc = raw_acc.split(" - ")[0].strip() if " - " in raw_acc else raw_acc
            pwd = entry_password.get().strip()
            
            if server_var.get() == "Custom...":
                srv = entry_custom_server.get().strip()
            else:
                srv = server_var.get().strip()
                
            if not acc or not pwd or not srv:
                import tkinter.messagebox as mb
                mb.showerror("Login Error", "Please fill in all fields.")
                return

            btn_connect.configure(state="disabled", text="Connecting...")
            popup.update_idletasks()
            
            def do_login():
                try:
                    success, msg = self.mt5.login_account(acc, pwd, srv)
                    if success:
                        def on_success():
                            account_labels = self.cfg.get("account_labels", {})
                            if acc not in account_labels:
                                dialog = ctk.CTkInputDialog(text="Simpan akun ini?\nMasukkan label/nama untuk akun ini (Opsional):", title="Label Akun")
                                label = dialog.get_input()
                                if label:
                                    account_labels[acc] = label.strip()
                                    self.cfg.set("account_labels", account_labels)
                            popup.destroy()
                        self.after(0, on_success)
                    else:
                        def on_fail():
                            btn_connect.configure(state="normal", text="Connect")
                            import tkinter.messagebox as mb
                            mb.showerror("Login Error", msg)
                        self.after(0, on_fail)
                except Exception as e:
                    def on_err():
                        btn_connect.configure(state="normal", text="Connect")
                        import tkinter.messagebox as mb
                        mb.showerror("Login Exception", f"An unexpected error occurred:\n{e}")
                    self.after(0, on_err)

            threading.Thread(target=do_login, daemon=True).start()

        btn_connect = ctk.CTkButton(frame, text="Connect", font=(FONT_FAMILY, 12, "bold"), fg_color=GREEN_BRIGHT, hover_color=GREEN, command=perform_login)
        btn_connect.grid(row=3, column=0, columnspan=2, pady=(20, 10))

    # ──────────────────────────────────────────────────────────
    # PANEL B + C (Live Monitor & Risk Calculator)
    # ──────────────────────────────────────────────────────────

    # ── Panel B – Live Monitor ────────────────────────────────
    def _build_panel_b(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color=CARD_BG, corner_radius=10,
                                       border_width=1, border_color=CARD_BORDER)
        frame.grid(row=0, column=0, sticky="nsew", padx=(12, 4), pady=4)

        header = ctk.CTkLabel(frame, text="📊  LIVE MONITOR", font=(FONT_FAMILY, 13, "bold"),
                              text_color=GOLD, anchor="w")
        header.pack(fill="x", padx=16, pady=(12, 2))

        # -- PnL --
        pnl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        pnl_frame.pack(fill="x", padx=16, pady=(15, 20))
        
        cur = get_currency_label(self.cfg)
        pnl_init = f"+0 {cur}  (Rp 0)" if cur != "IDR" else "+Rp 0"
        self._lbl_pnl = ctk.CTkLabel(pnl_frame, text=pnl_init,
                                      font=(FONT_MONO, 24, "bold"),
                                      text_color=GREEN_BRIGHT)
        self._lbl_pnl.pack(anchor="w")
        
        self._lbl_pnl_pct = ctk.CTkLabel(pnl_frame, text="+0.00% dari modal",
                                         font=(FONT_FAMILY, 14, "bold"),
                                         text_color=GREEN_BRIGHT)
        self._lbl_pnl_pct.pack(anchor="w", pady=(2, 0))

        sep = ctk.CTkFrame(frame, height=1, fg_color=CARD_BORDER)
        sep.pack(fill="x", padx=16, pady=0)

        monitor_data_frame = ctk.CTkFrame(frame, fg_color="transparent")
        monitor_data_frame.pack(fill="x", padx=16, pady=(8, 12))
        monitor_data_frame.columnconfigure(0, weight=0, minsize=130)
        monitor_data_frame.columnconfigure(1, weight=1)

        labels_left = ["Layers:", "Total Lots:", "Avg Price:", "Avg Distance:", "Layer Range:"]
        self._monitor_vals: dict[str, ctk.CTkLabel] = {}
        for i, lbl_text in enumerate(labels_left):
            lbl = ctk.CTkLabel(monitor_data_frame, text=lbl_text, width=130,
                               font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY, anchor="w")
            lbl.grid(row=i, column=0, sticky="w", pady=4)
            val = ctk.CTkLabel(monitor_data_frame, text="--", font=(FONT_MONO, 13, "bold"),
                               text_color=TEXT_PRIMARY, anchor="w")
            val.grid(row=i, column=1, sticky="w", padx=(10, 0), pady=4)
            self._monitor_vals[lbl_text] = val

        # -- Daily Goal & Risk Tracker --
        sep2 = ctk.CTkFrame(frame, height=1, fg_color=CARD_BORDER)
        sep2.pack(fill="x", padx=16, pady=(12, 12))

        tracker_header = ctk.CTkLabel(frame, text="\U0001f3af DAILY GOAL & RISK TRACKER", font=(FONT_FAMILY, 12, "bold"), text_color=GOLD, anchor="w")
        tracker_header.pack(fill="x", padx=16)

        tracker_frame = ctk.CTkFrame(frame, fg_color="transparent")
        tracker_frame.pack(fill="x", padx=16, pady=8)
        
        # Session counter
        self._lbl_sessions = ctk.CTkLabel(tracker_frame, text="Daily Sessions Completed: 0", font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_PRIMARY, anchor="w")
        self._lbl_sessions.pack(fill="x", pady=(0, 8))

        # Setup inner frame
        setup_f = ctk.CTkFrame(tracker_frame, fg_color=BG_DARK, corner_radius=6)
        setup_f.pack(fill="x", pady=4)
        setup_f.grid_columnconfigure((1,2,3), weight=1)

        import tkinter as tk
        
        self._var_tgt_pct = tk.StringVar(value=str(self.cfg.get("daily_tgt_pct", 0)))
        self._var_tgt_usc = tk.StringVar(value=str(self.cfg.get("daily_tgt_usc", 0)))
        self._var_tgt_idr = tk.StringVar(value=str(self.cfg.get("daily_tgt_idr", 0)))
        
        self._var_loss_pct = tk.StringVar(value=str(self.cfg.get("daily_loss_pct", 0)))
        self._var_loss_usc = tk.StringVar(value=str(self.cfg.get("daily_loss_usc", 0)))
        self._var_loss_idr = tk.StringVar(value=str(self.cfg.get("daily_loss_idr", 0)))
        
        self._disable_trace = False

        def _on_tgt_change(var_name, *args):
            if self._disable_trace: return
            try:
                s = self.mt5.get_state() if self.mt5 else {}
                bal = s.get("balance", 0.0)
                net = s.get("daily_net_pnl_usc", 0.0)
                start_bal = bal - net if bal > 0 else 1000.0  # fallback
                
                self._disable_trace = True
                if var_name == "pct":
                    val = float(self._var_tgt_pct.get() or 0)
                    acct_val = start_bal * (val / 100.0)
                    idr = to_idr(acct_val, self.cfg)
                    self._var_tgt_usc.set(f"{acct_val:.2f}")
                    self._var_tgt_idr.set(f"{idr:,.0f}")
                elif var_name == "usc":
                    val = float(self._var_tgt_usc.get() or 0)
                    pct = (val / start_bal * 100) if start_bal > 0 else 0
                    idr = to_idr(val, self.cfg)
                    self._var_tgt_pct.set(f"{pct:.2f}")
                    self._var_tgt_idr.set(f"{idr:,.0f}")
                elif var_name == "idr":
                    val_str = self._var_tgt_idr.get().replace(",", "").replace(".", "")
                    val = float(val_str or 0)
                    acct_val = from_idr_to_account(val, self.cfg)
                    pct = (acct_val / start_bal * 100) if start_bal > 0 else 0
                    self._var_tgt_usc.set(f"{acct_val:.2f}")
                    self._var_tgt_pct.set(f"{pct:.2f}")
                    
                self.cfg.set_many({
                    "daily_tgt_pct": self._var_tgt_pct.get(),
                    "daily_tgt_usc": self._var_tgt_usc.get(),
                    "daily_tgt_idr": self._var_tgt_idr.get()
                })
            except ValueError:
                pass
            finally:
                self._disable_trace = False
                
        def _on_loss_change(var_name, *args):
            if self._disable_trace: return
            try:
                s = self.mt5.get_state() if self.mt5 else {}
                bal = s.get("balance", 0.0)
                net = s.get("daily_net_pnl_usc", 0.0)
                start_bal = bal - net if bal > 0 else 1000.0
                
                self._disable_trace = True
                if var_name == "pct":
                    val = float(self._var_loss_pct.get() or 0)
                    acct_val = start_bal * (val / 100.0)
                    idr = to_idr(acct_val, self.cfg)
                    self._var_loss_usc.set(f"{acct_val:.2f}")
                    self._var_loss_idr.set(f"{idr:,.0f}")
                elif var_name == "usc":
                    val = float(self._var_loss_usc.get() or 0)
                    pct = (val / start_bal * 100) if start_bal > 0 else 0
                    idr = to_idr(val, self.cfg)
                    self._var_loss_pct.set(f"{pct:.2f}")
                    self._var_loss_idr.set(f"{idr:,.0f}")
                elif var_name == "idr":
                    val_str = self._var_loss_idr.get().replace(",", "").replace(".", "")
                    val = float(val_str or 0)
                    acct_val = from_idr_to_account(val, self.cfg)
                    pct = (acct_val / start_bal * 100) if start_bal > 0 else 0
                    self._var_loss_usc.set(f"{acct_val:.2f}")
                    self._var_loss_pct.set(f"{pct:.2f}")
                    
                self.cfg.set_many({
                    "daily_loss_pct": self._var_loss_pct.get(),
                    "daily_loss_usc": self._var_loss_usc.get(),
                    "daily_loss_idr": self._var_loss_idr.get()
                })
            except ValueError:
                pass
            finally:
                self._disable_trace = False

        self._var_tgt_pct.trace_add("write", lambda *a: _on_tgt_change("pct"))
        self._var_tgt_usc.trace_add("write", lambda *a: _on_tgt_change("usc"))
        self._var_tgt_idr.trace_add("write", lambda *a: _on_tgt_change("idr"))

        self._var_loss_pct.trace_add("write", lambda *a: _on_loss_change("pct"))
        self._var_loss_usc.trace_add("write", lambda *a: _on_loss_change("usc"))
        self._var_loss_idr.trace_add("write", lambda *a: _on_loss_change("idr"))

        # Row 0 headers inside setup
        ctk.CTkLabel(setup_f, text="%", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=1)
        self._lbl_tracker_cur_hdr = ctk.CTkLabel(setup_f, text=get_currency_label(self.cfg), font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY)
        self._lbl_tracker_cur_hdr.grid(row=0, column=2)
        self._lbl_tracker_idr_hdr = ctk.CTkLabel(setup_f, text="IDR", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY)
        self._lbl_tracker_idr_hdr.grid(row=0, column=3)

        # Row 1 Tgt
        ctk.CTkLabel(setup_f, text="Profit Goal:", font=(FONT_FAMILY, 11), text_color=GREEN).grid(row=1, column=0, padx=(8,4), sticky="w")
        ctk.CTkEntry(setup_f, textvariable=self._var_tgt_pct, width=50, height=24).grid(row=1, column=1, padx=2, pady=2)
        ctk.CTkEntry(setup_f, textvariable=self._var_tgt_usc, width=60, height=24).grid(row=1, column=2, padx=2, pady=2)
        ctk.CTkEntry(setup_f, textvariable=self._var_tgt_idr, width=80, height=24).grid(row=1, column=3, padx=2, pady=2)

        # Row 2 Loss
        ctk.CTkLabel(setup_f, text="Max Loss:", font=(FONT_FAMILY, 11), text_color=RED).grid(row=2, column=0, padx=(8,4), sticky="w", pady=(0,8))
        ctk.CTkEntry(setup_f, textvariable=self._var_loss_pct, width=50, height=24).grid(row=2, column=1, padx=2, pady=(0,8))
        ctk.CTkEntry(setup_f, textvariable=self._var_loss_usc, width=60, height=24).grid(row=2, column=2, padx=2, pady=(0,8))
        ctk.CTkEntry(setup_f, textvariable=self._var_loss_idr, width=80, height=24).grid(row=2, column=3, padx=2, pady=(0,8))

        # Progress bars
        cur = get_currency_label(self.cfg)
        
        # 1. Daily Goal Progress
        gf = ctk.CTkFrame(tracker_frame, fg_color="transparent")
        gf.pack(fill="x", pady=(8,0))
        self._lbl_daily_goal = ctk.CTkLabel(gf, text=f"Daily Net: 0 {cur} (Rp 0) | 0%", font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_PRIMARY)
        self._lbl_daily_goal.pack(side="left")
        self._pb_daily_goal = ctk.CTkCanvas(tracker_frame, height=8, bg=CARD_BG, highlightthickness=0)
        self._pb_daily_goal.pack(fill="x", pady=(2,6))
        self._pb_daily_goal.bind("<Configure>", self._redraw_daily_goal_bar)

        # 2. Session Wins Progress
        wf = ctk.CTkFrame(tracker_frame, fg_color="transparent")
        wf.pack(fill="x", pady=(2,0))
        self._lbl_session_wins = ctk.CTkLabel(wf, text=f"Wins: 0 {cur} (Rp 0) | 0%", font=(FONT_FAMILY, 11), text_color=GREEN)
        self._lbl_session_wins.pack(side="left")
        self._pb_session_wins = ctk.CTkProgressBar(tracker_frame, progress_color=GREEN, height=8)
        self._pb_session_wins.set(0)
        self._pb_session_wins.pack(fill="x", pady=(2,4))

        # 3. Session Losses Progress
        lf = ctk.CTkFrame(tracker_frame, fg_color="transparent")
        lf.pack(fill="x", pady=(2,0))
        self._lbl_session_losses = ctk.CTkLabel(lf, text=f"Losses: 0 {cur} (Rp 0) | 0%", font=(FONT_FAMILY, 11), text_color=RED)
        self._lbl_session_losses.pack(side="left")
        self._pb_session_losses = ctk.CTkProgressBar(tracker_frame, progress_color=RED, height=8)
        self._pb_session_losses.set(0)
        self._pb_session_losses.pack(fill="x", pady=(2,4))

    # ── Panel C – Risk & MC Calculator ────────────────────────
    def _build_panel_c(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color=CARD_BG, corner_radius=10,
                                       border_width=1, border_color=CARD_BORDER)
        frame.grid(row=0, column=1, sticky="nsew", padx=(4, 12), pady=4)

        # Header
        header = ctk.CTkLabel(frame, text="\u26a0\ufe0f  RISK & MC CALCULATOR",
                              font=(FONT_FAMILY, 13, "bold"),
                              text_color=ORANGE, anchor="w")
        header.pack(fill="x", padx=16, pady=(12, 2))

        # Risk data table
        risk_data_frame = ctk.CTkFrame(frame, fg_color="transparent")
        risk_data_frame.pack(fill="x", padx=16, pady=(4, 4))

        risk_labels = ["Balance:", "Equity:", "Margin:", "Margin Lvl:", "MC Price:", "MC Distance:"]
        self._risk_vals: dict[str, ctk.CTkLabel] = {}
        for i, lbl_text in enumerate(risk_labels):
            lbl = ctk.CTkLabel(risk_data_frame, text=lbl_text, width=130,
                               font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY, anchor="w")
            lbl.grid(row=i, column=0, sticky="w", pady=4)
            val = ctk.CTkLabel(risk_data_frame, text="--", font=(FONT_MONO, 13, "bold"),
                               text_color=TEXT_PRIMARY, anchor="w")
            val.grid(row=i, column=1, sticky="w", padx=(10, 0), pady=4)
            self._risk_vals[lbl_text] = val

        # Live Chart
        self.live_chart = CandleChart(frame, self.mt5, title="Live Position Chart", height=220)
        self.live_chart.pack(fill="x", padx=16, pady=(10, 4))

        # Separator
        sep = ctk.CTkFrame(frame, height=1, fg_color=CARD_BORDER)
        sep.pack(fill="x", padx=16, pady=6)

        # Simulator header
        sim_header = ctk.CTkLabel(frame, text="\U0001f9ea Add-Layer Simulator",
                                   font=(FONT_FAMILY, 12, "bold"),
                                   text_color=BLUE, anchor="w")
        sim_header.pack(fill="x", padx=16)

        # Simulator controls
        sim_row = ctk.CTkFrame(frame, fg_color="transparent")
        sim_row.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(sim_row, text="+", font=(FONT_MONO, 14, "bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")
        self._entry_sim_lots = ctk.CTkEntry(sim_row, width=70, height=35,
                                             font=(FONT_MONO, 12),
                                             placeholder_text="0.10")
        self._entry_sim_lots.pack(side="left", padx=4)
        ctk.CTkLabel(sim_row, text="lot", font=(FONT_FAMILY, 12),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 6))

        self._sim_dir = ctk.CTkOptionMenu(sim_row, values=["BUY", "SELL"],
                                           width=70, height=35,
                                           font=(FONT_FAMILY, 11),
                                           fg_color=CARD_BORDER,
                                           button_color=GOLD_DIM,
                                           button_hover_color=GOLD)
        self._sim_dir.pack(side="left", padx=(0, 6))

        self._btn_sim = ctk.CTkButton(sim_row, text="Preview", width=68, height=35,
                                       font=(FONT_FAMILY, 11, "bold"),
                                       fg_color=BLUE, hover_color="#79c0ff",
                                       text_color=BG_DARK,
                                       command=self._on_simulate)
        self._btn_sim.pack(side="left")

        # Simulator result
        self._lbl_sim_result = ctk.CTkLabel(frame, text="",
                                             font=(FONT_MONO, 12),
                                             text_color=TEXT_SECONDARY,
                                             anchor="w", justify="left")
        self._lbl_sim_result.pack(fill="x", padx=16, pady=(2, 4))
        
        # Simulator Chart
        self.sim_chart = CandleChart(frame, self.mt5, title="Preview Simulator Chart", height=220)
        self.sim_chart.pack(fill="x", padx=16, pady=(4, 10))

    def _fetch_calendar_data(self, year: int, month: int, force_refresh: bool = False) -> dict:
        from datetime import datetime
        now = datetime.now()
        is_current_month = (year == now.year and month == now.month)
        
        need_fetch = False
        if (year, month) not in self._pnl_calendar_cache:
            need_fetch = True
        elif is_current_month:
            if self._last_calendar_refresh_day != now.day:
                need_fetch = True
            elif force_refresh:
                need_fetch = True
                
        if need_fetch:
            data = self.mt5.get_daily_pnl_map(year, month)
            self._pnl_calendar_cache[(year, month)] = data
            if is_current_month:
                self._last_calendar_refresh_day = now.day
                
        return self._pnl_calendar_cache.get((year, month), {})

    # ── Performance Analytics Tab ─────────────────────────────
    def _build_performance_tab(self, parent):
        import tkinter as tk
        try:
            from tkcalendar import DateEntry
        except ImportError:
            DateEntry = None

        from datetime import datetime
        import calendar

        frame = ctk.CTkScrollableFrame(parent, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        frame.pack(fill="both", expand=True, padx=12, pady=4)

        header = ctk.CTkLabel(frame, text="📈 PERFORMANCE ANALYTICS", font=(FONT_FAMILY, 15, "bold"), text_color=GOLD, anchor="w")
        header.pack(fill="x", padx=16, pady=(16, 8))

        # Config frame
        config_f = ctk.CTkFrame(frame, fg_color="transparent")
        config_f.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(config_f, text="Period:", font=(FONT_FAMILY, 12)).grid(row=0, column=0, sticky="w", pady=4, padx=4)
        
        self._perf_period_var = ctk.StringVar(value="Bulanan")
        
        # We need frames for custom vs monthly
        input_container = ctk.CTkFrame(config_f, fg_color="transparent")
        input_container.grid(row=0, column=2, sticky="w", padx=16)
        
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        now = datetime.now()
        
        # Monthly container
        monthly_f = ctk.CTkFrame(input_container, fg_color="transparent")
        self._perf_month_var = ctk.StringVar(value=months[now.month - 1])
        self._perf_year_var = ctk.StringVar(value=str(now.year))
        ctk.CTkOptionMenu(monthly_f, values=months, variable=self._perf_month_var, width=120).pack(side="left", padx=4)
        ctk.CTkOptionMenu(monthly_f, values=["2025", "2026", "2027"], variable=self._perf_year_var, width=80).pack(side="left", padx=4)

        # Weekly container
        mingguan_f = ctk.CTkFrame(input_container, fg_color="transparent")
        ctk.CTkLabel(mingguan_f, text="Pilih Minggu:").pack(side="left", padx=4)

        # Daily container
        harian_f = ctk.CTkFrame(input_container, fg_color="transparent")
        ctk.CTkLabel(harian_f, text="Pilih Tanggal:").pack(side="left", padx=4)

        # Custom container
        custom_f = ctk.CTkFrame(input_container, fg_color="transparent")
        ctk.CTkLabel(custom_f, text="Dari:").pack(side="left", padx=4)
        
        if DateEntry:
            cal_kwargs = dict(width=12, date_pattern='yyyy-mm-dd',
                              background='#11121a', foreground='#ffffff', bordercolor='#11121a', 
                              headersbackground='#11121a', headersforeground='#525866', 
                              selectbackground='#2e303f', selectforeground='#ffffff', 
                              normalbackground='#11121a', normalforeground='#ffffff', 
                              weekendbackground='#11121a', weekendforeground='#ff5a5a', 
                              othermonthbackground='#11121a', othermonthforeground='#3a3c4a',
                              othermonthwebackground='#11121a', othermonthweforeground='#4a2a2a',
                              font=("Segoe UI", 10), showweeknumbers=False)
                              
            self.cal_weekly = DateEntry(mingguan_f, **cal_kwargs)
            self.cal_weekly.pack(side="left", padx=4)
            
            self.cal_daily = DateEntry(harian_f, **cal_kwargs)
            self.cal_daily.pack(side="left", padx=4)
            
            self.cal_start = DateEntry(custom_f, **cal_kwargs)
            self.cal_start.pack(side="left", padx=4)
            
            ctk.CTkLabel(custom_f, text="Sampai:").pack(side="left", padx=4)
            self.cal_end = DateEntry(custom_f, **cal_kwargs)
            self.cal_end.pack(side="left", padx=4)
        else:
            ctk.CTkLabel(mingguan_f, text="(tkcalendar missing)").pack(side="left")
            ctk.CTkLabel(harian_f, text="(tkcalendar missing)").pack(side="left")
            ctk.CTkLabel(custom_f, text="(tkcalendar missing)").pack(side="left")

        def _on_period_change(*args):
            for f in [monthly_f, mingguan_f, harian_f, custom_f]:
                f.pack_forget()
            
            p = self._perf_period_var.get()
            if p == "Bulanan":
                monthly_f.pack(side="left")
            elif p == "Mingguan":
                mingguan_f.pack(side="left")
            elif p == "Harian":
                harian_f.pack(side="left")
            elif p == "Custom":
                custom_f.pack(side="left")
            # For "All Time", do not pack any sub-frames.

        ctk.CTkOptionMenu(config_f, values=["Harian", "Mingguan", "Bulanan", "Custom", "All Time"], variable=self._perf_period_var, 
                          command=_on_period_change, width=120).grid(row=0, column=1, sticky="w", pady=4, padx=4)
        
        # Initialize visibility
        _on_period_change()

        # Results area
        res_f = ctk.CTkFrame(frame, fg_color=BG_DARK, corner_radius=8)
        res_f.pack(fill="both", expand=True, padx=16, pady=12)
        
        self._lbl_perf_period = ctk.CTkLabel(res_f, text="Periode Analisis: --", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY)
        self._lbl_perf_period.pack(pady=(12, 4))

        # Cards container
        cards_f = ctk.CTkFrame(res_f, fg_color="transparent")
        cards_f.pack(fill="x", padx=16, pady=8)
        cards_f.grid_columnconfigure((0,1,2), weight=1, uniform="card")

        def create_card(parent, title, col):
            card = ctk.CTkFrame(parent, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER, corner_radius=8)
            card.grid(row=0, column=col, sticky="nsew", padx=6)
            ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_SECONDARY).pack(pady=(10, 2))
            val_lbl = ctk.CTkLabel(card, text="Rp --", font=(FONT_MONO, 18, "bold"), text_color=TEXT_PRIMARY)
            val_lbl.pack(pady=0)
            cur = get_currency_label(self.cfg)
            sec_text = f"(-- {cur})" if cur != "IDR" else ""
            idr_lbl = ctk.CTkLabel(card, text=sec_text, font=(FONT_MONO, 11), text_color=TEXT_SECONDARY)
            idr_lbl.pack(pady=(0, 10))
            return card, val_lbl, idr_lbl

        self._card_net_f, self._lbl_net_val, self._lbl_net_idr = create_card(cards_f, "NET PROFIT", 0)
        self._card_gross_pf, self._lbl_gprof_val, self._lbl_gprof_idr = create_card(cards_f, "GROSS PROFIT", 1)
        self._card_gross_lf, self._lbl_gloss_val, self._lbl_gloss_idr = create_card(cards_f, "GROSS LOSS", 2)

        # Secondary stats container
        stats_f = ctk.CTkFrame(res_f, fg_color="transparent")
        stats_f.pack(fill="x", padx=16, pady=(8, 16))
        stats_f.grid_columnconfigure(0, weight=1, uniform="stat")
        stats_f.grid_columnconfigure(1, weight=1, uniform="stat")

        # Left column - Trade Counts
        left_f = ctk.CTkFrame(stats_f, fg_color="transparent")
        left_f.grid(row=0, column=0, sticky="nsew", padx=10)
        
        def create_stat_row(parent, label, color):
            row_f = ctk.CTkFrame(parent, fg_color="transparent")
            row_f.pack(fill="x", pady=4)
            ctk.CTkLabel(row_f, text=label, font=(FONT_FAMILY, 13), text_color=TEXT_SECONDARY, width=100, anchor="w").pack(side="left")
            val_lbl = ctk.CTkLabel(row_f, text="--", font=(FONT_MONO, 14, "bold"), text_color=color)
            val_lbl.pack(side="left")
            return val_lbl

        self._lbl_trades_tot = create_stat_row(left_f, "Total Trades:", TEXT_PRIMARY)
        self._lbl_trades_win = create_stat_row(left_f, "Win Trades:", GREEN_BRIGHT)
        self._lbl_trades_loss = create_stat_row(left_f, "Loss Trades:", RED)

        # Right column - Win Rate
        right_f = ctk.CTkFrame(stats_f, fg_color="transparent")
        right_f.grid(row=0, column=1, sticky="nsew", padx=10)
        
        self._lbl_win_rate_large = ctk.CTkLabel(right_f, text="Win Rate: --%", font=(FONT_FAMILY, 24, "bold"), text_color=GREEN_BRIGHT)
        self._lbl_win_rate_large.pack(pady=(0, 8), anchor="w")
        
        self._pb_win_rate = ctk.CTkProgressBar(right_f, progress_color=GREEN_BRIGHT, height=10)
        self._pb_win_rate.set(0)
        self._pb_win_rate.pack(fill="x", pady=4)
        
        self._lbl_win_ratio_txt = ctk.CTkLabel(right_f, text="Win Ratio: --% | Loss Ratio: --%", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY)
        self._lbl_win_ratio_txt.pack(anchor="w")
        
        # Chart container
        self._chart_frame = ctk.CTkFrame(res_f, fg_color=BG_DARK)
        self._chart_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        def _draw_chart(chart_data, period_type):
            for widget in self._chart_frame.winfo_children():
                widget.destroy()
                
            dates = chart_data.get("dates", [])
            if not dates:
                return
                
            # Format X-axis labels
            from datetime import datetime
            x_labels = []
            for d in dates:
                if len(d) == 7:  # YYYY-MM
                    dt = datetime.strptime(d, "%Y-%m")
                    x_labels.append(dt.strftime("%b '%y"))
                else:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    if period_type == "Mingguan":
                        day_map = {0: "Sen", 1: "Sel", 2: "Rab", 3: "Kam", 4: "Jum", 5: "Sab", 6: "Min"}
                        x_labels.append(day_map[dt.weekday()])
                    elif period_type == "Bulanan":
                        x_labels.append(str(dt.day))
                    else:
                        x_labels.append(dt.strftime("%d %b"))
                    
            fig = Figure(figsize=(6, 3), dpi=100, facecolor='#11121a')
            ax = fig.add_subplot(111)
            ax.set_facecolor('#11121a')
            
            x = range(len(dates))
            gross_profits = chart_data.get("gross_profits", [])
            gross_losses = chart_data.get("gross_losses", [])
            net_profits = chart_data.get("net_profits", [])
            
            # Draw Bidirectional Bars
            ax.bar(x, gross_profits, color=GREEN_BRIGHT, width=0.4, label='Gross Profit')
            # Negate gross losses for downward bars
            neg_losses = [-abs(val) for val in gross_losses]
            ax.bar(x, neg_losses, color=RED, width=0.4, label='Gross Loss')
            
            # Draw Cumulative Line
            ax.plot(x, net_profits, color='#f1c40f', marker='o', linewidth=2, markersize=6, label='Net Profit')
            
            # Styling
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_color('#30363d')
            ax.spines['left'].set_color('#30363d')
            ax.tick_params(colors='white', which='both')
            
            import matplotlib.ticker as ticker
            ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6, integer=True))
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda val, pos: x_labels[int(val)] if 0 <= int(val) < len(x_labels) else ''))
            
            ax.tick_params(axis='x', rotation=30)
            for label in ax.get_xticklabels():
                label.set_horizontalalignment('right')
                label.set_fontsize(9)
                
            ax.grid(axis='y', linestyle=':', color='#3a3c4a', alpha=0.7)
            
            # Horizontal zero line
            ax.axhline(0, color='#30363d', linewidth=1)
            
            fig.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

        def _on_filter():
            period = self._perf_period_var.get()
            from datetime import datetime, timedelta, timezone
            import calendar
            
            # 1. Define the Broker's Server Timezone (GMT+3 for HF Markets)
            server_tz = timezone(timedelta(hours=3))
            
            if period == "Bulanan":
                m_idx = months.index(self._perf_month_var.get()) + 1
                y = int(self._perf_year_var.get())
                start_dt = datetime(y, m_idx, 1, 0, 0, 0, tzinfo=server_tz)
                last_day = calendar.monthrange(y, m_idx)[1]
                end_dt = datetime(y, m_idx, last_day, 23, 59, 59, tzinfo=server_tz)
                period_str = f"Periode Analisis: {start_dt.strftime('%d %b %Y')} s/d {end_dt.strftime('%d %b %Y')}"
            elif period == "Mingguan":
                if not DateEntry: return
                selected = self.cal_weekly.get_date()
                monday = selected - timedelta(days=selected.weekday())
                friday = monday + timedelta(days=4)
                start_dt = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=server_tz)
                end_dt = datetime(friday.year, friday.month, friday.day, 23, 59, 59, tzinfo=server_tz)
                
                day_map = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
                period_str = f"Periode Analisis: {day_map[monday.weekday()]}, {start_dt.strftime('%Y-%m-%d')} s/d {day_map[friday.weekday()]}, {end_dt.strftime('%Y-%m-%d')}"
            elif period == "Harian":
                if not DateEntry: return
                selected = self.cal_daily.get_date()
                start_dt = datetime(selected.year, selected.month, selected.day, 0, 0, 0, tzinfo=server_tz)
                end_dt = datetime(selected.year, selected.month, selected.day, 23, 59, 59, tzinfo=server_tz)
                period_str = f"Periode Analisis: {start_dt.strftime('%d %b %Y')} s/d {end_dt.strftime('%d %b %Y')}"
            elif period == "All Time":
                start_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=server_tz)
                now = datetime.now()
                # Create timezone aware current time using server_tz
                end_dt = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second, tzinfo=server_tz)
                period_str = "Periode Analisis: All-Time (Sejak Awal Akun)"
            else:
                if not DateEntry: return
                sel_start = self.cal_start.get_date()
                sel_end = self.cal_end.get_date()
                start_dt = datetime(sel_start.year, sel_start.month, sel_start.day, 0, 0, 0, tzinfo=server_tz)
                end_dt = datetime(sel_end.year, sel_end.month, sel_end.day, 23, 59, 59, tzinfo=server_tz)
                period_str = f"Periode Analisis: {start_dt.strftime('%d %b %Y')} s/d {end_dt.strftime('%d %b %Y')}"
            
            # Update the period label safely on main thread
            self._lbl_perf_period.configure(text=period_str, text_color=TEXT_SECONDARY)
            
            def _fetch_and_update():
                try:
                    is_all = (period == "All Time")
                    res = self.mt5.fetch_historical_performance(start_dt, end_dt, is_all_time=is_all)
                    
                    def _update_gui():
                        self._filter_btn.configure(state="normal", text="Filter")
                        
                        if "error" in res:
                            self._lbl_perf_period.configure(text=res["error"], text_color=RED)
                            return
                            
                        def format_card(card_f, val_lbl, idr_lbl, val_acct, default_color, dynamic=False):
                            color = default_color
                            if dynamic:
                                color = GREEN_BRIGHT if val_acct >= 0 else RED
                            
                            card_f.configure(border_color=color)
                            primary = format_perf_card_primary(val_acct, self.cfg)
                            secondary = format_perf_card_secondary(val_acct, self.cfg)
                            val_lbl.configure(text=primary, text_color=color)
                            idr_lbl.configure(text=secondary, text_color=color)
            
                        # Update Cards
                        format_card(self._card_net_f, self._lbl_net_val, self._lbl_net_idr, res['net_profit_usc'], GREEN_BRIGHT, dynamic=True)
                        format_card(self._card_gross_pf, self._lbl_gprof_val, self._lbl_gprof_idr, res['total_profit_usc'], GREEN_BRIGHT)
                        format_card(self._card_gross_lf, self._lbl_gloss_val, self._lbl_gloss_idr, res['total_loss_usc'], RED)
            
                        # Update Stats
                        self._lbl_trades_tot.configure(text=str(res['total_trades']))
                        self._lbl_trades_win.configure(text=str(res['win_trades']))
                        self._lbl_trades_loss.configure(text=str(res['loss_trades']))
            
                        # Update Win Rate
                        wr = res['win_rate_pct']
                        lr = max(0, 100 - wr) if res['total_trades'] > 0 else 0
                        self._lbl_win_rate_large.configure(text=f"Win Rate: {wr:.1f}%")
                        self._pb_win_rate.set(wr / 100.0)
                        self._lbl_win_ratio_txt.configure(text=f"Win Ratio: {wr:.1f}% | Loss Ratio: {lr:.1f}%")
                        
                        if "chart_data" in res:
                            _draw_chart(res["chart_data"], period)
                    
                    self.after(0, _update_gui)
                except Exception as e:
                    def on_err():
                        self._filter_btn.configure(state="normal", text="Filter")
                        import tkinter.messagebox as mb
                        mb.showerror("History Error", f"An unexpected error occurred fetching history:\n{e}")
                    self.after(0, on_err)
                
            import threading
            self._filter_btn.configure(state="disabled", text="Loading...")
            threading.Thread(target=_fetch_and_update, daemon=True).start()

        self._filter_btn = ctk.CTkButton(config_f, text="Filter", command=_on_filter, width=80)
        self._filter_btn.grid(row=0, column=3, padx=16)

        # ── PNL CALENDAR SECTION ─────────────────────────────────────
        cal_section = ctk.CTkFrame(frame, fg_color="transparent")
        cal_section.pack(fill="x", expand=True, padx=16, pady=(10, 20))
        
        ctk.CTkLabel(cal_section, text="📅 KALENDER PNL BULANAN", font=(FONT_FAMILY, 14, "bold"), text_color=GOLD, anchor="w").pack(fill="x", pady=(0, 10))
        
        self._cal_container = ctk.CTkFrame(cal_section, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        self._cal_container.pack(fill="both", expand=True)
        
        now = datetime.now()
        self._calendar_current_year = now.year
        self._calendar_current_month = now.month
        
        # We need the class method for rendering, it will be added next.
        # But we can call it here.
        # Ensure it exists before running. Wait, we will add it right after this method.
        # Wait, tkinter UI usually needs `self._render_calendar()` here but let's just use `self.after(100, self._render_calendar)` to be safe if it's not defined yet, but Python evaluates methods at runtime so `self._render_calendar()` is fine.
        self.after(50, self._render_calendar)

    def _change_calendar_month(self, delta):
        self._calendar_current_month += delta
        if self._calendar_current_month > 12:
            self._calendar_current_month = 1
            self._calendar_current_year += 1
        elif self._calendar_current_month < 1:
            self._calendar_current_month = 12
            self._calendar_current_year -= 1
        self._render_calendar()

    def _render_calendar(self):
        for widget in self._cal_container.winfo_children():
            widget.destroy()
            
        import calendar
        
        year = self._calendar_current_year
        month = self._calendar_current_month
        
        header_f = ctk.CTkFrame(self._cal_container, fg_color="transparent")
        header_f.pack(fill="x", pady=(10, 10))
        
        btn_prev = ctk.CTkButton(header_f, text="◀", width=40, command=lambda: self._change_calendar_month(-1), fg_color=CARD_BORDER, hover_color="#3a3f45")
        btn_prev.pack(side="left", padx=16)
        
        month_name = calendar.month_name[month]
        title_lbl = ctk.CTkLabel(header_f, text=f"{month_name} {year}", font=(FONT_FAMILY, 15, "bold"), text_color=TEXT_PRIMARY)
        title_lbl.pack(side="left", expand=True)
        
        btn_next = ctk.CTkButton(header_f, text="▶", width=40, command=lambda: self._change_calendar_month(1), fg_color=CARD_BORDER, hover_color="#3a3f45")
        btn_next.pack(side="right", padx=16)
        
        grid_f = ctk.CTkFrame(self._cal_container, fg_color="transparent")
        grid_f.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        for i in range(7):
            grid_f.grid_columnconfigure(i, weight=1, uniform="cal")
            
        days_label = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, d in enumerate(days_label):
            ctk.CTkLabel(grid_f, text=d, font=(FONT_FAMILY, 12, "bold"), text_color=TEXT_SECONDARY).grid(row=0, column=i, pady=(0, 5))
            
        daily_pnl = self._fetch_calendar_data(year, month)
        start_weekday, num_days = calendar.monthrange(year, month)
        
        row = 1
        col = start_weekday
        
        sum_profit = 0.0
        sum_loss = 0.0
        
        for day in range(1, num_days + 1):
            pnl_val = daily_pnl.get(day, 0.0)
            
            if pnl_val > 0:
                bg_col = "#152a1b" # Dark green
                br_col = GREEN
                txt_col = GREEN_BRIGHT
                sum_profit += pnl_val
            elif pnl_val < 0:
                bg_col = "#2d1617" # Dark red
                br_col = RED_DIM
                txt_col = RED
                sum_loss += abs(pnl_val)
            else:
                bg_col = "#1e2329" # Gray
                br_col = CARD_BORDER
                txt_col = TEXT_SECONDARY
                
            cell_f = ctk.CTkFrame(grid_f, fg_color=bg_col, border_width=1, border_color=br_col, corner_radius=6, height=65)
            cell_f.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            cell_f.grid_propagate(False)
            cell_f.grid_rowconfigure(1, weight=1)
            cell_f.grid_columnconfigure(0, weight=1)
            
            ctk.CTkLabel(cell_f, text=str(day), font=(FONT_FAMILY, 10, "bold"), text_color=txt_col).grid(row=0, column=0, sticky="nw", padx=4, pady=2)
            
            val_f = ctk.CTkFrame(cell_f, fg_color="transparent")
            val_f.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
            
            if pnl_val != 0:
                primary_txt = format_perf_card_primary(pnl_val, self.cfg)
                ctk.CTkLabel(val_f, text=primary_txt, font=(FONT_MONO, 11, "bold"), text_color=txt_col).pack(pady=0)
                
                sec_txt = format_perf_card_secondary(pnl_val, self.cfg)
                if sec_txt:
                    ctk.CTkLabel(val_f, text=sec_txt, font=(FONT_MONO, 9), text_color=txt_col).pack(pady=0)
            else:
                ctk.CTkLabel(val_f, text="-", font=(FONT_MONO, 11, "bold"), text_color=txt_col).pack(pady=4)
            
            col += 1
            if col > 6:
                col = 0
                row += 1
                
        # Phase 5: Summary Section
        self._cal_summary_f = ctk.CTkFrame(self._cal_container, fg_color="transparent")
        self._cal_summary_f.pack(fill="x", padx=16, pady=(10, 16))
        self._cal_summary_f.grid_columnconfigure((0, 1, 2), weight=1, uniform="sum_col")
        
        sum_net = sum_profit - sum_loss
        
        def create_sum_card(parent, title, val, col_idx, base_color):
            card = ctk.CTkFrame(parent, fg_color=CARD_BG, border_width=1, border_color=base_color, corner_radius=8)
            card.grid(row=0, column=col_idx, sticky="nsew", padx=6)
            ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_SECONDARY).pack(pady=(8, 2))
            
            primary_txt = format_perf_card_primary(val, self.cfg)
            ctk.CTkLabel(card, text=primary_txt, font=(FONT_MONO, 15, "bold"), text_color=base_color).pack(pady=0)
            
            sec_txt = format_perf_card_secondary(val, self.cfg)
            if sec_txt:
                ctk.CTkLabel(card, text=sec_txt, font=(FONT_MONO, 10), text_color=base_color).pack(pady=(0, 8))
            else:
                ctk.CTkLabel(card, text="", font=(FONT_MONO, 10)).pack(pady=(0, 8))
                
        create_sum_card(self._cal_summary_f, "MONTHLY PROFIT", sum_profit, 0, GREEN_BRIGHT)
        create_sum_card(self._cal_summary_f, "MONTHLY LOSS", sum_loss, 1, RED)
        create_sum_card(self._cal_summary_f, "MONTHLY NET PNL", sum_net, 2, GREEN_BRIGHT if sum_net >= 0 else RED)

    # ──────────────────────────────────────────────────────────
    # 2x2 ACTION GRID
    # ──────────────────────────────────────────────────────────

    def _build_action_grid(self, parent):
        import tkinter as tk
        main_grid = ctk.CTkFrame(parent, fg_color="transparent")
        main_grid.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=12, pady=(4, 10))
        
        main_grid.grid_columnconfigure(0, weight=1, uniform="action_col")
        main_grid.grid_columnconfigure(1, weight=1, uniform="action_col")
        main_grid.grid_rowconfigure(0, weight=0)
        main_grid.grid_rowconfigure(1, weight=0)

        # --- BOX 1: MANUAL ORDER MODIFIER ---
        box1 = ctk.CTkScrollableFrame(main_grid, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER, height=220)
        box1.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        
        b1_hdr = ctk.CTkLabel(box1, text="MANUAL ORDER MODIFIER", font=(FONT_FAMILY, 13, "bold"), text_color=GOLD, anchor="w")
        b1_hdr.pack(fill="x", padx=12, pady=(8, 4))
        
        b1_inner = ctk.CTkFrame(box1, fg_color="transparent")
        b1_inner.pack(fill="x", padx=12, pady=(0, 8))
        b1_inner.grid_columnconfigure(0, weight=0)
        b1_inner.grid_columnconfigure(1, weight=0)
        b1_inner.grid_columnconfigure(2, weight=0)
        b1_inner.grid_columnconfigure(3, weight=1)
        
        # Row 0: Mode Selection
        self._tp_mode_var = ctk.StringVar(value="TP ALL")
        self._seg_tp_mode = ctk.CTkSegmentedButton(b1_inner, values=["TP ALL", "CUSTOM"], variable=self._tp_mode_var, command=self._on_tp_mode_change)
        self._seg_tp_mode.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        
        # Row 1: SL and TP
        ctk.CTkLabel(b1_inner, text="SL:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=1, column=0, sticky="w", padx=(0, 4), pady=5)
        self._var_sl = tk.StringVar()
        self._entry_sl = ctk.CTkEntry(b1_inner, textvariable=self._var_sl, height=35, width=80, font=(FONT_MONO, 12), placeholder_text="0.00")
        self._entry_sl.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=5)
        
        self._lbl_tp_all = ctk.CTkLabel(b1_inner, text="TP:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY)
        self._lbl_tp_all.grid(row=1, column=2, sticky="w", padx=(0, 4), pady=5)
        self._var_tp = tk.StringVar()
        self._entry_tp = ctk.CTkEntry(b1_inner, textvariable=self._var_tp, height=35, width=80, font=(FONT_MONO, 12), placeholder_text="0.00")
        self._entry_tp.grid(row=1, column=3, sticky="w", pady=5)
        
        # Row 2: Estimations
        self._lbl_sl_est = ctk.CTkLabel(b1_inner, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY)
        # self._lbl_sl_est.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=(0, 5))
        self._lbl_tp_est = ctk.CTkLabel(b1_inner, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY)
        # self._lbl_tp_est.grid(row=2, column=3, sticky="w", pady=(0, 5))
        
        # Row 3: CUSTOM mode
        self._frame_tp_custom = ctk.CTkFrame(b1_inner, fg_color="transparent")
        
        def _make_tp_row(parent, label, var_name, default_pct, entry_attr):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=2)
            ctk.CTkLabel(f, text=label, font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY, width=35).pack(side="left")
            entry = ctk.CTkEntry(f, height=28, width=70, font=(FONT_MONO, 12), placeholder_text="0.00")
            entry.pack(side="left", padx=5)
            setattr(self, entry_attr, entry)
            var = ctk.StringVar(value=default_pct)
            setattr(self, var_name, var)
            opt = ctk.CTkOptionMenu(f, values=["0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%", "100%"], variable=var, width=70, height=28, command=self._recalc_runner)
            opt.pack(side="left", padx=5)
            
        _make_tp_row(self._frame_tp_custom, "TP1:", "_var_vol1", "30%", "_entry_tp1")
        _make_tp_row(self._frame_tp_custom, "TP2:", "_var_vol2", "30%", "_entry_tp2")
        _make_tp_row(self._frame_tp_custom, "TP3:", "_var_vol3", "0%", "_entry_tp3")
        
        f_runner = ctk.CTkFrame(self._frame_tp_custom, fg_color="transparent")
        f_runner.pack(fill="x", pady=2)
        ctk.CTkLabel(f_runner, text="OPEN:", font=(FONT_FAMILY, 12, "bold"), text_color=GOLD, width=35).pack(side="left")
        self._lbl_runner_pct = ctk.CTkLabel(f_runner, text="40% (Runner)", font=(FONT_FAMILY, 12), text_color=TEXT_PRIMARY)
        self._lbl_runner_pct.pack(side="left", padx=5)
        
        # Hide custom frame initially
        self._frame_tp_custom.grid_remove()
        
        # Row 4: Apply SL/TP
        self._btn_apply_sltp = ctk.CTkButton(b1_inner, text="Apply SL/TP to All", height=35, font=(FONT_FAMILY, 11, "bold"),
                                             fg_color=BLUE, hover_color="#79c0ff", text_color=BG_DARK, command=self._on_apply_sltp)
        self._btn_apply_sltp.grid(row=4, column=0, columnspan=4, sticky="ew", pady=5)
        
        # Row 5: BE Offset + Smart BE
        ctk.CTkLabel(b1_inner, text="BE Offset:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=5, column=0, sticky="w", padx=(0, 4), pady=5)
        self._entry_be_offset = ctk.CTkEntry(b1_inner, height=35, width=60, font=(FONT_MONO, 12))
        self._entry_be_offset.insert(0, str(self.cfg.get("be_offset_pips", 0.5)))
        self._entry_be_offset.grid(row=5, column=1, sticky="w", padx=(0, 4), pady=5)
        ctk.CTkLabel(b1_inner, text="pips", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY).grid(row=5, column=2, sticky="w", padx=(0, 4), pady=5)
        self._btn_smart_be = ctk.CTkButton(b1_inner, text="\u26a1 Smart BE", height=35, font=(FONT_FAMILY, 11, "bold"),
                                           fg_color=GREEN, hover_color=GREEN_BRIGHT, text_color="#ffffff", command=self._on_smart_be)
        self._btn_smart_be.grid(row=5, column=3, sticky="ew", pady=5)
        
        # Row 6: Trailing Stop + Start Trailing
        ctk.CTkLabel(b1_inner, text="Trailing Stop:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=6, column=0, sticky="w", padx=(0, 4), pady=5)
        self._entry_trail = ctk.CTkEntry(b1_inner, height=35, width=60, font=(FONT_MONO, 12))
        self._entry_trail.insert(0, str(self.cfg.get("trailing_stop_pips", 10.0)))
        self._entry_trail.grid(row=6, column=1, sticky="w", padx=(0, 4), pady=5)
        ctk.CTkLabel(b1_inner, text="pips", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY).grid(row=6, column=2, sticky="w", padx=(0, 4), pady=5)
        self._trail_var = ctk.BooleanVar(value=False)
        self._btn_trail = ctk.CTkButton(b1_inner, text="Start Trailing", height=35, font=(FONT_FAMILY, 11, "bold"),
                                        fg_color=GOLD_DIM, hover_color=GOLD, text_color=BG_DARK, command=self._on_toggle_trailing)
        self._btn_trail.grid(row=6, column=3, sticky="ew", pady=5)
        
        self._var_sl.trace_add("write", self._update_sl_est)
        self._var_tp.trace_add("write", self._update_tp_est)

        # --- BOX 2: SELECTIVE LIQUIDATOR ---
        box2 = ctk.CTkFrame(main_grid, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        box2.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        
        b2_hdr = ctk.CTkLabel(box2, text="SELECTIVE LIQUIDATOR", font=(FONT_FAMILY, 13, "bold"), text_color=GOLD, anchor="w")
        b2_hdr.pack(fill="x", padx=12, pady=(8, 4))
        
        b2_inner = ctk.CTkFrame(box2, fg_color="transparent")
        b2_inner.pack(fill="x", padx=12, pady=4)
        b2_inner.grid_columnconfigure(0, weight=0)
        b2_inner.grid_columnconfigure(1, weight=1)
        b2_inner.grid_columnconfigure(2, weight=0)
        b2_inner.grid_columnconfigure(3, weight=1)
        
        ctk.CTkLabel(b2_inner, text="Close Qty:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="e", padx=(0, 6), pady=5)
        
        def _update_close_qty_display(mode: str):
            if mode == "All":
                self._entry_close_qty_custom.grid_remove()
                self._label_close_qty_all.grid(row=0, column=2, columnspan=2, sticky="ew", pady=5)
            else:
                self._label_close_qty_all.grid_remove()
                self._entry_close_qty_custom.grid(row=0, column=2, columnspan=2, sticky="ew", pady=5)
                
        def on_qty_mode_change(choice):
            _update_close_qty_display(choice)
        
        self._opt_close_qty_mode = ctk.CTkOptionMenu(b2_inner, values=["All", "Custom"], height=35, font=(FONT_FAMILY, 11),
                                                 fg_color=CARD_BORDER, button_color=GOLD_DIM, button_hover_color=GOLD, command=on_qty_mode_change)
        self._opt_close_qty_mode.set(self.cfg.get("selective_close_qty_mode", "All"))
        self._opt_close_qty_mode.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=5)
        
        vcmd = (b2_inner.register(lambda P: P.isdigit() or P == ""), '%P')
        self._entry_close_qty_custom = ctk.CTkEntry(b2_inner, height=35, font=(FONT_MONO, 14, "bold"),
                                             text_color=TEXT_PRIMARY,
                                             placeholder_text="Qty", validate="key", validatecommand=vcmd)
                                             
        self._label_close_qty_all = ctk.CTkLabel(b2_inner, text="Close All Layers", height=35, 
                                                 font=(FONT_MONO, 14, "bold"), text_color=GOLD, 
                                                 fg_color=CARD_BORDER, corner_radius=6)
        
        saved_qty_mode = self.cfg.get("selective_close_qty_mode", "All")
        if saved_qty_mode == "Custom":
            saved_qty = self.cfg.get("selective_close_qty", 1)
            self._entry_close_qty_custom.insert(0, str(saved_qty))
            
        _update_close_qty_display(saved_qty_mode)
        
        ctk.CTkLabel(b2_inner, text="Dir:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=1, column=0, sticky="e", padx=(0, 6), pady=5)
        self._opt_close_dir = ctk.CTkOptionMenu(b2_inner, values=["ALL", "BUY", "SELL"], height=35, font=(FONT_FAMILY, 11),
                                                fg_color=CARD_BORDER, button_color=GOLD_DIM, button_hover_color=GOLD)
        self._opt_close_dir.set(self.cfg.get("selective_close_direction", "ALL"))
        self._opt_close_dir.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=5)
        
        ctk.CTkLabel(b2_inner, text="Sort:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).grid(row=1, column=2, sticky="e", padx=(0, 6), pady=5)
        
        def on_sort_change(choice):
            if choice == "All":
                self._opt_close_qty_mode.set("All")
                on_qty_mode_change("All")
                self._opt_close_qty_mode.configure(state="disabled")
            else:
                self._opt_close_qty_mode.configure(state="normal")
                
        self._opt_close_sort = ctk.CTkOptionMenu(b2_inner, values=["All", "Most Loss", "Most Profit", "Top Price", "Bottom Price"],
                                                 height=35, font=(FONT_FAMILY, 11), fg_color=CARD_BORDER, button_color=GOLD_DIM, button_hover_color=GOLD, command=on_sort_change)
        self._opt_close_sort.set(self.cfg.get("selective_close_sort", "Most Loss"))
        self._opt_close_sort.grid(row=1, column=3, sticky="ew", pady=5)
        
        # Initialize UI state based on current value
        on_sort_change(self._opt_close_sort.get())
        
        # Row 2: Execute Close
        self._btn_exec_close = ctk.CTkButton(b2_inner, text="EXECUTE CLOSE", height=35, font=(FONT_FAMILY, 12, "bold"),
                                             fg_color=RED_DIM, hover_color=RED, text_color="#ffffff", command=self._on_selective_close)
        self._btn_exec_close.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(5, 0))

        # --- BOX 3: GOAL-BASED AUTOMATION ---
        box3 = ctk.CTkScrollableFrame(main_grid, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        box3.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(4, 0))
        
        b3_hdr = ctk.CTkLabel(box3, text="GOAL-BASED AUTOMATION", font=(FONT_FAMILY, 13, "bold"), text_color=GOLD, anchor="w")
        b3_hdr.pack(fill="x", padx=12, pady=(8, 4))
        
        b3_inner = ctk.CTkFrame(box3, fg_color="transparent")
        b3_inner.pack(fill="x", padx=12, pady=(0, 4))
        b3_inner.grid_columnconfigure(0, weight=0)
        b3_inner.grid_columnconfigure(1, weight=1)
        b3_inner.grid_columnconfigure(2, weight=0)
        b3_inner.grid_columnconfigure(3, weight=1)
        
        # Row 0: Target Profit Inputs
        cur = get_currency_label(self.cfg)
        self._lbl_target_cur = ctk.CTkLabel(b3_inner, text=f"Target {cur}:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY)
        self._lbl_target_cur.grid(row=0, column=0, sticky="w", padx=(0, 4), pady=5)
        self._var_tp_usc = tk.StringVar(value=str(self.cfg.get("target_profit_native", 0)))
        self._entry_tp_usc = ctk.CTkEntry(b3_inner, textvariable=self._var_tp_usc, height=35, width=80, font=(FONT_MONO, 12))
        self._entry_tp_usc.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=5)
        self._lbl_target_idr_label = ctk.CTkLabel(b3_inner, text="IDR:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY)
        self._lbl_target_idr_label.grid(row=0, column=2, sticky="w", padx=(0, 4), pady=5)
        self._var_tp_idr = tk.StringVar(value=str(self.cfg.get("target_profit_idr", 0)))
        self._entry_tp_idr = ctk.CTkEntry(b3_inner, textvariable=self._var_tp_idr, height=35, width=80, font=(FONT_MONO, 12))
        self._entry_tp_idr.grid(row=0, column=3, sticky="w", pady=5)
        
        self._syncing_tp = False
        self._var_tp_usc.trace_add("write", self._sync_tp_usc)
        self._var_tp_idr.trace_add("write", self._sync_tp_idr)
        
        # Row 1: Target Profit Switch
        self._tp_armed_var = ctk.BooleanVar(value=self.cfg.get("target_profit_armed", False))
        self._switch_arm_tp = ctk.CTkSwitch(b3_inner, text="Aktifkan Target Profit", variable=self._tp_armed_var,
                                            font=(FONT_FAMILY, 12), switch_height=18, switch_width=36, progress_color=GREEN_BRIGHT, command=self._on_arm_target_profit_switch)
        self._switch_arm_tp.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        self._lbl_tp_status = ctk.CTkLabel(b3_inner, text="STATUS: TIDAK AKTIF", font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_SECONDARY)
        self._lbl_tp_status.grid(row=1, column=2, columnspan=2, sticky="e", pady=5)
        
        # Row 2: Target Profit Progress bar
        b3_prog = ctk.CTkFrame(box3, fg_color="transparent")
        b3_prog.pack(fill="x", padx=12, pady=(0, 10))
        self._tp_canvas = ctk.CTkCanvas(b3_prog, height=14, bg=CARD_BG, highlightthickness=1, highlightbackground=CARD_BORDER)
        self._tp_canvas.bind("<Configure>", lambda e: self._draw_progress_bar(self._tp_canvas, 0, GREEN_BRIGHT))
        self._lbl_tp_progress = ctk.CTkLabel(b3_prog, text="0.0% Menuju Target", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY)
        self._lbl_tp_progress.pack(side="right")
        self._tp_canvas.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # Separator
        ctk.CTkFrame(box3, height=1, fg_color=CARD_BORDER).pack(fill="x", padx=12, pady=5)
        
        b3_inner2 = ctk.CTkFrame(box3, fg_color="transparent")
        b3_inner2.pack(fill="x", padx=12, pady=(4, 4))
        b3_inner2.grid_columnconfigure(0, weight=0)
        b3_inner2.grid_columnconfigure(1, weight=1)
        b3_inner2.grid_columnconfigure(2, weight=0)
        b3_inner2.grid_columnconfigure(3, weight=1)
        
        # Row 0: Target Loss Inputs
        self._lbl_tl_cur = ctk.CTkLabel(b3_inner2, text=f"Loss {cur}:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY)
        self._lbl_tl_cur.grid(row=0, column=0, sticky="w", padx=(0, 4), pady=5)
        self._var_tl_usc = tk.StringVar(value=str(self.cfg.get("target_loss_native", 0)))
        self._entry_tl_usc = ctk.CTkEntry(b3_inner2, textvariable=self._var_tl_usc, height=35, width=80, font=(FONT_MONO, 12))
        self._entry_tl_usc.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=5)
        self._lbl_tl_idr_label = ctk.CTkLabel(b3_inner2, text="IDR:", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY)
        self._lbl_tl_idr_label.grid(row=0, column=2, sticky="w", padx=(0, 4), pady=5)
        self._var_tl_idr = tk.StringVar(value=str(self.cfg.get("target_loss_idr", 0)))
        self._entry_tl_idr = ctk.CTkEntry(b3_inner2, textvariable=self._var_tl_idr, height=35, width=80, font=(FONT_MONO, 12))
        self._entry_tl_idr.grid(row=0, column=3, sticky="w", pady=5)
        
        self._syncing_tl = False
        self._var_tl_usc.trace_add("write", self._sync_tl_usc)
        self._var_tl_idr.trace_add("write", self._sync_tl_idr)
        
        # Row 1: Target Loss Switch
        self._tl_armed_var = ctk.BooleanVar(value=self.cfg.get("target_loss_armed", False))
        self._switch_arm_tl = ctk.CTkSwitch(b3_inner2, text="Aktifkan Target Loss", variable=self._tl_armed_var,
                                            font=(FONT_FAMILY, 12), switch_height=18, switch_width=36, progress_color=RED, command=self._on_arm_target_loss_switch)
        self._switch_arm_tl.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        self._lbl_tl_status = ctk.CTkLabel(b3_inner2, text="STATUS: TIDAK AKTIF", font=(FONT_FAMILY, 11, "bold"), text_color=TEXT_SECONDARY)
        self._lbl_tl_status.grid(row=1, column=2, columnspan=2, sticky="e", pady=5)
        
        # Row 2: Target Loss Progress bar
        b3_tl_prog = ctk.CTkFrame(box3, fg_color="transparent")
        b3_tl_prog.pack(fill="x", padx=12, pady=(0, 10))
        self._tl_canvas = ctk.CTkCanvas(b3_tl_prog, height=14, bg=CARD_BG, highlightthickness=1, highlightbackground=CARD_BORDER)
        self._tl_canvas.bind("<Configure>", lambda e: self._draw_progress_bar(self._tl_canvas, 0, RED))
        self._lbl_tl_progress = ctk.CTkLabel(b3_tl_prog, text="0.0% (Drawdown)", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY)
        self._lbl_tl_progress.pack(side="right")
        self._tl_canvas.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # --- BOX 4: EMERGENCY & SAFETY CONSOLE ---
        box4 = ctk.CTkFrame(main_grid, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=CARD_BORDER)
        box4.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(4, 0))
        
        b4_hdr = ctk.CTkLabel(box4, text="EMERGENCY & SAFETY CONSOLE", font=(FONT_FAMILY, 13, "bold"), text_color=GOLD, anchor="w")
        b4_hdr.pack(fill="x", padx=12, pady=(8, 4))
        
        self._btn_emergency = ctk.CTkButton(box4, text="\U0001f6a8 EMERGENCY CLOSE ALL", height=35, font=(FONT_FAMILY, 13, "bold"),
                                            fg_color=RED, hover_color="#ff6b6b", text_color="#ffffff", corner_radius=6, command=self._on_emergency_close)
        self._btn_emergency.pack(fill="x", padx=12, pady=5)
        
        self._btn_hedge = ctk.CTkButton(box4, text="\U0001f512 HEDGE LOCK", height=35, font=(FONT_FAMILY, 12, "bold"),
                                        fg_color=ORANGE, hover_color=YELLOW, text_color=BG_DARK, corner_radius=6, command=self._on_hedge)
        self._btn_hedge.pack(fill="x", padx=12, pady=5)
        
        b4_status = ctk.CTkFrame(box4, fg_color="transparent")
        b4_status.pack(fill="x", padx=12, pady=(10, 8))
        ctk.CTkLabel(b4_status, text="Equity Guard: ON", font=(FONT_FAMILY, 12, "bold"), text_color=GREEN_BRIGHT).pack(side="left")
        ctk.CTkLabel(b4_status, text="  |  ", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).pack(side="left")
        ctk.CTkLabel(b4_status, text=f"Threshold: {self.cfg.get('equity_protection_pct', 30)}%", font=(FONT_FAMILY, 12), text_color=TEXT_SECONDARY).pack(side="left")
    # ══════════════════════════════════════════════════════════
    # UI REFRESH (called every 200ms via self.after)
    # ══════════════════════════════════════════════════════════

    def _refresh_ui(self):
        try:
            self._do_refresh()
        except Exception as exc:
            print(f"[Dashboard] Refresh error: {exc}")
        self.after(200, self._refresh_ui)

    def _redraw_daily_goal_bar(self, event=None):
        canvas = getattr(self, "_pb_daily_goal", None)
        if not canvas: return
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1: return
        
        canvas.delete("all")
        # Base background track (dim grey)
        canvas.create_rectangle(0, 0, w, h, fill="#30363d", outline="")
        
        goal = getattr(self, "_last_goal_current_native", 0.0)
        tgt = getattr(self, "_last_tgt_native", 0.0)
        ls = getattr(self, "_last_ls_native", 0.0)
        
        mid_x = w / 2.0
        
        if goal >= 0:
            ratio = min(1.0, goal / tgt) if tgt > 0 else 0.0
            bar_w = ratio * mid_x
            if bar_w > 0:
                canvas.create_rectangle(mid_x, 0, mid_x + bar_w, h, fill=GREEN_BRIGHT, outline="")
        else:
            ratio = min(1.0, abs(goal) / ls) if ls > 0 else 0.0
            bar_w = ratio * mid_x
            if bar_w > 0:
                canvas.create_rectangle(mid_x - bar_w, 0, mid_x, h, fill=RED, outline="")
                
        # Center line marker
        canvas.create_line(mid_x, 0, mid_x, h, fill="#8b949e", width=2)

    def _do_refresh(self):
        s = self.mt5.get_state()
        rate = self.cfg.get("usd_idr_rate", 16250)

        # Sync account currency dropdown if auto-detected
        cfg_curr = self.cfg.get("account_currency", "USC")
        if getattr(self, "_opt_acct_currency", None):
            if self._opt_acct_currency.get() != cfg_curr:
                self._opt_acct_currency.set(cfg_curr)
                # Also update all dynamic labels that depend on currency
                self._on_acct_currency_change(cfg_curr)

        # ── Panel A ──
        connected = s.get("connected", False)
        if connected:
            self._heartbeat_canvas.itemconfig(self._hb_dot, fill=GREEN_BRIGHT)
            active_sym = self.mt5.get_active_symbol() if hasattr(self.mt5, 'get_active_symbol') else ""
            conn_text = f"Connected ({active_sym})" if active_sym else "Connected"
            self._lbl_conn.configure(text=conn_text, text_color=GREEN_BRIGHT)
        else:
            self._heartbeat_canvas.itemconfig(self._hb_dot, fill=RED)
            self._lbl_conn.configure(text="Disconnected", text_color=RED)
            # beep on disconnect transition
            if self._prev_connected and not connected:
                try:
                    winsound.Beep(800, 300)
                except Exception:
                    pass
        self._prev_connected = connected

        spread = s.get("spread_pips", 0.0)
        spread_limit = self.cfg.get("spread_limit_pips", 5.0)
        spread_color = RED if spread > spread_limit else TEXT_PRIMARY
        self._lbl_spread.configure(text=f"{spread} pips", text_color=spread_color)

        self._lbl_idr.configure(text=f"{rate:,.0f}")

        # ── Panel B ──
        pnl = s.get("floating_pnl_usc", 0)
        bal = s.get("balance", 0.0)
        
        pnl_text = format_amount(pnl, self.cfg)
        pnl_color = GREEN_BRIGHT if pnl >= 0 else RED
        self._lbl_pnl.configure(text=pnl_text, text_color=pnl_color)
        
        if bal > 0:
            pct = (pnl / bal) * 100
            self._lbl_pnl_pct.configure(text=f"{pct:+.2f}% dari modal", text_color=pnl_color)
            if not self._lbl_pnl_pct.winfo_ismapped():
                self._lbl_pnl_pct.pack(anchor="w", pady=(2, 0))
        else:
            if self._lbl_pnl_pct.winfo_ismapped():
                self._lbl_pnl_pct.pack_forget()

        mv = self._monitor_vals
        mv["Layers:"].configure(text=str(s.get("total_layers", 0)))
        mv["Total Lots:"].configure(text=f'{s.get("total_lots", 0):.2f}  '
                                          f'(B:{s.get("buy_lots", 0):.2f}  S:{s.get("sell_lots", 0):.2f})')
        mv["Avg Price:"].configure(text=f'{s.get("avg_price_combined", 0):.2f}')

        dist = s.get("avg_distance_pips", 0.0)
        dist_sign = "+" if dist >= 0 else ""
        mv["Avg Distance:"].configure(text=f"{dist_sign}{dist} pips",
                                       text_color=GREEN_BRIGHT if dist >= 0 else RED)
        mv["Layer Range:"].configure(text=f'{s.get("layer_range_pips", 0.0)} pips')

        # ── Panel C ──
        rv = self._risk_vals
        
        balance_val = s.get("balance", 0)
        rv["Balance:"].configure(text=format_with_idr(balance_val, self.cfg))
        
        equity_val = s.get("equity", 0)
        
        if balance_val > 0 and equity_val <= 0.7 * balance_val:
            eq_color = RED
            eq_font = (FONT_MONO, 13, "bold")
        else:
            eq_color = TEXT_PRIMARY
            eq_font = (FONT_MONO, 13, "bold")
        rv["Equity:"].configure(text=format_with_idr(equity_val, self.cfg), text_color=eq_color, font=eq_font)
        
        margin_val = s.get("margin", 0)
        ml = s.get("margin_level_pct", 0)
        mc_dist = s.get("mc_distance_pips", 0.0)
        net_lots = s.get("net_lots", 0.0)
        
        total_layers = s.get("total_layers", 0)
        
        # Detect hedge condition: positions open but margin=0 due to full hedge
        is_hedged_zero_margin = (total_layers > 0 and margin_val == 0 and abs(net_lots) < 0.01)
        
        if total_layers == 0:
            self._mc_zone_flashing = False
            rv["Margin:"].configure(text=format_with_idr(margin_val, self.cfg), text_color=TEXT_PRIMARY)
            rv["Margin Lvl:"].configure(text="0.0%", text_color=TEXT_PRIMARY)
            rv["MC Price:"].configure(text="0.00", text_color=TEXT_PRIMARY)
            rv["MC Distance:"].configure(text=" 0.0 pips ", text_color=TEXT_PRIMARY, fg_color="transparent")
        else:
            if mc_dist > 1000.0:
                self._mc_zone_state = "GREEN"
                zone_color = TEXT_PRIMARY
            elif mc_dist >= 700.0:
                self._mc_zone_state = "YELLOW"
                zone_color = YELLOW
            else:
                self._mc_zone_state = "RED"
                zone_color = RED
                
            margin_text = format_with_idr(margin_val, self.cfg)
            if is_hedged_zero_margin:
                margin_text += "  ⚖️ Hedge"
            rv["Margin:"].configure(text=margin_text, text_color=zone_color)
            rv["Margin Lvl:"].configure(text=f"{ml:.1f}%" + (" ⚖️" if is_hedged_zero_margin else ""), text_color=zone_color)
            rv["MC Price:"].configure(text=f'{s.get("mc_price", 0):.2f}', text_color=zone_color)
            
            if self._mc_zone_state == "GREEN":
                self._mc_zone_flashing = False
                rv["MC Distance:"].configure(text=f" {mc_dist} pips ", text_color=GREEN_BRIGHT, fg_color="transparent")
            else:
                rv["MC Distance:"].configure(text=f" {mc_dist} pips ")
                if not getattr(self, "_mc_zone_flashing", False):
                    self._mc_zone_flashing = True
                    self._mc_blink_toggle = True
                    self._flash_mc_zone()

        # ── Target profit & loss logic ──
        is_tp_armed = self.cfg.get("target_profit_armed", False)
        if self._tp_armed_var.get() != is_tp_armed:
            self._tp_armed_var.set(is_tp_armed)
        if is_tp_armed:
            self._lbl_tp_status.configure(text="STATUS: AKTIF", text_color=GREEN_BRIGHT)
        else:
            self._lbl_tp_status.configure(text="STATUS: TIDAK AKTIF", text_color=TEXT_SECONDARY)
            
        is_tl_armed = self.cfg.get("target_loss_armed", False)
        if self._tl_armed_var.get() != is_tl_armed:
            self._tl_armed_var.set(is_tl_armed)
        if is_tl_armed:
            self._lbl_tl_status.configure(text="STATUS: AKTIF", text_color=RED)
        else:
            self._lbl_tl_status.configure(text="STATUS: TIDAK AKTIF", text_color=TEXT_SECONDARY)
            
        # calculate progress
        target_tp_usc = self.cfg.get("target_profit_native", 0)
        target_tl_usc = self.cfg.get("target_loss_native", 0)
        floating_pnl = s.get("floating_pnl_usc", 0)
        
        # TP Progress (only track if floating is positive)
        ratio_tp = 0.0
        if target_tp_usc > 0 and floating_pnl > 0:
            ratio_tp = floating_pnl / target_tp_usc
        
        self._draw_progress_bar(self._tp_canvas, ratio_tp, GREEN_BRIGHT)
        self._lbl_tp_progress.configure(text=f"{ratio_tp * 100:.1f}% Menuju Target", text_color=GREEN_BRIGHT if ratio_tp > 0 else TEXT_SECONDARY)
            
        # TL Progress (only track if floating is negative)
        ratio_tl = 0.0
        if target_tl_usc > 0 and floating_pnl < 0:
            ratio_tl = abs(floating_pnl) / target_tl_usc
            
        self._draw_progress_bar(self._tl_canvas, ratio_tl, RED)
        self._lbl_tl_progress.configure(text=f"{ratio_tl * 100:.1f}% (Drawdown)", text_color=RED if ratio_tl > 0 else TEXT_SECONDARY)
        
        # trigger popups
        if self.cfg.get("trigger_celebration", False):
            self.cfg.set("trigger_celebration", False)
            amt_str = self.cfg.get("celebration_amount_str", "")
            pct_str = self.cfg.get("celebration_pct_str", "0.0")
            new_bal = self.cfg.get("celebration_new_balance", "0.00")
            self._trigger_cuan_celebration(amt_str, pct_str, new_bal)
            
        if self.cfg.get("trigger_loss_popup", False):
            self.cfg.set("trigger_loss_popup", False)
            amt_str = self.cfg.get("loss_amount_str", "")
            pct_str = self.cfg.get("loss_pct_str", "0.0")
            rem_pct = self.cfg.get("loss_rem_pct_str", "100.0")
            new_bal = self.cfg.get("loss_new_balance", "0.00")
            self._trigger_loss_celebration(amt_str, pct_str, rem_pct, new_bal)

        # ── Equity protection alarm ──
        if self.cfg.get("equity_alarm_armed", True):
            eq = s.get("equity", 0)
            bal = s.get("balance", 0)
            threshold_pct = self.cfg.get("equity_protection_pct", 30)
            if bal > 0:
                loss_pct = ((bal - eq) / bal) * 100
                if loss_pct >= threshold_pct and eq > 0:
                    self._trigger_equity_alarm()
                else:
                    self._equity_alarm_flashing = False
        
        # ── Daily Goal & Risk Tracker logic ──
        sessions = s.get("completed_sessions", 0)
        self._lbl_sessions.configure(text=f"Daily Sessions Completed: {sessions}")

        wins_usc = float(s.get("session_wins") or 0.0)
        losses_usc = float(s.get("session_losses") or 0.0)
        wins_count = s.get("session_wins_count", 0)
        losses_count = s.get("session_losses_count", 0)
        
        daily_net_usc = float(s.get("daily_net_pnl_usc") or 0.0)
        floating_usc = float(s.get("floating_pnl_usc") or 0.0)
        
        goal_current_usc = daily_net_usc + floating_usc
        
        cur = get_currency_label(self.cfg)
        
        goal_current_idr = to_idr(goal_current_usc, self.cfg)
        wins_idr = to_idr(wins_usc, self.cfg)
        losses_idr = to_idr(losses_usc, self.cfg)
        
        try:
            tgt_usc = float(self._var_tgt_usc.get() or 0)
            ls_usc = float(self._var_loss_usc.get() or 0)
            
            if tgt_usc == 0:
                tgt_idr_val = float(self._var_tgt_idr.get().replace(",", "").replace(".", "") or 0)
                if tgt_idr_val > 0: tgt_usc = from_idr_to_account(tgt_idr_val, self.cfg)
                
            if ls_usc == 0:
                ls_idr_val = float(self._var_loss_idr.get().replace(",", "").replace(".", "") or 0)
                if ls_idr_val > 0: ls_usc = from_idr_to_account(ls_idr_val, self.cfg)
            
            # 1. Daily Goal
            if goal_current_usc >= 0:
                goal_ratio = (goal_current_usc / tgt_usc) if tgt_usc > 0 else 0.0
            else:
                goal_ratio = (abs(goal_current_usc) / ls_usc) if ls_usc > 0 else 0.0
                
            self._last_goal_current_native = goal_current_usc
            self._last_tgt_native = tgt_usc
            self._last_ls_native = ls_usc
            self._redraw_daily_goal_bar()
            
            if cur == "IDR":
                self._lbl_daily_goal.configure(text=f"Daily Net: Rp {goal_current_usc:,.0f} | {goal_ratio*100:.1f}%")
            else:
                self._lbl_daily_goal.configure(text=f"Daily Net: {goal_current_usc:+.2f} {cur} (Rp {goal_current_idr:,.0f}) | {goal_ratio*100:.1f}%")
                
            # 2. Session Wins & Losses
            total_session_vol = wins_usc + losses_usc
            win_ratio = (wins_usc / total_session_vol) if total_session_vol > 0 else 0.0
            loss_ratio = (losses_usc / total_session_vol) if total_session_vol > 0 else 0.0
            
            self._pb_session_wins.set(win_ratio)
            self._pb_session_losses.set(loss_ratio)
            
            if cur == "IDR":
                self._lbl_session_wins.configure(text=f"Wins: Rp {wins_usc:,.0f} | {wins_count} Sesi | {win_ratio*100:.1f}%")
                self._lbl_session_losses.configure(text=f"Losses: Rp {losses_usc:,.0f} | {losses_count} Sesi | {loss_ratio*100:.1f}%")
            else:
                self._lbl_session_wins.configure(text=f"Wins: +{wins_usc:,.2f} {cur} (Rp {wins_idr:,.0f}) | {wins_count} Sesi | {win_ratio*100:.1f}%")
                self._lbl_session_losses.configure(text=f"Losses: -{losses_usc:,.2f} {cur} (Rp {losses_idr:,.0f}) | {losses_count} Sesi | {loss_ratio*100:.1f}%")
                
        except Exception:
            pass
                    
        # Update price history and draw tick chart
        bid = s.get("bid", 0.0)
        if bid > 0:
            self._price_history.append(bid)
            # update main chart overlay lines
            self.live_chart.update_lines(
                ask=s.get("ask", 0.0),
                bid=s.get("bid", 0.0),
                avg=s.get("avg_price_combined", 0.0),
                mc=s.get("mc_price", 0.0),
                mc_label="MC"
            )
            # update preview simulator chart lines
            sim_res = getattr(self, "sim_result", None)
            if sim_res:
                sim_mc = sim_res.get("new_mc_price", 0.0)
                sim_avg = sim_res.get("new_avg_price", s.get("avg_price_combined", 0.0))
            else:
                sim_mc = s.get("mc_price", 0.0)
                sim_avg = s.get("avg_price_combined", 0.0)
                
            self.sim_chart.update_lines(
                ask=s.get("ask", 0.0),
                bid=s.get("bid", 0.0),
                avg=sim_avg,
                mc=sim_mc,
                mc_label="Sim MC" if sim_res else "MC"
            )

    # ──────────────────────────────────────────────────────────
    # Equity Alarm
    # ──────────────────────────────────────────────────────────

    def _trigger_equity_alarm(self):
        if not self._equity_alarm_flashing:
            self._equity_alarm_flashing = True
            self._flash_equity_alarm()
            # sound in thread to not block
            threading.Thread(target=self._alarm_sound, daemon=True).start()

    def _flash_equity_alarm(self):
        if not self._equity_alarm_flashing:
            self.configure(fg_color=BG_DARK)
            return
        current = self.cget("fg_color")
        next_color = RED_DIM if current == BG_DARK else BG_DARK
        self.configure(fg_color=next_color)
        self.after(400, self._flash_equity_alarm)

    def _flash_mc_zone(self):
        if not getattr(self, "_mc_zone_flashing", False):
            self._risk_vals["MC Distance:"].configure(fg_color="transparent")
            return
            
        self._mc_blink_toggle = not getattr(self, "_mc_blink_toggle", False)
        
        if self._mc_blink_toggle:
            bg_color = YELLOW if getattr(self, "_mc_zone_state", "") == "YELLOW" else RED
            fg_color = "#ffffff"
        else:
            bg_color = BG_DARK
            fg_color = "#ffffff"
            
        self._risk_vals["MC Distance:"].configure(fg_color=bg_color, text_color=fg_color, corner_radius=6)
        self.after(500, self._flash_mc_zone)

    # ──────────────────────────────────────────────────────────
    # Celebration Popups
    # ──────────────────────────────────────────────────────────

    def _trigger_cuan_celebration(self, amt_str, pct_str, new_bal):
        cur = get_currency_label(self.cfg)
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.title("Goal Reached!")
        dialog.geometry("450x280")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 450) // 2
        y = self.winfo_y() + (self.winfo_height() - 280) // 2
        dialog.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(dialog, fg_color=BG_DARK, corner_radius=0)
        frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(frame, text="🎉 TARGET TERCAPAI! 🎉", font=(FONT_FAMILY, 16, "bold"), text_color=GOLD).pack(pady=(25, 10))
        
        textbox = ctk.CTkTextbox(frame, font=(FONT_FAMILY, 12), fg_color="transparent", text_color=TEXT_PRIMARY, wrap="word", width=420, height=140)
        textbox.pack(pady=5, padx=10)
        
        txt = textbox._textbox
        txt.tag_configure("center", justify="center")
        txt.tag_configure("green", foreground=GREEN_BRIGHT, font=(FONT_FAMILY, 12, "bold"))
        txt.tag_configure("blue", foreground="#339af0", font=(FONT_FAMILY, 12, "bold"))
        
        try:
            val = float(str(new_bal).replace(",", ""))
            idr_val = to_idr(val, self.cfg)
            bal_str = f"{new_bal} {cur}\n(Rp {idr_val:,.0f})"
        except ValueError:
            bal_str = f"{new_bal} {cur}"

        textbox.insert("end", "Selamat! Posisi Anda telah otomatis ditutup dengan\nProfit ", "center")
        textbox.insert("end", amt_str.replace(" (Rp ", "\n(Rp ") + "\n\n", ("center", "green"))
        textbox.insert("end", "Pertumbuhan akun: ", "center")
        textbox.insert("end", "+" + pct_str + "%\n", ("center", "green"))
        textbox.insert("end", "Saldo Anda sekarang bertambah menjadi: ", "center")
        textbox.insert("end", f"{bal_str}\n\n", ("center", "blue"))
        textbox.insert("end", "Kerja bagus hari ini! Silakan istirahat dan nikmati profit Anda.", "center")
        
        textbox.configure(state="disabled")
        
        ctk.CTkButton(frame, text="Tutup", width=120, fg_color=GREEN_BRIGHT, hover_color="#20c997",
                      text_color=BG_DARK, font=(FONT_FAMILY, 12, "bold"), command=dialog.destroy).pack(pady=5)

    def _trigger_loss_celebration(self, amt_str, pct_str, rem_pct, new_bal):
        cur = get_currency_label(self.cfg)
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.title("Loss Limit Reached")
        dialog.geometry("450x290")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        
        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 450) // 2
        y = self.winfo_y() + (self.winfo_height() - 290) // 2
        dialog.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(dialog, fg_color=BG_DARK, corner_radius=0)
        frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(frame, text="🛡️ MODAL DIAMANKAN 🛡️", font=(FONT_FAMILY, 16, "bold"), text_color=RED).pack(pady=(25, 10))
        
        textbox = ctk.CTkTextbox(frame, font=(FONT_FAMILY, 12), fg_color="transparent", text_color=TEXT_PRIMARY, wrap="word", width=430, height=150)
        textbox.pack(pady=5, padx=10)
        
        txt = textbox._textbox
        txt.tag_configure("center", justify="center")
        txt.tag_configure("red", foreground=RED, font=(FONT_FAMILY, 12, "bold"))
        txt.tag_configure("blue", foreground="#339af0", font=(FONT_FAMILY, 12, "bold"))
        
        try:
            val = float(str(new_bal).replace(",", ""))
            idr_val = to_idr(val, self.cfg)
            bal_str = f"{new_bal} {cur}\n(Rp {idr_val:,.0f})"
        except ValueError:
            bal_str = f"{new_bal} {cur}"

        textbox.insert("end", "Sayangnya, posisi Anda otomatis ditutup dengan Loss ", "center")
        textbox.insert("end", amt_str.replace(" (Rp ", "\n(Rp ") + "\n", ("center", "red"))
        textbox.insert("end", "karena menyentuh batas risiko.\n\n", "center")
        
        textbox.insert("end", "Tapi TENANG! Ini artinya sistem baru saja menyelamatkan Anda\ndari kerugian yang lebih dalam.\n\n", "center")
        
        textbox.insert("end", "Anda hanya kehilangan ", "center")
        textbox.insert("end", pct_str + "%", ("center", "red"))
        textbox.insert("end", " dari modal,\ndan masih memiliki sisa amunisi sebesar ", "center")
        textbox.insert("end", f"{rem_pct}% ({bal_str})", ("center", "blue"))
        textbox.insert("end", ".\n\nTetap semangat! Market besok masih ada!", "center")
        
        textbox.configure(state="disabled")
        
        ctk.CTkButton(frame, text="Tutup", width=120, fg_color=RED, hover_color="#ff6b6b",
                      text_color="#ffffff", font=(FONT_FAMILY, 12, "bold"), command=dialog.destroy).pack(pady=5)

    @staticmethod
    def _alarm_sound():
        for _ in range(5):
            try:
                winsound.Beep(1200, 200)
                winsound.Beep(800, 200)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # BUTTON CALLBACKS
    # ══════════════════════════════════════════════════════════

    def _on_set_idr_manual(self):
        val = self._entry_idr.get().strip()
        try:
            rate = float(val.replace(",", ""))
            self.cfg.set("usd_idr_rate", rate)
            self.cfg.set("usd_idr_auto", False)
        except ValueError:
            pass

    def _on_hotkey_toggle(self):
        self.cfg.set("hotkeys_enabled", self._hotkey_var.get())

    def _show_hotkey_info(self):
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.title("Hotkey Cheat Sheet")
        dialog.geometry("350x220")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color=CARD_BG)
        
        ctk.CTkLabel(dialog, text="Mission Control Hotkeys", font=(FONT_FAMILY, 14, "bold"), text_color=GOLD).pack(pady=(12, 10))
        
        info = [
            ("Ctrl+Shift+X", "Emergency Close All"),
            ("Ctrl+Shift+H", "Hedge Lock (Kunci Posisi)"),
            ("Ctrl+Shift+B", "Smart Break-Even (BE)"),
            ("Ctrl+Shift+S", "Capture Screenshot"),
        ]
        
        for k, v in info:
            row = ctk.CTkFrame(dialog, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row, text=k, font=(FONT_MONO, 12, "bold"), text_color=GREEN_BRIGHT).pack(side="left")
            ctk.CTkLabel(row, text=v, font=(FONT_FAMILY, 12), text_color=TEXT_PRIMARY).pack(side="right")
            
        dialog.transient(self)
        dialog.focus_force()

    def _on_acct_currency_change(self, new_currency):
        """Handle account currency dropdown change — update config and all dynamic labels."""
        self.cfg.set("account_currency", new_currency)
        cur = new_currency

        # Update Daily Goal tracker column header
        if hasattr(self, '_lbl_tracker_cur_hdr'):
            self._lbl_tracker_cur_hdr.configure(text=cur)

        # Show/hide IDR column if account is already IDR
        if hasattr(self, '_lbl_tracker_idr_hdr'):
            if cur == "IDR":
                self._lbl_tracker_idr_hdr.configure(text="")
            else:
                self._lbl_tracker_idr_hdr.configure(text="IDR")

        # Update Goal-Based Automation label
        if hasattr(self, '_lbl_target_cur'):
            self._lbl_target_cur.configure(text=f"Target {cur}:")

        # Show/hide IDR target field if account is IDR
        if hasattr(self, '_lbl_target_idr_label'):
            if cur == "IDR":
                self._lbl_target_idr_label.grid_remove()
                self._entry_tp_idr.grid_remove()
            else:
                self._lbl_target_idr_label.grid()
                self._entry_tp_idr.grid()
    # -- Panel D callbacks --
    
    def _update_sl_est(self, *args):
        if hasattr(self, '_lbl_sl_est'):
            self._calc_est(self._var_sl, self._lbl_sl_est, "SL")
        
    def _update_tp_est(self, *args):
        if hasattr(self, '_lbl_tp_est'):
            self._calc_est(self._var_tp, self._lbl_tp_est, "TP")
        
    def _calc_est(self, var, lbl, mode):
        try:
            val = float(var.get().strip() or 0)
        except ValueError:
            lbl.configure(text="")
            return
            
        s = self.mt5.get_state() if hasattr(self, 'mt5') and self.mt5 else {}
        if not s or not s.get("connected"):
            lbl.configure(text="")
            return
            
        lots = s.get("total_lots", 0.0)
        avg_combined = s.get("avg_price_combined", 0.0)
        tick_val = s.get("tick_value", 1.0)
        tick_size = s.get("tick_size", 0.01)
        if tick_size <= 0: tick_size = 0.01
        
        if lots == 0 or avg_combined == 0:
            lbl.configure(text="Rp 0")
            return
            
        net_lots = s.get("net_lots", 0.0)
        if net_lots == 0: net_lots = lots
        
        if net_lots > 0:
            profit_usd = (val - avg_combined) * (tick_val / tick_size) * net_lots
        else:
            profit_usd = (avg_combined - val) * (tick_val / tick_size) * abs(net_lots)
            
        from currency_utils import to_idr
        profit_idr = to_idr(profit_usd, self.cfg)
        color = GREEN_BRIGHT if profit_usd >= 0 else RED
        lbl.configure(text=f"Est: Rp {profit_idr:,.0f}", text_color=color)

    def _on_tp_mode_change(self, mode):
        if mode == "TP ALL":
            self._frame_tp_custom.grid_remove()
            self._lbl_tp_all.grid()
            self._entry_tp.grid()
        else:
            self._lbl_tp_all.grid_remove()
            self._entry_tp.grid_remove()
            self._frame_tp_custom.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 5))

    def _recalc_runner(self, *args):
        try:
            v1 = int(self._var_vol1.get().replace("%", ""))
            v2 = int(self._var_vol2.get().replace("%", ""))
            v3 = int(self._var_vol3.get().replace("%", ""))
            
            total = v1 + v2 + v3
            rem = 100 - total
            if rem < 0:
                self._lbl_runner_pct.configure(text=f"ERROR: {total}% > 100%", text_color=RED)
                self._btn_apply_sltp.configure(state="disabled")
            else:
                self._lbl_runner_pct.configure(text=f"{rem}% (Runner)", text_color=TEXT_PRIMARY)
                self._btn_apply_sltp.configure(state="normal")
        except:
            pass
    def _on_apply_sltp(self):
        import MetaTrader5 as mt5
        from currency_utils import to_idr, get_currency_label
        
        mode = self._tp_mode_var.get()
        sl_text = self._entry_sl.get().strip()
        try:
            sl = float(sl_text) if sl_text else None
        except ValueError:
            sl = None
            
        state = self.mt5.get_state()
        symbol = state.get("active_symbol", self.cfg.get("symbol", ""))
        cur = get_currency_label(self.cfg)
        positions = self.mt5._get_filtered_positions()
        
        if mode == "TP ALL":
            tp_text = self._entry_tp.get().strip()
            try:
                tp = float(tp_text) if tp_text else None
            except ValueError:
                tp = None
                
            if sl is None and tp is None: return
            
            msg_tuples = []
            if tp is not None:
                total_tp_prof = 0.0
                valid_tp = True
                for p in positions:
                    order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                    prof = mt5.order_calc_profit(order_type, symbol, p.volume, p.price_open, tp)
                    if prof is None:
                        valid_tp = False
                        break
                    total_tp_prof += prof + getattr(p, "swap", 0.0)
                if valid_tp and len(positions) > 0:
                    idr_val = to_idr(total_tp_prof, self.cfg)
                    msg_tuples.append((f"Jika TP ({tp}) tersentuh:", TEXT_PRIMARY))
                    if cur == "IDR":
                        msg_tuples.append((f"Profit Rp {total_tp_prof:,.0f}", GREEN_BRIGHT))
                    else:
                        msg_tuples.append((f"Profit {total_tp_prof:+.2f} {cur} (Rp {idr_val:,.0f})", GREEN_BRIGHT))
                else:
                    msg_tuples.append((f"Set TP={tp}", TEXT_PRIMARY))
            
            if sl is not None:
                total_sl_loss = 0.0
                valid_sl = True
                for p in positions:
                    order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                    prof = mt5.order_calc_profit(order_type, symbol, p.volume, p.price_open, sl)
                    if prof is None:
                        valid_sl = False
                        break
                    total_sl_loss += prof + getattr(p, "swap", 0.0)
                if valid_sl and len(positions) > 0:
                    idr_val = to_idr(total_sl_loss, self.cfg)
                    if msg_tuples: msg_tuples.append(("", TEXT_PRIMARY))
                    msg_tuples.append((f"Jika SL ({sl}) tersentuh:", TEXT_PRIMARY))
                    if cur == "IDR":
                        msg_tuples.append((f"Loss Rp {total_sl_loss:,.0f}", RED))
                    else:
                        msg_tuples.append((f"Loss {total_sl_loss:+.2f} {cur} (Rp {idr_val:,.0f})", RED))
                else:
                    if msg_tuples: msg_tuples.append(("", TEXT_PRIMARY))
                    msg_tuples.append((f"Set SL={sl}", TEXT_PRIMARY))
                    
            if not msg_tuples: return
            msg_tuples.append(("", TEXT_PRIMARY))
            msg_tuples.append(("Terapkan ke SEMUA posisi?", TEXT_PRIMARY))
            
            self._confirm_and_execute(
                "Apply SL/TP",
                msg_tuples,
                lambda: self._run_in_thread(self.mt5.bulk_set_sl_tp, sl, tp))
        else:
            # CUSTOM MODE
            try:
                v1 = int(self._var_vol1.get().replace("%", ""))
                v2 = int(self._var_vol2.get().replace("%", ""))
                v3 = int(self._var_vol3.get().replace("%", ""))
            except:
                return
                
            total = v1 + v2 + v3
            if total > 100: return
            
            tiers = []
            try:
                if v1 > 0:
                    t = self._entry_tp1.get().strip()
                    if t: tiers.append({"tp": float(t), "pct": v1})
                if v2 > 0:
                    t = self._entry_tp2.get().strip()
                    if t: tiers.append({"tp": float(t), "pct": v2})
                if v3 > 0:
                    t = self._entry_tp3.get().strip()
                    if t: tiers.append({"tp": float(t), "pct": v3})
            except ValueError:
                pass
                
            rem = 100 - total
            if rem > 0:
                tiers.append({"tp": 0.0, "pct": rem})
                
            msg_tuples = [
                ("Menerapkan Multi-Tier Take Profit:", TEXT_PRIMARY)
            ]
            
            positions.sort(key=lambda p: p.profit)
            total_pos = len(positions)
            
            counts = []
            for tier in tiers:
                counts.append(round(total_pos * (tier["pct"] / 100.0)))
                
            total_counts = sum(counts)
            if total_counts < total_pos and len(counts) > 0:
                counts[0] += (total_pos - total_counts)
            elif total_counts > total_pos and len(counts) > 0:
                counts[0] -= (total_counts - total_pos)
                counts[0] = max(0, counts[0])
                
            pos_idx = 0
            for i, tier in enumerate(tiers):
                count = counts[i]
                target_price = tier["tp"]
                
                tier_prof = 0.0
                valid = True
                
                for _ in range(count):
                    if pos_idx >= total_pos: break
                    p = positions[pos_idx]
                    pos_idx += 1
                    
                    if target_price > 0:
                        order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                        prof = mt5.order_calc_profit(order_type, symbol, p.volume, p.price_open, target_price)
                        if prof is not None:
                            tier_prof += prof + getattr(p, "swap", 0.0)
                        else:
                            valid = False
                
                if target_price > 0:
                    if valid and count > 0:
                        idr_val = to_idr(tier_prof, self.cfg)
                        if cur == "IDR":
                            msg_tuples.append((f"- {tier['pct']}% ({count} pos): TP {target_price} \u27a1 Prof Rp {tier_prof:,.0f}", GREEN_BRIGHT))
                        else:
                            msg_tuples.append((f"- {tier['pct']}% ({count} pos): TP {target_price} \u27a1 Prof {tier_prof:+.2f} {cur} (Rp {idr_val:,.0f})", GREEN_BRIGHT))
                    else:
                        msg_tuples.append((f"- {tier['pct']}% layer ditutup pada {target_price}", GREEN_BRIGHT))
                else:
                    msg_tuples.append((f"- {tier['pct']}% layer dibiarkan OPEN tanpa TP", GOLD))
                    
            if sl is not None:
                total_sl_loss = 0.0
                valid_sl = True
                for p in positions:
                    order_type = mt5.ORDER_TYPE_BUY if p.type == 0 else mt5.ORDER_TYPE_SELL
                    prof = mt5.order_calc_profit(order_type, symbol, p.volume, p.price_open, sl)
                    if prof is None:
                        valid_sl = False
                        break
                    total_sl_loss += prof + getattr(p, "swap", 0.0)
                    
                msg_tuples.append(("", TEXT_PRIMARY))
                if valid_sl and len(positions) > 0:
                    idr_val = to_idr(total_sl_loss, self.cfg)
                    if cur == "IDR":
                        msg_tuples.append((f"SL {sl} \u27a1 Loss Rp {total_sl_loss:,.0f}", RED))
                    else:
                        msg_tuples.append((f"SL {sl} \u27a1 Loss {total_sl_loss:+.2f} {cur} (Rp {idr_val:,.0f})", RED))
                else:
                    msg_tuples.append((f"SL dipasang ke: {sl} untuk semua layer.", TEXT_PRIMARY))
                
            self._confirm_and_execute(
                "Scale Out (Multi TP)",
                msg_tuples,
                lambda: self._run_in_thread(self.mt5.apply_multi_tp, sl, tiers))
    def _on_smart_be(self):
        try:
            offset = float(self._entry_be_offset.get() or 0.5)
        except ValueError:
            offset = 0.5
        self.cfg.set("be_offset_pips", offset)
        msg_tuples = [
            (f"Move SL to average price ± {offset} pips on ALL positions?", TEXT_PRIMARY),
            ("Estimasi Profit: ~Break Even / Sangat Kecil", GREEN_BRIGHT)
        ]
        self._confirm_and_execute(
            "Smart Break-Even",
            msg_tuples,
            lambda: self._run_in_thread(self.mt5.smart_be, offset))

    def _on_toggle_trailing(self):
        active = self.mt5.is_trailing_active()
        if active:
            self.mt5.set_trailing_active(False)
            self._btn_trail.configure(text="Start Trailing", fg_color=GOLD_DIM)
        else:
            try:
                pips = float(self._entry_trail.get() or 10.0)
            except ValueError:
                pips = 10.0
            self.cfg.set("trailing_stop_pips", pips)
            self.mt5.set_trailing_active(True)
            self._btn_trail.configure(text="⏹ Stop Trailing", fg_color=RED_DIM)

    def _on_selective_close(self):
        qty_mode = self._opt_close_qty_mode.get()
        
        if qty_mode == "All":
            qty = None
            qty_display = "ALL"
            qty_config = 1
        else:
            raw_qty = self._entry_close_qty_custom.get().strip()
            if not raw_qty or not raw_qty.isdigit() or int(raw_qty) <= 0:
                import tkinter.messagebox
                tkinter.messagebox.showerror("Invalid Input", "Please enter a valid quantity (minimum 1).")
                return
            qty = int(raw_qty)
            qty_display = str(qty)
            qty_config = qty
        
        direction = self._opt_close_dir.get()
        sort_order = self._opt_close_sort.get()
        
        if sort_order == "All":
            qty = None
            qty_display = "ALL"
            
        self.cfg.set_many({
            "selective_close_qty_mode": qty_mode,
            "selective_close_qty": qty_config,
            "selective_close_direction": direction,
            "selective_close_sort": sort_order,
        })
        
        # Calculate precise PnL estimate
        targets = self.mt5.get_selective_close_targets(qty, direction, sort_order)
        total_pnl = sum(p.profit + getattr(p, 'swap', 0.0) for p in targets)
        actual_qty = len(targets)
        
        from currency_utils import to_idr, get_currency_label
        cur = get_currency_label(self.cfg)
        idr_val = to_idr(total_pnl, self.cfg)
        
        msg_tuples = [
            (f"Close {actual_qty} {direction} position(s) sorted by '{sort_order}'?", TEXT_PRIMARY),
            ("", TEXT_PRIMARY),
            (f"Estimasi Hasil dari {actual_qty} Posisi Tersebut:", TEXT_PRIMARY),
        ]
        color = GREEN_BRIGHT if total_pnl >= 0 else RED
        
        if cur == "IDR":
            msg_tuples.append((f"{'Profit' if total_pnl>=0 else 'Loss'} Rp {total_pnl:,.0f}", color))
        else:
            msg_tuples.append((f"{'Profit' if total_pnl>=0 else 'Loss'} {total_pnl:+.2f} {cur} (Rp {idr_val:,.0f})", color))
            
        self._confirm_and_execute(
            "Selective Close",
            msg_tuples,
            lambda: self._run_in_thread(self.mt5.selective_close, qty, direction, sort_order))

    def _sync_tp_usc(self, *args):
        if getattr(self, '_syncing_tp', False): return
        try:
            val_str = self._var_tp_usc.get()
            if not val_str: return
            val = float(val_str)
            idr = to_idr(val, self.cfg)
            self._syncing_tp = True
            self._var_tp_idr.set(f"{idr:.0f}")
            self.cfg.set_many({"target_profit_native": val, "target_profit_idr": idr})
            self._syncing_tp = False
        except ValueError:
            pass

    def _sync_tp_idr(self, *args):
        if getattr(self, '_syncing_tp', False): return
        try:
            val_str = self._var_tp_idr.get().replace(",", "")
            if not val_str: return
            val = float(val_str)
            acct_val = from_idr_to_account(val, self.cfg)
            self._syncing_tp = True
            self._var_tp_usc.set(f"{acct_val:.2f}")
            self.cfg.set_many({"target_profit_native": acct_val, "target_profit_idr": val})
            self._syncing_tp = False
        except ValueError:
            pass

    def _sync_tl_usc(self, *args):
        if getattr(self, '_syncing_tl', False): return
        try:
            val_str = self._var_tl_usc.get()
            if not val_str: return
            val = float(val_str)
            idr = to_idr(val, self.cfg)
            self._syncing_tl = True
            self._var_tl_idr.set(f"{idr:.0f}")
            self.cfg.set_many({"target_loss_native": val, "target_loss_idr": idr})
            self._syncing_tl = False
        except ValueError:
            pass

    def _sync_tl_idr(self, *args):
        if getattr(self, '_syncing_tl', False): return
        try:
            val_str = self._var_tl_idr.get().replace(",", "")
            if not val_str: return
            val = float(val_str)
            acct_val = from_idr_to_account(val, self.cfg)
            self._syncing_tl = True
            self._var_tl_usc.set(f"{acct_val:.2f}")
            self.cfg.set_many({"target_loss_native": acct_val, "target_loss_idr": val})
            self._syncing_tl = False
        except ValueError:
            pass

    def _show_custom_info(self, title, message, text_color):
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.title(title)
        dialog.geometry("350x150")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        
        lbl = ctk.CTkLabel(dialog, text=message, font=(FONT_FAMILY, 12, "bold"), text_color=text_color)
        lbl.pack(expand=True, padx=20, pady=(20, 10))
        
        btn = ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy)
        btn.pack(pady=(0, 20))

    def _on_arm_target_profit_switch(self):
        armed = self._tp_armed_var.get()
        if armed:
            try:
                usc = float(str(self._var_tp_usc.get()).replace(",", "") or 0)
                idr = float(str(self._var_tp_idr.get()).replace(",", "") or 0)
            except ValueError:
                self._tp_armed_var.set(False)
                return
            def confirm_action():
                self.cfg.set_many({
                    "target_profit_native": usc,
                    "target_profit_idr": idr,
                    "target_profit_armed": True,
                })
                
            def cancel_action():
                self._tp_armed_var.set(False)
                
            self._confirm_and_execute(
                "Konfirmasi Auto-Close",
                [(f"Apakah Anda yakin ingin MENGAKTIFKAN Auto-Close Target Profit?\n\nNilai Target: {usc:.2f} USD / Rp {idr:,.0f}", GREEN_BRIGHT)],
                action=confirm_action,
                cancel_action=cancel_action
            )
        else:
            self.cfg.set("target_profit_armed", False)

    def _on_arm_target_loss_switch(self):
        armed = self._tl_armed_var.get()
        if armed:
            try:
                usc = float(str(self._var_tl_usc.get()).replace(",", "") or 0)
                idr = float(str(self._var_tl_idr.get()).replace(",", "") or 0)
            except ValueError:
                self._tl_armed_var.set(False)
                return
            def confirm_action():
                self.cfg.set_many({
                    "target_loss_native": usc,
                    "target_loss_idr": idr,
                    "target_loss_armed": True,
                })
                
            def cancel_action():
                self._tl_armed_var.set(False)
                
            self._confirm_and_execute(
                "Konfirmasi Auto-Close",
                [(f"Apakah Anda yakin ingin MENGAKTIFKAN Auto-Close Target Loss?\n\nNilai Target: {usc:.2f} USD / Rp {idr:,.0f}", RED)],
                action=confirm_action,
                cancel_action=cancel_action
            )
        else:
            self.cfg.set("target_loss_armed", False)

    # -- Panel E callbacks --

    def _on_emergency_close(self):
        from currency_utils import to_idr, get_currency_label
        state = self.mt5.get_state()
        pnl = state.get("floating_pnl_usc", 0.0)
        cur = get_currency_label(self.cfg)
        idr_val = to_idr(pnl, self.cfg)
        
        msg_tuples = [
            ("This will close ALL XAUUSD positions immediately!\nAre you absolutely sure?", TEXT_PRIMARY),
            ("", TEXT_PRIMARY),
            ("Estimasi Hasil (Floating PnL Saat Ini):", TEXT_PRIMARY),
        ]
        color = GREEN_BRIGHT if pnl >= 0 else RED
        if cur == "IDR":
            msg_tuples.append((f"{'Profit' if pnl>=0 else 'Loss'} Rp {pnl:,.0f}", color))
        else:
            msg_tuples.append((f"{'Profit' if pnl>=0 else 'Loss'} {pnl:+.2f} {cur} (Rp {idr_val:,.0f})", color))
            
        self._confirm_and_execute(
            "⚠️ EMERGENCY CLOSE ALL",
            msg_tuples,
            lambda: self._run_in_thread(self.mt5.emergency_close_all),
            screenshot_label="emergency_close")

    def _on_hedge(self):
        from currency_utils import to_idr, get_currency_label
        state = self.mt5.get_state()
        pnl = state.get("floating_pnl_usc", 0.0)
        cur = get_currency_label(self.cfg)
        idr_val = to_idr(pnl, self.cfg)
        
        msg_tuples = [
            ("Open an opposite position to lock current floating P/L?", TEXT_PRIMARY),
            ("", TEXT_PRIMARY),
            ("Floating P/L yang akan dikunci:", TEXT_PRIMARY),
        ]
        color = GREEN_BRIGHT if pnl >= 0 else RED
        if cur == "IDR":
            msg_tuples.append((f"Rp {pnl:,.0f}", color))
        else:
            msg_tuples.append((f"{pnl:+.2f} {cur} (Rp {idr_val:,.0f})", color))

        self._confirm_and_execute(
            "Hedge Lock",
            msg_tuples,
            lambda: self._run_in_thread(self.mt5.hedge_lock),
            screenshot_label="hedge_lock")

    # -- Simulator --

    def _on_simulate(self):
        try:
            lots = float(self._entry_sim_lots.get() or 0.1)
        except ValueError:
            lots = 0.1
        direction = self._sim_dir.get()
        result = self.mt5.simulate_add_layer(lots, direction)
        if "error" in result:
            self._lbl_sim_result.configure(text=f"Error: {result['error']}",
                                            text_color=RED)
            return
        safety = result.get("safety", "DANGER")
        color_map = {
            "SAFE": (GREEN_BRIGHT, "#ffffff"), 
            "WARNING": (ORANGE, "#000000"), 
            "DANGER": (RED, "#ffffff")
        }
        bg_col, fg_col = color_map.get(safety, (RED, "#ffffff"))
        text = (f" New MC: {result['new_mc_price']:.2f}  |  "
                f"Dist: {result['new_mc_distance_pips']} pips  |  "
                f"Net: {result['new_net_lots']:.2f}     {safety}   ")
        self._lbl_sim_result.configure(text=text,
                                        text_color=fg_col, fg_color=bg_col, corner_radius=6)
        
        self.sim_result = result

    def _draw_tick_chart(self, state: dict):
        # We no longer use canvas meter, only update the sim_chart
        self._simulated_mc_price = self.sim_result.get("new_mc_price", 0.0) if hasattr(self, 'sim_result') else 0.0
        s = self.mt5.get_state() if self.mt5 else {}
        self.sim_chart.update_lines(
            ask=s.get("ask", 0),
            bid=s.get("bid", 0),
            avg=self.sim_result.get("new_avg_price", s.get("avg_price_combined", 0)) if hasattr(self, 'sim_result') else s.get("avg_price_combined", 0),
            mc=self._simulated_mc_price,
            mc_label="Sim MC"
        )

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _show_info_popup(self, title: str, message):
        """Show information popup with dark theme.
        `message` can be a string or a list of tuples: [(text, color_hex), ...].
        """
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.withdraw()  # Hide to prevent flicker
        dialog.title(title)
        dialog.configure(fg_color=CARD_BG)

        ctk.CTkLabel(dialog, text=title, font=(FONT_FAMILY, 15, "bold"),
                     text_color=GOLD).pack(pady=(18, 4))
                     
        if isinstance(message, str):
            message = [(message, TEXT_PRIMARY)]
            
        for line, color in message:
            if not line:
                ctk.CTkFrame(dialog, height=1, fg_color=CARD_BORDER).pack(fill="x", padx=30, pady=8)
            else:
                ctk.CTkLabel(dialog, text=line, font=(FONT_FAMILY, 12),
                             text_color=color).pack(padx=30, pady=2)
                             
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(20, 15))
        
        btn_ok = ctk.CTkButton(btn_frame, text="OK", width=120, height=35,
                               fg_color=BLUE, hover_color="#79c0ff", text_color=BG_DARK,
                               font=(FONT_FAMILY, 12, "bold"),
                               command=dialog.destroy)
        btn_ok.pack()
        
        dialog.update_idletasks()
        
        # Center dialog
        w = max(380, dialog.winfo_reqwidth())
        h = max(150, dialog.winfo_reqheight() + 20)
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        dialog.deiconify()
        
        btn_ok.focus_set()
        dialog.bind("<Return>", lambda e: dialog.destroy())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def _confirm_and_execute(self, title: str, message, action, screenshot_label: str = "", cancel_action=None):
        """Show confirmation popup smoothly then execute action + optional screenshot.
        `message` can be a string or a list of tuples: [(text, color_hex), ...].
        """
        dialog = ctk.CTkToplevel(self, fg_color=BG_DARK)
        dialog.withdraw()  # Hide to prevent flicker
        dialog.title(title)
        dialog.configure(fg_color=CARD_BG)

        ctk.CTkLabel(dialog, text=title, font=(FONT_FAMILY, 15, "bold"),
                     text_color=GOLD).pack(pady=(18, 4))
                     
        if isinstance(message, str):
            message = [(message, TEXT_PRIMARY)]
            
        for text, color in message:
            if not text:
                ctk.CTkFrame(dialog, height=12, fg_color="transparent").pack()
            else:
                is_val = color != TEXT_PRIMARY
                font_sz = 14 if is_val else 13
                weight = "bold" if is_val else "normal"
                ctk.CTkLabel(dialog, text=text, font=(FONT_FAMILY, font_sz, weight),
                             text_color=color, wraplength=400, justify="center").pack(pady=(0, 6))
        
        # spacer
        ctk.CTkFrame(dialog, height=10, fg_color="transparent").pack()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=(0, 18))

        def on_confirm():
            dialog.destroy()
            if screenshot_label:
                threading.Thread(target=self.mt5.capture_screenshot,
                                 args=(screenshot_label,), daemon=True).start()
            action()

        def on_cancel():
            dialog.destroy()
            if cancel_action:
                cancel_action()

        ctk.CTkButton(btn_row, text="Confirm", width=100, height=32,
                      fg_color=GREEN, hover_color=GREEN_BRIGHT,
                      text_color="#fff", font=(FONT_FAMILY, 12, "bold"),
                      command=on_confirm).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100, height=32,
                      fg_color=CARD_BORDER, hover_color=TEXT_SECONDARY,
                      text_color=TEXT_PRIMARY, font=(FONT_FAMILY, 12),
                      command=on_cancel).pack(side="left", padx=8)
                      
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        # Calculate dimensions and center smoothly
        dialog.update_idletasks()
        req_width = max(440, dialog.winfo_reqwidth() + 20)
        req_height = max(190, dialog.winfo_reqheight() + 20)
        
        x = self.winfo_x() + (self.winfo_width() - req_width) // 2
        y = self.winfo_y() + (self.winfo_height() - req_height) // 2
        dialog.geometry(f"{req_width}x{req_height}+{x}+{y}")
        dialog.resizable(False, False)
        
        dialog.transient(self)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        dialog.bind("<Return>", lambda e: on_confirm())
        dialog.bind("<Escape>", lambda e: on_cancel())
        dialog.deiconify()  # Show smoothly at the correct position
        dialog.focus_force()

    def _run_in_thread(self, fn, *args):
        """Run a blocking MT5 action in a daemon thread and safely report errors to the GUI."""
        def worker():
            try:
                res = fn(*args)
                if not res: 
                    return
                
                errors = []
                if isinstance(res, list):
                    for r in res:
                        rc = r.get("retcode", -1)
                        if rc != 10009 and rc != -1: # 10009 is mt5.TRADE_RETCODE_DONE
                            ticket = r.get("ticket", "N/A")
                            comment = r.get("comment", "")
                            errors.append(f"Ticket {ticket}: Error {rc} - {comment}")
                        elif rc == -1 and r.get("comment"):
                            ticket = r.get("ticket", "N/A")
                            errors.append(f"Ticket {ticket}: {r.get('comment')}")
                elif isinstance(res, dict):
                    rc = res.get("retcode", -1)
                    if rc != 10009:
                        comment = res.get("comment", res.get("msg", "Unknown Error"))
                        errors.append(f"Error {rc}: {comment}")
                
                if errors:
                    err_msg = "EXECUTION FAILED!\n\n" + "\n".join(errors)
                    import tkinter.messagebox as messagebox
                    self.after(0, lambda: messagebox.showerror("Execution Error", err_msg))
                    
            except Exception as e:
                import tkinter.messagebox as messagebox
                self.after(0, lambda e=e: messagebox.showerror("Execution Error", f"Exception during execution:\n{str(e)}"))
                
        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ── Public methods for external hotkey triggers ──────────

    def trigger_emergency_close(self):
        """Called from global hotkey — schedules on main thread."""
        self.after(0, self._on_emergency_close)

    def _draw_progress_bar(self, canvas, ratio, color):
        if not canvas: return
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1: return
        
        canvas.delete("all")
        
        # Clamp ratio to [0.0, 1.0]
        clamped_ratio = max(0.0, min(1.0, ratio))
        
        if clamped_ratio > 0:
            rx = w * clamped_ratio
            canvas.create_rectangle(0, 0, rx, h, fill=color, outline="")

    def trigger_smart_be(self):
        self.after(0, self._on_smart_be)

    def trigger_hedge(self):
        self.after(0, self._on_hedge)

    def trigger_screenshot(self):
        threading.Thread(target=self.mt5.capture_screenshot,
                         args=("hotkey_capture",), daemon=True).start()
        try:
            winsound.Beep(600, 100)
        except Exception:
            pass

    # ── Window close ─────────────────────────────────────────

    def _on_close(self):
        self.mt5.stop_polling()
        self.mt5.disconnect()
        self.destroy()
