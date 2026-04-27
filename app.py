import os

import pandas as pd
import plotly.express as px
import streamlit as st
from utils import (
    COMPANY_SYMBOLS,
    FOCUS_METRICS,
    METRIC_LABELS,
    PERCENT_COLUMNS,
    VALUE_LABELS,
)

DATA_DIR = "data"
REQUIRED_COLUMNS = [
    "report_date",
    "report_name",
    "report_period",
    "quarter_name",
    "metric_name",
    "value",
]
VALUE_COLUMNS = ["value", "yoy"]
MONEY_METRICS = {"parent_holder_net_profit", "operating_income_total"}
PERCENT_VALUE_METRICS = {"assets_debt_ratio", "index_weighted_avg_roe"}


def choose_chinese_unit(series: pd.Series) -> tuple[float, str]:
    """Choose a human-friendly Chinese unit by data magnitude."""
    max_abs = series.abs().max()
    if pd.isna(max_abs):
        return 1.0, ""
    if max_abs >= 1e8:
        return 1e8, "亿"
    if max_abs >= 1e7:
        return 1e7, "千万"
    if max_abs >= 1e6:
        return 1e6, "百万"
    if max_abs >= 1e4:
        return 1e4, "万"
    return 1.0, ""


def list_company_names() -> list[str]:
    data_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".csv")])
    if not data_files:
        st.error("未在 data 目录找到 CSV 数据文件。")
        st.stop()
    return [f.replace(".csv", "") for f in data_files]


def select_company(company_names: list[str]) -> str:
    # Persist selection across reruns.
    if (
        "selected_company_name" not in st.session_state
        or st.session_state["selected_company_name"] not in company_names
    ):
        st.session_state["selected_company_name"] = company_names[0]

    st.sidebar.subheader("公司")
    default_idx = company_names.index(st.session_state["selected_company_name"])
    selected_company = st.sidebar.radio(
        "选择公司",
        company_names,
        index=default_idx,
        label_visibility="collapsed",
    )
    st.session_state["selected_company_name"] = selected_company
    return selected_company


def load_company_data(company_name: str) -> pd.DataFrame:
    selected_file = f"{company_name}.csv"
    df = pd.read_csv(os.path.join(DATA_DIR, selected_file))
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        st.error(f"数据缺少必要字段: {', '.join(missing_columns)}")
        st.stop()
    return df


def prepare_dashboard_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df = df.dropna(subset=["report_date", "metric_name"])
    df = df[df["report_name"].astype(str).str.contains("年报", na=False)]
    df = df[df["metric_name"].isin(FOCUS_METRICS)]
    return df


def get_metrics(df: pd.DataFrame) -> list[str]:
    metrics = [metric for metric in FOCUS_METRICS if metric in set(df["metric_name"].dropna())]
    if not metrics:
        st.warning("当前公司在目标指标列表中没有可展示数据。")
        st.stop()
    return metrics


def select_value_dimension(df: pd.DataFrame, metrics: list[str]) -> tuple[str, str]:
    available_value_columns = [
        col
        for col in VALUE_COLUMNS
        if col in df.columns
        and any(df[df["metric_name"] == metric][col].notna().any() for metric in metrics)
    ]
    if not available_value_columns:
        st.warning("当前指标没有可展示的数值维度。")
        st.stop()

    value_options = {VALUE_LABELS.get(col, col): col for col in available_value_columns}
    selected_value_label = st.selectbox("选择数值维度", list(value_options.keys()))
    return selected_value_label, value_options[selected_value_label]


def build_metric_plot(metric_df: pd.DataFrame, metric: str, value_label: str, value_column: str):
    plot_df = metric_df.copy()
    plot_y_column = value_column
    display_value_label = value_label
    value_unit = ""

    if value_column == "value" and metric in MONEY_METRICS:
        value_divisor, value_unit = choose_chinese_unit(plot_df[value_column])
        if value_divisor != 1.0:
            plot_y_column = "value_scaled"
            plot_df[plot_y_column] = plot_df[value_column] / value_divisor
            display_value_label = f"{value_label}（{value_unit}）"

    if value_column in PERCENT_COLUMNS:
        plot_y_column = "value_percent"
        plot_df[plot_y_column] = plot_df[value_column] * 100

    fig = px.line(
        plot_df,
        x="report_date",
        y=plot_y_column,
        markers=True,
        title=METRIC_LABELS.get(metric, metric),
        template="plotly_white",
        hover_data=["report_name"],
        labels={plot_y_column: display_value_label},
    )

    if value_column in PERCENT_COLUMNS:
        fig.update_yaxes(ticksuffix="%")
        fig.update_traces(hovertemplate="%{customdata[0]}<br>%{y:.2f}%<extra></extra>")
    else:
        value_suffix = value_unit if value_column == "value" else ""
        if value_column == "value" and metric in PERCENT_VALUE_METRICS:
            value_suffix = "%"
        fig.update_traces(
            hovertemplate=f"%{{customdata[0]}}<br>%{{y:.2f}}{value_suffix}<extra></extra>"
        )
    return fig


