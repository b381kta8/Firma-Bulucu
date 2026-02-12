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

# Yasaklı Domainler (Gereksiz vakit kaybı)
BLOCKED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", 
    "youtube.com", "pinterest.com", "trendyol.com", "hepsiburada.com", 
    "n11.com", "amazon.com", "ciceksepeti.com", "getir.com", "yemeksepeti.com",
    "google.com", "apple.com", "wikipedia.org", "sikayetvar.com"
]

# Çöp Mailler (Bunları asla kaydetme)
JUNK_EMAILS = [
    "sentry", "wixpress", "domain.com", "example.com", "email.com", 
    "noreply", "no-reply", "destek@trendyol", "yardim@", "wordpress", 
    "bootstrap", "react", "vue", "node", "support@wix"
]

# Öncelikli Mail Başlangıçları (Puanı yüksek olanlar)
PRIORITY_PREFIXES = ["info", "bilgi", "iletisim", "contact", "muhasebe", "satis", "siparis", "hello", "merhaba"]

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

def score_email(email):
    """Mailin kalitesine göre puan verir. Yüksek puanlılar seçilir."""
    score = 0
    local_part = email.split("@")[0].lower()
    
    # 1. Öncelikli kelimeler (info, bilgi vs.)
    for p in PRIORITY_PREFIXES:
        if local_part == p: score += 10
        elif local_part.startswith(p): score += 5
    
    # 2. Kurumsal görünüm (isim.soyisim genelde daha düşük önceliklidir kurumsal aramalarda)
    if "." not in local_part: score += 2 
    
    # 3. Uzunluk (Çok uzun mailler genelde çöp olur)
    if len(email) > 40: score -= 5
    
    return score

def extract_emails_from_html(html_content):
    found = set()
    # 1. DevTools Mantığı: HTML içindeki tüm 'mailto:' linklerini sök
    mailto_pattern = r'href=[\'"]mailto:([^\'" >]+)'
    for match in re.findall(mailto_pattern, html_content):
        if "@" in match:
            clean = match.split("?")[0].strip()
            found.add(clean)
            
    # 2. Text Taraması
    text_content = clean_obfuscated_email(html_content)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?!png|jpg|jpeg|gif|css|js|webp|svg|woff|ttf|wav|mp3)[a-zA-Z]{2,}'
    for email in re.findall(email_pattern, text_content):
        if len(email) < 50: found.add(email.lower())
    
    # FİLTRELEME VE SIRALAMA
    valid_emails = []
    for em in found:
        # Çöp filtre
        if any(junk in em for junk in JUNK_EMAILS): continue
        # Uzantı filtre
        if em.endswith((".png", ".jpg", ".js", ".css")): continue
        
        valid_emails.append(em)
        
    # Puanlama sistemine göre sırala (En yüksek puanlı en başa)
    valid_emails.sort(key=score_email, reverse=True)
    
    return valid_emails

def convert_df(df):
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Firmalar')
    return output.getvalue()

def kill_popups(page):
    try:
        page.keyboard.press("Escape")
        targets = ["Kabul Et", "Accept", "Tamam", "OK", "Kapat", "Close", "Reddet", "Onayla", "Allow"]
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

st.title("☁️ Joy Refund Ajanı (Akıllı Mail Avcısı)")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("📥 İndirme Paneli")
    download_placeholder = st.empty()
    
    st.divider()
    st.header("Ayarlar")
    city = st.text_input("İl", "İstanbul")
    district = st.text_input("İlçe", "Kadıköy")
    keyword = st.text_input("Sektör", "Giyim Mağazası")
    
    st.divider()
    if st.button("Başlat", type="primary"):
        st.session_state['start_scraping'] = True
        st.session_state['results'] = []
        st.session_state['processed_urls'] = set()
    
    if st.button("Durdur"):
        st.session_state['start_scraping'] = False

def update_download_button():
    if len(st.session_state['results']) > 0:
        df = pd.DataFrame(st.session_state['results'])
        download_placeholder.empty()
        download_placeholder.download_button(
            label=f"📂 Excel İndir ({len(df)} Kayıt)", 
            data=convert_df(df), 
            file_name="sonuc_listesi.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_btn_{len(df)}"
        )
    else:
        download_placeholder.info("Henüz kayıt bulunamadı.")

update_download_button()

# --- İSTATİSTİKLER ---
st.subheader("📊 İlerleme Durumu")
progress_bar = st.progress(0)
status_text = st.empty()

