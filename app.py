# =============================================================
# AI Phishing Awareness Training Tool
# -------------------------------------------------------------
# Project   : Study 3 - AI Tutor-Based Phishing Awareness
# Purpose   : Bilingual (Arabic/English) web platform for
#             phishing awareness training and assessment
#             designed for Saudi healthcare employees.
# Tech Stack: Python 3.9, Streamlit, Groq API (LLaMA 3.3-70b)
# AI Model  : llama-3.3-70b-versatile via Groq Cloud API
# Note      : Planned migration to Claude (Anthropic) API
#             for production deployment.
# -------------------------------------------------------------
# App Flow:
#   HOME -> LEARNING (6 AI-generated phishing examples)
#        -> COMPLETE -> ASSESSMENT (10 questions)
#        -> RESULTS -> PERFORMANCE REPORT
# =============================================================

# == Standard library imports ==================================
import streamlit as st   # Web UI framework - renders all pages
import json               # Parses JSON from AI API responses
import requests           # HTTP client for Groq API calls
import os                 # Reads GROQ_API_KEY environment variable
import re                 # Regex for text cleaning/validation
import html as html_lib   # HTML-escapes user-facing content (security)
import random             # Shuffles scenario order to avoid repetition

# == Streamlit page config =====================================
# Configures the browser tab, layout, and sidebar visibility
st.set_page_config(
    page_title="AI Phishing Awareness",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# == Session state initialisation ==============================
# Streamlit reruns the full script on every user interaction.
# st.session_state acts as persistent storage between reruns.
# These keys are used throughout the app:
#   language      : "English" or "Arabic" (controls UI direction)
#   page          : current page ("home","learning","assessment",etc.)
#   role          : user-selected job role (e.g. "Clinical")
#   example_index : which learning example is currently shown (0-5)
#   emails        : cache of AI-generated emails {index: email_dict}
for k, v in [("language","English"),("page","home"),("role",""),
              ("example_index",0),("emails",{}),("difficulty","medium"),
              ("user_name",""),("user_email",""),("ai_provider","groq")]:
    if k not in st.session_state:
        st.session_state[k] = v

# == Query params navigation handler ============================
_nav = st.query_params.get("nav", "")
if _nav in ("login", "register"):
    st.session_state["login_mode"] = _nav
    st.session_state["page"] = "login"
    # Preserve language from URL if passed
    _lang = st.query_params.get("lang", "")
    if _lang in ("Arabic", "English"):
        st.session_state["language"] = _lang
    st.query_params.clear()   # clear URL — no rerun needed

# == Global helper functions ===================================

def set_language(lang):
    st.session_state["language"] = lang
    st.session_state["lang_explicitly_chosen"] = True

def t(en, ar):
    # Translation helper used everywhere in the UI.
    # Returns Arabic string if Arabic mode is active, else English.
    # Example: t("Start", "ابدأ") returns "ابدأ" in Arabic mode.
    return ar if st.session_state["language"] == "Arabic" else en

def go_to_learning(role):
    # Navigates to the Learning Phase.
    # Resets example index and clears cached emails so fresh
    # AI content is generated for each new training session.
    st.session_state["role"]          = role
    st.session_state["page"]          = "learning"
    st.session_state["example_index"] = 0
    st.session_state["emails"]        = {}

# ── Text cleaners ──────────────────────────────────────────
def clean_foreign_only(text):
    if not text: return text
    text = re.sub(r'<[^>]+>', '', text)
    # Chinese, Japanese, Korean
    text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\uac00-\ud7af\u1100-\u11ff]', '', text)
    # Cyrillic (Russian etc.)
    text = re.sub(r'[\u0400-\u04ff]', '', text)
    # Extended Latin (French accents etc.)
    text = re.sub(r'[\u0100-\u017f]', '', text)
    # Vietnamese
    text = re.sub(r'[\u1ea0-\u1ef9]', '', text)
    # Devanagari (Hindi/Sanskrit like मर)
    text = re.sub(r'[\u0900-\u097f]', '', text)
    # Thai
    text = re.sub(r'[\u0e00-\u0e7f]', '', text)
    # Georgian, Armenian, Hebrew
    text = re.sub(r'[\u10a0-\u10ff\u0530-\u058f\u05d0-\u05ff]', '', text)
    # Control characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'  +', ' ', text).strip()
    return text

# Allowed Latin patterns inside Arabic text (URLs, emails, file extensions, numbers)
_ALLOWED_LATIN_RE = re.compile(
    r'^(https?://[^\s]+|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}|\.(?:pdf|xlsx|docx|txt|csv|zip|exe)|[0-9]+)$',
    re.IGNORECASE
)

def remove_foreign_latin_words(text):
    """Remove standalone Latin words (English, Turkish, Vietnamese…) from Arabic text,
    while preserving URLs, emails, file extensions and numbers."""
    if not text: return text
    arabic_chars = len(re.findall(r'[\u0600-\u06ff]', text))
    total_chars  = len(re.sub(r'\s', '', text))
    if total_chars == 0 or arabic_chars / total_chars < 0.25:
        return text  # not Arabic-dominant – leave untouched
    def keep_token(tok):
        if _ALLOWED_LATIN_RE.match(tok): return tok          # URL / email / number
        if re.search(r'[\u0600-\u06ff]', tok): return tok    # contains Arabic
        if re.match(r'^[\u060c\u061b\u061f،؛؟!.,;:\-\u2013\u2014()\[\]{}\'"]+$', tok): return tok  # punctuation
        if re.match(r'^[a-zA-Z\u00c0-\u024f]+$', tok): return ''   # any Latin word → remove (including single letters)
        return tok
    tokens  = re.split(r'(\s+)', text)
    cleaned = ''.join(keep_token(t) for t in tokens)
    # Remove mixed Latin-Arabic tokens like "used-في" or "HRالـ"
    cleaned = re.sub(r'[a-zA-Z]{1,}[-_](?=[\u0600-\u06ff])', '', cleaned)   # Latin-عربي
    cleaned = re.sub(r'(?<=[\u0600-\u06ff])[-_]?[a-zA-Z]{1,}', '', cleaned) # عربي-Latin
    cleaned = re.sub(r'[a-zA-Z]{1,}(?=[\u0600-\u06ff])', '', cleaned)        # HRالـ (no sep)
    cleaned = re.sub(r'  +', ' ', cleaned).strip()
    cleaned = re.sub(r'\s([،؛،,.;:])', r'\1', cleaned)
    return cleaned

def clean_email_field(addr):
    if not addr: return addr
    addr = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0400-\u04ff\u0100-\u017f]', '', addr)
    addr = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', addr)
    return addr.strip()

def extract_to_email(to_val):
    """Always return clean email only — no Arabic text mixed in."""
    if not to_val: return 'employee@hospital.org'
    # Extract just the email address part
    m = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', to_val)
    return m.group(0) if m else 'employee@hospital.org'

def fix_json_newlines(s):
    # Fixes a common LLM output issue: real newlines inside JSON strings.
    # The AI sometimes puts actual line breaks inside string values,
    # which breaks json.loads(). This function escapes them to \n.
    # Works by tracking whether we are inside a quoted string or not.
    result, in_string, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i-1] != '\\'):
            in_string = not in_string
        if in_string and c == '\n':   result.append('\\n')   # escape real newline
        elif in_string and c == '\r': result.append('\\r')   # escape carriage return
        elif in_string and c == '\t': result.append('\\t')   # escape tab
        else:                         result.append(c)
        i += 1
    return ''.join(result)

# =============================================================
# ROLE CONTEXT MAP
# -------------------------------------------------------------
# Maps user-selected job roles to:
#   [0] Human-readable role description (used in AI prompt)
#   [1] Work context keywords (makes AI output role-relevant)
#   [2] Internal role type key: "clinical", "admin", or "it"
#       Used to pick the correct scenario description and
#       recipient email pool.
# Supports both Arabic and English role names.
# =============================================================
ROLE_MAP = {
    "سريري": (
        "ممرض أو طبيب يعمل في مستشفى",
        "السجلات الطبية وجداول العمل السريرية والأنظمة الطبية وبيانات المرضى",
        "clinical"
    ),
    "إداري / إدارة": (
        "موظف إداري في مستشفى (سكرتارية طبية، استقبال، إدارة ملفات المرضى، التأمين الصحي، الفوترة الطبية)",
        "ملفات المرضى وحجز المواعيد والتأمين الصحي والفوترة الطبية وسكرتارية الأطباء وإدارة المستشفى والمشتريات الطبية",
        "admin"
    ),
    "تقنية المعلومات / المعلوماتية": (
        "متخصص تقنية معلومات في مستشفى",
        "الشبكة والخوادم وتحديثات البرامج والدعم التقني والأمن السيبراني",
        "it"
    ),
    "Clinical": (
        "a nurse or doctor in a hospital",
        "patient records, EMR systems, clinical schedules, medical data",
        "clinical"
    ),
    "Admin / Management": (
        "a healthcare administrative staff (medical secretary, receptionist, patient records manager, insurance coordinator, billing specialist)",
        "patient files, appointment scheduling, medical insurance, hospital billing, doctor's secretary, hospital management, medical procurement",
        "admin"
    ),
    "IT / Informatics": (
        "an IT specialist in a hospital",
        "VPN, network, servers, software updates, IT helpdesk, security systems",
        "it"
    ),
}
# ══════════════════════════════════════════════════════════
#  RECIPIENT NAME GENERATOR
# ══════════════════════════════════════════════════════════
# AR_NAMES removed — always use Latin email addresses
EN_NAMES = {
    "clinical": [
        "dr.sarah.almutairi@hospital.org",
        "dr.ahmed.alotaibi@hospital.org",
        "n.noura.alshamri@hospital.org",
        "dr.fahad.aldosari@hospital.org",
        "n.mona.alharbi@hospital.org",
        "dr.khalid.alanazi@hospital.org",
    ],
    "admin": [
        "m.reem.alsabiei@hospital.org",
        "m.abdullah.alqahtani@hospital.org",
        "m.hind.alrashidi@hospital.org",
        "m.sultan.alghamdi@hospital.org",
        "m.dalal.alzahrani@hospital.org",
        "m.omar.albaqami@hospital.org",
    ],
    "it": [
        "t.mohammed.alshahri@hospital.org",
        "t.rania.almalki@hospital.org",
        "t.yusuf.aljuhani@hospital.org",
        "t.lama.alumari@hospital.org",
        "t.bandar.althubaiti@hospital.org",
        "t.nadia.alsalmi@hospital.org",
    ],
}

def get_recipient(role, index, language):
    """Return a realistic Latin email recipient — always Latin regardless of language."""
    role_info = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    _, _, role_type = role_info
    pool = EN_NAMES.get(role_type, EN_NAMES["clinical"])
    return pool[index % len(pool)]



