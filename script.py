import os
import requests
import datetime
import yfinance as yf
from jinja2 import Template

FINNHUB_KEY = os.getenv("FINNHUB_KEY")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")

def get_us_data():
    symbols = {'^GSPC': '标普 500', '^IXIC': '纳斯达克', 'QQQ': '纳指 ETF', 'NVDA': '英伟达'}
    res = []
    for sym, name in symbols.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                close = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                pct = round(((close - prev) / prev) * 100, 2)
                res.append({'name': name, 'price': round(close, 2), 'change': pct})
        except Exception as e:
            print(f"获取美股 {sym} 失败:", e)
    return res

def get_cn_data():
    # 针对海外 GitHub Actions 服务器环境，优先使用 yfinance 抓取 A 股指数
    cn_symbols = {'000001.SS': '上证指数', '399001.SZ': '深证成指', '399006.SZ': '创业板指'}
    res = []
    for sym, name in cn_symbols.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                close = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                pct = round(((close - prev) / prev) * 100, 2)
                res.append({'name': name, 'price': round(close, 2), 'change': pct})
        except Exception as e:
            print(f"获取 A 股 {sym} 失败:", e)
    
    # 如果 yfinance 未拉取到，尝试调用 akshare 兜底
    if not res:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            mapping = {'上证指数': '000001', '深证成指': '399001', '创业板指': '399006'}
            for name, code in mapping.items():
                row = df[df['代码'] == code]
                if not row.empty:
                    res.append({
                        'name': name,
                        'price': round(float(row['最新价'].values[0]), 2),
                        'change': round(float(row['涨跌幅'].values[0]), 2)
                    })
        except Exception as e:
            print("AKshare 获取 A 股失败:", e)
            
    return res

def analyze_with_deepseek(prompt_text):
    if not DEEPSEEK_KEY:
        return "未检测到正确的 DEEPSEEK_KEY，请检查 GitHub Secrets 设置。"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 150
    }
    try:
        res = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=10)
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI 推演生成异常: {e}"

def get_macro_events():
    macro_list = []
    if not FINNHUB_KEY:
        macro_list.append({
            'country': '⚠️',
            'event_name': '密钥未配置',
            'stars': '★',
            'actual': '无',
            'estimate': '无',
            'prev': '无',
            'ai_insight': '请在 GitHub Secrets 配置 FINNHUB_KEY。'
        })
        return macro_list

    # 查询今日起未来几天的日历数据
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={future}&token={FINNHUB_KEY}"
    
    try:
        r = requests.get(url, timeout=10).json()
        events = r.get('economicCalendar', [])[:3]
        
        for ev in events:
            actual = ev.get('actual') if ev.get('actual') is not None else '待公布'
            estimate = ev.get('estimate') if ev.get('estimate') is not None else '待预测'
            event_name = ev.get('event', '核心经济事件')
            
            prompt = f"宏观事件：{event_name}，预期：{estimate}，公布：{actual}。分析对股市和黄金的影响。"
            ai_insight = analyze_with_deepseek(prompt)
            
            macro_list.append({
                'country': '🇺🇸' if ev.get('country') == 'US' else '🇨🇳',
                'event_name': event_name,
                'stars': '★' * (ev.get('importance') or 3),
                'actual': actual,
                'estimate': estimate,
                'prev': ev.get('prev') or '无',
                'ai_insight': ai_insight
            })
    except Exception as e:
        print("获取宏观日历失败:", e)

    if not macro_list:
        macro_list.append({
            'country': '🌐',
            'event_name': '近期暂无重磅宏观公布',
            'stars': '★★★',
            'actual': '-',
            'estimate': '-',
            'prev': '-',
            'ai_insight': '当前时间段 Finnhub 暂未返回核心经济事件数据。'
        })
        
    return macro_list

def build_html():
    us_stocks = get_us_data()
    cn_stocks = get_cn_data()
    macro_events = get_macro_events()
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    with open("template.html", "r", encoding="utf-8") as f:
        template = Template(f.read())
    
    html_out = template.render(
        update_time=now_str,
        us_stocks=us_stocks,
        cn_stocks=cn_stocks,
        macro_events=macro_events
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print("index.html 更新完毕！")

if __name__ == "__main__":
    build_html()
