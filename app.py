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

import streamlit as st
import json
import requests
import os
import re
import html as html_lib
import random

st.set_page_config(
    page_title="AI Phishing Awareness",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

for k, v in [("language","English"),("page","home"),("role",""),
              ("example_index",0),("emails",{}),("difficulty","medium"),
              ("user_name",""),("user_email",""),("ai_provider","groq")]:
    if k not in st.session_state:
        st.session_state[k] = v

_nav = st.query_params.get("nav", "")
if _nav in ("login", "register"):
    st.session_state["login_mode"] = _nav
    st.session_state["page"] = "login"
    _lang = st.query_params.get("lang", "")
    if _lang in ("Arabic", "English"):
        st.session_state["language"] = _lang
    st.query_params.clear()

def set_language(lang):
    st.session_state["language"] = lang
    st.session_state["lang_explicitly_chosen"] = True

def t(en, ar):
    return ar if st.session_state["language"] == "Arabic" else en

def go_to_learning(role):
    st.session_state["role"]          = role
    st.session_state["page"]          = "learning"
    st.session_state["example_index"] = 0
    st.session_state["emails"]        = {}

def clean_foreign_only(text):
    if not text: return text
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\uac00-\ud7af\u1100-\u11ff]', '', text)
    text = re.sub(r'[\u0400-\u04ff]', '', text)
    text = re.sub(r'[\u0100-\u017f]', '', text)
    text = re.sub(r'[\u1ea0-\u1ef9]', '', text)
    text = re.sub(r'[\u0900-\u097f]', '', text)
    text = re.sub(r'[\u0e00-\u0e7f]', '', text)
    text = re.sub(r'[\u10a0-\u10ff\u0530-\u058f\u05d0-\u05ff]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'  +', ' ', text).strip()
    return text

_ALLOWED_LATIN_RE = re.compile(
    r'^(https?://[^\s]+|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}|\.(?:pdf|xlsx|docx|txt|csv|zip|exe)|[0-9]+)$',
    re.IGNORECASE
)

def remove_foreign_latin_words(text):
    if not text: return text
    arabic_chars = len(re.findall(r'[\u0600-\u06ff]', text))
    total_chars  = len(re.sub(r'\s', '', text))
    if total_chars == 0 or arabic_chars / total_chars < 0.25:
        return text
    def keep_token(tok):
        if _ALLOWED_LATIN_RE.match(tok): return tok
        if re.search(r'[\u0600-\u06ff]', tok): return tok
        if re.match(r'^[\u060c\u061b\u061f،؛؟!.,;:\-\u2013\u2014()\[\]{}\'"]+$', tok): return tok
        if re.match(r'^[a-zA-Z\u00c0-\u024f]+$', tok): return ''
        return tok
    tokens  = re.split(r'(\s+)', text)
    cleaned = ''.join(keep_token(t) for t in tokens)
    cleaned = re.sub(r'[a-zA-Z]{1,}[-_](?=[\u0600-\u06ff])', '', cleaned)
    cleaned = re.sub(r'(?<=[\u0600-\u06ff])[-_]?[a-zA-Z]{1,}', '', cleaned)
    cleaned = re.sub(r'[a-zA-Z]{1,}(?=[\u0600-\u06ff])', '', cleaned)
    cleaned = re.sub(r'  +', ' ', cleaned).strip()
    cleaned = re.sub(r'\s([،؛،,.;:])', r'\1', cleaned)
    return cleaned

def clean_email_field(addr):
    if not addr: return addr
    addr = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0400-\u04ff\u0100-\u017f]', '', addr)
    addr = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', addr)
    return addr.strip()

def extract_to_email(to_val):
    if not to_val: return 'employee@hospital.org'
    m = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', to_val)
    return m.group(0) if m else 'employee@hospital.org'

def fix_json_newlines(s):
    result, in_string, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i-1] != '\\'):
            in_string = not in_string
        if in_string and c == '\n':   result.append('\\n')
        elif in_string and c == '\r': result.append('\\r')
        elif in_string and c == '\t': result.append('\\t')
        else:                         result.append(c)
        i += 1
    return ''.join(result)

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
    "Other": (
        "a general hospital employee in Saudi Arabia",
        "any hospital department — clinical, administrative, or technical",
        "other"
    ),
    "أخرى": (
        "موظف عام في مستشفى سعودي",
        "أي قسم في المستشفى — سريري أو إداري أو تقني",
        "other"
    ),
}

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
    "other": [
        "s.khalid.alharbi@hospital.org",
        "s.sara.alqahtani@hospital.org",
        "s.faisal.alzahrani@hospital.org",
        "s.nora.alotaibi@hospital.org",
        "s.ahmed.alshamri@hospital.org",
        "s.hessa.aldosari@hospital.org",
    ],
}

def get_recipient(role, index, language):
    role_info = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    _, _, role_type = role_info
    # للـ Other: نختار pool حسب نوع السيناريو (Admin→IT→Clinical بالتناوب)
    if role_type == "other":
        # السيناريوهات: 0=Admin, 1=IT, 2=Clinical, 3=Admin, 4=IT, 5=Clinical
        other_pool_map = {0: "admin", 1: "it", 2: "clinical",
                          3: "admin", 4: "it",  5: "clinical"}
        pool_type = other_pool_map.get(index % 6, "other")
        pool = EN_NAMES.get(pool_type, EN_NAMES["other"])
    else:
        pool = EN_NAMES.get(role_type, EN_NAMES["clinical"])
    return pool[index % len(pool)]

PHISHING_SCENARIOS = [
    {"key":"link",    "en_type":"Credential Harvesting Link",              "ar_type":"رابط سرقة بيانات الدخول",             "has_attachment":False, "attachment_ext":"", "has_link":True},
    {"key":"pdf",     "en_type":"Malicious PDF Attachment",                "ar_type":"مرفق PDF خبيث",                        "has_attachment":True,  "attachment_ext":".pdf", "has_link":False},
    {"key":"xlsx",    "en_type":"Malicious Excel Attachment",              "ar_type":"مرفق Excel خبيث",                     "has_attachment":True,  "attachment_ext":".xlsx","has_link":False},
    {"key":"docx",    "en_type":"Malicious Word Document - Enable Macros", "ar_type":"مرفق Word مزيف - تفعيل الماكرو",      "has_attachment":True,  "attachment_ext":".docx","has_link":False},
    {"key":"hr_link", "en_type":"Fake HR Announcement with Link",          "ar_type":"إعلان موارد بشرية مزيف برابط",        "has_attachment":False, "attachment_ext":"", "has_link":True},
    {"key":"exec",    "en_type":"Executive Impersonation - Urgent Request","ar_type":"انتحال هوية المدير - طلب عاجل",       "has_attachment":False, "attachment_ext":"", "has_link":False},
]

def get_shuffled_scenario_order():
    if "scenario_order" not in st.session_state:
        order = list(range(len(PHISHING_SCENARIOS)))
        random.shuffle(order)
        st.session_state["scenario_order"] = order
    return st.session_state["scenario_order"]

