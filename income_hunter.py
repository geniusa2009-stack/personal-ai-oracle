"""
income_hunter.py — ماكينة جني المال التلقائية (Autonomous Micro-SaaS & Monetization)
خمسة محرّكات دخل تعمل عبر OpenRouter + قاعدة البيانات:

  1) Freelance Proposal Machine  — مولّد عروض احترافي + تتبّع.
  2) Digital Products Hub        — تجميع e-books من بيانات الوكيل + روابط دفع + قمع مبيعات واتساب.
  3) Affiliate Marketing Agent   — صيد منتجات عمولة + مراجعات بالعامية بروابطك.
  4) Automated Media & AdSense   — مقالات SEO + نشر فعلي على WordPress (REST API).
  5) Financial Security Guard    — توقّع الأرباح ونصيحة المجال الأنسب.

⚠️ ملاحظات مسؤولة مدمجة في الكود:
  - كشط/إرسال العروض آلياً على Upwork/Fiverr/Mostaql يخالف شروطها وقد يحظر الحساب.
    لذلك المولّد يكتب العرض ويخزّنه ليُراجَع ويُرسل يدوياً (أو عبر API رسمي إن توفّر).
  - لا يتم تحريك أموال برمجياً؛ روابط الدفع هي روابط Gumroad/Stripe التي تنشئها أنت.
"""

import os
import json
import base64
from datetime import datetime, timedelta

import requests

import ai_core
import database

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PRODUCTS_DIR = os.environ.get("ORACLE_PRODUCTS_DIR",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "products"))

BUYER_TRIGGERS = ["سعر", "بكام", "كام", "اشتري", "اشترى", "حابب اخد", "عايز اشتري",
                  "الدفع", "رابط", "المنتج", "الكتاب", "الباقة", "اشتراك", "price", "buy"]


# ==========================================================================
# 1) Freelance Proposal Machine
# ==========================================================================
def tailor_proposal(project_desc: str, skills: str, rate, currency: str = "USD",
                    platform: str = "Upwork", profile: str = "", save: bool = True) -> str:
    """يقرأ شروط المشروع ويصوغ عرضاً مقنعاً مسعّراً. يُخزّن كمسودّة للمراجعة والإرسال."""
    instruction = (
        "إنت خبير فريلانس بتكتب Proposals بتكسب. اقرأ شروط المشروع، طابقها بمهارات "
        "المستخدم، واكتب عرضاً قصيراً مقنعاً: hook في أول سطر، فهم لمشكلة العميل، "
        "خطة تنفيذ مختصرة، دليل خبرة، وسعر واضح ودعوة لردّ. اكتبه احترافياً ومرتّباً."
    )
    payload = (f"المنصّة: {platform}\nمهارات المستخدم: {skills}\n"
               f"السعر المقترح: {rate} {currency}\n"
               + (f"نبذة المستخدم: {profile}\n" if profile else "")
               + f"\nوصف المشروع:\n{project_desc}")
    proposal = ai_core.llm(instruction, payload, mode="professional", temperature=0.7)
    if save and proposal and not proposal.startswith("⚠️"):
        database.add_proposal(platform, project_desc[:300], skills, rate, currency,
                              proposal, status="drafted")
    return proposal


def fetch_public_leads(skill: str, platform: str = "Upwork", limit: int = 6) -> list:
    """بحث استدلالي عن مشاريع منشورة علناً (best-effort). ليس كشطاً آلياً للمنصّات."""
    from search import web_search
    site = {"Upwork": "site:upwork.com", "Fiverr": "fiverr.com",
            "Mostaql": "mostaql.com"}.get(platform, "")
    rows = web_search(f"{skill} freelance project {site}".strip(), limit)
    leads = [{"title": r.get("title", ""), "url": r.get("url", "")}
             for r in rows if r.get("url")]
    return leads


# ==========================================================================
# 2) Digital Products Hub
# ==========================================================================
def _collect_source(source: str) -> list:
    """يجمّع أقيم البيانات اللي لقاها الوكيل لتحويلها لمنتج."""
    if source == "scholarships":
        return [{"t": s["name"], "u": s["url"], "d": s.get("requirements", "")}
                for s in database.list_discovered_scholarships(80)]
    if source == "content":
        return [{"t": f'{c["content_type"]} — {c["topic"]}', "u": "", "d": c["body"]}
                for c in database.list_content(50)]
    try:
        import db
        return [{"t": o["title"], "u": o["url"], "d": o.get("summary") or o.get("snippet", "")}
                for o in db.list_opportunities(limit=80)]
    except Exception:
        return []


