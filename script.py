import MetaTrader5 as mt5
import time
from datetime import datetime

if mt5.initialize():
    local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(local_midnight, datetime.now())
    if deals:
        sessions = []
        current_session = []
        for d in deals:
            if d.entry == 1 and d.magic == 0 and d.type in (0, 1): # ENTRY_OUT
                current_session.append(d)
                
        groups = []
        if current_session:
            cur_group = [current_session[0]]
            for d in current_session[1:]:
                if d.time - cur_group[-1].time < 60:
                    cur_group.append(d)
                else:
                    groups.append(cur_group)
                    cur_group = [d]
            groups.append(cur_group)
            
        wins = 0; win_val = 0.0
        losses = 0; loss_val = 0.0
        for g in groups:
            net = sum(d.profit + d.commission + d.swap for d in g)
            if net > 0:
                wins += 1; win_val += net
            elif net < 0:
                losses += 1; loss_val += net
                
        print(f'cfg["acct_235080962_completed_sessions"] = {len(groups)}')
        print(f'cfg["acct_235080962_session_wins_count"] = {wins}')
        print(f'cfg["acct_235080962_session_losses_count"] = {losses}')
        print(f'cfg["acct_235080962_session_wins"] = {win_val}')
        print(f'cfg["acct_235080962_session_losses"] = {loss_val}')
        
        import json
        with open('d:/TradeManager/config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        cfg['acct_235080962_completed_sessions'] = len(groups)
        cfg['acct_235080962_session_wins_count'] = wins
        cfg['acct_235080962_session_losses_count'] = losses
        cfg['acct_235080962_session_wins'] = win_val
        cfg['acct_235080962_session_losses'] = loss_val

        with open('d:/TradeManager/config.json', 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
        print('Config restored based on history!')

    mt5.shutdown()
