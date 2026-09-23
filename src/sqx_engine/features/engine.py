import numpy as np
import pandas as pd

class FeatureCache(dict):
    """Immutable-for-a-run feature mapping shared by all strategies."""
    dataset_length: int = 0

class PredicateCache(dict):
    """Named cache for boolean predicate arrays; evaluator owns population."""
    pass

def prepare_features(data, grammar_version="legacy"):
    close=data.close.to_numpy(float); high=data.high.to_numpy(float); low=data.low.to_numpy(float); prev=np.r_[close[0],close[:-1]]
    tr=np.maximum(high-low,np.maximum(abs(high-prev),abs(low-prev))); out=FeatureCache({"close":close,"atr_14":pd.Series(tr).rolling(14,min_periods=14).mean().to_numpy()}); out.dataset_length=len(data)
    for p in (10,20,50,100): out[f"ema_{p}"]=pd.Series(close).ewm(span=p,adjust=False,min_periods=p).mean().to_numpy()
    d=pd.Series(close).diff(); gain=d.clip(lower=0).rolling(14,min_periods=14).mean(); loss=(-d.clip(upper=0)).rolling(14,min_periods=14).mean(); out["rsi_14"]=(100-100/(1+gain/loss)).to_numpy()
    up=pd.Series(high).diff(); down=-pd.Series(low).diff(); plus=up.where((up>down)&(up>0),0.0); minus=down.where((down>up)&(down>0),0.0); pm=plus.rolling(14).mean(); mm=minus.rolling(14).mean(); out["adx_14"]=(100*(pm-mm).abs()/(pm+mm)).replace([np.inf,-np.inf],np.nan).to_numpy()
    if grammar_version == "v1.7": add_grammar_features(data, out)
    elif grammar_version != "legacy": raise ValueError("Unknown feature grammar")
    return out


def confirmed_structure(high, low, close, depth):
    """Strict unique extrema; pivot p is published at p+d, never backfilled.

    LAST_STRUCTURE persists the most recent non-equal swing comparison. A dual
    high+low confirmation has no unique event ordering and publishes neutral 0;
    both swing prices still update. Breakouts use swings known BEFORE signal t.
    """
    high, low, close = (np.asarray(x, float) for x in (high, low, close))
    n = len(close); d = int(depth)
    if d < 1: raise ValueError('Fractal depth must be positive')
    fh, fl = np.full(n, np.nan), np.full(n, np.nan)
    # Rolling extrema of 2d+1 bars end at confirmation time, not pivot time.
    hp = pd.Series(high).shift(d)
    lp = pd.Series(low).shift(d)
    left_h = pd.Series(high).rolling(d).max().shift(d + 1)
    left_l = pd.Series(low).rolling(d).min().shift(d + 1)
    right_h = pd.Series(high).rolling(d).max()
    right_l = pd.Series(low).rolling(d).min()
    valid = np.arange(n) >= 2 * d
    fh[valid] = ((hp > left_h) & (hp > right_h)).to_numpy()[valid]
    fl[valid] = ((lp < left_l) & (lp < right_l)).to_numpy()[valid]
    state = np.full(n, np.nan); swing_high = np.full(n, np.nan); swing_low = np.full(n, np.nan)
    last_h = last_l = np.nan; last_state = 0.
    for t in range(n):
        swing_high[t], swing_low[t] = last_h, last_l
        if not valid[t]: continue
        h_event, l_event = fh[t] == 1, fl[t] == 1
        if h_event and l_event:
            last_state = 0.
        elif h_event and np.isfinite(last_h):
            if high[t-d] > last_h: last_state = 1.  # HH
            elif high[t-d] < last_h: last_state = 3.  # LH
        elif l_event and np.isfinite(last_l):
            if low[t-d] > last_l: last_state = 2.  # HL
            elif low[t-d] < last_l: last_state = 4.  # LL
        if h_event: last_h = high[t-d]
        if l_event: last_l = low[t-d]
        state[t] = last_state
    return {'last': state, 'fractal_high': fh, 'fractal_low': fl,
            'swing_high': swing_high, 'swing_low': swing_low,
            'break_high': close - swing_high, 'break_low': close - swing_low}


def add_grammar_features(data, out):
    """Causal V1.7 feature bank, constructed once per dataset/split."""
    from ..grammar import EMA_PERIODS, SLOPE_HORIZONS, BREAKOUT_PERIODS, ROC_PERIODS, WILLR_PERIODS, FRACTAL_DEPTHS
    close, high, low = (data[c].reset_index(drop=True).astype(float) for c in ('close', 'high', 'low'))
    prev = close.shift(1).fillna(close.iloc[0])
    tr = pd.Series(np.maximum(high-low, np.maximum(abs(high-prev), abs(low-prev))))
    emas = {n: close.ewm(span=n, adjust=False, min_periods=n).mean() for n in EMA_PERIODS}
    for n, ema in emas.items():
        out[f'trend.close_ema.{n}'] = (close - ema).to_numpy()
        for k in SLOPE_HORIZONS: out[f'trend.ema_slope.{n}.{k}'] = (ema - ema.shift(k)).to_numpy()
        for slow in EMA_PERIODS:
            if n < slow: out[f'trend.ema_pair.{n}.{slow}'] = (ema - emas[slow]).to_numpy()
    for n in BREAKOUT_PERIODS:
        out[f'trend.breakout_high.{n}'] = (close - high.rolling(n).max().shift(1)).to_numpy()
        out[f'trend.breakout_low.{n}'] = (close - low.rolling(n).min().shift(1)).to_numpy()
    for n in ROC_PERIODS: out[f'momentum.roc.{n}'] = (close / close.shift(n) - 1).to_numpy()
    for n in WILLR_PERIODS:
        hi, lo = high.rolling(n).max(), low.rolling(n).min()
        out[f'momentum.willr.{n}'] = (-100 * (hi-close) / (hi-lo).replace(0, np.nan)).to_numpy()
    for n in (14, 28):
        normalized = tr.rolling(n).mean() / close
        # Relative to a prior-only baseline, portable across price scales.
        out[f'volatility.atr_regime.{n}.50'] = (normalized / normalized.rolling(50).mean().shift(1) - 1).to_numpy()
    for n in (20, 50):
        mid, std = close.rolling(n).mean(), close.rolling(n).std(ddof=0)
        upper, lower = mid + 2 * std, mid - 2 * std
        kc_mid = close.ewm(span=n, adjust=False, min_periods=n).mean()
        atr = tr.rolling(n).mean()
        kc_upper, kc_lower = kc_mid + 1.5 * atr, kc_mid - 1.5 * atr
        for name, band in [('upper', upper), ('lower', lower), ('middle', mid)]:
            out[f'volatility.bb_{name}.{n}.2'] = (close - band).to_numpy()
        compression = np.full(len(data), np.nan)
        valid = (std.notna() & atr.notna()).to_numpy()
        inside = ((upper < kc_upper) & (lower > kc_lower)).to_numpy()
        outside = ((upper > kc_upper) & (lower < kc_lower)).to_numpy()
        compression[valid] = np.where(inside[valid], 1., np.where(outside[valid], -1., 0.))
        out[f'volatility.compression.{n}.2.1.5'] = compression
    for d in FRACTAL_DEPTHS:
        for name, values in confirmed_structure(high, low, close, d).items():
            out[f'structure.{name}.{d}'] = values
    return out
