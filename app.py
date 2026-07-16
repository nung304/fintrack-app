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
    """สร้างยอดเงินเริ่มต้นเป็น 0.0 ในคอลเลกชัน account (ถ้ายังไม่มี)"""
    doc_ref = db.collection("account").document("main_wallet")
    if not doc_ref.get().exists:
        doc_ref.set({
            "current_bank_balance": 0.0,
            "savings": 0.0
        })

init_account()

def get_account_data():
    data = db.collection("account").document("main_wallet").get().to_dict()
    return data["current_bank_balance"], data["savings"]

def update_bank_balance(amount, is_income=True):
    """อัปเดตยอดเงินในบัญชีปัจจุบัน (บวกเข้า หรือ หักออก)"""
    current_balance, current_savings = get_account_data()
    if is_income:
        new_balance = current_balance + amount
    else:
        new_balance = current_balance - amount
    db.collection("account").document("main_wallet").update({"current_bank_balance": new_balance})

def update_savings_balance(amount, is_deposit=True):
    """อัปเดตยอดเงินเก็บ (ฝากเพิ่ม หรือ ถอนออก)"""
    current_balance, current_savings = get_account_data()
    if is_deposit:
        # ฝากเงินเก็บ: หักจากบัญชีหลัก ไปบวกเข้าเงินเก็บ
        if current_balance >= amount:
            db.collection("account").document("main_wallet").update({
                "current_bank_balance": current_balance - amount,
                "savings": current_savings + amount
            })
            return True
        return False
    else:
        # ถอนเงินเก็บ: หักจากเงินเก็บ กลับเข้าบัญชีหลัก
        if current_savings >= amount:
            db.collection("account").document("main_wallet").update({
                "current_bank_balance": current_balance + amount,
                "savings": current_savings - amount
            })
            return True
        return False

def calculate_daily_wallet():
    """ลอจิกคำนวณเงินโควตารายวันทบยอด"""
    today = datetime.now()
    days_passed = today.day # นับวันของเดือนปัจจุบัน
    total_allowance = days_passed * 100
    
    current_month = today.strftime('%m')
    current_year = today.strftime('%Y')
    start_date = f"{current_year}-{current_month}-01"
    
    docs = db.collection("daily_transactions").where("date", ">=", start_date).stream()
    total_spent = sum([doc.to_dict()['amount'] for doc in docs])
    
    return total_allowance - total_spent

# 4. ส่วนของการแสดงผล UI บน iPhone
st.title("📊 FinTrack Mobile")
st.caption("ระบบบริหารเงินอัจฉริยะ (ฐานข้อมูล Cloud Firebase NoSQL)")

bank_balance, current_savings = get_account_data()
daily_wallet = calculate_daily_wallet()

st.markdown("---")
if daily_wallet >= 0:
    st.metric(label="📱 เงินรายวันที่สามารถจ่ายได้ (ยอดสะสม)", value=f"฿ {daily_wallet:,.2f}")
else:
    st.metric(label="🚨 เงินรายวันติดลบ (หักเข้าเนื้อบัญชีหลัก)", value=f"฿ {daily_wallet:,.2f}")

col1, col2 = st.columns(2)
with col1:
    st.metric(label="💵 ยอดเงินในบัญชีปัจจุบัน", value=f"฿ {bank_balance:,.2f}")
with col2:
    st.metric(label="🏦 เงินเก็บปัจจุบัน", value=f"฿ {current_savings:,.2f}")
st.markdown("---")