# ══════════════════════════════════════════════════════════
#  PHISHING SCENARIOS — role-aware descriptions
# ══════════════════════════════════════════════════════════
def get_role_scenario_desc(scenario_key, role_type, is_ar):
    """Return role-specific scenario description."""
    descs = {
        "link": {
            "clinical": (
                "Generate an email targeting a clinical staff member (nurse/doctor). "
                "It contains a suspicious link asking them to verify their hospital EMR system login. "
                "The link MUST appear in body as plain text http:// URL pointing to a fake domain.",
                "أنشئ رسالة تستهدف موظفاً سريرياً (ممرض/طبيب). تحتوي على رابط مشبوه "
                "يطلب منه التحقق من بيانات دخوله لنظام السجلات الطبية. "
                "يجب أن يظهر الرابط في النص كنص عادي http:// يشير لنطاق مزيف."
            ),
            "admin": (
                "Generate an email targeting an admin/HR manager. "
                "It contains a suspicious link asking them to update payroll system credentials. "
                "The link MUST appear in body as plain text http:// URL pointing to a fake domain.",
                "أنشئ رسالة تستهدف مديراً إدارياً. تحتوي على رابط مشبوه "
                "يطلب منه تحديث بيانات دخول نظام الرواتب. "
                "يجب أن يظهر الرابط في النص كنص عادي http:// يشير لنطاق مزيف."
            ),
            "it": (
                "Generate an email targeting an IT specialist. "
                "It contains a suspicious link claiming a critical server security update is required. "
                "The link MUST appear in body as plain text http:// URL pointing to a fake domain.",
                "أنشئ رسالة تستهدف متخصص تقنية معلومات. تحتوي على رابط مشبوه "
                "يدّعي وجوب تثبيت تحديث أمني عاجل للخادم. "
                "يجب أن يظهر الرابط في النص كنص عادي http:// يشير لنطاق مزيف."
            ),
        },
        "pdf": {
            "clinical": (
                "Generate an email targeting a nurse/doctor with a PDF attachment "
                "(e.g. patient_data_update.pdf or clinical_protocol.pdf). "
                "Body urgently asks to open it. NO link.",
                "أنشئ رسالة تستهدف ممرضاً أو طبيباً تحتوي على مرفق PDF "
                "(مثل: تحديث_بيانات_المريض.pdf أو بروتوكول_سريري.pdf). "
                "النص يطلب فتحه بشكل عاجل. لا رابط."
            ),
            "admin": (
                "Generate an email targeting an admin manager with a PDF attachment "
                "(e.g. payroll_report_Q1.pdf or hr_policy_update.pdf). "
                "Body urgently asks to open it. NO link.",
                "أنشئ رسالة تستهدف مديراً إدارياً تحتوي على مرفق PDF "
                "(مثل: تقرير_الرواتب_الربع_الأول.pdf أو تحديث_سياسات_الموارد_البشرية.pdf). "
                "النص يطلب فتحه بشكل عاجل. لا رابط."
            ),
            "it": (
                "Generate an email targeting an IT specialist with a PDF attachment "
                "(e.g. network_security_audit.pdf or server_maintenance_report.pdf). "
                "Body urgently asks to open it. NO link.",
                "أنشئ رسالة تستهدف متخصص تقنية معلومات تحتوي على مرفق PDF "
                "(مثل: تقرير_تدقيق_الشبكة.pdf أو تقرير_صيانة_الخادم.pdf). "
                "النص يطلب فتحه بشكل عاجل. لا رابط."
            ),
        },
        "xlsx": {
            "clinical": (
                "Generate an email targeting clinical staff with an Excel attachment "
                "(e.g. staff_schedule_update.xlsx or patient_roster.xlsx). "
                "Body asks to open and fill it. NO suspicious link.",
                "أنشئ رسالة تستهدف الكادر السريري تحتوي على مرفق Excel "
                "(مثل: جدول_العمل_المحدث.xlsx أو قائمة_المرضى.xlsx). "
                "النص يطلب فتحه وتعبئته. لا رابط مشبوه."
            ),
            "admin": (
                "Generate an email targeting an admin manager with an Excel attachment "
                "(e.g. employee_data_form.xlsx or budget_approval.xlsx). "
                "Body asks to open and fill it. NO suspicious link.",
                "أنشئ رسالة تستهدف مديراً إدارياً تحتوي على مرفق Excel "
                "(مثل: نموذج_بيانات_الموظفين.xlsx أو اعتماد_الميزانية.xlsx). "
                "النص يطلب فتحه وتعبئته. لا رابط مشبوه."
            ),
            "it": (
                "Generate an email targeting an IT specialist with an Excel attachment "
                "(e.g. asset_inventory_update.xlsx or system_access_log.xlsx). "
                "Body asks to open and fill it. NO suspicious link.",
                "أنشئ رسالة تستهدف متخصص تقنية معلومات تحتوي على مرفق Excel "
                "(مثل: تحديث_جرد_الأصول.xlsx أو سجل_الوصول_للنظام.xlsx). "
                "النص يطلب فتحه وتعبئته. لا رابط مشبوه."
            ),
        },
        "docx": {
            "clinical": (
                "Generate an email targeting clinical staff with a Word doc attachment "
                "(e.g. clinical_guidelines_2024.docx). Body asks to Enable Macros to view content. NO link.",
                "أنشئ رسالة تستهدف الكادر السريري تحتوي على مرفق Word "
                "(مثل: إرشادات_سريرية_2024.docx). النص يطلب تفعيل الماكرو لعرض المحتوى. لا رابط."
            ),
            "admin": (
                "Generate an email targeting admin staff with a Word doc attachment "
                "(e.g. hr_policy_update_2024.docx). Body asks to Enable Macros to view content. NO link.",
                "أنشئ رسالة تستهدف الكادر الإداري تحتوي على مرفق Word "
                "(مثل: تحديث_سياسات_الموارد_البشرية_2024.docx). النص يطلب تفعيل الماكرو. لا رابط."
            ),
            "it": (
                "Generate an email targeting IT staff with a Word doc attachment "
                "(e.g. it_security_policy_2024.docx). Body asks to Enable Macros to view content. NO link.",
                "أنشئ رسالة تستهدف كادر تقنية المعلومات تحتوي على مرفق Word "
                "(مثل: سياسة_أمن_المعلومات_2024.docx). النص يطلب تفعيل الماكرو. لا رابط."
            ),
        },
        "hr_link": {
            "clinical": (
                "Generate an email that looks like an official hospital HR announcement about "
                "mandatory clinical compliance training enrollment. "
                "Contains suspicious link (http://...) — 'Click here to enroll'. Link MUST appear in body.",
                "أنشئ رسالة تبدو كإعلان رسمي من الموارد البشرية عن تسجيل إلزامي "
                "في تدريب الامتثال السريري. تحتوي على رابط مشبوه (http://...) — 'انقر هنا للتسجيل'. "
                "يجب أن يظهر الرابط في النص."
            ),
            "admin": (
                "Generate an email that looks like an official HR announcement about "
                "new employee benefits enrollment deadline. "
                "Contains suspicious link (http://...) — 'Click here to enroll'. Link MUST appear in body.",
                "أنشئ رسالة تبدو كإعلان رسمي من الموارد البشرية عن موعد نهائي "
                "للتسجيل في المزايا الجديدة للموظفين. تحتوي على رابط مشبوه (http://...) — 'انقر هنا للتسجيل'. "
                "يجب أن يظهر الرابط في النص."
            ),
            "it": (
                "Generate an email that looks like an official IT security policy update "
                "requiring immediate acknowledgment via a link. "
                "Contains suspicious link (http://...) — 'Click here to confirm'. Link MUST appear in body.",
                "أنشئ رسالة تبدو كتحديث رسمي لسياسة أمن المعلومات يتطلب تأكيداً فورياً عبر رابط. "
                "تحتوي على رابط مشبوه (http://...) — 'انقر هنا للتأكيد'. "
                "يجب أن يظهر الرابط في النص."
            ),
        },
        "exec": {
            "clinical": (
                "Generate an email impersonating the hospital medical director urgently requesting "
                "a clinical staff member to share patient data or system access credentials immediately. "
                "Pure social engineering — no link needed.",
                "أنشئ رسالة تنتحل هوية المدير الطبي للمستشفى وتطلب بشكل عاجل "
                "من أحد الكادر السريري مشاركة بيانات المرضى أو بيانات الوصول للأنظمة فوراً. "
                "هندسة اجتماعية بحتة — لا رابط."
            ),
            "admin": (
                "Generate an email impersonating the CEO/director urgently requesting "
                "an admin manager to process an urgent financial transaction or share payroll data. "
                "Pure social engineering — no link needed.",
                "أنشئ رسالة تنتحل هوية المدير التنفيذي وتطلب بشكل عاجل "
                "من المدير الإداري معالجة معاملة مالية عاجلة أو مشاركة بيانات الرواتب. "
                "هندسة اجتماعية بحتة — لا رابط."
            ),
            "it": (
                "Generate an email impersonating the CIO/IT director urgently requesting "
                "an IT specialist to provide server access credentials or disable security settings. "
                "Pure social engineering — no link needed.",
                "أنشئ رسالة تنتحل هوية مدير تقنية المعلومات وتطلب بشكل عاجل "
                "من متخصص تقنية المعلومات تقديم بيانات الوصول للخوادم أو تعطيل إعدادات الأمان. "
                "هندسة اجتماعية بحتة — لا رابط."
            ),
        },
    }
    en_desc, ar_desc = descs[scenario_key].get(role_type, descs[scenario_key]["clinical"])
    return ar_desc if is_ar else en_desc

# =============================================================
# LEARNING PHASE SCENARIOS (6 types)
# -------------------------------------------------------------
# Defines the 6 distinct phishing scenario types used in the
# Learning Phase. Each scenario has:
#   key            : internal identifier for role-specific desc
#   en_type/ar_type: display name shown in the UI
#   has_attachment : True if scenario involves a file attachment
#   attachment_ext : file extension (.pdf, .xlsx, .docx, "")
#   has_link       : True if scenario involves a suspicious URL
# The scenarios are shuffled randomly each session via
# get_shuffled_scenario_order() to prevent memorisation.
# =============================================================
PHISHING_SCENARIOS = [
    {"key":"link",    "en_type":"Credential Harvesting Link",              "ar_type":"رابط سرقة بيانات الدخول",             "has_attachment":False, "attachment_ext":"", "has_link":True},
    {"key":"pdf",     "en_type":"Malicious PDF Attachment",                "ar_type":"مرفق PDF خبيث",                        "has_attachment":True,  "attachment_ext":".pdf", "has_link":False},
    {"key":"xlsx",    "en_type":"Malicious Excel Attachment",              "ar_type":"مرفق Excel خبيث",                     "has_attachment":True,  "attachment_ext":".xlsx","has_link":False},
    {"key":"docx",    "en_type":"Malicious Word Document - Enable Macros", "ar_type":"مرفق Word مزيف - تفعيل الماكرو",      "has_attachment":True,  "attachment_ext":".docx","has_link":False},
    {"key":"hr_link", "en_type":"Fake HR Announcement with Link",          "ar_type":"إعلان موارد بشرية مزيف برابط",        "has_attachment":False, "attachment_ext":"", "has_link":True},
    {"key":"exec",    "en_type":"Executive Impersonation - Urgent Request","ar_type":"انتحال هوية المدير - طلب عاجل",       "has_attachment":False, "attachment_ext":"", "has_link":False},
]

def get_shuffled_scenario_order():
    # Returns a shuffled list of scenario indices (0-5).
    # Shuffled once per session and stored in session_state,
    # so the order stays consistent within a session but
    # changes between sessions. Prevents users from predicting
    # which scenario type comes next.
    if "scenario_order" not in st.session_state:
        order = list(range(len(PHISHING_SCENARIOS)))
        random.shuffle(order)
        st.session_state["scenario_order"] = order
    return st.session_state["scenario_order"]

# =============================================================
# AI PROMPT BUILDER - LEARNING PHASE
# -------------------------------------------------------------
# Constructs the prompt sent to the Groq API for each phishing
# example. The prompt is role-aware and language-aware:
#   - Uses the shuffled scenario order for variety
#   - Injects role-specific context (clinical/admin/IT)
#   - Sets strict language rules (Arabic OR English only)
#   - Specifies exactly what the JSON response must contain
# Returns a string prompt ready to send to the LLM.
# =============================================================
def build_prompt(role, index, language):
    is_ar      = (language == "Arabic")
    difficulty = st.session_state.get("difficulty", "medium")
    role_info  = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    role_desc, role_ctx, role_type = role_info
    seed = st.session_state.get("cache_version", 13)
    import time
    session_seed = abs(hash(str(seed) + str(index) + str(time.time()))) % 99999

    # ── Role guidance ────────────────────────────────────────────
    role_guidance = {
        "clinical": (
            "Doctors, nurses, pharmacists, lab technicians, radiologists in a Saudi hospital.",
            "EMR systems, patient records, lab results, clinical schedules, pharmacy, medical devices, "
            "surgery lists, vaccination records, ICU data, telemedicine, clinical protocols, MOH alerts, "
            "medical training, infection control, blood bank, patient transfers.",
            "Choose freely: credential theft link, malicious PDF/Excel/Word attachment, executive impersonation, "
            "fake MOH/hospital alert, fake medical system update — MUST be medical/clinical content only."
        ),
        "admin": (
            "Medical secretaries, receptionists, patient records clerks, insurance coordinators, "
            "billing specialists, procurement officers, hospital administrators in Saudi healthcare.",
            "Patient appointments, medical records, health insurance claims, hospital billing, "
            "medical procurement, supplier invoices, staff policies, MOH compliance, accreditation, "
            "patient registration, treatment authorizations, surgery scheduling.",
            "Choose freely: fake appointment/insurance/billing portal link, malicious patient records PDF/Excel, "
            "doctor/CEO impersonation, fake MOH audit, fake supplier invoice — MUST be healthcare admin content only."
        ),
        "it": (
            "IT specialists, informatics officers, system administrators, cybersecurity staff in a Saudi hospital.",
            "Hospital network, VPN, servers, EMR system, cloud backup, SSL certificates, firewall, "
            "software licenses, IT helpdesk, endpoint security, database administration, network monitoring.",
            "Choose freely: VPN/cloud/helpdesk credential theft link, malicious IT policy PDF/Excel, "
            "CIO/CISO impersonation, fake SSL/firewall/license alert — MUST be healthcare IT content only."
        ),
        "other": (
            "A general hospital employee in Saudi Arabia.",
            "Any hospital department — clinical, administrative, or technical.",
            "Choose freely any realistic phishing attack suitable for a Saudi hospital employee."
        ),
    }
    r_desc, r_ctx, r_guidance = role_guidance.get(role_type, role_guidance["other"])

    # ── Difficulty ───────────────────────────────────────────────
    if is_ar:
        diff_rules = {
            "easy": (
                "مستوى مبتدئ — العلامات يجب أن تكون واضحة جداً:\n"
                "- نطاق مزيف واضح تماماً (مثل hosp1tal-updates.xyz أو hospital.totally-fake.net)\n"
                "- خطأين إملائيين واضحين في نص الرسالة\n"
                "- إلحاح مبالغ فيه بحروف كبيرة (تصرف الآن! موعد نهائي اليوم!)\n"
                "- تحية عامة فقط: 'عزيزي الموظف' — ممنوع استخدام الاسم\n"
                "- طلب صريح ومشبوه (شارك كلمة المرور، أدخل بياناتك كاملة)"
            ),
            "medium": (
                "مستوى متوسط — صعوبة معتدلة:\n"
                "- نطاق مشبوه نسبياً لكن ليس واضح الزيف (مثل hospital-hr-portal.net)\n"
                "- أسلوب مهني مع علامة تحذيرية واحدة في الصياغة\n"
                "- إلحاح معتدل ('يرجى الرد بنهاية الأسبوع')\n"
                "- تحية شبه شخصية (اللقب مع اسم خاطئ أحياناً)"
            ),
            "hard": (
                "مستوى متقدم — العلامات خفية جداً:\n"
                "- نطاق يشبه الحقيقي مع تغيير بسيط جداً (مثل hosp1tal.org أو hospital-sa.net)\n"
                "- لغة عربية فصحى مهنية سليمة تماماً، صفر أخطاء\n"
                "- إلحاح خفيف ومهني ('نرجو الاطلاع قبل نهاية يوم العمل')\n"
                "- تحية بالاسم الكامل والمسمى الوظيفي\n"
                "- علامة تحذيرية واحدة فقط وخفية — كل شيء آخر يبدو حقيقياً تماماً"
            ),
        }
    else:
        diff_rules = {
            "easy": (
                "BEGINNER difficulty — signs must be VERY obvious:\n"
                "- Clearly fake domain (e.g. hosp1tal-updates.xyz, hospital.totally-fake.net)\n"
                "- 2 obvious spelling/grammar mistakes in the body\n"
                "- Aggressive ALL-CAPS urgency (ACT NOW! DEADLINE TODAY!)\n"
                "- Generic greeting only: 'Dear Staff' — never use recipient name\n"
                "- Obviously suspicious request (share password, enter full credentials)"
            ),
            "medium": (
                "INTERMEDIATE difficulty — moderate:\n"
                "- Slightly suspicious domain (e.g. hospital-hr-portal.net)\n"
                "- Mostly professional with 1 red flag in wording\n"
                "- Moderate urgency ('Please respond by end of week')\n"
                "- Semi-personal greeting (title with occasionally wrong name)"
            ),
            "hard": (
                "ADVANCED difficulty — signs must be very SUBTLE:\n"
                "- Nearly real domain with tiny change only (e.g. hosp1tal.org or hospital-sa.net)\n"
                "- Perfect professional language, zero errors\n"
                "- Subtle polite urgency ('Kindly review before end of business day')\n"
                "- Full name and job title in greeting\n"
                "- Only ONE subtle red flag — everything else looks completely legitimate"
            ),
        }
    diff_rule = diff_rules.get(difficulty, diff_rules["medium"])

    # ── Language ─────────────────────────────────────────────────
    if is_ar:
        lang_rule = (
            "اللغة: عربية فصحى فقط في كل النصوص (subject/body/indicators/why_risky/learning_tip).\n"
            "استثناء: عناوين البريد الإلكتروني والروابط (http://...) تبقى لاتينية.\n"
            "ممنوع: أي حرف لاتيني داخل النصوص العربية.\n"
            "حقل 'to': البريد الإلكتروني فقط بدون أي نص."
        )
        from_ex  = "اسم المرسل <fake@domain.com>"
        body_ex  = "نص الرسالة بالعربية الفصحى"
        ind_t_ex = "عنوان المؤشر"
        ind_d_ex = "وصف تقني تفصيلي"
    else:
        lang_rule = "Language: English only throughout. No Arabic or foreign characters in text fields."
        from_ex  = "Sender Name <fake@domain.com>"
        body_ex  = "email body in English"
        ind_t_ex = "indicator title"
        ind_d_ex = "detailed technical explanation"

    return f"""You are a cybersecurity expert creating phishing awareness training for Saudi healthcare.

TRAINING EXAMPLE #{index + 1} of 6 | Variety seed: {session_seed}

━━━ TARGET ━━━
Role: {r_desc}
Context: {r_ctx}

━━━ YOUR TASK ━━━
{r_guidance}
Be CREATIVE — choose a different attack type than typical examples.
Each of the 6 examples must be a COMPLETELY DIFFERENT attack type and format.

━━━ DIFFICULTY ━━━
{diff_rule}

━━━ LANGUAGE ━━━
{lang_rule}

━━━ FORMAT RULES ━━━
- body: plain text only, use \\n for line breaks, NO HTML
- "to": email address only, nothing else
- If attack uses a link: put URL in "suspicious_link" AND verbatim in body
- If attack uses attachment: put filename in "attachment" (e.g. file.pdf, data.xlsx)
- If social engineering only: "suspicious_link":"", "attachment":""

━━━ RETURN ONLY VALID JSON ━━━
{{"email_type":"attack type name","from":"{from_ex}","to":"employee@hospital.org","subject":"subject line","attachment":"filename or empty","body":"{body_ex}","suspicious_text":"most suspicious phrase","suspicious_link":"url or empty","indicators":[{{"number":1,"title":"{ind_t_ex}","description":"{ind_d_ex}"}},{{"number":2,"title":"{ind_t_ex}","description":"{ind_d_ex}"}},{{"number":3,"title":"{ind_t_ex}","description":"{ind_d_ex}"}}],"why_risky":"why dangerous for this role","learning_tip":"practical tip for this role"}}"""

