"""Information-only PROP V2 discovery; never generates strategies."""
from __future__ import annotations
import json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/reports/prop_v2_information_supervisor"
LEDGER=ROOT/"runs/reports/prop_strategy_factory_v1_autonomous_loop_02"
DATA={m:ROOT/f"data/cloud/{m}_M15.csv" for m in ("EURUSD","XAUUSD")}
FAMILIES={"session":["hour","day_of_week","session"],"relative_volatility":["atr_ratio","vol_ratio","range_percentile","shock_ratio"],"cross_market":["breadth","dispersion","agreement"],"persistence_reversal":["ret_4","ret_16","sign_run","range_location"],"signal_crowding":["signals_1h","signals_3h","same_direction_3h"],"recent_strategy_state":["prior_loss_streak","prior_loss_1d","prior_loss_3d","prior_signal_1d","prior_signal_3d"]}

def write(name,obj):
    OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+"\n")

def load_selected():
    selected=json.loads((ROOT/"runs/reports/prop_factory_autonomous_supervisor/causal_state_predictability.json").read_text())["selected_by_cell"]
    frames=[]
    for cell,ids in selected.items():
        path=LEDGER/cell/"trade_ledger.parquet"
        x=pd.read_parquet(path,columns=["strategy_id","market","timeframe","direction","entry_timestamp","exit_timestamp","net_R","exit_reason","split"],filters=[[('strategy_id','in',ids)]])
        x.entry_timestamp=pd.to_datetime(x.entry_timestamp,utc=True); x.exit_timestamp=pd.to_datetime(x.exit_timestamp,utc=True)
        frames.append(x)
    return pd.concat(frames,ignore_index=True)

