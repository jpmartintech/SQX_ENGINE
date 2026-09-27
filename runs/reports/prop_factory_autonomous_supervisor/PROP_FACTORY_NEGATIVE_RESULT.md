# SQX Prop Factory — Product-Level Negative Result

## Result

`PROP_FACTORY_NEGATIVE_RESULT`

The available architecture and current information set did not produce a
defensible short-horizon FTMO Prop manufacturing line after the completed
PROP_V1 campaign, causal loss-state analysis, exact diversification probe,
and cooldown falsification.

## What worked

- General Factory, canonical identities, Exact Equity Replay, MQL5 semantics,
  and OOS isolation remained intact.
- PROP_V1 materially increased opportunity density and shortened holding time.
- Positive 5D tails increased substantially relative to GENERAL.
- Cost robustness remained acceptable.

## What failed

- Six thousand generated PROP_V1 strategies yielded zero PROP_CANDIDATE
  strategies after the legitimate short-horizon/downside/temporal funnel.
- Losses were usually bounded near -1R but occurred in long temporal runs.
- Median maximum consecutive loss count was 13 and median cluster duration was
  approximately 5.33 days.
- M15 and SHORT variants increased opportunity but worsened downside.
- Wider stops improved downside only modestly and reduced upside.
- A shorter/stabilized exit range produced no additional material improvement.

## Causal information review

Market-state descriptors derived from existing causal OHLC information had
weak effects. Prior strategy loss/signal state had a small reproducible
association with subsequent losses, but a cooldown-after-two-losses probe
reduced upper-tail opportunity without producing target attainment.

## Portfolio review

The exact diagnostic diversification probe did not show a robust rescue.
Cross-market/timeframe portfolios had low utilization and weak upper tails.
The few small-sample Verification observations were concentrated in a narrow
XAUUSD M15 diagnostic and are not production evidence. Challenge attainment
remained zero.

## Binding limitation

`MULTIPLE`: the primary binding limitation is clustered downside in the
manufactured raw material, compounded by insufficient independent positive
5D capacity. Portfolio diversification and the simplest causal cooldown
mechanism did not overcome it.

## Why more search is not justified

Three bounded PROP_V1 manufacturing iterations tested distinct fitness and
exit hypotheses. The causal and portfolio probes tested the strongest
remaining explanations without using OOS. Further changes within the same
parameter space would repeat the falsified mechanisms rather than answer a
new product question.

## Reusable components

PROP lineage, Phase A metrics, Phase B fitness vectors, Phase C funnel,
EconomicSpec generation, deterministic manifests, Exact Equity Replay,
portfolio risk semantics, Deployment Engine, and MQL5 validation contracts.

## Freeze

Freeze GENERAL, PROP_V1, Exact Equity Replay, FTMO semantics, canonical
identity, and MQL5 behavior. Preserve all campaign and diagnostic evidence.

## Future redesign

The smallest plausible future redesign is a separately specified Prop
Factory line with a materially new causal information/state model capable of
testing regime-conditioned loss clustering. It should not be implemented by
further tuning PROP_V1 or by weakening its downside gates.
