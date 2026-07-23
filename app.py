import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date, timedelta
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้รองรับการแสดงผลบนมือถือ
st.set_page_config(page_title="FinTrack Ticker", page_icon="📈", layout="centered")

# 🎯 เสริม CSS สไตล์กระดานหุ้นไทย
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;600;700&display=swap');
    
    html, body, [data-testid="stWidgetLabel"], .main {
        font-family: 'IBM Plex Sans Thai', sans-serif !important;
    }

    @keyframes ticker-infinite {
        0% { transform: translate3d(0, 0, 0); }
        100% { transform: translate3d(-50%, 0, 0); }
    }
    
    .main { background-color: #0b0e14; }
    
    .ticker-wrap {
        width: 100%; background-color: #161a25;
        overflow: hidden; padding: 10px 0;
        border-bottom: 2px solid #232936; margin-bottom: 20px;
        border-radius: 8px;
        display: flex;
    }
    
    .ticker-content {
        display: inline-block;
        white-space: nowrap;
        padding-right: 50px;
        animation: ticker-infinite 30s linear infinite;
        font-weight: 600; font-size: 15px;
    }
    
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
    .ticker-purple { color: #b388ff; text-shadow: 0 0 8px rgba(179,136,255,0.4); }
    
    .lbl-title { font-size: 13px; color: #848e9c; font-weight: 500; }
    .lbl-val { font-size: 28px; font-weight: 700; margin-top: 5px; }
    
    div.stButton > button {
        background-color: #2b6cb0 !important; color: white !important;
        border-radius: 8px !important; width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# 2. เชื่อมต่อ Firebase
if not firebase_admin._apps:
    cred_json = dict(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 3. ฟังก์ชันจัดการข้อมูล
def init_account():
    doc_ref = db.collection("account").document("main_wallet")
    if not doc_ref.get().exists:
        doc_ref.set({
            "initial_bank_balance": 0.0,
            "savings": 0.0,
            "start_date": "2026-07-16"
        })
    
    history_ref = list(db.collection("rate_history").limit(1).stream())
    if len(history_ref) == 0:
        db.collection("rate_history").add({
            "start_date": "2026-07-16",
            "daily_rate": 100.0,
            "created_at": datetime.now().isoformat()
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

def set_new_daily_rate(start_date_str, new_rate):
    db.collection("rate_history").add({
        "start_date": start_date_str,
        "daily_rate": float(new_rate),
        "created_at": datetime.now().isoformat()
    })

def calculate_total_allocated(system_start_date_str):
    rates_docs = db.collection("rate_history").stream()
    rates_list = []
    
    for doc in rates_docs:
        d = doc.to_dict()
        if "start_date" in d and "daily_rate" in d:
            try:
                s_date = datetime.strptime(str(d["start_date"]), "%Y-%m-%d").date()
            except Exception:
                continue

            raw_created = d.get("created_at") or d.get("timestamp")
            ts = 0.0
            if raw_created:
                if isinstance(raw_created, datetime):
                    ts = raw_created.timestamp()
                elif isinstance(raw_created, str):
                    try:
                        ts = datetime.fromisoformat(raw_created).timestamp()
                    except Exception:
                        ts = 0.0
                elif hasattr(raw_created, 'timestamp'):
                    try:
                        ts = raw_created.timestamp()
                    except Exception:
                        ts = 0.0

            rates_list.append({
                "start_date": s_date,
                "rate": float(d["daily_rate"]),
                "ts": ts
            })
    
    if not rates_list:
        rates_list = [{"start_date": datetime.strptime(system_start_date_str, "%Y-%m-%d").date(), "rate": 100.0, "ts": 0.0}]
    
    rates_list.sort(key=lambda x: (x["start_date"], x["ts"]))
    
    today = date.today()
    system_start = datetime.strptime(system_start_date_str, "%Y-%m-%d").date()
    
    current_active_rate = rates_list[0]["rate"]
    for r in rates_list:
        if today >= r["start_date"]:
            current_active_rate = r["rate"]

    if today < system_start:
        return 0.0, current_active_rate

    total_allocated = 0.0
    current_eval_date = system_start
    
    while current_eval_date <= today:
        active_rate = rates_list[0]["rate"]
        for r in rates_list:
            if current_eval_date >= r["start_date"]:
                active_rate = r["rate"]
        total_allocated += active_rate
        current_eval_date = pd.Timedelta(days=1) + current_eval_date

    return total_allocated, current_active_rate

def calculate_finances():
    initial_bank, current_savings, start_date_str = get_account_data()
    
    total_auto_allocated, current_rate = calculate_total_allocated(start_date_str)
    
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
            
    if daily_wallet_balance < 0:
        actual_bank_balance = initial_bank - (total_daily_spent + total_daily_moved) - total_direct_spent
    else:
        actual_bank_balance = initial_bank - total_auto_allocated - total_direct_spent
    
    return actual_bank_balance, daily_wallet_balance, current_savings, start_date_str, current_rate

def get_past_descriptions():
    docs = db.collection("daily_transactions").stream()
    past_items = set()
    for doc in docs:
        desc = doc.to_dict().get("description")
        if desc:
            past_items.add(desc.strip())
    return sorted(list(past_items))

def get_direct_categories():
    default_cats = ["ค่าน้ำมัน", "ค่าเน็ต", "ค่าผ่อนของ", "ให้แฟน", "อื่นๆ"]
    docs = db.collection("direct_transactions").stream()
    custom_cats = set(default_cats)
    for doc in docs:
        cat = doc.to_dict().get("category")
        if cat and not cat.startswith("ฝากเงินเก็บ") and not cat.startswith("ถอนเงินเก็บ"):
            custom_cats.add(cat.strip())
    return sorted(list(custom_cats))

def get_income_categories():
    default_types = [
        "เงินเดือน/รายรับหลัก", 
        "รายรับอื่นๆ", 
        "ฝากเงินเก็บ (หักจากยอดเงินปัจจุบัน) 🏦", 
        "ฝากเงินเก็บ (หักจากเงินรายวันสะสม) 📱", 
        "ถอนเงินเก็บมาใช้ (กลับเข้าบัญชีปัจจุบัน) 💵"
    ]
    docs = db.collection("income_history").stream()
    custom_types = set(default_types)
    for doc in docs:
        inc_type = doc.to_dict().get("type")
        if inc_type:
            custom_types.add(inc_type.strip())
    return sorted(list(custom_types))

# 4. แสดงผล Dashboard
bank_balance, daily_wallet, current_savings, start_date_str, current_rate = calculate_finances()

# 🧮 คำนวณวันคงเหลือ (Runway Days) นับวันปัจจุบันเป็นวันที่ 1
total_spendable = bank_balance + daily_wallet
if current_rate > 0 and total_spendable > 0:
    runway_days = int(total_spendable // current_rate) # จำนวนวันเต็ม
    today_date = date.today()
    # นับวันนี้เป็นวันที่ 1 ดังนั้นวันสุดท้ายคือวันนี้ + (runway_days - 1)
    end_spend_date = today_date + timedelta(days=max(0, runway_days - 1))
    thai_months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    end_date_str = f"{end_spend_date.day} {thai_months[end_spend_date.month - 1]} {end_spend_date.year + 543}"
    runway_text = f"ใช้จ่ายได้อีกประมาณ {runway_days:,} วัน (ถึงวันที่ {end_date_str})"
else:
    runway_text = "ไม่พอดำเนินการ (ยอดเงินรวมเป็นศูนย์หรือติดลบ)"

daily_status = f"▲ คงเหลือ +{daily_wallet:,.2f}" if daily_wallet >= 0 else f"▼ ติดลบ {daily_wallet:,.2f}"
single_ticker = f"• โควตาจัดสรร: ฿{current_rate:,.0f}/วัน &nbsp;&nbsp;&nbsp;&nbsp; • กระเป๋ารายวันสะสม: {daily_status} บาท &nbsp;&nbsp;&nbsp;&nbsp; • บัญชีหลักปัจจุบัน: ฿{bank_balance:,.2f} &nbsp;&nbsp;&nbsp;&nbsp; • ยอดเงินเก็บออม: ฿{current_savings:,.2f} &nbsp;&nbsp;&nbsp;&nbsp; • สถานะระบบ: เปิดทำงานปกติ 🟢 &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"

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
st.caption(f"ระบบมอนิเตอร์และบริหารกระเป๋าเงินดิจิทัล (อัตราจัดสรรปัจจุบัน: ฿{current_rate:,.0f}/วัน)")

# 📅 การ์ดแสดงผลระยะเวลาที่ใช้จ่ายได้จริง (Runway Indicator)
st.markdown(f"""
    <div class="stock-card" style="border-left: 5px solid #b388ff;">
        <div class="lbl-title">⏳ FINANCIAL RUNWAY (ระยะเวลาใช้จ่ายที่เหลือ)</div>
        <div class="lbl-val ticker-purple" style="font-size: 22px;">{runway_text}</div>
        <div style="font-size: 12px; color: #848e9c; margin-top: 5px;">
            *คำนวณจาก (งบรายวันคงเหลือ + บัญชีหลัก = ฿{total_spendable:,.2f}) ÷ ฿{current_rate:,.0f}/วัน (นับวันนี้เป็นวันที่ 1)
        </div>
    </div>
""", unsafe_allow_html=True)

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

# 5. ฟอร์มจัดการ
st.subheader("➕ บันทึกธุรกรรมใหม่ (Execute Order)")
tab1, tab2, tab3, tab4 = st.tabs(["🛒 บันทึกรายวัน", "💳 หักบัญชีหลักโดยตรง", "💰 ฝาก/ถอน/รายรับ", "⚙️ ตั้งค่าเงินรายวัน"])

with tab1:
    with st.form("daily_form", clear_on_submit=True):
        st.write("📝 **รายละเอียดรายการ**")
        past_suggestions = get_past_descriptions()
        options = ["-- พิมพ์ระบุรายการใหม่เอง --"] + past_suggestions
        selected_item = st.selectbox("เลือกรายการเดิม หรือเลือกพิมพ์ใหม่:", options=options, index=0)
        custom_desc = st.text_input("ระบุรายละเอียดรายการ (พิมพ์คำใหม่ที่นี่):", placeholder="เช่น ค่าข้าวเช้า, กาแฟ")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="daily_amt")
        submit_daily = st.form_submit_button("💾 ยืนยันคำสั่งซื้อรายวัน")
        
        if submit_daily and amount > 0:
            final_desc = selected_item if (selected_item != "-- พิมพ์ระบุรายการใหม่เอง --" and not custom_desc) else custom_desc
            if final_desc and final_desc.strip():
                today_str = datetime.now().strftime('%Y-%m-%d')
                db.collection("daily_transactions").add({
                    "date": today_str,
                    "description": final_desc.strip(),
                    "amount": amount,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success(f"บันทึกคำสั่ง {final_desc} ฿{amount} สำเร็จ!")
                st.rerun()
            else:
                st.warning("กรุณาระบุรายละเอียดรายการ")

with tab2:
    existing_categories = get_direct_categories()
    cat_options = ["-- พิมพ์ระบุประเภทใหม่ --"] + existing_categories
    
    selected_cat_opt = st.selectbox("เลือกประเภทค่าใช้จ่ายหลัก:", options=cat_options, index=1 if len(cat_options)>1 else 0)
    
    custom_cat_input = ""
    if selected_cat_opt == "-- พิมพ์ระบุประเภทใหม่ --":
        custom_cat_input = st.text_input("ระบุประเภทค่าใช้จ่ายใหม่:", placeholder="เช่น ค่าซ่อมรถ, ค่าประกัน")

    with st.form("direct_form", clear_on_submit=True):
        note_direct = st.text_input("ระบุบันทึกย่อ (ถ้ามี):", placeholder="เช่น ปั๊ม ปตท., งวด 3/12")
        amount_direct = st.number_input("จำนวนเงินที่จ่ายจริง (บาท)", min_value=0.0, step=1.0, key="direct_amt")
        submit_direct = st.form_submit_button("💳 บันทึกตัดจ่ายบัญชีหลัก")
        
        if submit_direct and amount_direct > 0:
            final_category = custom_cat_input.strip() if selected_cat_opt == "-- พิมพ์ระบุประเภทใหม่ --" else selected_cat_opt
            
            if final_category:
                today_str = datetime.now().strftime('%Y-%m-%d')
                db.collection("direct_transactions").add({
                    "date": today_str,
                    "category": final_category,
                    "amount": amount_direct,
                    "note": note_direct.strip() if note_direct else "",
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success(f"บันทึกจ่าย [{final_category}] ฿{amount_direct} เรียบร้อย!")
                st.rerun()
            else:
                st.warning("กรุณาระบุประเภทค่าใช้จ่ายหลัก")

with tab3:
    existing_inc_categories = get_income_categories()
    inc_options = ["-- พิมพ์ระบุประเภทใหม่ --"] + existing_inc_categories
    
    selected_inc_opt = st.selectbox("เลือกประเภทรายการเงินเข้า/เงินเก็บ:", options=inc_options, index=1 if len(inc_options)>1 else 0)
    
    custom_inc_type_input = ""
    if selected_inc_opt == "-- พิมพ์ระบุประเภทใหม่ --":
        custom_inc_type_input = st.text_input("ระบุประเภทรายการเงินใหม่:", placeholder="เช่น เงินคืนภาษี, โบนัส")

    with st.form("income_form", clear_on_submit=True):
        note_income = st.text_input("ระบุบันทึกย่อ (ถ้ามี):", placeholder="เช่น รายรับเสริม, ออมเงินประจำเดือน")
        amount_income = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1.0, key="income_amt")
        submit_income = st.form_submit_button("💵 ประมวลผลธุรกรรมเงิน")
        
        if submit_income and amount_income > 0:
            income_type = custom_inc_type_input.strip() if selected_inc_opt == "-- พิมพ์ระบุประเภทใหม่ --" else selected_inc_opt
            
            if income_type:
                today_str = datetime.now().strftime('%Y-%m-%d')
                final_note = note_income.strip() if note_income else ""
                
                if "ฝากเงินเก็บ (หักจากยอดเงินปัจจุบัน)" in income_type:
                    if bank_balance >= amount_income:
                        db.collection("account").document("main_wallet").update({"savings": current_savings + amount_income})
                        db.collection("direct_transactions").add({
                            "date": today_str,
                            "category": "ฝากเงินเก็บ (หักจากบัญชีหลัก)",
                            "amount": amount_income,
                            "note": final_note,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        st.success(f"โอนเงิน ฿{amount_income} เข้าดัชนีเงินเก็บแล้ว!")
                    else:
                        st.error("เงินสดในบัญชีปัจจุบันไม่เพียงพอ")
                
                elif "ฝากเงินเก็บ (หักจากเงินรายวันสะสม)" in income_type:
                    if daily_wallet >= amount_income:
                        db.collection("account").document("main_wallet").update({"savings": current_savings + amount_income})
                        db.collection("direct_transactions").add({
                            "date": today_str,
                            "category": "ฝากเงินเก็บ (หักจากเงินรายวัน)",
                            "amount": amount_income,
                            "note": final_note,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        st.success(f"ย้ายโควตา ฿{amount_income} ไปยังเงินเก็บแล้ว!")
                    else:
                        st.error("ยอดสะสมรายวันไม่เพียงพอ")
                
                elif "ถอนเงินเก็บมาใช้" in income_type:
                    if current_savings >= amount_income:
                        db.collection("account").document("main_wallet").update({"savings": current_savings - amount_income})
                        db.collection("direct_transactions").add({
                            "date": today_str,
                            "category": "ถอนเงินเก็บกลับเข้าบัญชี",
                            "amount": -amount_income,
                            "note": final_note,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        st.success(f"ดึงสภาพคล่อง ฿{amount_income} กลับเข้าบัญชีหลัก!")
                    else:
                        st.error("ยอดเงินเก็บมีไม่เพียงพอสำหรับการถอน")
                
                else:
                    add_income_to_bank(amount_income)
                    db.collection("income_history").add({
                        "date": today_str,
                        "type": income_type,
                        "amount": amount_income,
                        "note": final_note,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    st.success(f"บันทึกรายรับ [{income_type}] ฿{amount_income} เข้าสู่พอร์ตแล้ว!")
                
                st.rerun()
            else:
                st.warning("กรุณาระบุประเภทรายการเงิน")

# TAB 4: ปรับเปลี่ยนอัตราเงินรายวัน
with tab4:
    st.write("⚙️ **ปรับเปลี่ยนอัตราจัดสรรเงินรายวัน**")
    st.caption("การปรับเปลี่ยนจะมีผลเริ่มตั้งแต่วันที่ระบุเป็นต้นไป")
    
    effective_date = st.date_input("วันที่เริ่มใช้อัตราใหม่", value=date.today(), key="rate_eff_date")
    val_rate = st.number_input("อัตราเงินจัดสรรใหม่ (บาท/วัน)", min_value=1.0, value=100.0, step=10.0, key="rate_val_input")
    
    if st.button("⚙️ บันทึกอัตราเงินรายวันใหม่"):
        if val_rate > 0:
            set_new_daily_rate(effective_date.strftime('%Y-%m-%d'), val_rate)
            st.success(f"อัปเดตอัตราเป็น ฿{val_rate:,.0f}/วัน เรียบร้อยแล้ว!")
            st.rerun()
        else:
            st.warning("กรุณาระบุจำนวนเงินที่มากกว่า 0")

# 6. แสดงประวัติ
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
