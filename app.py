import io
import re
import time
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

# ---------------- Config ----------------
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/17.0 Safari/605.1.15"
}
THROTTLE_DEFAULT = 0.8  # seconds between requests

# ---------------- HTTP helpers ----------------
def get(url: str, *, params=None, headers=None, timeout=15):
    try:
        r = requests.get(url, params=params, headers=headers or UA, timeout=timeout)
        if r.status_code == 200:
            return r
    except Exception:
        return None
    return None

@st.cache_data(show_spinner=False)
def cached_get(url: str, params_key: str = "") -> Optional[str]:
    params = None
    if params_key:
        try:
            import json
            params = json.loads(params_key)
        except Exception:
            params = None
    r = get(url, params=params)
    return r.text if r else None

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower()) if isinstance(s, str) else ""

# ---------------- Search ----------------
def ddg_html_search(query: str, site: Optional[str] = None, region: str = "uk") -> List[str]:
    q = query + (f" site:{site}" if site else "")
    url = "https://duckduckgo.com/html/"
    import json
    html = cached_get(url, params_key=json.dumps({"q": q, "kl": region}))
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a.result__a"):
        href = a.get("href")
        if href:
            links.append(href)
    return links[:5]

# ---------------- Adapters ----------------
class Adapter:
    name = "base"
    domain = ""
    market = "UK"
    def search(self, query: str) -> List[str]:
        return []
    def parse(self, url: str, ean: Optional[str], product_name: Optional[str]) -> Optional[Tuple[float, str]]:
        return None

class SephoraUK(Adapter):
    name = "Sephora UK"
    domain = "sephora.co.uk"
    market = "UK"
    def search(self, query: str) -> List[str]:
        return ddg_html_search(query, site=self.domain)
    def parse(self, url: str, ean: Optional[str], product_name: Optional[str]) -> Optional[Tuple[float, str]]:
        html = cached_get(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        price_el = soup.select_one('[data-testid="pdp-price-now"], [data-test="product-price"], [data-automation="product-price"]')
        if not price_el:
            meta = soup.select_one('meta[itemprop="price"]')
            if meta and meta.get("content"):
                try:
                    return (float(meta.get("content")), url)
                except Exception:
                    pass
        if price_el:
            text = price_el.get_text(" ", strip=True)
            m = re.search(r"£\s*(\d+[\.,]?\d*)", text)
            if m:
                return (float(m.group(1).replace(",", "")), url)
        return None

class SpaceNK(Adapter):
    name = "Space NK"
    domain = "spacenk.com"
    market = "UK"
    def search(self, query: str) -> List[str]:
        return ddg_html_search(query, site=self.domain)
    def parse(self, url: str, ean: Optional[str], product_name: Optional[str]) -> Optional[Tuple[float, str]]:
        html = cached_get(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        price_el = soup.select_one('[data-test="pdp-price"], .product-price, [itemprop="price"]')
        if price_el:
            text = price_el.get_text(" ", strip=True)
            m = re.search(r"£\s*(\d+[\.,]?\d*)", text)
            if m:
                return (float(m.group(1).replace(",", "")), url)
        meta = soup.select_one('meta[itemprop="price"]')
        if meta and meta.get("content"):
            try:
                return (float(meta.get("content")), url)
            except Exception:
                pass
        return None

class BootsUK(Adapter):
    name = "Boots UK"
    domain = "boots.com"
    market = "UK"
    def search(self, query: str) -> List[str]:
        return ddg_html_search(query, site=self.domain)
    def parse(self, url: str, ean: Optional[str], product_name: Optional[str]) -> Optional[Tuple[float, str]]:
        html = cached_get(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        price_el = soup.select_one('[data-e2e="product-price"], .price__now, .product__price, [itemprop="price"]')
        if price_el:
            text = price_el.get_text(" ", strip=True)
            m = re.search(r"£\s*(\d+[\.,]?\d*)", text)
            if m:
                return (float(m.group(1).replace(",", "")), url)
        meta = soup.select_one('meta[itemprop="price"]')
        if meta and meta.get("content"):
            try:
                return (float(meta.get("content")), url)
            except Exception:
                pass
        return None

ADAPTERS = {"UK": [SephoraUK(), SpaceNK(), BootsUK()]}
