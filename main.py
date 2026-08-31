# main.py
import schedule
import time
import logging
import yaml
import os

from app.core.notifier import FeishuNotifier
from app.tasks.daily_reporter import DailyReporter
from app.tasks.gold_watcher import GoldWatcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def load_config():
    config_path = 'config/config.yaml'
    if not os.path.exists(config_path):
        logging.error("配置文件 config/config.yaml 不存在！")
        return None
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def run():
    config = load_config()
    if not config: return

    notification = config['notification']
    # 失败告警优先走独立机器人；未配置时复用黄金机器人，确保现有部署升级后即可收到日报故障提醒。
    failure_config = notification.get('failure_webhook') or notification.get('gold_webhook')
    failure_notifier = FeishuNotifier(failure_config) if failure_config and failure_config.get('url') else None
    if not failure_notifier:
        logging.warning("⚠️ 未配置 failure_webhook，推送彻底失败时只能记录日志。")

    # 通道A: 日报机器人
    daily_notifier = FeishuNotifier(notification['webhook'], failure_notifier)
    # 通道B: 黄金报警机器人
    gold_notifier = FeishuNotifier(notification['gold_webhook'], failure_notifier)

    # 初始化任务 (Task) - 依赖注入 Notifier
    daily_task = DailyReporter(config, daily_notifier)
    gold_task = GoldWatcher(config, gold_notifier)

    # 注册定时调度 (Schedule)
    
    # 4.1 日报调度
    for t in config['schedules']['times']:
        schedule.every().day.at(t).do(daily_task.run)
        logging.info(f"⏰ 已注册日报任务: {t}")

    # 4.2 黄金监控调度
    interval = config.get('gold_monitor_interval', 5)
    schedule.every(interval).minutes.do(gold_task.run)
    logging.info(f"🏆 已注册黄金监控: 每 {interval} 分钟检测一次")

    # --- 启动自检 (Smoke Test) ---
    logging.info("🚀 系统启动，正在进行自检...")
    daily_task.run() # 跑一次日报
    gold_task.run()  # 跑一次黄金检查
    logging.info("✅ 自检完成，进入守候模式。")
    # ---------------------------

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run()
