"""
Analytics on merged UN Comtrade export data.

Structure:
  Part 0 – Data quality report: validation, completeness, descriptive statistics.
  Part A – Export flows by reporter → partner: route totals, YoY growth, heatmap.
  Part B – Commodity detail (cmdDesc): commodity breakdown per route, top commodities.
  Part C – Academic metrics: unit values (USD/kg), market concentration (HHI),
           market share analysis.

Data note: the merged dataset contains only export flows (flowCode = 'X').
Individual rows represent sub-transactions (shipments) and are aggregated
via summation within each analysis function.

Run: python analyze_merged_trade.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import seaborn as sns

    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
MERGED_CSV = OUTPUT_DIR / "merged_trade_data.csv"
ANALYTICS_OUT_DIR = OUTPUT_DIR / "analytics"
TOP_N = 15
TOP_ROUTES_FOR_COMMODITY = 10

# Columns expected from the merged Comtrade export
EXPECTED_COLS = {
    "period", "reporterCode", "reporterDesc", "partnerCode", "partnerDesc",
    "cmdCode", "cmdDesc", "flowCode", "flowDesc", "primaryValue", "netWgt",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("primaryValue", "netWgt", "qty", "period"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def ensure_analytics_dir():
    ANALYTICS_OUT_DIR.mkdir(parents=True, exist_ok=True)


def _route(df: pd.DataFrame) -> pd.Series:
    """Reporter → Partner label."""
    return df["reporterDesc"].astype(str) + " → " + df["partnerDesc"].astype(str)


def _fmt_usd(val: float) -> str:
    """Format large USD values for display."""
    if abs(val) >= 1e9:
        return f"${val / 1e9:,.2f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:,.2f}M"
    if abs(val) >= 1e3:
        return f"${val / 1e3:,.1f}K"
    return f"${val:,.2f}"


def _style_axes(ax, title: str, source_note: bool = True):
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if source_note:
        ax.annotate(
            "Source: UN Comtrade (exports only)",
            xy=(0.99, -0.08), xycoords="axes fraction",
            fontsize=7, color="grey", ha="right",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  PART 0 – DATA QUALITY REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Run quality checks and return a summary DataFrame.  Print warnings."""
    checks = []

    # Column presence
    missing_cols = EXPECTED_COLS - set(df.columns)
    checks.append(("expected_columns_present", len(missing_cols) == 0,
                    f"missing: {missing_cols}" if missing_cols else "all present"))

    # Row count
    checks.append(("total_rows", True, str(len(df))))

    # Period coverage
    periods = sorted(df["period"].dropna().unique())
    checks.append(("periods", True, ", ".join(str(int(p)) for p in periods)))

    # Flow direction — dataset should be exports only
    flows = df["flowDesc"].unique().tolist()
    is_export_only = len(flows) == 1 and flows[0] == "Export"
    checks.append(("export_only", is_export_only,
                    f"flowDesc values: {flows}"))
    if not is_export_only:
        print(f"  [WARN] Data contains non-export flows: {flows}")

    # Null counts in key columns
    for col in ["primaryValue", "netWgt", "reporterDesc", "partnerDesc", "cmdDesc"]:
        n_null = int(df[col].isna().sum())
        checks.append((f"null_{col}", n_null == 0, str(n_null)))
        if n_null > 0:
            print(f"  [WARN] {col}: {n_null} null value(s)")

    # Negative or zero trade values
    n_neg = int((df["primaryValue"] < 0).sum())
    n_zero = int((df["primaryValue"] == 0).sum())
    checks.append(("negative_primaryValue", n_neg == 0, str(n_neg)))
    checks.append(("zero_primaryValue", True, str(n_zero)))
    if n_neg > 0:
        print(f"  [WARN] {n_neg} row(s) with negative primaryValue")

    # Unique reporters and partners
    checks.append(("unique_reporters", True, str(df["reporterDesc"].nunique())))
    checks.append(("unique_partners", True, str(df["partnerDesc"].nunique())))
    checks.append(("unique_commodities", True, str(df["cmdDesc"].nunique())))

    # Sub-transaction density
    grp = df.groupby(["reporterDesc", "partnerDesc", "cmdCode", "period"]).size()
    checks.append(("max_subtransactions_per_group", True, str(int(grp.max()))))
    checks.append(("mean_subtransactions_per_group", True, f"{grp.mean():.1f}"))

    report = pd.DataFrame(checks, columns=["check", "passed", "detail"])
    return report


def descriptive_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Descriptive statistics for key numeric columns."""
    stats = df[["primaryValue", "netWgt"]].describe().round(2)
    stats.loc["total"] = df[["primaryValue", "netWgt"]].sum().round(2)
    stats.loc["null_count"] = df[["primaryValue", "netWgt"]].isna().sum()
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
#  PART A – EXPORT FLOWS BY REPORTER → PARTNER
# ═══════════════════════════════════════════════════════════════════════════════

def table_exports_by_route_year(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregated export value and weight by reporter, partner, and year."""
    g = df.groupby(["reporterDesc", "partnerDesc", "period"]).agg(
        value_usd=("primaryValue", "sum"),
        weight_kg=("netWgt", "sum"),
        n_transactions=("primaryValue", "count"),
    ).round(2)
    return g.reset_index()