# =============================================================
# =============================================================
# FIX 7: FORCED SCENARIO DIVERSITY PER INDEX
# كل مثال له سيناريو محدد مسبقاً — يمنع التكرار نهائياً
# =============================================================
FORCED_SCENARIOS = {
    "admin": [
        {"en": "SCENARIO: Fake supplier invoice — impersonate a medical equipment supplier requesting urgent payment. IMPORTANT: vary every time — change supplier name (MedSupply Co./Al-Rashid Medical/Gulf Medical Supplies), equipment type (surgical instruments/radiology equipment/lab supplies/ICU monitors), invoice amount (SAR 75,000-200,000), and PDF filename each time.",
         "ar": "السيناريو: فاتورة مورد مزيفة — انتحل هوية مورد معدات طبية يطلب دفع 150,000 ريال بشكل عاجل. استخدم مرفق PDF باسم invoice.pdf."},
        {"en": "SCENARIO: Fake health insurance portal — re-verify coverage details via suspicious link. IMPORTANT: vary the insurance provider name (Tawuniya/Bupa Arabia/MedGulf/AXA), specific claim type (annual renewal/coverage update/reimbursement), and suspicious link URL each time.",
         "ar": "السيناريو: بوابة تأمين صحي مزيفة — ادّعِ أن نظام تأمين الموظفين يحتاج تحديث بيانات التغطية عبر رابط مشبوه. بدون مرفق."},
        {"en": "SCENARIO: Fake payroll system — update bank account details to avoid delayed salary. IMPORTANT: vary the urgency deadline (end of month/before 15th/within 48 hours), bank detail type requested (IBAN/account number/branch code), and sender name each time.",
         "ar": "السيناريو: نظام رواتب مزيف — ادّعِ أن نظام صرف الرواتب يحتاج تحديث بيانات الحساب البنكي لتجنب تأخر الراتب. بدون مرفق."},
        {"en": "SCENARIO: CEO/director impersonation — impersonate the hospital CEO urgently requesting the admin manager to process a financial transfer or share sensitive payroll data immediately. Pure social engineering, NO link, NO attachment.",
         "ar": "السيناريو: انتحال هوية المدير التنفيذي — تظاهر بأنك المدير التنفيذي وتطلب من المدير الإداري تحويل مالي عاجل أو مشاركة بيانات الرواتب. هندسة اجتماعية فقط."},
        {"en": "SCENARIO: Fake patient appointment system migration — claim the appointment booking system is being upgraded and staff must verify login credentials through a suspicious link. NO attachment.",
         "ar": "السيناريو: ترحيل مزيف لنظام حجز المواعيد — ادّعِ أن النظام يُرقَّى ويطلب التحقق من بيانات الدخول عبر رابط مشبوه."},
        {"en": "SCENARIO: Fake medical procurement portal — impersonate procurement system admin claiming a critical supplier contract expires this week and must be renewed via a suspicious link. NO attachment.",
         "ar": "السيناريو: بوابة مشتريات طبية مزيفة — انتحل هوية مسؤول المشتريات وادّعِ أن عقد مورد حيوي ينتهي هذا الأسبوع ويجب تجديده عبر رابط مشبوه."},
    ],
    "clinical": [
        {"en": "SCENARIO: Fake EMR system credential harvest — claim the hospital EMR system requires urgent re-verification of login credentials through a suspicious link. IMPORTANT: vary the details every time — change the sender name, the specific system name (EMR/Patient Portal/Clinical System), the suspicious link URL, and the spelling mistake used (choose ONE from: credintials/urgant/acces/imediatly — never reuse recived or procedue).",
         "ar": "السيناريو: سرقة بيانات نظام السجلات الطبية. مهم: غيّر التفاصيل في كل مرة — اسم المرسل، اسم النظام، الرابط المشبوه، والخطأ الإملائي (اختر من: تسجيـل/عاجلة/وصلت — لا تكرر نفس الخطأ)."},
        {"en": "SCENARIO: Malicious patient data PDF — send a fake urgent patient lab results update as a PDF attachment. IMPORTANT: vary every time — change the patient department (ICU/oncology/cardiology/radiology/pediatrics), the PDF filename, the doctor name, and the spelling mistake (choose ONE from: recieved/attachement/critcal/paicent — never repeat the same error).",
         "ar": "السيناريو: مرفق PDF خبيث لنتائج مختبر. مهم: غيّر القسم (ICU/أورام/قلب/أطفال) واسم الملف والطبيب والخطأ الإملائي في كل مرة."},
        {"en": "SCENARIO: Fake MOH clinical protocol — impersonate MOH sending urgent clinical guidance. IMPORTANT: vary the protocol topic every time (infection control/COVID-19 update/vaccination campaign/MRSA alert/antimicrobial resistance) and use a different suspicious link URL each time.",
         "ar": "السيناريو: بروتوكول سريري مزيف من وزارة الصحة. مهم: غيّر موضوع البروتوكول (مكافحة العدوى/كوفيد/تطعيمات/MRSA) والرابط في كل مرة."},
        {"en": "SCENARIO: Medical director impersonation — impersonate the medical director urgently requesting patient data or system access. IMPORTANT: vary the director name, department (Surgery/Internal Medicine/Emergency/ICU), and specific request each time. Pure social engineering — no link needed.",
         "ar": "السيناريو: انتحال هوية المدير الطبي. مهم: غيّر اسم المدير والتخصص (جراحة/طوارئ/باطنية) والطلب المحدد في كل مرة."},
        {"en": "SCENARIO: Fake clinical staff schedule Excel — send a malicious Excel file with updated duty roster. IMPORTANT: vary the time period (next month/Ramadan schedule/Q2 roster/holiday coverage), Excel filename, and head nurse name each time.",
         "ar": "السيناريو: جدول مناوبات مزيف كمرفق Excel. مهم: غيّر الفترة الزمنية (رمضان/الربع الثاني/الإجازات) واسم الملف في كل مرة."},
        {"en": "SCENARIO: Fake pharmacy or medical system update — claim the pharmacy dispensing system or drug management portal requires urgent login verification. IMPORTANT: vary the system name (Pharmacy System/Drug Dispensing Portal/Medication Management/Blood Bank System) and suspicious link each time.",
         "ar": "السيناريو: تحديث مزيف لنظام الصيدلية أو بنك الدم. مهم: غيّر اسم النظام (صيدلية/بنك الدم/إدارة الدواء) والرابط في كل مرة."},
    ],
    "it": [
        {"en": "SCENARIO: Fake VPN credential update — claim the hospital VPN gateway requires urgent re-authentication. IMPORTANT: vary the VPN system name (Cisco AnyConnect/FortiClient/Pulse Secure), the suspicious portal URL, and the urgency reason each time.", "ar": "السيناريو: تحديث مزيف لبيانات الـ VPN. مهم: غيّر اسم النظام (Cisco/FortiClient) والرابط والسبب في كل مرة."},
        {"en": "SCENARIO: Fake SSL certificate expiry — claim the hospital website or portal SSL certificate has expired. IMPORTANT: vary the affected system (hospital website/patient portal/EMR login/staff intranet), renewal deadline, and suspicious link each time.", "ar": "السيناريو: تنبيه مزيف بانتهاء شهادة SSL. مهم: غيّر النظام المتأثر (موقع/بوابة/EMR) والموعد والرابط في كل مرة."},
        {"en": "SCENARIO: Fake IT helpdesk remote access — impersonate IT helpdesk claiming a critical server issue requires remote access credentials immediately.", "ar": "السيناريو: مكتب مساعدة مزيف يطلب بيانات الوصول عن بُعد لحل مشكلة خادم حرجة."},
        {"en": "SCENARIO: CIO impersonation — impersonate the Chief Information Officer urgently requesting server admin credentials or asking to disable security settings.", "ar": "السيناريو: انتحال هوية مدير تقنية المعلومات يطلب بيانات الخادم أو تعطيل إعدادات الأمان."},
        {"en": "SCENARIO: Fake software license renewal — claim a critical hospital software license is expiring in 24 hours and requires immediate renewal via a suspicious portal.", "ar": "السيناريو: تجديد مزيف لترخيص برنامج حيوي ينتهي خلال 24 ساعة."},
        {"en": "SCENARIO: Fake firewall policy update — send a malicious Word document claiming to contain a new mandatory firewall security policy requiring macro enablement.", "ar": "السيناريو: سياسة جدار ناري مزيفة — مستند Word يطلب تفعيل الماكرو."},
    ],
    "other": [
        # مزيج متنوع حقيقي — ADMIN first, then IT, then CLINICAL, rotating
        {"en": "SCENARIO (ADMIN): Fake payroll/HR system — salary payment on hold until employee updates bank account details (IBAN/account number). Sender pretends to be HR department. IMPORTANT: vary bank detail type, urgency deadline (end of month/within 48h/before 15th), HR manager name each time. NO attachment. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (إداري): نظام رواتب مزيف — ادّعِ أن صرف راتب الموظف موقوف حتى يحدّث بيانات حسابه البنكي. المرسل يتظاهر بأنه قسم الموارد البشرية. غيّر نوع البيانات البنكية والموعد النهائي واسم مدير الموارد البشرية في كل مرة. الهدف: موظف عام."},
        {"en": "SCENARIO (IT): Fake hospital network/VPN security alert — claim employee's network account has been flagged for suspicious activity and must re-verify credentials immediately via suspicious portal link. IMPORTANT: vary the alert type (account lockout/suspicious login/security breach), suspicious portal URL, and ONE spelling mistake each time. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (تقني): تنبيه أمني مزيف للشبكة — ادّعِ أن حساب الموظف على شبكة المستشفى تم تعليقه بسبب نشاط مشبوه ويجب إعادة التحقق من بياناته فوراً عبر رابط. غيّر نوع التنبيه والرابط والخطأ الإملائي في كل مرة. الهدف: موظف عام."},
        {"en": "SCENARIO (CLINICAL): Fake MOH urgent health directive — impersonate Ministry of Health sending a critical infection control or vaccination update requiring all hospital staff to confirm compliance by clicking a suspicious link. IMPORTANT: vary the directive topic (MRSA/COVID/vaccination campaign/antimicrobial resistance), MOH official name, and suspicious link each time. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (سريري): توجيه صحي عاجل مزيف من وزارة الصحة — تظاهر بأن الوزارة ترسل تحديثاً حرجاً لمكافحة العدوى أو التطعيمات يتطلب من جميع موظفي المستشفى تأكيد الامتثال عبر رابط مشبوه. غيّر موضوع التوجيه واسم المسؤول والرابط في كل مرة. الهدف: موظف عام."},
        {"en": "SCENARIO (ADMIN): Fake medical equipment supplier invoice — impersonate a supplier (MedSupply Co./Gulf Medical/Al-Rashid Medical) claiming an urgent invoice of SAR 75,000–150,000 must be approved via a suspicious link or PDF. IMPORTANT: vary supplier name, equipment type (surgical/lab/radiology/ICU), invoice amount, and PDF filename each time. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (إداري): فاتورة مورد معدات طبية مزيفة — انتحل هوية مورد وادّعِ أن فاتورة عاجلة بقيمة 75,000-150,000 ريال يجب الموافقة عليها. غيّر اسم المورد ونوع المعدات والمبلغ واسم الملف في كل مرة. الهدف: موظف عام."},
        {"en": "SCENARIO (IT): Fake IT helpdesk urgent alert — impersonate hospital IT helpdesk claiming employee's computer has a critical virus/malware and must click a link immediately to run a security scan and enter credentials to verify identity. IMPORTANT: vary the malware type, suspicious scan link URL, and ONE spelling mistake each time. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (تقني): تنبيه مزيف من مكتب المساعدة — انتحل هوية قسم تقنية المعلومات وادّعِ أن جهاز الموظف مصاب بفيروس حرج ويجب النقر على رابط لإجراء فحص أمني وإدخال البيانات. غيّر نوع الفيروس والرابط والخطأ الإملائي في كل مرة. الهدف: موظف عام."},
        {"en": "SCENARIO (CLINICAL): Fake hospital EMR/staff portal credential harvest — claim the hospital staff portal or scheduling system requires urgent re-verification of login credentials due to a system migration. IMPORTANT: vary system name (Staff Portal/Scheduling System/Patient System/Hospital Portal), suspicious link URL, and ONE spelling mistake (credintials OR urgant OR acces OR imediatly) each time. Target: general hospital employee — use generic greeting 'Dear Staff'.",
         "ar": "السيناريو (سريري): سرقة بيانات بوابة الموظفين — ادّعِ أن بوابة الموظفين أو نظام الجداول يحتاج إعادة التحقق من بيانات الدخول بسبب ترحيل النظام. غيّر اسم النظام والرابط والخطأ الإملائي في كل مرة. الهدف: موظف عام."},
    ],
}

