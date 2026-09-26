#property strict
double SQX_SMA(const MqlRates &a[],int n,int s){double x=0;for(int i=s;i<s+n;i++)x+=a[i].close;return x/n;}
double SQX_EMA(const MqlRates &a[],int n,int s){int z=s+n*4;double e=a[z].close,k=2.0/(n+1.0);for(int i=z-1;i>=s;i--)e=a[i].close*k+e*(1-k);return e;}
double SQX_TR(const MqlRates &a[],int i){double p=a[i+1].close;return MathMax(a[i].high-a[i].low,MathMax(MathAbs(a[i].high-p),MathAbs(a[i].low-p)));}
double SQX_ATR(const MqlRates &a[],int n,int s){double x=0;for(int i=s;i<s+n;i++)x+=SQX_TR(a,i);return x/n;}
double SQX_ROC(const MqlRates &a[],int n,int s){return a[s+n].close==0?0:a[s].close/a[s+n].close-1;}
double SQX_RSI(const MqlRates &a[],int n,int s){double g=0,l=0;for(int i=s;i<s+n;i++){double d=a[i].close-a[i+1].close;if(d>0)g+=d;else l-=d;}return l==0?100:100-100/(1+g/l);}
double SQX_WILLR(const MqlRates &a[],int n,int s){double h=a[s].high,l=a[s].low;for(int i=s+1;i<s+n;i++){h=MathMax(h,a[i].high);l=MathMin(l,a[i].low);}return h==l?EMPTY_VALUE:-100*(h-a[s].close)/(h-l);}
double SQX_BB(const MqlRates &a[],int n,double m,int s,int w){double x=SQX_SMA(a,n,s),v=0;for(int i=s;i<s+n;i++)v+=(a[i].close-x)*(a[i].close-x);double d=MathSqrt(v/n);return w==0?x+m*d:w==1?x-m*d:x;}
bool SQX_LoadRates(string sym,ENUM_TIMEFRAMES tf,MqlRates &a[],int n){ArraySetAsSeries(a,true);return CopyRates(sym,tf,0,n,a)>=n;}
bool SQX_PivotHigh(const MqlRates&a[],int d,int j){for(int k=1;k<=d;k++)if(a[j+d].high<=a[j+d-k].high||a[j+d].high<=a[j+d+k].high)return false;return true;}
bool SQX_PivotLow(const MqlRates&a[],int d,int j){for(int k=1;k<=d;k++)if(a[j+d].low>=a[j+d-k].low||a[j+d].low>=a[j+d+k].low)return false;return true;}
double SQX_Structure(const MqlRates&a[],int d,int s,int mode){double lastH=EMPTY_VALUE,lastL=EMPTY_VALUE,state=EMPTY_VALUE;for(int j=450-d*2;j>=s;j--){bool h=SQX_PivotHigh(a,d,j),l=SQX_PivotLow(a,d,j);if(h&&l)state=0;else if(h&&lastH!=EMPTY_VALUE)state=a[j+d].high>lastH?1:3;else if(l&&lastL!=EMPTY_VALUE)state=a[j+d].low>lastL?2:4;if(h)lastH=a[j+d].high;if(l)lastL=a[j+d].low;}if(mode==0)return state;if(mode==1)return a[s].close-lastH;if(mode==2)return a[s].close-lastL;return EMPTY_VALUE;}