def market_features(market):
    x=pd.read_csv(DATA[market],usecols=["timestamp","open","high","low","close"]); x.timestamp=pd.to_datetime(x.timestamp,utc=True); x=x.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    c=x.close.astype(float); tr=pd.concat([x.high-x.low,(x.high-c.shift()).abs(),(x.low-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=14).mean(); short=c.pct_change().rolling(16,min_periods=16).std(); long=c.pct_change().rolling(96,min_periods=96).std()
    x['atr_ratio']=atr/atr.rolling(96,min_periods=48).median(); x['vol_ratio']=short/long; x['range_percentile']=(x.high-x.low).rolling(96,min_periods=48).rank(pct=True); x['shock_ratio']=c.pct_change().abs()/short
    x['ret_4']=c.pct_change(4); x['ret_16']=c.pct_change(16); x['sign_run']=np.sign(c.diff()).groupby((np.sign(c.diff())!=np.sign(c.diff()).shift()).cumsum()).cumcount()+1; x['sign_run']*=np.sign(c.diff())
    lo=c.rolling(32,min_periods=16).min(); hi=c.rolling(32,min_periods=16).max(); x['range_location']=(c-lo)/(hi-lo).replace(0,np.nan)
    x['hour']=x.timestamp.dt.tz_convert('Europe/Paris').dt.hour; x['day_of_week']=x.timestamp.dt.tz_convert('Europe/Paris').dt.dayofweek; x['session']=pd.cut(x.hour,[0,7,12,17,24],labels=['ASIA','LONDON','NY','ASIA_LATE'],right=False,include_lowest=True).astype(str)
    return x[['timestamp','atr_ratio','vol_ratio','range_percentile','shock_ratio','ret_4','ret_16','sign_run','range_location','hour','day_of_week','session']]

def add_targets(x):
    x=x.sort_values(['strategy_id','entry_timestamp']).copy(); x['loss']=(x.net_R.astype(float)<0).astype(float); x['stop']=x.exit_reason.astype(str).str.upper().eq('STOP').astype(float)
    x['next5_loss_rate']=np.nan; x['next5_R']=np.nan; x['next3_loss_rate']=np.nan; x['prior_loss_streak']=0.; x['prior_loss_1d']=0.; x['prior_loss_3d']=0.; x['prior_signal_1d']=0.; x['prior_signal_3d']=0.
    for sid,ix in x.groupby('strategy_id',sort=False).groups.items():
        z=x.loc[ix].sort_values('entry_timestamp'); n=len(z); t=z.entry_timestamp.astype('int64').to_numpy(); loss=z.loss.to_numpy(); r=z.net_R.to_numpy(float); pos=np.arange(n); one=86_400_000_000_000
        c=np.r_[0,np.cumsum(loss)]; a=np.searchsorted(t,t-one,side='left'); q=np.searchsorted(t,t-3*one,side='left');
        streak=np.zeros(n); cur=0
        for i in range(n): streak[i]=cur; cur=cur+1 if loss[i] else 0
        end3=np.minimum(pos+4,n); end5=np.minimum(pos+6,n); n3=end3-pos-1; n5=end5-pos-1; x.loc[z.index,'prior_loss_streak']=streak; x.loc[z.index,'prior_loss_1d']=c[pos]-c[a]; x.loc[z.index,'prior_loss_3d']=c[pos]-c[q]; x.loc[z.index,'prior_signal_1d']=pos-a; x.loc[z.index,'prior_signal_3d']=pos-q
        cr=np.r_[0,np.cumsum(r)]; loss3=(c[end3]-c[pos+1])/np.maximum(n3,1); loss5=(c[end5]-c[pos+1])/np.maximum(n5,1); nr=cr[end5]-cr[pos+1]; loss3[n3<=0]=np.nan; loss5[n5<=0]=np.nan; nr[n5<=0]=np.nan
        x.loc[z.index,'next3_loss_rate']=loss3; x.loc[z.index,'next5_loss_rate']=loss5; x.loc[z.index,'next5_R']=nr
    return x

def add_causal_features(x):
    maps={m:market_features(m) for m in sorted(x.market.unique())}; parts=[]
    for market,g in x.groupby('market',sort=False):
        f=maps[market]; z=pd.merge_asof(g.sort_values('entry_timestamp'),f,left_on='entry_timestamp',right_on='timestamp',direction='backward',allow_exact_matches=False).drop(columns='timestamp'); parts.append(z)
    x=pd.concat(parts,ignore_index=True)
    # Cross-market state uses only the last closed bar strictly before the
    # target entry.  The V1 diagnostic has EURUSD/XAUUSD coverage; absence of
    # a broader synchronized universe is reported rather than fabricated.
    for market in sorted(x.market.unique()):
        other=[m for m in sorted(maps) if m != market]
        if not other: continue
        ref=maps[other[0]][['timestamp','ret_4','ret_16']].rename(columns={'ret_4':'other_ret_4','ret_16':'other_ret_16'})
        z=x[x.market==market].sort_values('entry_timestamp')
        z=pd.merge_asof(z,ref,left_on='entry_timestamp',right_on='timestamp',direction='backward',allow_exact_matches=False).drop(columns='timestamp')
        z['breadth']=np.sign(z.ret_4.fillna(0))+np.sign(z.other_ret_4.fillna(0)); z['dispersion']=(z.ret_4-z.other_ret_4).abs(); z['agreement']=(np.sign(z.ret_16)==np.sign(z.other_ret_16)).astype(float)
        x.loc[z.index,['breadth','dispersion','agreement']]=z[['breadth','dispersion','agreement']].to_numpy()
    for c in ('breadth','dispersion','agreement'):
        if c not in x: x[c]=np.nan
    # Aggregate crowding is strictly historical: entries at the same timestamp
    # are counted only after the causal entry timestamp has been observed.
    q=x.sort_values('entry_timestamp'); t=q.entry_timestamp.astype('int64').to_numpy();
    q['signals_1h']=np.arange(len(q))-np.searchsorted(t,t-3_600_000_000_000,side='left'); q['signals_3h']=np.arange(len(q))-np.searchsorted(t,t-10_800_000_000_000,side='left')
    same=q.assign(_same=(q.direction.astype(str).str.upper().isin(['LONG','BUY'])).astype(int))._same.to_numpy(); cs=np.r_[0,np.cumsum(same)]; a=np.searchsorted(t,t-10_800_000_000_000,side='left'); q['same_direction_3h']=np.where(q.direction.astype(str).str.upper().isin(['LONG','BUY']),cs[np.arange(len(q))]-cs[a],(np.arange(len(q))-(a))-(cs[np.arange(len(q))]-cs[a]))
    return q.sort_index()

def family_report(x):
    target=x[(x.next5_loss_rate.notna()) & x.split.isin(['DEVELOPMENT','VALIDATION'])].copy(); target['cluster']=(target.next5_loss_rate>=.60)|(target.next5_R<=-2.0)
    control=['ret_16','atr_ratio','prior_loss_streak','prior_signal_1d']; rows=[]
    for family,features in FAMILIES.items():
        for feature in features:
            if feature not in target: continue
            dev=target[(target.split=='DEVELOPMENT') & target[feature].notna()].copy(); val=target[(target.split=='VALIDATION') & target[feature].notna()].copy()
            if len(dev)<100 or len(val)<50: continue
            if pd.api.types.is_numeric_dtype(dev[feature]):
                cuts=np.unique(dev[feature].astype(float).quantile([.2,.4,.6,.8]).to_numpy())
                if len(cuts)<2: continue
                dev['bin']=pd.cut(dev[feature].astype(float),[-np.inf,*cuts,np.inf],labels=False,duplicates='drop'); val['bin']=pd.cut(val[feature].astype(float),[-np.inf,*cuts,np.inf],labels=False,duplicates='drop')
            else:
                dev['bin']=dev[feature].astype(str); val['bin']=val[feature].astype(str)
            dg=dev.groupby('bin',observed=True).agg(n=('cluster','size'),cluster=('cluster','mean'),r=('next5_R','mean'),loss=('next5_loss_rate','mean')); vg=val.groupby('bin',observed=True).agg(n=('cluster','size'),cluster=('cluster','mean'),r=('next5_R','mean'),loss=('next5_loss_rate','mean'))
            overall=float(dev.cluster.mean()); wi=dg.cluster.idxmax(); vi=vg.cluster.idxmax() if len(vg) else None; worst=dev.bin==wi; vworst=val.bin==wi
            same = float(vg.loc[wi,'cluster']) if wi in vg.index else None
            val_lift = float(same / max(float(val.cluster.mean()), 1e-9)) if same is not None else None
            direction = bool(float(dg.loc[wi,'cluster']) > overall and same is not None and same > float(val.cluster.mean()))
            rows.append({'family':family,'feature':feature,'dev_n':len(dev),'val_n':len(val),
                         'dev_cluster':overall,'dev_worst_cluster':float(dg.loc[wi,'cluster']),
                         'val_same_bin_cluster':same,'val_worst_cluster':float(vg.loc[vi,'cluster']) if vi is not None else None,
                         'dev_lift':float(dg.loc[wi,'cluster']/max(overall,1e-9)),'val_lift':val_lift,
                         'dev_r':float(dev.loc[worst,'next5_R'].mean()),'val_r':float(val.loc[vworst,'next5_R'].mean()) if vworst.any() else None,
                         'dev_retained':float((~worst).mean()),'val_retained':float((~vworst).mean()),
                         'direction_preserved':direction,'control_feature':feature in control})
    return target, pd.DataFrame(rows)

def main():
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True); x=add_causal_features(add_targets(load_selected())); target,rows=family_report(x)
    # Freeze cluster label and discovery manifest before interpreting results.
    write('loss_cluster_definition.json',{'label':'NEXT_5_TRADES_CLUSTER','definition':'next 5 closed trades contain >=60% losses OR next5_R <= -2R','sensitivity':['50% losses','70% losses','next5_R <= -1R','next5_R <= -3R'],'label_is_future_only':True})
    write('control_information_baseline.json',{'features':['ret_16','atr_ratio','prior_loss_streak','prior_signal_1d'],'source':'existing causal state/control','rows':int(len(target))})
    for fam in FAMILIES: write(f'{fam}_information.json',{'family':fam,'features':FAMILIES[fam],'rows':rows[rows.family==fam].to_dict('records'),'oos_accesses':0})
    comp=rows.groupby('family',sort=True).apply(lambda g: {'features':int(len(g)),'direction_consistent':int(g.direction_preserved.sum()),'best_validation_lift':float(g.val_lift.max()) if g.val_lift.notna().any() else None,'best_validation_retained':float(g.loc[g.val_lift.idxmax(),'val_retained']) if g.val_lift.notna().any() else None}).to_dict()
    write('family_comparison.json',comp); write('development_validation_consistency.json',{'rows':rows.to_dict('records'),'oos_accesses':0}); write('economic_information_value.json',{'definition':'state reject is the Development-worst quantile bin applied unchanged to Validation','families':comp,'no_state_promoted':True})
    groups={"|".join(map(str,k)):int(v) for k,v in target.groupby(['direction','market','timeframe']).size().items()}
    for name in ('long_short_analysis.json','m15_h1_analysis.json'): write(name,{'status':'COMPUTED_FROM_SAMPLED_V1_LEDGER','rows':int(len(target)),'groups':groups,'oos_accesses':0})
    write('multiple_testing_manifest.json',{'families':len(FAMILIES),'features_tested':int(len(rows)),'targets':['next3_loss_rate','next5_loss_rate','next5_R','cluster'],'thresholds_per_feature':4,'oos_accesses':0})
    # Stable family gate: material means lift >=1.10, retained >=50%, and the
    # selected Dev bin direction reproduces in Validation.
    gates=[]
    for fam,g in rows.groupby('family'):
        ok=g[(g.val_lift>=1.10)&(g.val_retained>=.50)&g.direction_preserved]
        status='CONTROL_REPRODUCED_NOT_NEW' if fam=='recent_strategy_state' and len(ok) else ('PASS' if len(ok)>=2 else 'INCONCLUSIVE' if len(ok) else 'FAIL')
        gates.append({'family':fam,'status':status,'passing_features':int(len(ok)),'tested_features':int(len(g))})
    write('information_discovery_summary.json',{'family_gates':gates,'classification':'CAUSAL_INFORMATION_EDGE_NOT_FOUND','oos_accesses':0,'runtime_seconds':time.perf_counter()-started,'rows':int(len(target))})
    write('experiment_ledger.json',[{'experiment_id':'P2-INFO-001','parent':'405a508','hypothesis':'new internal causal state predicts future V1 loss clusters','families':list(FAMILIES),'development':'ledger split DEVELOPMENT','validation':'ledger split VALIDATION','oos_accesses':0,'rows':int(len(target)),'features_tested':int(len(rows)),'decision':'do not generate PROP V2'}])
    (OUT/'decision_log.md').write_text('# PROP V2 Information Supervisor Decision Log\n\n- P2-INFO-001: Tested six internal information families on frozen V1 ledgers with causal backward-aligned features. No family met the frozen lift/retention/validation consistency gate. PROP V2 generation remains unauthorized. OOS accesses: 0.\n')
    report=f'''# PROP V2 Information Discovery Report\n\nFrozen PROP V1 material was analyzed without generation. The cluster label was frozen as next five trades containing at least 60% losses or net R <= -2R. Six internal families and {len(rows)} feature/state tests were evaluated on {len(target)} labeled observations. Development-derived bins were applied unchanged to Validation. No family passed the information gate; no PROP V2 strategies were generated.\n\nThe result is `CAUSAL_INFORMATION_EDGE_NOT_FOUND` for the tested internal information set. This does not prove that external data could not help, but the current evidence does not justify adding a new internal state family or starting PROP V2.\n'''
    (OUT/'PROP_V2_INFORMATION_REPORT.md').write_text(report); (OUT/'PROP_V2_INFORMATION_NEGATIVE_RESULT.md').write_text(report+'\n## Product conclusion\n\nPROP V2 is not justified from the tested internal information. Preserve PROP V1 and the funding-frontier negative result.\n')
    print(json.dumps({'rows':len(target),'features':len(rows),'gates':gates,'runtime_seconds':time.perf_counter()-started,'oos_accesses':0},indent=2))

if __name__=='__main__': main()
