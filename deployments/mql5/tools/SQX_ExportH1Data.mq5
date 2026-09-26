// SQX Deployment Engine V1 diagnostic utility.
// This script exports broker/tester H1 bars only; it does not trade.
#property strict
#property script_show_inputs

input string InpSymbol = "EURUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_H1;
input datetime InpFrom = D'2023.11.01 00:00';
input datetime InpTo = D'2024.02.02 00:00';
input string InpFileName = "SQX_mt5_h1_export.csv";

void OnStart()
{
   MqlRates rates[];
   int copied = CopyRates(InpSymbol, InpTimeframe, InpFrom, InpTo, rates);
   if(copied <= 0)
   {
      PrintFormat("SQX_DATA_EXPORT_FAILED symbol=%s timeframe=%d error=%d", InpSymbol, InpTimeframe, GetLastError());
      return;
   }
   ArraySetAsSeries(rates, false);
   int handle = FileOpen(InpFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("SQX_DATA_EXPORT_FAILED file=%s error=%d", InpFileName, GetLastError());
      return;
   }
   FileWrite(handle, "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume");
   for(int i = 0; i < copied; i++)
   {
      FileWrite(handle,
                TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS),
                DoubleToString(rates[i].open, _Digits),
                DoubleToString(rates[i].high, _Digits),
                DoubleToString(rates[i].low, _Digits),
                DoubleToString(rates[i].close, _Digits),
                (long)rates[i].tick_volume,
                (int)rates[i].spread,
                (long)rates[i].real_volume);
   }
   FileClose(handle);
   PrintFormat("SQX_DATA_EXPORT_DONE symbol=%s timeframe=%d rows=%d file=%s", InpSymbol, InpTimeframe, copied, InpFileName);
}
