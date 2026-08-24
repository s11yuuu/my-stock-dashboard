import os
import requests
import datetime
import yfinance as yf
from jinja2 import Template

FINNHUB_KEY = os.getenv("FINNHUB_KEY")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")

def get_us_data():
    us_symbols = {
        '^GSPC': '标普 500', 
        '^IXIC': '纳斯达克', 
        'QQQM': '纳指 100 ETF (QQQM)', 
        'NVDA': '英伟达 (NVDA)',
        'TSLA': '特斯拉 (TSLA)',
        'DRAM': 'Roundhill ETF (DRAM)',
        '005930.KS': 'SK海力士 (SKHY)'
    }
    res = []
    for sym, name in us_symbols.items():
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                close = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                pct = round(((close - prev) / prev) * 100, 2)
                res.append({'name': name, 'price': round(close, 2), 'change': pct})
            else:
                res.append({'name': name, 'price': '--', 'change': 0.0})
        except Exception:
            res.append({'name': name, 'price': 'Err', 'change': 0.0})
    return res

def get_cn_data():
    # A 股核心标的：采用新浪财经 API 强行保底，解决创业板指抓取不到的问题
    cn_map = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sz300750': '宁德时代'
    }
    res = []
    try:
        symbols_str = ",".join(cn_map.keys())
        url = f"http://hq.sinajs.cn/list={symbols_str}"
        headers = {'Referer': 'http://finance.sina.com.cn'}
        r = requests.get(url, headers=headers, timeout=5)
        r.encoding = 'gbk'
        lines = r.text.strip().split('\n')
        
        for line in lines:
            if '="' in line:
                code = line.split('var hq_str_')[1].split('=')[0]
                content = line.split('="')[1].replace('";', '')
                parts = content.split(',')
                if len(parts) > 3:
                    name = cn_map.get(code, code)
                    prev_close = float(parts[2])
                    curr_price = float(parts[3])
                    if prev_close > 0:
                        pct = round(((curr_price - prev_close) / prev_close) * 100, 2)
                    else:
                        pct = 0.0
                    res.append({'name': name, 'price': round(curr_price, 2), 'change': pct})
    except Exception as e:
        print("新浪接口抓取 A 股失败，降级使用 yfinance:", e)
        # 降级方案
        fallback_map = {'000001.SS': '上证指数', '399001.SZ': '深证成指', '399006.SZ': '创业板指', '300750.SZ': '宁德时代'}
        for sym, name in fallback_map.items():
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d")
                if len(h) >= 2:
                    c, p = h['Close'].iloc[-1], h['Close'].iloc[-2]
                    res.append({'name': name, 'price': round(c, 2), 'change': round(((c-p)/p)*100, 2)})
            except:
                res.append({'name': name, 'price': '--', 'change': 0.0})
    return res

def analyze_with_deepseek(prompt_text):
    if not DEEPSEEK_KEY or len(DEEPSEEK_KEY.strip()) < 5:
        return "⚠️ 未在 GitHub Secrets 配置正确的 DEEPSEEK_KEY。"
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 150
    }
    try:
        # 使用 DeepSeek 兼容 API 端点
        res = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        else:
            return f"API 返回错误码 {res.status_code}: 请检查 GitHub Secrets 中的 Key 是否有效或额度是否充足。"
    except Exception as e:
        return f"请求 DeepSeek 失败: {e}"

def get_macro_events():
    # 纠正为凯文·沃什 (Kevin Warsh) 相关的美联储宏观节点
    events = [
        {
            "country": "🇺🇸", 
            "name": "美联储主席凯文·沃什 (Kevin Warsh) 政策表态 & 利率决议", 
            "date": "近期重点", 
            "impact": "关注沃什对货币政策、缩表节奏及流动性的最新主张"
        },
        {
            "country": "🇺🇸", 
            "name": "美国非农就业与 CPI 通胀数据", 
            "date": "本周公布", 
            "impact": "降息路径的核心宏观锚点，直接影响美债收益率"
        },
        {
            "country": "🇨🇳", 
            "name": "中国 LPR 利率及降准/财政刺激政策", 
            "date": "月度节点", 
            "impact": "牵动 A 股与港股科技与顺周期估值修复"
        }
    ]
    
    for item in events:
        prompt = f"宏观事件：{item['name']}。背景：{item['impact']}。请用 100 字简要分析其对美股科技股（英伟达/纳指）和 A 股核心资产的利多/利空影响。"
        item['ai_insight'] = analyze_with_deepseek(prompt)
        
    return events

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
    print("更新成功！")

if __name__ == "__main__":
    build_html()