# =============================================================
# API COMMUNICATION LAYER
# -------------------------------------------------------------
# These functions handle all communication with the Groq API.
# Groq hosts the LLaMA 3.3-70b model and provides fast inference.
# API key is read from environment variable GROQ_API_KEY.
# (Can be swapped to OpenAI or Anthropic Claude by changing
#  the endpoint URL and response parsing in call_groq().)
# =============================================================
def call_ai(prompt, max_tokens=1600):
    # =============================================================
    # UNIFIED AI CALLER — supports 4 APIs for research comparison
    # Selected via st.session_state["ai_provider"]:
    #   "groq"      → Groq (LLaMA 3.3-70b)   — default / v3 baseline
    #   "openai"    → ChatGPT (GPT-4o)        — most used globally
    #   "anthropic" → Claude (claude-3-5-sonnet) — best writing quality
    #   "gemini"    → Gemini (gemini-1.5-pro) — fastest growing
    # All providers use temperature=0.85 for variety.
    # =============================================================
    provider = st.session_state.get("ai_provider", "groq")

    def get_secret(key):
        try:
            return st.secrets[key]
        except Exception:
            return os.environ.get(key, "")

    # ── Groq (LLaMA 3.3-70b) ──────────────────────────────────
    if provider == "groq":
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {get_secret('GROQ_API_KEY')}"
            },
            json={
                "model":       "llama-3.1-8b-instant",
                "max_tokens":  max_tokens,
                "temperature": 0.85,
                "messages":    [{"role": "user", "content": prompt}]
            },
            timeout=45
        )
        data = resp.json()
        # normalise to {"choices":[{"message":{"content":...}}]}
        return data

    # ── OpenAI (GPT-4o) ────────────────────────────────────────
    elif provider == "openai":
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {get_secret('OPENAI_API_KEY')}"
            },
            json={
                "model":       "gpt-4o",
                "max_tokens":  max_tokens,
                "temperature": 0.85,
                "messages":    [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        return resp.json()

    # ── Anthropic (Claude 3.5 Sonnet) ──────────────────────────
    elif provider == "anthropic":
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         get_secret("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01"
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        raw = resp.json()
        # Convert Anthropic format → OpenAI-compatible format
        if "content" in raw and len(raw["content"]) > 0:
            text = raw["content"][0].get("text", "")
            return {"choices": [{"message": {"content": text}}]}
        return {"error": raw}

    # ── Google Gemini (gemini-1.5-pro) ─────────────────────────
    elif provider == "gemini":
        api_key = get_secret("GEMINI_API_KEY")
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature":     0.85
                }
            },
            timeout=60
        )
        raw = resp.json()
        # Convert Gemini format → OpenAI-compatible format
        try:
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            return {"choices": [{"message": {"content": text}}]}
        except (KeyError, IndexError):
            return {"error": raw}

    else:
        return {"error": f"Unknown provider: {provider}"}

# Keep old name as alias for backwards compatibility
def call_groq(prompt, max_tokens=1600):
    return call_ai(prompt, max_tokens)

