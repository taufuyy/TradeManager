import customtkinter as ctk
import time
from mt5_manager import MT5Manager
import json
from candle_chart import CandleChart
import datetime

with open('config.json') as f:
    cfg = json.load(f)

mgr = MT5Manager(cfg)

app = ctk.CTk()
chart = CandleChart(app, mgr)

def test():
    # Mock candles
    now = time.time()
    mock_candles = []
    for i in range(60):
        mock_candles.append({
            "time": now - (60 - i) * 300,
            "open": 4120 + i,
            "high": 4125 + i,
            "low": 4115 + i,
            "close": 4122 + i
        })
    chart.candles = mock_candles
    print("Calling _draw_candles()...")
    chart._draw_candles()
    print("Done _draw_candles()")
    app.destroy()

app.after(100, test)
app.mainloop()
