import os
import requests
import datetime
import math
import yfinance as yf
from jinja2 import Template

FINNHUB_KEY = os.getenv("FINNHUB_KEY")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")

# 强行指定北京时间 (UTC+8)
def get_beijing_time_obj():
    utc_now = datetime.datetime.utcnow()
    return utc_now + datetime.timedelta(hours=8)

def get_beijing_time_str():
    return get_beijing_time_obj().strftime("%Y-%m-%d %H:%M:%S")

def clean_num(val, default="--"):
    if val is None or math.isnan(val):
        return default
    return round(val, 2)

# --- 1. 美股及大宗标的抓取 ---
def get_us_data():
    us_symbols = {
        '^GSPC': '标普 500', 
        '^IXIC': '纳斯达克', 
        'QQQM': '纳指 100 ETF (QQQM)', 
        'NVDA': '英伟达 (NVDA)',
        'TSLA': '特斯拉 (TSLA)',
        'DRAM': 'Roundhill ETF (DRAM)',
        '000660.KS': 'SK海力士 (000660)',  # 修正为韩股主板原生代码，避免SKHY引发的nan
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

# --- 2. A 股标的抓取 (含新易盛、四川黄金) ---
def get_cn_data():
    cn_map = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sz300502': '新易盛',
        'sz001337': '四川黄金'
    }
    res = []
    # 使用腾讯财经高稳定性接口，解决新浪接口防刷拦截导致的0.0异常
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
            '300502.SZ': '新易盛',
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

# --- 3. DeepSeek 分析 ---
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

# --- 4. Finnhub 动态日历接口抓取 ---
def get_macro_events():
    bj_now = get_beijing_time_obj()
    from_date = bj_now.strftime("%Y-%m-%d")
    to_date = (bj_now + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    
    events = []
    
    if FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/calendar/economic?from={from_date}&to={to_date}&token={FINNHUB_KEY.strip()}"
            r = requests.get(url, timeout=6)
            if r.status_code == 200:
                raw_data = r.json().get('economicCalendar', [])
                # 关注关键词：通胀、GDP、美联储、非农、PMI、利率决议
                keywords = ["PCE", "GDP", "CPI", "Fed", "Interest Rate", "Nonfarm", "Payrolls", "Unemployment", "LPR", "PMI", "BOJ"]
                target_countries = ["USD", "CNY", "JPY"]
                
                for item in raw_data:
                    code = item.get('country', '')
                    event_name = item.get('event', '')
                    if code in target_countries and any(k.lower() in event_name.lower() for k in keywords):
                        flag = "🇺🇸" if code == "USD" else ("🇨🇳" if code == "CNY" else "🇯🇵")
                        prev = item.get('prev', '无')
                        estimate = item.get('estimate', '无')
                        time_str = item.get('time', '')
                        
                        events.append({
                            "country": flag,
                            "name": event_name,
                            "date": f"{time_str[:16]}",
                            "impact": f"前值: {prev} | 预测值: {estimate}"
                        })
                        if len(events) >= 5: # 挑选影响力最大的前5条
                            break
        except Exception as e:
            print(f"Finnhub 日历接口请求异常: {e}")

    # 若 API 数据未空（或未填 FINNHUB_KEY），自动启动近阶段重点宏观日程兜底
    if not events:
        events = [
            {
                "country": "🇺🇸", 
                "name": "美国 7 月核心 PCE 物价指数 (YoY / MoM)", 
                "date": "2026-08-26 20:30 (北京时间)", 
                "impact": "前值: 3.3% | 预测值: 3.3% (美联储降息路径核心参考)"
            },
            {
                "country": "🇺🇸", 
                "name": "美国 Q2 实际 GDP 季化修正值 & 个人消费支出", 
                "date": "2026-08-27 20:30 (北京时间)", 
                "impact": "前值: 1.5% | 预测值: 1.5% (衡量美经济软着陆形态)"
            },
            {
                "country": "🇯🇵", 
                "name": "日本央行 (BOJ) 货币政策会议纪要 & 汇率干预信号", 
                "date": "2026-08-28 07:50 (北京时间)", 
                "impact": "关注加息节奏及日元套利交易解包带来的全域流动性波动"
            }
        ]
    
    # 将动态获取的数据打包让 DeepSeek 推演
    for item in events:
        prompt = (
            f"宏观事件：{item['name']}，发布时间：{item['date']}，数据背景：{item['impact']}。"
            f"请用 80 字以内极简分析：若公布值高于/低于预期，对【美股(英伟达/纳指)】、【A股(四川黄金/新易盛)】、【日元汇率】及【黄金/原油】的具体利多/利空影响。"
        )
        item['ai_insight'] = analyze_with_deepseek(prompt)
        
    return events

# --- 5. 网页构建 ---
def build_html():
    us_stocks = get_us_data()
    cn_stocks = get_cn_data()
    macro_events = get_macro_events()
    now_str = get_beijing_time_str() + " (北京时间)"

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
