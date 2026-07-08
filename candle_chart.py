import time
import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import mplfinance as mpf
import pandas as pd
from datetime import datetime

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

class CandleChart(ctk.CTkFrame):
    def __init__(self, master, mt5_mgr, title="Live Chart", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.mt5 = mt5_mgr
        self.title = title
        
        # UI
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 4))
        
        ctk.CTkLabel(top_bar, text=title, font=(FONT_FAMILY, 12, "bold"), text_color=GOLD).pack(side="left")
        
        self.tf_var = ctk.StringVar(value="M5")
        tfs = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
        self.tf_menu = ctk.CTkOptionMenu(top_bar, values=tfs, variable=self.tf_var, width=60, height=24,
                                         font=(FONT_FAMILY, 10), fg_color=CARD_BORDER, button_color=GOLD_DIM, button_hover_color=GOLD,
                                         command=self._on_tf_change)
        self.tf_menu.pack(side="right")
        
        controls_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        controls_frame.pack(side="right", padx=(0, 10))

        self.btn_reset = ctk.CTkButton(controls_frame, text="⟲ Reset", width=50, height=24,
                                       font=(FONT_FAMILY, 10), fg_color=CARD_BORDER,
                                       hover_color=GOLD_DIM, command=self._reset_view)
        self.btn_reset.pack(side="left", padx=2)

        self.btn_fit = ctk.CTkButton(controls_frame, text="Fit MC/Avg", width=70, height=24,
                                     font=(FONT_FAMILY, 10), fg_color=CARD_BORDER,
                                     hover_color=GOLD_DIM, command=self._fit_to_mc_avg)
        self.btn_fit.pack(side="left", padx=2)
        
        info_label = ctk.CTkLabel(controls_frame, text="Right-drag to zoom price range", 
                                  font=(FONT_FAMILY, 9, "italic"), text_color=TEXT_SECONDARY)
        info_label.pack(side="left", padx=(5, 2))

        
        # Matplotlib
        self.fig = Figure(figsize=(5, 2.5), facecolor=BG_DARK)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(BG_DARK)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        self._last_fetch = 0
        self.candles = []
        
        self.line_ask = None
        self.line_bid = None
        self.line_avg = None
        self.line_mc = None
        self.text_avg = None
        self.text_mc = None
        
        # Save current overlay prices
        self.current_ask = 0
        self.current_bid = 0
        self.current_avg = 0
        self.current_mc = 0
        self.current_mc_label = "MC"
        
        # Interactive State
        self._custom_xlim = None
        self._custom_ylim = None
        
        self._zoom_start_y = None
        self._zoom_orig_ylim = None
        self._zoom_center = None
        
        self.canvas.mpl_connect('button_press_event', self._on_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_motion)
        self.canvas.mpl_connect('button_release_event', self._on_release)
        
        self._after_id = None
        self._auto_update()

    def _auto_update(self):
        self.update_candles()
        self._after_id = self.after(5000, self._auto_update)

    def destroy(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        super().destroy()

    def _on_tf_change(self, val):
        self._last_fetch = 0
        self._custom_xlim = None
        self._custom_ylim = None
        self.update_candles(force=True)

    def _reset_view(self):
        self._custom_xlim = None
        self._custom_ylim = None
        self._draw_candles()
        
    def _fit_to_mc_avg(self):
        if not self.candles:
            return
            
        lows = [c['low'] for c in self.candles]
        highs = [c['high'] for c in self.candles]
        
        y_min_target = min(lows) if lows else 0
        y_max_target = max(highs) if highs else 0
        
        if getattr(self, 'current_avg', 0) and self.current_avg > 0:
            y_min_target = min(y_min_target, self.current_avg)
            y_max_target = max(y_max_target, self.current_avg)
            
        if getattr(self, 'current_mc', 0) and self.current_mc > 0:
            y_min_target = min(y_min_target, self.current_mc)
            y_max_target = max(y_max_target, self.current_mc)
            
        rng = y_max_target - y_min_target
        if rng == 0:
            rng = y_min_target * 0.001 if y_min_target else 1
            
        self._custom_ylim = (y_min_target - rng*0.05, y_max_target + rng*0.05)
        self._custom_xlim = None  # show all candles in X
        self._draw_candles()

    def _on_press(self, event):
        if event.inaxes != self.ax:
            return
        if event.button == 3:
            self._zoom_start_y = event.y
            self._zoom_orig_ylim = self.ax.get_ylim()
            self._zoom_center = event.ydata

    def _on_motion(self, event):
        if event.inaxes != self.ax:
            return
            
        if getattr(self, '_zoom_start_y', None) is not None:
            dy_pixels = event.y - self._zoom_start_y
            zoom_factor = 1.0 - (dy_pixels * 0.005)
            if zoom_factor < 0.1: zoom_factor = 0.1
            if zoom_factor > 10.0: zoom_factor = 10.0
            
            orig_span = self._zoom_orig_ylim[1] - self._zoom_orig_ylim[0]
            new_span = orig_span * zoom_factor
            
            center = self._zoom_center
            self._custom_ylim = (center - new_span/2, center + new_span/2)
            self.ax.set_ylim(self._custom_ylim)
            self.canvas.draw_idle()

    def _on_release(self, event):
        if event.button == 3:
            self._zoom_start_y = None
            self._zoom_orig_ylim = None
            self._zoom_center = None

    def update_candles(self, force=False):
        now = time.time()
        if not force and now - self._last_fetch < 5.0:
            return
            
        self._last_fetch = now
        
        if not self.mt5.is_connected():
            return
            
        state = self.mt5.get_state()
        symbol = state.get("active_symbol")
        if not symbol:
            symbol = self.mt5.cfg.get("symbol")
            
        if not symbol:
            return
            
        self.candles = self.mt5.get_candles(symbol, self.tf_var.get(), 60)
        
        print(f"[Chart] Rendering {len(self.candles)} candles for {symbol} @ {self.tf_var.get()}")
        self._draw_candles()
        
    def _draw_candles(self):
        try:
            self.ax.clear()
            
            # Reset line references
            self.line_ask = None
            self.line_bid = None
            self.line_avg = None
            self.line_mc = None
            self.text_avg = None
            self.text_mc = None
            
            if not self.candles:
                self.ax.set_facecolor(BG_DARK)
                for spine in self.ax.spines.values():
                    spine.set_color(CARD_BORDER)
                self.ax.text(0.5, 0.5, 'Tidak ada data candle untuk\nsimbol/timeframe ini', 
                            horizontalalignment='center', verticalalignment='center',
                            transform=self.ax.transAxes, color=TEXT_SECONDARY, fontsize=10)
                self.ax.set_xticks([])
                self.ax.set_yticks([])
                self.canvas.draw_idle()
                return
                
            df = pd.DataFrame(self.candles)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df = df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'})
            if 'volume' not in df.columns:
                df['Volume'] = 0
                
            mc = mpf.make_marketcolors(up=GREEN, down=RED, wick={'up':GREEN, 'down':RED}, edge='inherit')
            style = mpf.make_mpf_style(marketcolors=mc, facecolor=BG_DARK, edgecolor=BG_DARK, 
                                       gridcolor=CARD_BORDER, gridstyle=':')
                                       
            # mpf.plot draws on self.ax directly when ax is passed
            mpf.plot(df, type='candle', ax=self.ax, style=style, show_nontrading=False, 
                     xrotation=20, datetime_format="%d %b %H:%M")
            
            # Fix spines/ticks if mplfinance overwrites them
            self.ax.tick_params(axis='x', colors=TEXT_SECONDARY, labelsize=8)
            self.ax.tick_params(axis='y', colors=TEXT_SECONDARY, labelsize=8)
            for spine in self.ax.spines.values():
                spine.set_color(CARD_BORDER)

            # Apply custom limits if set (preserves manual zoom across refresh)
            if self._custom_xlim:
                self.ax.set_xlim(self._custom_xlim)
            if self._custom_ylim:
                self.ax.set_ylim(self._custom_ylim)

            # Get y_min, y_max to draw overlays correctly inside current view bounds
            y_min, y_max = self.ax.get_ylim()
            
            # Draw overlays
            self._draw_overlay_lines(y_min, y_max)
            
            self.fig.tight_layout(pad=0.2)
            self.canvas.draw_idle()
            
        except Exception as e:
            import traceback
            print(f"[DEBUG Candle] Exception in _draw_candles: {e}")
            traceback.print_exc()

    def update_lines(self, ask, bid, avg, mc, mc_label="MC"):
        self.current_ask = ask
        self.current_bid = bid
        self.current_avg = avg
        self.current_mc = mc
        self.current_mc_label = mc_label
        
        if not getattr(self, "candles", None) or len(self.candles) == 0:
            return
            
        y_min, y_max = self.ax.get_ylim()
        self._draw_overlay_lines(y_min, y_max)
        self.canvas.draw_idle()
        
    def _draw_overlay_lines(self, y_min, y_max):
        if getattr(self, 'overlay_artists', None):
            for artist in self.overlay_artists:
                try: artist.remove()
                except: pass
        self.overlay_artists = []

        # We need an x_max for text placement. In mpf, x-axis is integer index 0 to N-1
        chart_w = len(self.candles)
        
        if self.current_ask > 0:
            if y_min <= self.current_ask <= y_max:
                line = self.ax.axhline(self.current_ask, color=RED, linestyle="--", linewidth=1, alpha=0.5)
                self.overlay_artists.append(line)
            
        if self.current_bid > 0:
            if y_min <= self.current_bid <= y_max:
                line = self.ax.axhline(self.current_bid, color=BLUE, linestyle="--", linewidth=1, alpha=0.5)
                self.overlay_artists.append(line)
                
                # --- NEW: Current Price Label & Countdown Timer ---
                import time
                tf_str = getattr(self, 'tf_var', None)
                tf_str = tf_str.get() if tf_str else "M5"
                tf_secs = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}.get(tf_str, 60)
                rem = tf_secs - (int(time.time()) % tf_secs)
                countdown_str = f"{rem // 60:02d}:{rem % 60:02d}" if tf_secs < 86400 else ""
                
                trans = self.ax.get_yaxis_transform()
                # Draw Price Label on right edge
                txt1 = self.ax.text(1.0, self.current_bid, f" {self.current_bid:.2f} ", 
                             color='#ffffff', fontsize=9, fontweight='bold',
                             va='center', ha='left', transform=trans,
                             bbox=dict(facecolor='#0277bd', edgecolor='none', pad=2, alpha=0.9))
                self.overlay_artists.append(txt1)
                # Draw Countdown immediately below
                if countdown_str:
                    txt2 = self.ax.text(1.0, self.current_bid, f"\n\n {countdown_str} ", 
                                 color='#b0bec5', fontsize=8,
                                 va='center', ha='left', transform=trans)
                    self.overlay_artists.append(txt2)
                # ------------------------------------------------
        if self.current_avg and self.current_avg > 0:
            if self.current_avg > y_max:
                txt = self.ax.text(0.02, 0.95, f"▲ AVG: {self.current_avg:.2f} (jauh di atas)", transform=self.ax.transAxes,
                             color=YELLOW, fontsize=9, fontweight='bold', va='top')
                self.overlay_artists.append(txt)
            elif self.current_avg < y_min:
                txt = self.ax.text(0.02, 0.05, f"▼ AVG: {self.current_avg:.2f} (jauh di bawah)", transform=self.ax.transAxes,
                             color=YELLOW, fontsize=9, fontweight='bold', va='bottom')
                self.overlay_artists.append(txt)
            else:
                line = self.ax.axhline(self.current_avg, color=YELLOW, linestyle="--", linewidth=1.5)
                txt = self.ax.text(chart_w - 1, self.current_avg, f"AVG: {self.current_avg:.2f}", 
                             color=YELLOW, fontsize=8, fontweight='bold', va='bottom', ha='right',
                             bbox=dict(facecolor=BG_DARK, alpha=0.7, edgecolor='none', pad=1))
                self.overlay_artists.extend([line, txt])
                             
        if self.current_mc and self.current_mc > 0:
            if self.current_mc > y_max:
                txt = self.ax.text(0.02, 0.85, f"▲ {self.current_mc_label}: {self.current_mc:.2f} (jauh di atas)", transform=self.ax.transAxes,
                             color=RED, fontsize=9, fontweight='bold', va='top')
                self.overlay_artists.append(txt)
            elif self.current_mc < y_min:
                txt = self.ax.text(0.02, 0.15, f"▼ {self.current_mc_label}: {self.current_mc:.2f} (jauh di bawah)", transform=self.ax.transAxes,
                             color=RED, fontsize=9, fontweight='bold', va='bottom')
                self.overlay_artists.append(txt)
            else:
                line = self.ax.axhline(self.current_mc, color=RED, linestyle="-", linewidth=1.5)
                txt = self.ax.text(chart_w - 1, self.current_mc, f"{self.current_mc_label}: {self.current_mc:.2f}", 
                             color=RED, fontsize=8, fontweight='bold', va='bottom', ha='right',
                             bbox=dict(facecolor=BG_DARK, alpha=0.7, edgecolor='none', pad=1))
                self.overlay_artists.extend([line, txt])