# FIX 1: build_prompt — upgraded to llama-3.3-70b-versatile
# and enhanced difficulty rules with more detail
# =============================================================
def build_prompt(role, index, language):
    is_ar      = (language == "Arabic")
    difficulty = st.session_state.get("difficulty", "medium")
    role_info  = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    role_desc, role_ctx, role_type = role_info
    seed = st.session_state.get("cache_version", 13)
    import time
    session_seed = abs(hash(str(seed) + str(index) + str(time.time()))) % 99999

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
            "A general hospital employee in Saudi Arabia (could be any department).",
            "Any hospital area: clinical (patient records, EMR), administrative (billing, insurance, payroll), or IT (network, systems, helpdesk).",
            "Use the MANDATORY SCENARIO provided — it rotates across all three role types for maximum variety."
        ),
    }
    r_desc, r_ctx, r_guidance = role_guidance.get(role_type, role_guidance["other"])

    # FIX 3: Enhanced difficulty rules — more detailed for both languages
    if is_ar:
        diff_rules = {
            "easy": (
                "مستوى مبتدئ — العلامات يجب أن تكون واضحة جداً ولا تخطئها:\n"
                "- نطاق مزيف واضح تماماً (مثل hosp1tal-updates.xyz أو hospital.totally-fake.net أو secur3-login.com)\n"
                "- خطأين إملائيين واضحين على الأقل في نص الرسالة (مثل: 'تسجيل الدخوول' أو 'عزيزي الموظفف')\n"
                "- إلحاح مبالغ فيه بعبارات تحذيرية كبيرة (تصرف الآن! سيتم إغلاق حسابك خلال ساعة! موعد نهائي اليوم!)\n"
                "- تحية عامة فقط: 'عزيزي الموظف' أو 'عزيزي المستخدم' — ممنوع استخدام الاسم أو المسمى الوظيفي\n"
                "- طلب صريح ومشبوه جداً (شارك كلمة المرور، أدخل بياناتك الكاملة، أرسل رقم الهوية)\n"
                "- عنوان المرسل واضح الزيف (مثل: noreply@hospital-secure.xyz)"
            ),
            "medium": (
                "مستوى متوسط — صعوبة معتدلة، بعض العلامات واضحة وبعضها يحتاج تمعّناً:\n"
                "- نطاق مشبوه نسبياً لكن ليس واضح الزيف تماماً (مثل hospital-hr-portal.net أو moh-notifications.com)\n"
                "- أسلوب شبه مهني مع علامة تحذيرية واحدة أو اثنتين في الصياغة\n"
                "- خطأ إملائي واحد بسيط أو جملة غير طبيعية في السياق\n"
                "- إلحاح معتدل ('يرجى الرد بنهاية الأسبوع' أو 'يجب التحديث قبل يوم الاثنين')\n"
                "- تحية شبه شخصية (اللقب الوظيفي صح لكن الاسم أحياناً خاطئ أو عام)\n"
                "- الطلب غير عادي لكن ليس مستحيلاً في بيئة العمل"
            ),
            "hard": (
                "مستوى متقدم — العلامات خفية جداً، الرسالة تبدو حقيقية تقريباً:\n"
                "- نطاق يشبه الحقيقي مع تغيير بسيط جداً لا يُلاحَظ بسهولة (مثل hosp1tal.org أو hospital-sa.net أو moh.gov-sa.com)\n"
                "- لغة عربية فصحى مهنية سليمة تماماً، صفر أخطاء إملائية أو نحوية\n"
                "- إلحاح خفيف ومهني جداً ('نرجو الاطلاع قبل نهاية يوم العمل' أو 'للحفاظ على أمان حسابك')\n"
                "- تحية بالاسم الكامل والمسمى الوظيفي الدقيق\n"
                "- علامة تحذيرية واحدة فقط وخفية للغاية — كل شيء آخر يبدو حقيقياً تماماً\n"
                "- المحتوى ذو صلة مباشرة بعمل المستلم ويوحي بمعرفة داخلية"
            ),
        }
    else:
        diff_rules = {
            "easy": (
                "BEGINNER difficulty — red flags must be VERY obvious and easy to spot:\n"
                "- Clearly fake domain (e.g. hosp1tal-updates.xyz, hospital.totally-fake.net, secur3-login.com)\n"
                "- At least 2 obvious spelling/grammar mistakes in the body text\n"
                "- Aggressive ALL-CAPS urgency with alarming language (ACT NOW! YOUR ACCOUNT WILL BE CLOSED! DEADLINE TODAY!)\n"
                "- Generic greeting only: 'Dear Staff' or 'Dear User' — never use recipient's name or job title\n"
                "- Blatantly suspicious request (share your password, enter full credentials, send your ID number)\n"
                "- Sender address obviously fake (e.g. noreply@hospital-secure.xyz)"
            ),
            "medium": (
                "INTERMEDIATE difficulty — some flags obvious, some require careful reading:\n"
                "- Slightly suspicious domain that looks almost real (e.g. hospital-hr-portal.net, moh-notifications.com)\n"
                "- Mostly professional tone with 1-2 red flags in wording\n"
                "- One minor spelling error or awkward sentence that feels slightly off\n"
                "- Moderate urgency with a deadline ('Please respond by end of week' or 'Update required before Monday')\n"
                "- Semi-personal greeting — correct job title but name is generic or slightly wrong\n"
                "- Request is unusual but not impossible in a workplace context"
            ),
            "hard": (
                "ADVANCED difficulty — red flags extremely subtle, email looks almost completely legitimate:\n"
                "- Nearly real domain with only one tiny character change (e.g. hosp1tal.org, hospital-sa.net, moh.gov-sa.com)\n"
                "- Perfect professional English, zero spelling or grammar errors\n"
                "- Subtle, polite urgency only ('Kindly review before end of business day' or 'To keep your account secure')\n"
                "- Personalised greeting with full name and exact job title\n"
                "- Only ONE subtle red flag — everything else looks completely legitimate\n"
                "- Content directly relevant to recipient's work, implying insider knowledge"
            ),
        }

    diff_rule = diff_rules.get(difficulty, diff_rules["medium"])

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

    # FIX 7: Get forced scenario for this index
    forced = FORCED_SCENARIOS.get(role_type, FORCED_SCENARIOS["admin"])
    forced_scenario = forced[index % len(forced)]
    scenario_instruction = forced_scenario["ar"] if is_ar else forced_scenario["en"]

    return f"""You are a cybersecurity expert creating phishing awareness training for Saudi healthcare.

TRAINING EXAMPLE #{index + 1} of 6 | Variety seed: {session_seed}

━━━ TARGET ━━━
Role: {r_desc}
Context: {r_ctx}

━━━ YOUR TASK — MANDATORY SCENARIO ━━━
You MUST generate this EXACT scenario type — do NOT substitute or change it:
{scenario_instruction}

This scenario is NON-NEGOTIABLE. Generate the email body, subject, and sender to match this specific scenario exactly.

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
CRITICAL: Output ONLY the JSON object below. No text before it, no text after it, no explanations, no notes, no "Sincerely", no extra sentences. The response must start with {{ and end with }}.
{{"email_type":"attack type name","from":"{from_ex}","to":"employee@hospital.org","subject":"subject line","attachment":"filename or empty","body":"{body_ex}","suspicious_text":"most suspicious phrase","suspicious_link":"url or empty","indicators":[{{"number":1,"title":"{ind_t_ex}","description":"{ind_d_ex}"}},{{"number":2,"title":"{ind_t_ex}","description":"{ind_d_ex}"}},{{"number":3,"title":"{ind_t_ex}","description":"{ind_d_ex}"}}],"why_risky":"why dangerous for this role","learning_tip":"practical tip for this role"}}"""

