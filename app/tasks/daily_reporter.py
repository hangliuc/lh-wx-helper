# app/tasks/daily_reporter.py
import requests
import logging
import time
from datetime import datetime
from chinese_calendar import is_workday

class DailyReporter:
    def __init__(self, config, notifier):
        self.config = config
        self.notifier = notifier
        self.base_url = "http://qt.gtimg.cn/q="
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _is_trading_day(self):
        today = datetime.now().date()
        if not is_workday(today):
            logging.info("😴 今天是法定节假日或休息日，A股休市")
            return False
        if today.weekday() >= 5:
            logging.info("😴 今天是调休上班日(周末)，A股休市")
            return False
        return True

    def _get_price(self, symbol):
        try:
            url = f"{self.base_url}{symbol}"
            resp = requests.get(url, headers=self.headers, timeout=5)
            try:
                content = resp.content.decode('gbk').strip()
            except UnicodeDecodeError:
                content = resp.text.strip()

            if '="' not in content: return None, 0.0
            data_str = content.split('="')[1].split('"')[0]
            if not data_str: return None, 0.0
            fields = data_str.split("~")
            if len(fields) < 10: return None, 0.0

            current_price = float(fields[3])
            prev_close = float(fields[4])
            if current_price == 0: current_price = prev_close

            change_pct = 0.0
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
            
            return current_price, round(change_pct, 2)
        except Exception as e:
            logging.error(f"获取行情失败 {symbol}: {e}")
            return None, 0.00

    def _build_index_column(self, item):
        """构造顶部大盘指数列 (居中展示，配色 + 箭头)"""
        name = item['name']
        flag = item.get('flag', '')
        symbol = item['symbol_ref']

        price, day_change = self._get_price(symbol)
        if price is None or price == 0:
            return None

        if day_change > 0:
            color = "red"
            arrow = "▲"
            sign = "+"
        elif day_change < 0:
            color = "green"
            arrow = "▼"
            sign = ""
        else:
            color = "grey"
            arrow = "─"
            sign = ""

        # 指数(如上证 3000+)用千分位，ETF/个股保留两位小数即可
        if price >= 1000:
            price_str = f"{price:,.2f}"
        else:
            price_str = f"{price}"

        content = (
            f"<font color='grey'>{flag} {name}</font>\n"
            f"**{price_str}**\n"
            f"<font color='{color}'>{arrow} {sign}{day_change}%</font>"
        )

        return {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "vertical_align": "center",
            "elements": [
                {"tag": "markdown", "content": content, "text_align": "center"}
            ]
        }

    def run(self):
        if not self._is_trading_day():
            return

        logging.info("开始执行 [日报任务]...")

        elements = []

        # ============ 1. 顶部大盘指数 (动态卡片) ============
        index_columns = []
        for item in self.config.get('indices', []):
            col = self._build_index_column(item)
            if col is not None:
                index_columns.append(col)

        if index_columns:
            elements.append({
                "tag": "column_set",
                "flex_mode": "stretch",
                "background_style": "grey",
                "horizontal_spacing": "small",
                "columns": index_columns
            })
            elements.append({"tag": "hr"})

        # ============ 2. 持仓列表表头 ============
        elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 3, "elements": [{"tag": "markdown", "content": "**❤️我的持仓**"}]},
                {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": "**💰 现价**"}]},
                {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": "**📈 涨跌**"}]}
            ]
        })
        elements.append({"tag": "hr"})

        valid_items = 0

        # ============ 3. 持仓数据行 (按涨跌幅由大到小排序，每行后加分割线) ============
        holdings = self.config.get('holdings', [])

        # 3.1 先批量取价，过滤掉获取失败的
        rows = []
        for item in holdings:
            name = item['name'].replace(" 指数", "")
            symbol = item['symbol_ref']
            price, day_change = self._get_price(symbol)
            if price is None or price == 0:
                continue
            rows.append({"name": name, "price": price, "change": day_change})

        # 3.2 按涨跌幅由大到小排序 (涨幅最大在最上)
        rows.sort(key=lambda r: r["change"], reverse=True)

        # 3.3 渲染
        for idx, row in enumerate(rows):
            name = row["name"]
            price = row["price"]
            day_change = row["change"]
            valid_items += 1

            if day_change > 0:
                color = "red"
                sign = "+"
            elif day_change < 0:
                color = "green"
                sign = ""
            else:
                color = "grey"
                sign = ""

            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [
                    {"tag": "column", "width": "weighted", "weight": 3, "elements": [{"tag": "markdown", "content": f"**{name}**"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": f"{price}"}]},
                    {"tag": "column", "width": "weighted", "weight": 2, "elements": [{"tag": "markdown", "content": f"<font color='{color}'>{sign}{day_change}%</font>"}]}
                ]
            })
            # 每行后加一条淡分割线 (最后一行不加，由底部 hr 收尾)
            if idx < len(rows) - 1:
                elements.append({"tag": "hr"})

        if valid_items == 0:
            logging.warning("日报内容为空，跳过发送")
            return

        # ============ 4. 底部风控纪律 ============
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "lark_md",
                    "content": "💡 **风控纪律**: 优质资产越跌越买，做时间的朋友"
                }
            ]
        })

        current_time = time.strftime("%Y-%m-%d %H:%M")
        title = f"💷 收盘日报 ({current_time})"

        self.notifier.send_card(title=title, elements=elements, template="watchet")