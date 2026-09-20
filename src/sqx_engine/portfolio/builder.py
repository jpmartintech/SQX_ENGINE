import numpy as np

class PortfolioBuilder:
    def __init__(self, max_strategies=10, max_correlation=.70): self.max_strategies=max_strategies; self.max_correlation=max_correlation
    def build(self, items):
        selected=[]
        for item in sorted(items,key=lambda x:x.get("funnel",{}).get("quality_score", x["result"].expectancy_r),reverse=True):
            if len(selected)>=self.max_strategies: break
            x=np.asarray(item["result"].trade_returns,float); ok=True
            for old in selected:
                y=np.asarray(old["result"].trade_returns,float); n=max(len(x),len(y)); a=np.pad(x,(0,n-len(x))); b=np.pad(y,(0,n-len(y)))
                corr=0.0 if n < 2 or np.std(a)==0 or np.std(b)==0 else float(np.corrcoef(a,b)[0,1])
                if abs(corr)>self.max_correlation: ok=False; break
            if ok: selected.append(item)
        correlations=[]
        for i, old in enumerate(selected):
            for new in selected[i+1:]:
                x=np.asarray(old["result"].trade_returns,float); y=np.asarray(new["result"].trade_returns,float); n=max(len(x),len(y)); x=np.pad(x,(0,n-len(x))); y=np.pad(y,(0,n-len(y)))
                if n > 1 and np.std(x) and np.std(y): correlations.append(abs(float(np.corrcoef(x,y)[0,1])))
        combined = np.mean([np.asarray(x["result"].equity_curve, float) / x["result"].equity_curve[0] - 1 for x in selected], axis=0) if selected and all(x["result"].equity_curve for x in selected) else np.array([])
        if len(combined):
            peak = np.maximum.accumulate(combined); combined_dd = float(np.max(peak - combined)); combined_return = float(combined[-1]);
            changes = np.diff(combined, prepend=0.0); combined_sharpe = float(changes.mean() / changes.std() * np.sqrt(252)) if changes.std() else 0.0
        else:
            combined_return = combined_dd = combined_sharpe = 0.0
        return {"strategies":selected,"weights":{x["result"].strategy_id:1/max(1,len(selected)) for x in selected},"average_correlation":float(np.mean(correlations)) if correlations else 0.0,"max_correlation":max(correlations,default=0.0),"combined_return":combined_return,"combined_sharpe":combined_sharpe,"combined_max_drawdown":combined_dd}
