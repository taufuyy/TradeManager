import customtkinter as ctk
import time
from mt5_manager import MT5Manager
import json
from candle_chart import CandleChart
import datetime

with open('config.json') as f:
    cfg = json.load(f)

mgr = MT5Manager(cfg)
mgr.connect()

app = ctk.CTk()
chart = CandleChart(app, mgr)
chart.pack(fill='both', expand=True)

def test():
    # Force update to fetch live candles
    chart.update_candles(force=True)
    chart.update_lines(chart.current_ask, chart.current_bid, chart.current_avg, chart.current_mc)
    
    app.update()
    
    try:
        # Save matplotlib figure directly!
        chart.fig.savefig(r'C:\Users\Admin\.gemini\antigravity-ide\brain\3379a64f-8d1a-486c-adb8-81bf84f03411\chart_screenshot_live.png')
        print('Saved live chart figure')
    except Exception as e:
        print('Failed to save chart:', e)
        
    app.after(1000, app.destroy)

app.after(2000, test) # Wait a bit for connection
app.mainloop()
