import os  # 新增這個，用來讀取系統變數
import yfinance as yf
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# 1. 設定區 (改成從環境變數讀取，不要寫死！)
# ==========================================
# 這裡的 os.getenv 對應到等一下我們在 GitHub 網站上設定的秘密名稱
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

# 檢查一下是否有抓到金鑰 (除錯用)
if not GOOGLE_API_KEY or not GMAIL_PASSWORD:
    print("❌ 錯誤：找不到環境變數！請確認 GitHub Secrets 設定是否正確。")
    exit()

genai.configure(api_key=GOOGLE_API_KEY)

# ... (以下程式碼保持不變，照抄原本的即可) ...
# ... (包含 send_email, get_stock_data, ask_gemini_analyst, 以及主程式部分) ...

# ==========================================
# 2. 定義 Email 發送工具
# ==========================================
def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        # 連線到 Gmail 伺服器
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Email 發送成功！請檢查信箱。")
    except Exception as e:
        print(f"❌ Email 發送失敗：{e}")

# ==========================================
# 3. 抓取股票數據
# ==========================================
def get_stock_data(symbol):
    print(f"🔍 正在查詢 {symbol} 的數據...")
    stock = yf.Ticker(symbol)
    df = stock.history(period="1mo")
    
    if df.empty:
        return None

    current_price = df.iloc[-1]['Close']
    ma5 = df['Close'].tail(5).mean()
    ma20 = df['Close'].tail(20).mean()
    trend = "上漲" if ma5 > ma20 else "下跌"
    
    data_summary = (
        f"股票代號：{symbol}\n"
        f"最新收盤價：{current_price:.2f}\n"
        f"5日均線(MA5)：{ma5:.2f}\n"
        f"20日均線(MA20)：{ma20:.2f}\n"
        f"短期趨勢判斷：{trend}\n"
    )
    return data_summary

# ==========================================
# 4. 呼叫 Gemini 分析
# ==========================================
def ask_gemini_analyst(stock_data):
    print("✨ Gemini 正在撰寫分析報告... (請稍等)")
    
    # 使用免費且穩定的模型
    model = genai.GenerativeModel('gemini-flash-latest')

    prompt = f"""
    你是一位專業的台灣股市分析師。
    以下是這檔股票的最新數據：
    
    {stock_data}
    
    請根據數據，用繁體中文寫一份簡短的投資分析報告。
    1. 格式清晰，條列重點。
    2. 給出明確的操作建議（偏多、偏空、觀望）。
    """

    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 5. 主程式執行
# ==========================================
# ==========================================
# 5. 主程式執行 (升級版：多檔股票分析)
# ==========================================
# 你想監控的股票清單
stock_list = ["2330.TW", "2317.TW", "2454.TW"] # 台積電, 鴻海, 聯發科
full_report = ""

print("🚀 開始執行多檔股票掃描...")

for symbol in stock_list:
    # A. 抓數據
    data = get_stock_data(symbol)
    
    if data:
        # B. AI 分析
        analysis = ask_gemini_analyst(data)
        
        # C. 累積報告內容
        full_report += f"📊 **【{symbol} 分析報告】**\n{analysis}\n\n----------------------\n\n"
    else:
        print(f"❌ 跳過 {symbol} (無數據)")

# D. 全部跑完後，一次寄出一封總整理 Email
if full_report:
    email_subject = f"💰 【AI 投資日報】台積電、鴻海、聯發科 趨勢追蹤"
    final_msg = f"早安！這是您今天的投資懶人包：\n\n{full_report}\n(此為 AI 自動生成，僅供參考)"
    
    print("📧 正在寄送總整理報告...")
    send_email(email_subject, final_msg)
else:
    print("沒有產生任何報告。")