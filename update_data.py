import akshare as ak
import pandas as pd
import os
import smtplib

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


def fetch_and_sync():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    for name, symbol in COMPANY_SYMBOLS.items():
        print(f"正在同步 {name} ({symbol})...")
        # 拉取同花顺财务指标
        try:
            new_df = ak.stock_financial_abstract_new_ths(
                symbol=symbol, indicator="按报告期"
            )
            file_path = os.path.join(DATA_DIR, f"{name}.csv")

            if os.path.exists(file_path):
                old_df = pd.read_csv(file_path)
                old_period = str(old_df["report_period"][0])

                latest_period = str(new_df["report_period"][0])
                if latest_period != old_period:
                    print(f"【发现更新】{name} 发布了 {latest_period} 财报")
                    new_df.to_csv(file_path, index=False)
                    send_email(name, symbol, latest_period)
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
