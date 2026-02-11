import streamlit as st
import asyncio
import sys
import os
import subprocess
import gc
from datetime import datetime

# --- 1. TARAYICI KURULUMU ---
def install_playwright_browser():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Browser install error: {e}")

if "browser_installed" not in st.session_state:
    with st.spinner("Sistem hazırlanıyor..."):
        install_playwright_browser()
        st.session_state["browser_installed"] = True

# --- 2. GÜVENLİK ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if not st.session_state['authenticated']:
    st.set_page_config(page_title="Giriş", layout="centered")
    st.title("🔒 Güvenli Giriş")
    pwd = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        if pwd == "üç":
            st.session_state['authenticated'] = True
            st.rerun()
        else: st.error("Hatalı şifre!")
    st.stop()

# --- 3. AYARLAR ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
import dns.resolver

BLOCKED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", 
    "youtube.com", "pinterest.com", "trendyol.com", "hepsiburada.com", 
    "n11.com", "amazon.com", "ciceksepeti.com", "getir.com", "yemeksepeti.com"
]

if 'results' not in st.session_state: st.session_state['results'] = []
if 'processed_urls' not in st.session_state: st.session_state['processed_urls'] = set()
if 'logs' not in st.session_state: st.session_state['logs'] = []

# --- YENİ LOG SİSTEMİ (Son 5 Satır) ---
def log_msg(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    # Yeni mesajı en sona ekle
    st.session_state['logs'].append(f"[{timestamp}] {msg}")
    # Sadece son 5 tanesini tut, gerisini sil (Hafıza koruma)
    if len(st.session_state['logs']) > 5:
        st.session_state['logs'] = st.session_state['logs'][-5:]

def verify_domain_mx(email):
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except: return False

def clean_obfuscated_email(text):
    return text.replace(" [at] ", "@").replace("(at)", "@").replace(" at ", "@").replace(" [dot] ", ".").replace("(dot)", ".").replace(" dot ", ".")

def extract_emails_from_page(page):
    found_emails = set()
    try:
        for link in page.locator("a[href^='mailto:']").all():
            href = link.get_attribute("href")
            if href and "@" in href:
                clean = href.replace("mailto:", "").split("?")[0].strip()
                found_emails.add(clean)
        content = clean_obfuscated_email(page.content())
        for email in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?!png|jpg|jpeg|gif|css|js)[a-zA-Z]{2,}', content):
            if len(email) < 50: found_emails.add(email)
    except: pass
    return list(found_emails)

def convert_df(df):
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Firmalar')
    return output.getvalue()

# --- ARAYÜZ ---
st.set_page_config(page_title="Joy Refund Ajanı", layout="wide")

st.markdown("""
<div style="position: fixed; top: 65px; right: 20px; z-index: 99999; background: rgba(255, 255, 255, 0.25); backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); font-size: 12px; font-weight: 600; color: #333; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    🚀 Made by ÜÇ & AI
</div>""", unsafe_allow_html=True)

st.title("☁️ Joy Refund Ajanı (Fix Modu)")