# =============================================================
# FIX 2 + FIX 3: build_assess_prompt — tokens raised to 1200,
# difficulty rules expanded to match build_prompt detail level
# =============================================================
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
            "a general hospital employee in Saudi Arabia (any department)",
            "clinical areas (EMR, patient records), administrative tasks (billing, insurance, payroll), or IT systems (network, helpdesk)"
        ),
    }
    r_desc, r_ctx = role_guidance.get(role_type, role_guidance["other"])

    # FIX 3+10: diff_rules مطابقة للتعلم — مخصصة لكل دور
    # ══════════════════════════════════════════════════════
    # diff_rules — مطابقة لقسم التعلم تماماً
    # مخصصة لكل دور في كل مستوى (AR + EN)
    # ══════════════════════════════════════════════════════
    role_domains = {
        "admin":    {"easy": "hosp1tal-hr.xyz / moh-pay.net",
                     "medium": "hospital-hr-portal.net / moh-billing.com",
                     "hard":   "moh.gov-sa.com / hosp1tal.org"},
        "clinical": {"easy": "emr-secure.xyz / medrecords.net",
                     "medium": "emr-health-sa.net / moh-clinic.com",
                     "hard":   "hosp1tal-clinic.org / moh.gov.sa-health.com"},
        "it":       {"easy": "vpn-update.xyz / sysadmin-alert.net",
                     "medium": "vpn-hospital-sa.net / itsupport-moh.com",
                     "hard":   "hosp1tal-it.org / moh-itsupport.sa.com"},
        "other":    {"easy": "hospital-alert.xyz / hosp1tal-secure.net",
                     "medium": "hospital-portal-sa.net / moh-staff.com",
                     "hard":   "hosp1tal.org / moh.gov-sa.com"},
    }
    rd = role_domains.get(role_type, role_domains["admin"])

    if is_ar:
        diff_rules = {
            "easy": (
                "مستوى مبتدئ — العلامات يجب أن تكون واضحة جداً ولا تخطئها:\n"
                f"- نطاق مزيف واضح تماماً مناسب للدور (مثل {rd['easy']})\n"
                "- خطأين إملائيين واضحين على الأقل في نص الرسالة\n"
                "- إلحاح مبالغ فيه بعبارات كبيرة (تصرف الآن! حسابك سيُغلق! موعد نهائي اليوم!)\n"
                "- تحية عامة فقط: 'عزيزي الموظف' أو 'عزيزي الفريق' — ممنوع الاسم\n"
                "- طلب صريح ومشبوه جداً (شارك كلمة المرور، أدخل بياناتك كاملة)\n"
                "- عنوان المرسل واضح الزيف"
            ),
            "medium": (
                "مستوى متوسط — صعوبة معتدلة، بعض العلامات تحتاج تمعّناً:\n"
                f"- نطاق مشبوه نسبياً مناسب للدور (مثل {rd['medium']})\n"
                "- أسلوب شبه مهني مع علامة تحذيرية واحدة أو اثنتين فقط\n"
                "- خطأ إملائي واحد بسيط فقط في النص\n"
                "- إلحاح معتدل ('يرجى الرد بنهاية الأسبوع') — ممنوع ALL CAPS\n"
                "- تحية شبه شخصية (اللقب صح لكن الاسم أحياناً عام أو خاطئ)\n"
                "- الطلب غير عادي لكن ليس مستحيلاً في بيئة العمل"
            ),
            "hard": (
                "مستوى متقدم — العلامات خفية جداً، الرسالة تبدو حقيقية تقريباً:\n"
                f"- نطاق يشبه الحقيقي مع تغيير بسيط جداً مناسب للدور (مثل {rd['hard']})\n"
                "- لغة عربية فصحى مهنية سليمة تماماً، صفر أخطاء إملائية\n"
                "- صفر ALL CAPS — أسلوب مهني هادئ تماماً\n"
                "- إلحاح خفيف ومهني فقط ('نرجو الاطلاع قبل نهاية يوم العمل')\n"
                "- تحية بالاسم الكامل والمسمى الوظيفي الدقيق\n"
                "- علامة تحذيرية واحدة فقط وخفية — كل شيء آخر يبدو حقيقياً تماماً"
            ),
        }
    else:
        diff_rules = {
            "easy": (
                "BEGINNER difficulty — red flags VERY obvious and easy to spot:\n"
                f"- Clearly fake domain suited to the role (e.g. {rd['easy']})\n"
                "- At least 2 obvious spelling/grammar mistakes in the body\n"
                "- Aggressive ALL-CAPS urgency (ACT NOW! DEADLINE TODAY! ACCOUNT WILL BE CLOSED!)\n"
                "- Generic greeting only: 'Dear Staff' or 'Dear Team' — NEVER use name\n"
                "- Blatantly suspicious request (share password, enter full credentials)\n"
                "- Sender address obviously fake"
            ),
            "medium": (
                "INTERMEDIATE difficulty — some flags obvious, some need careful reading:\n"
                f"- Slightly suspicious domain suited to role (e.g. {rd['medium']})\n"
                "- Mostly professional tone with 1-2 red flags only\n"
                "- EXACTLY 1 minor spelling mistake — just one subtle error\n"
                "- Moderate urgency only: 'Please respond by end of week' — NO ALL-CAPS\n"
                "- Semi-personal greeting matching role (correct title, name slightly off)\n"
                "- Request unusual but not impossible in workplace context"
            ),
            "hard": (
                "ADVANCED difficulty — red flags extremely subtle, email looks almost completely real:\n"
                f"- Nearly real domain with ONE tiny change suited to role (e.g. {rd['hard']})\n"
                "- ZERO spelling or grammar mistakes — perfect professional language\n"
                "- ZERO ALL-CAPS — completely normal professional tone throughout\n"
                "- Subtle polite urgency only: 'Kindly review before end of business day'\n"
                "- Full name + exact job title matching the role in greeting\n"
                "- ONLY ONE subtle red flag (the domain) — everything else perfectly legitimate"
            ),
        }
    diff_rule = diff_rules.get(difficulty, diff_rules["medium"])

    # تعريف task_p و task_l — يُستخدمان كـ "Additional context" في الـ prompt
    if is_ar:
        task_p = f"ولّد رسالة تصيد إلكتروني واقعية تستهدف {r_desc}. اتبع السيناريو الإجباري أعلاه بدقة."
        task_l = f"ولّد بريد إلكتروني شرعي وطبيعي من بيئة عمل {r_desc}. استخدم نطاق رسمي (@hospital.org أو @moh.gov.sa). لا علامات تصيد إطلاقاً."
    else:
        task_p = f"Generate a realistic phishing email targeting {r_desc}. Follow the MANDATORY SCENARIO above exactly."
        task_l = f"Generate a realistic legitimate workplace email for {r_desc}. Use official domain (@hospital.org or @moh.gov.sa). Zero suspicious elements — must look completely normal."

    task = task_p if is_phishing else task_l

    # FIX 7b: Forced scenario for assessment based on index + is_phishing
    # ══════════════════════════════════════════════
    # ASSESSMENT SCENARIOS — مخصصة لكل دور مع تنويع
    # ══════════════════════════════════════════════
    assess_scenarios = {
        "admin": {
            True: [
                "MANDATORY PHISHING — Admin/Billing: Fake supplier invoice for medical equipment. Vary: supplier name (MedSupply Co./Gulf Medical/Al-Rashid Medical), equipment type (surgical instruments/lab supplies/radiology equipment/ICU monitors), invoice amount (SAR 75,000–200,000), PDF filename. Target: billing or procurement admin.",
                "MANDATORY PHISHING — Admin/Insurance: Fake health insurance portal — re-verify staff coverage. Vary: provider name (Tawuniya/Bupa Arabia/MedGulf/AXA), claim type (annual renewal/coverage update/reimbursement), suspicious link URL. Target: insurance coordinator.",
                "MANDATORY PHISHING — Admin/HR: Fake payroll system — salary on hold until bank details updated. Vary: bank detail type (IBAN/account number/branch code), deadline (end of month/within 48h/before 15th), sender name. Target: HR or billing staff.",
                "MANDATORY PHISHING — Admin/Executive: Hospital CEO or Director impersonation — urgent financial transfer or sensitive payroll data request. Vary: director name, amount, urgency reason. Pure social engineering, no link needed. Target: admin manager.",
                "MANDATORY PHISHING — Admin/Procurement: Fake medical procurement portal — supplier contract must be renewed via suspicious link. Vary: supplier type, contract value, deadline, suspicious URL. Target: procurement officer.",
            ],
            False: [
                "MANDATORY LEGITIMATE — Admin: Routine weekly patient appointment schedule reminder from department head. Official @hospital.org sender. No links, no requests, no urgency.",
                "MANDATORY LEGITIMATE — Admin/HR: Upcoming mandatory staff training notice (fire safety/CPR/MOH compliance). Official @hospital.org sender. Informational only.",
                "MANDATORY LEGITIMATE — Admin/Procurement: Approved medical supply order confirmed and dispatched. Official @hospital.org sender. No suspicious links.",
                "MANDATORY LEGITIMATE — Admin/Payroll: Monthly payslip notification from official HR system. Official @hospital.org sender. Standard routine notification.",
                "MANDATORY LEGITIMATE — Admin: Departmental meeting invitation from manager about next week. Official @hospital.org sender. Normal business communication.",
            ],
        },
        "clinical": {
            True: [
                "MANDATORY PHISHING — Clinical/EMR: Fake EMR credential harvest. Vary: system name (EMR/Patient Portal/Clinical System/HealthRecord), suspicious link URL, ONE spelling mistake (credintials OR urgant OR acces OR imediatly — never use recived). Address to Dr. or Nurse.",
                "MANDATORY PHISHING — Clinical/PDF: Malicious patient lab results PDF. Vary: patient department (ICU/oncology/cardiology/radiology/pediatrics), patient case reference, PDF filename (patient_results_XXXX.pdf), doctor name. Include one spelling mistake.",
                "MANDATORY PHISHING — Clinical/MOH: Fake MOH clinical protocol requiring immediate link click. Vary: protocol topic (infection control/COVID update/MRSA alert/vaccination/antimicrobial resistance), MOH official name, suspicious link URL.",
                "MANDATORY PHISHING — Clinical/Impersonation: Medical director or chief of staff impersonation — urgent patient data or system credentials request. Vary: director name, specialty (Surgery/Internal Medicine/Emergency/Oncology), specific request. Pure social engineering.",
                "MANDATORY PHISHING — Clinical/Excel: Malicious clinical duty roster Excel. Vary: schedule period (next month/Ramadan/Q2/holiday coverage), head nurse name, Excel filename. Request to enable macros.",
            ],
            False: [
                "MANDATORY LEGITIMATE — Clinical: Next week shift schedule update from head nurse. Official @hospital.org sender. No links, no requests. Normal clinical communication.",
                "MANDATORY LEGITIMATE — Clinical: Patient case review reminder for ward round or MDT meeting. Official @hospital.org sender. Routine clinical workflow, no suspicious elements.",
                "MANDATORY LEGITIMATE — Clinical/MOH: MOH mandatory training reminder (CPD/BLS/infection control). Official @moh.gov.sa or @hospital.org sender. Informational only.",
                "MANDATORY LEGITIMATE — Clinical: Updated infection control guidelines from infection control team. Official @hospital.org sender. Policy update only, no links.",
                "MANDATORY LEGITIMATE — Clinical: Department meeting invitation from medical director about clinical protocols. Official @hospital.org sender. Normal professional communication.",
            ],
        },
        "it": {
            True: [
                "MANDATORY PHISHING — IT/Helpdesk: Fake IT helpdesk remote support ticket — claim a critical server/network issue requires IT specialist to click a link and provide admin credentials immediately to allow remote access. Vary: ticket number, reported issue (EMR server down/network outage/database error), requester name, suspicious link URL. Target: IT specialist.",
                "MANDATORY PHISHING — IT/SSL: Fake SSL certificate expiry for hospital system. Vary: affected system (hospital website/patient portal/EMR login/staff intranet/lab system), renewal deadline, suspicious link URL. Target: system administrator.",
                "MANDATORY PHISHING — IT/Helpdesk: Fake helpdesk ticket requesting remote access or credentials. Vary: ticket reference number, reported issue (server outage/network fault/EMR performance), requester name. Target: IT helpdesk staff.",
                "MANDATORY PHISHING — IT/CIO: CIO or CISO impersonation — urgent server credentials or disable security settings. Vary: executive name, specific system (firewall/server/database), urgency reason. Pure social engineering. Target: IT specialist.",
                "MANDATORY PHISHING — IT/License: Fake software license renewal portal. Vary: software name (antivirus/EMR/Windows Server/database license), expiry urgency (24h/end of day/this week), suspicious renewal URL. Target: IT admin.",
            ],
            False: [
                "MANDATORY LEGITIMATE — IT: Scheduled server maintenance notice for next weekend. Official @hospital.org sender. Informational only, no credentials needed.",
                "MANDATORY LEGITIMATE — IT: Software update announcement for hospital systems (antivirus/Windows/EMR patch). Official @hospital.org sender. Standard IT notification.",
                "MANDATORY LEGITIMATE — IT: Network upgrade scheduled notification from IT department. Official @hospital.org sender. Informational, no action required.",
                "MANDATORY LEGITIMATE — IT/Helpdesk: IT helpdesk ticket resolution confirmation — issue resolved. Official @hospital.org sender. Closing notification only.",
                "MANDATORY LEGITIMATE — IT: Cybersecurity awareness training reminder for IT staff. Official @hospital.org or @moh.gov.sa sender. Training schedule only.",
            ],
        },
        "other": {
            True: [
                "MANDATORY PHISHING — Mixed/Admin: Fake supplier invoice for medical equipment — urgent payment request. Vary: supplier name, equipment type, invoice amount (SAR 50,000–150,000), PDF filename. Target: general hospital employee.",
                "MANDATORY PHISHING — Mixed/Clinical: Fake hospital system login credential harvest. Vary: system name (EMR/staff portal/scheduling system), suspicious URL, ONE spelling mistake. Target: general hospital employee.",
                "MANDATORY PHISHING — Mixed/IT: Fake hospital network or cybersecurity alert — urgent credential update. Vary: alert type (security breach/VPN expiry/account lockout), suspicious portal URL. Target: general hospital employee.",
                "MANDATORY PHISHING — Mixed/Admin: Fake payroll notification — salary on hold until bank details updated. Vary: bank detail type, urgency deadline, sender name. Target: general hospital employee.",
                "MANDATORY PHISHING — Mixed/Clinical: Fake MOH health directive — immediate acknowledgment via link. Vary: directive topic (vaccination/safety/compliance), MOH official name, suspicious URL. Target: general hospital employee.",
            ],
            False: [
                "MANDATORY LEGITIMATE — Mixed: Routine weekly work schedule update from department head. Official @hospital.org sender. No suspicious elements.",
                "MANDATORY LEGITIMATE — Mixed/HR: Staff training reminder from HR (safety/compliance/professional development). Official @hospital.org sender. Informational only.",
                "MANDATORY LEGITIMATE — Mixed: Hospital policy update notice from administration. Official @hospital.org sender. No links, no requests.",
                "MANDATORY LEGITIMATE — Mixed/Payroll: Monthly payslip notification from official HR system. Official @hospital.org sender. Standard notification.",
                "MANDATORY LEGITIMATE — Mixed: Team meeting or briefing invitation from manager. Official @hospital.org sender. Normal workplace communication.",
            ],
        },
    }
    role_assess = assess_scenarios.get(role_type, assess_scenarios["admin"])
    phish_list  = role_assess[True]
    legit_list  = role_assess[False]

    # FIX 8: حساب الـ rank الصحيح بدلاً من index الكلي
    # نحتاج نعرف "هذا الـ phishing/legit الثاني أم الثالث؟"
    # نستخدم assess_pattern من session_state إذا متوفر
    pattern = st.session_state.get("assess_pattern", [])
    if pattern and index < len(pattern):
        if is_phishing:
            # عدد الأسئلة الـ phishing قبل هذا السؤال
            rank = sum(1 for i in range(index) if pattern[i] == True)
        else:
            # عدد الأسئلة الـ legit قبل هذا السؤال
            rank = sum(1 for i in range(index) if pattern[i] == False)
    else:
        rank = index

    if is_phishing:
        forced_task_raw = phish_list[rank % len(phish_list)]
    else:
        forced_task_raw = legit_list[rank % len(legit_list)]

    # FIX 9: ترجمة forced_task حسب اللغة
    ASSESS_TRANSLATIONS = {
        # ── Admin phishing ──────────────────────────────────────
        "MANDATORY PHISHING — Admin/Billing: Fake supplier invoice for medical equipment. Vary: supplier name (MedSupply Co./Gulf Medical/Al-Rashid Medical), equipment type (surgical instruments/lab supplies/radiology equipment/ICU monitors), invoice amount (SAR 75,000–200,000), PDF filename. Target: billing or procurement admin.":
            "إجباري تصيد — إداري/فواتير: فاتورة مورد معدات طبية مزيفة. غيّر: اسم المورد (MedSupply/الخليج الطبي/الرشيد الطبي)، نوع المعدات (أجهزة جراحية/مستلزمات مختبر/أجهزة تصوير/أجهزة ICU)، المبلغ (75,000–200,000 ريال)، اسم ملف PDF. الهدف: موظف فوترة أو مشتريات.",
        "MANDATORY PHISHING — Admin/Insurance: Fake health insurance portal — re-verify staff coverage. Vary: provider name (Tawuniya/Bupa Arabia/MedGulf/AXA), claim type (annual renewal/coverage update/reimbursement), suspicious link URL. Target: insurance coordinator.":
            "إجباري تصيد — إداري/تأمين: بوابة تأمين صحي مزيفة لإعادة التحقق من التغطية. غيّر: اسم شركة التأمين (التعاونية/بوبا/ميدغلف/AXA)، نوع الطلب (تجديد/تحديث تغطية/استرداد)، رابط مشبوه. الهدف: منسق تأمين.",
        "MANDATORY PHISHING — Admin/HR: Fake payroll system — salary on hold until bank details updated. Vary: bank detail type (IBAN/account number/branch code), deadline (end of month/within 48h/before 15th), sender name. Target: HR or billing staff.":
            "إجباري تصيد — إداري/رواتب: نظام رواتب مزيف — الراتب موقوف حتى تحديث البيانات البنكية. غيّر: نوع البيانات (IBAN/رقم الحساب/رمز الفرع)، الموعد النهائي (نهاية الشهر/48 ساعة/قبل الـ15)، اسم المرسل. الهدف: موظف HR أو فوترة.",
        "MANDATORY PHISHING — Admin/Executive: Hospital CEO or Director impersonation — urgent financial transfer or sensitive payroll data request. Vary: director name, amount, urgency reason. Pure social engineering, no link needed. Target: admin manager.":
            "إجباري تصيد — إداري/مدير: انتحال هوية المدير التنفيذي — طلب تحويل مالي عاجل أو بيانات رواتب حساسة. غيّر: اسم المدير، المبلغ، سبب الاستعجال. هندسة اجتماعية بحتة. الهدف: مدير إداري.",
        "MANDATORY PHISHING — Admin/Procurement: Fake medical procurement portal — supplier contract must be renewed via suspicious link. Vary: supplier type, contract value, deadline, suspicious URL. Target: procurement officer.":
            "إجباري تصيد — إداري/مشتريات: بوابة مشتريات طبية مزيفة — تجديد عقد مورد عبر رابط مشبوه. غيّر: نوع المورد، قيمة العقد، الموعد النهائي، الرابط المشبوه. الهدف: مسؤول مشتريات.",
        # ── Admin legit ─────────────────────────────────────────
        "MANDATORY LEGITIMATE — Admin: Routine weekly patient appointment schedule reminder from department head. Official @hospital.org sender. No links, no requests, no urgency.":
            "إجباري شرعي — إداري: تذكير روتيني أسبوعي بجدول مواعيد المرضى من رئيس القسم. مرسل رسمي @hospital.org. بدون روابط أو طلبات.",
        "MANDATORY LEGITIMATE — Admin/HR: Upcoming mandatory staff training notice (fire safety/CPR/MOH compliance). Official @hospital.org sender. Informational only.":
            "إجباري شرعي — إداري/موارد بشرية: إشعار تدريب إلزامي قادم (سلامة/إسعافات/امتثال). مرسل رسمي @hospital.org. للإعلام فقط.",
        "MANDATORY LEGITIMATE — Admin/Procurement: Approved medical supply order confirmed and dispatched. Official @hospital.org sender. No suspicious links.":
            "إجباري شرعي — إداري/مشتريات: تأكيد اعتماد وشحن طلب توريد طبي. مرسل رسمي @hospital.org. بدون روابط مشبوهة.",
        "MANDATORY LEGITIMATE — Admin/Payroll: Monthly payslip notification from official HR system. Official @hospital.org sender. Standard routine notification.":
            "إجباري شرعي — إداري/رواتب: إشعار راتب شهري من نظام الموارد البشرية الرسمي. مرسل رسمي @hospital.org. إشعار روتيني عادي.",
        "MANDATORY LEGITIMATE — Admin: Departmental meeting invitation from manager about next week. Official @hospital.org sender. Normal business communication.":
            "إجباري شرعي — إداري: دعوة اجتماع قسم من المدير للأسبوع القادم. مرسل رسمي @hospital.org. تواصل عمل عادي.",
        # ── Clinical phishing ───────────────────────────────────
        "MANDATORY PHISHING — Clinical/EMR: Fake EMR credential harvest. Vary: system name (EMR/Patient Portal/Clinical System/HealthRecord), suspicious link URL, ONE spelling mistake (credintials OR urgant OR acces OR imediatly — never use recived). Address to Dr. or Nurse.":
            "إجباري تصيد — سريري/EMR: سرقة بيانات نظام السجلات الطبية. غيّر: اسم النظام (EMR/بوابة المريض/النظام السريري)، الرابط المشبوه، خطأ إملائي واحد (اختر: تسجيـل/عاجلة/وصلت). خاطب الدكتور أو الممرض.",
        "MANDATORY PHISHING — Clinical/PDF: Malicious patient lab results PDF. Vary: patient department (ICU/oncology/cardiology/radiology/pediatrics), patient case reference, PDF filename (patient_results_XXXX.pdf), doctor name. Include one spelling mistake.":
            "إجباري تصيد — سريري/PDF: مرفق PDF خبيث لنتائج مختبر مريض. غيّر: القسم (ICU/أورام/قلب/أشعة/أطفال)، رقم الحالة، اسم ملف PDF، اسم الطبيب. ضمّن خطأً إملائياً واحداً.",
        "MANDATORY PHISHING — Clinical/MOH: Fake MOH clinical protocol requiring immediate link click. Vary: protocol topic (infection control/COVID update/MRSA alert/vaccination/antimicrobial resistance), MOH official name, suspicious link URL.":
            "إجباري تصيد — سريري/وزارة: بروتوكول سريري مزيف من وزارة الصحة يستلزم نقر رابط فوري. غيّر: موضوع البروتوكول (مكافحة عدوى/كوفيد/MRSA/تطعيمات)، اسم المسؤول، الرابط المشبوه.",
        "MANDATORY PHISHING — Clinical/Impersonation: Medical director or chief of staff impersonation — urgent patient data or system credentials request. Vary: director name, specialty (Surgery/Internal Medicine/Emergency/Oncology), specific request. Pure social engineering.":
            "إجباري تصيد — سريري/انتحال: انتحال هوية المدير الطبي — طلب عاجل لبيانات مرضى أو بيانات دخول الأنظمة. غيّر: اسم المدير، التخصص (جراحة/باطنية/طوارئ/أورام)، الطلب المحدد.",
        "MANDATORY PHISHING — Clinical/Excel: Malicious clinical duty roster Excel. Vary: schedule period (next month/Ramadan/Q2/holiday coverage), head nurse name, Excel filename. Request to enable macros.":
            "إجباري تصيد — سريري/Excel: جدول مناوبات سريري مزيف كملف Excel خبيث. غيّر: الفترة (رمضان/الربع الثاني/الإجازات)، اسم رئيسة التمريض، اسم الملف. اطلب تفعيل الماكرو.",
        # ── Clinical legit ──────────────────────────────────────
        "MANDATORY LEGITIMATE — Clinical: Next week shift schedule update from head nurse. Official @hospital.org sender. No links, no requests. Normal clinical communication.":
            "إجباري شرعي — سريري: تحديث جدول المناوبة للأسبوع القادم من رئيسة التمريض. مرسل رسمي @hospital.org. بدون روابط أو طلبات.",
        "MANDATORY LEGITIMATE — Clinical: Patient case review reminder for ward round or MDT meeting. Official @hospital.org sender. Routine clinical workflow, no suspicious elements.":
            "إجباري شرعي — سريري: تذكير بمراجعة حالة مريض لجولة الزيارة أو اجتماع الفريق. مرسل رسمي @hospital.org. روتين سريري عادي.",
        "MANDATORY LEGITIMATE — Clinical/MOH: MOH mandatory training reminder (CPD/BLS/infection control). Official @moh.gov.sa or @hospital.org sender. Informational only.":
            "إجباري شرعي — سريري/وزارة: تذكير التدريب الإلزامي من وزارة الصحة (CPD/BLS/مكافحة عدوى). مرسل رسمي @moh.gov.sa. للإعلام فقط.",
        "MANDATORY LEGITIMATE — Clinical: Updated infection control guidelines from infection control team. Official @hospital.org sender. Policy update only, no links.":
            "إجباري شرعي — سريري: تحديث إرشادات مكافحة العدوى من الفريق المختص. مرسل رسمي @hospital.org. تحديث سياسة فقط.",
        "MANDATORY LEGITIMATE — Clinical: Department meeting invitation from medical director about clinical protocols. Official @hospital.org sender. Normal professional communication.":
            "إجباري شرعي — سريري: دعوة اجتماع قسم من المدير الطبي لمناقشة البروتوكولات. مرسل رسمي @hospital.org. تواصل مهني عادي.",
        # ── IT phishing ─────────────────────────────────────────
        "MANDATORY PHISHING — IT/VPN: Fake VPN re-authentication alert. Vary: VPN name (Cisco AnyConnect/FortiClient/Pulse Secure/GlobalProtect), suspicious portal URL, urgency reason (security update/certificate renewal/mandatory re-auth). Target: IT specialist.":
            "إجباري تصيد — تقني/VPN: تنبيه إعادة مصادقة VPN مزيف. غيّر: اسم الـ VPN (Cisco AnyConnect/FortiClient/Pulse Secure)، الرابط المشبوه، سبب الاستعجال. الهدف: متخصص تقنية معلومات.",
        "MANDATORY PHISHING — IT/SSL: Fake SSL certificate expiry for hospital system. Vary: affected system (hospital website/patient portal/EMR login/staff intranet/lab system), renewal deadline, suspicious link URL. Target: system administrator.":
            "إجباري تصيد — تقني/SSL: انتهاء شهادة SSL مزيف لنظام المستشفى. غيّر: النظام المتأثر (الموقع/بوابة المريض/EMR/الإنترانت)، الموعد النهائي، الرابط المشبوه. الهدف: مدير النظام.",
        "MANDATORY PHISHING — IT/Helpdesk: Fake helpdesk ticket requesting remote access or credentials. Vary: ticket reference number, reported issue (server outage/network fault/EMR performance), requester name. Target: IT helpdesk staff.":
            "إجباري تصيد — تقني/مكتب المساعدة: تذكرة مكتب مساعدة مزيفة تطلب وصولاً عن بُعد أو بيانات دخول. غيّر: رقم التذكرة، المشكلة المُبلَّغة (انقطاع الخادم/عطل الشبكة/أداء EMR)، اسم مقدم الطلب.",
        "MANDATORY PHISHING — IT/CIO: CIO or CISO impersonation — urgent server credentials or disable security settings. Vary: executive name, specific system (firewall/server/database), urgency reason. Pure social engineering. Target: IT specialist.":
            "إجباري تصيد — تقني/مدير: انتحال هوية مدير تقنية المعلومات — بيانات خادم عاجلة أو تعطيل إعدادات أمان. غيّر: اسم المدير، النظام المحدد (جدار ناري/خادم/قاعدة بيانات)، سبب الاستعجال.",
        "MANDATORY PHISHING — IT/License: Fake software license renewal portal. Vary: software name (antivirus/EMR/Windows Server/database license), expiry urgency (24h/end of day/this week), suspicious renewal URL. Target: IT admin.":
            "إجباري تصيد — تقني/ترخيص: بوابة تجديد ترخيص برنامج مزيفة. غيّر: اسم البرنامج (مضاد الفيروسات/EMR/Windows Server)، مدى الإلحاح (24 ساعة/نهاية اليوم/هذا الأسبوع)، الرابط المشبوه.",
        # ── IT legit ────────────────────────────────────────────
        "MANDATORY LEGITIMATE — IT: Scheduled server maintenance notice for next weekend. Official @hospital.org sender. Informational only, no credentials needed.":
            "إجباري شرعي — تقني: إشعار صيانة خادم مجدولة للعطلة القادمة. مرسل رسمي @hospital.org. للإعلام فقط، لا حاجة لبيانات دخول.",
        "MANDATORY LEGITIMATE — IT: Software update announcement for hospital systems (antivirus/Windows/EMR patch). Official @hospital.org sender. Standard IT notification.":
            "إجباري شرعي — تقني: إعلان تحديث برنامج لأنظمة المستشفى (مضاد الفيروسات/ويندوز/تحديث EMR). مرسل رسمي @hospital.org. إشعار تقني عادي.",
        "MANDATORY LEGITIMATE — IT: Network upgrade scheduled notification from IT department. Official @hospital.org sender. Informational, no action required.":
            "إجباري شرعي — تقني: إشعار ترقية شبكة مجدولة من قسم تقنية المعلومات. مرسل رسمي @hospital.org. للإعلام فقط.",
        "MANDATORY LEGITIMATE — IT/Helpdesk: IT helpdesk ticket resolution confirmation — issue resolved. Official @hospital.org sender. Closing notification only.":
            "إجباري شرعي — تقني/مكتب المساعدة: تأكيد حل تذكرة مكتب المساعدة. مرسل رسمي @hospital.org. إشعار إغلاق فقط.",
        "MANDATORY LEGITIMATE — IT: Cybersecurity awareness training reminder for IT staff. Official @hospital.org or @moh.gov.sa sender. Training schedule only.":
            "إجباري شرعي — تقني: تذكير تدريب الوعي الأمني لموظفي تقنية المعلومات. مرسل رسمي @hospital.org. جدول تدريب فقط.",
        # ── Other phishing ──────────────────────────────────────
        "MANDATORY PHISHING — Mixed/Admin: Fake supplier invoice for medical equipment — urgent payment request. Vary: supplier name, equipment type, invoice amount (SAR 50,000–150,000), PDF filename. Target: general hospital employee.":
            "إجباري تصيد — مختلط/إداري: فاتورة مورد طبية مزيفة — طلب دفع عاجل. غيّر: اسم المورد، نوع المعدات، المبلغ (50,000–150,000 ريال)، اسم PDF. الهدف: موظف عام.",
        "MANDATORY PHISHING — Mixed/Clinical: Fake hospital system login credential harvest. Vary: system name (EMR/staff portal/scheduling system), suspicious URL, ONE spelling mistake. Target: general hospital employee.":
            "إجباري تصيد — مختلط/سريري: سرقة بيانات دخول نظام المستشفى. غيّر: اسم النظام (EMR/بوابة الموظف/جدول المناوبات)، الرابط المشبوه، خطأ إملائي واحد. الهدف: موظف عام.",
        "MANDATORY PHISHING — Mixed/IT: Fake hospital network or cybersecurity alert — urgent credential update. Vary: alert type (security breach/VPN expiry/account lockout), suspicious portal URL. Target: general hospital employee.":
            "إجباري تصيد — مختلط/تقني: تنبيه أمني مزيف للشبكة — تحديث بيانات دخول عاجل. غيّر: نوع التنبيه (اختراق/انتهاء VPN/قفل الحساب)، الرابط المشبوه. الهدف: موظف عام.",
        "MANDATORY PHISHING — Mixed/Admin: Fake payroll notification — salary on hold until bank details updated. Vary: bank detail type, urgency deadline, sender name. Target: general hospital employee.":
            "إجباري تصيد — مختلط/إداري: إشعار راتب مزيف — موقوف حتى تحديث البيانات البنكية. غيّر: نوع البيانات البنكية، الموعد النهائي، اسم المرسل. الهدف: موظف عام.",
        "MANDATORY PHISHING — Mixed/Clinical: Fake MOH health directive — immediate acknowledgment via link. Vary: directive topic (vaccination/safety/compliance), MOH official name, suspicious URL. Target: general hospital employee.":
            "إجباري تصيد — مختلط/سريري: توجيه صحي مزيف من وزارة الصحة — تأكيد فوري عبر رابط. غيّر: موضوع التوجيه (تطعيمات/سلامة/امتثال)، اسم المسؤول، الرابط. الهدف: موظف عام.",
        # ── Other legit ─────────────────────────────────────────
        "MANDATORY LEGITIMATE — Mixed: Routine weekly work schedule update from department head. Official @hospital.org sender. No suspicious elements.":
            "إجباري شرعي — مختلط: تحديث جدول عمل أسبوعي روتيني من رئيس القسم. مرسل رسمي @hospital.org. بدون عناصر مشبوهة.",
        "MANDATORY LEGITIMATE — Mixed/HR: Staff training reminder from HR (safety/compliance/professional development). Official @hospital.org sender. Informational only.":
            "إجباري شرعي — مختلط/HR: تذكير تدريب موظفين من الموارد البشرية (سلامة/امتثال/تطوير). مرسل رسمي @hospital.org. للإعلام فقط.",
        "MANDATORY LEGITIMATE — Mixed: Hospital policy update notice from administration. Official @hospital.org sender. No links, no requests.":
            "إجباري شرعي — مختلط: إشعار تحديث سياسة المستشفى من الإدارة. مرسل رسمي @hospital.org. بدون روابط أو طلبات.",
        "MANDATORY LEGITIMATE — Mixed/Payroll: Monthly payslip notification from official HR system. Official @hospital.org sender. Standard notification.":
            "إجباري شرعي — مختلط/رواتب: إشعار راتب شهري من نظام الموارد البشرية الرسمي. مرسل رسمي @hospital.org. إشعار عادي.",
        "MANDATORY LEGITIMATE — Mixed: Team meeting or briefing invitation from manager. Official @hospital.org sender. Normal workplace communication.":
            "إجباري شرعي — مختلط: دعوة اجتماع فريق أو إحاطة من المدير. مرسل رسمي @hospital.org. تواصل عمل عادي.",
    }
    if is_ar:
        forced_task = ASSESS_TRANSLATIONS.get(forced_task_raw, forced_task_raw)
    else:
        forced_task = forced_task_raw

    # FIX 10: lang_rule مطابق للتعلم
    if is_ar:
        lang_rule = (
            "اللغة: عربية فصحى فقط في كل النصوص (subject/body/explanation).\n"
            "استثناء: عناوين البريد الإلكتروني والروابط (http://...) تبقى لاتينية.\n"
            "ممنوع: أي حرف لاتيني داخل النصوص العربية.\n"
            "حقل 'to': البريد الإلكتروني فقط بدون أي نص."
        )
    else:
        lang_rule = "Language: English only throughout. No Arabic or foreign characters in text fields. Email addresses and URLs stay Latin."

    # تعريف المتغيرات المستخدمة في JSON template
    if is_ar:
        from_ex = "اسم المرسل <email@domain.com>"
        subj_ex = "موضوع الرسالة"
        body_ex = "نص الرسالة بالعربية الفصحى"
        expl    = "اشرح بوضوح لماذا هذا البريد " + ("تصيد إلكتروني وما هي علاماته التحذيرية" if is_phishing else "شرعي وآمن وما الذي يجعله موثوقاً")
    else:
        from_ex = "Sender Name <email@domain.com>"
        subj_ex = "subject line"
        body_ex = "email body in English"
        expl    = f"Clearly explain why this email is {'phishing and identify the red flags' if is_phishing else 'legitimate and safe'}"

    return f"""Phishing awareness assessment email for Saudi healthcare. Seed:{session_seed}

TARGET: {r_desc}
CONTEXT: {r_ctx}

TASK — MANDATORY SCENARIO (do NOT change this):
{forced_task}
Additional context: {task}

DIFFICULTY: {diff_rule}

LANGUAGE: {lang_rule}

FORMAT: body=plain text only, \\n for line breaks, no HTML. "to"=email address only.
{"If phishing uses a link: put URL in suspicious_link AND in body. If attachment: filename in attachment field." if is_phishing else 'suspicious_link:"", attachment:""'}
{"If legitimate: use real official domain (@hospital.org or @moh.gov.sa), no suspicious links, no urgent credential requests.' " if not is_phishing else ""}

RETURN ONLY VALID JSON:
CRITICAL: Output ONLY the JSON object below. No text before it, no text after it, no explanations, no extra content whatsoever. Start with {{ end with }}.
{{"is_phishing":{"true" if is_phishing else "false"},"from":"{from_ex}","to":"employee@hospital.org","subject":"{subj_ex}","attachment":"","body":"{body_ex}","suspicious_link":"","explanation":"{expl}"}}"""

