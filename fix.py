import os
with open(r'd:\TradeManager\mt5_manager.py', 'r') as f:
    lines = f.readlines()
    
start = -1
for i, line in enumerate(lines):
    if line.startswith('    def get_candles('):
        start = i
        break

if start != -1:
    lines = lines[:start]

lines.append('''    def get_candles(self, symbol: str, timeframe_str: str, count: int = 100) -> list[dict]:
        with self._lock:
            if not getattr(self, 'mt5', None):
                return []
                
        tf_map = {
            'M1': self.mt5.TIMEFRAME_M1,
            'M5': self.mt5.TIMEFRAME_M5,
            'M15': self.mt5.TIMEFRAME_M15,
            'M30': self.mt5.TIMEFRAME_M30,
            'H1': self.mt5.TIMEFRAME_H1,
            'H4': self.mt5.TIMEFRAME_H4,
            'D1': self.mt5.TIMEFRAME_D1,
            'W1': self.mt5.TIMEFRAME_W1,
            'MN1': self.mt5.TIMEFRAME_MN1
        }
        tf = tf_map.get(timeframe_str, self.mt5.TIMEFRAME_M5)
        
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 0, count)
        print(f"[DEBUG Candle] Fetched {symbol} TF={timeframe_str} ({tf}) Count={count}. Result type: {type(rates)}")
        if rates is None or len(rates) == 0:
            err = self.mt5.last_error()
            print(f"[DEBUG Candle] Failed or empty! mt5.last_error() = {err}")
            return []
            
        print(f"[DEBUG Candle] Successfully fetched {len(rates)} candles.")
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
''')

with open(r'd:\TradeManager\mt5_manager.py', 'w') as f:
    f.writelines(lines)
print('OK')
