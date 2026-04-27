import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.express as px
from utils import COMPANY_SYMBOLS, FOCUS_METRICS, METRIC_LABELS

DATA_DIR = Path("data")
OUTPUT_DIR = Path("docs")
OUTPUT_FILE = OUTPUT_DIR / "index.html"
REQUIRED_COLUMNS = {
    "report_date",
    "report_name",
    "report_period",
    "quarter_name",
    "metric_name",
    "value",
}
TABLE_COLUMNS = ["report_date", "report_name", "metric_name_cn", "metric_name", "value"]
BASE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>价值投资财务指标网页看板</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0 auto;
      padding: 24px;
      max-width: 1280px;
      line-height: 1.6;
      color: #1f2937;
    }}
    h1, h2 {{
      margin-top: 0;
    }}
    section {{
      margin: 32px 0;
      padding: 20px;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      background: #fff;
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
  </style>
</head>
<body>
  <h1>价值投资财务指标网页看板</h1>
  <p class="meta">自动生成时间: {generated_at}</p>
  {sections}
</body>
</html>
"""


def get_display_name(company_name: str) -> str:
    symbol = COMPANY_SYMBOLS.get(company_name)
    return f"{company_name} ({symbol})" if symbol else company_name


def load_and_prepare_data(csv_file: Path) -> tuple[pd.DataFrame, str, set[str]]:
    # Normalize source data once so charts/table share the same filtered frame.
    df = pd.read_csv(csv_file)
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        return df, get_display_name(csv_file.stem), missing_columns

    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    df = df.dropna(subset=["report_date", "metric_name", "value"])
    df = df[df["report_name"].astype(str).str.contains("年报", na=False)]
    df = df[df["metric_name"].isin(FOCUS_METRICS)]
    df["metric_name_cn"] = df["metric_name"].map(lambda x: METRIC_LABELS.get(x, x))
    return df, get_display_name(csv_file.stem), set()


def build_trend_chart(df: pd.DataFrame, display_name: str) -> str:
    fig = px.line(
        df.sort_values("report_date"),
        x="report_date",
        y="value",
        color="metric_name_cn",
        markers=True,
        title=f"{display_name} 财务指标趋势",
        template="plotly_white",
        hover_data=["report_name", "report_period", "quarter_name", "metric_name"],
        labels={
            "report_date": "报告日期",
            "value": "报告期数值",
            "metric_name_cn": "指标名",
            "metric_name": "英文变量",
        },
    )
    fig.update_layout(legend_title="指标名", hovermode="x unified")
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def build_latest_table(df: pd.DataFrame) -> str:
    latest_rows = (
        df.sort_values("report_date", ascending=False).head(20)[TABLE_COLUMNS].copy()
    )
    latest_rows["report_date"] = latest_rows["report_date"].dt.strftime("%Y-%m-%d")
    latest_rows = latest_rows.rename(
        columns={
            "report_date": "报告日期",
            "report_name": "报告名称",
            "metric_name_cn": "指标中文名",
            "metric_name": "指标英文变量",
            "value": "报告期数值",
        }
    )
    return latest_rows.to_html(index=False, classes="table", border=0)


def build_company_section(csv_file: Path) -> str:
    df, display_name, missing_columns = load_and_prepare_data(csv_file)
    if missing_columns:
        return (
            f"<section><h2>{display_name}</h2>"
            f"<p>缺少字段: {', '.join(sorted(missing_columns))}</p></section>"
        )

    if df.empty:
        return (
            f"<section><h2>{display_name}</h2>" "<p>数据为空，无法绘图。</p></section>"
        )

    chart_html = build_trend_chart(df, display_name)
    table_html = build_latest_table(df)

    return (
        f"<section><h2>{display_name}</h2>"
        f"{chart_html}"
        "<h3>最新 20 条数据</h3>"
        f"{table_html}</section>"
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(DATA_DIR.glob("*.csv"))

    if not csv_files:
        OUTPUT_FILE.write_text(
            "<html><body><h1>未找到任何 CSV 数据文件</h1></body></html>",
            encoding="utf-8",
        )
        return

    sections = [build_company_section(csv_file) for csv_file in csv_files]
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = BASE_HTML.format(generated_at=generated_at, sections="".join(sections))
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"网页已生成: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
