import datetime as dt
import html
from pathlib import Path

import pandas as pd
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
    build_popmart_member_count_plot,
    build_popmart_repeat_rate_plot,
    build_popmart_store_network_plot,
    load_popmart_member_metrics_data,
    load_popmart_store_network_data,
)
from utils import COMPANY_SYMBOLS, VALUE_LABELS

DATA_DIR = Path("data")
OUTPUT_DIR = Path("docs")
OUTPUT_FILE = OUTPUT_DIR / "index.html"
INTERNAL_DATA_FILES = {"popmart_store_network.csv", "popmart_member_metrics.csv"}
BASE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>财务指标看板</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 0;
      line-height: 1.6;
      color: #1f2937;
      background: #f5f7fb;
    }}
    h1, h2, h3 {{
      margin-top: 0;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 250px 1fr;
      min-height: 100vh;
    }}
    .sidebar {{
      background: #ffffff;
      border-right: 1px solid #e5e7eb;
      padding: 20px 14px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
    }}
    .content {{
      padding: 24px;
      width: 100%;
      box-sizing: border-box;
    }}
    .sidebar h3 {{
      font-size: 16px;
      margin-bottom: 10px;
    }}
    section {{
      margin: 0 0 24px 0;
      padding: 20px;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}
    .table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 14px;
    }}
    .table th, .table td {{
      border: 1px solid #e5e7eb;
      padding: 8px;
      text-align: left;
    }}
    .table th {{
      background: #f9fafb;
    }}
    .meta {{
      color: #6b7280;
      font-size: 14px;
    }}
    .companies {{
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .market-group {{
      margin-bottom: 14px;
    }}
    .market-title {{
      font-size: 13px;
      color: #6b7280;
      margin: 0 0 6px 0;
      font-weight: 600;
    }}
    .company-btn {{
      border: 1px solid #d1d5db;
      background: #fff;
      color: #111827;
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
      font-size: 14px;
      text-align: left;
    }}
    .company-btn.active {{
      border-color: #2563eb;
      color: #fff;
      background: #2563eb;
    }}
    .combo-section {{
      display: none;
    }}
    .combo-section.active {{
      display: block;
    }}
    .metric-block {{
      margin-top: 20px;
      padding-top: 8px;
      border-top: 1px dashed #e5e7eb;
    }}
    #valueDimension {{
      width: 100%;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      padding: 8px;
      background: #fff;
      margin-bottom: 8px;
    }}
    .expander {{
      margin-top: 16px;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      background: #fff;
      padding: 8px 12px;
    }}
    .expander summary {{
      cursor: pointer;
      font-weight: 600;
      color: #374151;
    }}
    @media (max-width: 900px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
        height: auto;
        border-right: none;
        border-bottom: 1px solid #e5e7eb;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h3>公司</h3>
      {company_groups}
      <label for="valueDimension"><strong>选择数值维度</strong></label>
      <select id="valueDimension">
          {value_options}
      </select>
    </aside>
    <main class="content">
      <h1>💹 核心公司财务指标监控看板</h1>
      <p class="meta">自动生成时间: {generated_at}</p>
      {sections}
    </main>
  </div>
  <script>
    const companyButtons = Array.from(document.querySelectorAll('.company-btn'));
    const valueSelect = document.getElementById('valueDimension');
    const sections = Array.from(document.querySelectorAll('.combo-section'));

    function activeCompany() {{
      const active = companyButtons.find(btn => btn.classList.contains('active'));
      return active ? active.dataset.company : null;
    }}

    function refreshView() {{
      const company = activeCompany();
      let value = valueSelect.value;
      const availableValues = sections
        .filter(section => section.dataset.company === company)
        .map(section => section.dataset.value);
      if (availableValues.length > 0 && !availableValues.includes(value)) {{
        value = availableValues[0];
        valueSelect.value = value;
      }}
      sections.forEach(section => {{
        const show = section.dataset.company === company && section.dataset.value === value;
        section.classList.toggle('active', show);
      }});
    }}

    companyButtons.forEach(btn => {{
      btn.addEventListener('click', () => {{
        companyButtons.forEach(item => item.classList.remove('active'));
        btn.classList.add('active');
        refreshView();
      }});
    }});

    valueSelect.addEventListener('change', refreshView);
    refreshView();
  </script>
</body>
</html>
"""


def get_display_name(company_name: str) -> str:
    symbol = COMPANY_SYMBOLS.get(company_name)
    return f"{company_name} ({symbol})" if symbol else company_name


def load_company_data(csv_file: Path) -> tuple[pd.DataFrame, str, list[str]]:
    df = pd.read_csv(csv_file)
    return df, get_display_name(csv_file.stem), validate_required_columns(df)


def build_metric_block(
    df: pd.DataFrame, metrics: list[str], value_column: str, company_name: str
) -> str:
    value_label = VALUE_LABELS.get(value_column, value_column)
    chart_blocks: list[str] = []
    table_frames: list[pd.DataFrame] = []

    for metric in metrics:
        metric_df = build_metric_df(df, metric, value_column)
        if metric_df.empty:
            continue
        fig = build_metric_plot(metric_df, metric, value_label, value_column)
        chart_blocks.append(fig.to_html(full_html=False, include_plotlyjs="cdn"))
        table_frames.append(
            build_metric_table(metric_df, metric, value_label, value_column)
        )

        # 泡泡玛特专属图放在“存货周转天数”后面。
        if company_name == "泡泡玛特" and metric == "inventory_turnover_days":
            network_df = load_popmart_store_network_data()
            network_fig = build_popmart_store_network_plot(network_df)
            if network_fig is not None:
                chart_blocks.append(network_fig.to_html(full_html=False, include_plotlyjs="cdn"))
            member_df = load_popmart_member_metrics_data()
            member_count_fig = build_popmart_member_count_plot(member_df)
            if member_count_fig is not None:
                chart_blocks.append(
                    member_count_fig.to_html(full_html=False, include_plotlyjs="cdn")
                )
            repeat_rate_fig = build_popmart_repeat_rate_plot(member_df)
            if repeat_rate_fig is not None:
                chart_blocks.append(
                    repeat_rate_fig.to_html(full_html=False, include_plotlyjs="cdn")
                )

    if not chart_blocks:
        return ""

    detail_df = build_detail_table(table_frames, metrics)
    table_html = detail_df.to_html(index=False, classes="table", border=0)
    return (
        f"<div class='metric-block'>"
        f"{''.join(chart_blocks)}"
        "<details class='expander'>"
        "<summary>点击查看全部指标明细</summary>"
        f"{table_html}</details></div>"
    )


def build_combo_section(
    company_name: str, display_name: str, df: pd.DataFrame, value_column: str
) -> str:
    metrics = get_metrics(df)
    if not metrics:
        return ""

    metric_block = build_metric_block(df, metrics, value_column, company_name)
    if not metric_block:
        return ""

    return (
        f"<section class='combo-section' data-company='{html.escape(company_name)}' "
        f"data-value='{html.escape(value_column)}'>"
        f"<h2>{display_name}</h2>{metric_block}</section>"
    )


def build_company_sections(
    csv_file: Path,
) -> tuple[list[str], str, list[str], str]:
    raw_df, display_name, missing_columns = load_company_data(csv_file)
    company_name = csv_file.stem
    if missing_columns:
        return (
            [],
            display_name,
            [],
            f"<section><h2>{display_name}</h2><p>缺少字段: {', '.join(sorted(missing_columns))}</p></section>",
        )

    df = prepare_dashboard_data(raw_df)
    if df.empty:
        return (
            [],
            display_name,
            [],
            f"<section><h2>{display_name}</h2><p>数据为空，无法绘图。</p></section>",
        )

    metrics = get_metrics(df)
    if not metrics:
        return (
            [],
            display_name,
            [],
            f"<section><h2>{display_name}</h2><p>当前公司在目标指标列表中没有可展示数据。</p></section>",
        )

    value_columns = get_available_value_columns(df, metrics)
    if not value_columns:
        return (
            [],
            display_name,
            [],
            f"<section><h2>{display_name}</h2><p>当前指标没有可展示的数值维度。</p></section>",
        )

    sections = [
        build_combo_section(company_name, display_name, df, value_column)
        for value_column in value_columns
    ]
    sections = [section for section in sections if section]
    if not sections:
        return (
            [],
            display_name,
            [],
            f"<section><h2>{display_name}</h2><p>当前数值维度下暂无可展示图表。</p></section>",
        )

    return sections, display_name, value_columns, ""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_map = {
        csv_file.stem: csv_file
        for csv_file in DATA_DIR.glob("*.csv")
        if csv_file.name not in INTERNAL_DATA_FILES
    }
    csv_files = [
        csv_map[company] for company in COMPANY_SYMBOLS.keys() if company in csv_map
    ]
    extra_files = sorted(
        [csv_file for name, csv_file in csv_map.items() if name not in COMPANY_SYMBOLS]
    )
    csv_files.extend(extra_files)

    if not csv_files:
        OUTPUT_FILE.write_text(
            "<html><body><h1>未找到任何 CSV 数据文件</h1></body></html>",
            encoding="utf-8",
        )
        return

    all_sections: list[str] = []
    fallback_sections: list[str] = []
    company_names: list[str] = []
    company_labels: dict[str, str] = {}
    all_value_columns: set[str] = set()

    for csv_file in csv_files:
        sections, display_name, value_columns, fallback = build_company_sections(
            csv_file
        )
        company_name = csv_file.stem
        company_names.append(company_name)
        company_labels[company_name] = display_name
        all_value_columns.update(value_columns)
        all_sections.extend(sections)
        if fallback:
            fallback_sections.append(fallback)

    if not all_sections:
        all_sections = fallback_sections

    default_company = company_names[0] if company_names else ""
    ordered_value_columns = [
        value_column
        for value_column in ["value", "yoy"]
        if value_column in all_value_columns
    ]
    if not ordered_value_columns:
        ordered_value_columns = sorted(all_value_columns) or ["value"]

    a_share_names = [
        company_name
        for company_name in company_names
        if not str(COMPANY_SYMBOLS.get(company_name, "")).upper().startswith("HK")
    ]
    hk_names = [
        company_name
        for company_name in company_names
        if str(COMPANY_SYMBOLS.get(company_name, "")).upper().startswith("HK")
    ]

    def render_company_buttons(names: list[str]) -> str:
        return "".join(
            f"<button class='company-btn{' active' if company_name == default_company else ''}' "
            f"data-company='{html.escape(company_name)}'>"
            f"{html.escape(company_labels[company_name])}</button>"
            for company_name in names
        )

    company_groups_parts = []
    if a_share_names:
        company_groups_parts.append(
            "<div class='market-group'>"
            "<div class='market-title'>A股</div>"
            f"<div class='companies'>{render_company_buttons(a_share_names)}</div>"
            "</div>"
        )
    if hk_names:
        company_groups_parts.append(
            "<div class='market-group'>"
            "<div class='market-title'>港股</div>"
            f"<div class='companies'>{render_company_buttons(hk_names)}</div>"
            "</div>"
        )
    company_groups = "".join(company_groups_parts)
    value_options = "".join(
        f"<option value='{html.escape(value_column)}'>"
        f"{html.escape(VALUE_LABELS.get(value_column, value_column))}</option>"
        for value_column in ordered_value_columns
    )

    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_output = BASE_HTML.format(
        generated_at=generated_at,
        company_groups=company_groups,
        value_options=value_options,
        sections="".join(all_sections),
    )
    OUTPUT_FILE.write_text(html_output, encoding="utf-8")
    print(f"网页已生成: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
