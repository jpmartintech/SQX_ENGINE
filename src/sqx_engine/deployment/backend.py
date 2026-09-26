from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

from ..strategy import StrategyDefinition
from .models import PortfolioDefinition
from .templates import INDICATORS, PREDICATES, RISK, EXECUTION, DIAGNOSTIC


class UnsupportedPredicateError(ValueError):
    code = "EXPORT_REJECT_UNSUPPORTED_PREDICATE"


SUPPORTED_PREDICATES = {
    "trend.close_ema", "trend.ema_slope", "trend.ema_pair", "trend.breakout_high", "trend.breakout_low",
    "rsi_14", "momentum.roc", "momentum.willr", "volatility.atr_regime", "volatility.bb_upper",
    "volatility.bb_lower", "volatility.bb_middle", "volatility.compression", "structure.last",
    "structure.break_high", "structure.break_low", "structure.fractal_high", "structure.fractal_low",
}

def predicate_key(feature: str) -> str:
    p = feature.split(".")
    return ".".join(p[:2]) if p[0] == "volatility" and p[1] in {"bb_upper", "bb_lower", "bb_middle", "compression", "atr_regime"} else ".".join(p[:2]) if p[0] in {"trend", "momentum", "structure"} else feature

def magic_number(identity: str) -> int:
    return 100000 + (int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16) % 1900000000)

class DeploymentBackend(ABC):
    name = "abstract"
    @abstractmethod
    def export_strategy(self, strategy: StrategyDefinition, path: str | Path, **kwargs): ...
    @abstractmethod
    def export_portfolio(self, portfolio: PortfolioDefinition, path: str | Path, **kwargs): ...

@dataclass
class MQL5Backend(DeploymentBackend):
    name: str = "MQL5"

    def validate(self, strategy):
        for p in strategy.predicates:
            key = predicate_key(p.feature)
            if key not in SUPPORTED_PREDICATES:
                raise UnsupportedPredicateError(f"{UnsupportedPredicateError.code}: {p.feature}")
        if strategy.direction not in {"LONG", "SHORT"}: raise ValueError("Unsupported direction")

    def export_strategy(self, strategy, path, portfolio_id="", include_dir=None):
        self.validate(strategy); return _write_ea(strategy, None, Path(path), portfolio_id, include_dir)

    def export_portfolio(self, portfolio, path, include_dir=None):
        for x in portfolio.strategies: self.validate(x.strategy)
        return _write_ea(None, portfolio, Path(path), "", include_dir)


def _cpp_string(x): return str(x).replace('\\', '\\\\').replace('"', '\\"')
def _tf(x): return {"M15":"PERIOD_M15", "H1":"PERIOD_H1", "H4":"PERIOD_H4"}.get(x, f"PERIOD_{x}")

def _required_rate_count(strategy: StrategyDefinition, shift: int = 1) -> int:
    """Return the largest causal rate buffer required by the V1.7 helpers.

    The generated runtime still protects every helper against short arrays;
    this calculation prevents normal portfolio startup from requesting fewer
    bars than a strategy's longest indicator needs.
    """
    required = 600  # preserve the certified baseline warm-up window
    for predicate in strategy.predicates:
        parts = predicate.feature.split(".")
        def integer(index):
            return int(parts[index])
        maximum = shift
        if predicate.feature == "rsi_14":
            maximum = shift + 14
        elif parts[0] == "momentum" and parts[1] == "roc":
            maximum = shift + integer(2)
        elif parts[0] == "momentum" and parts[1] == "willr":
            maximum = shift + integer(2) - 1
        elif parts[0] == "trend" and parts[1] == "close_ema":
            maximum = shift + integer(2) * 4
        elif parts[0] == "trend" and parts[1] == "ema_slope":
            maximum = shift + integer(2) * 4 + integer(3)
        elif parts[0] == "trend" and parts[1] == "ema_pair":
            maximum = max(shift + integer(2) * 4, shift + integer(3) * 4)
        elif parts[0] == "trend" and parts[1] in {"breakout_high", "breakout_low"}:
            maximum = shift + integer(2)
        elif parts[0] == "volatility" and parts[1] == "atr_regime":
            maximum = shift + integer(2) + integer(3)
        elif parts[0] == "volatility" and parts[1] in {"bb_upper", "bb_lower", "bb_middle"}:
            maximum = shift + integer(2) - 1
        elif parts[0] == "volatility" and parts[1] == "compression":
            maximum = shift + integer(2) * 4
        elif parts[0] == "structure":
            d = integer(2)
            maximum = max(shift + 2 * d, 450)
        required = max(required, maximum + 1)
    return required