def table_top_routes(df: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    """Top reporter → partner routes by total export value."""
    df = df.copy()
    df["route"] = _route(df)
    g = df.groupby("route").agg(
        total_value_usd=("primaryValue", "sum"),
        total_weight_kg=("netWgt", "sum"),
        n_transactions=("primaryValue", "count"),
        reporterDesc=("reporterDesc", "first"),
        partnerDesc=("partnerDesc", "first"),
    ).round(2)
    g = g.sort_values("total_value_usd", ascending=False).head(n).reset_index()
    # Add share of total trade
    total_trade = df["primaryValue"].sum()
    g["share_pct"] = (g["total_value_usd"] / total_trade * 100).round(2)
    g["cumulative_share_pct"] = g["share_pct"].cumsum().round(2)
    return g[["route", "reporterDesc", "partnerDesc", "total_value_usd",
              "total_weight_kg", "n_transactions", "share_pct", "cumulative_share_pct"]]


def table_yoy_by_route(df: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year change in export value by route."""
    if "period" not in df.columns or df["period"].nunique() < 2:
        return pd.DataFrame()
    df = df.copy()
    df["route"] = _route(df)
    piv = df.pivot_table(
        index="route", columns="period", values="primaryValue",
        aggfunc="sum",
    ).reset_index()
    years = sorted([c for c in piv.columns if isinstance(c, (int, float))])
    if len(years) < 2:
        return pd.DataFrame()
    prev, last = years[-2], years[-1]
    piv["value_prev"] = piv[prev]
    piv["value_last"] = piv[last]
    piv["abs_change"] = (piv["value_last"] - piv["value_prev"]).round(2)
    piv["yoy_pct"] = (
        piv["abs_change"] / piv["value_prev"].replace(0, np.nan) * 100
    ).round(2)
    out = piv[["route", "value_prev", "value_last", "abs_change", "yoy_pct"]]
    out = out.copy()
    out.columns = ["route", f"value_{int(prev)}", f"value_{int(last)}", "abs_change_usd", "yoy_pct"]
    return out.sort_values("yoy_pct", ascending=False)


def table_reporter_partner_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot: reporters (rows) × partners (cols), total export value (USD)."""
    mat = df.pivot_table(
        index="reporterDesc", columns="partnerDesc",
        values="primaryValue", aggfunc="sum", fill_value=0,
    ).round(2)
    return mat.reset_index()


def table_partners_per_reporter(df: pd.DataFrame, n_partners: int = 10) -> pd.DataFrame:
    """For each reporter: top N destination partners by export value."""
    g = df.groupby(["reporterDesc", "partnerDesc"])["primaryValue"].sum().reset_index()
    g = g.sort_values(["reporterDesc", "primaryValue"], ascending=[True, False])
    # Add share within reporter
    reporter_totals = g.groupby("reporterDesc")["primaryValue"].transform("sum")
    g["share_of_reporter_pct"] = (g["primaryValue"] / reporter_totals * 100).round(2)
    top = g.groupby("reporterDesc").head(n_partners)
    top = top.rename(columns={"primaryValue": "value_usd"})
    return top.round(2)


def table_reporters_per_partner(df: pd.DataFrame, n_reporters: int = 10) -> pd.DataFrame:
    """For each partner (importer): top N source reporters by export value."""
    g = df.groupby(["partnerDesc", "reporterDesc"])["primaryValue"].sum().reset_index()
    g = g.sort_values(["partnerDesc", "primaryValue"], ascending=[True, False])
    partner_totals = g.groupby("partnerDesc")["primaryValue"].transform("sum")
    g["share_of_partner_pct"] = (g["primaryValue"] / partner_totals * 100).round(2)
    top = g.groupby("partnerDesc").head(n_reporters)
    top = top.rename(columns={"primaryValue": "value_usd"})
    return top.round(2)


def build_export_flow_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "exports_by_route_year": table_exports_by_route_year(df),
        "top_routes": table_top_routes(df),
        "yoy_by_route": table_yoy_by_route(df),
        "reporter_partner_matrix": table_reporter_partner_matrix(df),
        "partners_per_reporter": table_partners_per_reporter(df),
        "reporters_per_partner": table_reporters_per_partner(df),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PART B – COMMODITY DETAIL (cmdDesc)
# ═══════════════════════════════════════════════════════════════════════════════

def table_route_commodity_breakdown(df: pd.DataFrame, top_n_routes: int = TOP_ROUTES_FOR_COMMODITY) -> pd.DataFrame:
    """For each of top N routes: export value and weight by commodity."""
    df = df.copy()
    df["route"] = _route(df)
    route_totals = df.groupby("route")["primaryValue"].sum().nlargest(top_n_routes).index.tolist()
    sub = df[df["route"].isin(route_totals)]
    g = sub.groupby(["route", "reporterDesc", "partnerDesc", "cmdCode", "cmdDesc"]).agg(
        value_usd=("primaryValue", "sum"),
        weight_kg=("netWgt", "sum"),
        n_transactions=("primaryValue", "count"),
    ).round(2)
    result = g.reset_index()
    # Add share within each route
    route_vals = result.groupby("route")["value_usd"].transform("sum")
    result["share_of_route_pct"] = (result["value_usd"] / route_vals * 100).round(2)
    return result


def table_top_commodities_per_route(
    df: pd.DataFrame,
    top_n_routes: int = TOP_ROUTES_FOR_COMMODITY,
    top_n_commodities: int = 10,
) -> pd.DataFrame:
    """For each of top N routes, top M commodities by export value."""
    df = df.copy()
    df["route"] = _route(df)
    route_totals = df.groupby("route")["primaryValue"].sum().nlargest(top_n_routes).index.tolist()
    sub = df[df["route"].isin(route_totals)]
    g = sub.groupby(["route", "cmdDesc"])[["primaryValue", "netWgt"]].sum().reset_index()
    g = g.sort_values(["route", "primaryValue"], ascending=[True, False])
    top = g.groupby("route").head(top_n_commodities)
    # Add unit value
    top = top.copy()
    top["unit_value_usd_per_kg"] = (
        top["primaryValue"] / top["netWgt"].replace(0, np.nan)
    ).round(4)
    top = top.rename(columns={"primaryValue": "value_usd", "netWgt": "weight_kg"}).round(2)
    return top


def table_commodity_summary_by_route(
    df: pd.DataFrame,
    top_n_routes: int = TOP_ROUTES_FOR_COMMODITY,
) -> pd.DataFrame:
    """Pivot: route (rows) × cmdDesc (cols), export value. Top routes and commodities only."""
    df = df.copy()
    df["route"] = _route(df)
    route_totals = df.groupby("route")["primaryValue"].sum().nlargest(top_n_routes).index.tolist()
    sub = df[df["route"].isin(route_totals)]
    top_cmd = sub.groupby("cmdDesc")["primaryValue"].sum().nlargest(15).index.tolist()
    sub = sub[sub["cmdDesc"].isin(top_cmd)]
    mat = sub.pivot_table(
        index="route", columns="cmdDesc", values="primaryValue",
        aggfunc="sum", fill_value=0,
    ).round(2)
    return mat.reset_index()


def table_top_commodities_overall(df: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    """Top commodities by total export value across all routes."""
    g = df.groupby(["cmdCode", "cmdDesc"]).agg(
        total_value_usd=("primaryValue", "sum"),
        total_weight_kg=("netWgt", "sum"),
        n_routes=("reporterDesc", "nunique"),
        n_transactions=("primaryValue", "count"),
    ).round(2)
    g = g.sort_values("total_value_usd", ascending=False).head(n).reset_index()
    total = df["primaryValue"].sum()
    g["share_pct"] = (g["total_value_usd"] / total * 100).round(2)
    g["unit_value_usd_per_kg"] = (
        g["total_value_usd"] / g["total_weight_kg"].replace(0, np.nan)
    ).round(4)
    return g


def build_commodity_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "route_commodity_breakdown": table_route_commodity_breakdown(df),
        "top_commodities_per_route": table_top_commodities_per_route(df),
        "commodity_summary_by_route": table_commodity_summary_by_route(df),
        "top_commodities_overall": table_top_commodities_overall(df),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PART C – ACADEMIC METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def table_unit_values_by_commodity_year(df: pd.DataFrame) -> pd.DataFrame:
    """Unit value (USD per kg) by commodity and year — proxy for price trends."""
    g = df.groupby(["cmdDesc", "period"]).agg(
        value_usd=("primaryValue", "sum"),
        weight_kg=("netWgt", "sum"),
    ).reset_index()
    g["unit_value_usd_per_kg"] = (
        g["value_usd"] / g["weight_kg"].replace(0, np.nan)
    ).round(4)
    return g.sort_values(["cmdDesc", "period"])


def table_unit_values_by_route_year(df: pd.DataFrame) -> pd.DataFrame:
    """Unit value (USD per kg) by route and year — captures price variation across destinations."""
    df = df.copy()
    df["route"] = _route(df)
    g = df.groupby(["route", "period"]).agg(
        value_usd=("primaryValue", "sum"),
        weight_kg=("netWgt", "sum"),
    ).reset_index()
    g["unit_value_usd_per_kg"] = (
        g["value_usd"] / g["weight_kg"].replace(0, np.nan)
    ).round(4)
    return g.sort_values(["route", "period"])


def _hhi(shares: pd.Series) -> float:
    """Herfindahl–Hirschman Index from percentage shares (0–10,000 scale)."""
    return float((shares ** 2).sum())


def table_market_concentration(df: pd.DataFrame) -> pd.DataFrame:
    """HHI of export destinations per reporter (measures partner concentration).

    HHI interpretation (0–10,000 scale):
      < 1,500  → low concentration (diversified export base)
      1,500–2,500 → moderate concentration
      > 2,500  → high concentration (dependent on few partners)
    """
    g = df.groupby(["reporterDesc", "partnerDesc"])["primaryValue"].sum().reset_index()
    reporter_totals = g.groupby("reporterDesc")["primaryValue"].sum()
    rows = []
    for reporter, total in reporter_totals.items():
        if total == 0:
            continue
        subs = g[g["reporterDesc"] == reporter]
        shares = subs["primaryValue"] / total * 100
        hhi = _hhi(shares)
        n_partners = len(subs)
        top_partner = subs.loc[subs["primaryValue"].idxmax(), "partnerDesc"]
        top_share = shares.max()
        rows.append({
            "reporterDesc": reporter,
            "total_export_usd": round(total, 2),
            "n_partners": n_partners,
            "hhi": round(hhi, 1),
            "concentration": "high" if hhi > 2500 else ("moderate" if hhi > 1500 else "low"),
            "top_partner": top_partner,
            "top_partner_share_pct": round(top_share, 2),
        })
    return pd.DataFrame(rows).sort_values("hhi", ascending=False)


def table_market_concentration_by_year(df: pd.DataFrame) -> pd.DataFrame:
    """HHI of export destinations per reporter per year — tracks diversification over time."""
    g = df.groupby(["reporterDesc", "partnerDesc", "period"])["primaryValue"].sum().reset_index()
    reporter_year_totals = g.groupby(["reporterDesc", "period"])["primaryValue"].sum()
    rows = []
    for (reporter, year), total in reporter_year_totals.items():
        if total == 0:
            continue
        subs = g[(g["reporterDesc"] == reporter) & (g["period"] == year)]
        shares = subs["primaryValue"] / total * 100
        hhi = _hhi(shares)
        rows.append({
            "reporterDesc": reporter,
            "period": int(year),
            "total_export_usd": round(total, 2),
            "n_partners": len(subs),
            "hhi": round(hhi, 1),
            "concentration": "high" if hhi > 2500 else ("moderate" if hhi > 1500 else "low"),
        })
    return pd.DataFrame(rows).sort_values(["reporterDesc", "period"])


def table_commodity_concentration_per_reporter(df: pd.DataFrame) -> pd.DataFrame:
    """HHI of commodity mix per reporter — measures product diversification."""
    g = df.groupby(["reporterDesc", "cmdDesc"])["primaryValue"].sum().reset_index()
    reporter_totals = g.groupby("reporterDesc")["primaryValue"].sum()
    rows = []
    for reporter, total in reporter_totals.items():
        if total == 0:
            continue
        subs = g[g["reporterDesc"] == reporter]
        shares = subs["primaryValue"] / total * 100
        hhi = _hhi(shares)
        top_cmd = subs.loc[subs["primaryValue"].idxmax(), "cmdDesc"]
        top_share = shares.max()
        rows.append({
            "reporterDesc": reporter,
            "total_export_usd": round(total, 2),
            "n_commodities": len(subs),
            "commodity_hhi": round(hhi, 1),
            "concentration": "high" if hhi > 2500 else ("moderate" if hhi > 1500 else "low"),
            "top_commodity": top_cmd,
            "top_commodity_share_pct": round(top_share, 2),
        })
    return pd.DataFrame(rows).sort_values("commodity_hhi", ascending=False)


def table_market_share_by_commodity(df: pd.DataFrame) -> pd.DataFrame:
    """Each reporter's share of total exports for each commodity."""
    g = df.groupby(["cmdDesc", "reporterDesc"])["primaryValue"].sum().reset_index()
    cmd_totals = g.groupby("cmdDesc")["primaryValue"].transform("sum")
    g["market_share_pct"] = (g["primaryValue"] / cmd_totals * 100).round(2)
    g = g.rename(columns={"primaryValue": "value_usd"}).round(2)
    return g.sort_values(["cmdDesc", "market_share_pct"], ascending=[True, False])


def build_academic_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "unit_values_by_commodity_year": table_unit_values_by_commodity_year(df),
        "unit_values_by_route_year": table_unit_values_by_route_year(df),
        "market_concentration": table_market_concentration(df),
        "market_concentration_by_year": table_market_concentration_by_year(df),
        "commodity_concentration_per_reporter": table_commodity_concentration_per_reporter(df),
        "market_share_by_commodity": table_market_share_by_commodity(df),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SAVE TABLES
# ═══════════════════════════════════════════════════════════════════════════════

def save_tables(tables: dict[str, pd.DataFrame], prefix: str = ""):
    ensure_analytics_dir()
    for name, tbl in tables.items():
        if tbl is None or (isinstance(tbl, pd.DataFrame) and tbl.empty):
            continue
        fname = f"table_{prefix}{name}.csv" if prefix else f"table_{name}.csv"
        path = ANALYTICS_OUT_DIR / fname
        tbl.to_csv(path, index=False)
        print(f"  [table] {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPHS – Export flows (reporter → partner)
# ═══════════════════════════════════════════════════════════════════════════════

def graph_top_routes(tables: dict, out_dir: Path, n: int = TOP_N):
    tbl = tables.get("top_routes")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.head(n)
    fig, ax = plt.subplots(figsize=(10, max(4, n * 0.38)))
    y_pos = range(len(tbl))
    bars = ax.barh(y_pos, tbl["total_value_usd"] / 1e6, color="steelblue", height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tbl["route"], fontsize=9)
    ax.set_xlabel("Export Value (Million USD)")
    # Annotate share
    for i, (val, share) in enumerate(zip(tbl["total_value_usd"], tbl["share_pct"])):
        ax.text(val / 1e6 + ax.get_xlim()[1] * 0.01, i, f"{share:.1f}%",
                va="center", fontsize=7, color="grey")
    _style_axes(ax, "Top Export Routes by Trade Value (Reporter → Partner)")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_top_routes.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_top_routes.png")


def graph_yoy_by_route(tables: dict, out_dir: Path, n: int = TOP_N):
    tbl = tables.get("yoy_by_route")
    if tbl is None or tbl.empty or "yoy_pct" not in tbl.columns:
        return
    tbl = tbl.dropna(subset=["yoy_pct"])
    # Show top gainers and losers
    top_gain = tbl.head(n // 2)
    top_loss = tbl.tail(n // 2)
    tbl = pd.concat([top_gain, top_loss]).drop_duplicates()
    if tbl.empty:
        return
    fig, ax = plt.subplots(figsize=(10, max(4, len(tbl) * 0.38)))
    colors = ["#2ca02c" if x >= 0 else "#d62728" for x in tbl["yoy_pct"]]
    y_pos = range(len(tbl))
    ax.barh(y_pos, tbl["yoy_pct"], color=colors, height=0.7)
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tbl["route"], fontsize=8)
    ax.set_xlabel("Year-over-Year Change (%)")
    _style_axes(ax, "YoY Export Value Change by Route (Top Gainers & Losers)")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_yoy_by_route.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_yoy_by_route.png")


def graph_heatmap_reporter_partner(df: pd.DataFrame, out_dir: Path, top_r: int = 12, top_p: int = 12):
    reporters = df.groupby("reporterDesc")["primaryValue"].sum().nlargest(top_r).index.tolist()
    partners = df.groupby("partnerDesc")["primaryValue"].sum().nlargest(top_p).index.tolist()
    sub = df[df["reporterDesc"].isin(reporters) & df["partnerDesc"].isin(partners)]
    mat = sub.pivot_table(
        index="reporterDesc", columns="partnerDesc",
        values="primaryValue", aggfunc="sum", fill_value=0,
    ) / 1e6
    if mat.empty or mat.size < 2:
        return
    fig, ax = plt.subplots(figsize=(max(8, top_p * 0.55), max(6, top_r * 0.45)))
    sns.heatmap(mat, ax=ax, cmap="YlOrRd", fmt=".1f", annot=True, annot_kws={"size": 7},
                cbar_kws={"label": "Export Value (Million USD)"}, linewidths=0.5)
    _style_axes(ax, "Reporter × Partner Export Value (Million USD)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_heatmap_reporter_partner.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_heatmap_reporter_partner.png")


def graph_partners_for_top_reporters(df: pd.DataFrame, out_dir: Path,
                                      n_reporters: int = 5, n_partners: int = 8):
    """For each top reporter, bar chart of top destination partners."""
    reporters = df.groupby("reporterDesc")["primaryValue"].sum().nlargest(n_reporters).index.tolist()
    if not reporters:
        return
    fig, axes = plt.subplots(n_reporters, 1, figsize=(9, 2.8 * n_reporters))
    if n_reporters == 1:
        axes = [axes]
    for ax, rep in zip(axes, reporters):
        sub = df[df["reporterDesc"] == rep].groupby("partnerDesc")["primaryValue"].sum().nlargest(n_partners)
        total = sub.sum()
        sub_m = sub / 1e6
        ax.barh(range(len(sub_m)), sub_m.values, color="steelblue", height=0.7)
        ax.set_yticks(range(len(sub_m)))
        ax.set_yticklabels(sub_m.index, fontsize=9)
        ax.set_xlabel("Million USD")
        # Add share labels
        for i, (val, raw) in enumerate(zip(sub_m.values, sub.values)):
            ax.text(val + ax.get_xlim()[1] * 0.01, i,
                    f"{raw / total * 100:.0f}%", va="center", fontsize=7, color="grey")
        _style_axes(ax, f"Export Destinations: {rep}", source_note=(rep == reporters[-1]))
        ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_partners_per_top_reporter.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_partners_per_top_reporter.png")


def graph_reporters_for_top_partners(df: pd.DataFrame, out_dir: Path,
                                      n_partners: int = 5, n_reporters: int = 8):
    """For each top partner (importer), bar chart of top source reporters."""
    partners = df.groupby("partnerDesc")["primaryValue"].sum().nlargest(n_partners).index.tolist()
    if not partners:
        return
    fig, axes = plt.subplots(n_partners, 1, figsize=(9, 2.8 * n_partners))
    if n_partners == 1:
        axes = [axes]
    for ax, par in zip(axes, partners):
        sub = df[df["partnerDesc"] == par].groupby("reporterDesc")["primaryValue"].sum().nlargest(n_reporters)
        sub_m = sub / 1e6
        ax.barh(range(len(sub_m)), sub_m.values, color="seagreen", height=0.7)
        ax.set_yticks(range(len(sub_m)))
        ax.set_yticklabels(sub_m.index, fontsize=9)
        ax.set_xlabel("Million USD")
        _style_axes(ax, f"Export Sources to: {par}", source_note=(par == partners[-1]))
        ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_reporters_per_top_partner.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_reporters_per_top_partner.png")


def build_export_flow_graphs(df: pd.DataFrame, tables: dict, out_dir: Path):
    if not HAS_PLOTTING:
        return
    graph_top_routes(tables, out_dir)
    graph_yoy_by_route(tables, out_dir)
    graph_heatmap_reporter_partner(df, out_dir)
    graph_partners_for_top_reporters(df, out_dir)
    graph_reporters_for_top_partners(df, out_dir)


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPHS – Commodity detail
# ═══════════════════════════════════════════════════════════════════════════════

def _short_label(s: str, max_len: int = 40) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def graph_commodity_mix_top_routes(tables: dict, out_dir: Path, n_routes: int = 8, n_cmd: int = 8):
    """Stacked bar: for each of top N routes, export value by top commodities."""
    tbl = tables.get("top_commodities_per_route")
    if tbl is None or tbl.empty:
        return
    route_order = tbl.groupby("route")["value_usd"].sum().sort_values(ascending=False).index.tolist()[:n_routes]
    wide = tbl.pivot_table(index="route", columns="cmdDesc", values="value_usd", fill_value=0)
    wide = wide.reindex(route_order).dropna(how="all")
    if wide.empty:
        return
    top_cmd = wide.sum().nlargest(n_cmd).index.tolist()
    wide = wide[top_cmd]
    wide = wide / 1e6
    ax = wide.plot(kind="barh", stacked=True, figsize=(11, max(4, len(wide) * 0.55)), width=0.75)
    ax.set_xlabel("Export Value (Million USD)")
    ax.set_ylabel("Route (Reporter → Partner)")
    _style_axes(ax, "Commodity Composition for Top Export Routes")
    ax.legend(title="Commodity", bbox_to_anchor=(1.02, 1), fontsize=7, title_fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_commodity_mix_top_routes.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_commodity_mix_top_routes.png")


def graph_top_commodities_per_route_single(tables: dict, out_dir: Path, route_index: int = 0, n: int = 10):
    """Horizontal bar: top commodities for the highest-value route."""
    tbl = tables.get("top_commodities_per_route")
    if tbl is None or tbl.empty:
        return
    routes = tbl.groupby("route")["value_usd"].sum().sort_values(ascending=False).index.tolist()
    if route_index >= len(routes):
        route_index = 0
    route = routes[route_index]
    sub = tbl[tbl["route"] == route].sort_values("value_usd", ascending=False).head(n)
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(10, max(4, len(sub) * 0.42)))
    sub = sub.copy()
    sub["cmd_short"] = sub["cmdDesc"].apply(lambda s: _short_label(s, 50))
    y_pos = range(len(sub))
    ax.barh(y_pos, sub["value_usd"] / 1e6, color="mediumpurple", height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(sub["cmd_short"], fontsize=8)
    ax.set_xlabel("Export Value (Million USD)")
    _style_axes(ax, f"Commodity Breakdown: {route}")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_commodity_detail_top_route.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_commodity_detail_top_route.png")


def graph_top_commodities_overall(tables: dict, out_dir: Path, n: int = 13):
    tbl = tables.get("top_commodities_overall")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.head(n).copy()
    tbl["cmd_short"] = tbl["cmdDesc"].apply(lambda s: _short_label(s, 55))
    fig, ax = plt.subplots(figsize=(10, max(4, n * 0.42)))
    y_pos = range(len(tbl))
    ax.barh(y_pos, tbl["total_value_usd"] / 1e6, color="darkorange", height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tbl["cmd_short"], fontsize=8)
    ax.set_xlabel("Export Value (Million USD)")
    # Annotate share
    for i, share in enumerate(tbl["share_pct"]):
        ax.text(tbl.iloc[i]["total_value_usd"] / 1e6 + ax.get_xlim()[1] * 0.01, i,
                f"{share:.1f}%", va="center", fontsize=7, color="grey")
    _style_axes(ax, "Top Commodities by Total Export Value")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(out_dir / "fig_top_commodities_overall.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_top_commodities_overall.png")


def build_commodity_graphs(df: pd.DataFrame, tables: dict, out_dir: Path):
    if not HAS_PLOTTING:
        return
    graph_commodity_mix_top_routes(tables, out_dir)
    graph_top_commodities_per_route_single(tables, out_dir)
    graph_top_commodities_overall(tables, out_dir)


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPHS – Academic metrics
# ═══════════════════════════════════════════════════════════════════════════════

def graph_market_concentration(tables: dict, out_dir: Path):
    """Bar chart of HHI per reporter with concentration threshold lines."""
    tbl = tables.get("market_concentration")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.sort_values("hhi", ascending=True)
    fig, ax = plt.subplots(figsize=(10, max(4, len(tbl) * 0.45)))
    colors = []
    for h in tbl["hhi"]:
        if h > 2500:
            colors.append("#d62728")
        elif h > 1500:
            colors.append("#ff7f0e")
        else:
            colors.append("#2ca02c")
    y_pos = range(len(tbl))
    ax.barh(y_pos, tbl["hhi"], color=colors, height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tbl["reporterDesc"], fontsize=9)
    ax.set_xlabel("Herfindahl–Hirschman Index (HHI)")
    ax.axvline(1500, color="orange", linestyle="--", linewidth=0.8, label="Moderate (1,500)")
    ax.axvline(2500, color="red", linestyle="--", linewidth=0.8, label="High (2,500)")
    ax.legend(fontsize=8, loc="lower right")
    _style_axes(ax, "Export Destination Concentration by Reporter (HHI)")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_market_concentration.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_market_concentration.png")


def graph_unit_values_by_commodity(tables: dict, out_dir: Path):
    """Grouped bar chart of unit values by commodity and year."""
    tbl = tables.get("unit_values_by_commodity_year")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.dropna(subset=["unit_value_usd_per_kg"])
    if tbl.empty:
        return
    # Only show commodities with meaningful weight data
    valid = tbl.groupby("cmdDesc")["weight_kg"].sum()
    valid = valid[valid > 0].index.tolist()
    tbl = tbl[tbl["cmdDesc"].isin(valid)]
    if tbl.empty:
        return
    piv = tbl.pivot_table(index="cmdDesc", columns="period", values="unit_value_usd_per_kg")
    piv = piv.sort_values(piv.columns[-1], ascending=True)
    piv.index = [_short_label(s, 45) for s in piv.index]
    ax = piv.plot(kind="barh", figsize=(10, max(4, len(piv) * 0.5)), width=0.7)
    ax.set_xlabel("Unit Value (USD per kg)")
    ax.set_ylabel("")
    _style_axes(ax, "Export Unit Values by Commodity and Year (USD/kg)")
    ax.legend(title="Year", fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_unit_values_by_commodity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_unit_values_by_commodity.png")


def graph_commodity_concentration(tables: dict, out_dir: Path):
    """Bar chart of commodity HHI per reporter."""
    tbl = tables.get("commodity_concentration_per_reporter")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.sort_values("commodity_hhi", ascending=True)
    fig, ax = plt.subplots(figsize=(10, max(4, len(tbl) * 0.45)))
    colors = []
    for h in tbl["commodity_hhi"]:
        if h > 2500:
            colors.append("#d62728")
        elif h > 1500:
            colors.append("#ff7f0e")
        else:
            colors.append("#2ca02c")
    y_pos = range(len(tbl))
    ax.barh(y_pos, tbl["commodity_hhi"], color=colors, height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(tbl["reporterDesc"], fontsize=9)
    ax.set_xlabel("Herfindahl–Hirschman Index (HHI)")
    ax.axvline(1500, color="orange", linestyle="--", linewidth=0.8, label="Moderate (1,500)")
    ax.axvline(2500, color="red", linestyle="--", linewidth=0.8, label="High (2,500)")
    ax.legend(fontsize=8, loc="lower right")
    _style_axes(ax, "Commodity Export Concentration by Reporter (HHI)")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_commodity_concentration.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_commodity_concentration.png")


def build_academic_graphs(tables: dict, out_dir: Path):
    if not HAS_PLOTTING:
        return
    graph_market_concentration(tables, out_dir)
    graph_unit_values_by_commodity(tables, out_dir)
    graph_commodity_concentration(tables, out_dir)


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAPHS – INSIGHT GRAPHS (7 new visualisations)
# ═══════════════════════════════════════════════════════════════════════════════

def graph_hhi_year_comparison(acad_tables: dict, out_dir: Path):
    """#1 — Paired bar: HHI per reporter in 2022 vs 2023, showing diversification shifts."""
    tbl = acad_tables.get("market_concentration_by_year")
    if tbl is None or tbl.empty:
        return
    piv = tbl.pivot_table(index="reporterDesc", columns="period", values="hhi")
    if piv.shape[1] < 2:
        return
    years = sorted(piv.columns)
    piv = piv.sort_values(years[-1], ascending=True)

    fig, ax = plt.subplots(figsize=(11, max(5, len(piv) * 0.5)))
    y = np.arange(len(piv))
    bar_h = 0.35
    ax.barh(y + bar_h / 2, piv[years[0]], height=bar_h, color="#4c72b0", label=str(int(years[0])))
    ax.barh(y - bar_h / 2, piv[years[1]], height=bar_h, color="#dd8452", label=str(int(years[1])))
    ax.set_yticks(y)
    ax.set_yticklabels(piv.index, fontsize=9)
    ax.set_xlabel("Herfindahl–Hirschman Index (HHI)")
    ax.axvline(1500, color="orange", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axvline(2500, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.text(1500, len(piv) - 0.3, "Moderate", fontsize=7, color="orange", ha="center")
    ax.text(2500, len(piv) - 0.3, "High", fontsize=7, color="red", ha="center")
    # Annotate delta
    for i, reporter in enumerate(piv.index):
        v0 = piv.loc[reporter, years[0]]
        v1 = piv.loc[reporter, years[1]]
        if pd.notna(v0) and pd.notna(v1):
            delta = v1 - v0
            sign = "+" if delta >= 0 else ""
            clr = "#d62728" if delta > 0 else "#2ca02c"
            x_pos = max(v0, v1) + 100
            ax.text(x_pos, i, f"{sign}{delta:,.0f}", va="center", fontsize=7,
                    color=clr, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right")
    _style_axes(ax, "Destination Concentration Shift: 2022 vs 2023 (HHI)")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_hhi_year_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_hhi_year_comparison.png")


def graph_yoy_absolute_change(flow_tables: dict, out_dir: Path, n: int = 10):
    """#2 — Top gainers and losers by absolute USD change (not misleading %)."""
    tbl = flow_tables.get("yoy_by_route")
    if tbl is None or tbl.empty or "abs_change_usd" not in tbl.columns:
        return
    tbl = tbl.dropna(subset=["abs_change_usd"]).copy()
    if tbl.empty:
        return
    top_gain = tbl.nlargest(n, "abs_change_usd")
    top_loss = tbl.nsmallest(n, "abs_change_usd")
    combined = pd.concat([top_gain, top_loss]).drop_duplicates(subset=["route"])
    combined = combined.sort_values("abs_change_usd", ascending=True)

    fig, ax = plt.subplots(figsize=(11, max(5, len(combined) * 0.38)))
    colors = ["#2ca02c" if x >= 0 else "#d62728" for x in combined["abs_change_usd"]]
    y_pos = range(len(combined))
    ax.barh(y_pos, combined["abs_change_usd"] / 1e6, color=colors, height=0.7)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(combined["route"], fontsize=8)
    ax.set_xlabel("Absolute Change in Export Value (Million USD)")
    # Annotate YoY %
    for i, (absv, pct) in enumerate(zip(combined["abs_change_usd"], combined["yoy_pct"])):
        if pd.notna(pct):
            sign = "+" if pct >= 0 else ""
            ax.text(absv / 1e6 + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.01 * (1 if absv >= 0 else -1),
                    i, f"{sign}{pct:.0f}%", va="center", fontsize=7, color="grey",
                    ha="left" if absv >= 0 else "right")
    _style_axes(ax, "Largest YoY Export Value Changes (Absolute, Million USD)")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_yoy_absolute_change.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_yoy_absolute_change.png")


def graph_market_share_by_commodity(df: pd.DataFrame, out_dir: Path):
    """#3 — Stacked horizontal bar: reporter market share within each commodity."""
    g = df.groupby(["cmdDesc", "reporterDesc"])["primaryValue"].sum().reset_index()
    cmd_totals = g.groupby("cmdDesc")["primaryValue"].sum().sort_values(ascending=False)
    # Use short labels for commodities
    cmd_order = cmd_totals.index.tolist()
    g["cmd_short"] = g["cmdDesc"].apply(lambda s: _short_label(s, 50))
    short_order = [_short_label(s, 50) for s in cmd_order]

    piv = g.pivot_table(index="cmd_short", columns="reporterDesc", values="primaryValue", fill_value=0)
    piv = piv.reindex(short_order)
    piv = piv / 1e6
    # Sort columns by total contribution
    col_order = piv.sum().sort_values(ascending=False).index.tolist()
    piv = piv[col_order]

    cmap = plt.cm.get_cmap("tab20", len(col_order))
    colors = [cmap(i) for i in range(len(col_order))]

    fig, ax = plt.subplots(figsize=(12, max(5, len(piv) * 0.48)))
    piv.plot(kind="barh", stacked=True, ax=ax, color=colors, width=0.75)
    ax.set_xlabel("Export Value (Million USD)")
    ax.set_ylabel("")
    _style_axes(ax, "Market Share by Commodity: Which Reporters Dominate")
    ax.legend(title="Reporter", bbox_to_anchor=(1.02, 1), fontsize=7, title_fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_market_share_by_commodity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_market_share_by_commodity.png")


def graph_dual_concentration_scatter(acad_tables: dict, out_dir: Path):
    """#4 — Scatter: commodity HHI (x) vs destination HHI (y) per reporter.
    Reveals vulnerability profile — top-right = most concentrated/vulnerable."""
    dest = acad_tables.get("market_concentration")
    comm = acad_tables.get("commodity_concentration_per_reporter")
    if dest is None or comm is None or dest.empty or comm.empty:
        return
    merged = dest[["reporterDesc", "hhi", "total_export_usd"]].merge(
        comm[["reporterDesc", "commodity_hhi"]],
        on="reporterDesc", how="inner",
    )
    if merged.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 8))
    # Bubble size proportional to trade value
    max_val = merged["total_export_usd"].max()
    sizes = (merged["total_export_usd"] / max_val * 800) + 50

    scatter = ax.scatter(
        merged["commodity_hhi"], merged["hhi"],
        s=sizes, alpha=0.65, c="#4c72b0", edgecolors="white", linewidth=1.2,
    )
    # Label each point
    for _, row in merged.iterrows():
        ax.annotate(
            row["reporterDesc"],
            (row["commodity_hhi"], row["hhi"]),
            textcoords="offset points", xytext=(8, 5),
            fontsize=8, fontweight="bold",
        )
    # Quadrant lines
    ax.axvline(2500, color="grey", linestyle="--", linewidth=0.7, alpha=0.5)
    ax.axhline(2500, color="grey", linestyle="--", linewidth=0.7, alpha=0.5)
    # Quadrant labels
    ax.text(1200, 1200, "DIVERSIFIED\n(products & destinations)", fontsize=8,
            color="#2ca02c", ha="center", alpha=0.7, style="italic")
    ax.text(7500, 1200, "Product-concentrated\nbut destination-diversified", fontsize=8,
            color="#ff7f0e", ha="center", alpha=0.7, style="italic")
    ax.text(1200, 8000, "Destination-concentrated\nbut product-diversified", fontsize=8,
            color="#ff7f0e", ha="center", alpha=0.7, style="italic")
    ax.text(7500, 8000, "HIGHLY VULNERABLE\n(single product, single dest.)", fontsize=8,
            color="#d62728", ha="center", alpha=0.7, style="italic")
    ax.set_xlabel("Commodity Concentration (HHI)", fontsize=10)
    ax.set_ylabel("Destination Concentration (HHI)", fontsize=10)
    ax.set_xlim(0, 10500)
    ax.set_ylim(0, 10500)
    _style_axes(ax, "Export Vulnerability: Product vs Destination Concentration")
    ax.annotate("Bubble size = total export value", xy=(0.02, 0.02),
                xycoords="axes fraction", fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_dual_concentration_scatter.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_dual_concentration_scatter.png")


def graph_unit_value_slope(acad_tables: dict, out_dir: Path):
    """#5 — Slope chart: unit value per commodity from 2022 to 2023."""
    tbl = acad_tables.get("unit_values_by_commodity_year")
    if tbl is None or tbl.empty:
        return
    tbl = tbl.dropna(subset=["unit_value_usd_per_kg"])
    piv = tbl.pivot_table(index="cmdDesc", columns="period", values="unit_value_usd_per_kg")
    years = sorted(piv.columns)
    if len(years) < 2:
        return
    # Only commodities present in both years
    piv = piv.dropna()
    if piv.empty:
        return
    piv = piv.sort_values(years[-1], ascending=False)
    piv.index = [_short_label(s, 45) for s in piv.index]

    fig, ax = plt.subplots(figsize=(10, max(5, len(piv) * 0.55)))
    y0, y1 = 0.15, 0.85  # x-positions for the two years
    cmap = plt.cm.get_cmap("tab10", len(piv))

    for i, (cmd, row) in enumerate(piv.iterrows()):
        v0, v1 = row[years[0]], row[years[1]]
        color = cmap(i)
        ax.plot([y0, y1], [v0, v1], marker="o", markersize=6, color=color,
                linewidth=2, alpha=0.8)
        # Label left
        ax.text(y0 - 0.02, v0, f"{cmd}  ${v0:.2f}", ha="right", va="center",
                fontsize=7, color=color)
        # Label right with change
        pct = (v1 - v0) / v0 * 100 if v0 != 0 else 0
        sign = "+" if pct >= 0 else ""
        ax.text(y1 + 0.02, v1, f"${v1:.2f} ({sign}{pct:.0f}%)", ha="left",
                va="center", fontsize=7, color=color, fontweight="bold")

    ax.set_xlim(-0.4, 1.4)
    ax.set_xticks([y0, y1])
    ax.set_xticklabels([str(int(years[0])), str(int(years[1]))], fontsize=11, fontweight="bold")
    ax.set_ylabel("Unit Value (USD per kg)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Unit Value Trends by Commodity (USD/kg)", fontsize=12,
                 fontweight="bold", pad=12)
    ax.annotate("Source: UN Comtrade (exports only)", xy=(0.99, -0.06),
                xycoords="axes fraction", fontsize=7, color="grey", ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_unit_value_slope.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_unit_value_slope.png")


def graph_route_commodity_pies(df: pd.DataFrame, out_dir: Path, n_routes: int = 5):
    """#6 — Pie/donut charts: commodity composition for top 5 routes."""
    df = df.copy()
    df["route"] = _route(df)
    route_totals = df.groupby("route")["primaryValue"].sum().nlargest(n_routes)
    routes = route_totals.index.tolist()
    if not routes:
        return

    fig, axes = plt.subplots(1, n_routes, figsize=(4.5 * n_routes, 5))
    if n_routes == 1:
        axes = [axes]

    cmap = plt.cm.get_cmap("Set2", 8)

    for ax, route in zip(axes, routes):
        sub = df[df["route"] == route].groupby("cmdDesc")["primaryValue"].sum().sort_values(ascending=False)
        # Group small commodities into "Other"
        total = sub.sum()
        shares = sub / total * 100
        main = shares[shares >= 2.0]
        other_val = sub[shares < 2.0].sum()
        plot_data = sub[main.index]
        if other_val > 0:
            plot_data = pd.concat([plot_data, pd.Series({"Other": other_val})])

        labels = [_short_label(s, 28) for s in plot_data.index]
        colors = [cmap(i) for i in range(len(plot_data))]
        wedges, texts, autotexts = ax.pie(
            plot_data.values, labels=None, autopct="%1.0f%%",
            colors=colors, pctdistance=0.78, startangle=90,
            wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 1.5},
        )
        for t in autotexts:
            t.set_fontsize(7)
            t.set_fontweight("bold")
        ax.legend(labels, loc="center left", bbox_to_anchor=(-0.15, -0.25),
                  fontsize=6, ncol=1, frameon=False)
        route_val = route_totals[route]
        ax.set_title(f"{route}\n({_fmt_usd(route_val)})", fontsize=9, fontweight="bold", pad=8)

    fig.suptitle("Commodity Composition of Top Export Routes", fontsize=13,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_route_commodity_pies.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_route_commodity_pies.png")


def graph_reporter_commodity_stacked(df: pd.DataFrame, out_dir: Path, n_reporters: int = 10):
    """#7 — Stacked horizontal bar: trade value by reporter, coloured by commodity."""
    reporter_totals = df.groupby("reporterDesc")["primaryValue"].sum().nlargest(n_reporters)
    reporters = reporter_totals.index.tolist()
    sub = df[df["reporterDesc"].isin(reporters)]

    g = sub.groupby(["reporterDesc", "cmdDesc"])["primaryValue"].sum().reset_index()
    g["cmd_short"] = g["cmdDesc"].apply(lambda s: _short_label(s, 35))

    # Identify top commodities overall for consistent colouring
    top_cmds = g.groupby("cmd_short")["primaryValue"].sum().nlargest(8).index.tolist()
    g["cmd_label"] = g["cmd_short"].apply(lambda s: s if s in top_cmds else "Other")
    g2 = g.groupby(["reporterDesc", "cmd_label"])["primaryValue"].sum().reset_index()

    piv = g2.pivot_table(index="reporterDesc", columns="cmd_label", values="primaryValue", fill_value=0)
    piv = piv.reindex(reporters)
    piv = piv / 1e6
    # Sort columns: "Other" last
    cols = [c for c in piv.columns if c != "Other"]
    cols_sorted = sorted(cols, key=lambda c: piv[c].sum(), reverse=True)
    if "Other" in piv.columns:
        cols_sorted.append("Other")
    piv = piv[cols_sorted]

    n_cols = len(piv.columns)
    cmap = plt.cm.get_cmap("tab10", max(n_cols, 10))
    colors = [cmap(i) for i in range(n_cols)]
    # Make "Other" grey
    if "Other" in piv.columns:
        colors[-1] = "#cccccc"

    fig, ax = plt.subplots(figsize=(12, max(5, len(piv) * 0.5)))
    piv.plot(kind="barh", stacked=True, ax=ax, color=colors, width=0.75)
    ax.set_xlabel("Export Value (Million USD)")
    ax.set_ylabel("")
    # Annotate total
    for i, reporter in enumerate(piv.index):
        total = piv.loc[reporter].sum()
        ax.text(total + ax.get_xlim()[1] * 0.005, i, _fmt_usd(total * 1e6),
                va="center", fontsize=7, color="grey")
    _style_axes(ax, "Export Value by Reporter — Commodity Composition")
    ax.legend(title="Commodity", bbox_to_anchor=(1.02, 1), fontsize=7, title_fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_reporter_commodity_stacked.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [fig] fig_reporter_commodity_stacked.png")


def build_insight_graphs(df: pd.DataFrame, flow_tables: dict, acad_tables: dict, out_dir: Path):
    """Build all 7 insight graphs."""
    if not HAS_PLOTTING:
        return
    graph_hhi_year_comparison(acad_tables, out_dir)
    graph_yoy_absolute_change(flow_tables, out_dir)
    graph_market_share_by_commodity(df, out_dir)
    graph_dual_concentration_scatter(acad_tables, out_dir)
    graph_unit_value_slope(acad_tables, out_dir)
    graph_route_commodity_pies(df, out_dir)
    graph_reporter_commodity_stacked(df, out_dir)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not MERGED_CSV.exists():
        print(f"[Error] Merged file not found: {MERGED_CSV}")
        print("Run merge_output_csv.py first.")
        return
    df = load_data(MERGED_CSV)
    print(f"Loaded {len(df):,} rows from {MERGED_CSV.name}")

    # ── Part 0: Data quality ──
    print("\n" + "=" * 60)
    print("  PART 0 – DATA QUALITY REPORT")
    print("=" * 60)
    quality = validate_data(df)
    ensure_analytics_dir()
    quality.to_csv(ANALYTICS_OUT_DIR / "table_data_quality.csv", index=False)
    print(quality.to_string(index=False))

    desc = descriptive_statistics(df)
    desc.to_csv(ANALYTICS_OUT_DIR / "table_descriptive_statistics.csv")
    print("\nDescriptive statistics (primaryValue, netWgt):")
    print(desc.to_string())

    # ── Part A: Export flows ──
    print("\n" + "=" * 60)
    print("  PART A – EXPORT FLOWS (Reporter → Partner)")
    print("=" * 60)
    flow_tables = build_export_flow_tables(df)
    print("Tables:")
    save_tables(flow_tables)
    print("Graphs:")
    if HAS_PLOTTING:
        build_export_flow_graphs(df, flow_tables, ANALYTICS_OUT_DIR)
    else:
        print("  [skip] Install matplotlib and seaborn for graphs.")

    # ── Part B: Commodity detail ──
    print("\n" + "=" * 60)
    print("  PART B – COMMODITY DETAIL (cmdDesc)")
    print("=" * 60)
    cmd_tables = build_commodity_tables(df)
    print("Tables:")
    save_tables(cmd_tables)
    print("Graphs:")
    if HAS_PLOTTING:
        build_commodity_graphs(df, cmd_tables, ANALYTICS_OUT_DIR)

    # ── Part C: Academic metrics ──
    print("\n" + "=" * 60)
    print("  PART C – ACADEMIC METRICS")
    print("=" * 60)
    acad_tables = build_academic_tables(df)
    print("Tables:")
    save_tables(acad_tables)
    print("Graphs:")
    if HAS_PLOTTING:
        build_academic_graphs(acad_tables, ANALYTICS_OUT_DIR)

    # ── Part D: Insight graphs ──
    print("\n" + "=" * 60)
    print("  PART D – INSIGHT GRAPHS")
    print("=" * 60)
    if HAS_PLOTTING:
        build_insight_graphs(df, flow_tables, acad_tables, ANALYTICS_OUT_DIR)
    else:
        print("  [skip] Install matplotlib and seaborn for graphs.")

    # ── Console summary ──
    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    total_value = df["primaryValue"].sum()
    print(f"Total export value: {_fmt_usd(total_value)}")
    print(f"Periods: {sorted(int(p) for p in df['period'].unique())}")
    print(f"Reporters: {df['reporterDesc'].nunique()}, Partners: {df['partnerDesc'].nunique()}")
    print(f"Commodities: {df['cmdDesc'].nunique()}")

    print("\n--- Top 5 routes ---")
    print(flow_tables["top_routes"][["route", "total_value_usd", "share_pct"]].head(5).to_string(index=False))

    print("\n--- Market concentration (HHI by reporter) ---")
    print(acad_tables["market_concentration"][["reporterDesc", "hhi", "concentration", "top_partner"]].to_string(index=False))

    print("\n--- Top commodities ---")
    print(cmd_tables["top_commodities_overall"][["cmdDesc", "total_value_usd", "share_pct", "unit_value_usd_per_kg"]].head(5).to_string(index=False))

    print(f"\n[OK] Analytics written to {ANALYTICS_OUT_DIR}")


if __name__ == "__main__":
    main()
