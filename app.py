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
    if len(st.session_state['logs']) > 8: 
        st.session_state['logs'] = st.session_state['logs'][-8:]

def verify_domain_mx(email):
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
    mailto_pattern = r'href=[\'"]mailto:([^\'" >]+)'
    for match in re.findall(mailto_pattern, html_content):
        if "@" in match:
            found.add(match.split("?")[0].strip())
    text_content = clean_obfuscated_email(html_content)
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

# --- YENİ: POP-UP AVCISI ---
def kill_popups(page):
    """Sitedeki çerez, reklam ve abonelik pencerelerini kapatmaya çalışır."""
    try:
        # 1. ESC Tuşu (En etkili yöntem)
        page.keyboard.press("Escape")
        
        # 2. Yaygın Buton Metinleri (Kabul Et, Kapat vb.)
        targets = [
            "Kabul Et", "Tümünü Kabul Et", "Accept", "Accept All", "Allow", 
            "Tamam", "OK", "Anladım", "Kapat", "Close", "Reddet", "Reject", 
            "Onayla", "İzin Ver"
        ]
        
        # Sayfada bu metinleri içeren buton var mı diye hızlıca bak
        # (Çok vakit kaybetmemek için kısa timeout)
        for t in targets:
            try:
                # Görünür olan butonlara tıkla
                btn = page.get_by_text(t, exact=False).first
                if btn.is_visible():
                    btn.click(timeout=300)
                    # log_msg(f"Pop-up kapatıldı: {t}") # Log kirliliği olmasın diye kapalı
            except: pass
            
    except: pass

# --- ARAYÜZ TASARIMI ---
st.set_page_config(page_title="Joy Refund Ajanı", layout="wide")

st.markdown("""
<div style="position: fixed; top: 65px; right: 20px; z-index: 99999; background: rgba(255, 255, 255, 0.25); backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); font-size: 12px; font-weight: 600; color: #333; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    🚀 Made by ÜÇ & AI
</div>""", unsafe_allow_html=True)

st.title("☁️ Joy Refund Ajanı (Pop-up Killer Modu)")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("📥 İndirme Alanı")
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        st.success(f"✅ {len(df)} Kayıt Hazır")
        st.download_button("📂 Excel Olarak İndir", convert_df(df), "sonuc_listesi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Henüz kayıt yok.")

    st.divider()
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

# --- İLERLEME GÖSTERGESİ (ANA EKRAN) ---
st.subheader("📊 Canlı İlerleme Durumu")
col_prog1, col_prog2 = st.columns([3, 1])
with col_prog1:
    progress_bar = st.progress(0)
with col_prog2:
    percent_text = st.empty()
    percent_text.markdown("**%0 Başlandı**")

status_notification = st.empty()

c1, c2, c3 = st.columns(3)
c1.metric("Hedeflenen", max_target)
stat_havuz = c2.metric("Havuzdaki Aday", 0)
stat_mail = c3.metric("✅ Bulunan Mail", len(st.session_state['results']))

st.write("---")
st.subheader("📟 İşlem Logları")
log_placeholder = st.empty()

st.subheader("Sonuç Tablosu")
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
        context.set_default_timeout(20000)
        
        map_page = context.new_page()

        try:
            # 1. ARAMA
            status_notification.info("Google Maps üzerinde arama yapılıyor...")
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
            
            # 2. HAVUZ TOPLAMA
            listings = []
            prev_count = 0
            fails = 0
            # 20 mail için en az 150 aday (Daha da artırılabilir)
            min_pool = max_target * 10 
            if min_pool < 100: min_pool = 100
            
            log_msg(f"Havuz dolduruluyor... Hedef min: {min_pool}")
            update_ui_logs()
            
            while len(listings) < min_pool:
                if not st.session_state.get('start_scraping', False): break
                
                status_notification.warning(f"Havuz toplanıyor: {len(listings)} / {min_pool}")
                
                # Scroll
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(0.5)
                map_page.keyboard.press("PageDown")
                time.sleep(1)
                
                listings = map_page.locator('div[role="article"]').all()
                stat_havuz.metric("Havuzdaki Aday", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    if fails % 2 == 0:
                        log_msg(f"Yükleniyor... ({fails}/25)")
                        update_ui_logs()
                    
                    map_page.mouse.wheel(0, -1000)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 6000)
                    
                    if fails > 25:
                        log_msg(f"Harita sonu. {len(listings)} aday ile devam.")
                        break
                else: fails = 0
                prev_count = len(listings)

            # 3. ANALİZ
            log_msg(f"Analiz Başlıyor! Toplam {len(listings)} işletme.")
            update_ui_logs()
            
            visit_page = context.new_page()
            
            for idx, listing in enumerate(listings):
                if len(st.session_state['results']) >= max_target: 
                    st.session_state['start_scraping'] = False
                    status_notification.success("✅ HEDEF SAYIYA ULAŞILDI!")
                    progress_bar.progress(1.0)
                    percent_text.markdown("**%100 BİTTİ**")
                    st.balloons()
                    break
                
                if not st.session_state.get('start_scraping', False): break
                if (idx % 20 == 0): gc.collect()

                # İlerleme
                current_percent = len(st.session_state['results']) / max_target
                if current_percent > 1.0: current_percent = 1.0
                progress_bar.progress(current_percent)
                percent_text.markdown(f"**%{int(current_percent*100)} Tamamlandı**")

                try:
                    listing.click(timeout=2000)
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
                    
                    name = "Firma"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    status_notification.info(f"İnceleniyor ({idx+1}/{len(listings)}): {name}")
                    log_msg(f"İnceleniyor: {name}")
                    update_ui_logs()
                    
                    # --- SİTE TARAMA ---
                    email = None
                    verification_status = "Bilinmiyor"
                    
                    try:
                        # 1. Ana Sayfa (Pop-up Killer Aktif)
                        visit_page.goto(website, timeout=12000, wait_until="domcontentloaded")
                        kill_popups(visit_page) # <-- YENİ FONKSİYON BURADA
                        
                        # Footer'a in
                        visit_page.keyboard.press("End") 
                        time.sleep(1) 
                        
                        html = visit_page.content()
                        emails = extract_emails_from_html(html)
                        
                        # 2. Alt Sayfalar
                        if not emails:
                            keywords = ["iletisim", "contact", "hakkimizda", "about", "kvkk", "künye", "bize-ulasin"]
                            links = visit_page.locator("a").all()
                            target_url = None
                            for lnk in links:
                                try:
                                    href = lnk.get_attribute("href")
                                    if href and any(k in href.lower() for k in keywords):
                                        target_url = urljoin(website, href)
                                        if urlparse(website).netloc in target_url: break
                                except: continue
                            
                            if target_url:
                                log_msg(f"  > Alt sayfa: {target_url}")
                                visit_page.goto(target_url, timeout=10000, wait_until="domcontentloaded")
                                kill_popups(visit_page) # <-- Burada da çalıştır
                                visit_page.keyboard.press("End")
                                time.sleep(1)
                                emails = extract_emails_from_html(visit_page.content())

                        if emails:
                            for em in emails:
                                if em in [r['E-posta'] for r in st.session_state['results']]: continue
                                is_verified = verify_domain_mx(em)
                                email = em
                                verification_status = "Doğrulandı" if is_verified else "Doğrulanamadı"
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
            
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
                status_notification.success("Tarama Tamamlandı (Liste Sonu).")
                progress_bar.progress(1.0)
                st.balloons()

        except Exception as e:
            log_msg(f"Hata: {e}")
        finally:
            browser.close()
            st.session_state['start_scraping'] = False
