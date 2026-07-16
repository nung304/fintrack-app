import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้รองรับการแสดงผลบนมือถือ iPhone
st.set_page_config(page_title="FinTrack Motion", page_icon="📊", layout="centered")

# 🎯 เสริม CSS Animation & Glassmorphism Effect ให้ขยับเคลื่อนไหวได้สวยงามล้ำสมัย
st.markdown("""
    <style>
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .main { background-color: #f4f6f9; }
    
    /* การ์ดกระเป๋ารายวันสะสม */
    .card-daily {
        background: linear-gradient(135deg, #00b4db 0%, #0083b0 100%);
        padding: 22px; color: white; border-radius: 18px;
        box-shadow: 0 8px 20px rgba(0, 180, 219, 0.25); 
        margin-bottom: 18px;
        animation: fadeInUp 0.6s ease-out forwards;
        transition: all 0.3s ease;
    }
    .card-daily:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 25px rgba(0, 180, 219, 0.4);
    }
    
    /* การ์ดกระเป๋ารายวันสะสม (เมื่อติดลบ) */
    .card-daily-alert {
        background: linear-gradient(135deg, #ed213a 0%, #93291e 100%);
        padding: 22px; color: white; border-radius: 18px;
        box-shadow: 0 8px 20px rgba(237, 33, 58, 0.25); 
        margin-bottom: 18px;
        animation: fadeInUp 0.6s ease-out forwards;
        transition: all 0.3s ease;
    }
    .card-daily-alert:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 25px rgba(237, 33, 58, 0.4);
    }
    
    /* การ์ดบัญชีหลัก */
    .card-bank {
        background: linear-gradient(135deg, #1f4068 0%, #162447 100%);
        padding: 18px; color: white; border-radius: 15px;
        box-shadow: 0 6px 15px rgba(22, 36, 71, 0.2);
        animation: fadeInUp 0.8s ease-out forwards;
        transition: all 0.3s ease;
    }
    .card-bank:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 20px rgba(22, 36, 71, 0.35);
    }
    
    /* การ์ดเงินเก็บ */
    .card-savings {
        background: linear-gradient(135deg, #f12711 0%, #f5af19 100%);
        padding: 18px; color: white; border-radius: 15px;
        box-shadow: 0 6px 15px rgba(245, 175, 25, 0.2);
        animation: fadeInUp 1.0s ease-out forwards;
        transition: all 0.3s ease;
    }
    .card-savings:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 20px rgba(245, 175, 25, 0.35);
    }
    
    .card-title { font-size: 13px; opacity: 0.9; font-weight: 500; letter-spacing: 0.5px; margin-bottom: 6px; }
    .card-value { font-size: 26px; font-weight: 700; letter-spacing: 0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.15); }
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

# 4. ส่วนของการแสดงผล UI แดชบอร์ดเคลื่อนไหว (Motion Premium Design)
st.title("📊 FinTrack Mobile")
st.caption("ระบบบริหารเงินส่วนบุคคลอัจฉริยะ")

bank_balance, daily_wallet, current_savings, start_date_str = calculate_finances()

# การ์ดเงินรายวันสะสมเคลื่อนไหว Fade In & Slide Up อัตโนมัติ
if daily_wallet >= 0:
    st.markdown(f"""
        <div class="card-daily">
            <div class="card-title">📱 เงินรายวันสะสมคงเหลือ (พร้อมจ่าย)</div>
            <div class="card-value">฿ {daily_wallet:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
        <div class="card-daily-alert">
            <div class="card-title">🚨 เงินรายวันติดลบเกินงบสะสม</div>
            <div class="card-value">฿ {daily_wallet:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)

# การ์ดแถวสองจะสไลด์ตามขึ้นมาด้วยความเร็วที่ต่างกันเล็กน้อยเพื่อความเนียนตา (Stagger Animation)
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
        <div class="card-bank">
            <div class="card-title">💵 บัญชีหลักปัจจุบัน</div>
            <div class="card-value" style="font-size: 20px;">฿ {bank_balance:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
        <div class="card-savings">
            <div class="card-title">🏦 เงินเก็บปัจจุบัน</div>
            <div class="card-value" style="font-size: 20px;">฿ {current_savings:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 5. ส่วนฟอร์มบันทึกข้อมูล
st.subheader("➕ บันทึกรายการใหม่")
tab1, tab2, tab3 = st.tabs(["🛒 รายจ่ายรายวัน", "💳 หักบัญชีหลักโดยตรง", "💰 รายรับ/เงินเก็บ"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        st.write("📝 **เลือกหรือพิมพ์รายละเอียดรายการ**")
        past_suggestions = get_past_descriptions()
        options = ["-- พิมพ์รายการใหม่ด้วยตัวเอง --"] + past_suggestions
        selected_option = st.selectbox("เลือกจากรายการเดิมที่เคยบันทึก:", options)
        custom_desc = st.text_input("ระบุรายการใหม่ (หากไม่มีในตัวเลือกด้านบน):", placeholder="เช่น ค่าข้าวเช้า, กาแฟ")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="daily_amt")
        submit_daily = st.form_submit_button("💾 บันทึกรายวัน")
        
        if submit_daily and amount > 0:
            if selected_option != "-- พิมพ์รายการใหม่ด้วยตัวเอง --":
                final_desc = selected_option
            else:
                final_desc = custom_desc
                
            if final_desc:
                today_str = datetime.now().strftime('%Y-%m-%d')
                db.collection("daily_transactions").add({
                    "date": today_str,
                    "description": final_desc.strip(),
                    "amount": amount,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success(f"บันทึก {final_desc} ฿{amount} เรียบร้อย!")
                st.rerun()
            else:
                st.error("กรุณากรอกหรือเลือกรายละเอียดรายการ")

with tab2:
    with st.form("direct_form", clear_on_submit=True):
        category = st.selectbox("ประเภทค่าใช้จ่ายรายเดือน", ["ค่าน้ำมัน", "ค่าเน็ต", "ค่าผ่อนของ", "ให้แฟน"])
        amount_direct = st.number_input("จำนวนเงินที่จ่ายจริง (บาท)", min_value=0.0, step=1.0, key="direct_amt")
        note = st.text_input("บันทึกย่อ (ถ้ามี)", placeholder="เช่น ปั๊ม ปตท., งวด 3/12")
        submit_direct = st.form_submit_button("💳 บันทึกหักบัญชีหลักโดยตรง")
        if submit_direct and amount_direct > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            db.collection("direct_transactions").add({
                "date": today_str,
                "category": category,
                "amount": amount_direct,
                "note": note,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            st.success(f"บันทึกการจ่าย {category} ฿{amount_direct} เรียบร้อย!")
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
        submit_income = st.form_submit_button("💵 บันทึกรายการเงิน")
        if submit_income and amount_income > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            if income_type in ["เงินเดือน/รายรับหลัก", "รายรับอื่นๆ"]:
                add_income_to_bank(amount_income)
                st.success(f"บันทึกรายรับ ฿{amount_income} เข้าสู่ระบบเรียบร้อย!")
            
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
                    st.success(f"ย้ายเงิน ฿{amount_income} ไปยังเงินเก็บเรียบร้อย!")
                else:
                    st.error("ยอดเงินในบัญชีปัจจุบันไม่เพียงพอ")
            
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
                    st.success(f"หักเงินรายวันสะสม ฿{amount_income} ย้ายไปที่เงินเก็บเรียบร้อย!")
                else:
                    st.error("เงินรายวันสะสมมีไม่เพียงพอ")
            
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
                    st.success(f"ดึงเงินเก็บ ฿{amount_income} กลับเข้าสู่บัญชีหลักเรียบร้อย!")
                else:
                    st.error("เงินเก็บปัจจุบันมีไม่เพียงพอ")
            
            st.rerun()

# 6. ส่วนการแสดงประวัติรายการ
st.markdown("---")
st.subheader("🕒 รายการล่าสุด")

try:
    docs_daily = db.collection("daily_transactions").where("date", ">=", start_date_str).order_by("date", direction=firestore.Query.DESCENDING).limit(5).stream()
    list_daily = [doc.to_dict() for doc in docs_daily]
except Exception:
    list_daily = []

st.write("**📝 รายการกินใช้รายวัน**")
if list_daily:
    df_daily = pd.DataFrame(list_daily)[["date", "description", "amount"]]
    st.dataframe(df_daily.rename(columns={"date":"วันที่", "description":"รายการ", "amount":"จำนวนเงิน"}), use_container_width=True)
else:
    st.caption("ยังไม่มีรายการรายวันในระบบ")

try:
    docs_direct = db.collection("direct_transactions").where("date", ">=", start_date_str).order_by("date", direction=firestore.Query.DESCENDING).limit(10).stream()
    list_direct = [doc.to_dict() for doc in docs_direct]
except Exception:
    list_direct = []

st.write("**💰 รายการเคลื่อนไหวบัญชีหลัก (รายรับ/น้ำมัน/แฟน/ผ่อนของ/โอนเก็บ)**")
if list_direct:
    df_direct = pd.DataFrame(list_direct)[["date", "category", "amount", "note"]]
    df_display = df_direct.copy()
    df_display.columns = ["วันที่", "ประเภท", "จำนวนเงิน", "หมายเหตุ"]
    st.dataframe(df_display, use_container_width=True)
else:
    st.caption("ยังไม่มีรายการเคลื่อนไหวบัญชีหลักในระบบ")
