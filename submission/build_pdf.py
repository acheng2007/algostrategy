"""Build the three-page AlgoGators research report plus references.

All measured results are loaded from ``data/processed`` so the report cannot
drift from the reproducible research pipeline.
"""

from pathlib import Path
from xml.sax.saxutils import escape
import json

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
OUTPUT = ROOT / "output/pdf/algogators_crack_spread_research.pdf"
FIGURE = ROOT / "figures/research_summary.png"
PRIMARY = "July-October seasonal"
FULL_PERIOD = "2010-2025 full"

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#2F6F9F")
INK = colors.HexColor("#263238")
MUTED = colors.HexColor("#526777")
PALE = colors.HexColor("#EEF4F7")
RULE = colors.HexColor("#B8C6D1")
RED = colors.HexColor("#9B2226")


def text(body: str, style) -> Paragraph:
    """Escape reserved characters before ReportLab parses the paragraph."""
    return Paragraph(escape(body), style)


def dollars(value: float) -> str:
    return f"{'-' if value < 0 else ''}${abs(value):,.0f}"


def load_measurements() -> dict:
    summary = json.loads((PROCESSED / "research_summary.json").read_text())
    metrics = pd.read_csv(PROCESSED / "strategy_metrics.csv")
    windows = pd.read_csv(PROCESSED / "robustness_windows.csv")
    costs = pd.read_csv(PROCESSED / "cost_sensitivity.csv")
    trades = pd.read_csv(PROCESSED / "strategy_trades.csv", parse_dates=["entry_date"])

    primary = metrics[metrics["strategy"] == PRIMARY].set_index("period")
    original = metrics[metrics["strategy"] == "Original momentum-inventory"].set_index("period")
    full_windows = windows[windows["period"] == FULL_PERIOD].set_index(["start_month", "end_month"])

    assert summary["data"]["eia_publication_delay_days"] == 6
    assert abs(trades["net_pnl"].sum() - primary.loc[FULL_PERIOD, "net_pnl"]) < 1e-6
    return {
        "summary": summary,
        "primary": primary,
        "original": original,
        "windows": full_windows,
        "cost_sharpe_high": costs["sharpe"].max(),
        "cost_sharpe_low": costs["sharpe"].min(),
        "trades": trades,
        "mean_campaign": trades["net_pnl"].mean(),
        "worst_campaign": trades["net_pnl"].min(),
        "winning_campaigns": int((trades["net_pnl"] > 0).sum()),
        "bootstrap": summary["campaign_bootstrap"],
    }


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=25,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=15,
            textColor=BLUE,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=NAVY,
            spaceBefore=5,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=15,
            textColor=INK,
            spaceAfter=4,
        ),
        "source": ParagraphStyle(
            "Source",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=13,
            textColor=MUTED,
            spaceAfter=1,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=NAVY,
        ),
        "table_body": ParagraphStyle(
            "TableBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=13,
            textColor=INK,
            spaceAfter=0,
        ),
        "metric_header": ParagraphStyle(
            "MetricHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def footer(canvas, document):
    canvas.saveState()
    width, _ = letter
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.55 * inch, 0.42 * inch, width - 0.55 * inch, 0.42 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.55 * inch, 0.25 * inch, "AlgoGators systematic strategy research")
    canvas.drawRightString(width - 0.55 * inch, 0.25 * inch, f"Page {document.page}")
    canvas.restoreState()


