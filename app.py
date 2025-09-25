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

# ---------------- Lookup core ----------------
def lookup_rrp(ean: Optional[str], product: str, market: str, throttle: float) -> Optional[Tuple[float, str, str]]:
    adapters = ADAPTERS.get(market, [])
    if not adapters:
        return None
    query = product
    if isinstance(ean, str) and ean.strip():
        query = f"{product} {ean}"
    for adapter in adapters:
        links = adapter.search(query)
        for url in links:
            try:
                res = adapter.parse(url, ean, product)
            except Exception:
                res = None
            if res:
                price, src = res
                return price, ("GBP" if market == "UK" else ""), src
        if throttle:
            time.sleep(throttle)
    return None

# ---------------- UI ----------------
st.set_page_config(page_title="RRP Lookup Tool", layout="wide")
st.title("RRP Lookup Tool")

st.write("Upload an Excel/CSV with **EAN** and/or **Product** columns. Pick a market. Get RRPs with source links back.")

colA, colB = st.columns([2,1])
with colB:
    market = st.selectbox("Target Market", options=list(ADAPTERS.keys()), index=0)
    throttle = st.slider("Delay between retailer requests (seconds)", 0.0, 2.0, THROTTLE_DEFAULT, 0.1)

with colA:
    upl = st.file_uploader("Upload Excel or CSV", type=["xlsx","xls","csv"])

if upl is not None:
    if upl.name.lower().endswith(".csv"):
        df = pd.read_csv(upl)
    else:
        df = pd.read_excel(upl)

    cols = list(df.columns)
    ean_col = None
    prod_col = None
    for c in cols:
        if norm(c) in ("ean","barcode","gtin"):
            ean_col = c
        if norm(c) in ("product","name","title","description"):
            prod_col = c
    if prod_col is None and len(cols) >= 2:
        prod_col = cols[1]
    if ean_col is None and len(cols) >= 1:
        ean_col = cols[0]

    st.write(f"Detected columns → EAN: **{ean_col}**, Product: **{prod_col}**")

    if st.button("Run Lookup"):
        out = df.copy()
        out["RRP"] = None
        out["Currency"] = None
        out["Source URL"] = None
        out["Pulled At"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        progress = st.progress(0.0, text="Looking up RRPs…")
        n = len(out)
        for i, row in out.iterrows():
            ean = str(row.get(ean_col, "")) if ean_col else ""
            product = str(row.get(prod_col, "")) if prod_col else ""
            if product or ean:
                res = lookup_rrp(ean, product, market, throttle)
                if res:
                    price, curr, src = res
                    out.at[i, "RRP"] = price
                    out.at[i, "Currency"] = curr
                    out.at[i, "Source URL"] = src
            progress.progress((i+1)/max(1,n), text=f"Processed {i+1}/{n}")

        st.success("Lookup complete.")
        bio = io.BytesIO()
        if upl.name.lower().endswith((".xlsx",".xls")):
            with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                out.to_excel(writer, index=False)
            st.download_button("Download results (.xlsx)", data=bio.getvalue(),
                               file_name="rrp_results.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            csv = out.to_csv(index=False).encode("utf-8")
            st.download_button("Download results (.csv)", data=csv,
                               file_name="rrp_results.csv", mime="text/csv")

        st.dataframe(out, use_container_width=True)
else:
    st.info("Upload a file to begin. Name columns EAN / Product where possible.")