def compile_ebook(title: str, source: str = "scholarships", price: float = 9.99,
                  currency: str = "USD") -> dict:
    """يحوّل بيانات الوكيل لكتاب إلكتروني HTML منسّق (Arabic-safe، اطبعه PDF بنقرة).
    يسجّل المنتج في digital_sales. يُعيد {path, items, product_id}."""
    items = _collect_source(source)
    os.makedirs(PRODUCTS_DIR, exist_ok=True)
    cards = ""
    for i, it in enumerate(items, 1):
        link = f'<a href="{it["u"]}">{it["u"]}</a>' if it["u"] else ""
        cards += (f'<div class="card"><h3>{i}. {it["t"]}</h3>'
                  f'<p>{(it["d"] or "")[:400]}</p>{link}</div>')
    html = f"""<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>{title}</title><style>
body{{font-family:Tajawal,Arial,sans-serif;max-width:820px;margin:40px auto;line-height:1.9;color:#1f2937}}
.cover{{background:linear-gradient(120deg,#4f46e5,#db2777);color:#fff;padding:50px;border-radius:18px;text-align:center}}
.cover h1{{font-size:34px;margin:0}} .card{{background:#f8fafc;border-right:5px solid #6366f1;
padding:16px 20px;border-radius:12px;margin:14px 0}} h3{{color:#4338ca;margin:0 0 6px}}
a{{color:#4f46e5;word-break:break-all}}</style></head><body>
<div class="cover"><h1>{title}</h1><p>دليل عملي من إعداد وكيلك الذكي · {datetime.now():%Y-%m-%d}</p></div>
<p>هذا الكتاب يجمع أقيم {len(items)} فرصة/مورد رصدها الوكيل تلقائياً.</p>
{cards}
<hr><p style="color:#9ca3af;font-size:12px">© {datetime.now():%Y} — كل الحقوق محفوظة.</p>
</body></html>"""
    safe = "".join(c if c.isalnum() else "_" for c in title)[:40] or "ebook"
    path = os.path.join(PRODUCTS_DIR, f"{safe}_{datetime.now():%Y%m%d_%H%M}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    pid = database.add_digital_product(title, price, currency, link=path)
    return {"path": path, "items": len(items), "product_id": pid}


def create_payment_link(product: str, price: float, currency: str = "USD") -> dict:
    """ينشئ/يجهّز رابط دفع. يدعم Gumroad API إن توفّر المفتاح، وإلا يعيد الهيكل والتعليمات."""
    gumroad_key = os.environ.get("GUMROAD_API_KEY", "")
    if gumroad_key:
        try:
            r = requests.post("https://api.gumroad.com/v2/products",
                              data={"access_token": gumroad_key, "name": product,
                                    "price": int(float(price) * 100), "currency": currency.lower()},
                              timeout=30)
            r.raise_for_status()
            data = r.json()
            return {"ok": True, "provider": "gumroad",
                    "url": data.get("product", {}).get("short_url", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    base = os.environ.get("PAYMENT_LINK", "")
    return {"ok": bool(base), "provider": "manual", "url": base,
            "note": "اضبط GUMROAD_API_KEY لإنشاء آلي، أو PAYMENT_LINK برابط دفعك الجاهز."}


def is_buyer_intent(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in BUYER_TRIGGERS)


def sales_funnel_reply(text: str) -> str:
    """قمع مبيعات واتساب: يشرح المنتج بالعامية ويرفق رابط الدفع/التحميل تلقائياً."""
    pay = os.environ.get("PAYMENT_LINK", "")
    download = os.environ.get("PRODUCT_DOWNLOAD_LINK", "")
    instruction = (
        "إنت بائع ودود بالعامية المصرية بتبيع منتجات رقمية (كتب منح وفرص وقوالب). "
        "ردّ على المهتم بحماس محترم، اشرح القيمة باختصار، اطمنه، وادعُه يتمّ الشراء. "
        "لو فيه رابط دفع/تحميل ضِفه في آخر الرد بوضوح."
    )
    links = ""
    if pay:
        links += f"\n\n🔗 رابط الشراء: {pay}"
    if download:
        links += f"\n📥 بعد الدفع التحميل من: {download}"
    reply = ai_core.llm(instruction, text + ("\n\n[روابط متاحة للإرفاق]" + links if links else ""),
                        mode="friendly")
    if links and links not in reply:
        reply += links
    return reply


# ==========================================================================
# 3) Affiliate Marketing Agent
# ==========================================================================
def find_affiliate_products(niche: str, limit: int = 6) -> list:
    from search import web_search
    rows = web_search(f"high commission affiliate program {niche} (amazon OR jumia OR courses OR hosting)",
                      limit)
    return [{"title": r.get("title", ""), "url": r.get("url", "")}
            for r in rows if r.get("url")]


def write_review(product: str, affiliate_link: str, tone: str = "مضحك ومقنع",
                 save: bool = True) -> str:
    """يكتب مراجعة بالعامية المصرية تتضمّن رابط الأفيليت بأسلوب مقنع."""
    instruction = (
        f"اكتب مراجعة منتج بالعامية المصرية بأسلوب {tone}: تجربة واقعية، مميزات وعيوب "
        "بصدق، ولمن يصلح، وادعُ للشراء عبر الرابط. ضِف الرابط بشكل طبيعي داخل النص وفي الآخر."
    )
    payload = f"المنتج: {product}\nرابط الأفيليت: {affiliate_link}"
    review = ai_core.llm(instruction, payload, mode="friendly", temperature=0.9)
    if save and review and not review.startswith("⚠️"):
        database.add_affiliate(product, affiliate_link, clicks=0, est_commission=0)
    return review


# ==========================================================================
# 4) Automated Media & AdSense Network
# ==========================================================================
def generate_seo_article(keyword: str, niche: str = "المنح والبيزنس",
                         lang: str = "العربية") -> dict:
    """يولّد مقالاً محسّناً لمحركات البحث: عنوان + وصف ميتا + المقال بعناوين فرعية."""
    instruction = (
        f"اكتب مقال SEO ب{lang} مستهدف الكلمة المفتاحية بدقة في مجال {niche}. "
        "ابدأ بسطر 'TITLE:' للعنوان، ثم 'META:' لوصف ميتا (<=155 حرف)، ثم المقال "
        "بعناوين H2 وفقرات مفيدة وكلمات مفتاحية طبيعية، 600-900 كلمة."
    )
    text = ai_core.llm(instruction, f"الكلمة المفتاحية: {keyword}", mode="professional",
                       temperature=0.7)
    title, meta, body = keyword, "", text
    for line in text.splitlines():
        if line.strip().upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()
        elif line.strip().upper().startswith("META:"):
            meta = line.split(":", 1)[1].strip()
    return {"title": title, "meta": meta, "content": text}


def publish_to_wordpress(title: str, content: str, status: str = "draft") -> dict:
    """نشر فعلي على WordPress عبر REST API (يتطلب WP_URL / WP_USER / WP_APP_PASSWORD)."""
    url = os.environ.get("WP_URL", "").rstrip("/")
    user = os.environ.get("WP_USER", "")
    app_pw = os.environ.get("WP_APP_PASSWORD", "")
    if not (url and user and app_pw):
        return {"ok": False, "scaffold": True,
                "note": "اضبط WP_URL و WP_USER و WP_APP_PASSWORD لتفعيل النشر التلقائي. "
                        "(الـ Application Password من إعدادات بروفايلك في ووردبريس)."}
    token = base64.b64encode(f"{user}:{app_pw}".encode()).decode()
    try:
        r = requests.post(f"{url}/wp-json/wp/v2/posts",
                          headers={"Authorization": f"Basic {token}",
                                   "Content-Type": "application/json"},
                          data=json.dumps({"title": title, "content": content,
                                           "status": status}), timeout=40)
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "id": data.get("id"), "link": data.get("link", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ==========================================================================
# 5) Financial Security Guard
# ==========================================================================
def predict_revenue() -> dict:
    """توقّع بسيط للأرباح الشهرية من بيانات آخر 30 يوماً + نصيحة المجال الأنسب."""
    sales = database.list_digital_sales(500)
    ads = database.list_ad_revenue(500)
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()

    def _recent_sum(rows, ts_key, amt_key, cond=lambda r: True):
        return sum((r.get(amt_key) or 0) for r in rows
                   if cond(r) and (r.get(ts_key) or "") >= cutoff)

    last30 = (_recent_sum(sales, "ts", "price", lambda r: r.get("status") == "sold")
              + _recent_sum(ads, "date", "amount"))
    daily = last30 / 30 if last30 else 0
    projected = round(daily * 30, 2)

    # أي مجال جايب أكتر؟
    summ = database.revenue_summary()
    channels = {"الفريلانس/العروض": summ["proposals_won"],
                "المنتجات الرقمية": summ["sold"],
                "الأفيليت": summ["affiliate_clicks"]}
    best = max(channels, key=channels.get) if any(channels.values()) else "المنتجات الرقمية"

    advice = ai_core.llm(
        "إنت مستشار دخل رقمي بالعامية المصرية. بناءً على الأرقام، انصح المستخدم بالمجال "
        "اللي يكثّف عليه الأسبوع ده وليه، في 3-4 جمل عملية.",
        f"المبيعات آخر 30 يوم: {last30}. القنوات: {json.dumps(channels, ensure_ascii=False)}. "
        f"الأفضل حالياً: {best}.", mode="coach") if ai_core.has_key() else \
        f"ركّز الأسبوع ده على «{best}» لأنه أكتر قناة بتجيب نتيجة عندك دلوقتي."

    return {"projected_month": projected, "last_30_days": round(last30, 2),
            "best_channel": best, "advice": advice}


if __name__ == "__main__":
    print("income_hunter ready. revenue:", database.revenue_summary())
