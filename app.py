import streamlit as st
import asyncio
import sys
import os
import subprocess
import gc
from datetime import datetime

# --- 1. TARAYICI KURULUMU (CLOUD) ---
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

# --- 3. AYARLAR & LOGLAMA ---
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

# LOG FONKSİYONU
def log_msg(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state['logs'].insert(0, f"[{timestamp}] {msg}")
    # Log listesi çok şişmesin (son 200 satır)
    if len(st.session_state['logs']) > 200:
        st.session_state['logs'].pop()

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
        # Mailto
        for link in page.locator("a[href^='mailto:']").all():
            href = link.get_attribute("href")
            if href and "@" in href:
                clean = href.replace("mailto:", "").split("?")[0].strip()
                found_emails.add(clean)
        # Regex
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

st.title("☁️ Joy Refund Ajanı (Detaylı Log Modu)")

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
        log_msg("Sistem başlatıldı.")
    
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False
        log_msg("Kullanıcı tarafından durduruldu.")
    
    # Excel İndir
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        st.download_button("📥 Excel İndir", convert_df(df), "sonuc.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Üst Panel: İstatistikler
c1, c2, c3 = st.columns(3)
c1.metric("Hedeflenen", max_target)
stat_havuz = c2.metric("Havuzdaki Aday", 0)
stat_mail = c3.metric("✅ Bulunan Mail", len(st.session_state['results']))

# Orta Panel: İlerleme ve Loglar
st.divider()
progress_bar = st.progress(0)

# LOG PANELİ (Canlı akış)
with st.expander("📝 CANLI İŞLEM LOGLARI (Burayı takip et)", expanded=True):
    log_container = st.empty()

# Sonuç Tablosu
st.subheader("Bulunan Firmalar")
result_table = st.empty()
if len(st.session_state['results']) > 0:
    result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

# LOG GÜNCELLEME FONKSİYONU
def update_logs():
    log_text = "\n".join(st.session_state['logs'])
    log_container.code(log_text, language="log")

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Timeout'ları düşürüyoruz (10 saniye)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # Global timeout ayarı: 15 saniye içinde işlem bitmezse hata verip geç
        context.set_default_navigation_timeout(15000)
        context.set_default_timeout(15000)
        
        map_page = context.new_page()

        try:
            # 1. Google Maps
            search_term = f"{city} {district} {keyword}"
            log_msg(f"Google Maps açılıyor... Arama: {search_term}")
            update_logs()
            
            map_page.goto("https://www.google.com/maps?hl=tr")
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=5000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_term)
                map_page.keyboard.press("Enter")
                log_msg("Arama yapıldı, sonuçlar bekleniyor...")
            except: 
                log_msg("HATA: Arama kutusu bulunamadı!")
                st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. Havuz Toplama
            listings = []
            prev_count = 0
            fails = 0
            target_candidates = max_target * 50
            
            log_msg(f"Liste toplanıyor... Hedef: {target_candidates} aday.")
            update_logs()
            
            while len(listings) < target_candidates:
                if not st.session_state.get('start_scraping', False): break
                
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(1)
                
                listings = map_page.locator('div[role="article"]').all()
                stat_havuz.metric("Havuzdaki Aday", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    if fails % 2 == 0: log_msg(f"Liste yüklenmesi bekleniyor... ({fails}/15)")
                    update_logs()
                    
                    # Wiggle
                    map_page.mouse.wheel(0, -1500)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 6000)
                    time.sleep(1.5)
                    
                    if fails > 15: 
                        log_msg("Harita sonuna gelindi. Toplama bitti.")
                        break
                else: fails = 0
                prev_count = len(listings)

            log_msg(f"Toplam {len(listings)} aday toplandı. Analiz başlıyor...")
            update_logs()
            
            # 3. Analiz (Visit Page)
            visit_page = context.new_page()
            processed_count = 0
            
            for index, listing in enumerate(listings):
                if len(st.session_state['results']) >= max_target: 
                    log_msg("HEDEF TAMAMLANDI! 🎉")
                    st.success("İşlem Bitti!"); st.session_state['start_scraping'] = False; break
                if not st.session_state.get('start_scraping', False): break
                
                progress_bar.progress(min(len(st.session_state['results']) / max_target, 1.0))
                
                # RAM Garbage Collection
                processed_count += 1
                if processed_count % 10 == 0: gc.collect()

                try:
                    listing.click(timeout=2000)
                    time.sleep(0.5)
                    
                    # Veri Çekme
                    website = None
                    try:
                        wb = map_page.locator('[data-item-id="authority"]').first
                        if wb.count() > 0: website = wb.get_attribute("href")
                    except: pass
                    
                    name = "Bilinmiyor"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass

                    # LOGLAMA
                    if not website:
                        # Web sitesi yoksa logu kirletme, geç
                        # log_msg(f"Atlandı: {name} (Web sitesi yok)") 
                        continue
                    
                    clean_url = website.rstrip("/")
                    if clean_url in st.session_state['processed_urls']: continue
                    st.session_state['processed_urls'].add(clean_url)
                    
                    if any(b in website for b in BLOCKED_DOMAINS): 
                        log_msg(f"Atlandı: {name} (Sosyal Medya/Pazaryeri)")
                        update_logs()
                        continue
                    
                    # Analiz Başlıyor
                    log_msg(f"İnceleniyor ({index+1}/{len(listings)}): {name} -> {website}")
                    update_logs()
                    
                    phone = None
                    try:
                         pb = map_page.locator('[data-item-id^="phone:"]').first
                         if pb.count() > 0: phone = pb.get_attribute("aria-label").replace("Telefon: ", "")
                    except: pass
                    
                    email = None
                    method = "-"
                    
                    # ZİYARET (Try-Except ile korunmuş)
                    try:
                        visit_page.goto(website, timeout=10000) # 10 sn mühlet
                        emails = extract_emails_from_page(visit_page)
                        
                        if not emails:
                            log_msg(f"  > Ana sayfada yok. İletişim aranıyor...")
                            contact_links = visit_page.locator("a[href*='iletisim'], a[href*='contact']").all()
                            if contact_links:
                                try:
                                    link = contact_links[0].get_attribute("href")
                                    if link:
                                        if not link.startswith("http"): link = website.rstrip("/") + "/" + link.lstrip("/")
                                        visit_page.goto(link, timeout=8000)
                                        emails = extract_emails_from_page(visit_page)
                                except: pass
                        
                        if emails:
                            for p_email in emails:
                                if p_email in [i['E-posta'] for i in st.session_state['results']]: 
                                    log_msg(f"  > Mükerrer mail: {p_email}")
                                    continue
                                
                                log_msg(f"  > Mail bulundu: {p_email}. Doğrulanıyor...")
                                if verify_domain_mx(p_email):
                                    email = p_email; method = "Web"
                                    log_msg(f"  > ✅ ONAYLANDI: {email}")
                                    break
                                else:
                                    log_msg(f"  > ❌ MX Kaydı yok (Geçersiz): {p_email}")
                        else:
                            log_msg(f"  > Mail bulunamadı.")

                    except Exception as e_visit:
                        log_msg(f"  > ⚠️ Site Hatası (Timeout/Erişim): {str(e_visit)[:50]}...")
                    
                    # KAYIT
                    if email:
                        st.session_state['results'].append({
                            "Firma İsmi": name, "İl": city, "İlçe": district, 
                            "Telefon": phone, "Web Sitesi": website, "E-posta": email, "Yöntem": method
                        })
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_mail.metric("✅ Bulunan Mail", len(st.session_state['results']))
                    
                    update_logs() # Her firmadan sonra logu güncelle

                except Exception as e_listing: 
                    log_msg(f"Liste öğesi hatası: {e_listing}")
                    continue
            
            visit_page.close()

        except Exception as e: 
            log_msg(f"KRİTİK HATA: {e}")
            st.error(f"Hata: {e}")
        finally:
            browser.close()
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
                log_msg("İşlem tamamlandı.")
                update_logs()
