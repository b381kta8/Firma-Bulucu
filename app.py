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

def kill_popups(page):
    try:
        page.keyboard.press("Escape")
        targets = ["Kabul Et", "Accept", "Tamam", "OK", "Kapat", "Close", "Reddet", "Onayla"]
        for t in targets:
            try:
                btn = page.get_by_text(t, exact=False).first
                if btn.is_visible(): btn.click(timeout=200)
            except: pass
    except: pass

# --- ARAYÜZ ---
st.set_page_config(page_title="Joy Refund Ajanı", layout="wide")

st.markdown("""
<div style="position: fixed; top: 65px; right: 20px; z-index: 99999; background: rgba(255, 255, 255, 0.25); backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); font-size: 12px; font-weight: 600; color: #333; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    🚀 Made by ÜÇ & AI
</div>""", unsafe_allow_html=True)

st.title("☁️ Joy Refund Ajanı (Canlı Derin Tarama)")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("📥 İndirme Paneli")
    # Excel butonu için boş alan ayırıyoruz (Sonra güncelleyeceğiz)
    download_placeholder = st.empty()
    
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
    
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False

# Excel Butonu Güncelleme Fonksiyonu
def update_download_button():
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        # Placeholder'ı temizle ve yeni butonu koy
        download_placeholder.empty()
        download_placeholder.download_button(
            label=f"📂 Excel İndir ({len(df)} Kayıt)", 
            data=convert_df(df), 
            file_name="guncel_sonuc_listesi.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_btn_{len(df)}" # Benzersiz key ile yenilenmesini zorla
        )
    else:
        download_placeholder.info("Henüz kayıt bulunamadı.")

# İlk açılışta butonu göster
update_download_button()

# --- İSTATİSTİKLER ---
c1, c2, c3 = st.columns(3)
c1.metric("Hedef", max_target)
stat_havuz = c2.metric("Havuz", 0)
stat_mail = c3.metric("✅ Bulunan", len(st.session_state['results']))

st.write("---")
col_screen, col_table = st.columns([1, 1])

with col_screen:
    st.subheader("📺 Botun Gözü (Canlı Yayın)")
    screenshot_placeholder = st.empty()
    status_text = st.empty()

with col_table:
    st.subheader("📋 Sonuçlar")
    result_table = st.empty()
    if len(st.session_state['results']) > 0:
        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

def update_screenshot(page, msg):
    try:
        screenshot_path = "live_view.png"
        page.screenshot(path=screenshot_path)
        screenshot_placeholder.image(screenshot_path, caption=f"Anlık Durum: {msg}", use_container_width=True)
        status_text.info(msg)
    except: pass

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        context.set_default_timeout(15000)
        
        map_page = context.new_page()

        try:
            # 1. ARAMA
            search_query = f"{city} {district} {keyword}"
            update_screenshot(map_page, "Google Maps Yükleniyor...")
            
            map_page.goto("https://www.google.com/maps?hl=tr")
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=3000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_query)
                map_page.keyboard.press("Enter")
                time.sleep(1)
                update_screenshot(map_page, f"Aranıyor: {search_query}")
            except: 
                st.error("Arama kutusu bulunamadı.")
                st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. HAVUZ TOPLAMA (En az 50 aday)
            listings = []
            prev_count = 0
            fails = 0
            min_pool = max_target * 5 
            if min_pool < 50: min_pool = 50
            
            while len(listings) < min_pool:
                if not st.session_state.get('start_scraping', False): break
                
                # Scroll
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(0.5)
                map_page.keyboard.press("PageDown")
                
                # Kullanıcıya canlı görüntü ver
                if len(listings) % 20 == 0:
                    update_screenshot(map_page, f"Havuz Toplanıyor... ({len(listings)}/{min_pool})")
                
                listings = map_page.locator('div[role="article"]').all()
                stat_havuz.metric("Havuz", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    map_page.mouse.wheel(0, -1000)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 6000)
                    if fails > 15: break
                else: fails = 0
                prev_count = len(listings)

            # 3. ANALİZ
            visit_page = context.new_page()
            
            for idx, listing in enumerate(listings):
                if len(st.session_state['results']) >= max_target: 
                    st.success("HEDEF TAMAMLANDI! 🎉")
                    st.balloons()
                    st.session_state['start_scraping'] = False
                    break
                
                if not st.session_state.get('start_scraping', False): break
                if (idx % 20 == 0): gc.collect()

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
                    
                    update_screenshot(visit_page, f"GİRİLİYOR: {name}")
                    
                    # --- SİTE TARAMA ---
                    email = None
                    verification_status = "Bilinmiyor"
                    
                    try:
                        # Ana Sayfa
                        visit_page.goto(website, timeout=12000, wait_until="domcontentloaded")
                        kill_popups(visit_page)
                        
                        # Footer'a in
                        visit_page.keyboard.press("End") 
                        time.sleep(0.5)
                        
                        html = visit_page.content()
                        emails = extract_emails_from_html(html)
                        
                        # Eğer ana sayfada mail yoksa -> ALT SAYFALARA SALDIR
                        if not emails:
                            keywords = ["iletisim", "contact", "hakkimizda", "about", "kvkk", "künye", "bize-ulasin"]
                            links = visit_page.locator("a").all()
                            target_url = None
                            
                            for lnk in links:
                                try:
                                    href = lnk.get_attribute("href")
                                    if href and any(k in href.lower() for k in keywords):
                                        target_url = urljoin(website, href)
                                        # Domain dışına çıkma ve pdf/jpg linki olmasın
                                        if urlparse(website).netloc in target_url and not target_url.endswith((".pdf", ".jpg", ".png")):
                                            break
                                except: continue
                            
                            if target_url:
                                # Ekran görüntüsünde göster
                                update_screenshot(visit_page, f"ALT SAYFA: {target_url} taranıyor...")
                                visit_page.goto(target_url, timeout=10000, wait_until="domcontentloaded")
                                kill_popups(visit_page)
                                visit_page.keyboard.press("End")
                                time.sleep(0.5)
                                emails = extract_emails_from_html(visit_page.content())

                        if emails:
                            for em in emails:
                                if em in [r['E-posta'] for r in st.session_state['results']]: continue
                                is_verified = verify_domain_mx(em)
                                email = em
                                verification_status = "Doğrulandı" if is_verified else "Doğrulanamadı"
                                break 
                    except Exception as e:
                        # update_screenshot(visit_page, f"Hata: {str(e)[:20]}")
                        pass
                    
                    if email:
                        st.session_state['results'].append({
                            "Firma": name, "İl": city, "İlçe": district, "Web": website, "E-posta": email, "Durum": verification_status
                        })
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_mail.metric("✅ Bulunan", len(st.session_state['results']))
                        
                        # KRİTİK: Butonu anlık güncelle
                        update_download_button()
                        
                        update_screenshot(visit_page, f"✅ BULUNDU: {email}")
                        time.sleep(0.5)

                except: continue
            
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
                st.success("Tarama bitti.")

        except Exception as e:
            st.error(f"Hata: {e}")
        finally:
            browser.close()
            st.session_state['start_scraping'] = False
