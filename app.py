"""
LeadRadar Pro — Agency Multi-Channel Lead Generation, Team CRM, Strict RBAC & Activity Audit Platform
======================================================================================================
"""

import json
import os
import re
import csv
import io
import time
import random
import threading
import webbrowser
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, unquote, quote_plus
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify, render_template, Response, session
import requests

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

app = Flask(__name__)
app.secret_key = "leadradar_pro_master_key_secure_salt_998811"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "leads.json")
SKIP_FILE = os.path.join(BASE_DIR, "skip_brands.json")
TEAM_FILE = os.path.join(BASE_DIR, "team.json")
REQUESTS_FILE = os.path.join(BASE_DIR, "team_requests.json")
LOGS_FILE = os.path.join(BASE_DIR, "activity_logs.json")
SESSION_DIR = os.path.join(BASE_DIR, "chrome_session")

COUNTRY_MAP = {
    # UAE & Gulf
    "uae": "AE", "dubai": "AE", "abu dhabi": "AE", "sharjah": "AE", "ajman": "AE", "ras al khaimah": "AE",
    "saudi arabia": "SA", "riyadh": "SA", "jeddah": "SA", "ksa": "SA", "dammam": "SA", "mecca": "SA", "medina": "SA",
    "qatar": "QA", "doha": "QA", "kuwait": "KW", "bahrain": "BH", "oman": "OM", "muscat": "OM",
    # South Asia
    "pakistan": "PK", "lahore": "PK", "karachi": "PK", "islamabad": "PK", "rawalpindi": "PK",
    "faisalabad": "PK", "multan": "PK", "peshawar": "PK", "sialkot": "PK", "gujranwala": "PK",
    "india": "IN", "delhi": "IN", "mumbai": "IN", "bangalore": "IN", "hyderabad": "IN",
    "bangladesh": "BD", "dhaka": "BD", "sri lanka": "LK", "colombo": "LK",
    # North America & Europe
    "usa": "US", "united states": "US", "america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "london": "GB",
    "canada": "CA", "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "australia": "AU", "sydney": "AU", "melbourne": "AU", "new zealand": "NZ",
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES", "netherlands": "NL",
    "turkey": "TR", "istanbul": "TR", "sweden": "SE", "norway": "NO", "switzerland": "CH",
    # Southeast Asia & Africa
    "singapore": "SG", "malaysia": "MY", "indonesia": "ID", "philippines": "PH", "thailand": "TH",
    "south africa": "ZA", "nigeria": "NG", "egypt": "EG", "cairo": "EG", "kenya": "KE",
    "brazil": "BR", "mexico": "MX"
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7"
}


# ---------------------------------------------------------------- storage

def load_leads():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_leads(leads):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


