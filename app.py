import os

import pandas as pd
import streamlit as st
from dashboard_core import (
    build_detail_table,
    build_metric_df,
    build_metric_plot,
    build_metric_table,
    get_available_value_columns,
    get_metrics,
    prepare_dashboard_data,
    validate_required_columns,
)
from utils import (
    COMPANY_SYMBOLS,
    VALUE_LABELS,
)

DATA_DIR = "data"


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
    missing_columns = validate_required_columns(df)
    if missing_columns:
        st.error(f"数据缺少必要字段: {', '.join(missing_columns)}")
        st.stop()
    return df


def select_value_dimension(available_value_columns: list[str]) -> tuple[str, str]:
    if not available_value_columns:
        st.warning("当前指标没有可展示的数值维度。")
        st.stop()

    value_options = {VALUE_LABELS.get(col, col): col for col in available_value_columns}
    selected_value_label = st.selectbox("选择数值维度", list(value_options.keys()))
    return selected_value_label, value_options[selected_value_label]


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
    if not metrics:
        st.warning("当前公司在目标指标列表中没有可展示数据。")
        st.stop()

    available_value_columns = get_available_value_columns(df, metrics)
    selected_value_label, selected_value_column = select_value_dimension(
        available_value_columns
    )

    table_frames: list[pd.DataFrame] = []
    rendered_metric_count = 0

    # Render one chart per metric using the same chosen value dimension.
    for metric in metrics:
        metric_df = build_metric_df(df, metric, selected_value_column)
        if metric_df.empty:
            continue

        fig = build_metric_plot(metric_df, metric, selected_value_label, selected_value_column)
        st.plotly_chart(fig, use_container_width=True)
        rendered_metric_count += 1

        table_frames.append(
            build_metric_table(metric_df, metric, selected_value_label, selected_value_column)
        )

    if rendered_metric_count == 0:
        st.warning("当前数值维度下暂无可展示图表。")
        st.stop()

    with st.expander("点击查看全部指标明细"):
        st.dataframe(build_detail_table(table_frames, metrics), use_container_width=True)


if __name__ == "__main__":
    main()