def _predicate_expr(p):
    return f'SQX_Predicate(rates, {p.feature!r}, "{p.operator}", {float(p.value):.17g}, shift)'

def _strategy_block(s, index):
    preds = [f'SQX_Predicate(rates, "{_cpp_string(p.feature)}", "{p.operator}", {float(p.value):.17g}, shift)' for p in s.predicates]
    join = " && " if s.logic == "AND" else " || "
    return f'''// {s.readable_id} canonical={s.canonical_hash}\n#define SQX_S{index}_ID "{_cpp_string(s.readable_id)}"\n#define SQX_S{index}_MAGIC {magic_number(s.canonical_hash)}\n#define SQX_S{index}_TF {_tf(s.timeframe)}\n#define SQX_S{index}_ATR_PERIOD {s.atr_period}\n#define SQX_S{index}_STOP_ATR {s.stop_atr:.17g}\n#define SQX_S{index}_TARGET_ATR {s.target_atr:.17g}\n#define SQX_S{index}_TIME_EXIT {s.time_exit}\n#define SQX_S{index}_DIRECTION_{s.direction} 1\nbool SQX_S{index}_Signal(const MqlRates &rates[], const int shift) {{ double atr=SQX_ATR(rates, {s.atr_period}, shift); return ({join.join(preds)}) && atr!=EMPTY_VALUE && atr>0; }}\n'''

def _write_ea(strategy, portfolio, path, portfolio_id, include_dir):
    path.parent.mkdir(parents=True, exist_ok=True)
    if include_dir is None: include_dir = path.parent.parent / "Include" / "SQX"
    include_dir = Path(include_dir); include_dir.mkdir(parents=True, exist_ok=True)
    _write_includes(include_dir)
    if strategy:
        blocks = _strategy_block(strategy, 0); strategies = [(strategy, 0)]
        title = f"SQX_{strategy.readable_id.replace('-', '_')}"
        body = _single_ea(strategy, blocks, portfolio_id)
    else:
        strategies = [(x.strategy, i) for i, x in enumerate(portfolio.strategies)]
        blocks = "\n".join(_strategy_block(s, i) for s, i in strategies)
        title = f"SQX_{portfolio.portfolio_id.replace('-', '_')}"
        body = _portfolio_ea(portfolio, blocks, strategies)
    body = _normalize_exit_translation(body, strategy, portfolio)
    # MQL5 exposes equity through AccountInfoDouble; ACCOUNT_EQUITY is an enum,
    # not a callable function. Keep this normalization at the exporter boundary
    # so every generated EA, including future portfolio layouts, gets valid code.
    body = body.replace("ACCOUNT_EQUITY()", "AccountInfoDouble(ACCOUNT_EQUITY)")
    path.write_text("// Generated by SQX Deployment Engine V1; do not edit.\n" + body)
    return path

def _normalize_exit_translation(body, strategy, portfolio):
    """Keep distance arguments to SQX_SendEntry in ATR-price units.

    The execution wrapper receives stop/target *distances* and converts them
    to broker price levels.  The frozen Python evaluator defines target as
    ATR(signal bar) * target_atr; it must not be multiplied by the already
    expanded stop distance.
    """
    body = re.sub(r"atr\*([0-9.e+-]+)/([0-9.e+-]+)\*stop", r"atr*\1", body)
    body = re.sub(r"SQX_S(\d+)_TARGET_ATR/SQX_S\1_STOP_ATR\*stop", r"SQX_S\1_TARGET_ATR", body)
    if strategy is not None:
        body = body.replace(
            "void OnTick() { static datetime last=0;",
            f"void OnTick() {{ SQX_ManagePosition(_Symbol,InpMagic,{_tf(strategy.timeframe)},{strategy.time_exit},InpPortfolioId,SQX_S0_ID); static datetime last=0;",
        )
        body = body.replace(
            "if(!SQX_S0_Signal(rates,shift)) return;",
            "if(!SQX_S0_Signal(rates,shift) || SQX_HasPosition(_Symbol,InpMagic)) return;",
        )
    elif portfolio is not None:
        for i, item in enumerate(portfolio.strategies):
            needle = f"last[{i}]=iTime(_Symbol,SQX_S{i}_TF,0);{{ MqlRates r{i}[];"
            replacement = f"last[{i}]=iTime(_Symbol,SQX_S{i}_TF,0);{{ SQX_ManagePosition(_Symbol,SQX_S{i}_MAGIC,SQX_S{i}_TF,SQX_S{i}_TIME_EXIT,\"{_cpp_string(portfolio.portfolio_id)}\",SQX_S{i}_ID); MqlRates r{i}[];"
            body = body.replace(needle, replacement)
            pattern = rf"if\(SQX_LoadRates\(_Symbol,SQX_S{i}_TF,r{i},(\d+)\) && SQX_S{i}_Signal\(r{i},1\)\)"
            replacement = lambda m: f"if(!SQX_HasPosition(_Symbol,SQX_S{i}_MAGIC) && SQX_LoadRates(_Symbol,SQX_S{i}_TF,r{i},{m.group(1)}) && SQX_S{i}_Signal(r{i},1))"
            body = re.sub(pattern, replacement, body)
    return body

