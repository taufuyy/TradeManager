import MetaTrader5 as mt5
import time
from datetime import datetime
import json

if mt5.initialize():
    account_info = mt5.account_info()
    if account_info:
        login = account_info.login
        prefix = f"acct_{login}_"
        
        local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(local_midnight, datetime.now())
        
        wins = 0; win_val = 0.0
        losses = 0; loss_val = 0.0
        sessions_count = 0
        
        if deals:
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
                
            sessions_count = len(groups)
            for g in groups:
                net = sum(d.profit + d.commission + d.swap for d in g)
                if net > 0:
                    wins += 1; win_val += net
                elif net < 0:
                    losses += 1; loss_val += net
                    
        print(f"Restoring for account {login}...")
        print(f'SESSIONS: {sessions_count}')
        print(f'WINS: {wins} ({win_val})')
        print(f'LOSSES: {losses} ({loss_val})')
        
        try:
            with open('d:/TradeManager/config.json', 'r', encoding='utf-8') as f:
                cfg = json.load(f)

            cfg[prefix + 'completed_sessions'] = sessions_count
            cfg[prefix + 'session_wins_count'] = wins
            cfg[prefix + 'session_losses_count'] = losses
            cfg[prefix + 'session_wins'] = win_val
            cfg[prefix + 'session_losses'] = loss_val

            with open('d:/TradeManager/config.json', 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4)
            print('Config restored based on history!')
        except Exception as e:
            print(f"Error saving config: {e}")

    mt5.shutdown()
