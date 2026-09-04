"""Application content shared by the PDF and editable document builders."""
from reportlab.platypus import Paragraph, PageBreak, Image, Spacer
from reportlab.lib.units import inch
from build_pdf import text, dollars, metric_table, campaign_table, FIGURE, FULL_PERIOD


def make_story(s, m):
    story = []
    def p(body, style='body'):
        story.append(text(body, s[style]))
    def h(body):
        p(body, 'h1')
    full = m['primary'].loc[FULL_PERIOD]

    p('Seasonal Distillate Margin Expansion', 'title')
    p('Adam Cheng | Quantitative Development Application', 'subtitle')
    p('A systematic ULSD-WTI futures strategy implemented as a reproducible Python research pipeline. The original momentum and low-inventory hypothesis was unstable; a simpler July-October rule achieved similar development and validation Sharpe ratios, but remains provisional pending official settlement checks.')
    h('Core concept and economic rationale')
    p('One spread unit buys one New York Harbor ultra-low sulfur diesel (ULSD, ticker HO) futures contract and sells one West Texas Intermediate crude oil (WTI, ticker CL) contract with the same delivery month. HO represents 42,000 gallons and CL 1,000 barrels; 42 gallons equal one barrel [1]. This isolates changes in diesel value relative to crude, although it is not a complete refinery profit model.')
    p('Daily P&L per spread = 42,000 x change in HO price - 1,000 x change in CL price.')
    p('Fall harvest and heating demand can tighten distillate supply relative to crude. EIA reports an average 4% September-to-October consumption increase in 2019-2023, an October Midwest demand peak, and roughly 25% regional inventory draws during harvest [2]. Inventories buffer imbalances, while refinery product-slate constraints limit rapid diesel supply responses [3, 4]. Summer stockbuilding and revisions to expected fall tightness offer a plausible link to earlier spread widening.')
    p('Predictable demand is already reflected in futures prices. A return could arise from bearing seasonal risk or unexpected changes in tightness, but this study does not identify which mechanism drives it. July entry was selected from development data, not derived from demand timing alone. Low inventories did not consistently predict returns and are not an entry filter.')
    h('Trading rule and position sizing')
    p('Enter long the spread at the final June vendor close and exit at the final October vendor close; remain flat otherwise. Recalculate size at the close of the first observed session of each ISO week and whenever the seasonal signal changes. Use the trailing 60-session sample standard deviation of dollar P&L for one spread, with a 30-observation minimum.')
    p('Units = min(10, floor[(0.10 x $1,000,000) / (sqrt(252) x daily P&L standard deviation)]).')
    p('Round down to whole spreads and carry size between updates. A close decision determines exposure for the following close-to-close interval. The ten-unit cap and time spent flat mean realized annual volatility can be below the 10% sizing target. These are simulation conventions; vendor closes have not been demonstrated to be executable fills.')
    story.append(PageBreak())

    p('Software implementation and backtesting', 'title')
    h('Data pipeline and contract handling')
    p('Python with pandas and NumPy transforms QuantConnect individual-contract histories and official EIA weekly spreadsheets into a dated research panel. Raw inputs are retained separately from processed tables. The selected 2010-2025 panel contains 4,031 sessions and 192 coordinated rolls. Functions separate data preparation, hypothesis tests, signal generation, sizing, P&L accounting, and performance measurement.')
    p('Select the nearest eligible common delivery month for HO and CL using expiry metadata. Both legs roll together under a cutoff five business days before the earlier expiry. Across a roll, use the newly selected pair at both price endpoints, including its previous-session reference prices. This avoids booking the gap between old and new contract prices as profit. The construction audits reference-price availability, delivery-month progression, and roll cutoffs.')
    p('EIA Friday observations become usable six calendar days later. This conservative convention delays the normal Wednesday release by one day, but is not a complete archive of actual release timestamps. Seasonally normalized inventory values and momentum signals are used in hypothesis tests; the final rule uses the calendar and trailing volatility only.')
    h('Research sequence and chronological evaluation')
    p('The 2010-2020 development sample was used to examine monthly seasonality, 10-, 20-, and 40-session momentum, inventory states, and their interactions. Momentum had little forecasting power and inventory relationships changed across samples. July, August, and October were favorable development months; the contiguous July-October rule retained weak September rather than cherry-picking individual months. The frozen rule was then evaluated on 2021-2025 without tuning it to that period.')
    p('The backtest multiplies lagged whole-contract positions by daily spread P&L. Costs apply to entries, exits, resizing, and rolls: one minimum tick per leg plus $2.50 per contract side equals $19.20 per spread one way, or $38.40 to replace a carried spread at a roll. Daily net P&L is divided by a constant $1 million risk budget; returns are not compounded and Sharpe assumes zero financing.')
    h('Automated checks and a resolved accounting defect')
    p('Six unittest checks cover EIA availability, exclusion of the expiring negative-price WTI contract, one seasonal campaign per year, finite performance metrics, campaign-to-daily P&L reconciliation, and transaction-cost sensitivity. Opening costs initially fell outside campaign episodes even though daily total P&L was correct. The correction attributes opening costs to the next exposure interval; a regression test now requires campaign net P&L and costs to reconcile with daily totals.')
    p('The pipeline exports metrics, annual campaigns, robustness tables, and figures. The report builder reads measured outputs rather than hardcoding performance values. A Python LEAN backtest algorithm was also prepared and audited; this is a research implementation, with broker execution and operational controls still to be completed.')
    story.append(PageBreak())

    p('Evidence risk and deployment limits', 'title')
    p(f"After modeled costs, development Sharpe was 0.58 and validation Sharpe 0.60. Full-sample annual return was {full['annualized_return']:.2%}, volatility {full['annualized_volatility']:.2%}, and Sharpe {full['sharpe']:.2f}. {m['winning_campaigns']} of 16 campaigns were profitable; mean campaign P&L was {dollars(m['mean_campaign'])} and the worst was {dollars(m['worst_campaign'])}.")
    p(f"Nearby June-October, July-September, August-October, and July-November windows had full-sample Sharpes of 0.51, 0.47, 0.45, and 0.46. Across tested costs, Sharpe ranged from {m['cost_sharpe_low']:.2f} to {m['cost_sharpe_high']:.2f}. A fixed-seed 20,000-draw resampling of 16 campaigns placed mean P&L between {dollars(m['bootstrap']['bootstrap_mean_lower_95'])} and {dollars(m['bootstrap']['bootstrap_mean_upper_95'])} at 95%. This assumes campaigns are representative and does not correct for strategy selection or structural change.")
    h('Risk controls and capital requirements')
    p('Seasonality can weaken as refining capacity, exports, and demand change. Outages, weather, geopolitics, and curve shifts can abruptly compress the spread. Whole-contract volatility sizing and a ten-spread cap limit modeled exposure but do not prevent gap losses or margin calls. The sample has only 16 annual bets and five validation campaigns; thousands of daily observations do not establish durable alpha.')
    p('The $1 million denominator is a risk budget, not a demonstrated minimum account size. Ten spreads mean ten HO and ten CL contracts. Gross notional equals units x (42,000 x absolute HO price + 1,000 x absolute CL price), despite a much smaller net exposure. Exchange and broker margin requirements, cash reserves, and delivery-month liquidity must be checked before trading; the backtest does not enforce margin or volume participation limits, so capacity is not established.')
    p('Deployment requires an explicit order schedule, two-leg fill and partial-fill handling, spread/slippage limits, stale-data checks, position reconciliation, and margin monitoring. Closing-price volatility is unavailable before that close, so real execution would need an earlier information cutoff or later fill, followed by a backtest using that timing. The existing daily simulation does not prove achievable fills.')
    h('Independent data checks and research decision')
    p('Yahoo corroborated broad price levels [7], but Barchart matched only 2 of 20 contract prices within one tick and reversed one roll interval [6]. CFTC reports the April 20, 2020 WTI settlement as -$37.63 versus QuantConnect\'s -$13.10 [5]. That expiring contract was not held, but other vendor-close discrepancies remain unresolved. Reconcile at least 20 official HO/CL settlements across two roll windows before treating results as execution evidence. Retain July-October as a provisional candidate; do not retune it on validation results.')
    h('References')
    sources = [
        '[1] CME Group. An Introduction to Crack Spreads. https://www.cmegroup.com/articles/whitepapers/an-introduction-to-crack-spreads.html',
        '[2] EIA. Distillate demand and the fall agricultural harvest. https://www.eia.gov/todayinenergy/detail.php?id=63364',
        '[3] EIA. Petroleum product balances. https://www.eia.gov/finance/markets/products/balance.php',
        '[4] EIA. Where Our Heating Oil Comes From. https://www.eia.gov/energyexplained/heating-oil/where-our-heating-oil-comes-from.php',
        '[5] CFTC. Interim report on April 20, 2020 WTI trading. https://www.cftc.gov/PressRoom/PressReleases/8315-20',
        '[6] Barchart. Expired contract history. https://www.barchart.com/futures/quotes/CLK20/price-history',
        '[7] Yahoo Finance. https://finance.yahoo.com/quote/HO%3DF/history/ and https://finance.yahoo.com/quote/CL%3DF/history/'
    ]
    for ref in sources:
        p(ref, 'source')
    story.append(PageBreak())
    p('Performance and research exhibits', 'title')
    story.append(metric_table(s, m))
    story.append(Spacer(1, 5))
    story.append(Image(str(FIGURE), width=5.7*inch, height=3.8*inch))
    p('Source: project calculations from QuantConnect futures and EIA inventories. Charts show seasonality, inventory conditioning, and simulated cumulative net P&L; they are not live returns.', 'source')
    h('Annual campaign net P&L')
    story.append(campaign_table(s, m))
    return story