def callout(body: str, style) -> Table:
    table = Table([[text(body, style)]], colWidths=[7.25 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.7, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def metric_table(s: dict, measurements: dict) -> Table:
    primary = measurements["primary"]
    periods = ["2010-2020 development", "2021-2025 validation", "2010-2025 full"]

    def metric_row(label, field, formatter):
        return [label, *(formatter(primary.loc[period, field]) for period in periods)]

    rows = [
        [
            Paragraph("Metric", s["metric_header"]),
            Paragraph("2010-2020<br/>development", s["metric_header"]),
            Paragraph("2021-2025<br/>validation", s["metric_header"]),
            Paragraph("2010-2025<br/>full", s["metric_header"]),
        ],
        metric_row("Annualized return", "annualized_return", lambda value: f"{value:.2%}"),
        metric_row("Annualized volatility", "annualized_volatility", lambda value: f"{value:.2%}"),
        metric_row("Sharpe ratio", "sharpe", lambda value: f"{value:.2f}"),
        metric_row("Maximum drawdown", "maximum_drawdown", lambda value: f"{value:.2%}"),
        metric_row("Net P&L on $1 million", "net_pnl", dollars),
    ]
    table = Table(rows, colWidths=[2.25 * inch, 1.65 * inch, 1.65 * inch, 1.65 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 12),
                ("LEADING", (0, 1), (-1, -1), 14),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def risk_table(s: dict) -> Table:
    rows = [
        [text("Structural and model", s["table_body"]), text("Seasonality can decay, and 16 annual campaigns provide limited independent evidence.", s["table_body"])],
        [text("Shock and basis", s["table_body"]), text("Outages, weather, geopolitics, and curve changes can abruptly move either leg.", s["table_body"])],
        [text("Leverage and execution", s["table_body"]), text("Futures losses can exceed margin; cap units, retain cash, and verify roll liquidity.", s["table_body"])],
        [text("Data", s["table_body"]), text("Vendor closes remain unreconciled with official exchange settlements.", s["table_body"])],
    ]
    table = Table(rows, colWidths=[1.7 * inch, 5.55 * inch])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, PALE]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def campaign_table(s: dict, measurements: dict) -> Table:
    trades = measurements["trades"].copy()
    trades["year"] = trades["entry_date"].dt.year
    campaigns = trades[["year", "net_pnl"]].sort_values("year").reset_index(drop=True)
    assert len(campaigns) == 16

    left = campaigns.iloc[:8].reset_index(drop=True)
    right = campaigns.iloc[8:].reset_index(drop=True)
    rows = [
        [
            text("Year", s["metric_header"]),
            text("Net P&L", s["metric_header"]),
            text("Year", s["metric_header"]),
            text("Net P&L", s["metric_header"]),
        ]
    ]
    for index in range(8):
        rows.append(
            [
                str(int(left.loc[index, "year"])),
                dollars(left.loc[index, "net_pnl"]),
                str(int(right.loc[index, "year"])),
                dollars(right.loc[index, "net_pnl"]),
            ]
        )

    table = Table(rows, colWidths=[0.8 * inch, 2.8 * inch, 0.8 * inch, 2.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 12),
                ("LEADING", (0, 1), (-1, -1), 13),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    for row_index, campaign_index in enumerate(range(8), start=1):
        if left.loc[campaign_index, "net_pnl"] < 0:
            table.setStyle(TableStyle([("TEXTCOLOR", (1, row_index), (1, row_index), RED)]))
        if right.loc[campaign_index, "net_pnl"] < 0:
            table.setStyle(TableStyle([("TEXTCOLOR", (3, row_index), (3, row_index), RED)]))
    return table


def build_legacy():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    s = styles()
    m = load_measurements()
    data = m["summary"]["data"]
    full = m["primary"].loc[FULL_PERIOD]
    original = m["original"]
    windows = m["windows"]

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.55 * inch,
        title="Seasonal Distillate Margin Expansion",
        author="Adam Cheng",
    )
    story = []

    story.append(Paragraph("Seasonal Distillate Margin Expansion", s["title"]))
    story.append(Paragraph("A systematic futures crack-spread strategy | Research report", s["subtitle"]))
    story.append(
        callout(
            "Measured conclusion: the original momentum and low-inventory thesis was unstable. "
            "The strongest simple candidate is a long same-delivery-month crack spread held from "
            "the final June vendor close through the final October vendor close.",
            s["callout"],
        )
    )
    story.append(Paragraph("1. Core concept and cited rationale", s["h1"]))
    story.append(
        text(
            "One spread unit is long one New York Mercantile Exchange (NYMEX) New York Harbor "
            "ultra-low sulfur diesel (ULSD) futures contract, ticker HO, and short one "
            "same-delivery-month West Texas Intermediate (WTI) crude oil futures contract, ticker "
            "CL. Chicago Mercantile Exchange (CME) Group explains that crack spreads are quoted in "
            "dollars per barrel, that 42 gallons equal one barrel, and that HO and CL represent "
            "42,000 gallons and 1,000 barrels respectively [1].",
            s["body"],
        )
    )
    story.append(
        callout(
            "Daily profit and loss (P&L) per spread unit = 42,000 x change in HO - 1,000 x change in CL.",
            s["callout"],
        )
    )
    story.append(Paragraph("Why the opportunity may exist", s["h1"]))
    story.append(
        text(
            "The United States Energy Information Administration (EIA) reports that distillate "
            "consumption rose an average 4% from September to October in 2019-2023, Midwest demand "
            "regularly peaks in October, and regional inventories typically fall about 25% during "
            "the harvest [2]. EIA also links inventory levels to current and expected product prices "
            "[3] and notes that refinery product-slate constraints limit rapid increases in heating-oil "
            "output [4]. These sources support testing a recurring relative-price imbalance. They do "
            "not prove alpha; the historical simulation is the separate empirical test.",
            s["body"],
        )
    )
    story.append(Paragraph("Measured pattern, data, and rule", s["h1"]))
    story.append(
        text(
            f"The panel contains {data['sessions']:,} daily sessions from 2010-2025 and "
            f"{data['rolls_excluding_initial']} coordinated rolls. July, August, and October were "
            "the most stable favorable development months; winter was not consistently bullish. "
            "The frozen rule holds the contiguous July-October window, including weak September "
            "rather than selecting only the best months. Both legs share a delivery month and roll "
            "together five sessions before CL expiry. Position size updates weekly from trailing "
            "60-session volatility, targets 10% annualized volatility on $1 million, uses whole "
            "contracts, caps exposure at 10 spreads, and delays every close signal one session. "
            "One-way cost per spread is $19.20, including one tick per leg and $2.50 per contract side.",
            s["body"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("2. Evidence, robustness, and risk", s["title"]))
    story.append(metric_table(s, m))
    story.append(Spacer(1, 5))
    story.append(
        text(
            f"Returns use daily after-cost P&L divided by a constant $1 million risk budget and are "
            f"not compounded. Sharpe assumes zero financing. The full sample earned "
            f"{full['annualized_return']:.2%} annually at {full['annualized_volatility']:.2%} "
            f"volatility, giving a {full['sharpe']:.2f} Sharpe. {m['winning_campaigns']} of 16 "
            f"campaigns were profitable; the average was {dollars(m['mean_campaign'])}, and the "
            f"worst was {dollars(m['worst_campaign'])}. A fixed-seed 20,000-draw resampling placed "
            f"the mean campaign between {dollars(m['bootstrap']['bootstrap_mean_lower_95'])} and "
            f"{dollars(m['bootstrap']['bootstrap_mean_upper_95'])} at 95%.",
            s["body"],
        )
    )
    story.append(Paragraph("Robustness and rejected hypothesis", s["h1"]))
    story.append(
        text(
            f"Full-sample Sharpes were {windows.loc[(6, 10), 'sharpe']:.2f} for June-October, "
            f"{windows.loc[(7, 9), 'sharpe']:.2f} for July-September, "
            f"{windows.loc[(8, 10), 'sharpe']:.2f} for August-October, and "
            f"{windows.loc[(7, 11), 'sharpe']:.2f} for July-November, versus "
            f"{windows.loc[(7, 10), 'sharpe']:.2f} for the selected window. Across the tested cost "
            f"range, Sharpe remained {m['cost_sharpe_low']:.2f}-{m['cost_sharpe_high']:.2f}. The "
            f"original momentum-inventory rule produced {original.loc['2010-2020 development', 'sharpe']:.2f} "
            f"in development and {original.loc['2021-2025 validation', 'sharpe']:.2f} in validation, "
            "so its unstable sign was rejected rather than optimized away.",
            s["body"],
        )
    )
    story.append(Paragraph("Risks and data limitation", s["h1"]))
    story.append(risk_table(s))
    story.append(Spacer(1, 4))
    story.append(
        text(
            "Yahoo corroborated broad price levels but not execution-grade daily changes [7]. "
            "Barchart matched only 2 of 20 prices within one tick and reversed one roll interval [6]. "
            "The CFTC confirms -$37.63 for April 20, 2020 versus QuantConnect's -$13.10 [5]. The "
            "strategy had already rolled, so P&L is unaffected, but the official settlement gate is open.",
            s["body"],
        )
    )
    story.append(
        callout(
            "Decision: reject the original momentum thesis. Treat July-October as provisional until "
            "official settlement reconciliation and new out-of-sample campaigns strengthen it.",
            s["callout"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("3. Research exhibit and campaign evidence", s["title"]))
    story.append(Image(str(FIGURE), width=6.30 * inch, height=4.20 * inch))
    story.append(Spacer(1, 4))
    story.append(
        text(
            "Figure: development and validation seasonality, inventory-state results, and cumulative "
            "after-cost P&L. The chart shows why the selected rule is simpler than the rejected initial thesis.",
            s["body"],
        )
    )
    story.append(Paragraph("Annual campaign results", s["h1"]))
    story.append(campaign_table(s, m))
    story.append(Spacer(1, 4))
    story.append(
        text(
            "The 16 campaigns include losses in 2015, 2020, and 2024. This table makes the "
            "effective sample size visible: thousands of daily observations do not create thousands "
            "of independent seasonal bets. The validation period remains similar on return and "
            "Sharpe, but five validation campaigns are not enough to establish durable alpha.",
            s["body"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("References and abbreviations", s["title"]))
    story.append(
        text(
            "The citations below document the crack-spread construction, the economic mechanism, "
            "and the external price checks. They do not substitute for the measured backtest evidence.",
            s["body"],
        )
    )
    sources = [
        "[1] CME Group, An Introduction to Crack Spreads. Supports the 42-gallon conversion, contract sizes, and crack-spread construction: https://www.cmegroup.com/articles/whitepapers/an-introduction-to-crack-spreads.html",
        "[2] EIA, Distillate Fuel Oil Demand Will Increase in the Fall Because of the Agricultural Harvest. Supports fall demand, the October peak, and seasonal inventory draw: https://www.eia.gov/todayinenergy/detail.php?id=63364",
        "[3] EIA, What Drives Crude Oil Prices - Balance. Supports the relationship among inventories, expectations, and petroleum-product prices: https://www.eia.gov/finance/markets/products/balance.php",
        "[4] EIA, Where Our Heating Oil Comes From. Supports refinery product-slate constraints and summer and fall stock building: https://www.eia.gov/energyexplained/heating-oil/where-our-heating-oil-comes-from.php",
        "[5] CFTC, Interim Staff Report on NYMEX WTI Trading Around April 20, 2020. Confirms the official -$37.63 WTI settlement used in the data-quality check: https://www.cftc.gov/PressRoom/PressReleases/8315-20",
        "[6] Barchart, Expired NYMEX Contract Price History. Free secondary contract-price check: https://www.barchart.com/futures/quotes/CLK20/price-history",
        "[7] Yahoo Finance, HO and CL Continuous Futures Histories. Free broad-level smoke test: https://finance.yahoo.com/quote/HO%3DF/history/ and https://finance.yahoo.com/quote/CL%3DF/history/",
    ]
    for source in sources:
        story.append(text(source, s["source"]))
    story.append(
        text(
            "Abbreviations: NYMEX = New York Mercantile Exchange; ULSD = ultra-low sulfur diesel; "
            "WTI = West Texas Intermediate; HO and CL = exchange ticker symbols; P&L = profit and "
            "loss; EIA = Energy Information Administration; CME = Chicago Mercantile Exchange; "
            "CFTC = Commodity Futures Trading Commission; bbl = barrel.",
            s["source"],
        )
    )

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def build():
    from application_content import make_story
    s = styles()
    s['title'].fontSize = 19
    s['title'].leading = 22
    for name in ('body', 'source'):
        s[name].fontSize = 11 if name == 'body' else 9
        s[name].leading = 13.3 if name == 'body' else 10.5
    s['h1'].fontSize = 13
    s['h1'].leading = 15
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(OUTPUT), pagesize=letter,
        leftMargin=.6*inch, rightMargin=.6*inch, topMargin=.5*inch,
        bottomMargin=.55*inch, title='Seasonal Distillate Margin Expansion', author='Adam Cheng')
    document.build(make_story(s, load_measurements()), onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