with st.sidebar:
    st.header("Ayarlar")
    city = st.text_input("İl", "İstanbul")
    district = st.text_input("İlçe", "Kadıköy")
    keyword = st.text_input("Sektör", "Giyim Mağazası")
    max_target = st.number_input("Hedef Mail Sayısı", 1, 1000, 20)
    st.divider()
    if st.button("Başlat", type="primary"):
        st.session_state['start_scraping'] = True
        st.session_state['results'] = []
        st.session_state['processed_urls'] = set()
        st.session_state['logs'] = []
        log_msg("Sistem başlatılıyor...")
    
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False
    
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        st.download_button("📥 Excel İndir", convert_df(df), "sonuc.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

c1, c2, c3 = st.columns(3)
c1.metric("Hedef", max_target)
stat_havuz = c2.metric("Havuzdaki Aday", 0)
stat_mail = c3.metric("✅ Bulunan", len(st.session_state['results']))

st.write("---")
# --- LOG PANELİ (Sadece 5 satır) ---
st.subheader("📟 Canlı İşlem Terminali")
log_placeholder = st.empty()
# -----------------------------------

st.subheader("Sonuçlar")
result_table = st.empty()
if len(st.session_state['results']) > 0:
    result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

def update_ui_logs():
    # Listeyi tersten göster ki en yeni en üstte olsun ya da düz liste
    log_text = "\n".join(st.session_state['logs'])
    log_placeholder.code(log_text, language="cmd")

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        context.set_default_timeout(20000)
        
        map_page = context.new_page()

        try:
            # 1. ARAMA
            search_query = f"{city} {district} {keyword}"
            log_msg(f"Google Maps'e gidiliyor: {search_query}")
            update_ui_logs()
            
            map_page.goto("https://www.google.com/maps?hl=tr")
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=5000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_query)
                map_page.keyboard.press("Enter")
            except: 
                log_msg("Hata: Arama kutusu bulunamadı.")
                update_ui_logs()
                st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. ZORLA HAVUZ DOLDURMA (Loop Buradaydı, Düzelttik)
            listings = []
            prev_count = 0
            fails = 0
            
            # Formül: 50 mail için en az 500 aday lazım. Yoksa başlama.
            min_required_pool = max_target * 10 
            log_msg(f"HEDEF: En az {min_required_pool} aday toplanmadan analiz başlamayacak.")
            update_ui_logs()
            
            while len(listings) < min_required_pool:
                if not st.session_state.get('start_scraping', False): break
                
                # Scroll
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(1)
                
                listings = map_page.locator('div[role="article"]').all()
                stat_havuz.metric("Havuzdaki Aday", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    log_msg(f"Liste yükleniyor... Deneme {fails}/20")
                    update_ui_logs()
                    
                    # Wiggle (Sallama) ve Zoom Out
                    map_page.mouse.wheel(0, -1000)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 5000)
                    
                    # 20 kere denedi hala gelmiyorsa mecburen çık
                    if fails > 20:
                        log_msg(f"Google daha fazla sonuç vermiyor. {len(listings)} aday ile devam.")
                        update_ui_logs()
                        break
                else:
                    fails = 0
                    if len(listings) % 50 == 0:
                        log_msg(f"Havuz büyüyor: {len(listings)} aday...")
                        update_ui_logs()
                
                prev_count = len(listings)

            # 3. ANALİZ (Havuz dolduktan sonra)
            log_msg(f"Analiz Başlıyor! Toplam Aday: {len(listings)}")
            update_ui_logs()
            
            visit_page = context.new_page()
            
            for idx, listing in enumerate(listings):
                if len(st.session_state['results']) >= max_target: 
                    log_msg("HEDEF BAŞARIYLA TAMAMLANDI!")
                    st.success("Bitti!"); st.session_state['start_scraping'] = False; break
                
                if not st.session_state.get('start_scraping', False): break
                
                if (idx % 10 == 0): gc.collect()

                try:
                    listing.click(timeout=3000)
                    time.sleep(0.5)
                    
                    website = None
                    try:
                        wb = map_page.locator('[data-item-id="authority"]').first
                        if wb.count() > 0: website = wb.get_attribute("href")
                    except: pass
                    
                    if not website: continue
                    clean_url = website.rstrip("/")
                    if clean_url in st.session_state['processed_urls']: continue
                    st.session_state['processed_urls'].add(clean_url)
                    
                    if any(d in website for d in BLOCKED_DOMAINS): continue
                    
                    name = "Bilinmiyor"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    log_msg(f"Kontrol ({idx}/{len(listings)}): {name}")
                    update_ui_logs()
                    
                    # Ziyaret
                    email = None
                    try:
                        visit_page.goto(website, timeout=12000)
                        emails = extract_emails_from_page(visit_page)
                        
                        if not emails:
                            # İletişim'e bak
                            cl = visit_page.locator("a[href*='iletisim'], a[href*='contact']").all()
                            if cl:
                                lnk = cl[0].get_attribute("href")
                                if lnk:
                                    if not lnk.startswith("http"): lnk = website.rstrip("/") + "/" + lnk.lstrip("/")
                                    visit_page.goto(lnk, timeout=8000)
                                    emails = extract_emails_from_page(visit_page)
                        
                        if emails:
                            for em in emails:
                                if em in [r['E-posta'] for r in st.session_state['results']]: continue
                                if verify_domain_mx(em):
                                    email = em; break
                    except: pass
                    
                    if email:
                        st.session_state['results'].append({
                            "Firma": name, "İl": city, "İlçe": district, "Web": website, "E-posta": email
                        })
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_mail.metric("✅ Bulunan", len(st.session_state['results']))
                        log_msg(f"✅ BULUNDU: {email}")
                        update_ui_logs()

                except: continue

        except Exception as e:
            log_msg(f"Kritik Hata: {e}")
            update_ui_logs()
        finally:
            browser.close()
            st.session_state['start_scraping'] = False
