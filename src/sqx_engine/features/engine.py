import numpy as np
import pandas as pd

class FeatureCache(dict):
    """Immutable-for-a-run feature mapping shared by all strategies."""
    dataset_length: int = 0

class PredicateCache(dict):
    """Named cache for boolean predicate arrays; evaluator owns population."""
    pass

def prepare_features(data):
    close=data.close.to_numpy(float); high=data.high.to_numpy(float); low=data.low.to_numpy(float); prev=np.r_[close[0],close[:-1]]
    tr=np.maximum(high-low,np.maximum(abs(high-prev),abs(low-prev))); out=FeatureCache({"close":close,"atr_14":pd.Series(tr).rolling(14,min_periods=14).mean().to_numpy()}); out.dataset_length=len(data)
    for p in (10,20,50,100): out[f"ema_{p}"]=pd.Series(close).ewm(span=p,adjust=False,min_periods=p).mean().to_numpy()
    d=pd.Series(close).diff(); gain=d.clip(lower=0).rolling(14,min_periods=14).mean(); loss=(-d.clip(upper=0)).rolling(14,min_periods=14).mean(); out["rsi_14"]=(100-100/(1+gain/loss)).to_numpy()
    up=pd.Series(high).diff(); down=-pd.Series(low).diff(); plus=up.where((up>down)&(up>0),0.0); minus=down.where((down>up)&(down>0),0.0); pm=plus.rolling(14).mean(); mm=minus.rolling(14).mean(); out["adx_14"]=(100*(pm-mm).abs()/(pm+mm)).replace([np.inf,-np.inf],np.nan).to_numpy()
    return out
