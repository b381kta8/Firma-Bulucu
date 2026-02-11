import streamlit as st
import asyncio
import sys
import os
import subprocess
import gc # RAM temizliği için gerekli

# --- 1. TARAYICI KURULUMU (CLOUD İÇİN) ---
def install_playwright_browser():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("Playwright browser installed.")
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

# --- YARDIMCI FONKSİYONLAR ---
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

st.title("☁️ Joy Refund Firma Ajanı (Stabil Mod)")

with st.sidebar:
    st.header("Ayarlar")
    city = st.text_input("İl", "İstanbul")
    district = st.text_input("İlçe", "Kadıköy")
    keyword = st.text_input("Sektör", "Giyim Mağazası")
    max_target = st.number_input("Hedef Mail Sayısı", 1, 1000, 20)
    st.info(f"Yaklaşık {max_target*50} işletme taranacak.")
    st.divider()
    if st.button("Başlat", type="primary"):
        st.session_state['start_scraping'] = True
        st.session_state['results'] = []
        st.session_state['processed_urls'] = set()
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False
    
    excel_placeholder = st.empty()
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        excel_placeholder.download_button("📥 Excel İndir", convert_df(df), "sonuc.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

col1, col2 = st.columns([1, 2])
with col1:
    status_text = st.empty()
    progress_bar = st.progress(0)
    st.divider()
    stat_candidates_ph = st.empty()
    stat_candidates_ph.metric("Havuz", 0)
    stat_emails_ph = st.empty()
    stat_emails_ph.metric("✅ Mail", len(st.session_state['results']))

with col2:
    result_table = st.empty()
    if len(st.session_state['results']) > 0:
        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    status_text.info("Başlatılıyor (RAM Optimize Modu)...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Context ayarları: Gereksiz resimleri yükleme, hızlansın
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # Harita sekmesi
        map_page = context.new_page()

        try:
            # 1. Arama
            search_term = f"{city} {district} {keyword}"
            map_page.goto("https://www.google.com/maps?hl=tr", timeout=60000)
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=5000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_term)
                map_page.keyboard.press("Enter")
            except: st.error("Arama yapılamadı."); st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. Toplama (Sabırlı Scroll)
            listings = []
            prev_count = 0
            fails = 0
            target_candidates = max_target * 50
            
            status_text.warning(f"Havuz dolduruluyor... Hedef: {target_candidates}")
            
            while len(listings) < target_candidates:
                if not st.session_state.get('start_scraping', False): break
                
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(1.5) # Biraz daha bekle
                
                listings = map_page.locator('div[role="article"]').all()
                stat_candidates_ph.metric("Havuz", len(listings))
                
                if len(listings) == prev_count:
                    fails += 1
                    status_text.text(f"Liste yükleniyor... ({fails}/20)") # Sabır süresi artırıldı
                    
                    # Wiggle (Sallama)
                    map_page.mouse.wheel(0, -1500)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 6000)
                    time.sleep(2)
                    
                    if fails > 20: 
                        status_text.info("Harita sonu.")
                        break
                else: fails = 0
                prev_count = len(listings)

            status_text.success(f"{len(listings)} aday. Analiz başlıyor...")
            
            # 3. Analiz (TEK SEKME TEKNİĞİ)
            # Her site için yeni sekme açmak yerine, bu sekmeyi sürekli kullanacağız.
            visit_page = context.new_page()
            
            processed_count = 0
            
            for listing in listings:
                if len(st.session_state['results']) >= max_target: 
                    st.success("Bitti!"); st.session_state['start_scraping'] = False; break
                if not st.session_state.get('start_scraping', False): break
                
                progress_bar.progress(min(len(st.session_state['results']) / max_target, 1.0))
                
                # RAM TEMİZLİĞİ: Her 10 firmada bir çöp topla
                processed_count += 1
                if processed_count % 10 == 0:
                    gc.collect() 

                try:
                    listing.click()
                    time.sleep(1)
                    
                    website = None
                    try:
                        wb = map_page.locator('[data-item-id="authority"]').first
                        if wb.count() > 0: website = wb.get_attribute("href")
                    except: pass
                    
                    if not website: continue
                    clean_url = website.rstrip("/")
                    if clean_url in st.session_state['processed_urls']: continue
                    st.session_state['processed_urls'].add(clean_url)
                    
                    if any(b in website for b in BLOCKED_DOMAINS): continue
                    
                    name = "Firma"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    phone = None
                    try:
                         pb = map_page.locator('[data-item-id^="phone:"]').first
                         if pb.count() > 0: phone = pb.get_attribute("aria-label").replace("Telefon: ", "")
                    except: pass
                    
                    status_text.text(f"İnceleniyor: {name}")
                    
                    # AYNI SEKME ÜZERİNDEN GİT
                    email = None
                    method = "-"
                    
                    try:
                        visit_page.goto(website, timeout=15000) # Tekrar aynı sekmeyi kullan
                        emails = extract_emails_from_page(visit_page)
                        
                        if not emails:
                            contact_links = visit_page.locator("a[href*='iletisim'], a[href*='contact']").all()
                            if contact_links:
                                try:
                                    link = contact_links[0].get_attribute("href")
                                    if link:
                                        if not link.startswith("http"): link = website.rstrip("/") + "/" + link.lstrip("/")
                                        visit_page.goto(link, timeout=10000)
                                        emails = extract_emails_from_page(visit_page)
                                except: pass
                        
                        if emails:
                            for p_email in emails:
                                if p_email in [i['E-posta'] for i in st.session_state['results']]: continue
                                if verify_domain_mx(p_email):
                                    email = p_email; method = "Web"; break
                    except: 
                        # Eğer sekme donarsa resetle
                        pass
                    
                    if email:
                        entry = {"Firma İsmi": name, "İl": city, "İlçe": district, "Telefon": phone, "Web Sitesi": website, "E-posta": email, "Yöntem": method}
                        st.session_state['results'].append(entry)
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_emails_ph.metric("✅ Mail", len(st.session_state['results']))
                        df_new = pd.DataFrame(st.session_state['results'])
                        excel_placeholder.download_button("📥 Excel İndir", convert_df(df_new), "liste.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f'dl_{len(st.session_state["results"])}')

                except: continue
            
            visit_page.close() # İş bitince kapat

        except Exception as e: st.error(f"Hata: {e}")
        finally:
            browser.close()
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
