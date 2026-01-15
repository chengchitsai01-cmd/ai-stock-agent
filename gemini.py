import os
import yfinance as yf
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import requests

# ==========================================
# 1. 設定區 (個人資產與金鑰)
# ==========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

# 【你的庫存】
# 因為你是從 0 開始，這裡留空即可
MY_PORTFOLIO = {} 
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

# 【你的庫存】(目前是空手)
MY_PORTFOLIO = {} 

# 【股票代碼與名稱對照表】
# 為了速度，我們直接建立對照表，不需每次聯網查詢
STOCK_MAP = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "2881.TW": "富邦金", "2412.TW": "中華電", "2882.TW": "國泰金",
    "2382.TW": "廣達", "2891.TW": "中信金", "2002.TW": "中鋼", "3711.TW": "日月光",
    "2886.TW": "兆豐金", "2884.TW": "玉山金", "1216.TW": "統一", "2885.TW": "元大金",
    "3008.TW": "大立光", "3045.TW": "台灣大", "5880.TW": "合庫金", "2357.TW": "華碩",
    "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "3231.TW": "緯創",
    "6669.TW": "緯穎", "2376.TW": "技嘉", "3035.TW": "智原", "3037.TW": "欣興",
    "0050.TW": "元大台灣50", "006208.TW": "富邦台50", 
    "00878.TW": "國泰永續高股息", "0056.TW": "元大高股息", "00929.TW": "復華台灣科技優息"
}
# 【掃描清單】
# 既然要建倉，建議加入 ETF (0050, 006208) 作為核心配置
# 這裡幫你把清單稍微豐富一點，加入穩健的 ETF
TARGET_LIST = [
    "0050.TW", "006208.TW", "00878.TW", "0056.TW", # 核心 ETF
    "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2881.TW", # 權值股
    "2603.TW", "2609.TW", "2615.TW", # 航運
    "3231.TW", "2382.TW", "2376.TW", "6669.TW" # AI 概念
]
# 將庫存也加入掃描清單，確保一定會被分析
SCAN_LIST = list(set(TARGET_LIST + list(MY_PORTFOLIO.keys())))

genai.configure(api_key=GOOGLE_API_KEY)

# ==========================================
# 2. 技術指標計算函數
# ==========================================
def calculate_technicals(df):
    if len(df) < 20: return None
    
    # 均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# ==========================================
# 3. 篩選邏輯 (海選)
# ==========================================
def screen_stocks(symbol_list):
    print(f"🔍 正在掃描 {len(symbol_list)} 檔股票，請耐心等候...")
    
    # 批次下載數據 (比一個個下載快很多)
    # yfinance 限制：一次太多可能會失敗，這裡簡單處理，實戰建議分批
    try:
        data = yf.download(symbol_list, period="3mo", group_by='ticker', progress=False)
    except Exception as e:
        print(f"下載失敗: {e}")
        return [], {}

    candidates = [] # 篩選出的潛力股
    portfolio_status = {} # 庫存股狀態

    for symbol in symbol_list:
        try:
            # 處理 DataFrame 格式差異 (單檔 vs 多檔)
            if len(symbol_list) == 1:
                df = data
            else:
                df = data[symbol]
                
            # 移除空值
            df = df.dropna()
            if df.empty: continue

            # 計算指標
            df = calculate_technicals(df)
            if df is None: continue

            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            price = last_row['Close']
            ma5 = last_row['MA5']
            ma20 = last_row['MA20']
            rsi = last_row['RSI']
            
            # --- 庫存股檢查 ---
            if symbol in MY_PORTFOLIO:
                cost = MY_PORTFOLIO[symbol]
                profit_pct = (price - cost) / cost * 100
                status = "🟢 續抱"
                
                # 簡單出場邏輯：跌破月線 或 RSI 過熱
                if price < ma20: status = "⚠️ 破月線(警戒)"
                if rsi > 80: status = "🔥 過熱(考慮獲利)"
                
                portfolio_info = {
                    "Symbol": symbol,
                    "Price": price,
                    "Cost": cost,
                    "Profit": f"{profit_pct:.2f}%",
                    "MA5": ma5,
                    "MA20": ma20,
                    "RSI": rsi,
                    "Status": status
                }
                portfolio_status[symbol] = portfolio_info

            # --- 潛力股篩選 (海選邏輯) ---
            # 條件：
            # 1. 黃金交叉 (昨天 MA5 < MA20, 今天 MA5 > MA20)
            # 2. 或是 站上月線且 RSI 健康 (RSI < 70)
            # 3. 成交量判斷 (這裡暫略，可自行加入)
            
            is_golden_cross = (prev_row['MA5'] < prev_row['MA20']) and (last_row['MA5'] > last_row['MA20'])
            is_strong = (price > ma20) and (rsi < 70) and (price > last_row['MA60'])

            if is_golden_cross or (is_strong and symbol not in MY_PORTFOLIO):
                candidates.append({
                    "Symbol": symbol,
                    "Price": price,
                    "Note": "黃金交叉" if is_golden_cross else "多頭排列",
                    "RSI": rsi
                })
                
        except Exception as e:
            continue
            
    # 只取 RSI 最強勢的前 5 名給 AI 分析，避免 Token 爆掉
    candidates = sorted(candidates, key=lambda x: x['RSI'], reverse=True)[:5]
    
    return candidates, portfolio_status