def _write_includes(directory):
    for name, body in (("sqx_indicators.mqh", INDICATORS), ("sqx_predicates.mqh", PREDICATES),
                       ("sqx_risk.mqh", RISK), ("sqx_execution.mqh", EXECUTION),
                       ("sqx_diagnostic.mqh", DIAGNOSTIC)):
        (directory / name).write_text(body)

def _header():
    return '#property strict\n#include <Trade/Trade.mqh>\n#include <SQX/sqx_indicators.mqh>\n#include <SQX/sqx_predicates.mqh>\n#include <SQX/sqx_risk.mqh>\n#include <SQX/sqx_execution.mqh>\n#include <SQX/sqx_diagnostic.mqh>\n'

def _common_oninit(ids):
    return 'int OnInit() { SQX_Log("SQX_INIT", "", "", _Symbol, _Period, 0, 0, 0, 0, "NETTING_OR_HEDGING_ACCOUNT_MODE"); return INIT_SUCCEEDED; }\n'

def _single_ea(s, blocks, portfolio_id):
    d = 1 if s.direction == "LONG" else -1
    return _header() + f'''\ninput double InpRiskFraction={s.stop_atr and 0.01:.8f};\ninput long InpMagic={magic_number(s.canonical_hash)};\ninput string InpPortfolioId="{_cpp_string(portfolio_id)}";\n{blocks}\n{_common_oninit([s])}\nvoid OnTick() {{ static datetime last=0; datetime now=iTime(_Symbol,{_tf(s.timeframe)},0); if(now==last) return; last=now; MqlRates rates[]; if(!SQX_LoadRates(_Symbol,{_tf(s.timeframe)},rates,600)) return; int shift=1; if(!SQX_S0_Signal(rates,shift)) return; double atr=SQX_ATR(rates,{s.atr_period},shift); double stop=atr*{s.stop_atr:.17g}; double volume=SQX_RiskVolume(_Symbol,ACCOUNT_EQUITY(),InpRiskFraction,stop); SQX_RiskDecision decision=SQX_CheckPortfolioRisk(InpRiskFraction,InpRiskFraction,0.02); if(decision.action==SQX_REJECT) {{ SQX_Log("SQX_RISK_REJECT",InpPortfolioId,SQX_S0_ID,_Symbol,{_tf(s.timeframe)},0,volume,stop,InpRiskFraction,"RISK_LIMIT"); return; }} if(volume<=0) return; SQX_SendEntry(_Symbol,{"ORDER_TYPE_BUY" if d==1 else "ORDER_TYPE_SELL"},volume,stop,atr*{s.target_atr:.17g}/{s.stop_atr:.17g}*stop,InpMagic,InpPortfolioId,SQX_S0_ID); }}\n'''

