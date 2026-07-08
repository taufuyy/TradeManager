import customtkinter as ctk
import time
from mt5_manager import MT5Manager
import json
from candle_chart import CandleChart

with open('config.json') as f:
    cfg = json.load(f)

mgr = MT5Manager(cfg)

# Initialize CTk
app = ctk.CTk()

chart = CandleChart(app, mgr)

def test():
    # Wait to connect
    time.sleep(2)
    sym = mgr.get_state().get("symbol")
    print("Resolved symbol:", sym)
    
    candles = mgr.get_candles(sym, "M5", 60)
    print("Fetched candles len:", len(candles))
    
    chart.candles = candles
    chart.tf_var.set("M5")
    
    print("Calling _draw_candles()...")
    chart._draw_candles()
    print("Done calling _draw_candles()")
    
    app.destroy()

import threading
threading.Thread(target=mgr._poll_loop, daemon=True).start()
app.after(1000, test)
app.mainloop()
