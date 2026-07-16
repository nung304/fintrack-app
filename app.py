import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้รองรับการแสดงผลบนมือถือ iPhone
st.set_page_config(page_title="FinTrack NoSQL", page_icon="📊", layout="centered")

# 2. เชื่อมต่อ Firebase NoSQL (Firestore) ผ่าน Secrets
if not firebase_admin._apps:
    cred_json = dict(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 3. ฟังก์ชันจัดการข้อมูล (NoSQL Firestore API)
def init_account():
    """สร้างยอดเงินเริ่มต้นและบันทึกวันเริ่มใช้งานวันแรก"""
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
    """เมื่อมีรายรับเข้า ให้ไปบวกเพิ่มในยอดเงินตั้งต้น"""
    initial_bank, _, _ = get_account_data()
    db.collection("account").document("main_wallet").update({
        "initial_bank_balance": initial_bank + amount
    })

def calculate_finances():
    """ลอจิกคำนวณการหักเงินวันละ 100 อัตโนมัติ และยอดคงเหลือจริง ปลอดภัยจาก KeyError"""
    initial_bank, current_savings, start_date_str = get_account_data()
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    today = datetime.now()
    
    days_passed = (today - start_date).days + 1
    if days_passed < 1:
        days_passed = 1
    
    total_auto_allocated = days_passed * 100
    
    # คำนวณฝั่งรายจ่ายรายวัน
    docs_daily = db.collection("daily_transactions").where("date", ">=", start_date_str).stream()
    total_daily_spent = sum([doc.to_dict().get('amount', 0.0) for doc in docs_daily])
    
    # คำนวณฝั่งย้ายเงินรายวันไปเข้าเงินเก็บ
    docs_moved = db.collection("direct_transactions").where("category", "==", "ฝากเงินเก็บ (หักจากเงินรายวัน)").stream()
    total_daily_moved = sum([doc.to_dict().get('amount', 0.0) for doc in docs_moved])
    
    daily_wallet_balance = total_auto_allocated - total_daily_spent - total_daily_moved
    
    # คำนวณฝั่งรายจ่ายประจำ/รายรับ/ถอนเงินเก็บ
    docs_direct = db.collection("direct_transactions").stream()
    total_direct_spent = 0
    for doc in docs_direct:
        d = doc.to_dict()
        if d.get("category") != "ฝากเงินเก็บ (หักจากเงินรายวัน)":
            total_direct_spent += d.get('amount', 0.0)
            
    actual_bank_balance = initial_bank - total_auto_allocated - total_direct_spent
    
    return actual_bank_balance, daily_wallet_balance, current_savings, start_date_str

def get_past_descriptions():
    """ดึงประวัติรายการที่เคยพิมพ์ไปแล้ว เพื่อเอามาเป็นตัวเลือกอัตโนมัติ"""
    docs = db.collection("daily_transactions").stream()
    past_items = set() # ใช้ set เพื่อล้างคำซ้ำอัตโนมัติ
    for doc in docs:
        desc = doc.to_dict().get("description")
        if desc:
            past_items.add(desc.strip())
    return sorted(list(past_items))

# 4. ส่วนของการแสดงผล UI บน iPhone
st.title("📊 FinTrack Mobile")
st.caption("ระบบบริหารเงินอัจฉริยะ (หักโควตารายวัน 100B อัตโนมัติ)")

bank_balance, daily_wallet, current_savings, start_date_str = calculate_finances()

st.markdown("---")
if daily_wallet >= 0:
    st.metric(label="📱 เงินรายวันสะสมคงเหลือ (พร้อมให้กดจ่าย)", value=f"฿ {daily_wallet:,.2f}")
else:
    st.metric(label="🚨 เงินรายวันติดลบเกินงบสะสม", value=f"฿ {daily_wallet:,.2f}")

col1, col2 = st.columns(2)
with col1:
    st.metric(label="💵 ยอดเงินในบัญชีปัจจุบัน (หักวันละ 100 แล้ว)", value=f"฿ {bank_balance:,.2f}")
with col2:
    st.metric(label="🏦 เงินเก็บปัจจุบัน", value=f"฿ {current_savings:,.2f}")
st.markdown("---")

# 5. ส่วนฟอร์มบันทึกข้อมูล
st.subheader("➕ บันทึกรายการใหม่")
tab1, tab2, tab3 = st.tabs(["🛒 รายจ่ายรายวัน (หักจากยอดสะสม)", "💳 หักบัญชีหลักโดยตรง", "💰 บันทึกรายรับ/เงินเก็บ"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        st.write("📝 **เลือกหรือพิมพ์รายละเอียดรายการ**")
        
        # 🎯 ลอจิกดึงคำแนะนำอัจฉริยะ: ดึงคำเก่ามาทำลิสต์รายการให้จิ้ม
        past_suggestions = get_past_descriptions()
        options = ["-- พิมพ์รายการใหม่ด้วยตัวเอง --"] + past_suggestions
        
        selected_option = st.selectbox("เลือกจากรายการเดิมที่เคยบันทึก:", options)
        
        # ช่องสำหรับพิมพ์คำใหม่ (จะเปิดให้พิมพ์ถ้าเลือกข้อแรก หรือเลือกพิมพ์ใหม่)
        custom_desc = st.text_input("ระบุรายการใหม่ (หากไม่มีในตัวเลือกด้านบน):", placeholder="เช่น ค่าข้าวเช้า, กาแฟ")
        
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="daily_amt")
        submit_daily = st.form_submit_button("💾 บันทึกรายวัน")
        
        if submit_daily and amount > 0:
            # ลอจิกเลือกข้อความ: ถ้าไม่ได้เลือกคำเดิม ให้เอาคำใหม่ที่พิมพ์
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