def _portfolio_ea(p, blocks, strategies):
    calls = []
    for s, i in strategies:
        d = "ORDER_TYPE_BUY" if s.direction == "LONG" else "ORDER_TYPE_SELL"
        weight = dict((x.strategy.readable_id, x.weight) for x in p.strategies)[s.readable_id]
        pred_args = []
        for pred in s.predicates:
            pred_args.extend([f'"{_cpp_string(pred.feature)}"', f'SQX_Feature(r{i},"{_cpp_string(pred.feature)}",1)', f'{float(pred.value):.17g}', f'SQX_Predicate(r{i},"{_cpp_string(pred.feature)}","{pred.operator}",{float(pred.value):.17g},1)'])
        while len(pred_args) < 16:
            pred_args.extend(['""', 'EMPTY_VALUE', 'EMPTY_VALUE', 'false'])
        trace_call = f'SQX_TraceEvaluation(InpDiagnosticFile,now,r{i}[1].time,{i},SQX_S{i}_ID,"{s.direction}",has,open_before,{len(s.predicates)},"{s.logic}",' + ','.join(pred_args[:16]) + f',raw,!has,risk_gate,true,admitted,requested,v,open_after,reason);'
        raw_call = f'if(InpDiagnosticTrace && raw)SQX_TraceRawSignal(InpDiagnosticRawFile,r{i}[1].time,r{i}[0].time,{i},SQX_S{i}_ID,"{s.direction}",has,risk_gate,admitted,reason);'
        body = f'''{{ MqlRates r{i}[]; bool has=SQX_HasPosition(_Symbol,SQX_S{i}_MAGIC); bool loaded=false,raw=false; double open_before=SQX_OpenRisk(),open_after=open_before,requested=0.0,v=0.0; string risk_gate="NOT_EVALUATED",reason="NO_SIGNAL"; bool admitted=false; datetime now=iTime(_Symbol,SQX_S{i}_TF,0); if(!has || InpDiagnosticTrace){{ loaded=SQX_LoadRates(_Symbol,SQX_S{i}_TF,r{i},{_required_rate_count(s)}); if(loaded) raw=SQX_S{i}_Signal(r{i},1); }} if(!has && loaded && raw){{ requested=SQX_WEIGHTED_RISK({p.base_risk:.17g},{weight:.17g}); SQX_RiskDecision rd=SQX_CheckPortfolioRisk(requested,requested,{p.max_open_risk:.17g}); risk_gate=rd.action==SQX_REJECT?"REJECT_RISK_LIMIT":rd.action==SQX_ACCEPT_REDUCED?"ACCEPT_REDUCED":"ACCEPT_FULL"; if(rd.action==SQX_REJECT){{reason="RISK_LIMIT";SQX_Log("SQX_RISK_REJECT","{_cpp_string(p.portfolio_id)}",SQX_S{i}_ID,_Symbol,SQX_S{i}_TF,0,0,0,requested,"RISK_LIMIT");}} else {{v=SQX_RiskVolume(_Symbol,AccountInfoDouble(ACCOUNT_EQUITY),rd.risk, SQX_ATR(r{i},SQX_S{i}_ATR_PERIOD,1)*SQX_S{i}_STOP_ATR);if(v>0){{admitted=true;reason="ACCEPTED";SQX_SendEntry(_Symbol,{d},v,SQX_ATR(r{i},SQX_S{i}_ATR_PERIOD,1)*SQX_S{i}_STOP_ATR,SQX_ATR(r{i},SQX_S{i}_ATR_PERIOD,1)*SQX_S{i}_TARGET_ATR,SQX_S{i}_MAGIC,"{_cpp_string(p.portfolio_id)}",SQX_S{i}_ID);}}else reason="VOLUME_ZERO";}} open_after=SQX_OpenRisk(); }} else if(has) reason="POSITION_EXISTS"; else if(!loaded) reason="RATES_NOT_READY"; if(InpDiagnosticTrace && loaded){{ {trace_call} }} {raw_call} }}'''
        calls.append(f'if(iTime(_Symbol,SQX_S{i}_TF,0)!=last[{i}]){{last[{i}]=iTime(_Symbol,SQX_S{i}_TF,0);{body}}}')
    return _header() + f'''\ninput double InpBaseRisk={p.base_risk:.8f};\ninput double InpMaxOpenRisk={p.max_open_risk:.8f};\ninput double InpInternalDailyLimit=0.0;\ninput double InpInternalTotalLimit=0.0;\n{blocks}\n{_common_oninit([x.strategy for x in p.strategies])}\nvoid OnTick() {{ SQX_UpdatePropAccount(InpInternalDailyLimit,InpInternalTotalLimit); static datetime last[64]; int k=0; for(int i=0;i<{len(strategies)};i++) {{ datetime now=iTime(_Symbol,(i==i ? SQX_S{i}_TF : PERIOD_CURRENT),0); if(now==last[i]) continue; last[i]=now; }} for(int i=0;i<{len(strategies)};i++) {{ {calls[0] if len(calls)==1 else ''} }} }}\n'''.replace('for(int i=0;i<'+str(len(strategies))+';i++) { { '+(calls[0] if len(calls)==1 else '')+' } }', '\n'.join(calls)) if len(strategies)==1 else _portfolio_ea_impl(p, blocks, calls, strategies)

def _portfolio_ea_impl(p, blocks, calls, strategies):
    return _header() + f'''\ninput double InpBaseRisk={p.base_risk:.8f}; input double InpMaxOpenRisk={p.max_open_risk:.8f}; input double InpInternalDailyLimit=0.0; input double InpInternalTotalLimit=0.0; input bool InpDiagnosticTrace=false; input string InpDiagnosticFile="SQX_portfolio_predicate_trace.csv"; input string InpDiagnosticRawFile="SQX_portfolio_raw_signals.csv";\n{blocks}\n{_common_oninit([x.strategy for x in p.strategies])}\nvoid OnTick() {{ static datetime last[64]; SQX_UpdatePropAccount(InpInternalDailyLimit,InpInternalTotalLimit);\n'''+"\n".join(calls)+"\n}\n"
