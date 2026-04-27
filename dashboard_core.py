import pandas as pd
import plotly.express as px
from utils import FOCUS_METRICS, METRIC_LABELS, PERCENT_COLUMNS

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
VALUE_UNIT_METRICS = {
    "inventory_turnover_days": "天",
    "basic_eps": "元",
    "pe_ttm": "倍",
    "pb": "倍",
}


def choose_chinese_unit(series: pd.Series) -> tuple[float, str]:
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


def validate_required_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


def prepare_dashboard_data(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    data["report_date"] = pd.to_datetime(data["report_date"], errors="coerce")
    data = data.dropna(subset=["report_date", "metric_name"])
    data = data[data["report_name"].astype(str).str.contains("年报", na=False)]
    data = data[data["metric_name"].isin(FOCUS_METRICS)]
    return data


def get_metrics(df: pd.DataFrame) -> list[str]:
    return [metric for metric in FOCUS_METRICS if metric in set(df["metric_name"].dropna())]


def get_available_value_columns(df: pd.DataFrame, metrics: list[str]) -> list[str]:
    return [
        col
        for col in VALUE_COLUMNS
        if col in df.columns
        and any(df[df["metric_name"] == metric][col].notna().any() for metric in metrics)
    ]


def build_metric_df(df: pd.DataFrame, metric: str, value_column: str) -> pd.DataFrame:
    metric_df = (
        df[df["metric_name"] == metric]
        .sort_values("report_date")
        .dropna(subset=[value_column])
        .copy()
    )
    if metric_df.empty:
        return metric_df
    metric_df["metric_name_cn"] = metric_df["metric_name"].map(
        lambda x: METRIC_LABELS.get(x, x)
    )
    return metric_df


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
    elif value_column == "value" and metric in VALUE_UNIT_METRICS:
        display_value_label = f"{value_label}（{VALUE_UNIT_METRICS[metric]}）"

    if value_column in PERCENT_COLUMNS:
        plot_y_column = "value_percent"
        plot_df[plot_y_column] = plot_df[value_column] * 100

    fig = px.line(
        plot_df,
        x="report_date",
        y=plot_y_column,
        markers=True,
        title=f"<b>{METRIC_LABELS.get(metric, metric)}</b>",
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
        elif value_column == "value" and metric in VALUE_UNIT_METRICS:
            value_suffix = VALUE_UNIT_METRICS[metric]
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
    elif value_column == "value" and metric in VALUE_UNIT_METRICS:
        unit = VALUE_UNIT_METRICS[metric]
        table_df[value_label] = table_df[value_column].map(lambda x: f"{x:.2f}{unit}")
    else:
        table_df[value_label] = table_df[value_column].map(lambda x: f"{x:.2f}")

    return table_df[
        ["report_date", "report_name", "report_period", "quarter_name", "指标", value_label]
    ]


def build_detail_table(table_frames: list[pd.DataFrame], metrics: list[str]) -> pd.DataFrame:
    detail_df = pd.concat(table_frames, ignore_index=True)
    metric_order = [METRIC_LABELS.get(metric, metric) for metric in metrics]
    detail_df["指标"] = pd.Categorical(detail_df["指标"], categories=metric_order, ordered=True)
    detail_df = detail_df.sort_values(["指标", "report_date"], ascending=[True, False]).reset_index(
        drop=True
    )
    detail_df["指标"] = detail_df["指标"].astype(str)
    detail_df["report_date"] = detail_df["report_date"].dt.strftime("%Y-%m-%d")
    return detail_df
