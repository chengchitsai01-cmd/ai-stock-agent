import os
import yfinance as yf
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import requests

# ==========================================
# 1. 設定區
# ==========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

# 你的庫存 (目前空手)
MY_PORTFOLIO = {} 

# 股票對照表
STOCK_MAP = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
    "2308.TW": "台達電", "2603.TW": "長榮", "2609.TW": "陽明", 
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎",
    "0050.TW": "元大台灣50", "0056.TW": "元大高股息", "00878.TW": "國泰永續"
}

# 掃描清單 (你可以自己加)
TARGET_LIST = [
    "0050.TW", # 必備：用來判斷大盤氣氛
    "2330.TW", "2317.TW", "2603.TW", "2382.TW", "00878.TW"
]

genai.configure(api_key=GOOGLE_API_KEY)

# ==========================================
# 2. 技術指標 (新增 MACD)
# ==========================================
def calculate_technicals(df):
    if len(df) < 35: return None # MACD 需要較多天數
    
    # 基本均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal'] # 柱狀圖

    return df

def get_stock_name(symbol):
    return STOCK_MAP.get(symbol, symbol)

# ==========================================
# 3. 資料掃描與 HTML 產生器
# ==========================================
def screen_stocks(symbol_list):
    print(f"🔍 V4.0 正在掃描 {len(symbol_list)} 檔股票...")
    try:
        data = yf.download(symbol_list, period="3mo", group_by='ticker', progress=False)
    except Exception as e:
        print(f"下載失敗: {e}")
        return []

    results = []
    
    for symbol in symbol_list:
        try:
            if len(symbol_list) == 1: df = data
            else: 
                if symbol not in data: continue
                df = data[symbol]
                
            df = df.dropna()
            if df.empty: continue
            df = calculate_technicals(df)
            if df is None: continue

            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 判斷漲跌顏色 (台股：漲紅/跌綠)
            price_change = last['Close'] - prev['Close']
            color = "red" if price_change > 0 else "green"
            
            # MACD 狀態
            macd_status = "偏多" if last['Hist'] > 0 else "偏空"
            
            # 趨勢簡評
            trend = "盤整"
            if last['Close'] > last['MA20']: trend = "多頭 (站上月線)"
            if last['Close'] < last['MA20']: trend = "空頭 (跌破月線)"

            results.append({
                "symbol": symbol,
                "name": get_stock_name(symbol),
                "price": last['Close'],
                "change": price_change,
                "color": color,
                "rsi": last['RSI'],
                "macd": macd_status,
                "trend": trend
            })
        except:
            continue
    return results

def generate_html_table(stock_data):
    # 這是寫給 Email 看的 HTML 表格
    rows = ""
    for stock in stock_data:
        # RSI 顏色警示
        rsi_style = ""
        if stock['rsi'] > 70: rsi_style = "color: red; font-weight: bold;" # 過熱
        elif stock['rsi'] < 30: rsi_style = "color: green; font-weight: bold;" # 超賣
        
        rows += f"""
        <tr style="border-bottom: 1px solid #ddd;">
            <td style="padding: 8px;"><b>{stock['name']}</b><br><span style="font-size:12px; color:#666;">{stock['symbol']}</span></td>
            <td style="padding: 8px; color: {stock['color']};"><b>{stock['price']:.1f}</b></td>
            <td style="padding: 8px; {rsi_style}">{stock['rsi']:.1f}</td>
            <td style="padding: 8px;">{stock['macd']}</td>
            <td style="padding: 8px;">{stock['trend']}</td>
        </tr>
        """
        
    html = f"""
    <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;">
        <tr style="background-color: #f2f2f2; text-align: left;">
            <th style="padding: 8px;">股票</th>
            <th style="padding: 8px;">股價</th>
            <th style="padding: 8px;">RSI</th>
            <th style="padding: 8px;">MACD</th>
            <th style="padding: 8px;">趨勢</th>
        </tr>
        {rows}
    </table>
    """
    return html

# ==========================================
# 4. AI 分析 (加入大盤濾網)
# ==========================================
def ask_gemini_v4(stock_data):
    print("✨ Gemini V4 正在進行多層次分析...")
    model = genai.GenerativeModel('gemini-flash-latest')
    
    # 轉成文字供 AI 閱讀
    data_text = "\n".join([f"{s['name']}: 價{s['price']:.1f}, RSI:{s['rsi']:.1f}, MACD:{s['macd']}, {s['trend']}" for s in stock_data])

    prompt = f"""
    你是一位頂尖的「AI 基金經理人」。
    目前市場數據如下 (包含大盤 0050 與個股)：
    {data_text}

    請撰寫一份【V4.0 投資決策日報】，請依照以下邏輯思考：

    1. **大盤氣象站**：
       先看「元大台灣50 (0050)」的數據。
       - 如果 0050 跌破月線或 MACD 偏空，請建議「保守/多留現金」。
       - 如果 0050 強勢，請建議「積極進場」。
    
    2. **個股點將錄**：
       從清單中挑選 1 檔技術面最漂亮的股票 (RSI 健康 + MACD 偏多)。
       
    3. **操作指令**：
       給空手投資人的建議：今天適合買進資金的幾成？ (0% ~ 50%)

    格式要求：
    - 繁體中文 Markdown。
    - 語氣專業、果斷。
    """
    try:
        return model.generate_content(prompt).text
    except Exception as e:
        return f"AI 分析失敗: {e}"

def send_email(subject, html_content, ai_report):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    
    # 組合 HTML 信件內容
    full_body = f"""
    <html>
    <body>
        <h2>📊 AI 智能操盤日報 V4.0</h2>
        <p>早安！這是今天的市場掃描數據：</p>
        {html_content}
        <br>
        <hr>
        <h3>🤖 基金經理人解讀</h3>
        {ai_report.replace("\n", "<br>")}
        <br><br>
        <small>此信件由 Python 自動傳送，投資有風險，請謹慎評估。</small>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(full_body, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Email 發送成功！")
    except Exception as e:
        print(f"❌ Email 發送失敗：{e}")

# ==========================================
# 5. 主程式
# ==========================================
print("🚀 AI 操盤手 V4.0 (MACD + 彩色報表) 啟動...")

data = screen_stocks(TARGET_LIST)
if not data:
    print("❌ 無數據")
    exit()

# 1. 產生 HTML 表格
html_table = generate_html_table(data)

# 2. AI 寫評論
ai_analysis = ask_gemini_v4(data)

# 3. 寄出超漂亮的信
send_email("💰 【AI 操盤日報】大盤趨勢與個股精選", html_table, ai_analysis)
