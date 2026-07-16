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
    """สร้างยอดเงินเริ่มต้นในคอลเลกชัน account (ถ้ายังไม่มี)"""
    doc_ref = db.collection("account").document("main_wallet")
    if not doc_ref.get().exists:
        doc_ref.set({
            "current_bank_balance": 25000.0,
            "savings": 5000.0
        })

init_account()

def get_account_data():
    data = db.collection("account").document("main_wallet").get().to_dict()
    return data["current_bank_balance"], data["savings"]

def update_bank_balance(amount, is_income=False):
    current_balance, _ = get_account_data()
    new_balance = current_balance + amount if is_income else current_balance - amount
    db.collection("account").document("main_wallet").update({"current_bank_balance": new_balance})

def calculate_daily_wallet():
    """ลอจิกคำนวณเงินโควตารายวันทบยอด"""
    today = datetime.now()
    days_passed = today.day # นับวันของเดือนปัจจุบัน เช่น วันที่ 16
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
tab1, tab2 = st.tabs(["🛒 รายจ่ายรายวัน (งบ 100)", "💳 หักบัญชีหลักโดยตรง"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        desc = st.text_input("รายละเอียดรายการ", placeholder="เช่น ค่าข้าวเช้า, กาแฟ")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0)
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
        category = st.selectbox("ประเภทค่าใช้จ่ายรายเดือน", ["ค่าน้ำมัน", "ค่าเน็ต", "ค่าผ่อนของ", "ให้แฟน", "เติมเงินเข้าระบบ"])
        amount_direct = st.number_input("จำนวนเงินที่จ่ายจริง (บาท)", min_value=0.0, step=1.0)
        note = st.text_input("บันทึกย่อ (ถ้ามี)", placeholder="เช่น ปั๊ม ปตท., งวด 3/12")
        submit_direct = st.form_submit_button("💳 บันทึกหักบัญชีหลัก")
        if submit_direct and amount_direct > 0:
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            if category == "เติมเงินเข้าระบบ":
                update_bank_balance(amount_direct, is_income=True)
                st.success(f"เติมเงินเข้าบัญชีหลัก ฿{amount_direct} เรียบร้อย!")
            else:
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

# 6. ส่วนการแสดงประวัติรายการเดือนนี้
st.markdown("---")
st.subheader("🕒 รายการล่าสุดเดือนนี้")

today = datetime.now()
current_month = today.strftime('%m')
current_year = today.strftime('%Y')
start_date = f"{current_year}-{current_month}-01"

docs_daily = db.collection("daily_transactions").where("date", ">=", start_date).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5).stream()
list_daily = [doc.to_dict() for doc in docs_daily]
st.write("**📝 รายการกินใช้รายวัน**")
if list_daily:
    df_daily = pd.DataFrame(list_daily)[["date", "description", "amount"]]
    st.dataframe(df_daily.rename(columns={"date":"วันที่", "description":"รายการ", "amount":"จำนวนเงิน"}), use_container_width=True)
else:
    st.caption("ยังไม่มีรายการรายวันในเดือนนี้")

docs_direct = db.collection("direct_transactions").where("date", ">=", start_date).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
list_direct = [doc.to_dict() for doc in docs_direct]
st.write("**⛽ รายการหักบัญชีโดยตรง**")
if list_direct:
    df_direct = pd.DataFrame(list_direct)[["date", "category", "amount", "note"]]
    st.dataframe(df_direct.rename(columns={"date":"วันที่", "category":"ประเภท", "amount":"จำนวนเงิน", "note":"หมายเหตุ"}), use_container_width=True)
else:
    st.caption("ยังไม่มีรายการหักบัญชีโดยตรงในเดือนนี้")
