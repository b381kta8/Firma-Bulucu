import streamlit as st
import asyncio
import sys
import os

# --- GÜVENLİK VE GİRİŞ (EN BAŞA EKLENDİ) ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.set_page_config(page_title="Giriş", layout="centered")
    st.title("🔒 Güvenli Giriş")
    st.markdown("Devam etmek için şifreyi giriniz.")
    
    pwd = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        if pwd == "üç":  # ŞİFRE BURADA
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("Hatalı şifre!")
    st.stop() 
# -------------------------------------------

# --- WINDOWS DÜZELTMESİ ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# --------------------------

from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
import dns.resolver

# --- AYARLAR ---
BLOCKED_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com", "pinterest.com", "trendyol.com", "hepsiburada.com", "n11.com", "amazon.com", "ciceksepeti.com"]

# --- HAFIZA ---
if 'results' not in st.session_state:
    st.session_state['results'] = []
if 'processed_urls' not in st.session_state:
    st.session_state['processed_urls'] = set()

# --- YARDIMCI FONKSİYONLAR ---
def verify_domain_mx(email):
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except:
        return False

def clean_obfuscated_email(text):
    text = text.replace(" [at] ", "@").replace("(at)", "@").replace(" at ", "@")
    text = text.replace(" [dot] ", ".").replace("(dot)", ".").replace(" dot ", ".")
    return text

def extract_emails_from_page(page):
    found_emails = set()
    try:
        mailto_links = page.locator("a[href^='mailto:']").all()
        for link in mailto_links:
            href = link.get_attribute("href")
            if href:
                clean = href.replace("mailto:", "").split("?")[0].strip()
                if "@" in clean: found_emails.add(clean)
        
        content = page.content()
        cleaned_content = clean_obfuscated_email(content)
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?!png|jpg|jpeg|gif|css|js|webp|svg)[a-zA-Z]{2,}'
        regex_emails = re.findall(email_pattern, cleaned_content)
        
        for email in regex_emails:
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
st.set_page_config(page_title="Google Maps Scraper Cloud", layout="wide")

# İMZA
st.markdown("""
<div style="position: fixed; top: 65px; right: 20px; z-index: 99999; background: rgba(255, 255, 255, 0.25); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.4); font-size: 12px; font-weight: 600; color: #333; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    🚀 Made by ÜÇ & AI
</div>
""", unsafe_allow_html=True)

st.title("☁️ Google Maps Scraper (Cloud Edition)")
st.markdown("Şifreli, Güvenli ve Her Yerden Erişilebilir.")

