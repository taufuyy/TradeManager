with open(r'd:\TradeManager\candle_chart.py', 'a') as f:
    f.write('''
    def update_lines(self, ask, bid, avg, mc, mc_label="MC"):
        if getattr(self, "candles", None) is None:
            return
            
        if not getattr(self, '_lines_initialized', False):
            self.line_ask = self.ax.axhline(ask, color=RED, linestyle="--", linewidth=1, alpha=0.5)
            self.line_bid = self.ax.axhline(bid, color=BLUE, linestyle="--", linewidth=1, alpha=0.5)
            if avg is not None and avg > 0:
                self.line_avg = self.ax.axhline(avg, color=YELLOW, linestyle="--", linewidth=1.5)
            else:
                self.line_avg = None
                
            if mc is not None and mc > 0:
                self.line_mc = self.ax.axhline(mc, color=RED, linestyle="-", linewidth=1.5)
            else:
                self.line_mc = None
                
            self._lines_initialized = True
        else:
            self.line_ask.set_ydata([ask, ask])
            self.line_bid.set_ydata([bid, bid])
            
            if avg is not None and avg > 0:
                if getattr(self, 'line_avg', None):
                    self.line_avg.set_ydata([avg, avg])
                else:
                    self.line_avg = self.ax.axhline(avg, color=YELLOW, linestyle="--", linewidth=1.5)
            elif getattr(self, 'line_avg', None):
                self.line_avg.remove()
                self.line_avg = None
                
            if mc is not None and mc > 0:
                if getattr(self, 'line_mc', None):
                    self.line_mc.set_ydata([mc, mc])
                else:
                    self.line_mc = self.ax.axhline(mc, color=RED, linestyle="-", linewidth=1.5)
            elif getattr(self, 'line_mc', None):
                self.line_mc.remove()
                self.line_mc = None
            
        self.canvas.draw_idle()
''')
print("OK")
