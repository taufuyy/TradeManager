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
chart.pack(fill="both", expand=True)

def test():
    now = time.time()
    mock_candles = []
    for i in range(60):
        mock_candles.append({
            'time': now - (60 - i) * 300,
            'open': 4120 + i,
            'high': 4125 + i,
            'low': 4115 + i,
            'close': 4122 + i
        })
    chart.candles = mock_candles
    chart.update_lines(4125, 4124, 4120, 3600)
    
    # Save a screenshot of the frame
    app.update()
    
    import os
    try:
        from PIL import ImageGrab
        import win32gui
        
        # Get window rect
        hwnd = app.winfo_id()
        # in tkinter, winfo_id on windows might be the handle
        x0 = app.winfo_rootx()
        y0 = app.winfo_rooty()
        w = app.winfo_width()
        h = app.winfo_height()
        
        img = ImageGrab.grab((x0, y0, x0+w, y0+h))
        img.save(r"C:\Users\Admin\.gemini\antigravity-ide\brain\3379a64f-8d1a-486c-adb8-81bf84f03411\chart_mockup.png")
        print("Saved screenshot")
    except Exception as e:
        print("Failed to save screenshot:", e)
        
    app.after(1000, app.destroy)

app.after(500, test)
app.mainloop()