def build_metric_table(
    metric_df: pd.DataFrame, metric: str, value_label: str, value_column: str
) -> pd.DataFrame:
    table_df = metric_df[
        [
            "report_date",
            "report_name",
            "report_period",
            "quarter_name",
            "metric_name_cn",
            value_column,
        ]
    ].copy()
    table_df = table_df.rename(columns={"metric_name_cn": "指标"})

    if value_column in PERCENT_COLUMNS:
        table_df[value_label] = table_df[value_column].map(lambda x: f"{x * 100:.2f}%")
    elif value_column == "value" and metric in MONEY_METRICS:
        value_divisor, value_unit = choose_chinese_unit(table_df[value_column])
        if value_divisor != 1.0:
            table_df[value_label] = table_df[value_column].map(
                lambda x: f"{x / value_divisor:.2f}{value_unit}"
            )
        else:
            table_df[value_label] = table_df[value_column].map(lambda x: f"{x:.2f}")
    elif value_column == "value" and metric in PERCENT_VALUE_METRICS:
        table_df[value_label] = table_df[value_column].map(lambda x: f"{x:.2f}%")
    else:
        table_df[value_label] = table_df[value_column].map(lambda x: f"{x:.2f}")

    return table_df[
        ["report_date", "report_name", "report_period", "quarter_name", "指标", value_label]
    ]


def render_detail_table(table_frames: list[pd.DataFrame], metrics: list[str]) -> None:
    with st.expander("点击查看全部指标明细"):
        detail_df = pd.concat(table_frames, ignore_index=True)
        metric_order = [METRIC_LABELS.get(metric, metric) for metric in metrics]
        detail_df["指标"] = pd.Categorical(
            detail_df["指标"], categories=metric_order, ordered=True
        )
        detail_df = detail_df.sort_values(
            ["指标", "report_date"], ascending=[True, False]
        ).reset_index(drop=True)
        detail_df["指标"] = detail_df["指标"].astype(str)
        detail_df["report_date"] = detail_df["report_date"].dt.strftime("%Y-%m-%d")
        st.dataframe(detail_df, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="价值投资仪表盘", layout="wide")
    st.title("💹 核心公司财务指标监控看板")

    company_names = list_company_names()
    company_name = select_company(company_names)
    symbol = COMPANY_SYMBOLS.get(company_name)

    raw_df = load_company_data(company_name)
    df = prepare_dashboard_data(raw_df)
    if df.empty:
        st.warning("当前公司暂无年报口径的目标指标数据。")
        st.stop()

    st.header(f"{company_name} ({symbol})" if symbol else company_name)

    metrics = get_metrics(df)
    selected_value_label, selected_value_column = select_value_dimension(df, metrics)

    table_frames: list[pd.DataFrame] = []
    rendered_metric_count = 0

    # Render one chart per metric using the same chosen value dimension.
    for metric in metrics:
        metric_df = (
            df[df["metric_name"] == metric]
            .sort_values("report_date")
            .dropna(subset=[selected_value_column])
            .copy()
        )
        if metric_df.empty:
            continue

        metric_df["metric_name_cn"] = metric_df["metric_name"].map(
            lambda x: METRIC_LABELS.get(x, x)
        )
        fig = build_metric_plot(metric_df, metric, selected_value_label, selected_value_column)
        st.plotly_chart(fig, use_container_width=True)
        rendered_metric_count += 1

        table_frames.append(
            build_metric_table(metric_df, metric, selected_value_label, selected_value_column)
        )

    if rendered_metric_count == 0:
        st.warning("当前数值维度下暂无可展示图表。")
        st.stop()

    render_detail_table(table_frames, metrics)


if __name__ == "__main__":
    main()