def load_skip_brands():
    if not os.path.exists(SKIP_FILE):
        return []
    try:
        with open(SKIP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_skip_brands(names):
    with open(SKIP_FILE, "w", encoding="utf-8") as f:
        json.dump(names, f, indent=2, ensure_ascii=False)


def load_team():
    if not os.path.exists(TEAM_FILE):
        default_team = [
            {"id": "admin", "name": "Admin", "email": "admin@agency.com", "role": "admin", "pin": "admin123"},
            {"id": "rep_1", "name": "Ali", "email": "ali@agency.com", "role": "rep", "pin": "1234"},
            {"id": "rep_2", "name": "Sara", "email": "sara@agency.com", "role": "rep", "pin": "1234"}
        ]
        save_team(default_team)
        return default_team
    try:
        with open(TEAM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_team(team_list):
    with open(TEAM_FILE, "w", encoding="utf-8") as f:
        json.dump(team_list, f, indent=2, ensure_ascii=False)


def load_team_requests():
    if not os.path.exists(REQUESTS_FILE):
        return []
    try:
        with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_team_requests(requests_list):
    with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(requests_list, f, indent=2, ensure_ascii=False)


def load_activity_logs():
    if not os.path.exists(LOGS_FILE):
        return []
    try:
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def log_activity(user_name: str, role: str, action_type: str, lead_id: str, lead_name: str, details: str):
    logs = load_activity_logs()
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    entry = {
        "id": make_id(),
        "timestamp": now_str,
        "raw_time": int(time.time()),
        "user_name": user_name or "Anonymous",
        "role": role or "rep",
        "action_type": action_type,
        "lead_id": lead_id,
        "lead_name": lead_name,
        "details": details
    }
    logs.insert(0, entry)
    if len(logs) > 2000:
        logs = logs[:2000]
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    return entry


def is_skipped_brand(name: str, skip_list) -> bool:
    name_lower = (name or "").lower()
    return any(skip.lower() in name_lower for skip in skip_list if skip)


def make_id():
    return f"{int(time.time() * 1000)}{random.randint(100, 999)}"


# ------------------------------------------------------------- search unwrap & extraction

def search_web_urls(query: str, limit: int = 30) -> list:
    url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}&n={max(30, limit + 10)}"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        matches = re.findall(r'href="([^"]*r\.search\.yahoo\.com/[^"]*RU=([^/"]+)[^"]*)"', r.text)
        results = []
        seen = set()
        for full_href, ru_encoded in matches:
            try:
                real_url = unquote(ru_encoded)
                if real_url.startswith("http") and not any(bad in real_url for bad in [
                    "yahoo.com", "yimg.com", "bing.com", "microsoft.com", "google.com", "wikipedia.org",
                    "youtube.com", "reddit.com", "pinterest.com", "twitter.com", "x.com"
                ]):
                    if real_url not in seen:
                        seen.add(real_url)
                        results.append(real_url)
            except Exception:
                pass
        return results[:limit]
    except Exception as e:
        print(f"[WARN] Search query '{query}' notice: {e}")
        return []


# ------------------------------------------------------------- contact normalization & extraction

def normalize_phone_number(raw_num: str, country_hint: str = "") -> str:
    if not raw_num:
        return ""
    digits = re.sub(r"\D", "", raw_num)
    if not digits or len(digits) < 7:
        return ""

    if digits.startswith("92") and len(digits) in (12, 11):
        return digits
    if digits.startswith("971") and len(digits) in (11, 12):
        return digits
    if digits.startswith("44") and len(digits) in (11, 12, 13):
        return digits
    if digits.startswith("1") and len(digits) == 11:
        return digits

    c_hint = (country_hint or "").lower()

    if digits.startswith("03") and len(digits) == 11:
        return "92" + digits[1:]
    if digits.startswith("3") and len(digits) == 10 and ("pk" in c_hint or "pakistan" in c_hint or not c_hint):
        return "92" + digits

    if digits.startswith("05") and len(digits) == 10:
        return "971" + digits[1:]
    if digits.startswith("5") and len(digits) == 9 and ("uae" in c_hint or "dubai" in c_hint or "ae" in c_hint):
        return "971" + digits

    if digits.startswith("07") and len(digits) == 11:
        return "44" + digits[1:]

    if len(digits) == 10 and ("us" in c_hint or "usa" in c_hint or "ca" in c_hint or "canada" in c_hint):
        return "1" + digits

    return digits


def extract_contacts_from_html(html: str, country_hint: str = "") -> dict:
    contacts = {
        "whatsapp": "",
        "phone": "",
        "email": "",
        "instagram": "",
        "facebook_page": ""
    }
    if not html:
        return contacts

    wa_match = re.search(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=)(\+?\d{8,16})', html, re.IGNORECASE)
    if wa_match:
        contacts["whatsapp"] = normalize_phone_number(wa_match.group(1), country_hint)
        contacts["phone"] = contacts["whatsapp"]

    if not contacts["phone"]:
        tel_match = re.search(r'href=[\'"]tel:([+\d\s\-\(\)]{8,20})[\'"]', html, re.IGNORECASE)
        if tel_match:
            phone_clean = normalize_phone_number(tel_match.group(1), country_hint)
            if len(phone_clean) >= 9:
                contacts["phone"] = phone_clean
                if not contacts["whatsapp"]:
                    contacts["whatsapp"] = phone_clean

    email_candidates = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    ignored_patterns = [
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js',
        'sentry', 'shopify.com', 'wixpress.com', 'schema.org', 'cloudflare',
        'example.com', 'domain.com', 'yourname@', 'email@', 'youremail@',
        'klaviyo', 'judgeme', 'privacypolicy', 'noreply', 'no-reply', 'test@', 'user@'
    ]
    for em in email_candidates:
        em_lower = em.lower()
        if any(bad in em_lower for bad in ignored_patterns):
            continue
        if len(em) > 45:
            continue
        contacts["email"] = em
        break

    ig_match = re.search(r'href=[\'"]https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.\-]+)/?[\'"]', html, re.IGNORECASE)
    if ig_match:
        handle = ig_match.group(1).strip()
        if handle.lower() not in ("p", "explore", "reels", "stories", "tv", "accounts"):
            contacts["instagram"] = "@" + handle

    fb_match = re.search(r'href=[\'"](https?://(?:www\.|web\.)?facebook\.com/[a-zA-Z0-9_.\-]+)/?[\'"]', html, re.IGNORECASE)
    if fb_match:
        fb_url = fb_match.group(1).strip()
        if not any(x in fb_url.lower() for x in ("sharer", "share", "tr", "dialog", "privacy", "policies", "help", "ads/library")):
            contacts["facebook_page"] = fb_url

    return contacts


def detect_currency_and_tier(html: str) -> dict:
    info = {"currency": "USD", "tier": "Standard 🏷️"}
    if not html:
        return info

    h = html.lower()
    if "pkr" in h or "rs." in h or "rs " in h:
        info["currency"] = "PKR"
    elif "aed" in h or "dhs" in h or "dirham" in h:
        info["currency"] = "AED"
    elif "sar" in h or "riyal" in h:
        info["currency"] = "SAR"
    elif "£" in h or "gbp" in h:
        info["currency"] = "GBP"
    elif "€" in h or "eur" in h:
        info["currency"] = "EUR"
    elif "$" in h:
        info["currency"] = "USD"

    price_matches = re.findall(r'(?:rs\.?|pkr|\$|aed|sar|£|€)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', html, re.IGNORECASE)
    if price_matches:
        try:
            numeric_prices = [float(p.replace(",", "")) for p in price_matches if float(p.replace(",", "")) > 0]
            if numeric_prices:
                avg_price = sum(numeric_prices[:10]) / len(numeric_prices[:10])
                if info["currency"] == "PKR":
                    info["tier"] = "High Ticket 💎" if avg_price > 8000 else "Standard 🏷️"
                elif info["currency"] in ("AED", "SAR"):
                    info["tier"] = "High Ticket 💎" if avg_price > 250 else "Standard 🏷️"
                else:
                    info["tier"] = "High Ticket 💎" if avg_price > 90 else "Standard 🏷️"
        except Exception:
            pass

    return info


# ------------------------------------------------------------- enrichment

def get_domain_age(website: str) -> str:
    try:
        domain = urlparse(website).netloc or website
        domain = domain.replace("www.", "").split(":")[0]
        if not domain or "." not in domain:
            return ""
        resp = requests.get(f"https://rdap.org/domain/{domain}", timeout=6,
                             headers={"Accept": "application/rdap+json", "User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        data = resp.json()
        reg_date = None
        for event in data.get("events", []):
            if event.get("eventAction") in ("registration", "registered", "created"):
                reg_date = event.get("eventDate")
                break
        if not reg_date:
            return ""
        dt = datetime.fromisoformat(reg_date.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        years = days // 365
        months = (days % 365) // 30
        if years >= 1:
            return f"{years}y old"
        if months >= 1:
            return f"{months}mo old"
        return f"{max(days, 0)}d old"
    except Exception:
        return ""


def detect_tech_stack(html: str) -> str:
    h = html.lower()
    if "cdn.shopify.com" in h or "shopify.theme" in h or "myshopify.com" in h or "shopify" in h:
        return "Shopify"
    if "wp-content" in h or "woocommerce" in h or "wc-ajax" in h:
        return "WooCommerce"
    if "wixstatic.com" in h or "wix.com" in h:
        return "Wix"
    if "squarespace.com" in h:
        return "Squarespace"
    if "webflow.com" in h or "wf-site" in h:
        return "Webflow"
    if "bigcommerce.com" in h:
        return "BigCommerce"
    if "magento" in h or "mage/" in h:
        return "Magento"
    return "Custom / Other"


def has_meta_pixel(html: str) -> bool:
    return "fbq(" in html or "connect.facebook.net" in html or "fbevents.js" in html


def get_pagespeed_score(url: str) -> int:
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    try:
        resp = requests.get(endpoint, params={"url": url, "strategy": "mobile"}, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            score = data["lighthouseResult"]["categories"]["performance"]["score"]
            return round(score * 100)
        return -1
    except Exception:
        return -1


def get_instagram_followers(handle: str):
    if not handle:
        return None
    handle_clean = handle.replace("@", "").strip("/")
    try:
        resp = requests.get(
            f"https://www.instagram.com/{handle_clean}/",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        m = re.search(r'"edge_followed_by":\{"count":(\d+)\}', resp.text)
        if not m:
            m = re.search(r'([\d,.]+[KMk]?)\s+Followers', resp.text)
            if m:
                raw = m.group(1).replace(",", "")
                if raw.lower().endswith("k"):
                    return int(float(raw[:-1]) * 1000)
                if raw.lower().endswith("m"):
                    return int(float(raw[:-1]) * 1_000_000)
                return int(float(raw))
            return None
        return int(m.group(1))
    except Exception:
        return None


def fetch_deep_contact_pages(website: str, city_hint: str = "") -> dict:
    contacts = {"whatsapp": "", "phone": "", "email": ""}
    subpages = ["/pages/contact", "/contact-us", "/contact", "/pages/contact-us", "/about-us", "/about"]

    for path in subpages:
        target_url = urljoin(website, path)
        try:
            r = requests.get(target_url, timeout=4, headers=HTTP_HEADERS)
            if r.status_code == 200:
                sub_c = extract_contacts_from_html(r.text, city_hint)
                if sub_c["whatsapp"] and not contacts["whatsapp"]:
                    contacts["whatsapp"] = sub_c["whatsapp"]
                if sub_c["phone"] and not contacts["phone"]:
                    contacts["phone"] = sub_c["phone"]
                if sub_c["email"] and not contacts["email"]:
                    contacts["email"] = sub_c["email"]
                if contacts["whatsapp"] or (contacts["phone"] and contacts["email"]):
                    break
        except Exception:
            continue
    return contacts


def enrich_website(lead: dict) -> dict:
    lead.setdefault("tech", "Unknown")
    lead.setdefault("pixel", False)
    lead.setdefault("pagespeed", -1)
    lead.setdefault("email", "")
    lead.setdefault("whatsapp", "")
    lead.setdefault("phone", "")
    lead.setdefault("domain_age", "")
    lead.setdefault("design_rating", 0)
    lead.setdefault("followers", None)
    lead.setdefault("facebook_page", "")
    lead.setdefault("instagram", "")
    lead.setdefault("currency", "USD")
    lead.setdefault("tier", "Standard 🏷️")
    lead.setdefault("rating", "")
    lead.setdefault("deal_value", "")

    website = lead.get("website", "").strip()
    city_hint = lead.get("city", "")
    lead["has_website"] = bool(website)

    if website:
        if not website.startswith("http"):
            website = "https://" + website
            lead["website"] = website

        html = ""
        try:
            resp = requests.get(website, timeout=8, headers=HTTP_HEADERS)
            html = resp.text
            lead["tech"] = detect_tech_stack(html)
            lead["pixel"] = has_meta_pixel(html)
        except Exception:
            lead["tech"] = "Unknown"
            lead["pixel"] = False

        if html:
            extracted = extract_contacts_from_html(html, country_hint=city_hint)
            if extracted["whatsapp"] and not lead["whatsapp"]:
                lead["whatsapp"] = extracted["whatsapp"]
            if extracted["phone"] and not lead["phone"]:
                lead["phone"] = extracted["phone"]
            if extracted["email"] and not lead["email"]:
                lead["email"] = extracted["email"]
            if extracted["instagram"] and not lead["instagram"]:
                lead["instagram"] = extracted["instagram"]
            if extracted["facebook_page"] and not lead["facebook_page"]:
                lead["facebook_page"] = extracted["facebook_page"]

            ct_info = detect_currency_and_tier(html)
            lead["currency"] = ct_info["currency"]
            lead["tier"] = ct_info["tier"]

        # Deep Contact Page Scraping
        if not lead["whatsapp"]:
            deep_c = fetch_deep_contact_pages(website, city_hint)
            if deep_c["whatsapp"]:
                lead["whatsapp"] = deep_c["whatsapp"]
                lead["phone"] = deep_c["whatsapp"]
            elif deep_c["phone"] and not lead["phone"]:
                lead["phone"] = deep_c["phone"]
                lead["whatsapp"] = deep_c["phone"]
            if deep_c["email"] and not lead["email"]:
                lead["email"] = deep_c["email"]

        lead["domain_age"] = get_domain_age(website)
        score = get_pagespeed_score(website)
        lead["pagespeed"] = score if score >= 0 else 50
        lead["mobile"] = lead["pagespeed"] >= 40
    else:
        lead["tech"] = "No website"
        lead["mobile"] = False
        if lead.get("source") == "linktree":
            lead["tier"] = "Bio Seller 🌱"
        elif lead.get("source") == "gmaps":
            lead["tier"] = "Local Business 📍"
        else:
            lead["tier"] = "Full Build 🌱"

    if lead.get("instagram"):
        followers = get_instagram_followers(lead["instagram"])
        if followers is not None:
            lead["followers"] = followers

    if lead.get("whatsapp"):
        lead["whatsapp"] = normalize_phone_number(lead["whatsapp"], city_hint)
    if lead.get("phone"):
        lead["phone"] = normalize_phone_number(lead["phone"], city_hint)

    return lead


def opportunity_score(lead: dict) -> int:
    if not lead.get("has_website", bool(lead.get("website"))):
        score = 88
        if lead.get("source") in ("gmaps", "linktree"):
            score += 6
        if lead.get("rating") and "5." in lead.get("rating", ""):
            score += 4
        return min(100, score)

    score = 0
    ps = lead.get("pagespeed", 50)
    if ps < 0:
        ps = 50
    score += max(0, 100 - ps) * 0.5
    if not lead.get("pixel"):
        score += 22
    if not lead.get("mobile", True):
        score += 15
    if lead.get("ads_active"):
        score += 18
    return min(100, round(score))


def make_blank_lead(name, niche, city, website="", instagram="", facebook_page="",
                     ads_active=False, ad_start_date="", source="meta", whatsapp="", phone="", rating="", notes=""):
    return {
        "id": make_id(),
        "business": name,
        "owner": "",
        "niche": niche,
        "city": city,
        "website": website,
        "instagram": instagram,
        "facebook_page": facebook_page,
        "whatsapp": whatsapp,
        "phone": phone,
        "rating": rating,
        "ads_active": ads_active,
        "ad_start_date": ad_start_date,
        "notes": notes,
        "follow_up_date": "",
        "assigned_to": "",
        "deal_value": "",
        "source": source,
        "status": "new",
        "added_at": int(time.time()),
    }


# --------------------------------------------------- ENGINE 1: Meta Ads Library

def parse_ads_from_html(html: str, niche: str, country_query: str, skip_list: list, limit: int = 25) -> list:
    chunks = re.split(r'Library ID:?\s*\d+', html)
    results = []
    seen = set()

    for c in chunks[1:]:
        if len(results) >= limit:
            break

        date_m = re.search(r'Started running on\s+([A-Za-z0-9,\s]+?)(?:<|·|\n|$|Platforms|EU)', c)
        ad_date = date_m.group(1).strip() if date_m else ""

        a_tags = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', c, re.DOTALL)
        
        business_name = ""
        fb_page = ""
        dest_url = ""
        ig_handle = ""

        for href, inner_html in a_tags:
            clean_text = re.sub(r'<[^>]+>', ' ', inner_html).strip()
            clean_text = re.sub(r'\s+', ' ', clean_text)

            if 'l.facebook.com/l.php' in href or 'l.php?u=' in href:
                u_match = re.search(r'[?&]u=([^&]+)', href)
                if u_match and not dest_url:
                    dest_url = unquote(u_match.group(1))
            elif 'instagram.com/' in href:
                ig_m = re.search(r'instagram\.com/([a-zA-Z0-9_.\-]+)', href)
                if ig_m and ig_m.group(1) not in ('p', 'explore', 'reels', 'stories') and not ig_handle:
                    ig_handle = '@' + ig_m.group(1)
            elif ('facebook.com/' in href or 'fb.me/' in href) and not any(x in href for x in ['/ads/library', '/policies', '/help', 'l.php', 'sharer', 'share']):
                if clean_text and len(clean_text) > 1 and len(clean_text) < 80 and not business_name:
                    clean_text = re.sub(r'Sponsored|Sponsor|Like Page|·.*$', '', clean_text).strip()
                    if clean_text:
                        business_name = clean_text
                        fb_page = href.split('?')[0]
            elif href.startswith('http') and not any(x in href for x in ['facebook.com', 'fb.me', 'instagram.com', 'fbcdn.net', 'w3.org']) and not dest_url:
                dest_url = href

        if not business_name:
            header_m = re.search(r'<span[^>]*dir="auto"[^>]*>([^<]+)</span>', c)
            if header_m:
                cand = header_m.group(1).strip()
                if len(cand) > 1 and len(cand) < 60 and not any(x in cand.lower() for x in ['library', 'started', 'active', 'platforms', 'transparency']):
                    business_name = cand

        if not business_name or is_skipped_brand(business_name, skip_list):
            continue

        key = (dest_url or business_name).lower()
        if key in seen:
            continue
        seen.add(key)

        results.append(make_blank_lead(
            name=business_name,
            niche=niche,
            city=country_query,
            website=dest_url,
            instagram=ig_handle,
            facebook_page=fb_page,
            ads_active=True,
            ad_start_date=ad_date,
            source="meta"
        ))

    return results


def scrape_ads_library(niche: str, country_query: str, limit: int = 25, prefer_recent: bool = True):
    if not PLAYWRIGHT_OK:
        raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    skip_list = load_skip_brands()
    c_query_clean = country_query.strip().lower()

    if len(country_query.strip()) == 2:
        country_code = country_query.strip().upper()
    else:
        country_code = COUNTRY_MAP.get(c_query_clean, "ALL")

    search_url = (
        "https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country_code}"
        f"&q={niche.replace(' ', '%20')}&search_type=keyword&media_type=all"
    )

    results = []
    os.makedirs(SESSION_DIR, exist_ok=True)

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=False,
                viewport={"width": 1280, "height": 820},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
            except Exception:
                pass

            try:
                for btn_text in ["Allow all cookies", "Accept all", "Decline optional cookies",
                                "Allow essential and optional cookies", "Only allow essential cookies",
                                "Accept", "Allow"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if btn.is_visible(timeout=800):
                        btn.click(timeout=800)
                        page.wait_for_timeout(800)
                        break
            except Exception:
                pass

            scroll_count = min(25, max(6, limit // 2 + 3))
            for _ in range(scroll_count):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(random.uniform(400, 750))

            page.wait_for_timeout(1500)
            try:
                page_html = page.content()
            except Exception:
                page_html = ""
            results = parse_ads_from_html(page_html, niche, country_query, skip_list, limit)
            context.close()
    except Exception as e:
        print(f"[WARN] Playwright ads library scrape notice: {e}")


    # Robust Fallback: If Meta Ads Library UI returns fewer results, dork active social & store advertisers
    if len(results) < limit:
        fallback_queries = [
            f'site:facebook.com "{niche}" "{country_query}" "Send Message" OR "WhatsApp" OR "Shop Now"',
            f'site:instagram.com "{niche}" "{country_query}" "WhatsApp" OR "order"',
            f'{niche} stores online shopping {country_query}'
        ]
        seen_keys = {(r.get("website") or r.get("business") or "").lower() for r in results}
        for q in fallback_queries:
            if len(results) >= limit:
                break
            urls = search_web_urls(q, limit=15)
            for u in urls:
                if len(results) >= limit:
                    break
                parsed = urlparse(u)
                domain = parsed.netloc.replace("www.", "").lower()
                clean_u = u.split("?")[0].rstrip("/")
                if "facebook.com/" in clean_u:
                    parts = clean_u.split("facebook.com/")[1].strip("/").split("/")
                    name = parts[0].replace(".", " ").replace("-", " ").title()
                    if name and len(name) > 2 and name.lower() not in seen_keys and not is_skipped_brand(name, skip_list):
                        seen_keys.add(name.lower())
                        results.append(make_blank_lead(name=name, niche=niche, city=country_query, facebook_page=clean_u, ads_active=True, source="meta"))
                elif "instagram.com/" in clean_u:
                    parts = clean_u.split("instagram.com/")[1].strip("/").split("/")
                    handle = parts[0].strip()
                    if handle and handle.lower() not in ("p", "explore", "reels", "stories") and handle.lower() not in seen_keys and not is_skipped_brand(handle, skip_list):
                        seen_keys.add(handle.lower())
                        results.append(make_blank_lead(name=handle.replace(".", " ").replace("_", " ").title(), niche=niche, city=country_query, instagram="@"+handle, ads_active=True, source="meta"))
                elif domain and not any(bad in domain for bad in ("yahoo.com", "bing.com", "google.com", "wikipedia.org")):
                    name = domain.split(".")[0].replace("-", " ").title()
                    if name and len(name) > 2 and name.lower() not in seen_keys and not is_skipped_brand(name, skip_list):
                        seen_keys.add(name.lower())
                        results.append(make_blank_lead(name=name, niche=niche, city=country_query, website=f"https://{domain}", ads_active=True, source="meta"))

    return results



# --------------------------------------------------- ENGINE 2: Google Maps / Places Scraper

def scrape_google_maps(niche: str, city: str, limit: int = 20):
    if not PLAYWRIGHT_OK:
        raise RuntimeError("Playwright not installed.")

    skip_list = load_skip_brands()
    query = f"{niche} in {city}"
    search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"

    results = []
    os.makedirs(SESSION_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1280, "height": 820},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
        except Exception:
            pass

        try:
            for btn_t in ["Accept all", "I agree", "Reject all", "Accept"]:
                btn = page.locator(f"button:has-text('{btn_t}')").first
                if btn.is_visible(timeout=800):
                    btn.click(timeout=800)
                    page.wait_for_timeout(1000)
                    break
        except Exception:
            pass

        try:
            feed = page.locator('div[role="feed"]').first
            for _ in range(min(15, limit // 2 + 3)):
                feed.evaluate("el => el.scrollBy(0, 2000)")
                page.wait_for_timeout(random.uniform(600, 1000))
        except Exception:
            for _ in range(8):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(800)

        page.wait_for_timeout(2000)

        items_data = page.evaluate("""
            () => {
                const list = [];
                const cards = Array.from(document.querySelectorAll('div[role="feed"] > div, a[href*="/maps/place/"]'));
                const seenTitles = new Set();

                cards.forEach(card => {
                    const text = card.innerText || '';
                    if (text.length < 10) return;

                    let title = '';
                    const titleEl = card.querySelector('.fontHeadlineSmall, [class*="headline"], [class*="Title"], .qBF1Pd');
                    if (titleEl) {
                        title = titleEl.innerText.trim();
                    } else if (card.getAttribute('aria-label')) {
                        title = card.getAttribute('aria-label').trim();
                    }

                    if (!title || ['Results', 'Search Results', 'Sponsored'].includes(title) || seenTitles.has(title)) return;
                    seenTitles.add(title);

                    let rating = '';
                    const ratingMatch = text.match(/(\\d\\.\\d)\\s*\\(?(\\d+)?\\)?/);
                    if (ratingMatch) {
                        rating = `${ratingMatch[1]} Star (${ratingMatch[2] || 'reviews'})`;
                    }

                    let phone = '';
                    const phoneMatch = text.match(/(\\+?\\d[\\d\\s\\-\\(\\)]{8,18}\\d)/);
                    if (phoneMatch) {
                        phone = phoneMatch[1].trim();
                    }

                    let website = '';
                    const webLink = card.querySelector('a[data-value="Website"], a[href^="http"]:not([href*="google.com"])');
                    if (webLink) {
                        website = webLink.href;
                    }

                    list.push({ title, rating, phone, website });
                });
                return list;
            }
        """)

        seen = set()
        for item in items_data:
            if len(results) >= limit:
                break
            name = item.get("title", "").strip()
            if not name or is_skipped_brand(name, skip_list):
                continue
            if name in seen:
                continue
            seen.add(name)

            results.append(make_blank_lead(
                name=name,
                niche=niche,
                city=city,
                website=item.get("website", ""),
                phone=item.get("phone", ""),
                whatsapp=item.get("phone", ""),
                rating=item.get("rating", ""),
                source="gmaps"
            ))

        context.close()

    return results


# --------------------------------------------------- ENGINE 3: Linktree / Bio-Link Dorker

def scrape_linktree_dorker(niche: str, country: str, limit: int = 20):
    skip_list = load_skip_brands()
    queries = [
        f'site:linktr.ee {niche} {country}',
        f'linktr.ee {niche} {country}',
        f'site:beacons.ai {niche} {country}'
    ]

    all_urls = []
    for q in queries:
        urls = search_web_urls(q, limit=limit)
        all_urls.extend(urls)
        if len(all_urls) >= limit * 2:
            break

    results = []
    seen = set()

    for raw_url in all_urls:
        if len(results) >= limit:
            break
        
        handle = ""
        clean_url = raw_url.split("?")[0].rstrip("/")
        if "linktr.ee/" in clean_url:
            handle = clean_url.split("linktr.ee/")[1].strip("/")
        elif "beacons.ai/" in clean_url:
            handle = clean_url.split("beacons.ai/")[1].strip("/")
        else:
            continue

        if not handle or handle.lower() in seen or is_skipped_brand(handle, skip_list):
            continue
        seen.add(handle.lower())

        wa_num = ""
        ig_handle = "@" + handle
        bio_title = handle.replace(".", " ").replace("-", " ").title()

        try:
            prof_resp = requests.get(clean_url, timeout=5, headers=HTTP_HEADERS)
            prof_html = prof_resp.text
            extracted = extract_contacts_from_html(prof_html, country)
            if extracted["whatsapp"]:
                wa_num = extracted["whatsapp"]
            if extracted["instagram"]:
                ig_handle = extracted["instagram"]
        except Exception:
            pass

        results.append(make_blank_lead(
            name=bio_title,
            niche=niche,
            city=country,
            website="",
            instagram=ig_handle,
            whatsapp=wa_num,
            phone=wa_num,
            source="linktree"
        ))

    return results


# --------------------------------------------------- ENGINE 4: Active E-Commerce Store Dorker

def scrape_ecommerce_dorker(niche: str, country: str, limit: int = 20):
    skip_list = load_skip_brands()
    queries = [
        f'{niche} online store {country} buy',
        f'{niche} brands online shopping {country}',
        f'site:myshopify.com {niche} {country}',
        f'{niche} store {country}'
    ]

    all_urls = []
    for q in queries:
        urls = search_web_urls(q, limit=limit)
        all_urls.extend(urls)
        if len(all_urls) >= limit * 2:
            break

    results = []
    seen = set()

    for raw_url in all_urls:
        if len(results) >= limit:
            break
        if not raw_url.startswith("http"):
            continue

        try:
            parsed = urlparse(raw_url)
            domain = parsed.netloc.replace("www.", "").lower()
        except Exception:
            continue

        if not domain or any(bad in domain for bad in [
            "shopify.com", "yahoo.com", "bing.com", "google.com", "youtube.com",
            "amazon.", "noon.com", "daraz.pk", "aliexpress.com", "ebay.com",
            "wikipedia.org", "reddit.com", "pinterest.com", "facebook.com", "instagram.com"
        ]):
            continue

        if domain in seen or is_skipped_brand(domain, skip_list):
            continue
        seen.add(domain)

        business_name = domain.split(".")[0].replace("-", " ").title()
        site_url = f"https://{domain}"

        results.append(make_blank_lead(
            name=business_name,
            niche=niche,
            city=country,
            website=site_url,
            source="ecommerce"
        ))

    return results


# ------------------------------------------------------------------ parallel enrichment

def parallel_enrich_leads(leads_list: list) -> list:
    if not leads_list:
        return []
    max_w = min(8, len(leads_list))
    with ThreadPoolExecutor(max_workers=max_w) as executor:
        enriched = list(executor.map(enrich_website, leads_list))
    return enriched


# ------------------------------------------------------------------ routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/auth/current", methods=["GET"])
def api_auth_current():
    cur = session.get("user", None)
    return jsonify(cur)


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    body = request.get_json(force=True)
    identity = (body.get("name") or body.get("email") or "").strip().lower()
    pin = (body.get("pin") or "").strip()

    team = load_team()
    
    # 1. Admin direct login
    if pin == "admin123" or identity == "admin123" or (identity == "admin" and pin == "admin123"):
        admin_member = next((m for m in team if m.get("role") == "admin"), {"id": "admin", "name": "Admin", "email": "admin@agency.com", "role": "admin", "pin": "admin123"})
        session["user"] = {"name": admin_member["name"], "email": admin_member.get("email", ""), "role": "admin", "id": "admin"}
        log_activity(admin_member["name"], "admin", "login", "", "", "Logged in as ADMIN")
        return jsonify({"ok": True, "user": session["user"]})

    # 2. Match employee by Email OR Name + PIN
    matched = None
    for member in team:
        m_name = (member.get("name") or "").strip().lower()
        m_email = (member.get("email") or "").strip().lower()
        m_pin = str(member.get("pin", "")).strip()

        if (identity in (m_name, m_email) or not identity) and pin == m_pin:
            matched = member
            break
        if identity == m_pin:
            matched = member
            break

    if not matched:
        return jsonify({"error": "Ghalat Gmail / Username ya PIN entered."}), 401

    session["user"] = {
        "name": matched["name"],
        "email": matched.get("email", ""),
        "role": matched.get("role", "rep"),
        "id": matched.get("id")
    }
    log_activity(matched["name"], matched.get("role", "rep"), "login", "", "", f"Logged in as {matched.get('role','rep').upper()} ({matched.get('email','')})")
    return jsonify({"ok": True, "user": session["user"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    u = session.get("user", {})
    if u:
        log_activity(u.get("name"), u.get("role"), "logout", "", "", "Logged out")
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/request-access", methods=["POST"])
def api_request_access():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()

    if not name or not email:
        return jsonify({"error": "Name aur Gmail dono zaroori hain"}), 400

    requests_list = load_team_requests()
    team = load_team()

    for m in team:
        if (m.get("email") or "").lower() == email:
            return jsonify({"error": f"Email '{email}' pehle se approved hai! Apna PIN daal kar login karein."}), 400

    new_req = {
        "id": f"req_{int(time.time())}",
        "name": name,
        "email": email,
        "status": "pending",
        "requested_at": datetime.now().strftime("%Y-%m-%d %I:%M %p")
    }
    requests_list.insert(0, new_req)
    save_team_requests(requests_list)
    log_activity("System", "system", "access_request", "", "", f"New Gmail Access Request from '{name}' ({email})")
    return jsonify({"ok": True, "message": "Aapki request Admin ko send ho gayi hai! Approval milte hi aap login kar sakenge."})


@app.route("/api/auth/pending-requests", methods=["GET"])
def api_get_pending_requests():
    requests_list = load_team_requests()
    pending = [r for r in requests_list if r.get("status") == "pending"]
    return jsonify(pending)


@app.route("/api/auth/approve-request", methods=["POST"])
def api_approve_request():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    req_id = body.get("request_id")
    pin = (body.get("pin") or "1234").strip()

    requests_list = load_team_requests()
    target_req = next((r for r in requests_list if r.get("id") == req_id), None)
    if not target_req:
        return jsonify({"error": "Request nahi mili"}), 404

    target_req["status"] = "approved"
    save_team_requests(requests_list)

    team = load_team()
    new_member = {
        "id": f"rep_{int(time.time())}",
        "name": target_req["name"],
        "email": target_req["email"],
        "role": "rep",
        "pin": pin
    }
    team.append(new_member)
    save_team(team)

    cur_u = session.get("user", {}).get("name", "Admin")
    log_activity(cur_u, "admin", "approve_rep", "", "", f"Approved '{target_req['name']}' ({target_req['email']}) with PIN: {pin}")
    return jsonify({"ok": True, "member": new_member, "pin": pin})


@app.route("/api/auth/reject-request", methods=["POST"])
def api_reject_request():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    req_id = body.get("request_id")
    requests_list = load_team_requests()
    target_req = next((r for r in requests_list if r.get("id") == req_id), None)
    if target_req:
        target_req["status"] = "rejected"
        save_team_requests(requests_list)
    return jsonify({"ok": True})


@app.route("/api/team", methods=["GET", "POST"])
def api_team_mgmt():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    if request.method == "GET":
        team = load_team()
        leads = load_leads()
        logs = load_activity_logs()

        for member in team:
            r_name = member.get("name", "").lower()
            assigned = [l for l in leads if (l.get("assigned_to") or "").lower() == r_name]
            contacted = [l for l in assigned if l.get("status") != "new"]
            replied = [l for l in assigned if l.get("status") == "replied"]
            closed = [l for l in assigned if l.get("status") == "closed"]
            
            rep_logs = [lg for lg in logs if (lg.get("user_name") or "").lower() == r_name]
            pitches_sent = len([lg for lg in rep_logs if lg.get("action_type") in (
                "whatsapp_click", "email_click", "instagram_dm_click", "messenger_click", "pitch_copy"
            )])
            
            member["assigned_count"] = len(assigned)
            member["contacted_count"] = len(contacted)
            member["remaining_count"] = max(0, len(assigned) - len(contacted))
            member["replied_count"] = len(replied)
            member["closed_count"] = len(closed)
            member["pitches_sent"] = pitches_sent
            member["last_active"] = rep_logs[0]["timestamp"] if rep_logs else "Never"

        return jsonify(team)

    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    pin = (body.get("pin") or "1234").strip()
    role = body.get("role", "rep")

    if not name or not email:
        return jsonify({"error": "Name aur Gmail required hain"}), 400

    team = load_team()
    new_mem = {"id": f"rep_{int(time.time())}", "name": name, "email": email, "role": role, "pin": pin}
    team.append(new_mem)
    save_team(team)
    log_activity("Admin", "admin", "team_add", "", "", f"Directly invited '{name}' ({email})")
    return jsonify({"ok": True, "member": new_mem})


@app.route("/api/team/<rep_id>", methods=["DELETE", "PATCH"])
def api_modify_team(rep_id):
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    team = load_team()
    if request.method == "DELETE":
        remaining = [m for m in team if m.get("id") != rep_id and m.get("id") != "admin"]
        save_team(remaining)
        return jsonify({"ok": True})

    # PATCH: update role or PIN
    body = request.get_json(force=True)
    for m in team:
        if m.get("id") == rep_id:
            if "role" in body:
                m["role"] = body["role"]
            if "pin" in body and body["pin"]:
                m["pin"] = str(body["pin"]).strip()
    save_team(team)
    return jsonify({"ok": True})


@app.route("/api/team/<rep_name>/reclaim-leads", methods=["POST"])
def api_reclaim_rep_leads(rep_name):
    """Admin reclaims all leads from a specific rep back to unassigned pool."""
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    leads = load_leads()
    count = 0
    for l in leads:
        if (l.get("assigned_to") or "").lower() == rep_name.lower():
            l["assigned_to"] = ""
            count += 1

    save_leads(leads)
    log_activity("Admin", "admin", "reclaim_leads", "", "", f"Reclaimed {count} leads from '{rep_name}' back to unassigned pool")
    return jsonify({"ok": True, "reclaimed_count": count})


@app.route("/api/activity-logs", methods=["GET", "POST"])
def api_activity_logs():
    cur_u = session.get("user")
    if not cur_u:
        return jsonify({"error": "Login required"}), 401

    if request.method == "GET":
        if cur_u.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        logs = load_activity_logs()
        user_filter = request.args.get("user", "")
        if user_filter and user_filter != "all":
            logs = [l for l in logs if l.get("user_name", "").lower() == user_filter.lower()]
        return jsonify(logs)

    body = request.get_json(force=True)
    user_name = cur_u.get("name", "Rep")
    role = cur_u.get("role", "rep")
    action_type = body.get("action_type", "action")
    lead_id = body.get("lead_id", "")
    lead_name = body.get("lead_name", "")
    details = body.get("details", "")

    entry = log_activity(user_name, role, action_type, lead_id, lead_name, details)
    return jsonify({"ok": True, "entry": entry})


@app.route("/api/leads/bulk-assign", methods=["POST"])
def api_bulk_assign():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    rep_name = (body.get("rep_name") or "").strip()
    count = int(body.get("count", 15))

    leads = load_leads()
    unassigned = [l for l in leads if not l.get("assigned_to")]
    assigned_now = []

    for l in unassigned[:count]:
        l["assigned_to"] = rep_name
        assigned_now.append(l["id"])

    save_leads(leads)
    log_activity("Admin", "admin", "bulk_assign", "", "", f"Assigned {len(assigned_now)} leads to {rep_name}")
    return jsonify({"ok": True, "assigned_count": len(assigned_now)})


@app.route("/api/leads/assign-selected", methods=["POST"])
def api_assign_selected():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    lead_ids = set(body.get("lead_ids", []))
    rep_name = (body.get("rep_name") or "").strip()

    leads = load_leads()
    assigned_count = 0
    for l in leads:
        if l.get("id") in lead_ids:
            l["assigned_to"] = rep_name
            assigned_count += 1

    save_leads(leads)
    log_activity("Admin", "admin", "assign_selected", "", "", f"Assigned {assigned_count} custom-selected leads to {rep_name or 'Unassigned'}")
    return jsonify({"ok": True, "assigned_count": assigned_count})



@app.route("/api/leads", methods=["GET"])
def api_get_leads():
    cur_u = session.get("user")
    if not cur_u:
        return jsonify([])

    leads = load_leads()
    for l in leads:
        l.setdefault("facebook_page", "")
        l.setdefault("instagram", "")
        l.setdefault("whatsapp", "")
        l.setdefault("phone", "")
        l.setdefault("notes", "")
        l.setdefault("follow_up_date", "")
        l.setdefault("assigned_to", "")
        l.setdefault("deal_value", "")
        l.setdefault("ad_start_date", "")
        l.setdefault("followers", None)
        l.setdefault("currency", "USD")
        l.setdefault("tier", "Standard 🏷️")
        l.setdefault("rating", "")
        l.setdefault("source", "meta")
        l["score"] = opportunity_score(l)

    # If Rep: return ONLY their assigned leads
    if cur_u.get("role") != "admin":
        rep_name = (cur_u.get("name") or "").lower()
        leads = [l for l in leads if (l.get("assigned_to") or "").lower() == rep_name]

    return jsonify(leads)


SCAN_SOURCES = {
    "meta": lambda niche, city, limit, prefer_recent: scrape_ads_library(niche, city, limit, prefer_recent),
    "gmaps": lambda niche, city, limit, prefer_recent: scrape_google_maps(niche, city, limit),
    "linktree": lambda niche, city, limit, prefer_recent: scrape_linktree_dorker(niche, city, limit),
    "ecommerce": lambda niche, city, limit, prefer_recent: scrape_ecommerce_dorker(niche, city, limit),
}


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    niche = body.get("niche", "").strip()
    city = body.get("city", "").strip()
    limit = int(body.get("limit", 20))
    source = body.get("source", "meta")
    prefer_recent = bool(body.get("prefer_recent", True))

    if not niche or not city:
        return jsonify({"error": "Niche aur Country / City dono likhein"}), 400

    scan_fn = SCAN_SOURCES.get(source)
    if not scan_fn:
        return jsonify({"error": f"Invalid source '{source}'"}), 400

    try:
        raw_leads = scan_fn(niche, city, limit, prefer_recent)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    enriched = parallel_enrich_leads(raw_leads)

    leads = load_leads()
    existing_keys = {
        (l.get("website") or "").lower().replace("www.", "") if l.get("website") else (l.get("business") or "").lower()
        for l in leads
    }

    added = []
    for l in enriched:
        k = (l.get("website") or "").lower().replace("www.", "") if l.get("website") else (l.get("business") or "").lower()
        if k in existing_keys:
            continue
        leads.append(l)
        added.append(l)
        existing_keys.add(k)

    save_leads(leads)
    cur_u = session.get("user", {}).get("name", "Admin")
    log_activity(cur_u, "admin", "scan", "", "", f"Scanned {len(added)} new leads from '{source.upper()}' ({niche}, {city})")
    return jsonify({"added": added, "count": len(added), "source": source})


@app.route("/api/skip-brands", methods=["GET", "POST", "DELETE"])
def api_skip_brands_mgmt():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    if request.method == "GET":
        return jsonify(load_skip_brands())

    if request.method == "POST":
        body = request.get_json(force=True)
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name required"}), 400

        skip_list = load_skip_brands()
        if name.lower() not in [s.lower() for s in skip_list]:
            skip_list.append(name)
            save_skip_brands(skip_list)

        leads = load_leads()
        remaining = [l for l in leads if name.lower() not in (l.get("business", "").lower())]
        removed_count = len(leads) - len(remaining)
        save_leads(remaining)
        return jsonify({"ok": True, "skip_list": skip_list, "removed_existing": removed_count})

    save_skip_brands([])
    return jsonify({"ok": True})


@app.route("/api/manual-add", methods=["POST"])
def api_manual_add():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    body = request.get_json(force=True)
    urls = body.get("urls", [])
    niche = body.get("niche", "manual")
    city = body.get("city", "")

    leads = load_leads()
    existing_keys = {(l.get("website") or "").lower() for l in leads}
    raw_list = []

    for raw_url in urls:
        url = raw_url.strip()
        if not url:
            continue
        if not url.startswith("http"):
            url = "https://" + url
        if url.lower() in existing_keys:
            continue
        lead = make_blank_lead(
            name=url.replace("https://", "").replace("http://", "").split("/")[0],
            niche=niche,
            city=city,
            website=url,
            source="manual"
        )
        raw_list.append(lead)

    enriched = parallel_enrich_leads(raw_list)
    added = []
    for l in enriched:
        leads.append(l)
        added.append(l)
        existing_keys.add((l.get("website") or "").lower())

    save_leads(leads)
    return jsonify({"added": added, "count": len(added)})


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def api_update_lead(lead_id):
    cur_u = session.get("user")
    if not cur_u:
        return jsonify({"error": "Login required"}), 401

    body = request.get_json(force=True)
    leads = load_leads()
    user_name = cur_u.get("name", "User")
    role = cur_u.get("role", "rep")

    for l in leads:
        if l["id"] == lead_id:
            if role != "admin" and (l.get("assigned_to") or "").lower() != user_name.lower():
                return jsonify({"error": "Not assigned to you"}), 403

            if "status" in body:
                old_st = l.get("status", "new")
                l["status"] = body["status"]
                log_activity(user_name, role, "status_change", lead_id, l.get("business", ""), f"Changed status from [{old_st}] to [{body['status']}]")
            for field in ("phone", "whatsapp", "instagram", "facebook_page", "email",
                          "owner", "design_rating", "notes", "follow_up_date", "deal_value"):
                if field in body:
                    l[field] = body[field]
                    if field == "notes" and body[field]:
                        log_activity(user_name, role, "note_update", lead_id, l.get("business", ""), f"Updated note: {body[field][:45]}")
            if "assigned_to" in body and role == "admin":
                l["assigned_to"] = body["assigned_to"]

    save_leads(leads)
    return jsonify({"ok": True})


@app.route("/api/leads/<lead_id>", methods=["DELETE"])
def api_delete_lead(lead_id):
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    leads = load_leads()
    target = next((l for l in leads if l["id"] == lead_id), None)
    leads = [l for l in leads if l["id"] != lead_id]
    save_leads(leads)
    if target:
        cur_u = session.get("user", {}).get("name", "Admin")
        log_activity(cur_u, "admin", "delete_lead", lead_id, target.get("business", ""), "Deleted lead")
    return jsonify({"ok": True})


@app.route("/api/export")
def api_export():
    if session.get("user", {}).get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    leads = load_leads()
    for l in leads:
        l["score"] = opportunity_score(l)

    output = io.StringIO()
    fieldnames = ["business", "owner", "niche", "city", "website", "has_website", "tech",
                  "pagespeed", "pixel", "mobile", "currency", "tier", "domain_age", "design_rating", "rating", "followers",
                  "ads_active", "ad_start_date", "score", "source", "instagram", "facebook_page",
                  "whatsapp", "phone", "email", "notes", "assigned_to", "deal_value", "follow_up_date", "status"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(leads)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=leadradar_export.csv"},
    )


def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5050")


if __name__ == "__main__":
    if not PLAYWRIGHT_OK:
        print("WARNING: Playwright not installed — 'Scan Ads Library' will fail.")
        print("Run: pip install playwright && playwright install chromium")
        print("Manual add will still work.\n")
    threading.Thread(target=open_browser).start()
    app.run(host="0.0.0.0", port=5050, debug=False)
