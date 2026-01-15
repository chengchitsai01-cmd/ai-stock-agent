import os
import yfinance as yf
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd

# ==========================================
# 1. 設定區 (從 GitHub Secrets 讀取)
# ==========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

# 檢查環境變數
if not GOOGLE_API_KEY or not GMAIL_PASSWORD:
    print("❌ 錯誤：找不到環境變數！請確認 GitHub Secrets 設定是否正確。")
    exit()

genai.configure(api_key=GOOGLE_API_KEY)

# ==========================================
# 2. 定義功能函數 (Email & RSI 計算)
# ==========================================
def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Email 發送成功！")
    except Exception as e:
        print(f"❌ Email 發送失敗：{e}")

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ==========================================
# 3. 抓取股票數據 (含本益比 & RSI)
# ==========================================
def get_stock_data(symbol):
    print(f"🔍 正在查詢 {symbol} 的數據...")
    stock = yf.Ticker(symbol)
    
    # 抓取歷史股價 (為了算 RSI，我們抓 3 個月)
    df = stock.history(period="3mo")
    
    if df.empty:
        return None

    # A. 基礎數據
    current_price = df.iloc[-1]['Close']
    ma5 = df['Close'].tail(5).mean()
    ma20 = df['Close'].tail(20).mean()
    
    # B. 計算 RSI (14天)
    df['RSI'] = calculate_rsi(df['Close'])
    current_rsi = df.iloc[-1]['RSI']
    
    # C. 抓取本益比 (P/E Ratio)
    # 嘗試抓取，如果沒有數據 (例如虧損中) 則顯示 N/A
    try:
        pe_ratio = stock.info.get('trailingPE', 'N/A')
    except:
        pe_ratio = 'N/A'
    
    # 整理數據給 AI 看
    data_summary = (
        f"股票代號：{symbol}\n"
        f"最新收盤價：{current_price:.2f}\n"
        f"5日均線(MA5)：{ma5:.2f}\n"
        f"20日均線(MA20)：{ma20:.2f}\n"
        f"RSI (14天)：{current_rsi:.2f}\n"
        f"本益比 (P/E)：{pe_ratio}\n"
    )
    return data_summary

# ==========================================
# 4. 呼叫 Gemini 分析 (升級版 Prompt)
# ==========================================
def ask_gemini_analyst(stock_data):
    print("✨ Gemini 正在進行多維度分析... (請稍等)")
    
    model = genai.GenerativeModel('gemini-flash-latest')

    prompt = f"""
    你是一位華爾街等級的專業操盤手。
    以下是這檔股票的最新技術面與基本面數據：
    
    {stock_data}
    
    請用繁體中文寫一份約 200 字的精簡分析報告。
    
    重點分析邏輯：
    1. **趨勢判斷**：比較 MA5 與 MA20。
    2. **RSI 解讀**：
       - 若 RSI > 70，提醒是否過熱（有回檔風險）。
       - 若 RSI < 30，提醒是否超賣（有反彈機會）。
       - 若在 30-70 之間，視為正常波動。
    3. **估值判斷**：
       - 根據本益比 (P/E) 判斷股價是否過於昂貴（若 P/E > 30 視為高估，< 15 視為低估，僅供參考）。
    
    最後請給出明確操作建議：【強力買進 / 分批佈局 / 觀望 / 獲利了結 / 賣出】其中選一個。
    """

    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 5. 主程式執行 (監控多檔股票)
# ==========================================
# 你可以自由增加想看的股票
stock_list = ["2330.TW", "2317.TW", "2454.TW"] 
full_report = ""

print("🚀 開始執行 V2.0 智能掃描...")

for symbol in stock_list:
    try:
        data = get_stock_data(symbol)
        if data:
            analysis = ask_gemini_analyst(data)
            full_report += f"📊 **【{symbol} 深度分析】**\n{analysis}\n\n----------------------\n\n"
        else:
            print(f"❌ {symbol} 無數據")
    except Exception as e:
        print(f"❌ {symbol} 發生錯誤: {e}")

if full_report:
    email_subject = f"💰 【AI 投資日報 V2.0】含本益比與 RSI 深度解讀"
    final_msg = f"早安！這是您的進階投資報告：\n\n{full_report}\n(此為 AI 自動生成，投資請謹慎)"
    
    print("📧 正在寄送報告...")
    send_email(email_subject, final_msg)
else:
    print("沒有產生任何報告。")
