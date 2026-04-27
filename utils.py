COMPANY_SYMBOLS = {
    "贵州茅台": "600519",
    "长江电力": "600900",
}

METRIC_LABELS = {
    "index_per_operating_cash_flow_net": "每股经营现金流净额",
    "deduct_net_profit_yoy_growth_ratio": "扣非净利润同比增速",
    "parent_holder_net_profit": "归母净利润",
    "calc_per_net_assets": "每股净资产",
    "inventory_turnover_ratio": "存货周转率",
    "conservative_quick_ratio": "保守速动比率",
    "equity_ratio": "股东权益比率",
    "current_ratio": "流动比率",
    "basic_eps": "基本每股收益",
    "business_cycle": "营业周期",
    "receive_accounts_turnover_days": "应收账款周转天数",
    "quick_ratio": "速动比率",
    "sale_gross_margin": "销售毛利率",
    "inventory_turnover_days": "存货周转天数",
    "calculate_operating_income_total_yoy_growth_ratio": "营业总收入同比增速",
    "sale_net_interest_ratio": "销售净利率",
    "per_undistributed_profits": "每股未分配利润",
    "operating_income_total": "营业总收入",
    "per_capital_reserve": "每股资本公积",
    "index_full_diluted_roe": "全面摊薄净资产收益率",
    "calculate_parent_holder_net_profit_yoy_growth_ratio": "归母净利润同比增速",
    "assets_debt_ratio": "资产负债率",
    "index_deduct_holder_net_profit": "扣非归母净利润",
    "index_weighted_avg_roe": "加权平均净资产收益率",
}

VALUE_LABELS = {
    "value": "报告期数值",
    "single": "单季度数值",
    "yoy": "同比变化",
    "mom": "环比变化",
    "single_yoy": "单季度同比变化",
}

FOCUS_METRICS = [
    "parent_holder_net_profit",
    "operating_income_total",
    "basic_eps",
    "assets_debt_ratio",
    "index_weighted_avg_roe",
    "inventory_turnover_days",
]

PERCENT_COLUMNS = {"yoy", "mom", "single_yoy"}
