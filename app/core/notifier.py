# app/core/notifier.py
import logging
import time

import requests


class FeishuNotifier:
    """飞书机器人发送器，负责重试以及最终失败告警。"""

    RETRYABLE_FEISHU_CODES = {11232, 19006}

    def __init__(self, config, failure_notifier=None):
        self.webhook_url = config["url"]
        self.headers = {"Content-Type": "application/json"}
        # 告警发送时会禁用二次告警，避免 webhook 异常时发生递归。
        self.failure_notifier = failure_notifier

    @staticmethod
    def _wait_time(attempt):
        return 2 ** attempt

    def _send_failure_alert(self, failed_title, reason):
        if not self.failure_notifier:
            logging.error("未配置 failure_webhook，无法发送推送失败告警。")
            return

        alert_content = (
            "**原推送未送达，请检查机器人和服务日志。**\n"
            f"- 原消息：{failed_title}\n"
            f"- 最后错误：{reason}"
        )
        if not self.failure_notifier.send_card(
            title="🚨 飞书推送失败告警",
            markdown_content=alert_content,
            template="red",
            notify_on_failure=False,
        ):
            logging.error("🚨 推送失败告警 webhook 也发送失败。")

    def send_card(
        self,
        title,
        markdown_content=None,
        elements=None,
        template="blue",
        max_retries=3,
        notify_on_failure=True,
    ):
        """发送飞书互动卡片；成功返回 True，最终失败返回 False。"""
        if max_retries < 1:
            raise ValueError("max_retries 必须至少为 1")

        card_elements = []
        if markdown_content:
            card_elements.append({"tag": "markdown", "content": markdown_content})
        if elements:
            card_elements.extend(elements)

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": template,
                },
                "elements": card_elements,
            },
        }

        last_reason = "未知错误"
        for attempt in range(max_retries):
            attempt_number = attempt + 1
            retryable = False
            try:
                response = requests.post(
                    self.webhook_url, json=payload, headers=self.headers, timeout=10
                )
                try:
                    result = response.json()
                except ValueError:
                    result = {}

                if response.ok and result.get("code") == 0:
                    logging.info(f"✅ 飞书卡片推送成功: {title}")
                    return True

                code = result.get("code")
                last_reason = f"HTTP {response.status_code}, 飞书响应: {result or response.text[:200]}"
                # 11232 是限流，19006 是飞书侧 internal error；HTTP 429/5xx 也是暂时性故障。
                retryable = (
                    code in self.RETRYABLE_FEISHU_CODES
                    or response.status_code == 429
                    or response.status_code >= 500
                )
                log = logging.warning if retryable else logging.error
                log(
                    f"{'⚠️ 可重试' if retryable else '❌ 不可重试'}的飞书推送失败 "
                    f"(尝试 {attempt_number}/{max_retries}): {last_reason}"
                )
            except requests.exceptions.RequestException as error:
                last_reason = f"网络请求异常: {error}"
                retryable = True
                logging.warning(f"⚠️ {last_reason} (尝试 {attempt_number}/{max_retries})")

            if retryable and attempt_number < max_retries:
                wait_time = self._wait_time(attempt)
                logging.warning(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            break

        logging.error(f"🚨 飞书推送彻底失败: {title}。最后错误: {last_reason}")
        if notify_on_failure:
            self._send_failure_alert(title, last_reason)
        return False
