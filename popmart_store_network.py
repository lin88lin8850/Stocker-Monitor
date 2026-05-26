from pathlib import Path

import pandas as pd
import plotly.express as px


POPMART_STORE_NETWORK_FILE = Path("data/popmart_store_network.csv")


def load_popmart_store_network_data() -> pd.DataFrame:
    if not POPMART_STORE_NETWORK_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(POPMART_STORE_NETWORK_FILE)
    required = {"report_date", "scope", "standard_stores", "roboshops"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    data = df.copy()
    data["report_date"] = pd.to_datetime(data["report_date"], errors="coerce")
    data["standard_stores"] = pd.to_numeric(data["standard_stores"], errors="coerce")
    data["roboshops"] = pd.to_numeric(data["roboshops"], errors="coerce")
    data = data.dropna(subset=["report_date", "scope"]).sort_values("report_date")
    return data


def build_popmart_store_network_plot(network_df: pd.DataFrame):
    if network_df.empty:
        return None

    rows: list[dict] = []

    global_df = network_df[network_df["scope"] == "global"].copy()
    if not global_df.empty:
        for _, row in global_df.dropna(subset=["standard_stores"]).iterrows():
            rows.append(
                {
                    "report_date": row["report_date"],
                    "series": "全球标准店数量",
                    "value": float(row["standard_stores"]),
                }
            )
        for _, row in global_df.dropna(subset=["roboshops"]).iterrows():
            rows.append(
                {
                    "report_date": row["report_date"],
                    "series": "全球机器人店数量",
                    "value": float(row["roboshops"]),
                }
            )
        for _, row in global_df.dropna(subset=["standard_stores", "roboshops"]).iterrows():
            rows.append(
                {
                    "report_date": row["report_date"],
                    "series": "全球总网点数量（标准店+机器人店）",
                    "value": float(row["standard_stores"] + row["roboshops"]),
                }
            )

    plot_df = pd.DataFrame(rows)
    if plot_df.empty:
        return None

    fig = px.line(
        plot_df,
        x="report_date",
        y="value",
        color="series",
        markers=True,
        template="plotly_white",
        title="<b>泡泡玛特全球标准店与机器人店数量变化</b>",
        labels={"value": "数量（个）", "report_date": "报告期", "series": "口径"},
    )
    fig.update_traces(hovertemplate="%{fullData.name}<br>%{x|%Y-%m-%d}<br>%{y:.0f}个<extra></extra>")
    return fig
