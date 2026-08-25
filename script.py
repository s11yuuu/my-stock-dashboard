import os
import requests
import datetime
import math
import yfinance as yf
from jinja2 import Template

# 强行指定北京时间 (UTC+8)
def get_beijing_time():
    utc_now = datetime.datetime.utcnow()
    bj_now = utc_now + datetime.timedelta(hours=8)
    return bj_now.strftime("%Y-%m-%d %H:%M:%S")

DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")

def clean_num(val, default="--"):
    if val is None or math.isnan(val):
        return default
    return round(val, 2)

def get_us_data():
    us_symbols = {
        '^GSPC': '标普 500', 
        '^IXIC': '纳斯达克', 
        'QQQM': '纳指 100 ETF (QQQM)', 
        'NVDA': '英伟达 (NVDA)',
        'TSLA': '特斯拉 (TSLA)',
        'DRAM': 'Roundhill ETF (DRAM)',
        'SKHY': 'SK海力士 (SKHY)',  
        '^VIX': 'VIX 恐慌指数',
        'CL=F': 'NYMEX 原油',
        'GC=F': 'COMEX 黄金',
        'SI=F': 'COMEX 白银'
    }
    res = []
    for sym, name in us_symbols.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                close = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                if math.isnan(close) or math.isnan(prev):
                    res.append({'name': name, 'price': '--', 'change': 0.0})
                else:
                    pct = round(((close - prev) / prev) * 100, 2)
                    res.append({'name': name, 'price': clean_num(close), 'change': pct})
            else:
                res.append({'name': name, 'price': '--', 'change': 0.0})
        except Exception:
            res.append({'name': name, 'price': 'Err', 'change': 0.0})
    return res

def get_cn_data():
    cn_map = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sz300750': '宁德时代',
        'sz001337': '四川黄金'
    }
    res = []
    # 使用新浪财经+腾讯财经双接口容错，避免 0.0 异常
    try:
        symbols_str = ",".join(cn_map.keys())
        url = f"http://qt.gtimg.cn/q={symbols_str}"
        r = requests.get(url, timeout=5)
        lines = r.text.strip().split(';')
        
        for line in lines:
            if 'v_' in line and '="' in line:
                code = line.split('v_')[1].split('=')[0]
                content = line.split('="')[1].replace('"', '')
                parts = content.split('~')
                if len(parts) > 30:
                    name = cn_map.get(code, code)
                    curr_price = float(parts[3])
                    prev_close = float(parts[4])
                    if curr_price > 0 and prev_close > 0:
                        pct = round(((curr_price - prev_close) / prev_close) * 100, 2)
                        res.append({'name': name, 'price': round(curr_price, 2), 'change': pct})
                    else:
                        res.append({'name': name, 'price': '--', 'change': 0.0})
    except Exception as e:
        # 降级备用逻辑
        fallback_map = {
            '000001.SS': '上证指数', 
            '399001.SZ': '深证成指', 
            '399006.SZ': '创业板指', 
            '300750.SZ': '宁德时代',
            '001337.SZ': '四川黄金'
        }
        for sym, name in fallback_map.items():
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d")
                if len(h) >= 2:
                    c, p = h['Close'].iloc[-1], h['Close'].iloc[-2]
                    res.append({'name': name, 'price': clean_num(c), 'change': round(((c-p)/p)*100, 2)})
            except:
                res.append({'name': name, 'price': '--', 'change': 0.0})
    return res

def analyze_with_deepseek(prompt_text):
    key = DEEPSEEK_KEY.strip() if DEEPSEEK_KEY else ""
    if not key:
        return "⚠️ 未在 GitHub Secrets 中识别到 DEEPSEEK_KEY。"
    
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 150
    }
    try:
        res = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        else:
            return f"API 返回错误码 {res.status_code}: 请检查 GitHub Secrets 中的 DEEPSEEK_KEY。"
    except Exception as e:
        return f"请求 DeepSeek 失败: {e}"

def get_macro_events():
    # 标注精准具体的未来会议与发布时间
    events = [
        {
            "country": "🇺🇸", 
            "name": "美联储 FOMC 利率决议 (凯文·沃什政策导向)", 
            "date": "2026年9月17日 02:00 (北京时间)", 
            "impact": "评估新任主席政策框架、降息路径及流动性拐点"
        },
        {
            "country": "🇺🇸", 
            "name": "美国 8 月 CPI 通胀数据发布", 
            "date": "2026年9月11日 20:30 (北京时间)", 
            "impact": "通胀粘性评估，直接牵动美债收益率、美元指数及金价"
        },
        {
            "country": "🇨🇳", 
            "name": "中国 9 月 LPR (贷款市场报价利率) 拟定", 
            "date": "2026年9月20日 09:15 (北京时间)", 
            "impact": "宏观信用扩张信号，影响 A 股顺周期及科技股估值"
        }
    ]
    
    for item in events:
        prompt = f"宏观事件：{item['name']}，具体时间：{item['date']}。背景：{item['impact']}。请用 80 字简要分析其对美股科技股（英伟达/纳指）、黄金/原油及 A 股核心标的（四川黄金/宁德时代）的利多/利空推演。"
        item['ai_insight'] = analyze_with_deepseek(prompt)
        
    return events

def build_html():
    us_stocks = get_us_data()
    cn_stocks = get_cn_data()
    macro_events = get_macro_events()
    now_str = get_beijing_time() + " (北京时间)"

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
    print("更新完成！")

if __name__ == "__main__":
    build_html()
