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
from popmart_store_network import (
    build_popmart_store_network_plot,
    load_popmart_store_network_data,
)
from utils import (
    COMPANY_SYMBOLS,
    VALUE_LABELS,
)

DATA_DIR = "data"
INTERNAL_DATA_FILES = {"popmart_store_network.csv"}


def list_company_names() -> list[str]:
    data_files = [
        f
        for f in os.listdir(DATA_DIR)
        if f.endswith(".csv") and f not in INTERNAL_DATA_FILES
    ]
    if not data_files:
        st.error("未在 data 目录找到 CSV 数据文件。")
        st.stop()

    existing_companies = {f.replace(".csv", "") for f in data_files}
    ordered_companies = [
        company for company in COMPANY_SYMBOLS.keys() if company in existing_companies
    ]
    # Keep backward compatibility for CSV files not listed in config.
    extra_companies = sorted(existing_companies - set(ordered_companies))
    return ordered_companies + extra_companies


def is_hk_company(company_name: str) -> bool:
    symbol = str(COMPANY_SYMBOLS.get(company_name, "")).upper()
    return symbol.startswith("HK")


def select_company(company_names: list[str]) -> str:
    # Persist selection across reruns.
    if (
        "selected_company_name" not in st.session_state
        or st.session_state["selected_company_name"] not in company_names
    ):
        st.session_state["selected_company_name"] = company_names[0]

    st.sidebar.subheader("公司")
    a_share_companies = [name for name in company_names if not is_hk_company(name)]
    hk_companies = [name for name in company_names if is_hk_company(name)]
    market_options = []
    if a_share_companies:
        market_options.append("A股")
    if hk_companies:
        market_options.append("港股")

    selected_company = st.session_state["selected_company_name"]
    default_market = "港股" if is_hk_company(selected_company) else "A股"
    if default_market not in market_options:
        default_market = market_options[0]

    selected_market = st.sidebar.radio(
        "市场",
        market_options,
        index=market_options.index(default_market),
        horizontal=True,
    )
    candidates = hk_companies if selected_market == "港股" else a_share_companies
    default_idx = candidates.index(selected_company) if selected_company in candidates else 0
    selected_company = st.sidebar.radio(
        f"{selected_market}公司",
        candidates,
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

        # 泡泡玛特专属图放在“存货周转天数”后面，便于结合库存效率一起看渠道扩张。
        if company_name == "泡泡玛特" and metric == "inventory_turnover_days":
            network_df = load_popmart_store_network_data()
            network_fig = build_popmart_store_network_plot(network_df)
            if network_fig is not None:
                st.plotly_chart(network_fig, use_container_width=True)

    if rendered_metric_count == 0:
        st.warning("当前数值维度下暂无可展示图表。")
        st.stop()

    with st.expander("点击查看全部指标明细"):
        st.dataframe(build_detail_table(table_frames, metrics), use_container_width=True)


if __name__ == "__main__":
    main()