# 5. ส่วนฟอร์มบันทึกข้อมูล
st.subheader("➕ บันทึกรายการใหม่")
tab1, tab2, tab3 = st.tabs(["🛒 รายจ่ายรายวัน (งบ 100)", "💳 หักบัญชีหลักโดยตรง", "💰 บันทึกรายรับ/เงินเก็บ"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        desc = st.text_input("รายละเอียดรายการ", placeholder="เช่น ค่าข้าวเช้า, กาแฟ")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="daily_amt")
        submit_daily = st.form_submit_button("💾 บันทึกรายวัน")
        if submit_daily and desc and amount > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            db.collection("daily_transactions").add({
                "date": today_str,
                "description": desc,
                "amount": amount,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            st.success(f"บันทึก {desc} ฿{amount} เรียบร้อย!")
            st.rerun()

with tab2:
    with st.form("direct_form", clear_on_submit=True):
        category = st.selectbox("ประเภทค่าใช้จ่ายรายเดือน", ["ค่าน้ำมัน", "ค่าเน็ต", "ค่าผ่อนของ", "ให้แฟน"])
        amount_direct = st.number_input("จำนวนเงินที่จ่ายจริง (บาท)", min_value=0.0, step=1.0, key="direct_amt")
        note = st.text_input("บันทึกย่อ (ถ้ามี)", placeholder="เช่น ปั๊ม ปตท., งวด 3/12")
        submit_direct = st.form_submit_button("💳 บันทึกหักบัญชีหลัก")
        if submit_direct and amount_direct > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            db.collection("direct_transactions").add({
                "date": today_str,
                "category": category,
                "amount": amount_direct,
                "note": note,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            update_bank_balance(amount_direct, is_income=False)
            st.success(f"บันทึกการจ่าย {category} ฿{amount_direct} เรียบร้อย!")
            st.rerun()

with tab3:
    with st.form("income_form", clear_on_submit=True):
        income_type = st.selectbox("ประเภทรายการเงินเข้า", ["เงินเดือน/รายรับหลัก", "รายรับอื่นๆ", "ฝากเงินเข้าเงินเก็บ 🏦", "ถอนเงินเก็บมาใช้ 💵"])
        amount_income = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="income_amt")
        income_note = st.text_input("บันทึกย่อ", placeholder="เช่น เงินเดือนกรกฎา, โบนัส")
        submit_income = st.form_submit_button("💵 บันทึกรายการเงิน")
        if submit_income and amount_income > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            if income_type in ["เงินเดือน/รายรับหลัก", "รายรับอื่นๆ"]:
                update_bank_balance(amount_income, is_income=True)
                db.collection("direct_transactions").add({
                    "date": today_str,
                    "category": income_type,
                    "amount": amount_income,
                    "note": income_note,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success(f"บันทึกรายรับ ฿{amount_income} เข้าบัญชีหลักเรียบร้อย!")
            
            elif income_type == "ฝากเงินเข้าเงินเก็บ 🏦":
                if update_savings_balance(amount_income, is_deposit=True):
                    st.success(f"ย้ายเงิน ฿{amount_income} จากบัญชีหลัก ไปยังเงินเก็บเรียบร้อย!")
                else:
                    st.error("เงินในบัญชีปัจจุบันไม่เพียงพอสำหรับนำไปเก็บเพิ่ม")
            
            elif income_type == "ถอนเงินเก็บมาใช้ 💵":
                if update_savings_balance(amount_income, is_deposit=False):
                    st.success(f"ดึงเงินเก็บ ฿{amount_income} กลับเข้าสู่บัญชีหลักเรียบร้อย!")
                else:
                    st.error("เงินเก็บปัจจุบันมีไม่เพียงพอให้ถอน")
            
            st.rerun()

# 6. ส่วนการแสดงประวัติรายการเดือนนี้ (เรียงตาม date เพื่อเลี่ยง Composite Index Error)
st.markdown("---")
st.subheader("🕒 รายการล่าสุดเดือนนี้")

today = datetime.now()
current_month = today.strftime('%m')
current_year = today.strftime('%Y')
start_date = f"{current_year}-{current_month}-01"

docs_daily = db.collection("daily_transactions").where("date", ">=", start_date).order_by("date", direction=firestore.Query.DESCENDING).limit(5).stream()
list_daily = [doc.to_dict() for doc in docs_daily]
st.write("**📝 รายการกินใช้รายวัน**")
if list_daily:
    df_daily = pd.DataFrame(list_daily)[["date", "description", "amount"]]
    st.dataframe(df_daily.rename(columns={"date":"วันที่", "description":"รายการ", "amount":"จำนวนเงิน"}), use_container_width=True)
else:
    st.caption("ยังไม่มีรายการรายวันในเดือนนี้")

docs_direct = db.collection("direct_transactions").where("date", ">=", start_date).order_by("date", direction=firestore.Query.DESCENDING).stream()
list_direct = [doc.to_dict() for doc in docs_direct]
st.write("**💰 รายการเคลื่อนไหวบัญชีหลัก (รายรับ/น้ำมัน/แฟน/ผ่อนของ)**")
if list_direct:
    df_direct = pd.DataFrame(list_direct)[["date", "category", "amount", "note"]]
    st.dataframe(df_direct.rename(columns={"date":"วันที่", "category":"ประเภท", "amount":"จำนวนเงิน", "note":"หมายเหตุ"}), use_container_width=True)
else:
    st.caption("ยังไม่มีรายการเคลื่อนไหวบัญชีหลักในเดือนนี้")
