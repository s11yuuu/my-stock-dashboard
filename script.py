import os
import requests
import datetime
import yfinance as yf
import akshare as ak
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
    res = []
    try:
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
        print("获取 A 股失败:", e)
    return res

def analyze_with_deepseek(prompt_text):
    if not DEEPSEEK_KEY:
        return "未配置 DeepSeek Key。"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 150
    }
    try:
        res = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers)
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI 分析失败: {e}"

def get_macro_events():
    url = f"https://finnhub.io/api/v1/calendar/economic?token={FINNHUB_KEY}"
    macro_list = []
    try:
        r = requests.get(url).json()
        events = r.get('economicCalendar', [])[:3]
        for ev in events:
            actual = ev.get('actual') or '未公布'
            estimate = ev.get('estimate') or '无'
            event_name = ev.get('event', '宏观数据')
            
            prompt = f"宏观事件：{event_name}，预期值：{estimate}，公布值：{actual}。请用简短一句话分析该数据对美股及黄金的利多或利空影响。"
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
    print("index.html 生成完毕！")

if __name__ == "__main__":
    build_html()
