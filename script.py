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
            else:
                res.append({'name': name, 'price': '暂无', 'change': 0.0})
        except Exception as e:
            print(f"获取 A 股 {sym} 失败:", e)
            res.append({'name': name, 'price': '获取失败', 'change': 0.0})
    return res

def analyze_with_deepseek(prompt_text):
    if not DEEPSEEK_KEY:
        return "未读取到 DEEPSEEK_KEY，请检查 GitHub Secrets 名称是否准确。"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 150
    }
    try:
        # 使用 DeepSeek 兼容的官方 Endpoint
        res = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=10)
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        else:
            return f"API 返回异常: {data.get('error', {}).get('message', '未知错误')}"
    except Exception as e:
        return f"DeepSeek 请求失败: {e}"

def get_macro_events():
    macro_list = []
    if not FINNHUB_KEY:
        return [{
            'country': '⚠️',
            'event_name': 'Finnhub Key 未配置',
            'stars': '★',
            'actual': '-',
            'estimate': '-',
            'prev': '-',
            'ai_insight': '请检查 GitHub Secrets 中的 FINNHUB_KEY。'
        }]

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={future}&token={FINNHUB_KEY}"
    
    try:
        r = requests.get(url, timeout=10).json()
        events = r.get('economicCalendar', [])
        
        # 筛选重要度较高的前 3 个事件
        for ev in events[:3]:
            actual = ev.get('actual') if ev.get('actual') is not None else '待公布'
            estimate = ev.get('estimate') if ev.get('estimate') is not None else '待预测'
            event_name = ev.get('event', '重磅宏观数据')
            
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
            'event_name': '本周暂无核心宏观事件发布',
            'stars': '★★★',
            'actual': '-',
            'estimate': '-',
            'prev': '-',
            'ai_insight': 'Finnhub 接口当前返回空数据。'
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
    print("index.html 更新成功！")

if __name__ == "__main__":
    build_html()