c1, c2, c3 = st.columns(3)
stat_havuz = c1.metric("Toplam Havuz", 0)
stat_taranan = c2.metric("İncelenen", 0)
stat_mail = c3.metric("✅ Bulunan Mail", len(st.session_state['results']))

st.write("---")
col_screen, col_table = st.columns([1, 1])

with col_screen:
    st.subheader("📺 Botun Gözü (Canlı)")
    screenshot_placeholder = st.empty()
    live_status = st.empty()

with col_table:
    st.subheader("📋 Sonuç Listesi")
    result_table = st.empty()
    if len(st.session_state['results']) > 0:
        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)

def update_screenshot(page, msg):
    try:
        path = "live.png"
        page.screenshot(path=path)
        screenshot_placeholder.image(path, caption=msg, use_container_width=True)
        live_status.info(msg)
    except: pass

# --- MOTOR ---
if st.session_state.get('start_scraping', False):
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        context.set_default_timeout(20000)
        
        map_page = context.new_page()

        try:
            # 1. ARAMA
            search_query = f"{city} {district} {keyword}"
            update_screenshot(map_page, "Google Maps Açılıyor...")
            
            map_page.goto("https://www.google.com/maps?hl=tr")
            try: map_page.get_by_role("button", name="Tümünü kabul et").click(timeout=3000)
            except: pass

            try:
                sb = map_page.locator("input#searchboxinput").or_(map_page.locator("input[name='q']")).first
                sb.wait_for(state="visible", timeout=30000)
                sb.fill(search_query)
                map_page.keyboard.press("Enter")
                time.sleep(2)
                update_screenshot(map_page, f"Aranıyor: {search_query}")
            except: 
                st.error("Arama kutusu bulunamadı.")
                st.stop()
            
            map_page.wait_for_selector('div[role="feed"]', timeout=30000)
            
            # 2. HAVUZ TOPLAMA (SONSUZ)
            listings = []
            prev_count = 0
            fails = 0
            
            status_text.warning("HAVUZ TOPLANIYOR... Bu işlem listenin sonuna kadar devam edecek.")
            
            while True:
                if not st.session_state.get('start_scraping', False): break
                
                map_page.hover('div[role="feed"]')
                map_page.mouse.wheel(0, 5000)
                time.sleep(0.5)
                map_page.keyboard.press("End")
                time.sleep(1)
                
                listings = map_page.locator('div[role="article"]').all()
                count = len(listings)
                stat_havuz.metric("Toplam Havuz", count)
                
                if count % 40 == 0:
                    update_screenshot(map_page, f"Havuz Toplanıyor... ({count} adet)")
                
                if count == prev_count:
                    fails += 1
                    map_page.mouse.wheel(0, -500)
                    time.sleep(0.5)
                    map_page.mouse.wheel(0, 3000)
                    
                    if fails > 15:
                        update_screenshot(map_page, f"Liste Sonu! Toplam {count} işletme.")
                        break
                else: fails = 0
                prev_count = count

            status_text.success(f"Analiz Başlıyor! {len(listings)} işletme.")
            
            # 3. İNATÇI VE AKILLI ANALİZ
            visit_page = context.new_page()
            
            for idx, listing in enumerate(listings):
                if not st.session_state.get('start_scraping', False): break
                if (idx % 30 == 0): gc.collect()

                progress = (idx + 1) / len(listings)
                progress_bar.progress(progress)
                status_text.info(f"Analiz: %{int(progress*100)} ({idx+1} / {len(listings)})")
                stat_taranan.metric("İncelenen", idx+1)

                try:
                    listing.scroll_into_view_if_needed()
                    listing.click(timeout=3000)
                    time.sleep(1.5)
                    
                    # Panel Kaydırma
                    try:
                        map_page.locator('div[role="main"]').first.focus()
                        map_page.keyboard.press("PageDown")
                        time.sleep(0.5)
                    except: pass
                    
                    # Web Sitesi Bulma
                    website = None
                    try:
                        wb = map_page.locator('[data-item-id="authority"]').first
                        if wb.count() > 0: website = wb.get_attribute("href")
                        
                        if not website:
                            wb = map_page.locator("a", has_text="Web sitesi").first
                            if wb.count() > 0: website = wb.get_attribute("href")
                            
                        if not website:
                            wb = map_page.locator("a", has_text="Website").first
                            if wb.count() > 0: website = wb.get_attribute("href")
                    except: pass
                    
                    name = "Firma"
                    try: name = map_page.locator('h1.DUwDvf').first.inner_text()
                    except: pass
                    
                    update_screenshot(map_page, f"Analiz: {name} (Site: {'VAR' if website else 'YOK'})")
                    
                    if not website: continue
                    
                    clean_url = website.rstrip("/")
                    if clean_url in st.session_state['processed_urls']: continue
                    st.session_state['processed_urls'].add(clean_url)
                    
                    if any(d in website for d in BLOCKED_DOMAINS): continue
                    
                    update_screenshot(visit_page, f"Siteye Giriliyor: {name}")
                    
                    # --- SİTE TARAMA ---
                    email = None
                    verification_status = "Bilinmiyor"
                    
                    try:
                        # 1. Ana Sayfa
                        visit_page.goto(website, timeout=12000, wait_until="domcontentloaded")
                        kill_popups(visit_page)
                        
                        # Footer'a zorla in
                        visit_page.keyboard.press("End") 
                        time.sleep(0.5)
                        
                        emails = extract_emails_from_html(visit_page.content())
                        
                        # Eğer kaliteli bir mail (info, bilgi) bulunduysa direkt al ve çık
                        # Eğer bulunamadıysa veya şahıs maili varsa ALT SAYFALARA BAK
                        best_email_found = False
                        if emails and score_email(emails[0]) >= 5: # Yüksek puanlı mail bulundu
                             best_email_found = True
                        
                        if not best_email_found:
                            # HEDEF SAYFALAR: KVKK, İLETİŞİM, KÜNYE
                            # Bu kelimeler genelde footerda veya menüde olur
                            target_keywords = ["kvkk", "aydınlatma", "gizlilik", "privacy", "iletişim", "contact", "künye", "hakkımızda", "bize ulaşın"]
                            
                            links = visit_page.locator("a").all()
                            priority_urls = []
                            
                            for lnk in links:
                                try:
                                    href = lnk.get_attribute("href")
                                    text = lnk.inner_text().lower()
                                    if href:
                                        full_url = urljoin(website, href)
                                        # Sadece aynı domain içinde kal
                                        if urlparse(website).netloc in full_url:
                                            # Link metninde veya url'de anahtar kelime var mı?
                                            if any(k in text for k in target_keywords) or any(k in href.lower() for k in target_keywords):
                                                priority_urls.append(full_url)
                                except: continue
                            
                            # Tekrar edenleri temizle ve en fazla 3 sayfaya git
                            priority_urls = list(set(priority_urls))[:3]
                            
                            for sub_url in priority_urls:
                                try:
                                    update_screenshot(visit_page, f"Derin Arama: {sub_url}")
                                    visit_page.goto(sub_url, timeout=10000, wait_until="domcontentloaded")
                                    kill_popups(visit_page)
                                    visit_page.keyboard.press("End") # Footer'a in
                                    time.sleep(0.5)
                                    
                                    sub_emails = extract_emails_from_html(visit_page.content())
                                    if sub_emails:
                                        emails.extend(sub_emails)
                                except: pass

                        # E-postaları tekrar sırala (En iyi mail en üste)
                        if emails:
                            # Tekrarları sil ve sırala
                            emails = list(set(emails))
                            emails.sort(key=score_email, reverse=True)
                            
                            for em in emails:
                                if em in [r['E-posta'] for r in st.session_state['results']]: continue
                                is_verified = verify_domain_mx(em)
                                email = em
                                verification_status = "Doğrulandı" if is_verified else "Doğrulanamadı"
                                break 
                    except Exception as e: pass
                    
                    if email:
                        st.session_state['results'].append({
                            "Firma": name, "İl": city, "İlçe": district, "Web": website, "E-posta": email, "Durum": verification_status
                        })
                        result_table.dataframe(pd.DataFrame(st.session_state['results']), use_container_width=True)
                        stat_mail.metric("✅ Bulunan", len(st.session_state['results']))
                        
                        update_download_button()
                        update_screenshot(visit_page, f"✅ BULUNDU: {email}")
                        time.sleep(0.5)

                except: continue
            
            if st.session_state['start_scraping']:
                st.session_state['start_scraping'] = False
                status_text.success("TÜM İŞLEMLER TAMAMLANDI!")
                progress_bar.progress(1.0)
                st.balloons()

        except Exception as e:
            st.error(f"Hata: {e}")
        finally:
            browser.close()
            st.session_state['start_scraping'] = False
