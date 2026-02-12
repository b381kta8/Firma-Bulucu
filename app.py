import streamlit as st
import asyncio
import sys
import os
import subprocess
import gc
from datetime import datetime
from urllib.parse import urljoin, urlparse

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

# Yasaklı domainler
BLOCKED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", 
    "youtube.com", "pinterest.com", "trendyol.com", "hepsiburada.com", 
    "n11.com", "amazon.com", "ciceksepeti.com", "getir.com", "yemeksepeti.com",
    "google.com", "apple.com", "wikipedia.org"
]

if 'results' not in st.session_state: st.session_state['results'] = []
if 'processed_urls' not in st.session_state: st.session_state['processed_urls'] = set()
if 'logs' not in st.session_state: st.session_state['logs'] = []

# --- LOG SİSTEMİ ---
def log_msg(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].append(f"[{timestamp}] {msg}")
    if len(st.session_state['logs']) > 6: 
        st.session_state['logs'] = st.session_state['logs'][-6:]

def verify_domain_mx(email):
    """MX kontrolü yapar ama hata verirse False döner"""
    try:
        domain = email.split('@')[1]
        records = dns.resolver.resolve(domain, 'MX')
        return True if records else False
    except: return False

def clean_obfuscated_email(text):
    text = text.replace(" [at] ", "@").replace("(at)", "@").replace(" at ", "@")
    text = text.replace(" [dot] ", ".").replace("(dot)", ".").replace(" dot ", ".")
    return text

def extract_emails_from_html(html_content):
    found = set()
    # 1. Mailto Linkleri
    mailto_pattern = r'href=[\'"]mailto:([^\'" >]+)'
    for match in re.findall(mailto_pattern, html_content):
        if "@" in match:
            clean = match.split("?")[0].strip()
            found.add(clean)
            
    # 2. Düz Metin (Gelişmiş Regex)
    text_content = clean_obfuscated_email(html_content)
    # Resim dosyalarını mail sanmasın diye negatif lookahead
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?!png|jpg|jpeg|gif|css|js|webp|svg|woff|ttf)[a-zA-Z]{2,}'
    for email in re.findall(email_pattern, text_content):
        if len(email) < 50: found.add(email)
        
    return list(found)

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

st.title("☁️ Joy Refund Ajanı (Avcı Modu)")

