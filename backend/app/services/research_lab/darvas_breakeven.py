import pandas as pd
import numpy as np

def calculate_darvas_signals_breakeven(df: pd.DataFrame, sl_type='2close', vol_multiplier=5, be_trigger='none') -> pd.DataFrame:
    df = df.copy()
    if 'date' in df.columns:
        df = df.sort_values('date').reset_index(drop=True)
        
    if 'market_filter_ok' not in df.columns:
        df['market_filter_ok'] = True
    
    df['vol_sma_20'] = df['volume'].rolling(window=20).mean()
    df['high_252'] = df['high'].rolling(window=252).max()
    
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['prev_close']), abs(df['low'] - df['prev_close'])))
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    STATE_NO_BOX = 0
    STATE_SEEKING_BOTTOM = 1
    STATE_BOX_FORMED = 2
    
    state = STATE_NO_BOX
    box_top = np.nan
    box_bottom = np.nan
    active_stop_loss = np.nan 
    
    tops = []
    bottoms = []
    buy_signals = []
    sell_signals = []
    
    current_low = float('inf')
    days_since_low = 0
    
    consecutive_closes_below_bottom = 0
    
    # Portfolio tracking
    in_trade = False
    entry_price = np.nan
    breakeven_floor = -float('inf')
    
    for i in range(len(df)):
        buy = False
        sell = False
        
        if i < 252:
            tops.append(np.nan)
            bottoms.append(np.nan)
            buy_signals.append(False)
            sell_signals.append(False)
            continue
            
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        vol_sma = df['vol_sma_20'].iloc[i]
        market_ok = df['market_filter_ok'].iloc[i]
        atr = df['atr'].iloc[i]
        
        # 1. Box Top Logic
        high_3_ago = df['high'].iloc[i-3]
        if high_3_ago == df['high_252'].iloc[i-3] and not pd.isna(high_3_ago):
            if df['high'].iloc[i-2:i+1].max() < high_3_ago:
                if not pd.isna(box_bottom):
                    active_stop_loss = box_bottom
                    
                state = STATE_SEEKING_BOTTOM
                box_top = high_3_ago
                box_bottom = np.nan
                current_low = low
                days_since_low = 0
                consecutive_closes_below_bottom = 0
                
        # 2. Box Bottom Logic
        if state == STATE_SEEKING_BOTTOM:
            if low < current_low:
                current_low = low
                days_since_low = 0
            else:
                days_since_low += 1
                
            if days_since_low == 3:
                state = STATE_BOX_FORMED
                box_bottom = current_low
                active_stop_loss = current_low
                consecutive_closes_below_bottom = 0
                
                # BREAKEVEN RULE 1: New Box Formed
                if in_trade and be_trigger == 'new_box':
                    breakeven_floor = entry_price
                
        # 3. Buy Logic
        if state == STATE_BOX_FORMED:
            if close > box_top and vol > (vol_multiplier * vol_sma) and market_ok:
                buy = True
                if not in_trade:
                    in_trade = True
                    entry_price = close
                    breakeven_floor = -float('inf')
                consecutive_closes_below_bottom = 0
                
        # BREAKEVEN RULE 2: 10% Profit Hit
        if in_trade and be_trigger == 'profit_10':
            if close >= entry_price * 1.10:
                breakeven_floor = entry_price
                
        # 4. Sell Logic
        if in_trade:
            current_sl = -float('inf')
            
            if sl_type == 'atr' and not pd.isna(atr) and not pd.isna(box_top):
                current_sl = box_top - 2 * atr
            elif sl_type == '2close' and not pd.isna(active_stop_loss):
                current_sl = active_stop_loss
                
            effective_sl = max(current_sl, breakeven_floor)
            
            if sl_type == '2close':
                if close < effective_sl:
                    consecutive_closes_below_bottom += 1
                else:
                    consecutive_closes_below_bottom = 0
                    
                if consecutive_closes_below_bottom >= 2:
                    sell = True
            elif sl_type == 'atr':
                if close < effective_sl:
                    sell = True
            
            if sell:
                in_trade = False
                entry_price = np.nan
                breakeven_floor = -float('inf')
                state = STATE_NO_BOX
                box_top = np.nan
                box_bottom = np.nan
                active_stop_loss = np.nan
                consecutive_closes_below_bottom = 0
                
        tops.append(box_top)
        bottoms.append(box_bottom)
        buy_signals.append(buy)
        sell_signals.append(sell)
        
    df['box_top'] = tops
    df['box_bottom'] = bottoms
    df['buy_signal'] = buy_signals
    df['sell_signal'] = sell_signals
    
    return df