with st.sidebar:
    st.header("Ayarlar")
    city = st.text_input("İl", value="İstanbul")
    district = st.text_input("İlçe", value="Kadıköy")
    keyword = st.text_input("Sektör", value="Giyim Mağazası")
    max_target = st.number_input("Hedef Mail Sayısı", min_value=1, max_value=500, value=5)
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
        excel_placeholder.download_button(label="📥 İndir", data=convert_df(df), file_name='sonuc_listesi.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='dl_side')

col1, col2 = st.columns([1, 2])
with col1:
    status_text = st.empty()
    progress_bar = st.progress(0)
    st.divider()
    stat_emails = st.metric("✅ Bulunan Mail", len(st.session_state['results']))

with col2:
    result_table = st.empty()
    if len(st.session_state['results']) > 0:
        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    status_text.info("Bot sunucuda başlatılıyor...")
    
    with sync_playwright() as p:
        # BULUT İÇİN KRİTİK AYAR: headless=True
        # Sunucuda ekran olmadığı için False yaparsan uygulama çöker.
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        try:
            search_term = f"{city} {district} {keyword}"
            page.goto("https://www.google.com/maps?hl=tr", timeout=60000)
            try: page.get_by_role("button", name="Tümünü kabul et").click(timeout=3000)
            except: pass

            try:
                search_box = page.locator("input#searchboxinput").or_(page.locator("input[name='q']")).first
                search_box.wait_for(state="visible", timeout=30000)
                search_box.fill(search_term)
                page.keyboard.press("Enter")
            except:
                st.error("Arama kutusu bulunamadı.")
                st.stop()
            
            page.wait_for_selector('div[role="feed"]', timeout=20000)
            
            listings = []
            prev_count = 0
            scroll_attempts = 0
            target_candidates = max_target * 12
            status_text.warning(f"Liste toplanıyor... (Hedef: {target_candidates})")
            
            while len(listings) < target_candidates:
                if not st.session_state.get('start_scraping', False): break
                page.hover('div[role="feed"]')
                page.mouse.wheel(0, 5000)
                time.sleep(1)
                listings = page.locator('div[role="article"]').all()
                if len(listings) == prev_count:
                    scroll_attempts += 1
                    if scroll_attempts > 6: break
                else: scroll_attempts = 0
                prev_count = len(listings)
                status_text.text(f"Adaylar: {len(listings)}")

            status_text.success(f"{len(listings)} aday taramaya başlıyor...")
            
            for listing in listings:
                if len(st.session_state['results']) >= max_target: 
                    st.success("Hedefe ulaşıldı.")
                    st.session_state['start_scraping'] = False
                    break
                if not st.session_state.get('start_scraping', False): break
                
                progress_bar.progress(min(len(st.session_state['results']) / max_target, 1.0))
                
                try:
                    listing.click()
                    time.sleep(1)
                    website = None
                    try:
                        website_btn = page.locator('[data-item-id="authority"]').first
                        if website_btn.count() > 0: website = website_btn.get_attribute("href")
                    except: pass
                    
                    if not website: continue
                    clean_url = website.rstrip("/")
                    if clean_url in st.session_state['processed_urls']: continue
                    st.session_state['processed_urls'].add(clean_url)
                    
                    is_blocked = False
                    for domain in BLOCKED_DOMAINS:
                        if domain in website:
                            is_blocked = True; break
                    if is_blocked: continue
                    
                    name = "Firma"
                    try: name = page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    phone = None
                    try:
                         phone_btn = page.locator('[data-item-id^="phone:"]').first
                         if phone_btn.count() > 0: phone = phone_btn.get_attribute("aria-label").replace("Telefon: ", "")
                    except: pass
                    
                    status_text.text(f"Analiz: {name}")
                    site_page = context.new_page()
                    email = None
                    method = "-"
                    
                    try:
                        for attempt in range(2): # Cloud'da daha az deneme yapalım hız için
                            try:
                                site_page.goto(website, timeout=12000)
                                break
                            except: time.sleep(1)
                        
                        emails = extract_emails_from_page(site_page)
                        if not emails:
                            contact_links = site_page.locator("a[href*='iletisim'], a[href*='contact']").all()
                            if contact_links:
                                try:
                                    link = contact_links[0].get_attribute("href")
                                    if link:
                                        if not link.startswith("http"): link = website.rstrip("/") + "/" + link.lstrip("/")
                                        site_page.goto(link, timeout=8000)
                                        emails = extract_emails_from_page(site_page)
                                except: pass
                        
                        if emails:
                            for p_email in emails:
                                existing = [i['E-posta'] for i in st.session_state['results']]
                                if p_email in existing: continue
                                if verify_domain_mx(p_email):
                                    email = p_email
                                    method = "Web"
                                    break
                    except: pass
                    finally: site_page.close()
                    
                    if email:
                        entry = {"Firma İsmi": name, "İl": city, "İlçe": district, "Telefon": phone, "Web Sitesi": website, "E-posta": email, "Yöntem": method}
                        st.session_state['results'].append(entry)
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_emails.metric("✅ Bulunan", len(st.session_state['results']))
                        df_new = pd.DataFrame(st.session_state['results'])
                        excel_placeholder.download_button(label="📥 İndir", data=convert_df(df_new), file_name='liste.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'dl_{len(st.session_state["results"])}')
                except: continue

        except Exception as e:
            st.error(f"Hata: {e}")
        finally:
            browser.close()
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