def get_system_prompt():
    """
    FIX 4+5: System prompt يُقيّد النموذج بصرامة حسب الصعوبة والـ role.
    - FIX 4: قواعد الصعوبة (Easy/Medium/Hard)
    - FIX 5: تعليمات الـ role لضمان أن التحية والمحتوى مناسبان للدور
    """
    difficulty = st.session_state.get("difficulty", "medium")
    role       = st.session_state.get("role", "Clinical")
    role_info  = ROLE_MAP.get(role, ROLE_MAP.get("Clinical"))
    _, _, role_type = role_info

    # تعليمات الـ role للتحية والمحتوى
    role_greetings = {
        "clinical": (
            "TARGET ROLE: Clinical staff (nurses, doctors, pharmacists, lab technicians).\n"
            "GREETING: Use 'Dear Dr. [Name]' or 'Dear Nurse [Name]' — medical titles only.\n"
            "CONTENT: Must relate to EMR systems, patient records, clinical schedules, lab results, pharmacy, MOH medical alerts, medical device updates, or clinical protocols.\n"
            "DO NOT use administrative, billing, or IT content."
        ),
        "admin": (
            "TARGET ROLE: Administrative/management staff — pick ONE specific sub-role each time (rotate between them):\n"
            "  - Medical Secretary: manages doctor schedules, correspondence, referral letters\n"
            "  - Receptionist: patient check-in, phone calls, appointment booking\n"
            "  - Patient Records Clerk: patient files, medical history, document archiving\n"
            "  - Insurance Coordinator: health insurance claims, pre-authorizations, coverage updates\n"
            "  - Billing Specialist: invoices, payments, accounts receivable, supplier contracts\n"
            "  - Procurement Officer: medical equipment orders, supplier relationships, purchase orders\n"
            "  - Hospital Administrator: staff HR policies, MOH accreditation, budget approvals\n\n"
            "GREETING: Match the sub-role — e.g. 'Dear Ms. Reem,' / 'Dear Medical Secretary,' / 'Dear Ms. Al-Zahrani,' — NEVER use 'Dr.' or medical titles.\n\n"
            "CONTENT: Choose a DIFFERENT scenario each time — rotate through these varied attack types:\n"
            "  1. Fake health insurance portal — update employee coverage or re-submit denied claims\n"
            "  2. Fake supplier invoice — urgent payment for medical equipment delivery\n"
            "  3. Fake payroll/HR system — update bank account or salary information\n"
            "  4. Fake patient appointment system — verify login after system migration\n"
            "  5. Fake MOH accreditation request — upload required compliance documents\n"
            "  6. Fake HR policy acknowledgment — click link to confirm new leave/overtime policy\n"
            "  7. Fake medical procurement portal — renew supplier contract before expiry\n"
            "  8. CEO/director impersonation — urgent financial transfer or sensitive data request\n\n"
            "DO NOT repeat the same scenario. DO NOT use clinical (lab/pharmacy/EMR) or IT infrastructure content."
        ),
        "it": (
            "TARGET ROLE: IT/Informatics staff (IT specialist, system administrator, cybersecurity officer).\n"
            "GREETING: Use 'Dear [Name],' or 'Dear IT Team,' or 'Dear Mr./Ms. [Name]' — NOT 'Dr.'.\n"
            "CONTENT: Must relate to VPN access, network infrastructure, server maintenance, EMR system updates, SSL certificates, firewall rules, software licenses, IT helpdesk, or endpoint security.\n"
            "DO NOT use clinical or administrative content."
        ),
        "other": (
            "TARGET ROLE: General hospital employee — could be from any department.\n"
            "GREETING: Use 'Dear [Name],' or 'Dear Colleague,' — avoid specific titles like 'Dr.' unless the scenario requires it.\n"
            "CONTENT: Follow the MANDATORY SCENARIO exactly — it already specifies the department context (admin/clinical/IT). Generate content that any hospital employee could plausibly receive.\n"
            "The scenario rotates across all three role types to ensure maximum variety."
        ),
    }
    role_instruction = role_greetings.get(role_type, role_greetings["admin"])

    sys_prompts = {
        "easy": (
            "You are a cybersecurity trainer generating phishing email examples.\n\n"
            f"{role_instruction}\n\n"
            "EASY level RULES — ALL mandatory:\n"
            f"1. Use a CLEARLY FAKE domain suited to the role (admin: hosp1tal-hr.xyz / moh-pay.net | clinical: emr-secure.xyz / medrecords.net | it: vpn-update.xyz / sysadmin-alert.net)\n"
            "2. Include EXACTLY 2 obvious spelling mistakes in the body\n"
            "3. Use ALL-CAPS for at least 2 sentences — aggressive urgency\n"
            "4. Generic greeting ONLY: \'Dear Staff\' or \'Dear Team\' — NO personal name\n"
            "5. Blatant suspicious request matching the scenario (urgent payment / share password / enter credentials)\n"
            "These rules are NON-NEGOTIABLE."
        ),
        "medium": (
            "You are a cybersecurity trainer generating phishing email examples.\n\n"
            f"{role_instruction}\n\n"
            "MEDIUM level RULES — ALL mandatory:\n"
            f"1. Use a slightly suspicious domain (admin: hospital-hr-portal.net / moh-billing.com | clinical: emr-health-sa.net / moh-clinic.com | it: vpn-hospital-sa.net / itsupport-moh.com)\n"
            "2. Include EXACTLY 1 minor spelling mistake — subtle, one word only\n"
            "3. ZERO ALL-CAPS — use normal sentence case throughout\n"
            "4. Moderate urgency only: \'Please respond by end of week\' — no threatening language\n"
            "5. Semi-personal greeting matching sub-role (e.g. \'Dear Ms. Al-Zahrani,\')\n"
            "6. Unusual but plausible request for the workplace context\n"
            "These rules are NON-NEGOTIABLE. NO ALL-CAPS under any circumstances."
        ),
        "hard": (
            "You are a cybersecurity trainer generating phishing email examples.\n\n"
            f"{role_instruction}\n\n"
            "HARD level RULES — ALL mandatory:\n"
            f"1. Domain with ONE tiny change only (admin: hosp1tal.org / moh.gov-sa.com | clinical: moh.gov.sa-health.com / hosp1tal-clinic.org | it: hosp1tal-it.org / moh-itsupport.sa.com)\n"
            "2. ZERO spelling or grammar mistakes — flawless professional language\n"
            "3. ZERO ALL-CAPS — completely professional tone throughout\n"
            "4. Polite subtle urgency ONLY: \'Kindly review before end of business day\'\n"
            "5. Full name + exact job title in greeting matching the sub-role\n"
            "6. ONLY ONE subtle red flag (the domain) — everything else perfectly legitimate\n"
            "These rules are NON-NEGOTIABLE. The email must look almost completely real."
        ),
    }
    return sys_prompts.get(difficulty, sys_prompts["medium"])


