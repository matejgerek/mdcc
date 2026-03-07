---
title: Example Market Snapshot
author: mdcc
date: 2026-03-07
---

# Example Market Snapshot

This example document reads external data files from the local `data/` folder.
It demonstrates how `mdcc` can combine narrative text, JSON input, CSV input,
tables, charts, and block metadata in a single compiled report.

## Data Sources

The report uses two files:

- `data/market-data.json` for monthly revenue, cost, and customer metrics
- `data/region-targets.csv` for region-level operating targets

Every executable block is isolated, so each block reloads the data it needs.
That is expected behavior in `mdcc`.

## Dataset Summary

```mdcc_table caption="Dataset summary for the bundled market inputs" label="tbl:dataset-summary"
market = pd.read_json("data/market-data.json")
targets = pd.read_csv("data/region-targets.csv")

summary = pd.DataFrame({
    "metric": [
        "Market rows",
        "Regions",
        "Months",
        "Total revenue",
        "Total customers",
        "Target rows",
    ],
    "value": [
        len(market),
        market["region"].nunique(),
        market["month"].nunique(),
        int(market["revenue"].sum()),
        int(market["customers"].sum()),
        len(targets),
    ],
})

summary
```

## Revenue Trend

The first chart reads the JSON file and plots monthly revenue trajectories by
region.

```mdcc_chart caption="Monthly revenue trajectories by region" label="fig:revenue-trend"
market = pd.read_json("data/market-data.json")
month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]

alt.Chart(market).mark_line(point=True, strokeWidth=3).encode(
    x=alt.X("month:N", sort=month_order, title="Month"),
    y=alt.Y("revenue:Q", title="Revenue"),
    color=alt.Color("region:N", title="Region"),
    tooltip=["month:N", "region:N", "revenue:Q", "customers:Q"],
).properties(
    width=640,
    height=320,
    title="Revenue Trend by Region",
)
```

This is a reference to the chart above @fig:revenue-trend.

## Target Attainment

This table joins the JSON and CSV files so the report can compare June actuals
against target expectations.

```mdcc_table caption="June revenue and customer attainment versus targets" label="tbl:target-attainment"
market = pd.read_json("data/market-data.json")
targets = pd.read_csv("data/region-targets.csv")

june = market[market["month"] == "Jun"].copy()
june["gross_profit"] = june["revenue"] - june["cost"]

merged = june.merge(targets, on="region", how="left")
merged["revenue_attainment_pct"] = (
    (merged["revenue"] / merged["revenue_target"]) * 100
).round(1)
merged["customer_attainment_pct"] = (
    (merged["customers"] / merged["customer_target"]) * 100
).round(1)

merged[
    [
        "region",
        "revenue",
        "revenue_target",
        "revenue_attainment_pct",
        "customers",
        "customer_target",
        "customer_attainment_pct",
        "gross_profit",
        "strategy_band",
        "priority",
    ]
].sort_values(["priority", "revenue_attainment_pct"], ascending=[True, False])
```

## Bubble View

This chart uses the same joined data to compare customer scale, revenue, and
gross profit in one view.

```mdcc_chart caption="June customer scale, revenue, and gross profit by strategy band" label="fig:bubble-view"
market = pd.read_json("data/market-data.json")
targets = pd.read_csv("data/region-targets.csv")

june = market[market["month"] == "Jun"].copy()
june["gross_profit"] = june["revenue"] - june["cost"]
merged = june.merge(targets, on="region", how="left")

alt.Chart(merged).mark_circle(opacity=0.82).encode(
    x=alt.X("customers:Q", title="Customers"),
    y=alt.Y("revenue:Q", title="Revenue"),
    size=alt.Size("gross_profit:Q", title="Gross Profit"),
    color=alt.Color("strategy_band:N", title="Strategy Band"),
    tooltip=[
        "region:N",
        "strategy_band:N",
        "revenue:Q",
        "revenue_target:Q",
        "customers:Q",
        "gross_profit:Q",
    ],
).properties(
    width=640,
    height=320,
    title="June Revenue vs Customers",
)
```

## Closing Note

The important part of this example is not the fake business data. It is the
file layout and runtime behavior:

- the source document stays plain Markdown
- the data files live beside it under `data/`
- each block reads from disk explicitly
- the compiler renders narrative, charts, and tables into one PDF
