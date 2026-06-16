"""
🔮 الوكيل الذكي الشخصي والمحلل الاستراتيجي — نسخة سحابية
Personal AI Agent & Strategic Analyst — Cloud edition

- تحليل عميق متدفّق (Streaming) عبر OpenRouter (DeepSeek-V3 / GPT-4o).
- رادار فرص يعمل في الخلفية تلقائياً (كورسات / وظائف / منح).
- جاهز للنشر على Render / Railway عبر Docker.

التشغيل محلياً:  streamlit run app.py
المفاتيح تُقرأ من القائمة الجانبية أو من متغيّرات البيئة (الأفضل على السحابة):
  OPENROUTER_API_KEY, TAVILY_API_KEY (اختياري), SCAN_INTERVAL_HOURS, OPENROUTER_MODEL
"""

import os
import re
import json
from datetime import datetime, timedelta

import requests
import streamlit as st

import db
import database
import radar
import scholarship_expert
import whatsapp_agent
import hyper_scheduler
import content_factory
import ai_core
import income_hunter
import discipline_oracle
import advanced_scholarship
import feature_hub  # يجمّع features + advanced_module + wealth_empire

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "🧠 DeepSeek-V3 (العقل المفكّر العميق)": "deepseek/deepseek-chat",
    "⚡ GPT-4o (سريع وذكي)": "openai/gpt-4o",
    "🔬 DeepSeek-R1 (تفكير منطقي متسلسل)": "deepseek/deepseek-r1",
}

