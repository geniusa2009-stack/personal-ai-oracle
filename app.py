"""
Personal AI Oracle — Local Mac edition.

The dashboard runs on the owner's MacBook and binds to localhost only.
The local runtime and LaunchAgent keep the UI and background worker alive.
AI requests can use hosted providers or models served locally by Ollama.
"""

import os
import re
import json
import uuid
from datetime import datetime, timedelta

import streamlit as st

from local_config import load_local_environment
load_local_environment()

import db
import database
import radar
import scholarship_expert
import whatsapp_agent
import hyper_scheduler
import content_factory
import ai_core
import memory
import agent_orchestrator
import agent_profiles
import income_hunter
import discipline_oracle
import advanced_scholarship
import feature_hub  # يجمّع features + advanced_module + wealth_empire

PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "ollama": "Ollama (local Mac models)",
}
PROVIDER_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

st.set_page_config(page_title="الوكيل الذكي الشخصي", page_icon="🔮",
                   layout="wide", initial_sidebar_state="expanded")

# Cloud mode is private: authenticate before rendering any personal data.
if os.environ.get("ORACLE_RUNTIME_MODE", "local").strip().lower() == "cloud":
    import secrets as _secrets
    _dashboard_password = os.environ.get("ORACLE_CLOUD_DASHBOARD_PASSWORD", "")
    if len(_dashboard_password) < 16:
        st.error("Cloud dashboard is not configured with a strong dashboard password.")
        st.stop()
    if not st.session_state.get("oracle_cloud_authenticated", False):
        st.title("Personal AI Oracle")
        st.caption("Private cloud workspace")
        with st.form("oracle_cloud_login"):
            _entered_password = st.text_input("Dashboard password", type="password")
            _submitted = st.form_submit_button("Sign in")
        if _submitted:
            if _secrets.compare_digest(_entered_password, _dashboard_password):
                st.session_state["oracle_cloud_authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()
    if st.sidebar.button("Sign out"):
        st.session_state.pop("oracle_cloud_authenticated", None)
        st.rerun()
    st.sidebar.divider()
    st.sidebar.caption("Hybrid connection · Cloud + Mac")
    try:
        import cloud_client
        _oracle_devices = cloud_client.list_devices()
        if not _oracle_devices:
            st.sidebar.warning("No Mac agent paired yet.")
        for _device in _oracle_devices:
            _label = str(_device.get("name") or "Mac agent")
            if _device.get("online"):
                st.sidebar.success(f"{_label} · online")
            elif _device.get("disabled"):
                st.sidebar.error(f"{_label} · disabled")
            else:
                st.sidebar.warning(f"{_label} · offline")
    except Exception:
        st.sidebar.caption("Mac connection status is temporarily unavailable.")

# Local mode remains private to 127.0.0.1; cloud mode uses the authenticated dashboard.

def render_report(content):
    """Render untrusted model/data output as Markdown, never raw HTML."""
    with st.container(border=True):
        st.markdown(str(content))


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
AUTO_RADAR = bool(
    os.environ.get("ENABLE_RADAR")
    or os.environ.get("OPENROUTER_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
)
if AUTO_RADAR and not os.environ.get("ORACLE_EXTERNAL_WORKER"):
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
def stream_openrouter(api_key, model, prompt, provider_name=None):
    """Compatibility wrapper for selected multi-provider streaming."""
    yield from ai_core.stream(
        [{"role": "user", "content": prompt}],
        temperature=0.8,
        task_type="reasoning",
        requested_model=model,
        provider_name=provider_name,
        api_key=api_key,
        agent_role="assistant",
    )


def extract_keywords(api_key, model, text, provider_name=None):
    """Extract radar keywords through the shared router with validated JSON output."""
    prompt = (
        "استخرج من النص التالي حتى 6 كلمات مفتاحية تمثّل مهارات/اهتمامات/"
        "مجالات يبحث فيها صاحبه عن فرص. أعد JSON فقط بهذا الشكل: "
        '{"keywords":["..."]}.\n\nالنص:\n' + text
    )
    try:
        content = ai_core.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            task_type="research",
            requested_model=model,
            provider_name=provider_name,
            api_key=api_key,
            response_format={"type": "json_object"},
            agent_role="researcher",
        )
        if not content or content.startswith(("⚠️", "(تعذّر")):
            return []
        data = json.loads(content)
        keywords = data.get("keywords", [])
        if not isinstance(keywords, list):
            return []
        return [str(keyword).strip() for keyword in keywords
                if isinstance(keyword, str) and keyword.strip()][:6]
    except (TypeError, ValueError, KeyError):
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
    st.markdown("### 🔮 Oracle — Local Mac")
    st.caption("يعمل محلياً تحت حساب macOS الحالي، وليس موقعاً عاماً.")
    st.divider()

    provider_options = ai_core.available_providers() or ["openrouter", "ollama"]
    current_provider = ai_core.default_provider_name()
    provider_name = st.selectbox(
        "مزود الذكاء الاصطناعي",
        provider_options,
        index=provider_options.index(current_provider) if current_provider in provider_options else 0,
        format_func=lambda value: PROVIDER_LABELS.get(value, value),
    )
    key_env = PROVIDER_KEY_ENV.get(provider_name)
    api_key = None
    if key_env:
        default_api_key = os.environ.get(key_env, "")
        if provider_name == "gemini":
            default_api_key = default_api_key or os.environ.get("GOOGLE_API_KEY", "")
        api_key = st.text_input(
            f"مفتاح {PROVIDER_LABELS.get(provider_name, provider_name)}",
            type="password",
            value=default_api_key,
        )
        if api_key:
            os.environ[key_env] = api_key
    model = st.text_input(
        "اسم الموديل",
        value=ai_core.default_model_name(provider_name),
        help="اكتب اسم موديل المزوّد كما يظهر في حسابك أو في Ollama المحلي.",
    )
    os.environ["ORACLE_DEFAULT_PROVIDER"] = provider_name
    if model.strip():
        os.environ["ORACLE_DEFAULT_MODEL"] = model.strip()
    else:
        os.environ.pop("ORACLE_DEFAULT_MODEL", None)

    if provider_name == "ollama":
        st.info("موديلات Ollama محلية؛ يجب تشغيل Ollama وتثبيت الموديل المختار.")
    elif ai_core.has_key(provider_name):
        st.success("بيانات المزوّد موجودة ✅")
    else:
        st.warning("أضف مفتاح المزوّد في إعدادات Oracle المحلية.")

    with st.expander("🧠 نماذج الوكلاء المتخصصين"):
        st.dataframe(
            [{
                "Agent": item["role"],
                "Provider": item["provider"],
                "Model": item["model"] or "استخدم موديل المهمة الافتراضي",
            } for item in agent_profiles.profile_catalog()],
            use_container_width=True,
            hide_index=True,
        )

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
 tab_wa, tab_income, tab_hub, tab_disc, tab_settings, tab_oracle) = st.tabs(
    ["✍️ التحليل العميق", "🗓️ المخطط الصارم", "🏭 مصنع المحتوى", "💬 الشات المرن",
     "🕵️ رادار الفرص", "🎓 خبير المنح", "📲 واتساب", "💸 ماكينة الدخل",
     "🧠 مركز الميزات", "🧭 محراب الانضباط", "⚙️ الإعدادات", "🔮 Oracle Control Center"]
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
            if not ai_core.has_key(provider_name):
                st.error("اضبط مزود الذكاء الاصطناعي في القائمة الجانبية.")
            elif not user_log.strip():
                st.warning("اكتب بعض الأفكار أولاً.")
            else:
                try:
                    with st.container(border=True):
                        with st.spinner("⚡ يتم تشغيل العقول التحليلية وقراءة ما بين السطور…"):
                            result = st.write_stream(
                                stream_openrouter(api_key, model, build_prompt(user_log), provider_name)
                            )
                    # حفظ اليومية + كلماتها لتغذية الرادار
                    kws = extract_keywords(api_key, model, user_log, provider_name)
                    db.save_entry(user_log, kws)
                    if kws:
                        st.caption("🧠 كلمات أُضيفت لرادارك: " + "، ".join(kws))
                    st.toast("🎯 تم التحليل وتغذية الرادار بنجاح!", icon="✅")
                except Exception as e:
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
                _ensure_env_key()
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
            with st.container(border=True):
                st.markdown(f"**{o['score']}% · {o['title'] or o['url']}**")
                st.caption(f"{label} · {o['keyword']} · {o['source']}")
                if o.get("url"):
                    st.write(o["url"])
                if summary:
                    st.write(summary)

def _ensure_env_key():
    """Keep the selected model profile available to all feature modules in this local process."""
    os.environ["ORACLE_DEFAULT_PROVIDER"] = provider_name
    if model.strip():
        os.environ["ORACLE_DEFAULT_MODEL"] = model.strip()
    if api_key and key_env:
        os.environ[key_env] = api_key


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
            render_report(ans)
            st.caption("📌 المواعيد تقريبية وبتتغيّر سنوياً — راجع الموقع الرسمي لكل منحة.")

    with st.expander("📚 تصفّح قاعدة المنح المدمجة"):
        cc1, cc2 = st.columns(2)
        f_level = cc1.selectbox("المستوى", ["", "bachelor", "master", "phd", "research", "training"])
        f_country = cc2.selectbox("الدولة", ["", "USA", "UK", "Germany", "EU", "Türkiye",
                                              "Japan", "Australia", "Egypt", "Multiple"])
        for s in scholarship_expert.search_scholarships(level=f_level or None,
                                                        country=f_country or None, limit=20):
            render_report(scholarship_expert.format_scholarship(s))

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
                render_report(out)
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
                render_report(out)
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
            render_report(q)
        ans = st.text_area("إجابتك على آخر سؤال", height=110, key="apex_ans")
        if cews[1].button("📨 سلّم الإجابة", key="apex_send"):
            if not ans.strip():
                st.warning("اكتب إجابتك أولاً.")
            else:
                _ensure_env_key()
                with st.spinner("بيقيّم بصرامة…"):
                    fb = advanced_scholarship.apex_interview_turn(sch, st.session_state.apex_hist, ans)
                st.session_state.apex_hist += f"\nأنا: {ans}\nمفتّش: {fb}"
                render_report(fb)

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
            render_report(preview)

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
        _ensure_env_key()
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
        if not ai_core.has_key(provider_name):
            st.error("ضع مفتاح الـ API أولاً.")
        elif not fc_topic.strip():
            st.warning("اكتب الفكرة أولاً.")
        else:
            _ensure_env_key()
            with st.container(border=True):
                out = st.write_stream(content_factory.stream_content(fc_type, fc_topic))
            if out and not out.startswith("⚠️"):
                database.save_content(fc_type, fc_topic, out)
                st.download_button("⬇️ تحميل", out,
                                   file_name=f"content_{datetime.now():%Y%m%d_%H%M}.txt")
                st.toast("اتحفظ في الأرشيف ✅", icon="✅")

    saved = database.list_content(limit=20)
    if saved:
        with st.expander(f"🗂️ أرشيف المحتوى ({len(saved)})"):
            for c in saved:
                st.markdown(f"**{c['content_type']} — {c['topic']}**")
                st.caption(c["created_at"])
                render_report(c["body"])

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
        render_report(
            f"**{res['name']}** ({badge.get(res['status'], res['status'])})\n\n{res['result']}"
        )

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
    agent_mode = st.toggle(
        "🤖 وضع الوكيل المحلي — صلاحيات حساب Mac الحالي",
        value=True,
        help="يستطيع استخدام أدوات Oracle وقراءة/كتابة الملفات وتشغيل البرامج والأوامر بصلاحيات حساب macOS الحالي. لا يتجاوز موافقات macOS أو صلاحيات root."
    )
    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = []
    # Bound conversation context to 12 recent turns to control latency and token cost.
    st.session_state.chat_msgs = st.session_state.chat_msgs[-24:]
    memory_scope = (os.environ.get("ORACLE_MEMORY_SCOPE") or "user:oracle-owner").strip()
    cc = st.columns([1, 5])
    if cc[0].button("🧹 مسح الشات"):
        st.session_state.chat_msgs = []
    for m in st.session_state.chat_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    prompt = st.chat_input("اكتب رسالتك…")
    if prompt:
        if not ai_core.has_key(provider_name):
            st.error("ضع مفتاح الـ API أولاً في القائمة الجانبية.")
        else:
            _ensure_env_key()
            st.session_state.chat_msgs.append({"role": "user", "content": prompt})
            st.session_state.chat_msgs = st.session_state.chat_msgs[-24:]
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                if agent_mode:
                    try:
                        with st.spinner("🤖 Oracle بيخطط وينفّذ على جهازك المحلي…"):
                            agent_result = agent_orchestrator.run(
                                prompt,
                                memory_scope=memory_scope,
                                max_steps=None,
                            )
                        out = agent_result["answer"]
                        st.markdown(out)
                        if agent_result.get("steps"):
                            with st.expander("🔎 تفاصيل خطوات الوكيل"):
                                for index, step in enumerate(agent_result["steps"], start=1):
                                    st.markdown(
                                        f"**{index}. {step['name']}** — {step['status']}"
                                    )
                                    st.caption(f"المدخل: {step['input'][:300]}")
                                    st.write(step["result"][:1200])
                        elif agent_result.get("clarifying_question"):
                            st.info(agent_result["clarifying_question"])
                    except agent_orchestrator.AgentError as exc:
                        out = f"تعذّر تنفيذ وضع الوكيل: {exc}"
                        st.warning(out)
                    except Exception as exc:
                        out = f"حدث خطأ غير متوقع في الوكيل: {type(exc).__name__}"
                        st.error(out)
                else:
                    msgs = [{"role": "system", "content": ai_core.system_prompt(chat_mode)}] \
                        + st.session_state.chat_msgs
                    out = st.write_stream(
                        ai_core.stream(msgs, memory_scope=memory_scope)
                    )
            st.session_state.chat_msgs.append({"role": "assistant", "content": out})
            st.session_state.chat_msgs = st.session_state.chat_msgs[-24:]

    with st.expander("🧠 الذاكرة الشخصية — أنت تتحكم فيما يُحفظ", expanded=False):
        st.caption("الذكريات المحفوظة صراحةً فقط تدخل في سياق المحادثة. لا تُحفظ رسائلك تلقائياً.")
        with st.form("oracle_memory_write", clear_on_submit=True):
            memory_content = st.text_area(
                "معلومة أو تفضيل أو هدف تريد من Oracle تذكّره",
                max_chars=4000,
            )
            memory_type_label = st.selectbox(
                "نوع الذاكرة", ["حقيقة", "تفضيل", "هدف"]
            )
            memory_saved = st.form_submit_button("💾 احفظ في ذاكرتي")
        if memory_saved:
            type_map = {"حقيقة": "fact", "تفضيل": "preference", "هدف": "goal"}
            try:
                record = memory.write_memory(
                    memory_content,
                    type_map[memory_type_label],
                    memory_scope,
                    "manual",
                )
                st.success(f"اتحفظت الذاكرة رقم {record.id}.")
                st.rerun()
            except memory.MemoryValidationError as exc:
                st.error(str(exc))

        saved_memories = memory.list_memories(memory_scope, limit=50)
        if saved_memories:
            st.dataframe(
                [{
                    "ID": item.id,
                    "النوع": {"fact": "حقيقة", "preference": "تفضيل", "goal": "هدف"}.get(item.memory_type, item.memory_type),
                    "المحتوى": item.content,
                    "المصدر": item.source,
                    "التاريخ": item.created_at,
                } for item in saved_memories],
                use_container_width=True,
                hide_index=True,
            )
            memory_labels = {
                item.id: f"#{item.id} — {item.content[:70]}"
                for item in saved_memories
            }
            selected_memory = st.selectbox(
                "اختر ذاكرة لحذفها",
                options=list(memory_labels),
                format_func=lambda item_id: memory_labels[item_id],
                key="oracle_memory_delete_id",
            )
            if st.button("🗑️ احذف الذاكرة المختارة", key="oracle_memory_delete"):
                memory.delete_memory(selected_memory, memory_scope)
                st.success("تم حذف الذاكرة.")
                st.rerun()
        else:
            st.caption("لسه مفيش ذكريات محفوظة.")

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
                render_report(p)
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
            render_report(rev)

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
            render_report(art["content"])
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
            render_report(pred["advice"])
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
            render_report(out)

    elif tool == "🗺️ خريطة المستقبل (4 مستويات)":
        g = st.text_input("هدفك الأكبر", placeholder="أبقى مهندس AI وأبني دخل سحابي")
        sk = st.text_input("مهاراتك الحالية")
        if st.button("🧱 ابنِ الخريطة", use_container_width=True):
            with st.spinner("ببني خريطة 10 سنين → اليوم…"):
                res = discipline_oracle.generate_hyper_realistic_roadmap(g, sk)
            render_report(res["text"])
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
            render_report(discipline_oracle.daily_course_enforcer(courses, a, b))

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
            render_report(sc)

    elif tool == "💬 مسودّات ردود الكومنتات":
        cmnts = st.text_area("الصق الكومنتات (كومنت لكل سطر)", height=140)
        if st.button("✍️ اكتب مسودّات الردود", use_container_width=True):
            render_report(discipline_oracle.youtube_comment_drafts(cmnts))

    else:  # موجّه التركيز الصحّي
        ctx = st.text_area("إيه اللي حاسس إنه بيشتتك أو محتاج تركّز عليه؟", height=100)
        if st.button("🎯 وجّهني", use_container_width=True):
            with st.spinner("…"):
                out = discipline_oracle.sovereign_focus_prompt(ctx)
            render_report(out)

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
    st.markdown("#### 🧠 إعدادات النماذج والوكلاء — محلية")
    st.caption("احفظ المفاتيح وأسماء النماذج في ~/.personal_ai_oracle/.env. لا تضعها في Git.")
    st.code(
        "ORACLE_DEFAULT_PROVIDER=ollama\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1\n"
        "OLLAMA_MODEL=اسم-موديل-مثبت-في-Ollama\n"
        "OPENROUTER_API_KEY=...\n"
        "OPENAI_API_KEY=...\n"
        "GEMINI_API_KEY=...\n"
        "ORACLE_AGENT_PLANNER_PROVIDER=...\n"
        "ORACLE_AGENT_PLANNER_MODEL=...\n"
        "ORACLE_AGENT_RESEARCHER_PROVIDER=...\n"
        "ORACLE_AGENT_RESEARCHER_MODEL=...\n"
        "ORACLE_AGENT_CODER_PROVIDER=...\n"
        "ORACLE_AGENT_CODER_MODEL=...\n"
        "ORACLE_AGENT_REVIEWER_PROVIDER=...\n"
        "ORACLE_AGENT_REVIEWER_MODEL=...\n"
        "ORACLE_MAX_AGENT_STEPS=12\n"
        "SCAN_INTERVAL_HOURS=12",
        language="bash",
    )

    st.divider()
    st.markdown("#### 🔐 الخزنة المشفّرة (password_vault)")
    reveal = st.toggle("اعرض كلمات السر (يتطلب ORACLE_VAULT_KEY)", value=False)
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


# ====================== Oracle Control Center ======================
with tab_oracle:
    import knowledge_graph
    import workflow_ledger
    import task_control_center
    import task_execution
    import agent_task_execution
    import deep_research
    import execution_policy
    import model_observability

    oracle_scope = (
        os.environ.get("ORACLE_MEMORY_SCOPE")
        or os.environ.get("ORACLE_WORKFLOW_SCOPE")
        or "user:oracle-owner"
    ).strip()
    st.markdown("### 🔮 Oracle Control Center")
    st.caption(
        "لوحة تشغيل وذاكرة وبحث. القراءة بلا موافقة؛ الكتابة والأوامر المحددة داخل Workspace موثوق قد تعمل تلقائياً؛ الحذف يحتاج موافقة صريحة دائماً."
    )

    st.divider()
    st.markdown("#### 🛡️ صندوق موافقات التنفيذ المحلي")
    try:
        approval_items = execution_policy.list_approvals(oracle_scope, include_decided=True, limit=50)
    except Exception as exc:
        approval_items = []
        st.error(f"تعذّر تحميل طلبات الموافقة: {type(exc).__name__}")

    pending_items = [item for item in approval_items if item["status"] == "pending"]
    approved_items = [item for item in approval_items if item["status"] == "approved"]
    ap1, ap2 = st.columns(2)
    ap1.metric("تحتاج موافقتك", len(pending_items))
    ap2.metric("موافقات جاهزة للاستكمال", len(approved_items))
    if not approval_items:
        st.info("لا توجد إجراءات محلية معلّقة. الحذف يحتاج موافقة صريحة دائماً؛ أما الكتابة والنقل والأوامر فتخضع لقائمة الأدوات ومساحات العمل الموثوقة.")
    for item in approval_items:
        approval_label = f"{item['tool_id']} · {item['approval_id'][:10]} · {item['status']}"
        with st.expander(approval_label, expanded=item["status"] == "pending"):
            st.json(item["preview"])
            expires = datetime.fromtimestamp(item["expires_at"]).strftime("%Y-%m-%d %H:%M:%S")
            st.caption(f"بصمة العملية: {item['action_digest'][:16]} · تنتهي: {expires}")
            if item["status"] == "pending":
                approve_col, deny_col = st.columns(2)
                if approve_col.button("أوافق على العملية دي فقط", key=f"oracle_approve_{item['approval_id']}"):
                    changed = execution_policy.decide_approval(item["approval_id"], scope=oracle_scope, approve=True)
                    if changed:
                        st.success("تمت الموافقة على العملية المحددة لمرة واحدة.")
                        st.rerun()
                    else:
                        st.warning("انتهت صلاحية الطلب أو تم اتخاذ قرار بشأنه بالفعل.")
                if deny_col.button("ارفض العملية", key=f"oracle_deny_{item['approval_id']}"):
                    changed = execution_policy.decide_approval(item["approval_id"], scope=oracle_scope, approve=False)
                    if changed:
                        st.warning("تم رفض العملية.")
                        st.rerun()
                    else:
                        st.info("الطلب لم يعد في حالة انتظار.")
            elif item["status"] == "approved":
                checkpoint = item.get("checkpoint_id") or ""
                if checkpoint:
                    if st.button("Resume — استكمال المهمة", key=f"oracle_resume_{item['approval_id']}"):
                        try:
                            with st.spinner("يتم استكمال المهمة من Checkpoint مشفّر…"):
                                resumed = agent_orchestrator.resume(checkpoint, scope=oracle_scope)
                            st.markdown(resumed.get("answer", ""))
                            st.success("انتهى استكمال سير العمل.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"تعذّر استكمال المهمة: {type(exc).__name__}")
                else:
                    st.info("تمت الموافقة، لكن لا يوجد Checkpoint صالح؛ أعد إرسال المهمة من وضع Mac المحلي.")
    st.caption(
        "الموافقة مربوطة ببصمة SHA-256 للمدخلات الدقيقة، وتُستهلك مرة واحدة. "
        "محتوى الملف المراد كتابته لا يظهر داخل معاينة الموافقة."
    )

    st.divider()
    st.markdown("#### 📈 أداء النماذج والمزوّدين")
    try:
        model_rows = model_observability.summary(oracle_scope, limit=1000)
        if model_rows:
            st.dataframe(
                [{
                    "المزوّد": row["provider"],
                    "النموذج": row["model"],
                    "الطلبات": row["requests"],
                    "نسبة النجاح": f"{row['success_rate']:.1%}",
                    "الأخطاء": row["errors"],
                    "P50 ms": row["p50_latency_ms"],
                    "P95 ms": row["p95_latency_ms"],
                } for row in model_rows],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("ستظهر إحصائيات الأداء بعد أول استدعاء لنموذج.")
    except Exception as exc:
        st.warning(f"تعذّر تحميل إحصائيات النماذج: {type(exc).__name__}")
    st.caption("المقاييس لا تحتوي على نصوص الطلبات أو الردود أو محتوى الملفات.")

    try:
        graph_entities = knowledge_graph.list_entities(oracle_scope, limit=100)
        graph_relations = knowledge_graph.list_relations(oracle_scope, limit=200)
        workflow_runs = workflow_ledger.list_runs(oracle_scope, limit=30)
    except Exception as exc:
        graph_entities, graph_relations, workflow_runs = [], [], []
        st.error(f"تعذّر تحميل بيانات مركز التحكم: {type(exc).__name__}")

    routing_enabled = os.environ.get("ORACLE_AUTO_MODEL_ROUTING", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    tools_count = len(agent_orchestrator.available_tools())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("الأدوات المتاحة", tools_count)
    m2.metric("الوكل المتخصصون", len(agent_profiles.ROLE_DEFAULTS))
    m3.metric("كيانات الذاكرة المعرفية", len(graph_entities))
    m4.metric("سجلات التشغيل", len(workflow_runs))
    st.caption(
        f"التوجيه التلقائي للنماذج: {'مفعّل' if routing_enabled else 'متوقف'} · "
        f"نطاق البيانات: {oracle_scope}"
    )

    st.divider()
    st.markdown("#### 🧭 سجل تنفيذ الوكيل")
    if workflow_runs:
        st.dataframe(
            [{
                "Workflow ID": item["workflow_id"][:12],
                "الحالة": item["status"],
                "الخطوات القصوى": item["max_steps"],
                "البداية": item["created_at"],
                "آخر تحديث": item["updated_at"],
                "رمز الخطأ": item["error_code"] or "—",
            } for item in workflow_runs],
            use_container_width=True,
            hide_index=True,
        )
        run_ids = [item["workflow_id"] for item in workflow_runs]
        selected_run = st.selectbox(
            "تفاصيل تشغيل محدد",
            run_ids,
            format_func=lambda value: value[:12],
            key="oracle_selected_workflow",
        )
        steps = workflow_ledger.list_steps(oracle_scope, selected_run)
        if steps:
            st.dataframe(
                [{
                    "الخطوة": item["step_index"] + 1,
                    "الأداة": item["tool_id"],
                    "الحالة": item["status"],
                    "المدة (ms)": item["duration_ms"],
                    "بصمة المدخل": item["input_digest"][:12],
                    "بصمة الناتج": item["output_digest"][:12],
                    "آخر تحديث": item["updated_at"],
                } for item in steps],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("لا توجد خطوات مسجلة لهذا التشغيل حتى الآن.")
    else:
        st.info("لا توجد سجلات تشغيل بعد. أول مهمة ينفذها الوكيل ستظهر هنا.")
    st.caption(
        "السجل يحفظ بصمات SHA-256 وبيانات التشغيل فقط، وليس نص المهمة أو محتوى الملفات أو مخرجات الأدوات."
    )

    st.divider()
    st.markdown("#### 🧵 Durable Task Queue — المهام الدائمة")
    st.caption(
        "إنشاء مهام البحث وتشغيل مهمة واحدة يتم بطلب صريح منك. لا توجد خدمة خلفية أو Worker دائم."
    )
    if "oracle_research_idempotency_key" not in st.session_state:
        st.session_state["oracle_research_idempotency_key"] = uuid.uuid4().hex
    with st.expander("إنشاء مهمة بحث دائمة", expanded=False):
        with st.form("oracle_create_research_task"):
            research_query = st.text_area(
                "سؤال البحث", max_chars=500,
                placeholder="اكتب سؤال البحث الذي تريد من Oracle دراسته..."
            )
            research_col1, research_col2 = st.columns(2)
            research_max_queries = research_col1.slider(
                "عدد استعلامات البحث", min_value=1, max_value=4, value=3
            )
            research_max_sources = research_col2.slider(
                "أقصى عدد مصادر", min_value=1, max_value=12, value=8
            )
            research_fetch_pages = st.checkbox("استخراج نص الصفحات المختارة", value=True)
            research_verify_claims = st.checkbox("تشغيل تقييم الأدلة والادعاءات", value=True)
            research_submitted = st.form_submit_button("إضافة إلى قائمة المهام")
        if research_submitted:
            try:
                created_graph = task_execution.create_research_graph(
                    oracle_scope,
                    f"control-center-research-{st.session_state['oracle_research_idempotency_key']}",
                    research_query,
                    max_queries=research_max_queries,
                    max_sources=research_max_sources,
                    fetch_pages=research_fetch_pages,
                    verify_claims=research_verify_claims,
                )
                st.session_state["oracle_research_idempotency_key"] = uuid.uuid4().hex
                st.success(f"تم إنشاء مهمة البحث. Graph ID: {created_graph.graph_id[:12]}")
                st.rerun()
            except Exception as exc:
                st.error(f"تعذّر إنشاء المهمة: {type(exc).__name__}")

    if "oracle_agent_idempotency_key" not in st.session_state:
        st.session_state["oracle_agent_idempotency_key"] = uuid.uuid4().hex
    with st.expander("تخطيط مهمة متعددة الوكلاء (Autonomous Task Planner)", expanded=False):
        st.caption(
            "حوّل الطلب إلى DAG من خطوات متخصصة مترابطة. كل خطوة ونتيجتها تُحفظ مشفّرة، "
            "والمراجع النهائي خطوة مستقلة. لا يتم تشغيل أي مهمة تلقائياً."
        )
        with st.form("oracle_create_agent_task_graph"):
            agent_request = st.text_area(
                "المهمة المطلوبة من Oracle",
                max_chars=8000,
                placeholder="اشرح النتيجة المطلوبة، وسيقوم Planner بتقسيمها إلى خطوات متخصصة...",
                key="oracle_agent_request",
            )
            agent_max_steps = st.slider(
                "الحد الأقصى لخطوات الوكلاء",
                min_value=1,
                max_value=8,
                value=5,
                key="oracle_agent_max_steps",
            )
            agent_submitted = st.form_submit_button("حلّل الطلب وأنشئ Task DAG")
        if agent_submitted:
            try:
                with st.spinner("Planner بيحلل الطلب ويبني DAG..."):
                    created_agent_graph = agent_task_execution.create_agent_graph(
                        oracle_scope,
                        f"control-center-agent-{st.session_state['oracle_agent_idempotency_key']}",
                        agent_request,
                        max_steps=agent_max_steps,
                    )
                st.session_state["oracle_agent_idempotency_key"] = uuid.uuid4().hex
                st.success(
                    f"تم حفظ Task DAG مشفّر. Graph ID: {created_agent_graph.graph_id[:12]} "
                    f"· عدد المهام: {created_agent_graph.task_count} (بما فيها المراجعة النهائية)"
                )
                st.rerun()
            except Exception as exc:
                st.error(f"تعذّر إنشاء Task DAG: {type(exc).__name__}")

    try:
        task_graph_rows = task_control_center.list_graph_summaries(oracle_scope, limit=50)
    except Exception as exc:
        task_graph_rows = []
        st.error(f"تعذّر تحميل قائمة المهام: {type(exc).__name__}")

    if task_graph_rows:
        queue_active = sum(item["status"] == "active" for item in task_graph_rows)
        queue_paused = sum(item["status"] == "paused" for item in task_graph_rows)
        queue_pending = sum(item["pending_count"] for item in task_graph_rows)
        queue_failed = sum(item["failed_count"] + item["blocked_count"] for item in task_graph_rows)
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Task Graphs", len(task_graph_rows))
        q2.metric("نشطة", queue_active)
        q3.metric("متوقفة مؤقتًا", queue_paused)
        q4.metric("مهام معلّقة", queue_pending)
        if queue_pending:
            if st.button("تشغيل مهمة بحث واحدة الآن", key="oracle_dispatch_one_research_task"):
                try:
                    dispatched = task_execution.dispatch_research_once(
                        oracle_scope, f"control-center-{uuid.uuid4().hex[:16]}"
                    )
                    if dispatched is None:
                        st.info("لا توجد مهمة بحث مسجلة وجاهزة للتشغيل حالياً.")
                    else:
                        st.success(
                            f"انتهى التشغيل المحدود: {dispatched.task_key} · {dispatched.status}"
                        )
                    st.rerun()
                except Exception as exc:
                    st.error(f"تعذّر تشغيل المهمة: {type(exc).__name__}")
        st.dataframe(
            [{
                "Graph": item["graph_id"][:12],
                "الحالة": item["status"],
                "عدد المهام": item["task_count"],
                "نجحت": item["succeeded_count"],
                "فشلت": item["failed_count"],
                "محجوبة": item["blocked_count"],
                "قيد الانتظار/التنفيذ": item["pending_count"],
                "آخر تحديث": item["updated_at"],
            } for item in task_graph_rows],
            use_container_width=True,
            hide_index=True,
        )
        graph_labels = {
            item["graph_id"]: f"{item['graph_id'][:12]} · {item['status']} · {item['task_count']} tasks"
            for item in task_graph_rows
        }
        selected_graph_id = st.selectbox(
            "تفاصيل Task Graph",
            list(graph_labels),
            format_func=lambda value: graph_labels.get(value, value[:12]),
            key="oracle_durable_task_graph",
        )
        try:
            task_detail = task_control_center.get_graph_detail(
                oracle_scope, selected_graph_id
            )
        except Exception as exc:
            task_detail = None
            st.error(f"تعذّر تحميل تفاصيل المهام: {type(exc).__name__}")

        if task_detail:
            selected_graph = task_detail["graph"]
            task_rows = task_detail["tasks"]
            st.dataframe(
                [{
                    "Task": item["task_key"],
                    "النوع": item["task_type"],
                    "الحالة": item["status"],
                    "المحاولات": f"{item['attempt_count']}/{item['max_attempts']}",
                    "Retry Safe": item["retry_safe"],
                    "Worker": item["lease_owner"] or "—",
                    "رمز الخطأ": item["last_error_code"] or "—",
                } for item in task_rows],
                use_container_width=True,
                hide_index=True,
            )

            is_agent_graph = any(
                item["task_type"] in {
                    agent_task_execution.TASK_TYPE_AGENT_STEP,
                    agent_task_execution.TASK_TYPE_AGENT_REVIEW,
                }
                for item in task_rows
            )
            if is_agent_graph:
                st.markdown("#### 🤖 نتائج الوكلاء والمراجع النهائي")
                if selected_graph["status"] == "active" and selected_graph["pending_count"] > 0:
                    if st.button(
                        "تشغيل حتى 3 خطوات وكلاء جاهزة الآن",
                        key=f"oracle_dispatch_agent_batch_{selected_graph_id}",
                    ):
                        try:
                            with st.spinner("يتم تشغيل دفعة محدودة حسب الـDependencies..."):
                                agent_dispatches = agent_task_execution.dispatch_agent_tasks(
                                    oracle_scope,
                                    f"control-center-agent-{uuid.uuid4().hex[:16]}",
                                    max_tasks=3,
                                )
                            if agent_dispatches:
                                st.success(
                                    "نتيجة الدفعة: " + " · ".join(
                                        f"{item.task_key}: {item.status}" for item in agent_dispatches
                                    )
                                )
                            else:
                                st.info("لا توجد خطوة وكلاء جاهزة للتشغيل حالياً.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"تعذّر تشغيل دفعة الوكلاء: {type(exc).__name__}")
                try:
                    agent_graph_result = agent_task_execution.get_agent_graph_result(
                        oracle_scope, selected_graph_id
                    )
                except Exception as exc:
                    agent_graph_result = None
                    st.warning(f"تعذّر تحميل نتائج الوكلاء: {type(exc).__name__}")
                if agent_graph_result:
                    st.caption(
                        f"تم تنفيذ {agent_graph_result['succeeded_count']} من "
                        f"{agent_graph_result['task_count']} مهام · "
                        f"المتبقي {agent_graph_result['pending_count']} · "
                        f"الفاشل {agent_graph_result['failed_count']} · "
                        f"المحجوب {agent_graph_result['blocked_count']}"
                    )
                    for agent_task in agent_graph_result["tasks"]:
                        if agent_task["result"]:
                            with st.expander(
                                f"{agent_task['task_key']} · {agent_task['result']['agent_role']}"
                            ):
                                st.markdown(agent_task["result"]["output"])
                    final_review = agent_graph_result.get("final_review")
                    if final_review:
                        if agent_graph_result["accepted"]:
                            st.success("المراجع النهائي قبل اكتمال التغطية المطلوبة.")
                        elif final_review["decision"] == "needs_revision":
                            st.warning("المراجع النهائي طلب تعديلات؛ لا تعتبر المهمة مقبولة بعد.")
                        else:
                            st.warning("المراجع النهائي وجد أن التغطية غير مكتملة.")
                        st.markdown(final_review["summary"])
                        if final_review["issues"]:
                            st.markdown("**نقاط تحتاج معالجة:**")
                            for issue in final_review["issues"]:
                                st.markdown(f"- {issue}")
                        st.caption("المراجعة تقيس اكتمال الطلب والاتساق الداخلي فقط، ولا تثبت صحة الحقائق.")
            action_cols = st.columns(3)
            if selected_graph["status"] == "active":
                if action_cols[0].button(
                    "Pause Graph",
                    key=f"oracle_task_pause_{selected_graph_id}",
                ):
                    try:
                        task_control_center.transition_graph(
                            oracle_scope, selected_graph_id, "pause"
                        )
                        st.success("تم إيقاف جدولة المهام الجديدة. المهام الجارية قد تكمل عملها.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"تعذّر إيقاف الجدولة: {type(exc).__name__}")
            elif selected_graph["status"] == "paused":
                if action_cols[0].button(
                    "Resume Graph",
                    key=f"oracle_task_resume_{selected_graph_id}",
                ):
                    try:
                        task_control_center.transition_graph(
                            oracle_scope, selected_graph_id, "resume"
                        )
                        st.success("تم استئناف جدولة المهام.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"تعذّر استئناف الجدولة: {type(exc).__name__}")

            can_cancel = selected_graph["status"] in {"active", "paused"}
            confirm_cancel = action_cols[1].checkbox(
                "تأكيد الإلغاء",
                key=f"oracle_task_cancel_confirm_{selected_graph_id}",
                disabled=not can_cancel,
            )
            if action_cols[2].button(
                "Cancel Graph",
                key=f"oracle_task_cancel_{selected_graph_id}",
                disabled=(not can_cancel or not confirm_cancel),
            ):
                try:
                    task_control_center.transition_graph(
                        oracle_scope, selected_graph_id, "cancel"
                    )
                    st.warning("تم إلغاء الجدولة وإبطال الـLeases. الإجراء الخارجي الجاري يحتاج إيقافًا تعاونيًا.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"تعذّر إلغاء Graph: {type(exc).__name__}")

            if task_rows:
                task_labels = {
                    item["task_id"]: f"{item['task_key']} · {item['status']}"
                    for item in task_rows
                }
                selected_task_id = st.selectbox(
                    "سجل محاولات مهمة",
                    list(task_labels),
                    format_func=lambda value: task_labels.get(value, value[:12]),
                    key=f"oracle_task_attempt_select_{selected_graph_id}",
                )
                try:
                    attempts = task_control_center.list_task_attempts(
                        oracle_scope, selected_task_id, limit=5
                    )
                    if attempts:
                        st.dataframe(
                            [{
                                "المحاولة": item["attempt_number"],
                                "Worker": item["worker_id"],
                                "الحالة": item["status"],
                                "رمز الخطأ": item["error_code"] or "—",
                                "المدة ms": item["duration_ms"],
                                "Result Digest": (item["result_digest"] or "")[:12],
                                "بدأت": item["started_at"],
                                "انتهت": item["finished_at"] or "—",
                            } for item in attempts],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("لا توجد محاولات مسجلة لهذه المهمة.")
                except Exception as exc:
                    st.warning(f"تعذّر تحميل محاولات المهمة: {type(exc).__name__}")

                try:
                    research_result = task_execution.get_research_result(
                        oracle_scope, selected_task_id
                    )
                    if research_result:
                        st.markdown("##### نتيجة البحث المحفوظة")
                        st.caption(f"حالة التقرير: {research_result['status']}")
                        st.write(research_result["answer"])
                        if research_result["key_findings"]:
                            st.markdown("**أهم النتائج**")
                            for finding in research_result["key_findings"]:
                                st.write(f"• {finding}")
                        if research_result["citations"]:
                            st.markdown("**المصادر المستشهد بها**")
                            st.dataframe(research_result["citations"], use_container_width=True, hide_index=True)
                        st.caption("ملخص التقييم لا يثبت الحقيقة؛ راجع حدود الأدلة والتحقق الدلالي.")
                        st.json({
                            "evidence": research_result["evidence_summary"],
                            "quality": research_result["quality_summary"],
                            "semantic": research_result["semantic_summary"],
                            "freshness": research_result["freshness_summary"],
                        })
                except Exception as exc:
                    st.warning(f"تعذّر تحميل نتيجة البحث: {type(exc).__name__}")
            if queue_failed:
                st.caption(f"إجمالي المهام الفاشلة أو المحجوبة في النطاق: {queue_failed}")
    else:
        st.info("لا توجد Task Graphs في هذا النطاق حتى الآن.")

    st.caption(
        "التشغيل يتم لمهمة واحدة فقط عند الضغط على الزر. لا توجد جدولة تلقائية أو خدمة دائمة؛ النتائج البحثية تُعرض بملخص محدود داخل نطاق المالك."
    )

    st.divider()
    st.markdown("#### 🧠 Knowledge Graph — إدارة المعرفة")
    with st.expander("إضافة كيان جديد", expanded=False):
        with st.form("oracle_add_knowledge_entity"):
            entity_name = st.text_input("اسم الكيان", max_chars=180)
            entity_type = st.selectbox(
                "نوع الكيان",
                ["person", "project", "organization", "skill", "topic",
                 "place", "tool", "concept", "event", "custom"],
            )
            entity_saved = st.form_submit_button("حفظ الكيان")
        if entity_saved:
            try:
                saved_entity = knowledge_graph.add_entity(
                    oracle_scope, entity_name, entity_type
                )
                st.success(f"تم حفظ «{saved_entity.name}» بالمعرّف #{saved_entity.id}.")
                st.rerun()
            except Exception as exc:
                st.error(f"تعذّر حفظ الكيان: {type(exc).__name__}: {exc}")

    graph_entities = knowledge_graph.list_entities(oracle_scope, limit=100)
    if graph_entities:
        st.dataframe(
            [{
                "ID": item.id,
                "الاسم": item.name,
                "النوع": item.entity_type,
                "آخر تحديث": item.updated_at,
            } for item in graph_entities],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("ابدأ بإضافة مشاريع أو أشخاص أو مؤسسات أو مهارات تريد ربطها ببعضها.")

    if len(graph_entities) >= 2:
        labels = {
            f"#{item.id} · {item.name} ({item.entity_type})": item.id
            for item in graph_entities
        }
        with st.expander("إنشاء علاقة بين كيانين", expanded=False):
            with st.form("oracle_add_knowledge_relation"):
                source_label = st.selectbox("من", list(labels), key="oracle_relation_source")
                target_options = [key for key in labels if labels[key] != labels[source_label]]
                target_label = st.selectbox("إلى", target_options, key="oracle_relation_target")
                relation_type = st.text_input(
                    "نوع العلاقة (مثال: works_on / uses / belongs_to)",
                    value="related_to",
                    max_chars=64,
                )
                relation_evidence = st.text_input(
                    "دليل أو ملاحظة اختيارية",
                    max_chars=2000,
                )
                relation_saved = st.form_submit_button("حفظ العلاقة")
            if relation_saved:
                try:
                    created = knowledge_graph.link_entities(
                        oracle_scope,
                        labels[source_label],
                        labels[target_label],
                        relation_type,
                        evidence=relation_evidence,
                    )
                    st.success("تم حفظ العلاقة." if created else "العلاقة موجودة بالفعل.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"تعذّر حفظ العلاقة: {type(exc).__name__}: {exc}")

    graph_relations = knowledge_graph.list_relations(oracle_scope, limit=100)
    if graph_relations:
        with st.expander(f"العلاقات المحفوظة ({len(graph_relations)})"):
            st.dataframe(
                [{
                    "من": item["source_name"],
                    "العلاقة": item["relation_type"],
                    "إلى": item["target_name"],
                    "الدليل": item["evidence"] or "—",
                } for item in graph_relations],
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("استرجاع سياق من الرسم المعرفي", expanded=False):
        graph_query = st.text_input(
            "ابحث في العلاقات والكيانات",
            key="oracle_graph_query",
        )
        if st.button("استرجاع السياق", key="oracle_graph_retrieve"):
            if graph_query.strip():
                graph_context = knowledge_graph.retrieve_context(
                    oracle_scope, graph_query, max_entities=5, max_relations=12
                )
                if graph_context:
                    st.code(graph_context)
                else:
                    st.info("لا توجد كيانات أو علاقات مطابقة في هذا النطاق.")

    st.divider()
    st.markdown("#### 🧑‍💻 خريطة النماذج والوكلاء")
    try:
        profile_rows = []
        for profile in agent_profiles.profile_catalog():
            prefix = agent_profiles.ROLE_DEFAULTS[profile["role"]][0]
            profile_rows.append({
                "الوكيل": profile["role"],
                "المهمة": profile["task_type"],
                "المزوّد الحالي": profile["provider"],
                "الموديل": profile["model"] or "افتراضي المزوّد",
                "الحرارة": profile["temperature"],
                "تخصيص مباشر": bool(
                    os.environ.get(f"{prefix}_PROVIDER")
                    or os.environ.get(f"{prefix}_MODEL")
                ),
            })
        st.dataframe(profile_rows, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"تعذّر عرض إعدادات الوكلاء: {type(exc).__name__}")

    tier_rows = []
    for tier in ("FAST", "BALANCED", "DEEP"):
        tier_rows.append({
            "المستوى": tier.lower(),
            "المزوّد": os.environ.get(f"ORACLE_PROVIDER_TIER_{tier}") or "الافتراضي",
            "الموديل": os.environ.get(f"ORACLE_MODEL_TIER_{tier}") or "الافتراضي",
        })
    st.dataframe(tier_rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### 🔬 بحث عميق متعدد المصادر")
    st.caption(
        "يجمع استعلامات ومصادر مستقلة، ويحاول استخراج الصفحات من متصفح Oracle المعزول، "
        "ثم يعرض مراجع قابلة للمراجعة. في وضع السحابة يحتاج استخراج الصفحات إلى اتصال الماك."
    )
    with st.form("oracle_deep_research_form"):
        research_question = st.text_area(
            "سؤال البحث",
            height=100,
            max_chars=500,
            placeholder="اكتب سؤالاً يحتاج إلى مقارنة مصادر وتحليل الأدلة…",
        )
        rc1, rc2, rc3 = st.columns(3)
        research_query_count = rc1.selectbox("عدد الاستعلامات", [2, 3, 4], index=1)
        research_source_count = rc2.selectbox("عدد المصادر الأقصى", [4, 6, 8, 10, 12], index=2)
        research_fetch = rc3.checkbox("استخراج محتوى الصفحات", value=True)
        run_research_button = st.form_submit_button("ابدأ البحث العميق")
    if run_research_button:
        if not research_question.strip():
            st.warning("اكتب سؤال البحث أولاً.")
        elif not ai_core.has_key(provider_name):
            st.warning("اضبط مزوّد الذكاء الاصطناعي قبل تشغيل التحليل.")
        else:
            try:
                with st.spinner("الباحث بيجمع المصادر ويفحص الأدلة…"):
                    research_report = deep_research.run_research(
                        research_question,
                        memory_scope=oracle_scope,
                        max_queries=research_query_count,
                        max_sources=research_source_count,
                        fetch_pages=research_fetch,
                    )
                if research_report["status"] == "success":
                    st.success("اكتمل البحث مع أدلة قابلة للمراجعة.")
                elif research_report["status"] == "partial":
                    st.warning("اكتمل البحث جزئياً؛ راجع القيود ومصادر النتائج.")
                else:
                    st.error("لم يتم العثور على مصادر بحث صالحة.")
                st.markdown(research_report["answer"])
                if research_report.get("key_findings"):
                    st.markdown("**أهم النتائج**")
                    for finding in research_report["key_findings"]:
                        st.markdown(f"- {finding}")
                if research_report.get("limitations"):
                    st.markdown("**حدود البحث**")
                    for limitation in research_report["limitations"]:
                        st.warning(limitation)
                if research_report.get("citations"):
                    st.markdown("**المراجع المستشهد بها**")
                    for citation in research_report["citations"]:
                        st.markdown(
                            f"- [{citation['id']}] [{citation['title']}]({citation['url']}) "
                            f"— {citation['page_status']}"
                        )
                with st.expander("كل المصادر التي جرى جمعها"):
                    st.dataframe(
                        [{
                            "المرجع": source["citation_id"],
                            "العنوان": source["title"],
                            "النطاق": source["domain"],
                            "حالة الصفحة": source["page_status"],
                            "الرابط": source["url"],
                        } for source in research_report["sources"]],
                        use_container_width=True,
                        hide_index=True,
                    )
            except Exception as exc:
                st.error(f"تعذّر تشغيل البحث: {type(exc).__name__}: {str(exc)[:300]}")
