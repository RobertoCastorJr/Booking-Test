import smtplib
import ssl
from email.message import EmailMessage
from datetime import date, datetime, time, timedelta
import sqlite3
import time as time_lib
import uuid
import io
import qrcode
import pandas as pd
import streamlit as st


def send_admin_gmail_notification(booking_details: dict) -> tuple[bool, str]:
    try:
        sender = st.secrets["GMAIL_SENDER"].strip()
        app_password = st.secrets["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
        recipient = st.secrets["ADMIN_NOTIFY_EMAIL"].strip()

        msg = EmailMessage()
        msg["Subject"] = f"📅 New Booking: {booking_details['Name']} ({booking_details['Ref']})"
        msg["From"] = sender
        msg["To"] = recipient

        body = (
            f"You have a new appointment booking!\n\n"
            f"Reference: {booking_details['Ref']}\n"
            f"Client Name: {booking_details['Name']}\n"
            f"Client Email: {booking_details.get('Email') or 'Not provided'}\n"
            f"Service: {booking_details['Service']}\n"
            f"Date: {booking_details['Date'].strftime('%A, %b %d, %Y')}\n"
            f"Time: {booking_details['Time'].strftime('%I:%M %p')}\n"
            f"Notes: {booking_details.get('Notes') or 'None'}\n"
        )
        msg.set_content(body)

        smtp_host = "smtp" + ".gmail.com"
        context = ssl.create_default_context()

        with smtplib.SMTP(smtp_host, 587, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(sender, app_password)
            smtp.send_message(msg)

        return True, "Admin notified via email"
    except Exception as e:
        return False, f"Email notification skipped: {e}"


# ==========================================
# 1. DYNAMIC THEME & PAGE CONFIG (MUST BE FIRST)
# ==========================================
def generate_booking_qr(booking_details: dict) -> bytes:
    qr_text = (
        f"Booking Ref: {booking_details['Ref']}\n"
        f"Name: {booking_details['Name']}\n"
        f"Service: {booking_details['Service']}\n"
        f"Date: {booking_details['Date'].strftime('%b %d, %Y')}\n"
        f"Time: {booking_details['Time'].strftime('%I:%M %p')}"
    )
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


now = datetime.now()
current_month = now.month

if current_month == 10:
    THEME = {
        "title": "Spooky Halloween Booking Schedule",
        "icon": "🎃",
        "header": "🎃 Spooky Booking",
        "msg": "Grab your slot before it vanishes! 🦇",
        "weekend": "💀",
        "free": "🟠",
        "locked": "⚰️",
        "btn": "secondary",
    }
elif current_month == 12:
    THEME = {
        "title": "Merry Christmas Booking Schedule",
        "icon": "🎄",
        "header": "🎄 Festive Booking",
        "msg": "Book your holiday slots before Santa arrives! 🎅",
        "weekend": "🎁",
        "free": "🟢",
        "locked": "🦌",
        "btn": "primary",
    }
else:
    THEME = {
        "title": "7-Day Weekly Booking Schedule",
        "icon": "📅",
        "header": "📅 Weekly Booking",
        "msg": "Click an open green slot below to book.",
        "weekend": "🎨",
        "free": "🟢",
        "locked": "🔒",
        "btn": "secondary",
    }

st.set_page_config(
    page_title=THEME["title"],
    page_icon=THEME["icon"],
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject CSS to tighten vertical spacing and fit everything on one screen
st.markdown(
    """
    <style>
        /* Add enough top padding so the title isn't cut off */
        .block-container {
            padding-top: 3.8rem !important;
            padding-bottom: 0rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
            max-width: 100%;
        }
        /* Hide Streamlit default header & footer */
        header[data-testid="stHeader"] {
            height: 2rem;
            background: transparent;
        }
        footer {display: none;}
        /* Tighten vertical gaps between elements */
        div[data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        /* Highlight today's container box */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.today-marker) {
            background-color: rgba(56, 189, 248, 0.12) !important;
            border: 2px solid #38bdf8 !important;
            border-radius: 12px !important;
        }

        /* Available (Active) Slots - Vibrant Emerald Green */
        div.stButton > button[kind="secondary"]:not(:disabled),
        div.stButton > button[kind="primary"]:not(:disabled) {
            background-color: rgba(16, 185, 129, 0.16) !important;
            border: 1px solid #10b981 !important;
            color: #ecfdf5 !important;
            font-weight: 600 !important;
        }
        div.stButton > button[kind="secondary"]:not(:disabled):hover,
        div.stButton > button[kind="primary"]:not(:disabled):hover {
            background-color: rgba(16, 185, 129, 0.35) !important;
            border-color: #34d399 !important;
            color: #ffffff !important;
        }

        /* Reserved / Unavailable Disabled Slots - Soft Red */
        div.stButton > button:disabled {
            background-color: rgba(239, 68, 68, 0.14) !important;
            border: 1px solid rgba(239, 68, 68, 0.45) !important;
            color: #fca5a5 !important;
            opacity: 1 !important;
        }

        /* Compact day headers */
        h3 {
            font-size: 1.45rem !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        hr {
            margin: 0.35rem 0 !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# 2. SQLITE PERSISTENT DATABASE HELPERS
# ==========================================
DB_FILE = "bookings.db"
SERVICES = {
    "Initial Consultation (Free - 1 hr)": {"price": 0, "duration": 1},
    "Standard Session ($50 - 1 hr)": {"price": 50, "duration": 1},
    "Extended Deep-Dive ($90 - 2 hrs)": {"price": 90, "duration": 2},
    "Weekend Check-In ($40 - 1 hr)": {"price": 40, "duration": 1},
    "Basic Consultation ($500 - 1 hr)": {"price": 500, "duration": 1},
    "Standard Treatment ($1,200 - 2 hrs)": {"price": 1200, "duration": 2},
    "Full Package ($1,800 - 3 hrs)": {"price": 1800, "duration": 3},
}


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                ref_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                service TEXT,
                booking_date TEXT NOT NULL,
                booking_time TEXT NOT NULL,
                notes TEXT,
                UNIQUE(booking_date, booking_time)
            )
        """)


def load_bookings():
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT ref_code, name, email, service, booking_date, booking_time, notes
            FROM bookings
        """).fetchall()
    result = []
    for r in rows:
        result.append({
            "Ref": r[0],
            "Name": r[1],
            "Email": r[2] or "",
            "Service": r[3] or "Standard Session ($50 - 1 hr)",
            "Date": date.fromisoformat(r[4]),
            "Time": time.fromisoformat(r[5]),
            "Notes": r[6] or "",
        })
    return result


def save_booking(ref_code, name, email, service, b_date, b_time, notes):
    duration_hrs = SERVICES.get(service, {}).get("duration", 1)
    new_start = datetime.combine(b_date, b_time)
    new_end = new_start + timedelta(hours=duration_hrs)

    try:
        with sqlite3.connect(DB_FILE) as conn:
            # Check for overlapping multi-hour bookings on the same date
            existing_rows = conn.execute(
                "SELECT service, booking_time FROM bookings WHERE booking_date = ?",
                (b_date.isoformat(),),
            ).fetchall()

            for ex_service, ex_time_str in existing_rows:
                ex_duration = SERVICES.get(ex_service, {}).get("duration", 1)
                ex_start = datetime.combine(b_date, time.fromisoformat(ex_time_str))
                ex_end = ex_start + timedelta(hours=ex_duration)
                if new_start < ex_end and new_end > ex_start:
                    return False

            conn.execute(
                """
                INSERT INTO bookings (ref_code, name, email, service, booking_date, booking_time, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref_code,
                    name,
                    email,
                    service,
                    b_date.isoformat(),
                    b_time.isoformat(),
                    notes,
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def delete_booking(ref_code):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM bookings WHERE ref_code = ?", (ref_code,))


def init_block_tables():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_type TEXT NOT NULL,
                rule_value TEXT NOT NULL,
                reason TEXT,
                UNIQUE(rule_type, rule_value)
            )
        """)


def load_blocked_rules():
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("SELECT id, rule_type, rule_value, reason FROM blocked_rules").fetchall()
    return [{"id": r[0], "type": r[1], "value": r[2], "reason": r[3] or "Unavailable"} for r in rows]


def add_blocked_rule(rule_type: str, rule_value: str, reason: str):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT INTO blocked_rules (rule_type, rule_value, reason) VALUES (?, ?, ?)",
                (rule_type, rule_value, reason.strip() or "Unavailable"),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def delete_blocked_rule(rule_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM blocked_rules WHERE id = ?", (rule_id,))


init_db()
init_block_tables()

# ==========================================
# 3. SESSION TIMEOUT & STATE HELPERS
# ==========================================

TIMEOUT_SECONDS = 5 * 60
st.session_state.setdefault("last_interaction", time_lib.time())
st.session_state.setdefault("week_offset", 0)
st.session_state.setdefault("keep_admin_open", False)


def record_user_activity():
    st.session_state.last_interaction = time_lib.time()


def reset_booking_workflow():
    keys_to_clear = [
        "preselected_date",
        "preselected_time",
        "review_mode",
        "input_name",
        "input_email",
        "input_service",
        "input_date",
        "input_time",
        "input_notes",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


@st.fragment(run_every=10)
def check_session_timeout():
    elapsed = time_lib.time() - st.session_state.last_interaction
    if elapsed > TIMEOUT_SECONDS and not st.session_state.get("session_expired", False):
        st.session_state.session_expired = True
        st.rerun()


check_session_timeout()

if st.session_state.get("session_expired", False):
    st.title("🔒 Session Expired")
    st.error("Your scheduling connection has timed out due to 5 minutes of inactivity.")
    if st.button("🔄 Refresh & Start New Session", type="primary", use_container_width=True):
        st.session_state.session_expired = False
        record_user_activity()
        reset_booking_workflow()
        st.rerun()
    st.stop()


def get_booking_at_slot(bookings_list, target_date, target_slot):
    """Returns the booking covering target_slot (including multi-hour durations), or None."""
    target_dt = datetime.combine(target_date, target_slot)
    for b in bookings_list:
        if b["Date"] == target_date:
            service_info = SERVICES.get(b["Service"], {})
            duration_hrs = service_info.get("duration", 1) if isinstance(service_info, dict) else 1
            start_dt = datetime.combine(b["Date"], b["Time"])
            end_dt = start_dt + timedelta(hours=duration_hrs)
            if start_dt <= target_dt < end_dt:
                return b
    return None
# ==========================================
# 4. SCHEDULE DATA & MULTI-WEEK CALCULATION
# ==========================================

BUSINESS_HOURS = [time(hour, 0) for hour in range(9, 17)]
today = date.today()
current_time_obj = now.time()
base_monday = today - timedelta(days=today.weekday())
start_of_week = base_monday + timedelta(weeks=st.session_state.week_offset)
WEEK_DATES = [start_of_week + timedelta(days=i) for i in range(7)]

bookings = load_bookings()
blocked_rules = load_blocked_rules()

BLOCKED_HOURS = {
    time.fromisoformat(r["value"]): r["reason"]
    for r in blocked_rules
    if r["type"] == "DAILY_HOUR"
}
BLOCKED_DATES = {
    date.fromisoformat(r["value"]): r["reason"]
    for r in blocked_rules
    if r["type"] == "SPECIFIC_DATE"
}

# ==========================================
# 5. SIDEBAR: CLIENT LOOKUP & ADMIN PANEL
# ==========================================

st.sidebar.title("🔍 Find My Booking")
lookup_code = (
    st.sidebar.text_input(
        "Enter 6-Character Booking Ref:",
        placeholder="e.g., A1B2C3",
        on_change=record_user_activity,
    )
    .strip()
    .upper()
)

if lookup_code:
    match = next((b for b in bookings if b["Ref"] == lookup_code), None)
    if match:
        st.sidebar.success(
            f"{match['Name']}\n\n"
            f"📅 {match['Date'].strftime('%b %d, %Y')} @ {match['Time'].strftime('%I:%M %p')}\n\n"
            f"🏷️ {match['Service']}"
        )
        sidebar_qr_bytes = generate_booking_qr(match)
        st.sidebar.image(sidebar_qr_bytes, caption="Booking QR Pass", width=150)
        st.sidebar.download_button(
            label="📥 Download QR Pass",
            data=sidebar_qr_bytes,
            file_name=f"booking_{match['Ref']}.png",
            mime="image/png",
            use_container_width=True,
            on_click=record_user_activity,
        )
        if match["Date"] >= today:
            if st.sidebar.button("❌ Cancel My Appointment", use_container_width=True):
                delete_booking(match["Ref"])
                record_user_activity()
                st.sidebar.warning("Appointment cancelled.")
                time_lib.sleep(1)
                st.rerun()
    else:
        st.sidebar.error("No booking found.")

st.sidebar.markdown("---")
st.sidebar.title("🔐 Admin Panel")

try:
    ADMIN_PASS = st.secrets["ADMIN_PASSWORD"]
except Exception:
    ADMIN_PASS = "admin123"

admin_password = st.sidebar.text_input(
    "Enter Admin Password",
    type="password",
    placeholder="Password...",
    on_change=record_user_activity,
)
is_admin = admin_password == ADMIN_PASS

if is_admin:
    st.sidebar.success("🔑 Admin Mode Active")
elif admin_password:
    st.sidebar.error("❌ Incorrect Password")
# ==========================================
# 6. STANDALONE QR CONFIRMATION SCREEN
# ==========================================

if "last_confirmed_booking" in st.session_state:
    confirmed = st.session_state.last_confirmed_booking
    qr_bytes = generate_booking_qr(confirmed)
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        with st.container(border=True):
            st.success(f"🎫 Booking Confirmed! Ref: {confirmed['Ref']}")
            if "EmailStatus" in confirmed:
                ok, msg = confirmed["EmailStatus"]
                if ok:
                    st.info(f"📧 {msg}")
                else:
                    st.warning(f"⚠️ {msg}")
            q_col1, q_col2 = st.columns([1, 1.5])
            with q_col1:
                st.image(qr_bytes, width=180)
            with q_col2:
                st.markdown(
                    f"Name: {confirmed['Name']}\n\n"
                    f"Service: {confirmed['Service']}\n\n"
                    f"Date: {confirmed['Date'].strftime('%a, %b %d, %Y')}\n\n"
                    f"Time: {confirmed['Time'].strftime('%I:%M %p')}"
                )
            st.download_button(
                label="📥 Download QR Code",
                data=qr_bytes,
                file_name=f"booking_{confirmed['Ref']}.png",
                mime="image/png",
                type="primary",
                use_container_width=True,
                on_click=record_user_activity,
            )
            if st.button("⬅️ Back to Schedule", use_container_width=True):
                st.session_state.pop("last_confirmed_booking", None)
                record_user_activity()
                st.rerun()
    st.stop()

# ==========================================
# 7. MODAL DIALOG FOR BOOKING & ADMIN
# ==========================================

@st.dialog("📝 Appointment Booking", width="large")
def show_booking_modal():
    st.session_state.setdefault("input_name", "")
    st.session_state.setdefault("input_email", "")
    st.session_state.setdefault("input_service", list(SERVICES.keys())[0])
    st.session_state.setdefault("input_date", st.session_state.preselected_date)
    st.session_state.setdefault("input_time", st.session_state.preselected_time)
    st.session_state.setdefault("input_notes", "")
    st.session_state.setdefault("review_mode", False)

    if st.session_state.review_mode:
        st.warning("⚠️ Verify your details before final submission.")
        review_df = pd.DataFrame([
            {"Detail": "Full Name", "Your Value": st.session_state.input_name},
            {
                "Detail": "Email",
                "Your Value": st.session_state.input_email.strip() or "Not provided",
            },
            {"Detail": "Service", "Your Value": st.session_state.input_service},
            {
                "Detail": "Date",
                "Your Value": st.session_state.input_date.strftime("%A, %b %d, %Y"),
            },
            {
                "Detail": "Time",
                "Your Value": st.session_state.input_time.strftime("%I:%M %p"),
            },
            {
                "Detail": "Notes",
                "Your Value": st.session_state.input_notes.strip() or "None",
            },
        ])
        st.dataframe(review_df, use_container_width=True, hide_index=True)

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("✅ Confirm", type="primary", use_container_width=True):
                record_user_activity()
                ref_code = uuid.uuid4().hex[:6].upper()
                saved = save_booking(
                    ref_code=ref_code,
                    name=st.session_state.input_name.strip(),
                    email=st.session_state.input_email.strip(),
                    service=st.session_state.input_service,
                    b_date=st.session_state.input_date,
                    b_time=st.session_state.input_time,
                    notes=st.session_state.input_notes.strip(),
                )
                if not saved:
                    st.error("❌ Slot just taken! Choose another.")
                    st.session_state.review_mode = False
                else:
                    booking_payload = {
                        "Ref": ref_code,
                        "Name": st.session_state.input_name.strip(),
                        "Email": st.session_state.input_email.strip(),
                        "Service": st.session_state.input_service,
                        "Date": st.session_state.input_date,
                        "Time": st.session_state.input_time,
                        "Notes": st.session_state.input_notes.strip(),
                    }
                    email_ok, email_msg = send_admin_gmail_notification(booking_payload)
                    booking_payload["EmailStatus"] = (email_ok, email_msg)
                    st.session_state.last_confirmed_booking = booking_payload
                    reset_booking_workflow()
                    st.rerun()
        with b2:
            if st.button("✏️ Edit", use_container_width=True):
                record_user_activity()
                st.session_state.review_mode = False
                st.rerun()
        with b3:
            if st.button("Cancel ❌", use_container_width=True):
                record_user_activity()
                reset_booking_workflow()
                st.rerun()
    else:
        try:
            time_index = BUSINESS_HOURS.index(st.session_state.input_time)
        except ValueError:
            time_index = 0

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.input_name = st.text_input(
                "Full Name *",
                value=st.session_state.input_name,
                placeholder="e.g., Alice Johnson",
                on_change=record_user_activity,
            )
            st.session_state.input_email = st.text_input(
                "Email (Optional)",
                value=st.session_state.input_email,
                placeholder="e.g., alice@example.com",
                on_change=record_user_activity,
            )
            st.session_state.input_service = st.selectbox(
                "Service",
                options=list(SERVICES.keys()),
                index=list(SERVICES.keys()).index(st.session_state.input_service),
                on_change=record_user_activity,
            )
        with col2:
            st.session_state.input_date = st.date_input(
                "Date",
                value=st.session_state.input_date,
                min_value=today,
                on_change=record_user_activity,
            )
            st.session_state.input_time = st.selectbox(
                "Time Slot",
                options=BUSINESS_HOURS,
                index=time_index,
                format_func=lambda t: t.strftime("%I:%M %p"),
                on_change=record_user_activity,
            )
        st.session_state.input_notes = st.text_input(
            "Notes (Optional)",
            value=st.session_state.input_notes,
            placeholder="Any remarks...",
            on_change=record_user_activity,
        )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("👉 Review Booking", type="primary", use_container_width=True):
                record_user_activity()
                is_selected_past = (st.session_state.input_date < today) or (
                    st.session_state.input_date == today
                    and st.session_state.input_time <= datetime.now().time()
                )
                duration_hrs = SERVICES[st.session_state.input_service]["duration"]
                start_dt = datetime.combine(st.session_state.input_date, st.session_state.input_time)
                closing_dt = datetime.combine(st.session_state.input_date, time(17, 0))

                # Check if all consecutive hours needed are free
                slot_conflict = False
                for h in range(duration_hrs):
                    check_time = (start_dt + timedelta(hours=h)).time()
                    if (
                        check_time in BLOCKED_HOURS
                        or get_booking_at_slot(bookings, st.session_state.input_date, check_time) is not None
                    ):
                        slot_conflict = True
                        break

                if not st.session_state.input_name.strip():
                    st.error("Please enter your name.")
                elif is_selected_past:
                    st.error("❌ Cannot choose a past date or time.")
                elif st.session_state.input_date in BLOCKED_DATES:
                    st.error(f"❌ Unavailable: {BLOCKED_DATES[st.session_state.input_date]}")
                elif start_dt + timedelta(hours=duration_hrs) > closing_dt:
                    st.error(f"❌ {st.session_state.input_service} extends past closing time (5:00 PM).")
                elif slot_conflict:
                    st.error(f"❌ Not enough consecutive free hours for a {duration_hrs}-hour service.")
                else:
                    st.session_state.review_mode = True
                    st.rerun()
        with b2:
            if st.button("Cancel ❌", use_container_width=True):
                record_user_activity()
                reset_booking_workflow()
                st.rerun()


@st.dialog("📥 Master Schedule & Management", width="large")
def show_admin_modal():
    tab1, tab2 = st.tabs(["📅 Bookings", "⛔ Holidays & Breaks"])

    with tab1:
        if not bookings:
            st.info("No appointments scheduled yet.")
        else:
            df = pd.DataFrame(bookings).sort_values(by=["Date", "Time"])
            upcoming_count = len(df[df["Date"] >= today])
            est_revenue = sum(
                SERVICES.get(s, {}).get("price", 0) if isinstance(SERVICES.get(s), dict) else SERVICES.get(s, 0)
                for s in df["Service"]
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Bookings", len(df))
            m2.metric("Upcoming", upcoming_count)
            m3.metric("Est. Revenue", f"${est_revenue:,}")

            display_df = df.copy()
            display_df["Date"] = display_df["Date"].apply(lambda d: d.strftime("%Y-%m-%d"))
            display_df["Time"] = display_df["Time"].apply(lambda t: t.strftime("%I:%M %p"))
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=200)

            c1, c2 = st.columns([1, 2])
            with c1:
                csv_data = display_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Export CSV",
                    data=csv_data,
                    file_name=f"booking_schedule_{today}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c2:
                booking_labels = [
                    f"[{b['Ref']}] {b['Date'].strftime('%b %d')} @ {b['Time'].strftime('%I:%M %p')} - {b['Name']}"
                    for b in bookings
                ]
                sc1, sc2 = st.columns([2, 1])
                with sc1:
                    selected_idx = st.selectbox(
                        "Cancel slot:",
                        options=range(len(bookings)),
                        format_func=lambda idx: booking_labels[idx],
                        label_visibility="collapsed",
                    )
                with sc2:
                    if st.button("🗑️ Cancel", use_container_width=True):
                        delete_booking(bookings[selected_idx]["Ref"])
                        record_user_activity()
                        st.session_state.keep_admin_open = True
                        st.rerun()

    with tab2:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("☕ Block Daily Break Hour")
            break_hour = st.selectbox(
                "Select Hour",
                options=BUSINESS_HOURS,
                index=3,
                format_func=lambda t: t.strftime("%I:%M %p"),
            )
            break_reason = st.text_input("Label", value="Lunch Break", key="break_label")
            if st.button("➕ Add Daily Break", use_container_width=True):
                if add_blocked_rule("DAILY_HOUR", break_hour.isoformat(), break_reason):
                    record_user_activity()
                    st.session_state.keep_admin_open = True
                    st.rerun()
                else:
                    st.warning("This hour is already blocked.")

        with col_b:
            st.markdown("🏖️ Block Full Date / Holiday")
            holiday_date = st.date_input("Select Date", min_value=today, key="holiday_picker")
            holiday_reason = st.text_input("Reason", value="Holiday / Closed", key="holiday_label")
            if st.button("➕ Block Date", use_container_width=True):
                if add_blocked_rule("SPECIFIC_DATE", holiday_date.isoformat(), holiday_reason):
                    record_user_activity()
                    st.session_state.keep_admin_open = True
                    st.rerun()
                else:
                    st.warning("This date is already blocked.")
        st.markdown("---")
        st.markdown("Active Blocks (Click to Remove)")
        if not blocked_rules:
            st.caption("No active holidays or break rules.")
        else:
            for rule in blocked_rules:
                r_col1, r_col2 = st.columns([4, 1])
                if rule["type"] == "DAILY_HOUR":
                    formatted_val = time.fromisoformat(rule["value"]).strftime("%I:%M %p")
                    desc = f"☕ Daily Break: {formatted_val} — {rule['reason']}"
                else:
                    formatted_val = date.fromisoformat(rule["value"]).strftime("%b %d, %Y")
                    desc = f"🏖️ Holiday/Closed: {formatted_val} — {rule['reason']}"
                r_col1.markdown(desc)
                if r_col2.button("🗑️", key=f"del_rule_{rule['id']}", use_container_width=True):
                    delete_blocked_rule(rule["id"])
                    record_user_activity()
                    st.session_state.keep_admin_open = True
                    st.rerun()


# Trigger booking modal if a slot was clicked
if st.session_state.get("preselected_date") and st.session_state.get("preselected_time"):
    show_booking_modal()

# ==========================================
# 8. COMPACT SINGLE-ROW HEADER & NAVIGATION
# ==========================================

if is_admin:
    h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([3.2, 1.8, 0.8, 0.8, 0.8])
else:
    h_col1, h_col2, h_col3, h_col4 = st.columns([3.5, 2.0, 0.8, 0.8])

with h_col1:
    st.markdown(
        f"{THEME['header']} — {THEME['msg']}",
        unsafe_allow_html=True,
    )
with h_col2:
    st.markdown(
        f"📆 {WEEK_DATES[0].strftime('%b %d')} – {WEEK_DATES[-1].strftime('%b %d, %Y')}",
        unsafe_allow_html=True,
    )
with h_col3:
    if st.button(
        "⬅️ Prev",
        disabled=(st.session_state.week_offset <= 0),
        use_container_width=True,
    ):
        st.session_state.week_offset -= 1
        record_user_activity()
        st.rerun()
with h_col4:
    if st.button(
        "Next ➡️",
        disabled=(st.session_state.week_offset >= 8),
        use_container_width=True,
    ):
        st.session_state.week_offset += 1
        record_user_activity()
        st.rerun()

if is_admin:
    with h_col5:
        if st.button("⚙️ Admin", key="open_admin_btn", type="primary", use_container_width=True):
            st.session_state.keep_admin_open = True

if is_admin and st.session_state.keep_admin_open:
    st.session_state.keep_admin_open = False
    show_admin_modal()

st.markdown("---")

# ==========================================
# 9. WEEKLY AVAILABILITY MATRIX (COMPACT)
# ==========================================

cols = st.columns(len(WEEK_DATES))
for i, day_date in enumerate(WEEK_DATES):
    with cols[i]:
        with st.container(border=True):
            is_today = day_date == today
            pin_icon = " 📍" if is_today else ""
            is_weekend = day_date.weekday() >= 5
            day_prefix = f"{THEME['weekend']} " if is_weekend else ""

            if is_today:
                st.markdown(
                    f"\n"
                    f"### {day_prefix}{day_date.strftime('%a')}{pin_icon}\n"
                    f"{day_date.strftime('%b %d')} (Today)",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"### {day_prefix}{day_date.strftime('%a')}\n"
                    f"{day_date.strftime('%b %d')}",
                    unsafe_allow_html=True,
                )

            for slot in BUSINESS_HOURS:
                slot_str = slot.strftime("%I:%M %p")
                booking = get_booking_at_slot(bookings, day_date, slot)
                is_past_slot = (day_date < today) or (
                    day_date == today and slot <= current_time_obj
                )
                is_blocked_date = day_date in BLOCKED_DATES
                is_blocked_hour = slot in BLOCKED_HOURS

                if booking:
                    label = (
                        f"{THEME['locked']} {booking['Name'][:8]}"
                        if is_admin
                        else f"{THEME['locked']} Reserved"
                    )
                    st.button(
                        label,
                        key=f"taken_{day_date}{slot}",
                        disabled=True,
                        use_container_width=True,
                    )
                elif is_blocked_date:
                    st.button(
                        f"🏖️ {BLOCKED_DATES[day_date][:10]}",
                        key=f"hol{day_date}{slot}",
                        disabled=True,
                        use_container_width=True,
                    )
                elif is_blocked_hour:
                    st.button(
                        f"☕ {BLOCKED_HOURS[slot][:10]}",
                        key=f"brk{day_date}{slot}",
                        disabled=True,
                        use_container_width=True,
                    )
                elif is_past_slot:
                    st.button(
                        f"🚫 {slot_str}",
                        key=f"past{day_date}{slot}",
                        disabled=True,
                        use_container_width=True,
                    )
                else:
                    if st.button(
                        f"{THEME['free']} {slot_str}",
                        key=f"free{day_date}_{slot}",
                        use_container_width=True,
                        type=THEME["btn"],
                    ):
                        reset_booking_workflow()
                        st.session_state.preselected_date = day_date
                        st.session_state.preselected_time = slot
                        record_user_activity()
                        st.rerun()
