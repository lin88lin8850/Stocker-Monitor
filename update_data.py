import akshare as ak
import pandas as pd
import os
import smtplib
import requests

from email.mime.text import MIMEText
from email.header import Header
from utils import COMPANY_SYMBOLS


DATA_DIR = "data"

# 邮件配置
smtp_server = "smtp.qq.com"  # QQ 邮箱的 SMTP 服务器
smtp_port = 465  # SSL 端口通常是 465
EMAIL_SENDER = "linwugo@qq.com"
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_RECEIVER = "linwugo@qq.com"


def normalize_symbol(symbol: str) -> str:
    symbol_text = str(symbol).strip().upper()
    if symbol_text.startswith("HK"):
        return symbol_text[2:].zfill(5)
    return symbol_text


def is_hk_symbol(symbol: str) -> bool:
    symbol_text = str(symbol).strip().upper()
    return symbol_text.startswith("HK") or len(normalize_symbol(symbol_text)) == 5


def report_labels_from_date(report_date: pd.Timestamp) -> tuple[str, str, str]:
    year = report_date.year
    month = report_date.month
    quarter = ((month - 1) // 3) + 1
    report_period = f"{year}-{quarter}"
    quarter_name_map = {1: "一季度", 2: "二季度", 3: "三季度", 4: "四季度"}
    quarter_name = f"{year}{quarter_name_map.get(quarter, f'{quarter}季度')}"
    report_name_map = {1: "一季报", 2: "中报", 3: "三季报", 4: "年报"}
    report_name = f"{year}{report_name_map.get(quarter, f'Q{quarter}报')}"
    return report_name, report_period, quarter_name


def fetch_hk_avg_inventory_map(symbol: str) -> dict[pd.Timestamp, float]:
    # 东财港股财报明细接口为长表结构，这里提取“存货”并按报告期构造平均存货，
    # 用于估算存货周转天数。
    frames: list[pd.DataFrame] = []
    for indicator in ("年度", "报告期"):
        try:
            partial_df = ak.stock_financial_hk_report_em(
                stock=symbol, symbol="资产负债表", indicator=indicator
            )
        except Exception as exc:
            print(f"港股资产负债表拉取失败 ({symbol}, {indicator}): {exc}")
            continue
        if partial_df is not None and not partial_df.empty:
            frames.append(partial_df)

    if not frames:
        return {}

    inventory_df = pd.concat(frames, ignore_index=True)
    inventory_df = inventory_df[inventory_df["STD_ITEM_NAME"] == "存货"].copy()
    inventory_df["REPORT_DATE"] = pd.to_datetime(
        inventory_df["REPORT_DATE"], errors="coerce"
    )
    inventory_df["AMOUNT"] = pd.to_numeric(inventory_df["AMOUNT"], errors="coerce")
    inventory_df = (
        inventory_df.dropna(subset=["REPORT_DATE", "AMOUNT"])
        .sort_values("REPORT_DATE")
        .drop_duplicates(subset=["REPORT_DATE"], keep="last")
    )
    if inventory_df.empty:
        return {}

    avg_inventory_map: dict[pd.Timestamp, float] = {}
    previous_inventory: float | None = None
    for _, row in inventory_df.iterrows():
        report_date = row["REPORT_DATE"].normalize()
        current_inventory = float(row["AMOUNT"])
        average_inventory = (
            (current_inventory + previous_inventory) / 2
            if previous_inventory is not None
            else current_inventory
        )
        avg_inventory_map[report_date] = average_inventory
        previous_inventory = current_inventory

    return avg_inventory_map


def fetch_hk_financial_long(symbol: str) -> pd.DataFrame:
    hk_symbol = normalize_symbol(symbol)

    # 东财港股财务指标接口对 "报告期" 仅返回最近 9 个季度（约两年），对 "年度" 返回最近 9 个年报。
    # 同时拉两种再按 REPORT_DATE 去重，既能拿到完整的年报历史，又能补上当年的最新季报。
    frames: list[pd.DataFrame] = []
    for indicator in ("年度", "报告期"):
        try:
            partial_df = ak.stock_financial_hk_analysis_indicator_em(
                symbol=hk_symbol, indicator=indicator
            )
        except Exception as exc:
            print(f"港股财务指标拉取失败 ({hk_symbol}, {indicator}): {exc}")
            continue
        if partial_df is not None and not partial_df.empty:
            frames.append(partial_df)

    if not frames:
        return pd.DataFrame()

    hk_df = pd.concat(frames, ignore_index=True)
    hk_df["REPORT_DATE"] = pd.to_datetime(hk_df["REPORT_DATE"], errors="coerce")
    hk_df = (
        hk_df.dropna(subset=["REPORT_DATE"])
        .drop_duplicates(subset=["REPORT_DATE"], keep="first")
        .sort_values("REPORT_DATE", ascending=False)
    )
    avg_inventory_map = fetch_hk_avg_inventory_map(hk_symbol)

    metric_mapping = [
        (
            "operating_income_total",
            "OPERATE_INCOME",
            "OPERATE_INCOME_YOY",
            "OPERATE_INCOME_QOQ",
        ),
        (
            "parent_holder_net_profit",
            "HOLDER_PROFIT",
            "HOLDER_PROFIT_YOY",
            "HOLDER_PROFIT_QOQ",
        ),
        ("basic_eps", "BASIC_EPS", None, None),
        ("assets_debt_ratio", "DEBT_ASSET_RATIO", None, None),
        ("index_weighted_avg_roe", "ROE_AVG", None, None),
        ("pe_ttm", "市盈率", None, None),
        ("pb", "市净率", None, None),
    ]

    rows: list[dict] = []
    for _, row in hk_df.iterrows():
        report_date = row["REPORT_DATE"]
        report_name, report_period, quarter_name = report_labels_from_date(report_date)
        for metric_name, value_col, yoy_col, qoq_col in metric_mapping:
            if value_col not in hk_df.columns:
                continue
            value = pd.to_numeric(row[value_col], errors="coerce")
            if pd.isna(value):
                continue

            yoy = (
                pd.to_numeric(row[yoy_col], errors="coerce")
                if yoy_col and yoy_col in hk_df.columns
                else pd.NA
            )
            qoq = (
                pd.to_numeric(row[qoq_col], errors="coerce")
                if qoq_col and qoq_col in hk_df.columns
                else pd.NA
            )

            rows.append(
                {
                    "report_date": report_date.strftime("%Y-%m-%d"),
                    "report_name": report_name,
                    "report_period": report_period,
                    "quarter_name": quarter_name,
                    "metric_name": metric_name,
                    "value": value,
                    "single": pd.NA,
                    "yoy": yoy,
                    "mom": qoq,
                    "single_yoy": pd.NA,
                }
            )

        # 港股接口没有直接给“存货周转天数”，这里按报告期估算：
        # 存货周转天数 = 平均存货 / 营业成本 * 报告期天数
        # 其中营业成本 = 营业总收入 - 毛利。
        average_inventory = avg_inventory_map.get(report_date.normalize())
        operate_income = pd.to_numeric(row.get("OPERATE_INCOME"), errors="coerce")
        gross_profit = pd.to_numeric(row.get("GROSS_PROFIT"), errors="coerce")
        cogs = operate_income - gross_profit
        if (
            average_inventory is not None
            and pd.notna(operate_income)
            and pd.notna(gross_profit)
            and pd.notna(cogs)
            and cogs > 0
        ):
            period_days = int(report_date.dayofyear)
            inventory_turnover_days = average_inventory / cogs * period_days
            rows.append(
                {
                    "report_date": report_date.strftime("%Y-%m-%d"),
                    "report_name": report_name,
                    "report_period": report_period,
                    "quarter_name": quarter_name,
                    "metric_name": "inventory_turnover_days",
                    "value": inventory_turnover_days,
                    "single": pd.NA,
                    "yoy": pd.NA,
                    "mom": pd.NA,
                    "single_yoy": pd.NA,
                }
            )

    return pd.DataFrame(rows)


def fetch_financial_data(symbol: str) -> pd.DataFrame:
    normalized_symbol = normalize_symbol(symbol)
    if is_hk_symbol(symbol):
        return fetch_hk_financial_long(normalized_symbol)
    return ak.stock_financial_abstract_new_ths(
        symbol=normalized_symbol, indicator="按报告期"
    )


def _fetch_hk_baidu_indicator(symbol: str, indicator: str) -> pd.DataFrame:
    # akshare 自带的 stock_hk_valuation_baidu 使用 http.client 且不跟随 301 重定向，
    # 该接口已迁移至 finance.baidu.com，所以这里用 requests 直连并允许重定向。
    url = "https://gushitong.baidu.com/opendata"
    params = {
        "openapi": "1",
        "dspName": "iphone",
        "tn": "tangram",
        "client": "app",
        "query": indicator,
        "code": symbol,
        "word": "",
        "resource_id": "51171",
        "market": "hk",
        "tag": indicator,
        "chart_select": "全部",
        "industry_select": "",
        "skip_industry": "1",
        "finClientType": "pc",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(
        url, params=params, headers=headers, allow_redirects=True, timeout=20
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload["Result"][0]["DisplayData"]["resultData"]["tplData"]["result"][
        "chartInfo"
    ][0]["body"]
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date"])


def fetch_valuation_history(symbol: str) -> pd.DataFrame:
    if is_hk_symbol(symbol):
        hk_symbol = normalize_symbol(symbol)
        try:
            pe_df = _fetch_hk_baidu_indicator(hk_symbol, "市盈率(TTM)").rename(
                columns={"date": "trade_date", "value": "pe_ttm"}
            )
            pb_df = _fetch_hk_baidu_indicator(hk_symbol, "市净率").rename(
                columns={"date": "trade_date", "value": "pb"}
            )
            pe_df = pe_df.sort_values("trade_date")
            pb_df = pb_df.sort_values("trade_date")
            merged_df = pd.merge_asof(
                pe_df[["trade_date", "pe_ttm"]],
                pb_df[["trade_date", "pb"]],
                on="trade_date",
                direction="nearest",
                tolerance=pd.Timedelta(days=14),
            )
            merged_df = merged_df.dropna(subset=["pe_ttm", "pb"])
            if not merged_df.empty:
                return merged_df
        except Exception as exc:
            print(f"百度港股估值接口失败 ({symbol}): {exc}")

        # 备用方案: eniu 接口，但数据自 2022-07-13 起停止更新，仅作为兜底。
        if hasattr(ak, "stock_hk_indicator_eniu"):
            try:
                eniu_symbol = f"hk{normalize_symbol(symbol)}"
                pe_df = ak.stock_hk_indicator_eniu(
                    symbol=eniu_symbol, indicator="市盈率"
                )
                pb_df = ak.stock_hk_indicator_eniu(
                    symbol=eniu_symbol, indicator="市净率"
                )
                pe_df = pe_df.rename(columns={"date": "trade_date", "pe": "pe_ttm"})
                pb_df = pb_df.rename(columns={"date": "trade_date", "pb": "pb"})
                pe_df["trade_date"] = pd.to_datetime(
                    pe_df["trade_date"], errors="coerce"
                )
                pb_df["trade_date"] = pd.to_datetime(
                    pb_df["trade_date"], errors="coerce"
                )
                pe_df = pe_df.dropna(subset=["trade_date"]).sort_values("trade_date")
                pb_df = pb_df.dropna(subset=["trade_date"]).sort_values("trade_date")
                merged_df = pd.merge_asof(
                    pe_df[["trade_date", "pe_ttm"]],
                    pb_df[["trade_date", "pb"]],
                    on="trade_date",
                    direction="nearest",
                    tolerance=pd.Timedelta(days=7),
                )
                merged_df = merged_df.dropna(subset=["pe_ttm", "pb"])
                if not merged_df.empty:
                    return merged_df
            except Exception:
                pass

        return pd.DataFrame()

    if hasattr(ak, "stock_zh_valuation_baidu"):
        try:
            pe_df = ak.stock_zh_valuation_baidu(
                symbol=symbol, indicator="市盈率(TTM)", period="全部"
            )
            pb_df = ak.stock_zh_valuation_baidu(
                symbol=symbol, indicator="市净率", period="全部"
            )

            pe_df = pe_df.rename(columns={"date": "trade_date", "value": "pe_ttm"})
            pb_df = pb_df.rename(columns={"date": "trade_date", "value": "pb"})
            pe_df["trade_date"] = pd.to_datetime(pe_df["trade_date"], errors="coerce")
            pb_df["trade_date"] = pd.to_datetime(pb_df["trade_date"], errors="coerce")
            pe_df = pe_df.dropna(subset=["trade_date"]).sort_values("trade_date")
            pb_df = pb_df.dropna(subset=["trade_date"]).sort_values("trade_date")
            merged_df = pd.merge_asof(
                pe_df,
                pb_df,
                on="trade_date",
                direction="nearest",
                tolerance=pd.Timedelta(days=7),
            )
            merged_df = merged_df.dropna(subset=["pe_ttm", "pb"])
            if not merged_df.empty:
                return merged_df
        except Exception:
            pass

    market_symbol = f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
    source_candidates = [market_symbol, symbol]
    func_names = ["stock_a_indicator_lg", "stock_a_lg_indicator"]

    for func_name in func_names:
        if not hasattr(ak, func_name):
            continue
        func = getattr(ak, func_name)
        for source_symbol in source_candidates:
            try:
                valuation_df = func(symbol=source_symbol)
                if not valuation_df.empty:
                    return valuation_df
            except Exception:
                continue
    return pd.DataFrame()


def normalize_valuation_df(valuation_df: pd.DataFrame) -> pd.DataFrame:
    if valuation_df.empty:
        return valuation_df

    if {"trade_date", "pe_ttm", "pb"}.issubset(set(valuation_df.columns)):
        normalized_df = valuation_df[["trade_date", "pe_ttm", "pb"]].copy()
        normalized_df["trade_date"] = pd.to_datetime(
            normalized_df["trade_date"], errors="coerce"
        )
        normalized_df["pe_ttm"] = pd.to_numeric(
            normalized_df["pe_ttm"], errors="coerce"
        )
        normalized_df["pb"] = pd.to_numeric(normalized_df["pb"], errors="coerce")
        normalized_df = normalized_df.dropna(subset=["trade_date"]).sort_values(
            "trade_date"
        )
        return normalized_df

    date_col = next(
        (col for col in ["trade_date", "date", "日期"] if col in valuation_df.columns),
        None,
    )
    pe_col = next(
        (
            col
            for col in ["pe_ttm", "pe", "市盈率(TTM)", "市盈率"]
            if col in valuation_df.columns
        ),
        None,
    )
    pb_col = next(
        (col for col in ["pb", "市净率"] if col in valuation_df.columns), None
    )

    if not date_col or not pe_col or not pb_col:
        return pd.DataFrame()

    normalized_df = valuation_df[[date_col, pe_col, pb_col]].copy()
    normalized_df.columns = ["trade_date", "pe_ttm", "pb"]
    normalized_df["trade_date"] = pd.to_datetime(
        normalized_df["trade_date"], errors="coerce"
    )
    normalized_df["pe_ttm"] = pd.to_numeric(normalized_df["pe_ttm"], errors="coerce")
    normalized_df["pb"] = pd.to_numeric(normalized_df["pb"], errors="coerce")
    normalized_df = normalized_df.dropna(subset=["trade_date"]).sort_values(
        "trade_date"
    )
    return normalized_df


def build_valuation_rows(
    financial_df: pd.DataFrame, valuation_df: pd.DataFrame
) -> pd.DataFrame:
    if valuation_df.empty or financial_df.empty:
        return pd.DataFrame()

    report_dates = (
        pd.to_datetime(financial_df["report_date"], errors="coerce")
        .dropna()
        .drop_duplicates()
        .sort_values()
    )
    if report_dates.empty:
        return pd.DataFrame()

    report_meta = (
        financial_df[["report_date", "report_name", "report_period", "quarter_name"]]
        .drop_duplicates("report_date")
        .copy()
    )
    report_meta["report_date"] = pd.to_datetime(
        report_meta["report_date"], errors="coerce"
    )

    rows: list[dict] = []
    for report_date in report_dates:
        history = valuation_df[valuation_df["trade_date"] <= report_date]
        if history.empty:
            continue

        latest = history.iloc[-1]
        meta_row = report_meta[report_meta["report_date"] == report_date]
        if meta_row.empty:
            continue
        meta = meta_row.iloc[0]

        rows.append(
            {
                "report_date": report_date.strftime("%Y-%m-%d"),
                "report_name": meta["report_name"],
                "report_period": meta["report_period"],
                "quarter_name": meta["quarter_name"],
                "metric_name": "pe_ttm",
                "value": latest["pe_ttm"],
                "single": pd.NA,
                "yoy": pd.NA,
                "mom": pd.NA,
                "single_yoy": pd.NA,
            }
        )
        rows.append(
            {
                "report_date": report_date.strftime("%Y-%m-%d"),
                "report_name": meta["report_name"],
                "report_period": meta["report_period"],
                "quarter_name": meta["quarter_name"],
                "metric_name": "pb",
                "value": latest["pb"],
                "single": pd.NA,
                "yoy": pd.NA,
                "mom": pd.NA,
                "single_yoy": pd.NA,
            }
        )

    return pd.DataFrame(rows)


def fetch_a_share_cashflow_df(symbol: str) -> pd.DataFrame:
    market_symbol = f"sh{symbol}" if str(symbol).startswith("6") else f"sz{symbol}"
    try:
        cf_df = ak.stock_financial_report_sina(stock=market_symbol, symbol="现金流量表")
    except Exception as exc:
        print(f"A股现金流量表拉取失败 ({symbol}): {exc}")
        return pd.DataFrame()

    cfo_col_candidates = [
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
    ]
    capex_col_candidates = [
        "购建固定资产、无形资产和其他长期资产所支付的现金",
        "购建固定资产、无形资产和其他长期资产支付的现金",
    ]
    cfo_col = next((col for col in cfo_col_candidates if col in cf_df.columns), None)
    capex_col = next((col for col in capex_col_candidates if col in cf_df.columns), None)
    if "报告日" not in cf_df.columns or not cfo_col or not capex_col:
        return pd.DataFrame()

    result_df = cf_df[["报告日", cfo_col, capex_col]].copy()
    result_df.columns = ["report_date", "operating_cashflow", "capex"]
    result_df["report_date"] = pd.to_datetime(result_df["report_date"], errors="coerce")
    result_df["operating_cashflow"] = pd.to_numeric(
        result_df["operating_cashflow"], errors="coerce"
    )
    result_df["capex"] = pd.to_numeric(result_df["capex"], errors="coerce")
    result_df = result_df.dropna(subset=["report_date", "operating_cashflow", "capex"])
    result_df["report_date"] = result_df["report_date"].dt.normalize()
    result_df = (
        result_df.sort_values("report_date")
        .drop_duplicates(subset=["report_date"], keep="last")
        .reset_index(drop=True)
    )
    return result_df


def fetch_hk_cashflow_df(symbol: str) -> pd.DataFrame:
    hk_symbol = normalize_symbol(symbol)
    frames: list[pd.DataFrame] = []
    for indicator in ("年度", "报告期"):
        try:
            part_df = ak.stock_financial_hk_report_em(
                stock=hk_symbol, symbol="现金流量表", indicator=indicator
            )
        except Exception as exc:
            print(f"港股现金流量表拉取失败 ({hk_symbol}, {indicator}): {exc}")
            continue
        if part_df is not None and not part_df.empty:
            frames.append(part_df)

    if not frames:
        return pd.DataFrame()

    raw_df = pd.concat(frames, ignore_index=True)
    raw_df["REPORT_DATE"] = pd.to_datetime(raw_df["REPORT_DATE"], errors="coerce")
    raw_df["AMOUNT"] = pd.to_numeric(raw_df["AMOUNT"], errors="coerce")
    raw_df = raw_df.dropna(subset=["REPORT_DATE", "STD_ITEM_NAME", "AMOUNT"])
    raw_df["REPORT_DATE"] = raw_df["REPORT_DATE"].dt.normalize()

    cfo_items = {
        "经营业务现金净额",
        "经营活动所得现金净额",
        "经营活动产生的现金流量净额",
        "经营活动现金净流量",
    }
    capex_items = {
        "购建固定资产",
        "购建无形资产及其他资产",
        "购建固定资产、无形资产和其他长期资产支付的现金",
    }

    cfo_df = (
        raw_df[raw_df["STD_ITEM_NAME"].isin(cfo_items)]
        .groupby("REPORT_DATE", as_index=False)["AMOUNT"]
        .sum()
        .rename(columns={"REPORT_DATE": "report_date", "AMOUNT": "operating_cashflow"})
    )
    capex_df = (
        raw_df[raw_df["STD_ITEM_NAME"].isin(capex_items)]
        .groupby("REPORT_DATE", as_index=False)["AMOUNT"]
        .sum()
        .rename(columns={"REPORT_DATE": "report_date", "AMOUNT": "capex"})
    )

    if cfo_df.empty or capex_df.empty:
        return pd.DataFrame()

    result_df = cfo_df.merge(capex_df, on="report_date", how="inner")
    result_df = (
        result_df.sort_values("report_date")
        .drop_duplicates(subset=["report_date"], keep="last")
        .reset_index(drop=True)
    )
    return result_df


def build_fcf_ratio_rows(financial_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if financial_df.empty:
        return pd.DataFrame()

    net_profit_df = financial_df[financial_df["metric_name"] == "parent_holder_net_profit"][
        ["report_date", "value"]
    ].copy()
    net_profit_df["report_date"] = pd.to_datetime(
        net_profit_df["report_date"], errors="coerce"
    )
    net_profit_df["value"] = pd.to_numeric(net_profit_df["value"], errors="coerce")
    net_profit_df = net_profit_df.dropna(subset=["report_date", "value"]).rename(
        columns={"value": "net_profit"}
    )
    if net_profit_df.empty:
        return pd.DataFrame()
    net_profit_df["report_date"] = net_profit_df["report_date"].dt.normalize()
    net_profit_df = net_profit_df.drop_duplicates(subset=["report_date"], keep="last")

    cashflow_df = fetch_hk_cashflow_df(symbol) if is_hk_symbol(symbol) else fetch_a_share_cashflow_df(symbol)
    if cashflow_df.empty:
        return pd.DataFrame()

    report_meta = (
        financial_df[["report_date", "report_name", "report_period", "quarter_name"]]
        .drop_duplicates("report_date")
        .copy()
    )
    report_meta["report_date"] = pd.to_datetime(report_meta["report_date"], errors="coerce")
    report_meta["report_date"] = report_meta["report_date"].dt.normalize()

    merged = (
        report_meta.merge(net_profit_df, on="report_date", how="inner")
        .merge(cashflow_df, on="report_date", how="inner")
        .drop_duplicates(subset=["report_date"], keep="first")
    )
    merged = merged[merged["net_profit"] != 0]
    if merged.empty:
        return pd.DataFrame()

    merged["free_cashflow"] = merged["operating_cashflow"] - merged["capex"]
    merged["fcf_to_net_profit_ratio"] = merged["free_cashflow"] / merged["net_profit"]
    merged = merged.replace([float("inf"), float("-inf")], pd.NA).dropna(
        subset=["fcf_to_net_profit_ratio"]
    )
    if merged.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, row in merged.iterrows():
        rows.append(
            {
                "report_date": row["report_date"].strftime("%Y-%m-%d"),
                "report_name": row["report_name"],
                "report_period": row["report_period"],
                "quarter_name": row["quarter_name"],
                "metric_name": "fcf_to_net_profit_ratio",
                "value": row["fcf_to_net_profit_ratio"],
                "single": pd.NA,
                "yoy": pd.NA,
                "mom": pd.NA,
                "single_yoy": pd.NA,
            }
        )
    return pd.DataFrame(rows)


def enrich_financial_with_valuation(
    financial_df: pd.DataFrame, symbol: str
) -> pd.DataFrame:
    fcf_ratio_rows_df = build_fcf_ratio_rows(financial_df, symbol)
    valuation_raw_df = fetch_valuation_history(symbol)
    valuation_df = normalize_valuation_df(valuation_raw_df)
    valuation_rows_df = build_valuation_rows(financial_df, valuation_df)

    # Remove old derived rows to avoid duplicates on repeated sync.
    base_df = financial_df[
        ~financial_df["metric_name"].isin(
            ["pe_ttm", "pb", "fcf_to_net_profit_ratio"]
        )
    ].copy()
    extra_frames = [df for df in [fcf_ratio_rows_df, valuation_rows_df] if not df.empty]
    if not extra_frames:
        return financial_df
    enriched_df = pd.concat([base_df] + extra_frames, ignore_index=True)

    metric_order = (
        base_df["metric_name"].dropna().drop_duplicates().tolist()
        + ["fcf_to_net_profit_ratio", "pe_ttm", "pb"]
    )
    metric_order = list(dict.fromkeys(metric_order))
    enriched_df["metric_name"] = pd.Categorical(
        enriched_df["metric_name"], categories=metric_order, ordered=True
    )
    enriched_df["report_date"] = pd.to_datetime(
        enriched_df["report_date"], errors="coerce"
    )
    enriched_df = enriched_df.sort_values(
        by=["report_date", "metric_name"], ascending=[False, True]
    ).reset_index(drop=True)
    enriched_df["report_date"] = enriched_df["report_date"].dt.strftime("%Y-%m-%d")
    enriched_df["metric_name"] = enriched_df["metric_name"].astype(str)
    return enriched_df


def fetch_and_sync():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    for name, symbol in COMPANY_SYMBOLS.items():
        print(f"正在同步 {name} ({symbol})...")
        # 拉取同花顺财务指标
        try:
            new_df = fetch_financial_data(symbol)
            new_df = enrich_financial_with_valuation(new_df, symbol)
            file_path = os.path.join(DATA_DIR, f"{name}.csv")

            if os.path.exists(file_path):
                old_df = pd.read_csv(file_path)
                old_period = str(old_df["report_period"][0])

                latest_period = str(new_df["report_period"][0])
                if latest_period != old_period:
                    print(f"【发现更新】{name} 发布了 {latest_period} 财报")
                    # send_email(name, symbol, latest_period)
                new_df.to_csv(file_path, index=False)
            else:
                # 初始化数据
                new_df.to_csv(file_path, index=False)
        except Exception as e:
            print(f"同步失败 {name}: {e}")


def send_email(name, symbol, period):
    if not EMAIL_PASS:
        raise RuntimeError("缺少环境变量 EMAIL_PASS，请先在运行环境中配置。")

    content = (
        f"检测到 {name}({symbol}) 财报更新，最新周期：{period}。请查看网页仪表盘。"
    )
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(f"财报监控提醒：{name} 已更新", "utf-8")
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(EMAIL_SENDER, EMAIL_PASS)  # 这里的 PASS 是授权码
        server.sendmail(EMAIL_SENDER, [EMAIL_RECEIVER], msg.as_string())
        server.quit()
        print("通知发送成功！")
    except Exception as e:
        print(f"发送失败，错误原因: {e}")


if __name__ == "__main__":

    fetch_and_sync()