# ==========================================
# 4. AI 基金經理人 (決選)
# ==========================================
def ask_gemini_manager(candidates, portfolio_status):
    print("✨ Gemini 基金經理人正在撰寫決策報告...")
    
    model = genai.GenerativeModel('gemini-flash-latest')

    # 把數據轉成文字給 AI
    portfolio_text = "\n".join([str(v) for k, v in portfolio_status.items()])
    candidates_text = "\n".join([str(c) for c in candidates])

    # prompt = f"""
    # 你是一位負責管理我資產的「AI 基金經理人」。
    # 這是我的投資組合狀況與市場掃描結果：

    # 【我的庫存資產 (Portfolio)】：
    # {portfolio_text}

    # 【市場掃描到的潛力股 (Candidates)】：
    # {candidates_text}

    # 請撰寫一份「每日投資決策日報」，包含三個部分：
    # 1. **庫存診斷**：針對我的持股，哪一支該續抱？哪一支該停損或獲利了結？請給出具體建議 (因為我的成本已列出)。
    # 2. **新機會推薦**：從掃描清單中，挑選 1-2 檔最值得買入的股票，並說明理由 (結合技術面)。
    # 3. **今日總結**：給出今天的整體操作策略 (例如：積極加碼 / 保守觀望 / 換股操作)。

    # 格式要求：
    # - 使用繁體中文。
    # - 用 Markdown 格式 (粗體、條列)。
    # - 語氣專業、冷靜、客觀。
    # """
    prompt = f"""
    你是一位專業的「AI 投資顧問」，正在協助一位【空手（持有 100% 現金）】的投資人進行初始建倉。
    
    以下是市場掃描到的潛力股清單 (Candidates)：
    {candidates_text}

    請撰寫一份「初始建倉建議書」，包含：
    
    1. **市場氣氛判斷**：
       根據掃描到的股票數量與技術面表現，判斷現在適合「積極進場」還是「分批佈局」？
       
    2. **精選投資組合 (Top Picks)**：
       請從清單中挑選 3 檔最值得作為「第一筆買進」的標的。
       - **穩健型**：挑一檔波動較小或 ETF。
       - **成長型**：挑一檔技術面最強勢的個股。
       - 請說明選擇理由 (例如：RSI 黃金交叉、均線多頭)。
       
    3. **資金配置建議**：
       假設投資人有一筆資金，你建議第一筆資金應該投入多少比例？ (例如：建議先投入 30% 資金試單，若拉回再加碼)。

    格式要求：
    - 使用繁體中文。
    - 用 Markdown 格式。
    - 語氣要鼓勵且謹慎，適合新手。
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析失敗: {e}"

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    # 這裡加入簡單的 HTML 換行處理
    body = body.replace("\n", "<br>")
    msg.attach(MIMEText(body, 'html', 'utf-8')) # 改成 HTML 格式

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
print("🚀 AI 基金經理人啟動...")

# A. 海選
top_picks, my_assets = screen_stocks(SCAN_LIST)

if not top_picks and not my_assets:
    print("今日無特殊數據。")
    exit()

# B. AI 決策
report = ask_gemini_manager(top_picks, my_assets)

# C. 寄送報告
subject = f"💰 【AI 投資決策】庫存診斷 & 潛力股掃描"
full_content = f"""
<h2>📊 AI 基金經理人日報</h2>
<hr>
{report}
<br><br>
<small>(此報告由 AI 自動生成，僅供輔助參考，投資盈虧自負)</small>
"""


send_email(subject, full_content)