def call_ai(prompt, max_tokens=1600):
    provider = st.session_state.get("ai_provider", "groq")
    system_prompt = get_system_prompt()  # FIX 4: system prompt

    def get_secret(key):
        try:
            return st.secrets[key]
        except Exception:
            return os.environ.get(key, "")

    # FIX 1: Changed model from llama-3.1-8b-instant to llama-3.3-70b-versatile
    if provider == "groq":
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {get_secret('GROQ_API_KEY')}"
            },
            json={
                "model":       "llama-3.3-70b-versatile",
                "max_tokens":  max_tokens,
                "temperature": 0.85,
                "messages":    [
                    {"role": "system", "content": system_prompt},  # FIX 4: system msg
                    {"role": "user",   "content": prompt}
                ]
            },
            timeout=45
        )
        data = resp.json()
        return data

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
                "messages":    [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt}
                ]
            },
            timeout=60
        )
        return resp.json()

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
                "system":     system_prompt,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        raw = resp.json()
        if "content" in raw and len(raw["content"]) > 0:
            text = raw["content"][0].get("text", "")
            return {"choices": [{"message": {"content": text}}]}
        return {"error": raw}

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
        try:
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            return {"choices": [{"message": {"content": text}}]}
        except (KeyError, IndexError):
            return {"error": raw}

    else:
        return {"error": f"Unknown provider: {provider}"}

