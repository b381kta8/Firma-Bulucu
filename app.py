import streamlit as st
import asyncio
import sys
import os
import subprocess

# --- 1. TARAYICI KURULUMU (CLOUD İÇİN) ---
def install_playwright_browser():
    try:
        # Chromium'u sessizce kur
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("Playwright browser installed.")
    except Exception as e:
        print(f"Browser install error: {e}")

# Uygulama açılışında bir kere çalışır
if "browser_installed" not in st.session_state:
    with st.spinner("Sistem hazırlanıyor... (Bu işlem ilk seferde 1 dakika sürebilir)"):
        install_playwright_browser()
        st.session_state["browser_installed"] = True

# --- 2. GÜVENLİK (ŞİFRE: üç) ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.set_page_config(page_title="Giriş", layout="centered")
    st.title("🔒 Güvenli Giriş")
    pwd = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        if pwd == "üç":
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("Hatalı şifre!")
    st.stop() 

# --- 3. WINDOWS DÜZELTMESİ ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- KÜTÜPHANELER ---
from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
import dns.resolver

# --- AYARLAR ---
# Vakit kaybetmemek için bu sitelere girilmez
BLOCKED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", 
    "youtube.com", "pinterest.com", "trendyol.com", "hepsiburada.com", 
    "n11.com", "amazon.com", "ciceksepeti.com", "getir.com", "yemeksepeti.com"
]

# --- HAFIZA ---
if 'results' not in st.session_state: st.session_state['results'] = []
if 'processed_urls' not in st.session_state: st.session_state['processed_urls'] = set()

# --- YARDIMCI FONKSİYONLAR ---
def verify_domain_mx(email):
    """Mail sunucusu kontrolü (MX Kaydı)"""
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except:
        return False

def clean_obfuscated_email(text):
    """Gizlenmiş mailleri düzeltir"""
    text = text.replace(" [at] ", "@").replace("(at)", "@").replace(" at ", "@")
    text = text.replace(" [dot] ", ".").replace("(dot)", ".").replace(" dot ", ".")
    return text

def extract_emails_from_page(page):
    """Sayfadan mail kazıma"""
    found_emails = set()
    try:
        # Mailto linkleri
        mailto_links = page.locator("a[href^='mailto:']").all()
        for link in mailto_links:
            href = link.get_attribute("href")
            if href:
                clean = href.replace("mailto:", "").split("?")[0].strip()
                if "@" in clean: found_emails.add(clean)
        
        # Metin tarama
        content = page.content()
        cleaned_content = clean_obfuscated_email(content)
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?!png|jpg|jpeg|gif|css|js|webp|svg)[a-zA-Z]{2,}'
        regex_emails = re.findall(email_pattern, cleaned_content)
        
        for email in regex_emails:
            if len(email) < 50: found_emails.add(email)
    except: pass
    return list(found_emails)

def convert_df(df):
    """Excel çıktısı oluşturur"""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Firmalar')
    return output.getvalue()

# --- ARAYÜZ ---
st.set_page_config(page_title="Joy Refund Ajanı", layout="wide")

# İMZA (Sağ Üst)
st.markdown("""
<div style="
    position: fixed; top: 65px; right: 20px; z-index: 99999; 
    background: rgba(255, 255, 255, 0.25); 
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); 
    padding: 8px 16px; border-radius: 20px; 
    border: 1px solid rgba(255, 255, 255, 0.4); 
    font-size: 12px; font-weight: 600; color: #333; 
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    🚀 Made by ÜÇ & AI
</div>
""", unsafe_allow_html=True)

st.title("☁️ Joy Refund Firma Ajanı")
st.markdown("Otomatik Doğrulama | Mükerrer Kontrolü | Cloud Modu")

with st.sidebar:
    st.header("Ayarlar")
    city = st.text_input("İl", value="İstanbul")
    district = st.text_input("İlçe", value="Kadıköy")
    keyword = st.text_input("Sektör", value="Giyim Mağazası")
    max_target = st.number_input("Hedef Mail Sayısı", min_value=1, max_value=500, value=5)
    
    st.info(f"💡 {max_target} temiz mail için yaklaşık {max_target*40} işletme taranacaktır.")
    
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
        excel_placeholder.download_button(
            label="📥 Excel İndir", 
            data=convert_df(df), 
            file_name='sonuc_listesi.xlsx', 
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
            key='dl_side'
        )

col1, col2 = st.columns([1, 2])
with col1:
    status_text = st.empty()
    progress_bar = st.progress(0)
    st.divider()
    stat_candidates = st.metric("Havuzdaki Aday", 0)
    stat_emails = st.metric("✅ Bulunan Mail", len(st.session_state['results']))

with col2:
    result_table = st.empty()
    if len(st.session_state['results']) > 0:
        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

# --- ANA MOTOR ---
if st.session_state.get('start_scraping', False):
    status_text.info("Bot sunucuda başlatılıyor...")
    
    with sync_playwright() as p:
        # CLOUD İÇİN HEADLESS=TRUE ŞART
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. Google Maps Arama
            search_term = f"{city} {district} {keyword}"
            page.goto("https://www.google.com/maps?hl=tr", timeout=60000)
            
            try: page.get_by_role("button", name="Tümünü kabul et").click(timeout=5000)
            except: pass

            try:
                # Arama kutusunu bulmak için alternatif yöntemler
                search_box = page.locator("input#searchboxinput").or_(page.locator("input[name='q']")).first
                search_box.wait_for(state="visible", timeout=30000)
                search_box.fill(search_term)
                page.keyboard.press("Enter")
            except:
                st.error("Arama kutusu bulunamadı. Lütfen sayfayı yenileyip tekrar deneyin.")
                st.stop()
            
            page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. ADAY TOPLAMA (GÜÇLENDİRİLMİŞ SCROLL)
            listings = []
            prev_count = 0
            fails = 0
            
            # Huni Mantığı: 1 Mail = 50 İşletme (Garanti olsun diye)
            target_candidates = max_target * 50
            
            status_text.warning(f"Derin tarama yapılıyor... Hedef havuz: {target_candidates} işletme")
            
            while len(listings) < target_candidates:
                if not st.session_state.get('start_scraping', False): break
                
                # Standart Scroll
                page.hover('div[role="feed"]')
                page.mouse.wheel(0, 5000)
                time.sleep(1)
                
                # Liste sayısını kontrol et
                listings = page.locator('div[role="article"]').all()
                stat_candidates.metric("Havuzdaki Aday", len(listings))
