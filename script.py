import os
import requests
import datetime
import yfinance as yf
from jinja2 import Template

FINNHUB_KEY = os.getenv("FINNHUB_KEY")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")

def get_market_data(symbol_dict):
    res = []
    for sym, name in symbol_dict.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                close = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                pct = round(((close - prev) / prev) * 100, 2)
                res.append({'sym': sym, 'name': name, 'price': round(close, 2), 'change': pct})
            else:
                res.append({'sym': sym, 'name': name, 'price': '--', 'change': 0.0})
        except Exception as e:
            res.append({'sym': sym, 'name': name, 'price': 'Err', 'change': 0.0})
    return res

def analyze_with_deepseek(prompt_text):
    if not DEEPSEEK_KEY:
        return "请在 GitHub Secrets 配置 DEEPSEEK_KEY。"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 200
    }
    try:
        res = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, timeout=10)
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI 推演异常: {e}"

def get_macro_events():
    # 模拟核心关注的近期宏观节点（避免 API 空数据）
    events_to_monitor = [
        {"country": "🇺🇸", "name": "美联储利率决议 & 鲍威尔讲话", "date": "近期重点", "impact": "决定美科技股与流动性走向"},
        {"country": "🇺🇸", "name": "美国非农就业与 CPI 数据", "date": "本周公布", "impact": "影响降息预期与美债收益率"},
        {"country": "🇨🇳", "name": "中国 LPR 利率及宏观刺激政策", "date": "月度节点", "impact": "直接牵动 A 股/港股估值修复"}
    ]
    
    for item in events_to_monitor:
        prompt = f"宏观事件：{item['name']}。简要预测对美股/A股及科技核心标的（英伟达/QQQ等）的利多/利空影响。"
        item['ai_insight'] = analyze_with_deepseek(prompt)
        
    return events_to_monitor

def build_html():
    # 1. 美股及核心标的（可在此自由增删）
    us_symbols = {
        '^GSPC': '标普 500', 
        '^IXIC': '纳斯达克', 
        'QQQM': '纳指 100 ETF (QQQM)', 
        'NVDA': '英伟达 (NVDA)',
        'TSLA': '特斯拉 (TSLA)',
        'DRAM': 'RoundhillETF (DRAM)',
        'SKHY': 'SK海力士 (SKHY)'
    }
    
    # 2. A股/港股核心指数与标的
    cn_symbols = {
        '000001.SS': '上证指数', 
        '399001.SZ': '深证成指', 
        '399006.SZ': '创业板指',
        '300750.SZ': '宁德时代'
    }

    us_stocks = get_market_data(us_symbols)
    cn_stocks = get_market_data(cn_symbols)
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

if __name__ == "__main__":
    build_html()
