#property strict
double SQX_Feature(const MqlRates &a[],string f,int s){string p[];int n=StringSplit(f,'.',p);if(f=="rsi_14")return SQX_RSI(a,14,s);
if(n>=3&&p[0]=="momentum"&&p[1]=="roc")return SQX_ROC(a,(int)StringToInteger(p[2]),s);
if(n>=3&&p[0]=="momentum"&&p[1]=="willr")return SQX_WILLR(a,(int)StringToInteger(p[2]),s);
if(n>=3&&p[0]=="trend"&&p[1]=="close_ema"){int x=(int)StringToInteger(p[2]);return a[s].close-SQX_EMA(a,x,s);}
if(n>=4&&p[0]=="trend"&&p[1]=="ema_slope"){int x=(int)StringToInteger(p[2]),k=(int)StringToInteger(p[3]);return SQX_EMA(a,x,s)-SQX_EMA(a,x,s+k);}
if(n>=4&&p[0]=="trend"&&p[1]=="ema_pair"){int x=(int)StringToInteger(p[2]),y=(int)StringToInteger(p[3]);return SQX_EMA(a,x,s)-SQX_EMA(a,y,s);}
if(n>=3&&p[0]=="trend"&&(p[1]=="breakout_high"||p[1]=="breakout_low")){int x=(int)StringToInteger(p[2]);double z=p[1]=="breakout_high"?-DBL_MAX:DBL_MAX;for(int i=s+1;i<s+x+1;i++)z=p[1]=="breakout_high"?MathMax(z,a[i].high):MathMin(z,a[i].low);return a[s].close-z;}
if(n>=4&&p[0]=="volatility"&&p[1]=="atr_regime"){int x=(int)StringToInteger(p[2]),b=(int)StringToInteger(p[3]);double now=SQX_ATR(a,x,s)/a[s].close,avg=0;for(int i=s+1;i<s+b+1;i++)avg+=SQX_ATR(a,x,i)/a[i].close;return avg==0?EMPTY_VALUE:now/(avg/b)-1;}
if(n>=4&&p[0]=="volatility"&&StringFind(p[1],"bb_")==0){int x=(int)StringToInteger(p[2]);return a[s].close-SQX_BB(a,x,StringToDouble(p[3]),s,p[1]=="bb_upper"?0:p[1]=="bb_lower"?1:2);}
if(n>=5&&p[0]=="volatility"&&p[1]=="compression"){int x=(int)StringToInteger(p[2]);double u=SQX_BB(a,x,StringToDouble(p[3]),s,0),l=SQX_BB(a,x,StringToDouble(p[3]),s,1),m=SQX_EMA(a,x,s),q=SQX_ATR(a,x,s);return(u<m+StringToDouble(p[4])*q&&l>m-StringToDouble(p[4])*q)?1:(u>m+StringToDouble(p[4])*q&&l<m-StringToDouble(p[4])*q)?-1:0;}
if(n>=3&&p[0]=="structure"){int d=(int)StringToInteger(p[2]);if(p[1]=="last")return SQX_Structure(a,d,s,0);if(p[1]=="break_high")return SQX_Structure(a,d,s,1);if(p[1]=="break_low")return SQX_Structure(a,d,s,2);if(p[1]=="fractal_high")return SQX_PivotHigh(a,d,s)?1:0;if(p[1]=="fractal_low")return SQX_PivotLow(a,d,s)?1:0;}
return EMPTY_VALUE;}
bool SQX_Predicate(const MqlRates&a[],string f,string op,double v,int s){double x=SQX_Feature(a,f,s);if(x==EMPTY_VALUE||!MathIsValidNumber(x))return false;return op==">"?x>v:op=="<"?x<v:MathAbs(x-v)<1e-10;}
