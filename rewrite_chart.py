import time
import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
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
        
        # We need a reference to the update callback to cancel it if needed
        self._after_id = None
        self._auto_update()

    def _auto_update(self):
        """Periodically fetch candles every 5 seconds."""
        self.update_candles()
        self._after_id = self.after(5000, self._auto_update)

    def destroy(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        super().destroy()

    def _on_tf_change(self, val):
        self._last_fetch = 0
        self.update_candles()

    def update_candles(self, force=False):
        now = time.time()
        if not force and now - self._last_fetch < 5.0:
            return
            
        self._last_fetch = now
        
        if not getattr(self.mt5, 'connected', False):
            return
            
        symbol = self.mt5.get_state().get("symbol")
        if not symbol:
            return
            
        self.candles = self.mt5.get_candles(symbol, self.tf_var.get(), 60)
        self._draw_candles()
        
    def _draw_candles(self):
        try:
            self.ax.clear()
            
            # Reset lines to force recreation on next update_lines call
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
                
            lows = []
            highs = []
            
            # Draw candles using mpatches.Rectangle and Line2D
            for i, candle in enumerate(self.candles):
                o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
                lows.append(l)
                highs.append(h)
                
                color = GREEN if c >= o else RED
                
                # Wick (garis tipis high-low)
                self.ax.add_line(Line2D([i, i], [l, h], color=color, linewidth=1))
                
                # Body (kotak open-close)
                body_bottom = min(o, c)
                body_height = abs(c - o)
                if body_height == 0:
                    body_height = (h - l) * 0.001
                    if body_height == 0:
                        body_height = 0.01
                        
                rect = mpatches.Rectangle((i - 0.3, body_bottom), 0.6, body_height, 
                                            facecolor=color, edgecolor=color)
                self.ax.add_patch(rect)
                
            self.ax.set_facecolor(BG_DARK)
            self.ax.tick_params(axis='x', colors=TEXT_SECONDARY, labelsize=8)
            self.ax.tick_params(axis='y', colors=TEXT_SECONDARY, labelsize=8)
            for spine in self.ax.spines.values():
                spine.set_color(CARD_BORDER)
                
            # Grid halus
            self.ax.grid(axis="y", color=CARD_BORDER, linestyle=":", alpha=0.5)
            self.ax.grid(axis="x", color=CARD_BORDER, linestyle=":", alpha=0.3)
            
            # Skala Y HANYA berdasarkan candle (min(low) max(high))
            min_low = min(lows)
            max_high = max(highs)
            
            pad = (max_high - min_low) * 0.1
            if pad == 0: pad = 1.0
            
            self.ax.set_ylim(min_low - pad, max_high + pad)
            self.ax.set_xlim(-1, len(self.candles))
            
            # Format label waktu di Sumbu X
            tf_str = self.tf_var.get()
            date_format = "%H:%M" if tf_str in ["M1", "M5", "M15", "M30"] else "%d %b %H:%M"
            if tf_str in ["D1", "W1", "MN1"]:
                date_format = "%d %b"
                
            step = max(1, len(self.candles) // 6)
            xticks = []
            xticklabels = []
            for i in range(0, len(self.candles), step):
                xticks.append(i)
                dt = datetime.fromtimestamp(self.candles[i]['time'])
                xticklabels.append(dt.strftime(date_format))
                
            self.ax.set_xticks(xticks)
            self.ax.set_xticklabels(xticklabels, rotation=20, ha='right')
            
            self.fig.tight_layout(pad=0.2)
            self.canvas.draw_idle()
            
            print(f"[DEBUG Candle] Rendered {len(self.candles)} candles. Y-Lim: {min_low-pad:.2f} to {max_high+pad:.2f}. TF: {tf_str}")
        except Exception as e:
            import traceback
            print(f"[DEBUG Candle] Exception in _draw_candles: {e}")
            traceback.print_exc()

    def update_lines(self, ask, bid, avg, mc, mc_label="MC"):
        if getattr(self, "candles", None) is None or len(self.candles) == 0:
            return
            
        y_min, y_max = self.ax.get_ylim()
        
        # Helper for axhline
        def update_hz_line(line_obj, val, color, style, width):
            if val is None or val <= 0:
                if line_obj: line_obj.set_visible(False)
                return line_obj
            
            if line_obj is None:
                line_obj = self.ax.axhline(val, color=color, linestyle=style, linewidth=width)
            
            if y_min <= val <= y_max:
                line_obj.set_ydata([val, val])
                line_obj.set_visible(True)
            else:
                line_obj.set_visible(False)
            return line_obj

        self.line_ask = update_hz_line(getattr(self, 'line_ask', None), ask, RED, "--", 1)
        self.line_bid = update_hz_line(getattr(self, 'line_bid', None), bid, BLUE, "--", 1)
        
        # Helper for out-of-bounds text + inside line
        def update_indicator(val, line_obj, text_obj, label, color, style, width, y_pos_top, y_pos_bottom):
            if val is None or val <= 0:
                if line_obj: line_obj.set_visible(False)
                if text_obj: text_obj.set_visible(False)
                return line_obj, text_obj
                
            if line_obj is None:
                line_obj = self.ax.axhline(val, color=color, linestyle=style, linewidth=width)
            if text_obj is None:
                text_obj = self.ax.text(0.02, 0.5, "", transform=self.ax.transAxes,
                                        color=color, fontsize=9, fontweight='bold')
                                        
            if val > y_max:
                line_obj.set_visible(False)
                text_obj.set_text(f"▲ {label}: {val:.2f} (jauh di atas)")
                text_obj.set_y(y_pos_top)
                text_obj.set_va('top')
                text_obj.set_visible(True)
            elif val < y_min:
                line_obj.set_visible(False)
                text_obj.set_text(f"▼ {label}: {val:.2f} (jauh di bawah)")
                text_obj.set_y(y_pos_bottom)
                text_obj.set_va('bottom')
                text_obj.set_visible(True)
            else:
                line_obj.set_ydata([val, val])
                line_obj.set_visible(True)
                text_obj.set_visible(False)
                
            return line_obj, text_obj

        self.line_avg, self.text_avg = update_indicator(
            avg, getattr(self, 'line_avg', None), getattr(self, 'text_avg', None), 
            "AVG", YELLOW, "--", 1.5, 0.95, 0.05
        )
        
        self.line_mc, self.text_mc = update_indicator(
            mc, getattr(self, 'line_mc', None), getattr(self, 'text_mc', None), 
            mc_label, RED, "-", 1.5, 0.85, 0.15
        )

        self.canvas.draw_idle()
