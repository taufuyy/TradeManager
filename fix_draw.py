import os
with open(r'd:\TradeManager\candle_chart.py', 'r') as f:
    lines = f.readlines()

start = -1
for i, line in enumerate(lines):
    if line.startswith('    def _draw_candles('):
        start = i
        break

end = -1
for i in range(start + 1, len(lines)):
    if line.startswith('    def update_lines('):
        end = i - 1
        break

if end == -1:
    end = len(lines)

new_func = '''    def _draw_candles(self):
        try:
            self.ax.clear()
            
            if not self.candles:
                self.ax.set_facecolor(BG_DARK)
                for spine in self.ax.spines.values():
                    spine.set_color(CARD_BORDER)
                self.ax.text(0.5, 0.5, 'Tidak ada data candle untuk\\nsimbol/timeframe ini', 
                            horizontalalignment='center', verticalalignment='center',
                            transform=self.ax.transAxes, color=TEXT_SECONDARY, fontsize=10)
                self.ax.set_xticks([])
                self.ax.set_yticks([])
                self.canvas.draw_idle()
                return
                
            # Draw candles using bar and vlines
            indices = list(range(len(self.candles)))
            opens = [c["open"] for c in self.candles]
            closes = [c["close"] for c in self.candles]
            highs = [c["high"] for c in self.candles]
            lows = [c["low"] for c in self.candles]
            
            up = [c >= o for c, o in zip(closes, opens)]
            down = [not u for u in up]
            
            # Up candles
            up_idx = [i for i, u in enumerate(up) if u]
            if up_idx:
                self.ax.bar(up_idx, [closes[i]-opens[i] for i in up_idx], bottom=[opens[i] for i in up_idx], color=GREEN, width=0.6, align="center")
                self.ax.vlines(up_idx, [lows[i] for i in up_idx], [highs[i] for i in up_idx], color=GREEN, linewidth=1)
                
            # Down candles
            down_idx = [i for i, d in enumerate(down) if d]
            if down_idx:
                self.ax.bar(down_idx, [opens[i]-closes[i] for i in down_idx], bottom=[closes[i] for i in down_idx], color=RED, width=0.6, align="center")
                self.ax.vlines(down_idx, [lows[i] for i in down_idx], [highs[i] for i in down_idx], color=RED, linewidth=1)
                
            self.ax.set_facecolor(BG_DARK)
            self.ax.tick_params(axis='x', colors=TEXT_SECONDARY, labelsize=8)
            self.ax.tick_params(axis='y', colors=TEXT_SECONDARY, labelsize=8)
            for spine in self.ax.spines.values():
                spine.set_color(CARD_BORDER)
                
            self.ax.grid(axis="y", color=CARD_BORDER, linestyle=":", alpha=0.5)
            
            # Set explicit X and Y limits
            self.ax.set_xlim(-1, len(self.candles))
            min_low = min(lows)
            max_high = max(highs)
            
            # Give 10% padding
            pad = (max_high - min_low) * 0.1
            if pad == 0: pad = 1.0
            
            self.ax.set_ylim(min_low - pad, max_high + pad)
            
            self.fig.tight_layout(pad=0.2)
            
            self._lines_initialized = False # force redraw lines
            self.canvas.draw_idle()
            
            print(f"[DEBUG Candle] Rendered {len(self.candles)} candles. Y-Lim: {min_low - pad:.2f} to {max_high + pad:.2f}")
        except Exception as e:
            import traceback
            print(f"[DEBUG Candle] Exception in _draw_candles: {e}")
            traceback.print_exc()
'''

lines = lines[:start] + [new_func] + lines[end+1:]
with open(r'd:\TradeManager\candle_chart.py', 'w') as f:
    f.writelines(lines)
print('OK')