st.set_page_config(page_title="الوكيل الذكي الشخصي", page_icon="🔮",
                   layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# تهيئة قاعدة البيانات + تشغيل المجدول الخلفي مرة واحدة لكل عملية
# ---------------------------------------------------------------------------
db.init_db()
database.init_database()


@st.cache_resource(show_spinner=False)
def start_background_scheduler():
    """يُشغّل رادار الفرص دورياً في الخلفية. يُنشأ مرة واحدة فقط لكل عملية."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception:
        return None  # APScheduler غير مثبّت — الرادار يعمل يدوياً فقط
    interval = int(os.environ.get("SCAN_INTERVAL_HOURS", "12"))
    scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    scheduler.add_job(
        radar.run_opportunity_scan, "interval", hours=interval,
        id="opportunity_radar", replace_existing=True, max_instances=1,
        next_run_time=datetime.now() + timedelta(seconds=20),  # أول مسح بعد 20 ثانية
    )
    scheduler.start()
    return scheduler


# يُفعّل تلقائياً فقط لو كان مفتاح البحث/التحليل متاحاً في البيئة (وضع السحابة)
AUTO_RADAR = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("TAVILY_API_KEY")
                  or os.environ.get("ENABLE_RADAR"))
if AUTO_RADAR:
    start_background_scheduler()

# ---------------------------------------------------------------------------
# التصميم (CSS + RTL)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Tajawal', sans-serif; }
    .stApp { background: linear-gradient(180deg,#f7f9fc 0%, #eef2ff 100%); }
    section.main > div { direction: rtl; text-align: right; }
    .hero { background: linear-gradient(120deg,#4f46e5,#7c3aed 55%,#db2777);
        color:#fff; padding: 26px 30px; border-radius: 22px;
        box-shadow: 0 18px 40px -12px rgba(79,70,229,.45); margin-bottom: 18px; }
    .hero h1 { color:#fff !important; margin:0; font-weight:900; font-size: 28px; }
    .hero p { color:#e9e7ff; margin:8px 0 0; font-size: 16px; }
    .report-card { background:#ffffff; padding: 24px 28px; border-radius: 18px;
        box-shadow: 0 12px 28px -10px rgba(2,6,23,.12); border-right: 6px solid #6366f1;
        font-size: 16px; line-height: 1.9; color:#1f2937; min-height: 360px; }
    .opp-card { background:#fff; padding:16px 18px; border-radius:14px; margin-bottom:12px;
        box-shadow:0 8px 18px -10px rgba(2,6,23,.12); border-right:5px solid #22c55e; }
    .opp-card .score { float:left; background:#eef2ff; color:#4338ca; font-weight:700;
        border-radius:999px; padding:2px 10px; font-size:13px; }
    .opp-card a { color:#4f46e5; font-weight:700; text-decoration:none; }
    h1,h2,h3 { color:#1e1b4b; }
    .stButton>button { background: linear-gradient(120deg,#4f46e5,#7c3aed);
        color:#fff; border:0; border-radius: 12px; padding: 11px 16px; font-weight: 700; }
    .stTextArea textarea { direction: rtl; text-align: right; font-size: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# OpenRouter — البث الفوري + استخراج الكلمات المفتاحية
# ---------------------------------------------------------------------------
def _headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501", "X-Title": "Personal AI Oracle"}


def stream_openrouter(api_key, model, prompt):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "stream": True, "temperature": 0.8}
    with requests.post(OPENROUTER_URL, headers=_headers(api_key),
                       data=json.dumps(payload), stream=True, timeout=180) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore")
            if not line.startswith("data: "):
                continue
            chunk = line[6:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
            except Exception:
                continue


def extract_keywords(api_key, model, text):
    """يستخرج كلمات مفتاحية يستخدمها الرادار للبحث عن الفرص."""
    try:
        payload = {"model": model, "temperature": 0.2,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content":
                       "استخرج من النص التالي حتى 6 كلمات مفتاحية تمثّل مهارات/اهتمامات/"
                       "مجالات يبحث فيها صاحبه عن فرص. أعد JSON فقط: "
                       '{"keywords":["..."]}.\n\nالنص:\n' + text}]}
        r = requests.post(OPENROUTER_URL, headers=_headers(api_key),
                          data=json.dumps(payload), timeout=60)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(match.group(0) if match else content)
        kws = data.get("keywords", [])
        return [str(k).strip() for k in kws if str(k).strip()][:6]
    except Exception:
        return []


def build_prompt(user_log):
    return f"""أنت خبير عالمي في علم النفس السلوكي، وتطوير الذات، واقتناص الفرص الاستراتيجية.
حلّل النص التالي بدقة شديدة، واقرأ ما بين السطور، واكتب تحليلاً عميقاً ومبهراً بصيغة المخاطب
وباللغة العربية الفصحى المبسّطة.

=== النص ===
{user_log}
=== نهاية النص ===

اكتب بتنسيق Markdown أنيق مقسّماً إلى ثلاثة أقسام:

## 🧠 التحليل النفسي والسلوكي
المشاعر المخفية، أنماط الطاقة، وصفات/مخاوف في الشخصية قد لا يكون واعياً بها.

## 🎯 رادار الفرص والاستكشاف
فرص مهنية وتعليمية واستثمارية قابلة للاستغلال فوراً، مع قائمة كلمات بحث جاهزة لجوجل.

## 🗓️ خطة الحركة التنفيذية (3 خطوات لغدٍ)
ثلاث خطوات عملية حادة وواضحة لتنفيذها غداً.
"""


# ---------------------------------------------------------------------------
# القائمة الجانبية
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🔮 لوحة التحكم")
    env_key = os.environ.get("OPENROUTER_API_KEY", "")
    api_key = st.text_input("🔑 مفتاح OpenRouter API:", type="password", value=env_key)
    if api_key:
        st.success("تم تحميل المفتاح ✅")
    else:
        st.warning("🔑 أدخل مفتاح الـ API لتشغيل التحليل.")

    model_name = st.selectbox("🧠 النموذج الذكي:", list(MODELS.keys()))
    model = MODELS[model_name]

    st.divider()
    last_scan = db.get_setting("last_scan", "—")
    status = db.get_setting("last_scan_status", "—")
    st.caption(f"🕵️ آخر مسح للرادار: {last_scan}\n\nالحالة: {status}")
    if AUTO_RADAR:
        st.caption(f"⚙️ الرادار التلقائي مُفعّل كل {os.environ.get('SCAN_INTERVAL_HOURS','12')} ساعة.")
    else:
        st.caption("⚙️ الرادار التلقائي يُفعّل تلقائياً على السحابة (عبر متغيّرات البيئة).")

# ---------------------------------------------------------------------------
# الترويسة + التبويبات
# ---------------------------------------------------------------------------
st.markdown(
    """<div class="hero"><h1>🔮 الوكيل الذكي الشخصي والمحلل الاستراتيجي</h1>
    <p>تحليل عميق لأفكارك ويومياتك + رادار فرص يعمل في الخلفية على مدار الساعة.</p></div>""",
    unsafe_allow_html=True,
)

(tab_analyze, tab_sched, tab_factory, tab_chat, tab_radar, tab_scholar,
 tab_wa, tab_income, tab_hub, tab_disc, tab_settings) = st.tabs(
    ["✍️ التحليل العميق", "🗓️ المخطط الصارم", "🏭 مصنع المحتوى", "💬 الشات المرن",
     "🕵️ رادار الفرص", "🎓 خبير المنح", "📲 واتساب", "💸 ماكينة الدخل",
     "🧠 مركز الميزات", "🧭 محراب الانضباط", "⚙️ الإعدادات"]
)

# ====================== تبويب التحليل ======================
with tab_analyze:
    col1, col2 = st.columns([1, 1.25])
    with col1:
        st.markdown("### ✍️ تفريغ الأفكار واليوميات")
        user_log = st.text_area(
            "اكتب هنا بالتفصيل (أحداث، مشاعر، أحلام، أفكار مشاريع):",
            height=420, placeholder="اليوم شعرت بتشتت ولكن خطرت لي فكرة…")
        analyze_button = st.button("🚀 تشغيل التحليل العميق", use_container_width=True)

    with col2:
        st.markdown("### 📊 لوحة التحليل الاستراتيجي")
        if analyze_button:
            if not api_key:
                st.error("ضع مفتاح الـ API أولاً في القائمة الجانبية.")
            elif not user_log.strip():
                st.warning("اكتب بعض الأفكار أولاً.")
            else:
                st.markdown('<div class="report-card">', unsafe_allow_html=True)
                try:
                    with st.spinner("⚡ يتم تشغيل العقول التحليلية وقراءة ما بين السطور…"):
                        result = st.write_stream(
                            stream_openrouter(api_key, model, build_prompt(user_log)))
                    st.markdown("</div>", unsafe_allow_html=True)
                    # حفظ اليومية + كلماتها لتغذية الرادار
                    kws = extract_keywords(api_key, model, user_log)
                    db.save_entry(user_log, kws)
                    if kws:
                        st.caption("🧠 كلمات أُضيفت لرادارك: " + "، ".join(kws))
                    st.toast("🎯 تم التحليل وتغذية الرادار بنجاح!", icon="✅")
                except requests.exceptions.HTTPError as e:
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.error(f"خطأ من الخادم: تأكد من المفتاح والرصيد. {e}")
                except Exception as e:
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.error(f"حدث خطأ أثناء الاتصال: {e}")
        else:
            st.markdown('<div class="report-card">اكتب على اليمين واضغط زر التحليل… '
                        'وستظهر هنا قراءتك النفسية، فرصك، وخطة غدٍ. 🔮</div>',
                        unsafe_allow_html=True)

# ====================== تبويب رادار الفرص ======================
with tab_radar:
    st.markdown("### 🕵️ رادار الفرص — كورسات ووظائف ومنح")
    top = st.columns([1, 1, 2])
    with top[0]:
        if st.button("🔄 شغّل مسحاً الآن", use_container_width=True):
            with st.spinner("🔎 يتم البحث في الإنترنت عن أحدث الفرص…"):
                # على السحابة المفتاح في البيئة؛ محلياً نمرّره مؤقتاً
                if api_key and not os.environ.get("OPENROUTER_API_KEY"):
                    os.environ["OPENROUTER_API_KEY"] = api_key
                res = radar.run_opportunity_scan()
            if res["status"] == "no_keywords":
                st.warning("لا توجد كلمات مفتاحية بعد — اكتب يومية أو أضف اهتماماتك في الإعدادات.")
            else:
                st.success(f"تم العثور على {res['added']} فرصة جديدة (من {res['scanned']} نتيجة).")
    with top[1]:
        cat = st.selectbox("الفئة", ["all", "courses", "jobs", "grants"],
                           format_func=lambda c: {"all": "الكل", **radar.CATEGORY_LABELS_AR}.get(c, c))
    with top[2]:
        st.caption(f"إجمالي الفرص المحفوظة: {db.opportunities_count()}")

    opps = db.list_opportunities(category=cat, limit=80)
    if not opps:
        st.info("لا توجد فرص بعد. اضغط «شغّل مسحاً الآن» أو انتظر المسح التلقائي.")
    else:
        for o in opps:
            label = radar.CATEGORY_LABELS_AR.get(o["category"], o["category"])
            summary = o.get("summary") or o.get("snippet") or ""
            st.markdown(
                f'''<div class="opp-card">
                    <span class="score">{o["score"]}%</span>
                    <a href="{o["url"]}" target="_blank">🔗 {o["title"] or o["url"]}</a>
                    <div style="color:#6b7280;font-size:13px;margin:4px 0;">
                        {label} · {o["keyword"]} · {o["source"]}</div>
                    <div style="color:#374151;font-size:14px;">{summary}</div>
                </div>''',
                unsafe_allow_html=True,
            )

def _ensure_env_key():
    """يضمن توفّر المفتاح في البيئة للموديولات الخلفية أثناء الاستخدام المحلي."""
    if api_key and not os.environ.get("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = api_key


# ====================== تبويب خبير المنح ======================
with tab_scholar:
    st.markdown("### 🎓 خبير المنح الدراسية")
    st.caption("اسأل عن منح ماجستير/دكتوراه/بكالوريوس حسب الدولة والمجال — بالعامية المصرية.")
    sc_q = st.text_input("اكتب سؤالك:",
                         placeholder="عايز منحة ماجستير ممولة في ألمانيا في الهندسة")
    if st.button("🔎 اسأل خبير المنح", use_container_width=True):
        if not sc_q.strip():
            st.warning("اكتب سؤالك أولاً.")
        else:
            _ensure_env_key()
            with st.spinner("بدوّر على أنسب المنح ليك…"):
                ans = scholarship_expert.answer_scholarship_query(sc_q, use_web=True)
            st.markdown(f'<div class="report-card">{ans}</div>', unsafe_allow_html=True)
            st.caption("📌 المواعيد تقريبية وبتتغيّر سنوياً — راجع الموقع الرسمي لكل منحة.")

    with st.expander("📚 تصفّح قاعدة المنح المدمجة"):
        cc1, cc2 = st.columns(2)
        f_level = cc1.selectbox("المستوى", ["", "bachelor", "master", "phd", "research", "training"])
        f_country = cc2.selectbox("الدولة", ["", "USA", "UK", "Germany", "EU", "Türkiye",
                                              "Japan", "Australia", "Egypt", "Multiple"])
        for s in scholarship_expert.search_scholarships(level=f_level or None,
                                                        country=f_country or None, limit=20):
            st.markdown(f'<div class="opp-card">{scholarship_expert.format_scholarship(s)}</div>',
                        unsafe_allow_html=True)

    # ----- الأدوات الأكاديمية المطوّرة -----
    st.divider()
    st.markdown("#### 🎓 الأدوات الأكاديمية المطوّرة")
    TIERS = {"أفضل الجامعات عالمياً": "top_global", "Ivy League": "ivy_league",
             "Oxford/Cambridge": "oxbridge", "MIT/STEM": "mit_stem",
             "ثانويات IB/IGCSE": "ib_stem_schools"}
    with st.expander("📝 محسّن خطاب النوايا (Personal Statement)"):
        tier_l = st.selectbox("الفئة المستهدفة", list(TIERS.keys()), key="ps_tier")
        prog = st.text_input("البرنامج/الجامعة", key="ps_prog")
        ps = st.text_area("الصق مسودّة خطاب النوايا", height=160, key="ps_text")
        if st.button("✨ راجع وطوّر الخطاب", key="ps_btn"):
            if not ps.strip():
                st.warning("الصق المسودّة أولاً.")
            else:
                _ensure_env_key()
                with st.spinner("براجع وأطوّر…"):
                    out = advanced_scholarship.optimize_personal_statement(ps, prog, TIERS[tier_l])
                st.markdown(f'<div class="report-card">{out}</div>', unsafe_allow_html=True)
                st.caption("📌 بنرفع الجودة والفرص — القبول بيعتمد على عوامل كتير، مفيش ضمان نتيجة.")
    with st.expander("📄 محسّن السيرة الذاتية (CV / ATS)"):
        role = st.text_input("الوظيفة/البرنامج المستهدف", key="cv_role")
        cv = st.text_area("الصق سيرتك الذاتية", height=160, key="cv_text")
        if st.button("✨ حسّن الـ CV", key="cv_btn"):
            if not cv.strip():
                st.warning("الصق السيرة أولاً.")
            else:
                _ensure_env_key()
                with st.spinner("بحسّن…"):
                    out = advanced_scholarship.optimize_cv(cv, role)
                st.markdown(f'<div class="report-card">{out}</div>', unsafe_allow_html=True)
    with st.expander("🎤 محاكي المقابلات الشرس (Apex Interview)"):
        if "apex_hist" not in st.session_state:
            st.session_state.apex_hist = ""
        sch = st.selectbox("نمط المنحة", ["Chevening", "DAAD", "Fulbright", "Erasmus"], key="apex_sch")
        cews = st.columns(2)
        if cews[0].button("▶️ ابدأ مقابلة جديدة", key="apex_start"):
            _ensure_env_key()
            with st.spinner("المفتّش بيجهّز…"):
                q = advanced_scholarship.start_apex_interview(sch)
            st.session_state.apex_hist = "مفتّش: " + q
            st.markdown(f'<div class="report-card">{q}</div>', unsafe_allow_html=True)
        ans = st.text_area("إجابتك على آخر سؤال", height=110, key="apex_ans")
        if cews[1].button("📨 سلّم الإجابة", key="apex_send"):
            if not ans.strip():
                st.warning("اكتب إجابتك أولاً.")
            else:
                _ensure_env_key()
                with st.spinner("بيقيّم بصرامة…"):
                    fb = advanced_scholarship.apex_interview_turn(sch, st.session_state.apex_hist, ans)
                st.session_state.apex_hist += f"\nأنا: {ans}\nمفتّش: {fb}"
                st.markdown(f'<div class="report-card">{fb}</div>', unsafe_allow_html=True)

    # ----- لوحة المنح المكتشفة تلقائياً (Dashboard) -----
    st.divider()
    dh1, dh2 = st.columns([3, 1])
    dh1.markdown(f"#### 📋 المنح المكتشفة تلقائياً ({database.discovered_count()})")
    if dh2.button("🗑️ تفريغ القائمة", use_container_width=True):
        database.clear_discovered()
        st.rerun()
    discovered = database.list_discovered_scholarships(limit=200)
    if not discovered:
        st.caption("لسه مفيش منح مكتشفة. هتتجمّع تلقائياً من رادار الفرص ومن أسئلتك هنا.")
    else:
        st.dataframe(
            discovered, use_container_width=True, height=320, hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("اسم المنحة", width="medium"),
                "url": st.column_config.LinkColumn("الرابط", display_text="🔗 افتح"),
                "requirements": st.column_config.TextColumn("شروط / وصف", width="large"),
                "source": st.column_config.TextColumn("المصدر"),
                "discovered_at": st.column_config.TextColumn("تاريخ الاكتشاف"),
            },
        )

# ====================== تبويب واتساب ======================
with tab_wa:
    st.markdown("### 📲 نظام الرد الآلي على واتساب")
    mode = os.environ.get("WA_AUTO_REPLY", "draft").lower()
    configured = bool(os.environ.get("WA_ACCESS_TOKEN") and os.environ.get("WA_PHONE_NUMBER_ID"))
    st.info(("🟢 وضع الإرسال التلقائي مفعّل (send)." if mode == "send"
             else "🟡 وضع المسودّة (draft): الردود تتكتب وتستنّى موافقتك قبل الإرسال.")
            + ("  ✅ بيانات Cloud API مضبوطة." if configured
               else "  ⚠️ لسه محتاج تضبط WA_ACCESS_TOKEN و WA_PHONE_NUMBER_ID للإرسال."))

    st.markdown("#### 🧪 جرّب الرد (محاكاة رسالة واردة)")
    tcol1, tcol2 = st.columns([1, 2])
    test_rel = tcol1.selectbox("علاقة المرسِل", list(whatsapp_agent.RELATIONSHIP_STYLE.keys()))
    test_msg = tcol2.text_input("الرسالة الواردة", placeholder="عامل ايه يا نجم؟ نزلت امتحانك؟")
    if st.button("✍️ ولّد الرد المقترح"):
        if not test_msg.strip():
            st.warning("اكتب رسالة أولاً.")
        else:
            _ensure_env_key()
            with st.spinner("بكتب رد بالعامية…"):
                preview = whatsapp_agent.generate_reply(test_msg, {"relationship": test_rel, "name": ""})
            st.markdown(f'<div class="opp-card">{preview}</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("#### 📝 المسودّات بانتظار موافقتك")
    drafts = db.list_wa_messages(status="draft", limit=50)
    if not drafts:
        st.caption("لا توجد مسودّات حالياً. تظهر هنا تلقائياً عند وصول رسائل عبر الويبهوك.")
    for d in drafts:
        c = db.get_contact(d["wa_id"]) or {"name": d["wa_id"]}
        edited = st.text_area(f"إلى {c.get('name')} ({d['wa_id']})",
                              value=d["body"], key=f"draft_{d['id']}", height=90)
        bc1, bc2 = st.columns([1, 4])
        if bc1.button("📤 وافق وأرسل", key=f"send_{d['id']}"):
            res = whatsapp_agent.approve_and_send(d["id"], d["wa_id"], edited)
            if res.get("ok"):
                st.success("اتبعت ✅"); st.rerun()
            else:
                st.error(f"فشل الإرسال: {res.get('error')}")

    st.divider()
    st.markdown("#### 🧠 ذاكرة المحادثات (آخر ما تم حفظه)")
    chats = database.list_chats(limit=30)
    if not chats:
        st.caption("هتظهر هنا المحادثات المحفوظة تلقائياً لبناء ذاكرة مستمرة لكل شخص.")
    else:
        st.dataframe(
            chats, use_container_width=True, height=240, hide_index=True,
            column_config={
                "id": None,
                "sender": st.column_config.TextColumn("المرسِل"),
                "incoming_message": st.column_config.TextColumn("الرسالة الواردة", width="medium"),
                "smart_reply": st.column_config.TextColumn("الرد الذكي", width="large"),
                "timestamp": st.column_config.TextColumn("التوقيت"),
            },
        )

    st.divider()
    st.markdown("#### 👥 جهات الاتصال (اضبط أسلوب الرد لكل شخص)")
    contacts = db.list_contacts()
    if not contacts:
        st.caption("هتظهر جهات الاتصال هنا تلقائياً أول ما توصل رسائل.")
    for c in contacts:
        with st.expander(f"{c.get('name')} — {c['wa_id']}"):
            rel = st.selectbox("العلاقة", list(whatsapp_agent.RELATIONSHIP_STYLE.keys()),
                               index=max(0, list(whatsapp_agent.RELATIONSHIP_STYLE.keys())
                                         .index(c.get("relationship", "friend"))
                                         if c.get("relationship") in whatsapp_agent.RELATIONSHIP_STYLE else 0),
                               key=f"rel_{c['wa_id']}")
            notes = st.text_input("ملاحظات", value=c.get("notes", ""), key=f"notes_{c['wa_id']}")
            if st.button("💾 حفظ", key=f"save_{c['wa_id']}"):
                db.update_contact(c["wa_id"], relationship=rel, notes=notes)
                st.success("اتحفظ ✅")

# ====================== تبويب المخطط الصارم ======================
SCHED_TYPE_AR = {"routine": "🌅 روتين", "focus": "🎯 تركيز عميق", "break": "🌿 راحة",
                 "admin": "🗂️ مهام خفيفة", "meal": "🍽️ وجبة",
                 "winddown": "🌙 تهدئة", "sleep": "😴 نوم"}
with tab_sched:
    st.markdown("### 🗓️ المخطط الصارم وجدول الحركة الدقيق")
    st.caption("بيقسّم يومك بالدقيقة حسب طاقتك، ويربط أهدافك الكبيرة بأفعال صغيرة، ويوجّهك لحظياً.")

    sc1, sc2, sc3 = st.columns([2, 1, 1])
    goals_txt = sc1.text_area("أهدافك الكبيرة (هدف في كل سطر):",
                              placeholder="تعلم بايثون\nمشروع التخرج\nقراءة كتاب", height=110)
    wake = sc2.text_input("ميعاد الصحيان", value="08:00")
    sleep = sc3.text_input("ميعاد النوم", value="00:00")

    if st.button("🚀 ابنِ جدول اليوم", use_container_width=True):
        _ensure_env_key() if False else None  # المخطط يعمل بدون مفتاح (افتراضي ذكي)
        if api_key and not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = api_key
        goals = [g.strip() for g in goals_txt.splitlines() if g.strip()]
        conn = db.get_conn()
        rows = conn.execute("SELECT text FROM entries ORDER BY id DESC LIMIT 8").fetchall()
        conn.close()
        entries_texts = [r["text"] for r in rows]
        with st.spinner("بحلّل طاقتك وأبني الجدول…"):
            sched = hyper_scheduler.generate_and_save(goals, wake, sleep, entries_texts)
        st.session_state["today_sched"] = sched
        st.success("اتبنى الجدول واتحفظ ✅")

    # تحميل جدول اليوم لو موجود
    sched = st.session_state.get("today_sched") or database.get_schedule(
        datetime.now().strftime("%Y-%m-%d"))
    if sched and sched.get("plan"):
        guide = hyper_scheduler.now_guidance(sched["plan"])
        (st.success if guide["active"] else st.info)(
            f'**{guide["message"]}**' + (f'  ⏰ {guide["window"]}' if guide["window"] else ""))
        st.markdown("#### تفاصيل اليوم")
        table = [{"الوقت": f'{b["start"]} - {b["end"]}',
                  "النوع": SCHED_TYPE_AR.get(b["type"], b["type"]),
                  "التفاصيل": b["label"]} for b in sched["plan"]]
        st.dataframe(table, use_container_width=True, height=420, hide_index=True)
    else:
        st.info("اكتب أهدافك واضغط «ابنِ جدول اليوم» ليظهر هنا جدولك الدقيق وتوجيه اللحظة.")

# ====================== تبويب مصنع المحتوى ======================
with tab_factory:
    st.markdown("### 🏭 مصنع المحتوى الذكي")
    st.caption("بيتعلّم أسلوبك من يومياتك ويحوّل أفكارك لمحتوى بالعامية المصرية بصوتك أنت.")
    fc_type = st.selectbox("نوع المحتوى", list(content_factory.CONTENT_TYPES.keys()))
    fc_topic = st.text_area("الفكرة / الموضوع",
                            placeholder="اكتب الفكرة اللي عايز تعمل حواليها محتوى…", height=120)
    if st.button("✨ ولّد المحتوى بأسلوبي", use_container_width=True):
        if not api_key:
            st.error("ضع مفتاح الـ API أولاً.")
        elif not fc_topic.strip():
            st.warning("اكتب الفكرة أولاً.")
        else:
            _ensure_env_key()
            st.markdown('<div class="report-card">', unsafe_allow_html=True)
            out = st.write_stream(content_factory.stream_content(fc_type, fc_topic))
            st.markdown("</div>", unsafe_allow_html=True)
            if out and not out.startswith("⚠️"):
                database.save_content(fc_type, fc_topic, out)
                st.download_button("⬇️ تحميل", out,
                                   file_name=f"content_{datetime.now():%Y%m%d_%H%M}.txt")
                st.toast("اتحفظ في الأرشيف ✅", icon="✅")

    saved = database.list_content(limit=20)
    if saved:
        with st.expander(f"🗂️ أرشيف المحتوى ({len(saved)})"):
            for c in saved:
                st.markdown(f"**{c['content_type']} — {c['topic']}**  \n"
                            f"<span style='color:#6b7280;font-size:12px'>{c['created_at']}</span>",
                            unsafe_allow_html=True)
                st.markdown(f'<div class="opp-card">{c["body"]}</div>', unsafe_allow_html=True)

# ====================== تبويب مركز الميزات الموحّد ======================
with tab_hub:
    gt = feature_hub.grand_total()
    st.markdown("### 🧠 مركز الميزات الموحّد")
    st.caption(f"كل الأنظمة في مكان واحد: {gt['groups']} مجموعات · {gt['features']} ميزة "
               f"({gt['active']} فعّالة). اختر المجموعة ثم القسم ثم الميزة.")

    g_label = st.selectbox("المجموعة", [g["label"] for g in feature_hub.GROUPS])
    group = feature_hub.GROUP_BY_LABEL[g_label]
    st.caption("ℹ️ " + group["desc"])
    nc = feature_hub.normalized_counts(group)
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("الإجمالي", nc["total"]); h2.metric("🟢 فعّالة", nc["active"])
    h3.metric("🟡 تجريبية", nc["beta"]); h4.metric("🔌/⛔ غير ذلك", nc["other"])

    badge = group["badge"]
    secs = group["sections"]()
    sec_label = st.selectbox("القسم", [s["label"] for s in secs], key="hub_sec")
    sec = next(s for s in secs if s["label"] == sec_label)
    labels = {f'#{f["id"]} — {f["name"]} ({badge.get(f["status"], f["status"])})': f["id"]
              for f in sec["features"]}
    pick = st.selectbox("الميزة", list(labels.keys()), key="hub_feat")
    fid = labels[pick]
    feat = next(f for f in sec["features"] if f["id"] == fid)
    if feat.get("note"):
        st.caption("ℹ️ " + feat["note"])
    hub_in = st.text_area("المدخلات (حسب الميزة)", height=110, key="hub_in",
                          placeholder="اكتب التفاصيل / النص / الرابط / الأرقام هنا…")
    if st.button("⚡ تشغيل الميزة", use_container_width=True, key="hub_run"):
        _ensure_env_key()
        with st.spinner("بشتغل…"):
            res = group["run"](fid, hub_in)
        st.markdown(f'<div class="report-card"><b>{res["name"]}</b> '
                    f'({badge.get(res["status"], res["status"])})<br><br>'
                    f'{res["result"]}</div>', unsafe_allow_html=True)

    with st.expander(f"📜 كل ميزات «{g_label}»"):
        for s in secs:
            st.markdown(f"**{s['label']}**")
            for f in s["features"]:
                st.markdown(f"- #{f['id']} {f['name']} — {badge.get(f['status'], f['status'])}")

    # ---------- لوحات البيانات الحيّة (موحّدة هنا) ----------
    st.divider()
    st.markdown("#### 🗃️ لوحات البيانات الحيّة")
    with st.expander("❤️ المود والطاقة (user_wellbeing)"):
        w1, w2, w3 = st.columns(3)
        wm = w1.slider("المود", 0, 100, 60); we = w2.slider("الطاقة", 0, 100, 60)
        ws = w3.slider("التوتر", 0, 100, 40)
        wn = st.text_input("ملاحظة", key="wb_note")
        if st.button("💾 سجّل الحالة", key="wb_save"):
            database.add_wellbeing(wm, we, ws, wn); st.success("اتسجّلت ✅")
        wb = list(reversed(database.list_wellbeing(30)))
        if wb:
            st.line_chart({"المود": [r["mood"] for r in wb],
                           "الطاقة": [r["energy"] for r in wb],
                           "التوتر": [r["stress"] for r in wb]}, height=220)
    with st.expander("💰 المتتبّع المالي (financial_tracker)"):
        s = database.finance_summary()
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("دخل", s["income"]); f2.metric("مصاريف", s["expense"])
        f3.metric("اشتراكات", s["subscription"]); f4.metric("الرصيد", s["balance"])
        fc = st.columns([1, 1, 1, 2])
        ftype = fc[0].selectbox("النوع", ["expense", "income", "subscription"], key="fin_t")
        fcat = fc[1].text_input("الفئة", key="fin_cat")
        famt = fc[2].number_input("المبلغ", min_value=0.0, step=10.0, key="fin_amt")
        fnote = fc[3].text_input("ملاحظة", key="fin_note")
        if st.button("➕ أضف حركة مالية", key="fin_add"):
            database.add_finance("", ftype, fcat, famt, "EGP", fnote); st.rerun()
        fin = database.list_finance(50)
        if fin:
            st.dataframe(fin, use_container_width=True, height=200, hide_index=True)
    with st.expander("💹 لوحة ROI وقنوات الدخل (revenue_streams)"):
        roi = database.roi_dashboard()
        if roi["totals_mixed"]:
            st.bar_chart(roi["totals_mixed"], height=220)
            st.success(f"🏆 القطاع الأعلى عائداً: {roi['best_stream']}")
        else:
            st.caption("سجّل قنوات الدخل لتظهر لوحة ROI.")
        rc = st.columns([1, 1, 1, 2])
        strm = rc[0].selectbox("القناة", ["freelance", "digital", "affiliate", "seo",
                                          "arbitrage", "agency"], key="roi_strm")
        amt = rc[1].number_input("المبلغ", min_value=0.0, step=10.0, key="roi_amt")
        cur3 = rc[2].selectbox("العملة", ["USD", "EGP"], key="roi_cur")
        note3 = rc[3].text_input("ملاحظة", key="roi_note")
        if st.button("➕ سجّل دخلاً", key="roi_add"):
            database.add_revenue_stream(strm, amt, cur3, note3); st.rerun()
    with st.expander("🤝 الوعود (promises) + الفواتير (bills)"):
        pr = database.list_promises(50)
        if pr:
            st.dataframe(pr, use_container_width=True, height=150, hide_index=True)
        else:
            st.caption("سجّل وعداً من «الوحدة الخارقة → العلاقات».")
        bl = database.list_bills(50)
        if bl:
            st.dataframe(bl, use_container_width=True, height=150, hide_index=True)

# ====================== تبويب الشات المرن ======================
with tab_chat:
    st.markdown("### 💬 الشات المرن — شخصية تتبدّل حسب الموقف")
    CHAT_MODES = {"ودّي (علاقات وسعادة)": "friendly", "احترافي (شغل/منح/إيميلات)": "professional",
                  "مدرّب محفّز": "coach", "صارم وحاسم": "strict"}
    mode_label = st.radio("نبرة المساعد", list(CHAT_MODES.keys()), horizontal=True)
    chat_mode = CHAT_MODES[mode_label]
    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = []
    cc = st.columns([1, 5])
    if cc[0].button("🧹 مسح الشات"):
        st.session_state.chat_msgs = []
    for m in st.session_state.chat_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    prompt = st.chat_input("اكتب رسالتك…")
    if prompt:
        if not api_key:
            st.error("ضع مفتاح الـ API أولاً في القائمة الجانبية.")
        else:
            _ensure_env_key()
            st.session_state.chat_msgs.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            msgs = [{"role": "system", "content": ai_core.system_prompt(chat_mode)}] \
                + st.session_state.chat_msgs
            with st.chat_message("assistant"):
                out = st.write_stream(ai_core.stream(msgs))
            st.session_state.chat_msgs.append({"role": "assistant", "content": out})

# ====================== تبويب ماكينة الدخل ======================
with tab_income:
    st.markdown("### 💸 ماكينة الدخل التلقائية")
    s = database.revenue_summary()
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("📨 عروض", s["proposals_total"])
    r2.metric("🛒 مبيعات", s["sold"])
    r3.metric("🖱️ نقرات أفيليت", s["affiliate_clicks"])
    r4.metric("💵 إجمالي $", s["total_revenue"]["USD"])
    r5.metric("💷 إجمالي ج.م", s["total_revenue"]["EGP"])
    st.caption(f"معدل التحويل: {s['conversion_rate']}% — "
               f"مبيعات منتجات: ${s['sales_revenue'].get('USD',0)} / "
               f"أفيليت: ${s['affiliate_revenue'].get('USD',0)} / "
               f"إعلانات: ${s['ad_revenue'].get('USD',0)}")

    eng = st.selectbox("اختر المحرّك", [
        "📨 مولّد عروض الفريلانس", "📚 مصنع المنتجات الرقمية", "🤝 وكيل الأفيليت",
        "📝 مقالات SEO + نشر ووردبريس", "📈 توقّع الأرباح والنصيحة"])

    _ensure_env_key()

    if eng == "📨 مولّد عروض الفريلانس":
        c = st.columns([2, 1, 1])
        skills = c[0].text_input("مهاراتك", placeholder="Python, Data Analysis, تصميم")
        rate = c[1].number_input("سعرك", min_value=0.0, value=50.0, step=5.0)
        curr = c[2].selectbox("العملة", ["USD", "EGP"])
        proj = st.text_area("الصق وصف المشروع", height=140)
        if st.button("✍️ اكتب العرض", use_container_width=True):
            if not proj.strip():
                st.warning("الصق وصف المشروع.")
            else:
                with st.spinner("بكتب عرض يكسب…"):
                    p = income_hunter.tailor_proposal(proj, skills, rate, curr)
                st.markdown(f'<div class="report-card">{p}</div>', unsafe_allow_html=True)
        props = database.list_proposals(20)
        if props:
            with st.expander(f"📂 العروض المحفوظة ({len(props)})"):
                st.dataframe([{"المشروع": x["project"][:50], "السعر": x["price"],
                               "العملة": x["currency"], "الحالة": x["status"],
                               "وقت": x["ts"]} for x in props],
                             use_container_width=True, hide_index=True, height=200)

    elif eng == "📚 مصنع المنتجات الرقمية":
        c = st.columns([2, 1, 1])
        title = c[0].text_input("عنوان الكتاب/القالب", "دليل المنح الممولة 2026")
        src = c[1].selectbox("المصدر", ["scholarships", "opportunities", "content"])
        price = c[2].number_input("السعر", min_value=0.0, value=9.99, step=1.0)
        if st.button("🏗️ كوّن المنتج", use_container_width=True):
            with st.spinner("بجمّع البيانات وأبني الكتاب…"):
                res = income_hunter.compile_ebook(title, src, price)
            st.success(f"اتعمل كتاب فيه {res['items']} عنصر ✅")
            st.caption(f"الملف: {res['path']}")
            pay = income_hunter.create_payment_link(title, price)
            if pay.get("url"):
                st.markdown(f"🔗 رابط الدفع: {pay['url']}")
            else:
                st.info(pay.get("note", "اضبط رابط الدفع في الإعدادات."))
        st.caption("قمع مبيعات واتساب يعمل تلقائياً: لو وصلت رسالة فيها نية شراء، "
                   "الرد بيشرح المنتج ويرفق رابط الدفع/التحميل (وضع المسودّة افتراضياً).")

    elif eng == "🤝 وكيل الأفيليت":
        niche = st.text_input("المجال", placeholder="استضافة مواقع، كورسات، إلكترونيات")
        if st.button("🔎 دوّر على منتجات عمولة"):
            with st.spinner("بدوّر…"):
                prods = income_hunter.find_affiliate_products(niche or "courses")
            st.write("\n".join(f"- [{p['title']}]({p['url']})" for p in prods) or "مفيش نتائج دلوقتي.")
        st.divider()
        pc = st.columns([2, 2])
        prod = pc[0].text_input("اسم المنتج للمراجعة")
        link = pc[1].text_input("رابط الأفيليت بتاعك")
        if st.button("📝 اكتب مراجعة بالعامية"):
            with st.spinner("بكتب…"):
                rev = income_hunter.write_review(prod or "منتج", link or "")
            st.markdown(f'<div class="report-card">{rev}</div>', unsafe_allow_html=True)

    elif eng == "📝 مقالات SEO + نشر ووردبريس":
        kw = st.text_input("الكلمة المفتاحية", placeholder="منح ممولة بالكامل 2026")
        niche = st.text_input("المجال", "المنح والبيزنس")
        if st.button("🧠 ولّد مقال SEO"):
            with st.spinner("بكتب المقال…"):
                art = income_hunter.generate_seo_article(kw or "منح", niche)
            st.session_state["seo_art"] = art
        art = st.session_state.get("seo_art")
        if art:
            st.text_input("العنوان", art["title"], key="seo_title")
            st.caption("Meta: " + (art["meta"] or "—"))
            st.markdown(f'<div class="report-card">{art["content"]}</div>', unsafe_allow_html=True)
            pubcol = st.columns([1, 1])
            pstatus = pubcol[0].selectbox("حالة النشر", ["draft", "publish"])
            if pubcol[1].button("🚀 انشر على ووردبريس"):
                res = income_hunter.publish_to_wordpress(
                    st.session_state.get("seo_title", art["title"]), art["content"], pstatus)
                if res.get("ok"):
                    st.success(f"اتنشر ✅ {res.get('link','')}")
                else:
                    st.warning(res.get("note") or f"تعذّر: {res.get('error')}")

    else:  # توقّع الأرباح
        if st.button("📈 احسب التوقّع والنصيحة", use_container_width=True):
            with st.spinner("بحسب…"):
                pred = income_hunter.predict_revenue()
            pc = st.columns(2)
            pc[0].metric("توقّع الشهر", pred["projected_month"])
            pc[1].metric("آخر 30 يوم", pred["last_30_days"])
            st.info(f"🏆 المجال الأنسب حالياً: **{pred['best_channel']}**")
            st.markdown(f'<div class="report-card">{pred["advice"]}</div>', unsafe_allow_html=True)
        with st.expander("➕ سجّل بيع/إعلان يدوياً (للتجربة)"):
            mc = st.columns(4)
            kind = mc[0].selectbox("النوع", ["بيع منتج", "إعلان"])
            nm = mc[1].text_input("الاسم/المصدر")
            amt = mc[2].number_input("المبلغ", min_value=0.0, step=1.0)
            cur2 = mc[3].selectbox("عملة", ["USD", "EGP"])
            if st.button("حفظ الحركة"):
                if kind == "بيع منتج":
                    database.record_sale(nm or "منتج", amt, cur2)
                else:
                    database.add_ad_revenue("", nm or "AdSense", amt, cur2)
                st.rerun()

# ====================== تبويب محراب الانضباط ======================
with tab_disc:
    st.markdown("### 🧭 محراب الانضباط والمستقبل الواقعي")
    st.caption("نظام تركيز صارم لكنه صحّي. (أُعيدت صياغة جزء «العزوف» لموجّه تركيص إيجابي "
               "بلا تأطير ضد العلاقات أو الزواج.)")
    tool = st.selectbox("اختر الأداة", [
        "🏛️ مجلس الحكماء", "🗺️ خريطة المستقبل (4 مستويات)", "🟥 أمر الكورس اليومي",
        "🔒 حجب المشتتات", "🧪 فلتر القيمة", "▶️ سيناريو يوتيوب",
        "💬 مسودّات ردود الكومنتات", "🎯 موجّه التركيز الصحّي"])
    _ensure_env_key()

    if tool == "🏛️ مجلس الحكماء":
        sit = st.text_area("موقفك/سؤالك النهاردة", height=100)
        if st.button("⚖️ استدعِ المجلس", use_container_width=True):
            with st.spinner("المجلس بيتشاور…"):
                out = discipline_oracle.compile_masters_council(sit)
            st.markdown(f'<div class="report-card">{out}</div>', unsafe_allow_html=True)

    elif tool == "🗺️ خريطة المستقبل (4 مستويات)":
        g = st.text_input("هدفك الأكبر", placeholder="أبقى مهندس AI وأبني دخل سحابي")
        sk = st.text_input("مهاراتك الحالية")
        if st.button("🧱 ابنِ الخريطة", use_container_width=True):
            with st.spinner("ببني خريطة 10 سنين → اليوم…"):
                res = discipline_oracle.generate_hyper_realistic_roadmap(g, sk)
            st.markdown(f'<div class="report-card">{res["text"]}</div>', unsafe_allow_html=True)
        ms = database.list_milestones(limit=200)
        if ms:
            with st.expander(f"📌 المعالم المحفوظة ({len(ms)})"):
                st.dataframe([{"المستوى": m["horizon"], "المعلم": m["title"],
                               "الحالة": m["status"]} for m in ms],
                             use_container_width=True, hide_index=True, height=240)

    elif tool == "🟥 أمر الكورس اليومي":
        courses = st.text_area("كورساتك (سطر لكل كورس، ويفضّل «الاسم | عدد الشباتر»)",
                               height=120, placeholder="Python للمبتدئين | 20\nمنح والتقديم | 8")
        cc = st.columns(2)
        a = cc[0].text_input("من", "09:00"); b = cc[1].text_input("إلى", "11:00")
        if st.button("🟥 أصدر أمر النهاردة", use_container_width=True):
            st.markdown(f'<div class="report-card">{discipline_oracle.daily_course_enforcer(courses, a, b)}</div>',
                        unsafe_allow_html=True)

    elif tool == "🔒 حجب المشتتات":
        hrs = st.slider("ساعات التركيز", 1, 8, 3)
        if st.button("🔒 ولّد قائمة الحجب", use_container_width=True):
            res = discipline_oracle.activate_distraction_blocker(hrs)
            st.code(res["instructions"])
            st.download_button("⬇️ تحميل قائمة hosts", res["hosts_block"],
                               file_name="focus_hosts_block.txt")

    elif tool == "🧪 فلتر القيمة":
        items = st.text_area("الصق عناوين/روابط (سطر لكل واحد)", height=140)
        if st.button("🧪 فلتر", use_container_width=True):
            r = discipline_oracle.inbound_value_filtration_loop(items)
            st.success(r["summary"])
            st.markdown("**القيّم:**\n" + "\n".join(f"- {x}" for x in r["kept"]))
            if r["blocked"]:
                st.markdown("**المحجوب:**\n" + "\n".join(f"- ~~{x}~~" for x in r["blocked"]))

    elif tool == "▶️ سيناريو يوتيوب":
        niche = st.text_input("مجال القناة", placeholder="منح وتكنولوجيا")
        if st.button("🎬 اكتب سيناريو كامل", use_container_width=True):
            with st.spinner("بكتب السيناريو…"):
                sc = discipline_oracle.youtube_trend_scout(niche or "تكنولوجيا")
            st.markdown(f'<div class="report-card">{sc}</div>', unsafe_allow_html=True)

    elif tool == "💬 مسودّات ردود الكومنتات":
        cmnts = st.text_area("الصق الكومنتات (كومنت لكل سطر)", height=140)
        if st.button("✍️ اكتب مسودّات الردود", use_container_width=True):
            st.markdown(f'<div class="report-card">{discipline_oracle.youtube_comment_drafts(cmnts)}</div>',
                        unsafe_allow_html=True)

    else:  # موجّه التركيز الصحّي
        ctx = st.text_area("إيه اللي حاسس إنه بيشتتك أو محتاج تركّز عليه؟", height=100)
        if st.button("🎯 وجّهني", use_container_width=True):
            with st.spinner("…"):
                out = discipline_oracle.sovereign_focus_prompt(ctx)
            st.markdown(f'<div class="report-card">{out}</div>', unsafe_allow_html=True)

    st.divider()
    dm = database.list_discipline(20)
    if dm:
        with st.expander(f"📋 سجل الأوامر ({len(dm)})"):
            st.dataframe([{"التاريخ": d["date"], "الأمر": d["command"], "الحالة": d["status"]}
                          for d in dm], use_container_width=True, hide_index=True, height=200)

# ====================== تبويب الإعدادات ======================
with tab_settings:
    st.markdown("### ⚙️ إعدادات الرادار")
    st.caption("حدّد اهتماماتك ليبحث الرادار عن فرص تخصّك. تُدمج تلقائياً مع كلمات يومياتك.")
    current = db.get_setting("keywords", "")
    kw_input = st.text_area("كلماتك المفتاحية (افصل بينها بفاصلة):",
                            value=current, height=120,
                            placeholder="بايثون, تصميم جرافيك, تسويق رقمي, منح ماجستير")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 حفظ الكلمات", use_container_width=True):
            db.set_setting("keywords", kw_input)
            st.success("تم الحفظ ✅")
    with c2:
        if st.button("🗑️ مسح كل الفرص المحفوظة", use_container_width=True):
            db.clear_opportunities()
            st.success("تم مسح الفرص.")

    st.divider()
    st.markdown("#### 🔐 متغيّرات البيئة (للنشر السحابي)")
    st.code(
        "OPENROUTER_API_KEY=...        # مطلوب للتحليل والردود وترتيب الفرص\n"
        "TAVILY_API_KEY=...            # اختياري: بحث أكثر موثوقية على السحابة\n"
        "SCAN_INTERVAL_HOURS=12        # كل كم ساعة يعمل الرادار\n"
        "OPENROUTER_MODEL=deepseek/deepseek-chat\n"
        "ORACLE_DB_PATH=/data/oracle.db   # قرص دائم على السحابة\n"
        "\n# --- واتساب (Cloud API الرسمي) ---\n"
        "WA_VERIFY_TOKEN=...           # رمز تحقق الويبهوك (تختاره أنت)\n"
        "WA_ACCESS_TOKEN=...           # توكن الوصول من Meta\n"
        "WA_PHONE_NUMBER_ID=...        # معرّف رقم الواتساب من Meta\n"
        "WA_AUTO_REPLY=draft           # draft (مسودّة) أو send (إرسال تلقائي)",
        language="bash",
    )

    st.divider()
    st.markdown("#### 🔐 الخزنة المشفّرة (password_vault)")
    reveal = st.toggle("اعرض كلمات السر (محلياً فقط)", value=False)
    vault = database.list_vault(reveal=reveal)
    if vault:
        st.dataframe([{"الاسم": v["label"], "اليوزر": v["username"],
                       "السرّ": v["secret"], "التاريخ": v["created_at"]} for v in vault],
                     use_container_width=True, height=180, hide_index=True)
    else:
        st.caption("الخزنة فاضية. ولّد/خزّن سرّاً من قسم الأمن السيبراني (#32 / #36).")

    st.divider()
    st.markdown("#### 🛑 زر الذعر — التدمير الذاتي للخصوصية")
    st.warning("بيمسح فوراً السجلات الحساسة (محادثات، جهات اتصال، يوميات، مالية، خزنة، وعود…). "
               "الإجراء لا يمكن التراجع عنه.")
    confirm = st.text_input('اكتب كلمة «تأكيد» للتفعيل:', key="panic_confirm")
    if st.button("🔥 تصفير السجلات الحساسة الآن", use_container_width=True):
        if confirm.strip() == "تأكيد":
            wiped = database.panic_wipe()
            total = sum(v for v in wiped.values() if isinstance(v, int))
            st.success(f"تم التصفير ✅ — أُزيل {total} سجلاً من {len(wiped)} جدولاً.")
            st.json(wiped)
        else:
            st.error("اكتب كلمة «تأكيد» بالظبط في الخانة قبل التفعيل.")