def parse_json_response(raw):
    # Step 1: strip markdown fences
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # Step 2: strip control chars
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    # Step 3: fix real newlines inside strings
    raw = fix_json_newlines(raw)
    # Step 4: try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Step 5: aggressive fix — extract first {...} block and sanitize
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        candidate = match.group(0)
        # Replace unescaped single quotes inside string values with unicode equiv
        candidate = re.sub(r"(?<=\w)'(?=\w)", "\u2019", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("Cannot parse JSON", raw, 0)

def clean_result(result, is_arabic):
    for f in ["body","suspicious_text","why_risky","learning_tip","subject","email_type"]:
        if result.get(f):
            result[f] = clean_foreign_only(result[f])
            if is_arabic:
                result[f] = remove_foreign_latin_words(result[f])
    for ind in result.get("indicators",[]):
        for k in ["title","description"]:
            if ind.get(k):
                ind[k] = clean_foreign_only(ind[k])
                if is_arabic:
                    ind[k] = remove_foreign_latin_words(ind[k])
    result["from"] = clean_email_field(result.get("from",""))
    # ALWAYS extract clean email only for "to" field
    result["to"] = extract_to_email(result.get("to",""))
    if result.get("suspicious_link"):
        sl = result["suspicious_link"]
        sl = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',sl).strip()
        # Remove any Arabic text that might have leaked into the link
        sl = re.sub(r'[\u0600-\u06ff\s]','',sl)
        result["suspicious_link"] = sl
    return result

def generate_email(role, index, language):
    try:
        data = call_groq(build_prompt(role, index, language))
        if "error" in data:
            return {"error": data['error'].get('message', str(data['error']))}
        if "choices" not in data:
            return {"error": f"Unexpected API response: {str(data)[:200]}"}
        raw    = data["choices"][0]["message"]["content"].strip()
        result = parse_json_response(raw)
        result = clean_result(result, language=="Arabic")
        result["to"] = get_recipient(role, index, language)

        # If AI generated a link, make sure it appears in the body too
        if result.get("suspicious_link","").strip():
            if result["suspicious_link"] not in result.get("body",""):
                result["body"] = result.get("body","") + f'\n{result["suspicious_link"]}'

        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": str(e)}

# =============================================================
# EMAIL WINDOW RENDERER
# -------------------------------------------------------------
# Shared renderer used by BOTH the Learning Phase and Assessment.
# Renders an HTML email client window (dark theme, macOS style).
# Parameters:
#   email       : dict with keys: from, to, subject, body,
#                 attachment, suspicious_text, suspicious_link
#   is_arabic   : bool - controls RTL/LTR layout direction
#   show_badges : True in Learning Phase only - adds numbered
#                 red circles on suspicious elements to guide
#                 the learner's attention.
# Layout direction:
#   Arabic  : direction=rtl, text-align=right
#   English : direction=ltr, text-align=left
#   "To" field: always LTR (email addresses are Latin)
# =============================================================
def render_email_window(email, is_arabic, show_badges=False):
    bd = 'rtl' if is_arabic else 'ltr'
    ta = 'right' if is_arabic else 'left'
    email_font = 'Tahoma,Arial,sans-serif' if is_arabic else "'Courier New',monospace"

    body_raw        = re.sub(r'<[^>]+>','', email.get("body",""))
    suspicious_text = re.sub(r'<[^>]+>','', email.get("suspicious_text",""))
    suspicious_link = re.sub(r'<[^>]+>','', email.get("suspicious_link",""))
    has_attachment  = bool(email.get("attachment","").strip())

    body_html   = html_lib.escape(body_raw)
    badge_count = [4 if has_attachment else 3]

    def make_badge(n, color="#DC2626"):
        return (f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'width:20px;height:20px;border-radius:50%;background:{color};color:white;'
                f'font-size:.7rem;font-weight:800;margin:0 3px;vertical-align:middle;">{n}</span>')

    def next_badge():
        b = badge_count[0]; badge_count[0] += 1; return b

    if show_badges:
        if suspicious_text:
            safe_s = html_lib.escape(suspicious_text)
            if safe_s in body_html:
                b = next_badge()
                body_html = body_html.replace(safe_s,
                    f'<span style="border:2px solid rgba(239,68,68,.6);border-radius:8px;'
                    f'padding:.2rem .5rem;background:rgba(239,68,68,.08);color:#FCA5A5;">'
                    f'{make_badge(b)}{safe_s}</span>', 1)

        if suspicious_link:
            safe_l = html_lib.escape(suspicious_link)
            if safe_l in body_html:
                b = next_badge()
                body_html = body_html.replace(safe_l,
                    f'<span style="border:2px solid rgba(239,68,68,.6);border-radius:6px;'
                    f'padding:.2rem .5rem;background:rgba(239,68,68,.08);color:#60A5FA;'
                    f'text-decoration:underline;">{make_badge(b)}{safe_l}</span>', 1)
            else:
                # Always show the link even if not found in body
                b = next_badge()
                body_html += (f'<br><br><span style="border:2px solid rgba(239,68,68,.6);'
                              f'border-radius:6px;padding:.2rem .5rem;background:rgba(239,68,68,.08);'
                              f'color:#60A5FA;text-decoration:underline;">'
                              f'{make_badge(b)}{html_lib.escape(suspicious_link)}</span>')

    body_html = body_html.replace("\n","<br>")

    from_val = html_lib.escape(email.get("from",""))
    # "to" is already clean email only from extract_to_email
    to_val   = html_lib.escape(email.get("to","employee@hospital.org"))
    subj_val = html_lib.escape(email.get("subject",""))
    att_val  = html_lib.escape(email.get("attachment",""))

    fl = t("From:","من:")
    tl = t("To:","إلى:")
    sl = t("Subject:","الموضوع:")

    b_from = make_badge(1) if show_badges else ""
    b_subj = make_badge(2) if show_badges else ""
    b_att  = make_badge(3) if show_badges else ""

    att_html = ""
    if att_val:
        att_html = (f'<div style="display:inline-flex;align-items:center;gap:.5rem;'
                    f'border:1px solid rgba(37,99,235,.5);border-radius:8px;padding:.4rem .8rem;'
                    f'background:rgba(37,99,235,.15);color:#93C5FD;font-size:.88rem;margin:.4rem 0;">'
                    f'{b_att}📎 {att_val}</div>')

    st.markdown(f"""
<div style="background:#0F172A;border:1px solid rgba(37,99,235,.5);
            border-radius:16px 16px 0 0;overflow:hidden;">
  <div style="background:#1E293B;padding:.6rem 1rem;display:flex;gap:8px;align-items:center;">
    <div style="width:12px;height:12px;border-radius:50%;background:#FF5F57;"></div>
    <div style="width:12px;height:12px;border-radius:50%;background:#FFBD2E;"></div>
    <div style="width:12px;height:12px;border-radius:50%;background:#28C840;"></div>
  </div>
  <div style="padding:1rem 1.6rem .5rem;font-size:.92rem;color:#CBD5E1;
              direction:{bd};text-align:{ta};
              font-family:{email_font};">
    <table style="width:100%;border-collapse:collapse;direction:{bd};">
      <tr style="vertical-align:top;">
        <td style="color:#64748B;font-weight:700;padding:0 8px 6px 0;white-space:nowrap;width:70px;">{fl}</td>
        <td style="color:#E2E8F0;padding:0 0 6px 0;word-break:break-all;">{b_from}{from_val}</td>
      </tr>
      <tr style="vertical-align:middle;">
        <td style="color:#64748B;font-weight:700;padding:0 8px 6px 0;white-space:nowrap;">{tl}</td>
        <td style="color:#93C5FD;padding:0 0 6px 0;direction:ltr;text-align:{('right' if bd=='rtl' else 'left')};overflow:hidden;text-overflow:ellipsis;">{to_val}</td>
      </tr>
      <tr style="vertical-align:top;">
        <td style="color:#64748B;font-weight:700;padding:0 8px 6px 0;white-space:nowrap;">{sl}</td>
        <td style="color:#E2E8F0;padding:0 0 6px 0;word-break:break-word;">{b_subj}{subj_val}</td>
      </tr>
    </table>
    {att_html}
  </div>
</div>
<div style="background:#0F172A;border:1px solid rgba(37,99,235,.5);border-top:none;
            border-radius:0 0 16px 16px;padding:.8rem 1.6rem 1.4rem;
            font-family:{email_font};
            font-size:.92rem;color:#CBD5E1;
            line-height:2;direction:{bd};text-align:{ta};
            box-shadow:0 20px 60px rgba(0,0,0,.5);">
  {body_html}
</div>""", unsafe_allow_html=True)


# =============================================================
# PAGE 1: HOME
# -------------------------------------------------------------
# Entry point of the application. Shows:
#   - Hero section with app title and shield icon
#   - 4 feature cards explaining the tool
#   - Language selector (English / Arabic)
#   - Role selector (Clinical / Admin / IT / Other)
#   - "Start Personalised Training" button
# On start: clears old session data, shuffles scenario order,
# and navigates to the Learning Phase.
# =============================================================
def page_home():
    is_arabic      = st.session_state["language"] == "Arabic"
    dir_attr       = 'rtl' if is_arabic else 'ltr'
    text_align     = 'right' if is_arabic else 'left'
    hero_grid_cols = '1fr 230px' if is_arabic else '230px 1fr'

    st.markdown(f"""<style>
#MainMenu,header,footer{{visibility:hidden;}}
.stApp{{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}}
.block-container{{max-width:1160px;padding-top:2rem;}}
.hero-card{{border:1px solid rgba(37,99,235,.55);border-radius:24px;padding:2.2rem 2.4rem;background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));box-shadow:0 24px 70px rgba(0,0,0,.42);margin-bottom:1.3rem;}}
.hero-grid{{display:grid;grid-template-columns:{hero_grid_cols};gap:2rem;align-items:center;}}
.shield-orb{{width:180px;height:180px;border-radius:50%;margin:auto;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle,rgba(37,99,235,.45),rgba(2,6,23,.15) 65%);border:1px solid rgba(56,189,248,.35);box-shadow:0 0 45px rgba(37,99,235,.36);position:relative;overflow:visible;}}
.shield-orb::before{{content:"";position:absolute;width:215px;height:215px;border-radius:50%;border:1px dashed rgba(56,189,248,.34);}}
.hero-content{{text-align:center;}}
.hero-title{{font-size:3.4rem;font-weight:900;color:#F8FAFC;margin-bottom:.7rem;}}
.hero-tagline{{font-size:1.45rem;font-weight:800;color:#1EA7FF;margin-bottom:.9rem;}}
.hero-desc{{font-size:1rem;color:#DCEBFF;line-height:1.7;max-width:620px;margin:0 auto;}}
.features-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.4rem;direction:{dir_attr};}}
.feature-card{{border:1px solid rgba(37,99,235,.55);background:rgba(2,6,23,.60);border-radius:18px;padding:1.5rem 1rem;min-height:175px;text-align:center;cursor:pointer;transition:.25s ease;}}
.feature-card:hover{{transform:translateY(-6px);border-color:#1EA7FF;box-shadow:0 0 28px rgba(30,167,255,.22);}}
.feature-icon{{height:60px;margin-bottom:.8rem;display:flex;justify-content:center;align-items:center;}}
.feature-title{{font-size:1rem;font-weight:800;color:white;margin-bottom:.5rem;}}
.feature-text{{color:#BFD7F5;font-size:.9rem;line-height:1.55;}}
.form-section{{direction:{dir_attr};text-align:{text_align};margin-bottom:.5rem;}}
.form-title{{font-size:1.35rem;font-weight:900;color:white;margin-bottom:1rem;}}
.section-label{{font-weight:800;color:white;margin-bottom:.5rem;direction:{dir_attr};text-align:{text_align};}}
[data-testid="column"]{{direction:{dir_attr};}}
.stButton>button{{width:100%;min-height:48px;background:rgba(15,23,42,.78);color:#EAF4FF;border:1px solid rgba(37,99,235,.55);border-radius:12px;font-weight:800;direction:{dir_attr};}}
.stButton>button:hover,.stButton>button:focus{{background:linear-gradient(90deg,#0B4FA8,#0284C7);color:white;border-color:#1EA7FF !important;}}
.start-btn>button{{min-height:56px !important;background:rgba(15,23,42,.88) !important;color:white !important;border:1px solid rgba(37,99,235,.65) !important;font-size:1.05rem !important;font-weight:900 !important;border-radius:14px !important;}}
.start-btn>button:hover{{background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;border-color:#1EA7FF !important;}}
.stSelectbox>div>div,.stTextInput>div>div>input{{background-color:rgba(15,23,42,.88) !important;color:white !important;border:1px solid rgba(37,99,235,.55) !important;border-radius:12px !important;min-height:48px;direction:{dir_attr};text-align:{text_align};}}
div[data-baseweb="select"] span{{color:white !important;}}
div[data-baseweb="popover"] ul li{{text-align:{text_align} !important;direction:{dir_attr} !important;}}
.footer-bar{{margin-top:2rem;padding:1.5rem 0;border-top:1px solid rgba(37,99,235,.35);display:flex;justify-content:space-between;align-items:center;color:#7DD3FC;font-size:.95rem;direction:{dir_attr};}}
.footer-side{{display:flex;align-items:center;gap:.8rem;}}
.diff-btn>button{{width:100% !important;min-height:52px !important;border-radius:14px !important;font-weight:800 !important;font-size:.95rem !important;transition:.2s ease !important;background:rgba(2,6,23,.55) !important;border:2px solid rgba(37,99,235,.35) !important;color:#94A3B8 !important;}}
.diff-btn>button:hover{{background:rgba(11,79,168,.25) !important;border-color:#1EA7FF !important;color:#FFFFFF !important;}}
.diff-btn-sel>button{{background:linear-gradient(135deg,#0B4FA8,#0284C7) !important;border:2px solid #1EA7FF !important;color:#FFFFFF !important;box-shadow:0 0 18px rgba(30,167,255,.3) !important;opacity:1 !important;cursor:default !important;pointer-events:none !important;}}
@media(max-width:950px){{.hero-grid{{grid-template-columns:1fr;}}.features-grid{{grid-template-columns:1fr;}}.footer-bar{{flex-direction:column;gap:1rem;text-align:center;}}}}
</style>""", unsafe_allow_html=True)

    SHIELD_MAIN_SVG = """<svg width="130" height="148" viewBox="0 0 130 148" fill="none" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="lock_g" x1="38" y1="72" x2="92" y2="132" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#FFFFFF"/><stop offset="100%" stop-color="#C8E6FF"/></linearGradient><filter id="sh_glow" x="-25%" y="-25%" width="150%" height="150%"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><path d="M65 4L124 24V72C124 108 98 136 65 144C32 136 6 108 6 72V24L65 4Z" fill="rgba(30,90,180,0.15)" stroke="#4A9EFF" stroke-width="3" filter="url(#sh_glow)"/><path d="M65 13L114 30V72C114 103 91 128 65 136C39 128 16 103 16 72V30L65 13Z" fill="none" stroke="rgba(120,190,255,0.3)" stroke-width="1.5"/><path d="M44 82V67C44 52 86 52 86 67V82" stroke="url(#lock_g)" stroke-width="10" stroke-linecap="round" fill="none"/><rect x="34" y="79" width="62" height="48" rx="9" fill="url(#lock_g)"/><circle cx="65" cy="100" r="8" fill="#1558A8"/><rect x="61.5" y="100" width="7" height="13" rx="2.5" fill="#1558A8"/></svg>"""
    BRAIN_SVG  = """<svg width="52" height="52" viewBox="0 0 52 52" fill="none"><path d="M26 8C20 8 17 12 15 20C12 20 9 22 9 26C9 30 12 32 15 32C14 37 17 40 26 44" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round" fill="none"/><path d="M26 8C32 8 35 12 37 20C40 20 43 22 43 26C43 30 40 32 37 32C38 37 35 40 26 44" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round" fill="none"/><line x1="26" y1="8" x2="26" y2="44" stroke="#1EA7FF" stroke-width="2"/><path d="M15 20C18 18 22 20 26 18C30 20 34 18 37 20" stroke="#1EA7FF" stroke-width="2" fill="none"/><path d="M15 32C18 30 22 32 26 30C30 32 34 30 37 32" stroke="#1EA7FF" stroke-width="2" fill="none"/></svg>"""
    TARGET_SVG = """<svg width="52" height="52" viewBox="0 0 52 52" fill="none"><circle cx="26" cy="28" r="18" stroke="#1EA7FF" stroke-width="2.5" fill="none"/><circle cx="26" cy="28" r="10" stroke="#1EA7FF" stroke-width="2.5" fill="none"/><circle cx="26" cy="28" r="3" fill="#1EA7FF"/><path d="M34 10L42 10L42 18" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round" fill="none"/><line x1="42" y1="10" x2="29" y2="23" stroke="#1EA7FF" stroke-width="2.5"/></svg>"""
    CHART_SVG  = """<svg width="52" height="52" viewBox="0 0 52 52" fill="none"><line x1="10" y1="44" x2="10" y2="8" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round"/><line x1="10" y1="44" x2="46" y2="44" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round"/><rect x="15" y="32" width="7" height="12" rx="2" fill="#1EA7FF" opacity=".85"/><rect x="26" y="22" width="7" height="22" rx="2" fill="#1EA7FF" opacity=".85"/><rect x="37" y="12" width="7" height="32" rx="2" fill="#1EA7FF" opacity=".85"/></svg>"""
    SHIELD_SVG = """<svg width="52" height="56" viewBox="0 0 52 56" fill="none"><path d="M26 4L46 12V28C46 39 36 50 26 52C16 50 6 39 6 28V12L26 4Z" stroke="#1EA7FF" stroke-width="2.5" fill="none"/><path d="M18 28L23 33L34 22" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round" fill="none"/></svg>"""
    SHFOOT     = """<svg width="42" height="48" viewBox="0 0 42 48" fill="none"><path d="M21 3L39 10V24C39 34 31 43 21 46C11 43 3 34 3 24V10L21 3Z" stroke="#1EA7FF" stroke-width="2.5" fill="none"/></svg>"""
    ECG_SVG    = """<svg width="80" height="28" viewBox="0 0 80 28" fill="none"><polyline points="0,14 15,14 20,4 25,24 30,4 35,20 40,14 80,14" stroke="#1EA7FF" stroke-width="2.5" stroke-linecap="round" fill="none"/></svg>"""

    # ── Navbar ──────────────────────────────────────────────────
    # Pure HTML navbar — no st.columns() at all.
    # Buttons are HTML <button> elements. JS sends a click to the
    # hidden Streamlit buttons below so session_state updates fire.
    nav_login    = t("Login","تسجيل الدخول")
    nav_register = t("Register","إنشاء حساب")
    nav_brand    = t("AI Phishing Awareness","التوعية بالتصيد الإلكتروني")
    user_name    = st.session_state.get("user_name","")
    shield_small = SHIELD_SVG.replace('width="52"','width="20"').replace('height="56"','height="22"')
    flex_dir     = "row-reverse" if is_arabic else "row"

    if user_name:
        # ── Logged-in: pure HTML, no buttons needed
        st.markdown(f"""
<div style="background:rgba(11,46,104,0.55);border:1px solid rgba(37,99,235,.4);
     border-radius:14px;padding:8px 20px;margin-bottom:1.2rem;
     display:flex;align-items:center;justify-content:space-between;
     flex-direction:{flex_dir};min-height:52px;">
  <div style="display:flex;align-items:center;gap:8px;flex-direction:{"row-reverse" if is_arabic else "row"};">
    {shield_small}
    <span style="font-size:15px;font-weight:800;color:#F8FAFC;white-space:nowrap;">{nav_brand}</span>
  </div>
  <div style="display:inline-flex;align-items:center;gap:6px;
      background:rgba(37,99,235,.15);border:1px solid rgba(37,99,235,.4);
      border-radius:20px;padding:5px 10px 5px 6px;">
    <div style="width:24px;height:24px;border-radius:50%;
        background:linear-gradient(135deg,#0B4FA8,#0284C7);
        display:flex;align-items:center;justify-content:center;font-size:11px;">👤</div>
    <span style="font-size:12px;color:#7DD3FC;font-weight:700;
        white-space:nowrap;max-width:140px;overflow:hidden;text-overflow:ellipsis;">
      {html_lib.escape(user_name)}</span>
  </div>
</div>""", unsafe_allow_html=True)

    else:
        # ── Guest: HTML navbar only — navigation via ?nav= query param
        st.markdown(f"""
<style>
.nb-btn {{
    height:34px; padding:0 16px; border-radius:9px; font-size:12px;
    font-weight:700; cursor:pointer; display:inline-flex; align-items:center;
    white-space:nowrap; text-decoration:none;
}}
.nb-btn-ghost {{
    background:rgba(15,23,42,.88); color:#EAF4FF !important;
    border:1px solid rgba(37,99,235,.5);
}}
.nb-btn-ghost:hover {{ background:rgba(37,99,235,.25); border-color:#1EA7FF; color:#fff !important; }}
.nb-btn-solid {{
    background:linear-gradient(90deg,#0B4FA8,#0284C7);
    color:white !important; border:none;
}}
.nb-btn-solid:hover {{ background:linear-gradient(90deg,#1560C0,#0396E0); }}
</style>
<div style="background:rgba(11,46,104,0.55);border:1px solid rgba(37,99,235,.4);
     border-radius:14px;padding:8px 20px;margin-bottom:1.2rem;
     display:flex;align-items:center;justify-content:space-between;
     flex-direction:{flex_dir};min-height:52px;">
  <div style="display:flex;align-items:center;gap:8px;flex-direction:{"row-reverse" if is_arabic else "row"};">
    {shield_small}
    <span style="font-size:15px;font-weight:800;color:#F8FAFC;white-space:nowrap;">{nav_brand}</span>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <a href="?nav=login&lang={st.session_state.get('language','English')}"  class="nb-btn nb-btn-ghost">{nav_login}</a>
    <a href="?nav=register&lang={st.session_state.get('language','English')}" class="nb-btn nb-btn-solid">{nav_register}</a>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Hero ────────────────────────────────────────────────────
    title   = t("AI Phishing Awareness","التوعية بالتصيد الإلكتروني بالذكاء الاصطناعي")
    tagline = t("Smart, Personalised, Protective.","ذكي، مخصص، وقائي")
    desc    = t("AI-powered training and assessment to help healthcare employees recognise and avoid phishing threats.",
                "تدريب وتقييم مدعوم بالذكاء الاصطناعي لمساعدة الموظفين الصحيين على التعرف على تهديدات التصيد الإلكتروني وتجنبها")
    time_badge = t("⏱️ ~15 minutes","⏱️ ~١٥ دقيقة")
    sh = f'<div class="shield-orb">{SHIELD_MAIN_SVG}</div>'
    co = f'''<div class="hero-content">
      <div class="hero-title">{title}</div>
      <div class="hero-tagline">{tagline}</div>
      <div class="hero-desc">{desc}</div>
      <div style="display:inline-flex;align-items:center;gap:6px;margin-top:.8rem;
                  background:rgba(37,99,235,.15);border:1px solid rgba(37,99,235,.35);
                  border-radius:8px;padding:5px 14px;">
        <span style="font-size:.9rem;color:#7DD3FC;font-weight:600;">{time_badge}</span>
      </div>
    </div>'''
    gi = co+sh if is_arabic else sh+co
    st.markdown(f'<div class="hero-card"><div class="hero-grid">{gi}</div></div>', unsafe_allow_html=True)

    # ── Feature cards ───────────────────────────────────────────
    cards = [
        (BRAIN_SVG, t("AI-Powered Learning","تعلم بالذكاء الاصطناعي"), t("Personalised content adapted to your role.","محتوى تعليمي مخصص حسب دورك الوظيفي")),
        (TARGET_SVG,t("Smart Assessment","تقييم ذكي"),                 t("Short, focused assessments to test your awareness.","تقييمات قصيرة ومركزة لاختبار وعيك")),
        (CHART_SVG, t("Personalised Feedback","تغذية راجعة مخصصة"),   t("Detailed results with insights and recommendations.","نتائج مفصلة تتضمن ملاحظات وتوصيات مخصصة")),
        (SHIELD_SVG,t("Stronger Together","معًا أكثر أمانًا"),         t("Building a secure healthcare environment for everyone.","بناء بيئة صحية آمنة للجميع")),
    ]
    st.markdown('<div class="features-grid">'+"".join(f'<div class="feature-card"><div class="feature-icon">{i}</div><div class="feature-title">{tt}</div><div class="feature-text">{tx}</div></div>' for i,tt,tx in cards)+'</div>', unsafe_allow_html=True)

    # ── Form + Side panel layout ─────────────────────────────────
    form_col, panel_col = st.columns([3, 1], gap="large")

    with form_col:
        form_title_txt = t("Let's personalise your experience","لنخصص تجربتك")
        st.markdown(f'<div class="form-section"><div class="form-title">👤 {form_title_txt}</div></div>', unsafe_allow_html=True)

        # Step labels
        def step_label(n, txt):
            return f'''<div style="font-size:.85rem;color:#94A3B8;margin-bottom:.5rem;
                        display:flex;align-items:center;gap:6px;direction:{dir_attr};">
              <span style="display:inline-flex;align-items:center;justify-content:center;
                           width:18px;height:18px;border-radius:50%;
                           background:rgba(37,99,235,.5);color:#7DD3FC;
                           font-size:10px;font-weight:800;">{n}</span>
              {txt}
            </div>'''

        # Step 1 — Language (required)
        lang_ok   = st.session_state.get("language","") != ""
        diff_ok   = st.session_state.get("difficulty","") != ""
        req_badge = f'<span style="color:#EF4444;font-size:.75rem;margin-right:4px;">*</span>'

        st.markdown(step_label("1", t("Select your preferred language","اختر اللغة المفضلة")), unsafe_allow_html=True)
        cur_lang  = st.session_state.get("language","")
        # Inject CSS to highlight selected language button
        en_cls = "lang-btn-sel" if cur_lang == "English" else "lang-btn"
        ar_cls = "lang-btn-sel" if cur_lang == "Arabic"  else "lang-btn"
        st.markdown(f"""<style>
.lang-btn button {{
    background: rgba(15,23,42,.78) !important;
    border: 1px solid rgba(37,99,235,.55) !important;
    color: #EAF4FF !important;
}}
.lang-btn-sel button {{
    background: linear-gradient(90deg,#0B4FA8,#0284C7) !important;
    border: 2px solid #1EA7FF !important;
    color: white !important;
    box-shadow: 0 0 14px rgba(30,167,255,.35) !important;
}}
.lang-btn-sel button:hover,
.lang-btn-sel button:focus,
.lang-btn-sel button:active {{
    background: linear-gradient(90deg,#0B4FA8,#0284C7) !important;
    border: 2px solid #1EA7FF !important;
    color: white !important;
}}
</style>""", unsafe_allow_html=True)
        col1,col2 = st.columns(2)
        with col1:
            st.markdown(f'<div class="{en_cls}">', unsafe_allow_html=True)
            st.button("English", key="english", on_click=set_language, args=("English",), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="{ar_cls}">', unsafe_allow_html=True)
            st.button("العربية", key="arabic",  on_click=set_language, args=("Arabic",), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(step_label("2", t("Select your role","اختر دورك الوظيفي")), unsafe_allow_html=True)
        opts = [t("Choose your role","اختر دورك الوظيفي"),t("Clinical","سريري"),t("Admin / Management","إداري / إدارة"),t("IT / Informatics","تقنية المعلومات / المعلوماتية"),t("Other","أخرى")]
        sel  = st.selectbox("role",opts,index=0,label_visibility="collapsed")
        other_role = ""
        if sel==opts[-1]: other_role=st.text_input(t("Please specify your role","يرجى كتابة دورك الوظيفي"),placeholder=t("Type your role here","اكتب دورك الوظيفي هنا"))

        st.markdown(step_label("3", t("Select difficulty level","اختر مستوى الصعوبة")), unsafe_allow_html=True)

    with panel_col:
        # What to expect side panel
        ph_label  = t("Learning phase","مرحلة التعلم")
        as_label  = t("Assessment","الاختبار")
        rep_label = t("Performance report","تقرير الأداء")
        exp_title = t("WHAT TO EXPECT","ماذا تتوقع")
        diff_title= t("DIFFICULTY","الصعوبة")
        beg_lbl   = t("Beginner","مبتدئ")
        mid_lbl   = t("Intermediate","متوسط")
        adv_lbl   = t("Advanced","متقدم")
        small_brain  = BRAIN_SVG.replace('width="52"','width="18"').replace('height="52"','height="18"')
        small_target = TARGET_SVG.replace('width="52"','width="18"').replace('height="52"','height="18"')
        small_chart  = CHART_SVG.replace('width="52"','width="18"').replace('height="52"','height="18"')
        st.markdown(f"""
<div style="background:rgba(8,47,73,.2);border:1px solid rgba(37,99,235,.25);
            border-radius:14px;padding:1.2rem 1rem;margin-top:1rem;direction:{dir_attr};">
  <div style="font-size:.75rem;font-weight:800;color:#7DD3FC;letter-spacing:.06em;margin-bottom:14px;">{exp_title}</div>
  <div style="display:flex;flex-direction:column;gap:9px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;
                background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">
      {small_brain}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{ph_label}</span>
    </div>
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;
                background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">
      {small_target}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{as_label}</span>
    </div>
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;
                background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">
      {small_chart}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{rep_label}</span>
    </div>
  </div>
  <div style="border-top:1px solid rgba(37,99,235,.2);padding-top:12px;">
    <div style="font-size:.75rem;font-weight:800;color:#7DD3FC;letter-spacing:.05em;margin-bottom:8px;direction:{dir_attr};text-align:{text_align};">{diff_title}</div>
    <div style="display:flex;flex-direction:column;gap:5px;direction:{dir_attr};text-align:{text_align};">
      <div style="font-size:.8rem;color:#94A3B8;">🟢 {beg_lbl}</div>
      <div style="font-size:.8rem;color:#94A3B8;">🟡 {mid_lbl}</div>
      <div style="font-size:.8rem;color:#94A3B8;">🔴 {adv_lbl}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # Difficulty + Start button inside form_col
    with form_col:
        # Difficulty level selector
        current_diff  = st.session_state.get("difficulty","medium")
        is_arabic_now = st.session_state["language"] == "Arabic"

        if st.session_state.get("language","English") == "Arabic":
            ordered = [("easy","🟢  مبتدئ"),("medium","🟡  متوسط"),("hard","🔴  متقدم")]
        else:
            ordered = [("easy","🟢  Beginner"),("medium","🟡  Intermediate"),("hard","🔴  Advanced")]

        # For Arabic: مبتدئ on right, متوسط center, متقدم left
        # Streamlit cols go left→right: col[0]=left, col[2]=right
        # So for RTL: display order = [hard, medium, easy] in cols [0,1,2]
        diff_cols = st.columns(3)
        if st.session_state.get("language","English") == "Arabic":
            ordered_display = list(reversed(ordered))  # متقدم, متوسط, مبتدئ
        else:
            ordered_display = ordered

        for i,(dk,lbl) in enumerate(ordered_display):
            with diff_cols[i]:
                is_sel  = current_diff == dk
                css_cls = "diff-btn diff-btn-sel" if is_sel else "diff-btn"
                st.markdown(f'<div class="{css_cls}">', unsafe_allow_html=True)
                if st.button(lbl, key=f"diff_{dk}", use_container_width=True):
                    st.session_state["difficulty"] = dk
                    st.session_state["diff_explicitly_chosen"] = True
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        # ── Researcher Mode: AI Provider selector (hidden from normal users) ──
        # Access via: ?mode=researcher in the URL
        if st.query_params.get("mode") == "researcher":
            st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size:.75rem;font-weight:800;color:#F59E0B;letter-spacing:.06em;margin-bottom:.5rem;direction:{dir_attr};">🔬 RESEARCHER MODE — AI Provider</div>', unsafe_allow_html=True)
            provider_options = {
                "groq":      "🟠 Groq  (LLaMA 3.3-70b) — Baseline v3",
                "openai":    "🟢 ChatGPT  (GPT-4o) — Most used globally",
                "anthropic": "🟣 Claude  (claude-sonnet-4-6) — Best writing quality",
                "gemini":    "🔵 Gemini  (1.5 Pro) — Fastest growing",
            }
            cur_provider = st.session_state.get("ai_provider", "groq")
            prov_cols = st.columns(2)
            prov_items = list(provider_options.items())
            for i, (pk, plbl) in enumerate(prov_items):
                with prov_cols[i % 2]:
                    is_psel = cur_provider == pk
                    pcss = "diff-btn diff-btn-sel" if is_psel else "diff-btn"
                    st.markdown(f'<div class="{pcss}">', unsafe_allow_html=True)
                    if st.button(plbl, key=f"prov_{pk}", use_container_width=True):
                        st.session_state["ai_provider"] = pk
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size:.72rem;color:#64748B;margin-top:.3rem;direction:{dir_attr};">Active: <b style="color:#F59E0B;">{provider_options.get(cur_provider,"")}</b></div>', unsafe_allow_html=True)
            st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

        st.markdown('<div class="start-btn" style="margin-top:.8rem;">',unsafe_allow_html=True)
        if st.button(t("Start Personalised Training","ابدأ التدريب المخصص"),key="start_training", use_container_width=True):
            fr = other_role.strip() if sel==opts[-1] else sel
            lang_chosen = st.session_state.get("lang_explicitly_chosen", False)
            diff_chosen = st.session_state.get("diff_explicitly_chosen", False)
            user_logged = st.session_state.get("user_name","").strip() != ""

            if not user_logged:
                st.warning(t("⚠️ Please login or register first using the button at the top.",
                             "⚠️ يرجى تسجيل الدخول أو إنشاء حساب أولاً عبر الزر في الأعلى"))
            elif not lang_chosen:
                st.warning(t("⚠️ Please select your preferred language first.",
                             "⚠️ يرجى اختيار اللغة المفضلة أولاً"))
            elif fr==opts[0]:
                st.warning(t("⚠️ Please select your role.",
                             "⚠️ يرجى اختيار دورك الوظيفي"))
            elif not diff_chosen:
                st.warning(t("⚠️ Please select a difficulty level.",
                             "⚠️ يرجى اختيار مستوى الصعوبة"))
            else:
                if "scenario_order" in st.session_state: del st.session_state["scenario_order"]
                go_to_learning(fr); st.rerun()
        st.markdown('</div>',unsafe_allow_html=True)

    ft = t("Together, let's build a stronger, phishing-resistant healthcare environment.","معًا نبني بيئة صحية أكثر مقاومة للتصيد الإلكتروني")
    fs = t("Stay aware, Stay secure, Save lives.","كن واعيًا، ابق آمنًا، وساهم في حماية الأرواح")
    if is_arabic:
        f1=f'<div class="footer-side" style="direction:ltr;"><span style="direction:rtl;">{fs}</span>&nbsp;{ECG_SVG}</div>'
        f2=f'<div class="footer-side" style="direction:ltr;justify-content:flex-end;"><span style="direction:rtl;">{ft}</span>{SHFOOT}</div>'
    else:
        f1=f'<div class="footer-side">{SHFOOT}<span>{ft}</span></div>'
        f2=f'<div class="footer-side">{ECG_SVG}&nbsp;{fs}</div>'
    st.markdown(f'<div class="footer-bar">{f1}{f2}</div>',unsafe_allow_html=True)


# =============================================================
# PAGE 2: LEARNING PHASE
# -------------------------------------------------------------
# Shows 6 AI-generated phishing email examples one at a time.
# Each example includes:
#   - The phishing email (rendered by render_email_window)
#     with numbered red badge indicators on suspicious elements
#   - AI Tutor panel: indicators, why_risky, learning_tip
# Emails are cached in session_state["emails"] so navigating
# back does not trigger a new API call.
# Progress bar shows current position (1 of 6 ... 6 of 6).
# =============================================================
def page_learning():
    is_arabic  = st.session_state["language"]=="Arabic"
    dir_attr   = 'rtl' if is_arabic else 'ltr'
    text_align = 'right' if is_arabic else 'left'
    TOTAL      = 6
    idx       = st.session_state["example_index"]

    if st.session_state.get("cache_version",0) < 13:
        st.session_state["emails"]={}; st.session_state["cache_version"]=13

    st.markdown(f"""<style>
#MainMenu,header,footer{{visibility:hidden;}}
.stApp{{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}}
.block-container{{max-width:1200px;padding-top:2rem;}}
.tutor-panel{{background:rgba(2,6,23,.7);border:1px solid rgba(37,99,235,.45);border-radius:16px;padding:1.4rem 1.5rem;direction:{dir_attr};text-align:{text_align};}}
.tutor-section{{font-size:1rem;font-weight:800;color:#F1F5F9;margin:1rem 0 .4rem;direction:{dir_attr};text-align:{text_align};}}
.tutor-text{{color:#94A3B8;font-size:.92rem;line-height:1.65;direction:{dir_attr};text-align:{text_align};}}
.tip-box{{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.35);border-radius:10px;padding:.8rem 1rem;color:#6EE7B7;font-size:.9rem;line-height:1.6;margin-top:.8rem;direction:{dir_attr};text-align:{text_align};}}
.stButton>button{{min-height:52px;background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;color:white !important;border:none !important;font-weight:800 !important;border-radius:12px !important;font-size:1rem !important;}}
</style>""", unsafe_allow_html=True)

    if idx not in st.session_state["emails"]:
        with st.spinner(t("🤖 Generating phishing example...","🤖 جارٍ توليد مثال التصيد...")):
            st.session_state["emails"][idx] = generate_email(st.session_state["role"],idx,st.session_state["language"])
            st.rerun()

    email = st.session_state["emails"].get(idx,{})
    pct   = int((idx/TOTAL)*100)

    st.markdown(f"""
<div style="margin-bottom:1.5rem;direction:{dir_attr};">
  <div style="font-size:2.2rem;font-weight:900;color:#F8FAFC;margin-bottom:.4rem;text-align:{text_align};">
    {t("AI Tutor-Guided Learning Phase","مرحلة التعلم بتوجيه الذكاء الاصطناعي")}
  </div>
  <div style="width:100%;height:6px;background:rgba(37,99,235,.25);border-radius:99px;margin:.8rem 0;">
    <div style="height:6px;border-radius:99px;background:linear-gradient(90deg,#1EA7FF,#2563EB);width:{pct}%;transition:width .4s ease;"></div>
  </div>
  <div style="color:#7DD3FC;font-size:.95rem;font-weight:600;">
    {t(f"Example {idx+1} of {TOTAL}",f"مثال {idx+1} من {TOTAL}")}
  </div>
</div>""", unsafe_allow_html=True)

    if "error" in email:
        st.error(f"**Error:** {email['error']}")
        if st.button(t("🔄 Try Again","🔄 حاول مرة أخرى"),key="retry_btn"):
            del st.session_state["emails"][idx]; st.rerun()
        return

    if is_arabic:
        col_tutor, col_email = st.columns([1,1.1],gap="large")
    else:
        col_email, col_tutor = st.columns([1.1,1],gap="large")

    with col_email:
        render_email_window(email, is_arabic, show_badges=True)

    with col_tutor:
        indicators    = email.get("indicators",[])
        indicators_html = ""
        for ind in indicators:
            row_dir = 'rtl' if is_arabic else 'ltr'
            pad     = 'padding-right:2rem;' if is_arabic else 'padding-left:2rem;'
            ta2     = 'right' if is_arabic else 'left'
            indicators_html += f"""
<div style="margin-bottom:1rem;">
  <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.3rem;direction:{row_dir};">
    <span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#DC2626;color:white;font-size:.75rem;font-weight:800;flex-shrink:0;">{ind.get('number','')}</span>
    <span style="font-weight:700;color:#E2E8F0;font-size:.95rem;">{ind.get('title','')}</span>
  </div>
  <div style="color:#94A3B8;font-size:.9rem;line-height:1.65;{pad};direction:{row_dir};text-align:{ta2};">{ind.get('description','')}</div>
</div>"""

        st.markdown(f"""
<div class="tutor-panel">
  <div style="font-size:1.3rem;font-weight:900;color:#F8FAFC;margin-bottom:.2rem;">🎯 {t("AI Tutor Analysis","تحليل المعلم الذكي")}</div>
  <div style="color:#64748B;font-size:.85rem;margin-bottom:1.2rem;">{t("AI-guided phishing awareness","شرح توعوي بالتصيد")}</div>
  <div class="tutor-section">{t("What is suspicious?","ما هو المشبوه؟")}</div>
  {indicators_html}
  <div class="tutor-section">{t("Why is it risky?","لماذا هو خطير؟")}</div>
  <div class="tutor-text">{email.get("why_risky","")}</div>
  <div class="tutor-section">💡 {t("Learning Tip","نصيحة تعليمية")}</div>
  <div class="tip-box">{email.get("learning_tip","")}</div>
</div>""", unsafe_allow_html=True)

    st.markdown('<div style="height:1.5rem"></div>',unsafe_allow_html=True)
    bc,_ = st.columns([1,3])
    with bc:
        if idx<TOTAL-1:
            if st.button(t("Next Example →","← المثال التالي"),key="next_btn"):
                st.session_state["example_index"]+=1; st.rerun()
        else:
            if st.button(t("Complete Learning Phase →","← إتمام مرحلة التعلم"),key="complete_btn"):
                st.session_state["page"]="complete"; st.rerun()

# =============================================================
# PAGE 3: LEARNING COMPLETE
# -------------------------------------------------------------
# Transition page shown after all 6 learning examples are done.
# Congratulates the user and provides a button to start the
# Assessment Phase. Also resets the assessment scenario order
# so each assessment session is freshly shuffled.
# =============================================================
def page_complete():
    is_arabic=st.session_state["language"]=="Arabic"; da='rtl' if is_arabic else 'ltr'
    def tc(e,a): return a if is_arabic else e
    st.markdown("""<style>#MainMenu,header,footer{visibility:hidden;}.stApp{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}.block-container{max-width:700px;padding-top:4rem;}.stButton>button{min-height:52px;background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;color:white !important;border:none !important;font-weight:800 !important;border-radius:12px !important;font-size:1rem !important;width:100%;}</style>""",unsafe_allow_html=True)
    msg=tc("You have completed all 6 learning examples.\nYou are now ready to test your phishing awareness skills.","لقد أكملت جميع الأمثلة التعليمية الـ 6.\nأنت الآن جاهز لاختبار مستوى وعيك بالتصيد الإلكتروني.")
    st.markdown(f'<div style="text-align:center;padding:3rem 2rem;border:1px solid rgba(37,99,235,.45);border-radius:24px;background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));direction:{da};"><div style="font-size:4rem;margin-bottom:1rem;">🎓</div><div style="font-size:2rem;font-weight:900;color:#F8FAFC;margin-bottom:1rem;">{tc("Great job","ممتاز")}</div><div style="font-size:1.05rem;color:#DCEBFF;line-height:1.8;margin-bottom:2rem;white-space:pre-line;">{msg}</div></div>',unsafe_allow_html=True)
    st.markdown('<div style="height:1.5rem"></div>',unsafe_allow_html=True)
    if st.button(tc("Start Assessment →","← ابدأ الاختبار"),key="go_assessment"):
        if "assess_scenario_order" in st.session_state: del st.session_state["assess_scenario_order"]
        st.session_state.update({"page":"assessment","assess_index":0,"assess_emails":{},"assess_answers":{}})
        st.rerun()


# ══════════════════════════════════════════════════════════
#  ASSESSMENT — DIVERSE ROLE-AWARE SCENARIOS
# ══════════════════════════════════════════════════════════
ASSESS_PHISHING_TYPES = [
    ("link",  False, "", True),
    ("pdf",   True, ".pdf", False),
    ("xlsx",  True, ".xlsx", False),
    ("hr_link",False,"",True),
    ("exec",  False,"",False),
]
ASSESS_LEGIT_TYPES = [
    ("meeting",     "دعوة اجتماع روتينية من نطاق المستشفى الرسمي. أسلوب مهني هادئ، لا إلحاح.","A routine meeting invitation from an official hospital domain. Professional tone, no urgency."),
    ("maintenance", "إعلان رسمي من قسم تقنية المعلومات عن صيانة مجدولة. بريد رسمي، لا روابط مشبوهة.","Official IT department notice about scheduled maintenance. Official domain, no suspicious links."),
    ("hr_legit",    "إشعار موارد بشرية شرعي عن دورة تدريبية أو تحديث سياسات. نطاق رسمي، لا طلب بيانات.","Legitimate HR notification about training or policy update. Official domain, no credential requests."),
    ("manager",     "مدير القسم يرسل تحديثاً روتينياً للعمل. تواصل عمل عادي من بريد رسمي.","Department manager sending a routine work update. Normal business communication from official email."),
    ("payslip",     "إشعار راتب أو جدول عمل شرعي من نظام الموارد البشرية الرسمي. إشعار عادي، لا عناصر مشبوهة.","Legitimate payslip or schedule notification from official HR system. Standard notification, no suspicious elements."),
]

def get_assess_shuffled_order():
    if "assess_scenario_order" not in st.session_state:
        order = list(range(5)); random.shuffle(order)
        st.session_state["assess_scenario_order"] = order
    return st.session_state["assess_scenario_order"]

def build_assess_prompt(role, index, is_phishing, language):
    is_ar      = (language == "Arabic")
    difficulty = st.session_state.get("difficulty", "medium")
    role_info  = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    role_desc, role_ctx, role_type = role_info
    seed = st.session_state.get("cache_version", 13)
    import time
    session_seed = abs(hash(str(seed) + str(index) + str(is_phishing) + str(time.time()))) % 99999

    role_guidance = {
        "clinical": (
            "a nurse, doctor, pharmacist, or lab technician in a Saudi hospital",
            "EMR, patient records, lab results, pharmacy, clinical schedules, MOH alerts, medical devices, surgery"
        ),
        "admin": (
            "a medical secretary, receptionist, patient records clerk, insurance coordinator, or billing specialist in Saudi healthcare",
            "patient appointments, medical records, health insurance, hospital billing, medical procurement, MOH compliance"
        ),
        "it": (
            "an IT specialist, system administrator, or cybersecurity officer in a Saudi hospital",
            "hospital network, VPN, servers, EMR system, cloud backup, SSL, firewall, software licenses, IT helpdesk"
        ),
        "other": (
            "a general hospital employee in Saudi Arabia",
            "any hospital department"
        ),
    }
    r_desc, r_ctx = role_guidance.get(role_type, role_guidance["other"])

    if is_ar:
        diff_rules = {
            "easy":   "مبتدئ: نطاق مزيف واضح، أخطاء إملائية، ALL-CAPS، تحية عامة، طلب مشبوه صريح.",
            "medium": "متوسط: نطاق مشبوه نسبياً، علامة تحذيرية واحدة، إلحاح معتدل.",
            "hard":   "متقدم: نطاق يشبه الحقيقي مع تغيير بسيط، لغة سليمة، علامة واحدة خفية فقط.",
        }
        lang_rule = "عربية فصحى فقط. الروابط والبريد الإلكتروني لاتينية. حقل 'to' بريد فقط."
        task_p = f"ولّد رسالة تصيد إلكتروني واقعية تستهدف {r_desc}. اختر نوع الهجوم بحرية كاملة من السياق: {r_ctx}. كن مبدعاً ومختلفاً."
        task_l = f"ولّد بريد إلكتروني شرعي وطبيعي من بيئة عمل {r_desc}. استخدم نطاق رسمي (@hospital.org أو @moh.gov.sa). لا علامات تصيد."
        expl   = "اشرح بوضوح لماذا هذا البريد " + ("تصيد إلكتروني وما هي العلامات التحذيرية" if is_phishing else "شرعي وآمن")
        from_ex, subj_ex, body_ex = "المرسل <email@domain.com>", "موضوع الرسالة", "نص الرسالة بالعربية"
    else:
        diff_rules = {
            "easy":   "BEGINNER: obvious fake domain, spelling mistakes, ALL-CAPS urgency, generic greeting, suspicious request.",
            "medium": "INTERMEDIATE: slightly suspicious domain, 1 red flag, moderate urgency.",
            "hard":   "ADVANCED: nearly real domain tiny change only, perfect language, only 1 subtle red flag.",
        }
        lang_rule = "English only throughout. Email addresses and URLs stay Latin."
        task_p = f"Generate a realistic phishing email targeting {r_desc}. Freely choose any attack type from this context: {r_ctx}. Be creative and varied."
        task_l = f"Generate a realistic legitimate workplace email for {r_desc}. Use official domain (@hospital.org or @moh.gov.sa). Zero suspicious elements."
        expl   = f"Clearly explain why this email is {'phishing — identify the red flags' if is_phishing else 'legitimate and safe'}"
        from_ex, subj_ex, body_ex = "Sender Name <email@domain.com>", "subject line", "email body in English"

    diff_rule = diff_rules.get(difficulty, diff_rules["medium"])
    task = task_p if is_phishing else task_l

    return f"""Phishing awareness assessment email for Saudi healthcare. Seed:{session_seed}

TARGET: {r_desc}
CONTEXT: {r_ctx}

TASK: {task}

DIFFICULTY: {diff_rule}

LANGUAGE: {lang_rule}

FORMAT: body=plain text only, \\n for line breaks, no HTML. "to"=email address only.
{"If phishing uses a link: put URL in suspicious_link AND in body. If attachment: put filename in attachment field." if is_phishing else 'suspicious_link:"", attachment:""'}
{"If legitimate: use real official domain, no suspicious links or requests." if not is_phishing else ""}

RETURN ONLY VALID JSON:
{{"is_phishing":{"true" if is_phishing else "false"},"from":"{from_ex}","to":"employee@hospital.org","subject":"{subj_ex}","attachment":"","body":"{body_ex}","suspicious_link":"","explanation":"{expl}"}}"""

def generate_assess_email(role, index, is_phishing, language):
    for attempt in range(3):
        try:
            data = call_groq(build_assess_prompt(role, index, is_phishing, language), max_tokens=800)
            if "error" in data:
                return {"error": data["error"].get("message", str(data["error"]))}
            result = parse_json_response(data["choices"][0]["message"]["content"].strip())
            result = clean_result(result, language=="Arabic")
            result["to"] = get_recipient(st.session_state.get("role","Clinical"), index, language)
            # If AI included a link, make sure it appears in body
            if result.get("suspicious_link","").strip():
                if result["suspicious_link"] not in result.get("body",""):
                    result["body"] = result.get("body","") + f'\n{result["suspicious_link"]}'
            return result
        except json.JSONDecodeError:
            if attempt == 2:
                return {"error": "Failed to parse. Please try again."}
        except Exception as e:
            return {"error": str(e)}

# =============================================================
# PAGE 4: ASSESSMENT PHASE
# -------------------------------------------------------------
# Presents 10 email scenarios (5 phishing + 5 legitimate) in
# random order. The user must classify each as phishing or
# legitimate by clicking one of two buttons.
# After answering: shows correct/incorrect feedback only.
# Full explanation is deferred to the Results page.
# Emails cached in session_state["assess_emails"].
# Pattern (which are phishing/legit) stored in assess_pattern.
# Layout: Arabic = action panel LEFT, email RIGHT.
#         English = email LEFT, action panel RIGHT.
# =============================================================
def page_assessment():
    is_arabic=st.session_state["language"]=="Arabic"; da='rtl' if is_arabic else 'ltr'
    TOTAL=10; idx=st.session_state.get("assess_index",0)
    def ta(e,a): return a if is_arabic else e

    if "assess_pattern" not in st.session_state:
        p=[True]*5+[False]*5; random.shuffle(p); st.session_state["assess_pattern"]=p
    pattern=st.session_state["assess_pattern"]

    st.markdown(f"""<style>
#MainMenu,header,footer{{visibility:hidden;}}
.stApp{{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}}
.block-container{{max-width:960px;padding-top:2rem;}}
.stButton>button{{min-height:52px;font-weight:800 !important;border-radius:12px !important;font-size:1rem !important;background:rgba(15,23,42,.88) !important;color:white !important;border:1px solid rgba(37,99,235,.55) !important;width:100% !important;transition:.2s ease;}}
.stButton>button:hover{{background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;border-color:#1EA7FF !important;}}
</style>""",unsafe_allow_html=True)

    if idx not in st.session_state["assess_emails"]:
        with st.spinner(ta("🤖 Generating scenario...","🤖 جارٍ توليد السيناريو...")):
            st.session_state["assess_emails"][idx]=generate_assess_email(st.session_state["role"],idx,pattern[idx],st.session_state["language"])
            st.rerun()

    email=st.session_state["assess_emails"].get(idx,{})
    answered_count = len(st.session_state.get("assess_answers", {}))
    pct=int((answered_count/TOTAL)*100)
    st.markdown(f"""
<div style="margin-bottom:1.5rem;direction:{da};">
  <div style="font-size:2rem;font-weight:900;color:#F8FAFC;margin-bottom:.4rem;">{ta("AI-Generated Assessment","مرحلة الاختبار")}</div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin:.8rem 0 .3rem;">
    <div style="color:#7DD3FC;font-size:.95rem;font-weight:600;">{ta(f"Question {idx+1} of {TOTAL}",f"السؤال {idx+1} من {TOTAL}")}</div>
    <div style="color:#F59E0B;font-size:.9rem;font-weight:700;">{pct}%</div>
  </div>
  <div style="width:100%;height:8px;background:rgba(37,99,235,.2);border-radius:99px;overflow:hidden;">
    <div style="height:8px;border-radius:99px;background:linear-gradient(90deg,#F59E0B,#EF4444);width:{pct}%;transition:width .5s ease;"></div>
  </div>
  <div style="display:flex;justify-content:space-between;margin-top:.4rem;">
    {"".join(f'<div style="width:{100//TOTAL}%;height:4px;border-radius:2px;background:{"#F59E0B" if i < answered_count else "rgba(255,255,255,.1)"};margin:0 1px;"></div>' for i in range(TOTAL))}
  </div>
</div>""",unsafe_allow_html=True)

    if "error" in email:
        st.error(f"Error: {email['error']}")
        if st.button(ta("🔄 Try Again","🔄 حاول مرة أخرى"),key="assess_retry"):
            del st.session_state["assess_emails"][idx]; st.rerun()
        return

    if is_arabic: col_action,col_email=st.columns([1,1.2],gap="large")
    else:         col_email,col_action=st.columns([1.2,1],gap="large")

    with col_email: render_email_window(email,is_arabic,show_badges=False)

    with col_action:
        q=ta("Is this email phishing or legitimate?","هل هذه الرسالة تصيد إلكتروني أم شرعية؟")
        st.markdown(f'<div style="background:rgba(2,6,23,.7);border:1px solid rgba(37,99,235,.45);border-radius:16px;padding:1.5rem;text-align:center;direction:{da};margin-bottom:1rem;"><div style="font-size:1.1rem;font-weight:800;color:#F1F5F9;">{q}</div></div>',unsafe_allow_html=True)

        answered=idx in st.session_state["assess_answers"]
        if not answered:
            c1,c2=st.columns(2)
            with c1:
                if st.button(f"🚨 {ta('Phishing','تصيد إلكتروني')}",key=f"ph_{idx}", use_container_width=True):
                    st.session_state["assess_answers"][idx]="phishing"; st.rerun()
            with c2:
                if st.button(f"✅ {ta('Legitimate','شرعية')}",key=f"lg_{idx}", use_container_width=True):
                    st.session_state["assess_answers"][idx]="legitimate"; st.rerun()
        else:
            ua=st.session_state["assess_answers"][idx]; ca2="phishing" if pattern[idx] else "legitimate"; ok=ua==ca2
            c="#6EE7B7" if ok else "#FCA5A5"; bg="rgba(16,185,129,.15)" if ok else "rgba(239,68,68,.15)"; br="rgba(16,185,129,.5)" if ok else "rgba(239,68,68,.5)"
            ic="✅" if ok else "❌"; lb=ta("Correct!","إجابة صحيحة!") if ok else ta("Incorrect!","إجابة خاطئة!")
            st.markdown(f'<div style="background:{bg};border:2px solid {br};border-radius:12px;padding:1rem;text-align:center;color:{c};font-weight:800;font-size:1.1rem;margin-bottom:1rem;">{ic} {lb}</div>',unsafe_allow_html=True)
            if idx<TOTAL-1:
                if st.button(ta("Next Question →","← السؤال التالي"),key=f"na_{idx}", use_container_width=True):
                    st.session_state["assess_index"]+=1; st.rerun()
            else:
                if st.button(ta("View Results →","← عرض النتائج"),key="vr", use_container_width=True):
                    st.session_state["page"]="results"; st.rerun()


# =============================================================
# PAGE 5: RESULTS
# -------------------------------------------------------------
# Shows overall score (X/10) with colour-coded feedback.
# Lists all 10 questions with:
#   - tick/cross icon for correct/incorrect
#   - phishing/legitimate badge
#   - AI-generated explanation of WHY each email is what it is
# Provides a "Go to Report" button to see the full analysis.
# =============================================================
def page_results():
    is_arabic=st.session_state["language"]=="Arabic"; da='rtl' if is_arabic else 'ltr'; TOTAL=10
    def tr(e,a): return a if is_arabic else e
    st.markdown("""<style>#MainMenu,header,footer{visibility:hidden;}.stApp{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}.block-container{max-width:900px;padding-top:2rem;}.stButton>button{min-height:52px;background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;color:white !important;border:none !important;font-weight:800 !important;border-radius:12px !important;}</style>""",unsafe_allow_html=True)
    answers=st.session_state.get("assess_answers",{}); pattern=st.session_state.get("assess_pattern",[True]*5+[False]*5); emails=st.session_state.get("assess_emails",{})
    score=sum(1 for i in range(TOTAL) if answers.get(i)==("phishing" if pattern[i] else "legitimate"))
    pct=int((score/TOTAL)*100)
    sc="#10B981" if pct>=80 else "#F59E0B" if pct>=60 else "#EF4444"
    sl=tr("Excellent 🎉","ممتاز 🎉") if pct>=80 else tr("Good job 👍","جيد 👍") if pct>=60 else tr("Keep practicing 💪","استمر في التدريب 💪")
    st.markdown(f'<div style="text-align:center;padding:2rem;border:1px solid rgba(37,99,235,.45);border-radius:24px;background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));margin-bottom:2rem;direction:{da};"><div style="font-size:1.5rem;font-weight:900;color:#F8FAFC;margin-bottom:1rem;">{tr("Your Results","نتائجك")}</div><div style="font-size:4rem;font-weight:900;color:{sc};">{score}/{TOTAL}</div><div style="font-size:1.2rem;color:{sc};font-weight:700;">{sl}</div><div style="color:#94A3B8;margin-top:.5rem;">{tr(f"You answered {score} of {TOTAL} correctly ({pct}%)",f"أجبت على {score} من {TOTAL} بشكل صحيح ({pct}٪)")}</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:1.3rem;font-weight:900;color:#F8FAFC;margin-bottom:1rem;direction:{da};">📋 {tr("Review","مراجعة الإجابات")}</div>',unsafe_allow_html=True)
    for i in range(TOTAL):
        em=emails.get(i,{})
        if not em or "error" in em: continue
        ua=answers.get(i,""); ca2="phishing" if pattern[i] else "legitimate"; ok=ua==ca2
        bc2="rgba(16,185,129,.5)" if ok else "rgba(239,68,68,.5)"; bg2="rgba(16,185,129,.05)" if ok else "rgba(239,68,68,.05)"
        ri="✅" if ok else "❌"; tl=tr("Phishing","تصيد") if pattern[i] else tr("Legitimate","شرعية"); ic="🚨" if pattern[i] else "✅"
        exp=re.sub(r'<[^>]+>','',em.get("explanation",""))
        st.markdown(f'<div style="border:1px solid {bc2};border-radius:14px;padding:1.2rem 1.5rem;background:{bg2};margin-bottom:1rem;direction:{da};"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;flex-wrap:wrap;gap:.5rem;"><span style="font-weight:800;color:#E2E8F0;">{ri} {tr(f"Q{i+1}",f"س{i+1}")} — {html_lib.escape(em.get("subject",""))}</span><span style="background:{"rgba(239,68,68,.2)" if pattern[i] else "rgba(16,185,129,.2)"};color:{"#FCA5A5" if pattern[i] else "#6EE7B7"};padding:.2rem .8rem;border-radius:99px;font-size:.85rem;font-weight:700;">{ic} {tl}</span></div><div style="color:#94A3B8;font-size:.9rem;line-height:1.6;">{exp}</div></div>',unsafe_allow_html=True)
    st.markdown('<div style="height:1rem"></div>',unsafe_allow_html=True)
    if st.button(tr("Go to Report →","← الانتقال للتقرير"),key="go_report"):
        st.session_state["page"]="report"; st.rerun()

# =============================================================
# PAGE 6: PERFORMANCE REPORT
# -------------------------------------------------------------
# Detailed performance breakdown showing:
#   - Overall score and awareness level (High/Moderate/Low)
#   - Detection rates: phishing vs legitimate separately
#   - Strengths: what the user did well
#   - Areas to improve: where they struggled
#   - Recommendations: 4 practical security tips
#   - Motivational closing message
#   - "Retake Training" button: resets ALL session state for
#     a completely fresh session.
# =============================================================
def page_report():
    is_arabic=st.session_state["language"]=="Arabic"; da='rtl' if is_arabic else 'ltr'; TOTAL=10
    def tp(e,a): return a if is_arabic else e
    st.markdown(f"""<style>#MainMenu,header,footer{{visibility:hidden;}}.stApp{{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}}.block-container{{max-width:900px;padding-top:2rem;}}.stButton>button{{min-height:52px !important;font-weight:800 !important;border-radius:12px !important;background:rgba(15,23,42,.88) !important;color:white !important;border:1px solid rgba(37,99,235,.55) !important;width:100% !important;}}.stButton>button:hover{{background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;border-color:#1EA7FF !important;}}</style>""",unsafe_allow_html=True)
    answers=st.session_state.get("assess_answers",{}); pattern=st.session_state.get("assess_pattern",[True]*5+[False]*5)
    role=st.session_state.get("role",""); lang=st.session_state.get("language","English")
    score=pc=lc=0; pt=sum(1 for p in pattern if p); lt=TOTAL-pt
    for i in range(TOTAL):
        ca2="phishing" if pattern[i] else "legitimate"
        if answers.get(i)==ca2:
            score+=1
            if pattern[i]: pc+=1
            else: lc+=1
    pct=int((score/TOTAL)*100); pp=int(pc/pt*100) if pt else 0; lp=int(lc/lt*100) if lt else 0
    aw="🥇" if pct>=80 else "🥈" if pct>=60 else "🥉"
    sc2="#10B981" if pct>=80 else "#F59E0B" if pct>=60 else "#EF4444"
    awl=tp("High","عالي") if pct>=80 else tp("Moderate","متوسط") if pct>=60 else tp("Needs Improvement","يحتاج تحسين")
    strengths=[]; areas=[]
    if pp>=70: strengths.append(tp("Good at identifying phishing emails","جيد في تحديد رسائل التصيد"))
    else: areas.append(tp("Review phishing indicators more carefully","راجع مؤشرات التصيد بعناية أكبر"))
    if lp>=70: strengths.append(tp("Good at identifying legitimate emails","جيد في تمييز الرسائل الشرعية"))
    else: areas.append(tp("Be cautious not to flag legitimate emails","احذر من تصنيف الرسائل الشرعية كتصيد"))
    recs=[tp("Always verify sender email addresses carefully","تحقق دائماً من عنوان البريد الإلكتروني للمرسل"),
          tp("Never click suspicious links — type URLs directly","لا تنقر على الروابط المشبوهة — اكتب العنوان مباشرة"),
          tp("Be cautious with unexpected attachments","كن حذراً مع المرفقات غير المتوقعة"),
          tp("When in doubt, contact IT or the sender directly","عند الشك، تواصل مع تقنية المعلومات أو المرسل مباشرة")]
    user_name  = st.session_state.get("user_name","")
    user_email = st.session_state.get("user_email","")
    name_line  = f'<div style="color:#F8FAFC;font-size:1rem;font-weight:700;margin-bottom:.2rem;">{html_lib.escape(user_name)}</div>' if user_name else ""
    email_line = f'<div style="color:#64748B;font-size:.8rem;margin-bottom:.3rem;">{html_lib.escape(user_email)}</div>' if user_email else ""
    st.markdown(f'<div style="text-align:center;padding:2rem;border:1px solid rgba(37,99,235,.45);border-radius:24px;background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));margin-bottom:1.5rem;direction:{da};">'
                f'<div style="font-size:1.6rem;font-weight:900;color:#F8FAFC;margin-bottom:.5rem;">📊 {tp("Your Performance Report","تقرير أدائك")}</div>'
                f'{name_line}{email_line}'
                f'<div style="color:#7DD3FC;font-size:.95rem;">{tp(f"Role: {role}","الدور: "+role)}</div></div>',
                unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    card = "border:1px solid rgba(37,99,235,.45);border-radius:16px;padding:1.5rem;text-align:center;background:rgba(2,6,23,.6);direction:{da};height:200px;display:flex;flex-direction:column;justify-content:center;align-items:center;box-sizing:border-box;"
    with c1: st.markdown(f'<div style="{card.format(da=da)}"><div style="color:#94A3B8;font-size:.85rem;margin-bottom:.4rem;">{tp("Overall Score","النتيجة الإجمالية")}</div><div style="font-size:2.5rem;font-weight:900;color:{sc2};">{score}/{TOTAL}</div><div style="color:{sc2};font-size:.9rem;">{pct}%</div></div>',unsafe_allow_html=True)
    with c2: st.markdown(f'<div style="{card.format(da=da)}"><div style="color:#94A3B8;font-size:.85rem;margin-bottom:.4rem;">{tp("Awareness Level","مستوى الوعي")}</div><div style="font-size:2.5rem;">{aw}</div><div style="color:{sc2};font-weight:700;font-size:.95rem;">{awl}</div></div>',unsafe_allow_html=True)
    with c3: st.markdown(f'<div style="{card.format(da=da)}"><div style="color:#94A3B8;font-size:.85rem;margin-bottom:.3rem;">{tp("Detection Rate","معدل الاكتشاف")}</div><div style="font-size:1rem;font-weight:700;color:#FCA5A5;margin-bottom:.3rem;">🚨 {tp("Phishing detected","التصيد المكتشف")}: {pp}%</div><div style="font-size:1rem;font-weight:700;color:#6EE7B7;">✅ {tp("Legitimate identified","الشرعية المميزة")}: {lp}%</div></div>',unsafe_allow_html=True)
    st.markdown('<div style="height:1rem"></div>',unsafe_allow_html=True)
    s1,s2=st.columns(2)
    with s1:
        si="".join([f'<div style="color:#6EE7B7;margin-bottom:.4rem;text-align:{"right" if is_arabic else "left"};">✅ {s}</div>' for s in strengths]) or f'<div style="color:#94A3B8;">{tp("Keep practicing","استمر في التدريب")}</div>'
        st.markdown(f'<div style="border:1px solid rgba(16,185,129,.35);border-radius:14px;padding:1.2rem;background:rgba(16,185,129,.05);direction:{da};text-align:{"right" if is_arabic else "left"};"><div style="font-weight:800;color:#F1F5F9;margin-bottom:.8rem;text-align:{"right" if is_arabic else "left"};">💪 {tp("Strengths","نقاط القوة")}</div>{si}</div>',unsafe_allow_html=True)
    with s2:
        ai="".join([f'<div style="color:#FCA5A5;margin-bottom:.4rem;text-align:{"right" if is_arabic else "left"};">⚠️ {a}</div>' for a in areas]) or f'<div style="color:#94A3B8;">{tp("Great work!","عمل رائع!")}</div>'
        st.markdown(f'<div style="border:1px solid rgba(239,68,68,.35);border-radius:14px;padding:1.2rem;background:rgba(239,68,68,.05);direction:{da};text-align:{"right" if is_arabic else "left"};"><div style="font-weight:800;color:#F1F5F9;margin-bottom:.8rem;text-align:{"right" if is_arabic else "left"};">📈 {tp("Areas to Improve","مجالات التحسين")}</div>{ai}</div>',unsafe_allow_html=True)
    st.markdown('<div style="height:1rem"></div>',unsafe_allow_html=True)
    ri="".join([f'<div style="color:#DCEBFF;margin-bottom:.5rem;text-align:{"right" if is_arabic else "left"};">📌 {r}</div>' for r in recs])
    st.markdown(f'<div style="border:1px solid rgba(37,99,235,.45);border-radius:14px;padding:1.2rem 1.5rem;background:rgba(2,6,23,.6);margin-bottom:1.5rem;direction:{da};text-align:{"right" if is_arabic else "left"};"><div style="font-weight:800;color:#F1F5F9;margin-bottom:.8rem;text-align:{"right" if is_arabic else "left"};">💡 {tp("Recommendations","التوصيات")}</div>{ri}</div>',unsafe_allow_html=True)
    st.markdown(f'<div style="text-align:center;padding:.8rem;border:1px solid rgba(37,99,235,.3);border-radius:10px;background:rgba(37,99,235,.08);color:#7DD3FC;margin-bottom:1.5rem;">⭐ {tp("Your awareness helps keep your organization safe","وعيك يساهم في حماية مؤسستك")}</div>',unsafe_allow_html=True)
    if st.button(tp("Retake Training","إعادة التدريب من البداية"),key="retake", use_container_width=True):
        for k in ["page","example_index","emails","assess_index","assess_emails","assess_answers","assess_pattern","cache_version","role","scenario_order","assess_scenario_order","difficulty","user_name","user_email","lang_explicitly_chosen","diff_explicitly_chosen"]:
            st.session_state.pop(k,None)
        st.rerun()

# =============================================================
# PAGE 0: LOGIN
# =============================================================
def page_login():
    is_arabic = st.session_state["language"] == "Arabic"
    da = 'rtl' if is_arabic else 'ltr'
    mode = st.session_state.get("login_mode","login")
    def tl(e,a): return a if is_arabic else e

    is_reg = mode == "register"
    page_title = tl("Create Account","إنشاء حساب") if is_reg else tl("Welcome Back","مرحباً بك")
    page_sub   = tl("Enter your details to get started","أدخل بياناتك للبدء") if is_reg else tl("Enter your details to personalise your experience","أدخل بياناتك لتخصيص تجربتك التدريبية")
    page_icon  = "✨" if is_reg else "👤"

    st.markdown(f"""<style>
#MainMenu,header,footer{{visibility:hidden;}}
.stApp{{background:radial-gradient(circle at top left,#0B2E68 0%,#020617 35%,#020617 100%);color:white;}}
.block-container{{max-width:480px;padding-top:4rem;}}
.stTextInput>div>div>input{{
    background:rgba(15,23,42,.88) !important;color:white !important;
    border:1px solid rgba(37,99,235,.55) !important;border-radius:12px !important;
    min-height:48px;direction:{da};font-size:.95rem !important;
}}
.stTextInput label{{color:#94A3B8 !important;font-size:.85rem !important;}}
.stButton>button {{
    width:100% !important;
    min-height:48px !important;
    max-height:48px !important;
    font-weight:700 !important;
    border-radius:12px !important;
    font-size:.9rem !important;
    padding:0 16px !important;
    line-height:48px !important;
}}
/* Back button */
div[data-testid="stHorizontalBlock"] > div:first-child .stButton>button {{
    background:rgba(15,23,42,.88) !important;
    color:#EAF4FF !important;
    border:1px solid rgba(37,99,235,.55) !important;
}}
/* Continue button - border only */
div[data-testid="stHorizontalBlock"] > div:last-child .stButton>button {{
    background:rgba(15,23,42,.88) !important;
    color:#EAF4FF !important;
    border:1px solid rgba(37,99,235,.55) !important;
}}
</style>""", unsafe_allow_html=True)

    st.markdown(f"""
<div style="text-align:center;padding:2.5rem 2rem 2rem;
            border:1px solid rgba(37,99,235,.45);border-radius:24px;
            background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));
            direction:{da};margin-bottom:1.5rem;">
  <div style="font-size:2.8rem;margin-bottom:.8rem;">{page_icon}</div>
  <div style="font-size:1.4rem;font-weight:900;color:#F8FAFC;margin-bottom:.4rem;">{page_title}</div>
  <div style="font-size:.9rem;color:#94A3B8;">{page_sub}</div>
</div>""", unsafe_allow_html=True)

    if is_arabic:
        st.markdown(f'''<style>
.stTextInput label{{direction:rtl;text-align:right;display:block;}}
.stTextInput input{{text-align:right;direction:rtl;}}
</style>''', unsafe_allow_html=True)

    user_name  = st.text_input(
        tl("Full name","الاسم الكامل"),
        value=st.session_state.get("user_name",""),
        placeholder=tl("e.g. Dr. Sarah Al-Mutairi","مثال: د. سارة المطيري")
    )
    user_email = st.text_input(
        tl("Email address","البريد الإلكتروني"),
        value=st.session_state.get("user_email",""),
        placeholder="name@hospital.org"
    )

    st.markdown('<div style="height:.8rem;"></div>', unsafe_allow_html=True)

    st.markdown("""<style>
/* Force both login page buttons to exact same height */
div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button {
    height:48px !important;
    min-height:48px !important;
    max-height:48px !important;
    padding-top:0 !important;
    padding-bottom:0 !important;
    line-height:48px !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    box-sizing:border-box !important;
}
</style>""", unsafe_allow_html=True)

    c1, c2 = st.columns([1,1])
    with c1:
        if st.button(tl("← Back","← رجوع"), key="login_back", use_container_width=True):
            st.session_state["page"] = "home"
            st.rerun()
    with c2:
        if st.button(tl("Continue","متابعة"), key="login_continue", use_container_width=True):
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
            if not user_name.strip():
                st.warning(tl("⚠️ Please enter your full name.","⚠️ يرجى إدخال اسمك الكامل"))
            elif not user_email.strip():
                st.warning(tl("⚠️ Please enter your email address.","⚠️ يرجى إدخال بريدك الإلكتروني"))
            elif not email_pattern.match(user_email.strip()):
                st.warning(tl("⚠️ Please enter a valid email address (e.g. name@hospital.org).",
                              "⚠️ يرجى إدخال بريد إلكتروني صحيح مثل: name@hospital.org"))
            else:
                st.session_state["user_name"]  = user_name.strip()
                st.session_state["user_email"] = user_email.strip()
                st.session_state["page"] = "home"
                st.rerun()

# ── ROUTER ─────────────────────────────────────────────────
pg=st.session_state.get("page","home")
{"home":page_home,"login":page_login,"learning":page_learning,"complete":page_complete,
 "assessment":page_assessment,"results":page_results,"report":page_report}.get(pg,page_home)()