with st.sidebar:
    st.header("Ayarlar")
    city = st.text_input("İl", "İstanbul")
    district = st.text_input("İlçe", "Kadıköy")
    keyword = st.text_input("Sektör", "Giyim Mağazası")
    max_target = st.number_input("Hedef Mail Sayısı", 1, 1000, 20)
    
    st.divider()
    
    # YENİ AYAR: DOĞRULAMA ZORUNLULUĞU
    strict_mode = st.checkbox("Sadece %100 Doğrulanmış Mailleri Kaydet", value=False)
    st.caption("Tik kapalıyken (Önerilen), MX kaydı yanıt vermese bile mail formatı düzgünse kaydeder.")
    
    st.divider()
    if st.button("Başlat", type="primary"):
        st.session_state['start_scraping'] = True
        st.session_state['results'] = []
        st.session_state['processed_urls'] = set()
        st.session_state['logs'] = []
        log_msg("Avcı modu başlatılıyor...")
    
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False
    
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        st.download_button("📥 Excel İndir", convert_df(df), "sonuc.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

c1, c2, c3 = st.columns(3)
c1.metric("Hedef", max_target)
stat_havuz = c2.metric("Havuzdaki Aday", 0)
stat_mail = c3.metric("✅ Bulunan Mail", len(st.session_state['results']))

st.write("---")
st.subheader("📟 Canlı Log")
log_placeholder = st.empty()

st.subheader("Sonuçlar")
result_table = st.empty()
if len(st.session_state['results']) > 0:
    result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

def update_ui_logs():
    log_text = "\n".join(st.session_state['logs'])
    log_placeholder.code(log_text, language="cmd")

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.set_default_timeout(20000) # 20 saniye zaman aşımı
        
        map_page = context.new_page()

        try:
            # 1. ARAMA
            search_query = f"{city} {district} {keyword}"
            log_msg(f"Aranıyor: {search_query}")
            update_ui_logs()
            
            map_page.goto("https://www.google.com/maps?hl=tr")
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=3000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_query)
                map_page.keyboard.press("Enter")
            except: 
                st.error("Arama yapılamadı.")
                st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. HAVUZ TOPLAMA (EN AZ 100 ADAY)
            listings = []
            prev_count = 0
            fails = 0
            # 20 mail için en az 200 aday
            min_pool = max_target * 10
            if min_pool < 100: min_pool = 100
            
            log_msg(f"Havuz dolduruluyor... Hedef: {min_pool}")
            update_ui_logs()
            
            while len(listings) < min_pool:
                if not st.session_state.get('start_scraping', False): break
                
                # Çift Scroll Tekniği
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(0.5)
                map_page.keyboard.press("End")
                time.sleep(1)
                
                listings = map_page.locator('div[role="article"]').all()
                stat_havuz.metric("Havuzdaki Aday", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    if fails % 2 == 0:
                        log_msg(f"Yükleniyor... ({fails}/20)")
                        update_ui_logs()
                    
                    map_page.mouse.wheel(0, -500)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 4000)
                    
                    if fails > 20:
                        log_msg(f"Harita bitti. {len(listings)} aday incelenecek.")
                        break
                else: fails = 0
                prev_count = len(listings)

            # 3. DERİN ANALİZ
            log_msg(f"Analiz Başlıyor! {len(listings)} işletme.")
            update_ui_logs()
            
            visit_page = context.new_page()
            
            for idx, listing in enumerate(listings):
                if len(st.session_state['results']) >= max_target: 
                    st.success("HEDEF TAMAMLANDI!"); st.session_state['start_scraping'] = False; break
                
                if not st.session_state.get('start_scraping', False): break
                if (idx % 20 == 0): gc.collect()

                try:
                    listing.click(timeout=2000)
                    time.sleep(0.5)
                    
                    # Veri Alma
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
                    
                    name = "Firma"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    log_msg(f"({idx+1}/{len(listings)}) {name}")
                    update_ui_logs()
                    
                    # --- SİTE TARAMA ---
                    email = None
                    verification_status = "Bilinmiyor"
                    
                    try:
                        # Ana Sayfa
                        visit_page.goto(website, timeout=12000, wait_until="domcontentloaded")
                        emails = extract_emails_from_html(visit_page.content())
                        
                        # Ana sayfada yoksa alt sayfalara saldır
                        if not emails:
                            keywords = ["iletisim", "contact", "hakkimizda", "about", "kvkk", "künye", "bize-ulasin"]
                            links = visit_page.locator("a").all()
                            
                            target_url = None
                            for lnk in links:
                                try:
                                    href = lnk.get_attribute("href")
                                    if href and any(k in href.lower() for k in keywords):
                                        target_url = urljoin(website, href)
                                        # Domain dışına çıkma
                                        if urlparse(website).netloc in target_url:
                                            break
                                except: continue
                            
                            if target_url:
                                log_msg(f"  > Alt sayfa: {target_url}")
                                update_ui_logs()
                                visit_page.goto(target_url, timeout=10000, wait_until="domcontentloaded")
                                emails = extract_emails_from_html(visit_page.content())

                        # E-posta Seçimi
                        if emails:
                            for em in emails:
                                if em in [r['E-posta'] for r in st.session_state['results']]: continue
                                
                                # Doğrulama
                                is_mx_ok = verify_domain_mx(em)
                                
                                # Eğer "Sıkı Mod" kapalıysa (Varsayılan), maili her türlü al
                                if not strict_mode:
                                    email = em
                                    verification_status = "Doğrulandı" if is_mx_ok else "Doğrulanamadı (Riskli)"
                                    break
                                # Eğer "Sıkı Mod" açıksa, sadece MX varsa al
                                elif strict_mode and is_mx_ok:
                                    email = em
                                    verification_status = "Doğrulandı"
                                    break
                    except: pass
                    
                    if email:
                        st.session_state['results'].append({
                            "Firma": name, "İl": city, "İlçe": district, "Web": website, "E-posta": email, "Durum": verification_status
                        })
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_mail.metric("✅ Bulunan Mail", len(st.session_state['results']))
                        log_msg(f"✅ BULUNDU: {email}")
                        update_ui_logs()

                except: continue

        except Exception as e:
            log_msg(f"Hata: {e}")
        finally:
            browser.close()
            st.session_state['start_scraping'] = False
