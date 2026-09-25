import csv,json,pickle,time,resource
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; O=ROOT/'runs/reports/portfolio_factory_v1/risk_reconstruction'; RISKS=(.0025,.005,.0075,.01,.0125,.015,.02); H=(30,60,90,180,None)
rows=list(csv.DictReader(open(ROOT/'runs/reports/portfolio_factory_v1/pilot_results.csv'))); streams=pickle.load(open(O/'r_streams.pkl','rb')); ids=sorted(streams); T=sorted({t for d in streams.values() for t in d}); ti={t:i for i,t in enumerate(T)}; R=np.zeros((len(ids),len(T)))
for i,s in enumerate(ids):
 for t,v in streams[s].items():R[i,ti[t]]=float(v)
W=np.zeros((len(rows),len(ids))); idx={s:i for i,s in enumerate(ids)}
for j,r in enumerate(rows):
 for s,v in json.loads(r['weights_json']).items():W[j,idx[s]]=float(v)
S=W@R
D=np.array([str(t)[:10] for t in T]); ud=np.unique(D); di={d:i for i,d in enumerate(ud)}; B=np.zeros((len(T),len(ud)))
for i,d in enumerate(D):B[i,di[d]]=1
starts=np.array([di[str(T[np.flatnonzero(x)[0]])[:10]] if np.any(x) else 0 for x in S]); orddays=np.array([pd.Timestamp(str(d)).toordinal() for d in ud])
front=[];start=time.time()
for h in H:
 cutoff=np.array([orddays[s]+h-1 if h is not None else 10**9 for s in starts]); valid=np.array([orddays<=cutoff[j] for j in range(len(rows))])
 for risk in RISKS:
  daily=(S*(risk/.01))@B; cum=np.cumsum(daily,axis=1); counts=dict.fromkeys(['PASS','FAIL_DAILY','FAIL_TOTAL','TIMEOUT','DATA_END'],0)
  for j in range(len(rows)):
   x=cum[j,valid[j]];y=daily[j,valid[j]]
   # explicit horizon/data-end distinction
   st='TIMEOUT' if h is not None and ud[-1] and orddays[-1]>=cutoff[j] else 'DATA_END'
   db=np.flatnonzero(y<-.05);tb=np.flatnonzero(x<-.10);pb=np.flatnonzero((x>=.10)&(np.arange(len(x))>=3));ev=[]
   if len(db):ev.append((db[0],'FAIL_DAILY'))
   if len(tb):ev.append((tb[0],'FAIL_TOTAL'))
   if len(pb):ev.append((pb[0],'PASS'))
   if ev:st=min(ev,key=lambda z:z[0])[1]
   counts[st]+=1
  front.append({'horizon_days':h if h is not None else 'FULL','risk_target':risk,'tested':len(rows),**counts})
att=[]
for risk in RISKS:
 daily=(S*(risk/.01))@B; cum=np.cumsum(daily,axis=1); counts={q:0 for q in (1,2,5,8,10)}
 for j in range(len(rows)):
  br=np.r_[np.flatnonzero(daily[j]<-.05),np.flatnonzero(cum[j]<-.10)]; b=int(br.min()) if len(br) else 10**9
  for q in counts:
   ix=np.flatnonzero(cum[j]>=q/100)
   if len(ix) and int(ix[0])<=b: counts[q]+=1
 for q in counts:att.append({'risk_target':risk,'target_pct':q,'tested':len(rows),'reached':counts[q],'reached_pct':counts[q]/len(rows)})
def write(path,arr):
 with open(path,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(arr[0]));w.writeheader();w.writerows(arr)
write(O/'r_based_risk_frontier.csv',front);write(O/'r_based_target_attainment.csv',att);write(O/'r_based_prop_results.csv',front)
json.dump({'status':'PASS','runtime_seconds':time.time()-start,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'portfolios':len(rows),'representatives':len(ids),'risk_levels':len(RISKS),'horizons':len(H),'vectorized':True},open(O/'risk_matrix_performance.json','w'),indent=2)
print(json.dumps({'runtime':time.time()-start,'frontier_rows':len(front)},indent=2))
