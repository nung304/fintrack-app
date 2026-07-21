import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้รองรับการแสดงผลบนมือถือ iPhone
st.set_page_config(page_title="FinTrack Ticker", page_icon="📈", layout="centered")

# 🎯 เสริม CSS สไตล์กระดานหุ้นไทย (ตัววิ่งภาษาไทย วนลูปต่อเนื่องไร้รอยต่อ Seamless Loop)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;600;700&display=swap');
    
    html, body, [data-testid="stWidgetLabel"], .main {
        font-family: 'IBM Plex Sans Thai', sans-serif !important;
    }

    /* แอนิเมชันสำหรับข้อความวิ่งวนลูปต่อเนื่อง */
    @keyframes ticker-infinite {
        0% { transform: translate3d(0, 0, 0); }
        100% { transform: translate3d(-50%, 0, 0); }
    }
    
    .main { background-color: #0b0e14; }
    
    /* แถบกระดานหุ้นแบบวนต่อเนื่อง */
    .ticker-wrap {
        width: 100%; background-color: #161a25;
        overflow: hidden; padding: 10px 0;
        border-bottom: 2px solid #232936; margin-bottom: 20px;
        border-radius: 8px;
        display: flex;
    }
    
    /* กล่องข้อความแฝดที่วิ่งต่อท้ายกันตลอดเวลา */
    .ticker-content {
        display: inline-block;
        white-space: nowrap;
        padding-right: 50px;
        animation: ticker-infinite 30s linear infinite;
        font-weight: 600; font-size: 15px;
    }
    
    /* กล่องการ์ดหลักสไตล์ Dashboard หุ้น */
    .stock-card {
        background: #161a25; border: 1px solid #232936;
        padding: 20px; border-radius: 12px; margin-bottom: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
    }
    .stock-card:hover {
        border-color: #3b82f6;
        transform: scale(1.02);
    }
    
    .ticker-green { color: #00e676; text-shadow: 0 0 8px rgba(0,230,118,0.4); }
    .ticker-red { color: #ff1744; text-shadow: 0 0 8px rgba(255,23,68,0.4); }
    .ticker-blue { color: #29b6f6; text-shadow: 0 0 8px rgba(41,182,246,0.4); }
    .ticker-gold { color: #ffd700; text-shadow: 0 0 8px rgba(255,215,0,0.4); }
    
    .lbl-title { font-size: 13px; color: #848e9c; font-weight: 500; }
    .lbl-val { font-size: 28px; font-weight: 700; margin-top: 5px; }
    
    div.stButton > button {
        background-color: #2b6cb0 !important; color: white !important;
        border-radius: 8px !important; width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# 2. เชื่อมต่อ Firebase NoSQL (Firestore) ผ่าน Secrets
if not firebase_admin._apps:
    cred_json = dict(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 3. ฟังก์ชันจัดการข้อมูล (NoSQL Firestore API)
def init_account():
    doc_ref = db.collection("account").document("main_wallet")
    if not doc_ref.get().exists:
        doc_ref.set({
            "initial_bank_balance": 0.0,
            "savings": 0.0,
            "start_date": "2026-07-16"
        })

init_account()

def get_account_data():
    data = db.collection("account").document("main_wallet").get().to_dict()
    if not data:
        return 0.0, 0.0, "2026-07-16"
    if "initial_bank_balance" not in data:
        data["initial_bank_balance"] = data.get("current_bank_balance", 0.0)
    if "start_date" not in data:
        data["start_date"] = "2026-07-16"
    return data["initial_bank_balance"], data.get("savings", 0.0), data["start_date"]

def add_income_to_bank(amount):
    initial_bank, _, _ = get_account_data()
    db.collection("account").document("main_wallet").update({
        "initial_bank_balance": initial_bank + amount
    })

def calculate_finances():
    initial_bank, current_savings, start_date_str = get_account_data()
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    today = datetime.now()
    
    days_passed = (today - start_date).days + 1
    if days_passed < 1:
        days_passed = 1
    
    total_auto_allocated = days_passed * 100
    
    docs_daily = db.collection("daily_transactions").where("date", ">=", start_date_str).stream()
    total_daily_spent = sum([doc.to_dict().get('amount', 0.0) for doc in docs_daily])
    
    docs_moved = db.collection("direct_transactions").where("category", "==", "ฝากเงินเก็บ (หักจากเงินรายวัน)").stream()
    total_daily_moved = sum([doc.to_dict().get('amount', 0.0) for doc in docs_moved])
    
    daily_wallet_balance = total_auto_allocated - total_daily_spent - total_daily_moved
    
    docs_direct = db.collection("direct_transactions").stream()
    total_direct_spent = 0
    for doc in docs_direct:
        d = doc.to_dict()
        if d.get("category") != "ฝากเงินเก็บ (หักจากเงินรายวัน)":
            total_direct_spent += d.get('amount', 0.0)
            
    # คำนวณยอดบัญชีหลักให้สมดุล (ติดลบ = หักเงินสดจริงเพิ่ม)
    if daily_wallet_balance < 0:
        actual_bank_balance = initial_bank - (total_daily_spent + total_daily_moved) - total_direct_spent
    else:
        actual_bank_balance = initial_bank - total_auto_allocated - total_direct_spent
    
    return actual_bank_balance, daily_wallet_balance, current_savings, start_date_str

def get_past_descriptions():
    docs = db.collection("daily_transactions").stream()
    past_items = set()
    for doc in docs:
        desc = doc.to_dict().get("description")
        if desc:
            past_items.add(desc.strip())
    return sorted(list(past_items))

# 4. ส่วนคำนวณเงินและจัดฟอร์แมตข้อมูล
bank_balance, daily_wallet, current_savings, start_date_str = calculate_finances()

# 📈 จัดคำข้อความวิ่งภาษาไทย
daily_status = f"▲ คงเหลือ +{daily_wallet:,.2f}" if daily_wallet >= 0 else f"▼ ติดลบ {daily_wallet:,.2f}"
single_ticker = f"• กระเป๋ารายวันสะสม: {daily_status} บาท &nbsp;&nbsp;&nbsp;&nbsp; • บัญชีหลักปัจจุบัน: ฿{bank_balance:,.2f} &nbsp;&nbsp;&nbsp;&nbsp; • ยอดเงินเก็บออม: ฿{current_savings:,.2f} &nbsp;&nbsp;&nbsp;&nbsp; • สถานะระบบ: เปิดทำงานปกติ 🟢 &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"

st.markdown(f"""
    <div class="ticker-wrap">
        <div class="ticker-content { 'ticker-green' if daily_wallet >= 0 else 'ticker-red' }">
            {single_ticker} {single_ticker}
        </div>
        <div class="ticker-content { 'ticker-green' if daily_wallet >= 0 else 'ticker-red' }">
            {single_ticker} {single_ticker}
        </div>
    </div>
""", unsafe_allow_html=True)

st.title("📈 FinTrack Terminal")
st.caption("ระบบมอนิเตอร์และบริหารกระเป๋าเงินดิจิทัลสไตล์พอร์ตหุ้น")

# 📊 กล่อง Dashboard
if daily_wallet >= 0:
    st.markdown(f"""
        <div class="stock-card">
            <div class="lbl-title">📱 DAILY ALLOCATED INDEX (งบรายวันสะสม)</div>
            <div class="lbl-val ticker-green">฿ {daily_wallet:,.2f} <span style="font-size:16px;">▲ พร้อมใช้งาน</span></div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
        <div class="stock-card">
            <div class="lbl-title">🚨 DAILY ALLOCATED INDEX (งบรายวันสะสม)</div>
            <div class="lbl-val ticker-red">฿ {daily_wallet:,.2f} <span style="font-size:16px;">▼ เกินงบสะสม</span></div>
        </div>
    """, unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
        <div class="stock-card">
            <div class="lbl-title">💵 CURRENT CASH (บัญชีหลัก)</div>
            <div class="lbl-val ticker-blue" style="font-size: 20px;">฿ {bank_balance:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
        <div class="stock-card">
            <div class="lbl-title">🏦 TOTAL SAVINGS (เงินเก็บออม)</div>
            <div class="lbl-val ticker-gold" style="font-size: 20px;">฿ {current_savings:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 5. ส่วนฟอร์มบันทึกข้อมูล
st.subheader("➕ บันทึกธุรกรรมใหม่ (Execute Order)")
tab1, tab2, tab3 = st.tabs(["🛒 บันทึกรายวัน", "💳 หักบัญชีหลักโดยตรง", "💰 ฝาก/ถอน/รายรับ"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        st.write("📝 **รายละเอียดรายการ**")
        past_suggestions = get_past_descriptions()
        
        # 🎯 ยุบเหลือช่องเดียว: พิมพ์ค้นหาข้อความเดิม หรือพิมพ์สร้างรายการใหม่ได้ในช่องนี้เลย
        final_desc = st.selectbox(
            "เลือกหรือพิมพ์ระบุรายการใหม่:",
            options=past_suggestions,
            index=None,
            placeholder="เช่น ค่าข้าวเช้า, กาแฟ (พิมพ์แล้วเลือกหรือกด Enter)",
            accept_value_from_user=True
        )
        
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="daily_amt")
        submit_daily = st.form_submit_button("💾 ยืนยันคำสั่งซื้อรายวัน")
        
        if submit_daily and amount > 0:
            if final_desc:
                today_str = datetime.now().strftime('%Y-%m-%d')
                db.collection("daily_transactions").add({
                    "date": today_str,
                    "description": str(final_desc).strip(),
                    "amount": amount,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success(f"บันทึกคำสั่ง {final_desc} ฿{amount} สำเร็จ!")
                st.rerun()
            else:
                st.warning("กรุณาระบุรายละเอียดรายการก่อนกดบันทึก")

with tab2:
    with st.form("direct_form", clear_on_submit=True):
        category = st.selectbox("ประเภทค่าใช้จ่ายหลัก", ["ค่าน้ำมัน", "ค่าเน็ต", "ค่าผ่อนของ", "ให้แฟน"])
        amount_direct = st.number_input("จำนวนเงินที่จ่ายจริง (บาท)", min_value=0.0, step=1.0, key="direct_amt")
        note = st.text_input("บันทึกย่อ (ถ้ามี)", placeholder="เช่น ปั๊ม ปตท., งวด 3/12")
        submit_direct = st.form_submit_button("💳 บันทึกตัดจ่ายบัญชีหลัก")
        if submit_direct and amount_direct > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            db.collection("direct_transactions").add({
                "date": today_str,
                "category": category,
                "amount": amount_direct,
                "note": note,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            st.success(f"บันทึกจ่าย {category} ฿{amount_direct} เรียบร้อย!")
            st.rerun()

with tab3:
    with st.form("income_form", clear_on_submit=True):
        income_type = st.selectbox(
            "ประเภทรายการเงินเข้า/เงินเก็บ", 
            [
                "เงินเดือน/รายรับหลัก", 
                "รายรับอื่นๆ", 
                "ฝากเงินเก็บ (หักจากยอดเงินปัจจุบัน) 🏦", 
                "ฝากเงินเก็บ (หักจากเงินรายวันสะสม) 📱", 
                "ถอนเงินเก็บมาใช้ (กลับเข้าบัญชีปัจจุบัน) 💵"
            ]
        )
        amount_income = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="income_amt")
        income_note = st.text_input("บันทึกย่อ", placeholder="เช่น รายรับเสริม, ออมเงิน")
        submit_income = st.form_submit_button("💵 ประมวลผลธุรกรรมเงิน")
        if submit_income and amount_income > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            if income_type in ["เงินเดือน/รายรับหลัก", "รายรับอื่นๆ"]:
                add_income_to_bank(amount_income)
                st.success(f"เติมเงินรับ ฿{amount_income} เข้าสู่พอร์ตแล้ว!")
            
            elif income_type == "ฝากเงินเก็บ (หักจากยอดเงินปัจจุบัน) 🏦":
                if bank_balance >= amount_income:
                    db.collection("account").document("main_wallet").update({"savings": current_savings + amount_income})
                    db.collection("direct_transactions").add({
                        "date": today_str,
                        "category": "ฝากเงินเก็บ (หักจากบัญชีหลัก)",
                        "amount": amount_income,
                        "note": income_note,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.success(f"โอนเงิน ฿{amount_income} เข้าดัชนีเงินเก็บแล้ว!")
                else:
                    st.error("เงินสดในบัญชีปัจจุบันไม่เพียงพอ")
            
            elif income_type == "ฝากเงินเก็บ (หักจากเงินรายวันสะสม) 📱":
                if daily_wallet >= amount_income:
                    db.collection("account").document("main_wallet").update({"savings": current_savings + amount_income})
                    db.collection("direct_transactions").add({
                        "date": today_str,
                        "category": "ฝากเงินเก็บ (หักจากเงินรายวัน)",
                        "amount": amount_income,
                        "note": income_note,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.success(f"ย้ายโควตา ฿{amount_income} ไปยังเงินเก็บแล้ว!")
                else:
                    st.error("ยอดสะสมรายวันไม่เพียงพอ")
            
            elif income_type == "ถอนเงินเก็บมาใช้ (กลับเข้าบัญชีปัจจุบัน) 💵":
                if current_savings >= amount_income:
                    db.collection("account").document("main_wallet").update({"savings": current_savings - amount_income})
                    db.collection("direct_transactions").add({
                        "date": today_str,
                        "category": "ถอนเงินเก็บกลับเข้าบัญชี",
                        "amount": -amount_income,
                        "note": income_note,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.success(f"ดึงสภาพคล่อง ฿{amount_income} กลับเข้าบัญชีหลัก!")
                else:
                    st.error("ยอดเงินเก็บมีไม่เพียงพอสำหรับการถอน")
            
            st.rerun()

# 6. ส่วนการแสดงประวัติรายการ
st.markdown("---")
st.subheader("🕒 ประวัติการทำรายการย้อนหลัง")

try:
    docs_daily = db.collection("daily_transactions").where("date", ">=", start_date_str).order_by("date", direction=firestore.Query.DESCENDING).limit(5).stream()
    list_daily = [doc.to_dict() for doc in docs_daily]
except Exception:
    list_daily = []

st.write("**📝 ออเดอร์กินใช้รายวันล่าสุด**")
if list_daily:
    df_daily = pd.DataFrame(list_daily)[["date", "description", "amount"]]
    st.dataframe(df_daily.rename(columns={"date":"วันที่", "description":"รายการ", "amount":"จำนวนเงิน"}), use_container_width=True)
else:
    st.caption("ไม่มีรายการประวัติ")

try:
    docs_direct = db.collection("direct_transactions").where("date", ">=", start_date_str).order_by("date", direction=firestore.Query.DESCENDING).limit(10).stream()
    list_direct = [doc.to_dict() for doc in docs_direct]
except Exception:
    list_direct = []

st.write("**💰 บันทึกความเคลื่อนไหวบัญชีหลักและกองทุน**")
if list_direct:
    df_direct = pd.DataFrame(list_direct)[["date", "category", "amount", "note"]]
    df_display = df_direct.copy()
    df_display.columns = ["วันที่", "ประเภทธุรกรรม", "จำนวนเงิน", "หมายเหตุ"]
    st.dataframe(df_display, use_container_width=True)
else:
    st.caption("ไม่มีรายการประวัติ")