def call_groq(prompt, max_tokens=1600):
    return call_ai(prompt, max_tokens)

def parse_json_response(raw):
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    raw = fix_json_newlines(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        candidate = match.group(0)
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
    result["to"] = extract_to_email(result.get("to",""))
    if result.get("suspicious_link"):
        sl = result["suspicious_link"]
        sl = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',sl).strip()
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
        if result.get("suspicious_link","").strip():
            if result["suspicious_link"] not in result.get("body",""):
                result["body"] = result.get("body","") + f'\n{result["suspicious_link"]}'
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": str(e)}

def generate_assess_email(role, index, is_phishing, language):
    # FIX 2: max_tokens raised from 800 to 1200
    for attempt in range(3):
        try:
            data = call_groq(build_assess_prompt(role, index, is_phishing, language), max_tokens=1200)
            if "error" in data:
                return {"error": data["error"].get("message", str(data["error"]))}
            result = parse_json_response(data["choices"][0]["message"]["content"].strip())
            result = clean_result(result, language=="Arabic")
            result["to"] = get_recipient(st.session_state.get("role","Clinical"), index, language)
            if result.get("suspicious_link","").strip():
                if result["suspicious_link"] not in result.get("body",""):
                    result["body"] = result.get("body","") + f'\n{result["suspicious_link"]}'
            return result
        except json.JSONDecodeError:
            if attempt == 2:
                return {"error": "Failed to parse. Please try again."}
        except Exception as e:
            return {"error": str(e)}

def render_email_window(email, is_arabic, show_badges=False):
    bd = 'rtl' if is_arabic else 'ltr'
    ta = 'right' if is_arabic else 'left'
    email_font = 'Tahoma,Arial,sans-serif' if is_arabic else "'Courier New',monospace"

    body_raw        = re.sub(r'<[^>]+>','', email.get("body",""))
    suspicious_text = re.sub(r'<[^>]+>','', email.get("suspicious_text",""))
    suspicious_link = re.sub(r'<[^>]+>','', email.get("suspicious_link","")).strip()

    body_raw = re.sub(r'suspicious_link\s*:\s*', '', body_raw, flags=re.IGNORECASE)
    body_raw = re.sub(r'suspicious_text\s*:\s*', '', body_raw, flags=re.IGNORECASE)

    if suspicious_link and suspicious_link not in body_raw:
        link_bare = re.sub(r'^https?://', '', suspicious_link)
        if link_bare not in body_raw:
            body_raw = body_raw.rstrip() + f'\n\n{suspicious_link}'

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
                b = next_badge()
                body_html += (f'<br><br><span style="border:2px solid rgba(239,68,68,.6);'
                              f'border-radius:6px;padding:.2rem .5rem;background:rgba(239,68,68,.08);'
                              f'color:#60A5FA;text-decoration:underline;">'
                              f'{make_badge(b)}{html_lib.escape(suspicious_link)}</span>')

    body_html = body_html.replace("\n","<br>")

    from_val = html_lib.escape(email.get("from",""))
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

    nav_login    = t("Login","تسجيل الدخول")
    nav_register = t("Register","إنشاء حساب")
    nav_brand    = t("AI Phishing Awareness","التوعية بالتصيد الإلكتروني")
    user_name    = st.session_state.get("user_name","")
    shield_small = SHIELD_SVG.replace('width="52"','width="20"').replace('height="56"','height="22"')
    flex_dir     = "row-reverse" if is_arabic else "row"

    if user_name:
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
        st.markdown(f"""
<style>
.nb-btn {{height:34px;padding:0 16px;border-radius:9px;font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;text-decoration:none;}}
.nb-btn-ghost {{background:rgba(15,23,42,.88);color:#EAF4FF !important;border:1px solid rgba(37,99,235,.5);}}
.nb-btn-ghost:hover {{background:rgba(37,99,235,.25);border-color:#1EA7FF;color:#fff !important;}}
.nb-btn-solid {{background:linear-gradient(90deg,#0B4FA8,#0284C7);color:white !important;border:none;}}
.nb-btn-solid:hover {{background:linear-gradient(90deg,#1560C0,#0396E0);}}
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
    <a href="?nav=login&lang={st.session_state.get('language','English')}" class="nb-btn nb-btn-ghost">{nav_login}</a>
    <a href="?nav=register&lang={st.session_state.get('language','English')}" class="nb-btn nb-btn-solid">{nav_register}</a>
  </div>
</div>""", unsafe_allow_html=True)

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

    cards = [
        (BRAIN_SVG, t("AI-Powered Learning","تعلم بالذكاء الاصطناعي"), t("Personalised content adapted to your role.","محتوى تعليمي مخصص حسب دورك الوظيفي")),
        (TARGET_SVG,t("Smart Assessment","تقييم ذكي"),                 t("Short, focused assessments to test your awareness.","تقييمات قصيرة ومركزة لاختبار وعيك")),
        (CHART_SVG, t("Personalised Feedback","تغذية راجعة مخصصة"),   t("Detailed results with insights and recommendations.","نتائج مفصلة تتضمن ملاحظات وتوصيات مخصصة")),
        (SHIELD_SVG,t("Stronger Together","معًا أكثر أمانًا"),         t("Building a secure healthcare environment for everyone.","بناء بيئة صحية آمنة للجميع")),
    ]
    st.markdown('<div class="features-grid">'+"".join(f'<div class="feature-card"><div class="feature-icon">{i}</div><div class="feature-title">{tt}</div><div class="feature-text">{tx}</div></div>' for i,tt,tx in cards)+'</div>', unsafe_allow_html=True)

    form_col, panel_col = st.columns([3, 1], gap="large")

    with form_col:
        form_title_txt = t("Let's personalise your experience","لنخصص تجربتك")
        st.markdown(f'<div class="form-section"><div class="form-title">👤 {form_title_txt}</div></div>', unsafe_allow_html=True)

        def step_label(n, txt):
            return f'''<div style="font-size:.85rem;color:#94A3B8;margin-bottom:.5rem;
                        display:flex;align-items:center;gap:6px;direction:{dir_attr};">
              <span style="display:inline-flex;align-items:center;justify-content:center;
                           width:18px;height:18px;border-radius:50%;
                           background:rgba(37,99,235,.5);color:#7DD3FC;
                           font-size:10px;font-weight:800;">{n}</span>
              {txt}
            </div>'''

        st.markdown(step_label("1", t("Select your preferred language","اختر اللغة المفضلة")), unsafe_allow_html=True)
        cur_lang  = st.session_state.get("language","")
        en_cls = "lang-btn-sel" if cur_lang == "English" else "lang-btn"
        ar_cls = "lang-btn-sel" if cur_lang == "Arabic"  else "lang-btn"
        st.markdown(f"""<style>
.lang-btn button {{background:rgba(15,23,42,.78) !important;border:1px solid rgba(37,99,235,.55) !important;color:#EAF4FF !important;}}
.lang-btn-sel button {{background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;border:2px solid #1EA7FF !important;color:white !important;box-shadow:0 0 14px rgba(30,167,255,.35) !important;}}
.lang-btn-sel button:hover,.lang-btn-sel button:focus,.lang-btn-sel button:active {{background:linear-gradient(90deg,#0B4FA8,#0284C7) !important;border:2px solid #1EA7FF !important;color:white !important;}}
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
<div style="background:rgba(8,47,73,.2);border:1px solid rgba(37,99,235,.25);border-radius:14px;padding:1.2rem 1rem;margin-top:1rem;direction:{dir_attr};">
  <div style="font-size:.75rem;font-weight:800;color:#7DD3FC;letter-spacing:.06em;margin-bottom:14px;">{exp_title}</div>
  <div style="display:flex;flex-direction:column;gap:9px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">{small_brain}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{ph_label}</span></div>
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">{small_target}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{as_label}</span></div>
    <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;background:rgba(15,23,42,.7);border:1px solid rgba(37,99,235,.3);border-radius:9px;">{small_chart}<span style="font-size:.82rem;font-weight:700;color:#E2E8F0;">{rep_label}</span></div>
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

    with form_col:
        current_diff  = st.session_state.get("difficulty","medium")
        if st.session_state.get("language","English") == "Arabic":
            ordered = [("easy","🟢  مبتدئ"),("medium","🟡  متوسط"),("hard","🔴  متقدم")]
        else:
            ordered = [("easy","🟢  Beginner"),("medium","🟡  Intermediate"),("hard","🔴  Advanced")]

        diff_cols = st.columns(3)
        if st.session_state.get("language","English") == "Arabic":
            ordered_display = list(reversed(ordered))
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
        ai2="".join([f'<div style="color:#FCA5A5;margin-bottom:.4rem;text-align:{"right" if is_arabic else "left"};">⚠️ {a}</div>' for a in areas]) or f'<div style="color:#94A3B8;">{tp("Great work!","عمل رائع!")}</div>'
        st.markdown(f'<div style="border:1px solid rgba(239,68,68,.35);border-radius:14px;padding:1.2rem;background:rgba(239,68,68,.05);direction:{da};text-align:{"right" if is_arabic else "left"};"><div style="font-weight:800;color:#F1F5F9;margin-bottom:.8rem;text-align:{"right" if is_arabic else "left"};">📈 {tp("Areas to Improve","مجالات التحسين")}</div>{ai2}</div>',unsafe_allow_html=True)
    st.markdown('<div style="height:1rem"></div>',unsafe_allow_html=True)
    ri="".join([f'<div style="color:#DCEBFF;margin-bottom:.5rem;text-align:{"right" if is_arabic else "left"};">📌 {r}</div>' for r in recs])
    st.markdown(f'<div style="border:1px solid rgba(37,99,235,.45);border-radius:14px;padding:1.2rem 1.5rem;background:rgba(2,6,23,.6);margin-bottom:1.5rem;direction:{da};text-align:{"right" if is_arabic else "left"};"><div style="font-weight:800;color:#F1F5F9;margin-bottom:.8rem;text-align:{"right" if is_arabic else "left"};">💡 {tp("Recommendations","التوصيات")}</div>{ri}</div>',unsafe_allow_html=True)
    st.markdown(f'<div style="text-align:center;padding:.8rem;border:1px solid rgba(37,99,235,.3);border-radius:10px;background:rgba(37,99,235,.08);color:#7DD3FC;margin-bottom:1.5rem;">⭐ {tp("Your awareness helps keep your organization safe","وعيك يساهم في حماية مؤسستك")}</div>',unsafe_allow_html=True)
    if st.button(tp("Retake Training","إعادة التدريب من البداية"),key="retake", use_container_width=True):
        # FIX 6: مسح كامل لكل session data لضمان تنوع المحتوى
        keys_to_clear = [
            "page","example_index","emails","assess_index",
            "assess_emails","assess_answers","assess_pattern",
            "cache_version","role","scenario_order",
            "assess_scenario_order","difficulty",
            "user_name","user_email",
            "lang_explicitly_chosen","diff_explicitly_chosen",
            "login_mode","assess_index",
        ]
        for k in keys_to_clear:
            st.session_state.pop(k, None)
        # تجديد الـ cache_version لإجبار النموذج على توليد محتوى جديد
        st.session_state["cache_version"] = int(__import__("time").time()) % 99999
        st.rerun()


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
.stTextInput>div>div>input{{background:rgba(15,23,42,.88) !important;color:white !important;border:1px solid rgba(37,99,235,.55) !important;border-radius:12px !important;min-height:48px;direction:{da};font-size:.95rem !important;}}
.stTextInput label{{color:#94A3B8 !important;font-size:.85rem !important;}}
.stButton>button{{width:100% !important;min-height:48px !important;max-height:48px !important;font-weight:700 !important;border-radius:12px !important;font-size:.9rem !important;padding:0 16px !important;line-height:48px !important;}}
div[data-testid="stHorizontalBlock"] > div:first-child .stButton>button{{background:rgba(15,23,42,.88) !important;color:#EAF4FF !important;border:1px solid rgba(37,99,235,.55) !important;}}
div[data-testid="stHorizontalBlock"] > div:last-child .stButton>button{{background:rgba(15,23,42,.88) !important;color:#EAF4FF !important;border:1px solid rgba(37,99,235,.55) !important;}}
</style>""", unsafe_allow_html=True)

    st.markdown(f"""
<div style="text-align:center;padding:2.5rem 2rem 2rem;border:1px solid rgba(37,99,235,.45);border-radius:24px;background:linear-gradient(135deg,rgba(2,6,23,.96),rgba(8,47,73,.88));direction:{da};margin-bottom:1.5rem;">
  <div style="font-size:2.8rem;margin-bottom:.8rem;">{page_icon}</div>
  <div style="font-size:1.4rem;font-weight:900;color:#F8FAFC;margin-bottom:.4rem;">{page_title}</div>
  <div style="font-size:.9rem;color:#94A3B8;">{page_sub}</div>
</div>""", unsafe_allow_html=True)

    if is_arabic:
        st.markdown('<style>.stTextInput label{direction:rtl;text-align:right;display:block;}.stTextInput input{text-align:right;direction:rtl;}</style>', unsafe_allow_html=True)

    user_name  = st.text_input(tl("Full name","الاسم الكامل"), value=st.session_state.get("user_name",""), placeholder=tl("e.g. Dr. Sarah Al-Mutairi","مثال: د. سارة المطيري"))
    user_email = st.text_input(tl("Email address","البريد الإلكتروني"), value=st.session_state.get("user_email",""), placeholder="name@hospital.org")

    st.markdown('<div style="height:.8rem;"></div>', unsafe_allow_html=True)
    st.markdown("""<style>div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button{height:48px !important;min-height:48px !important;max-height:48px !important;padding-top:0 !important;padding-bottom:0 !important;display:flex !important;align-items:center !important;justify-content:center !important;box-sizing:border-box !important;}</style>""", unsafe_allow_html=True)

    c1, c2 = st.columns([1,1])
    with c1:
        if st.button(tl("← Back","← رجوع"), key="login_back", use_container_width=True):
            st.session_state["page"] = "home"; st.rerun()
    with c2:
        if st.button(tl("Continue","متابعة"), key="login_continue", use_container_width=True):
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
            if not user_name.strip():
                st.warning(tl("⚠️ Please enter your full name.","⚠️ يرجى إدخال اسمك الكامل"))
            elif not user_email.strip():
                st.warning(tl("⚠️ Please enter your email address.","⚠️ يرجى إدخال بريدك الإلكتروني"))
            elif not email_pattern.match(user_email.strip()):
                st.warning(tl("⚠️ Please enter a valid email address (e.g. name@hospital.org).","⚠️ يرجى إدخال بريد إلكتروني صحيح مثل: name@hospital.org"))
            else:
                st.session_state["user_name"]  = user_name.strip()
                st.session_state["user_email"] = user_email.strip()
                st.session_state["page"] = "home"; st.rerun()

pg=st.session_state.get("page","home")
{"home":page_home,"login":page_login,"learning":page_learning,"complete":page_complete,
 "assessment":page_assessment,"results":page_results,"report":page_report}.get(pg,page_home)()
