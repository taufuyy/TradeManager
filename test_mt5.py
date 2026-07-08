import MetaTrader5 as mt5

if not mt5.initialize():
    print('Failed to initialize MT5')
else:
    # Try XAUUSD
    rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M5, 0, 60)
    if rates is None or len(rates) == 0:
        rates = mt5.copy_rates_from_pos('XAUUSDc', mt5.TIMEFRAME_M5, 0, 60)
        
    if rates is None or len(rates) == 0:
        print('Failed to fetch candles. Error:', mt5.last_error())
    else:
        print(f'Successfully fetched {len(rates)} candles.')
        lows = [r['low'] for r in rates]
        highs = [r['high'] for r in rates]
        min_low = min(lows)
        max_high = max(highs)
        pad = (max_high - min_low) * 0.1
        if pad == 0: pad = 1.0
        print(f'Y-Lim range: {min_low - pad:.2f} to {max_high + pad:.2f}')
        print(f'Sample candle close: {rates[-1]["close"]}')
