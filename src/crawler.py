"""
WatchCrawler - Lab03 EC312 (Nguyen Van Gia Bao - 24520176)
Thu thap san pham DONG HO tu 2 san TMDT qua API JSON, xuat file CSV
theo "Mau nhap san pham" cua WooCommerce (tham khao sample_import_product_for_woocommerce.txt).

  - Tiki        : https://tiki.vn/api/personalish/v1/blocks/listings  (danh sach)
                  https://tiki.vn/api/v2/products/<id>                 (chi tiet)
  - WatchStore  : https://www.watchstore.vn/products.json              (Shopify API)

Su dung (dong lenh):
  python crawler.py --site all --limit 200
  python crawler.py --site tiki --category 1778 --limit 100 --min-price 505000 --keyword casio
Giao dien:  python app.py  ->  http://127.0.0.1:5050
"""
import argparse
import csv
import html
import re
import threading
import time

# curl_cffi gia lap TLS fingerprint cua Chrome -> tranh bi Shopify chan (HTTP 429)
from curl_cffi import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SESSION = requests.Session(impersonate="chrome")
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

# Danh muc dong ho tren Tiki (lay tu /api/v2/categories?parent_id=8371)
TIKI_CATEGORIES = {1778: "Đồng hồ nam", 977: "Đồng hồ nữ", 11375: "Đồng hồ trẻ em"}

# Cot cua mau nhap WooCommerce (giong file sample)
COLUMNS = [
    "ID", "Type", "SKU", "Name", "Published", "Is featured?", "Visibility in catalog",
    "Short description", "Description", "Tax status", "In stock?", "Stock",
    "Backorders allowed?", "Sold individually?", "Weight(kg)", "Allow customer reviews?",
    "Sale price", "Regular price", "Categories", "Tags", "Images", "External URL",
    "Position",
    "Attribute 1 name", "Attribute 1 value(s)", "Attribute 1 visible", "Attribute 1 global",
    "Attribute 2 name", "Attribute 2 value(s)", "Attribute 2 visible", "Attribute 2 global",
    "Attribute 3 name", "Attribute 3 value(s)", "Attribute 3 visible", "Attribute 3 global",
]


class Options:
    """Tuy chinh cho crawler (dung chung cho dong lenh va giao dien)."""
    def __init__(self, limit=50, min_price=0, max_price=0, keyword="", max_images=5,
                 delay=0.3, only_sale=False):
        self.limit = limit              # so san pham toi da moi nguon / danh muc
        self.min_price = min_price      # loc gia (0 = khong loc)
        self.max_price = max_price
        self.keyword = keyword.lower().strip()  # chi lay san pham co tu khoa trong ten
        self.max_images = max_images    # so anh toi da moi san pham
        self.delay = delay              # nghi giua cac request (giay)
        self.only_sale = only_sale      # chi lay san pham dang giam gia

    def accept(self, name, price, regular):
        if self.keyword and self.keyword not in (name or "").lower():
            return False
        if self.min_price and price < self.min_price:
            return False
        if self.max_price and price > self.max_price:
            return False
        if self.only_sale and not (regular and regular > price):
            return False
        return True


LOG = print                  # giao dien thay bang ham ghi log rieng
STOP = threading.Event()     # giao dien bat co nay de dung crawler


def get_json(url, params=None, retries=5):
    """GET JSON co retry + nghi giua cac lan goi de tranh bi chan (HTTP 429)."""
    for i in range(retries):
        if STOP.is_set():
            return None
        try:
            r = SESSION.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            LOG(f"  ! HTTP {r.status_code} {url}")
            if r.status_code == 429:  # bi gioi han toc do -> cho lau hon
                time.sleep(int(r.headers.get("Retry-After", 0) or 0) or 15 * (i + 1))
                continue
        except Exception as e:
            LOG(f"  ! loi {e}")
        time.sleep(1.5 * (i + 1))
    return None


def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def make_row(sku, name, desc, short, regular, sale, category, tags, images, url, attrs, max_images=5):
    row = dict.fromkeys(COLUMNS, "")
    row.update({
        "Type": "simple", "SKU": sku, "Name": name, "Published": 1, "Is featured?": 0,
        "Visibility in catalog": "visible", "Short description": short, "Description": desc,
        "Tax status": "taxable", "In stock?": 1, "Stock": "", "Backorders allowed?": 0,
        "Sold individually?": 0, "Allow customer reviews?": 1,
        "Regular price": int(regular) if regular else "",
        "Sale price": int(sale) if sale and regular and sale < regular else "",
        "Categories": category, "Tags": ", ".join(t for t in tags if t),
        # WordPress chi nhan jpg/png/webp -> bo anh .avif, .gif...
        "Images": ", ".join([u for u in images if re.search(r"\.(jpe?g|png|webp)$", u, re.I)][:max_images]),
        "External URL": url, "Position": 0,
    })
    for i, (k, v) in enumerate(list(attrs.items())[:3], 1):
        row[f"Attribute {i} name"] = k
        row[f"Attribute {i} value(s)"] = str(v).replace(",", " ")
        row[f"Attribute {i} visible"] = 1
        row[f"Attribute {i} global"] = 1
    return row


# ----------------------------- TIKI -----------------------------
def crawl_tiki(category_id, opt, on_item=None):
    cat_name = TIKI_CATEGORIES.get(category_id, f"Tiki {category_id}")
    rows, page = [], 1
    LOG(f"[Tiki] Danh muc {category_id} - {cat_name}")
    while len(rows) < opt.limit and not STOP.is_set():
        data = get_json("https://tiki.vn/api/personalish/v1/blocks/listings",
                        {"limit": 40, "category": category_id, "page": page})
        items = (data or {}).get("data", [])
        if not items:
            break
        LOG(f"  trang {page}: {len(items)} san pham")
        for it in items:
            if len(rows) >= opt.limit or STOP.is_set():
                break
            # loc so bo bang du lieu trang danh sach -> do phai goi API chi tiet
            if not opt.accept(it.get("name"), it.get("price") or 0,
                              it.get("original_price") or it.get("list_price")):
                continue
            d = get_json(f"https://tiki.vn/api/v2/products/{it['id']}")
            if not d or not d.get("price"):
                continue
            brand = (d.get("brand") or {}).get("name", "")
            attrs = {"Thương hiệu": brand} if brand else {}
            for grp in d.get("specifications") or []:
                for a in grp.get("attributes", []):
                    if a.get("code") in ("origin", "brand_country", "material", "water_resistance"):
                        attrs[a["name"]] = clean_text(a["value"])
            imgs = [im.get("base_url") for im in d.get("images", []) if im.get("base_url")]
            regular = d.get("original_price") or d.get("list_price") or d["price"]
            row = make_row(
                sku=f"TIKI-{d['id']}", name=d["name"],
                desc=d.get("description", ""), short=d.get("short_description", ""),
                regular=regular, sale=d["price"],
                category=f"Đồng hồ > {cat_name}", tags=[brand, "Tiki"],
                images=imgs, url=f"https://tiki.vn/{d.get('url_path', '')}", attrs=attrs,
                max_images=opt.max_images)
            rows.append(row)
            LOG(f"   + [{len(rows):3}] {d['name'][:60]} - {d['price']:,}đ")
            if on_item:
                on_item(row, "Tiki")
            time.sleep(opt.delay)
        page += 1
    return rows


# --------------------------- WATCHSTORE (Shopify) ---------------------------
def crawl_watchstore(opt, on_item=None):
    rows, page = [], 1
    LOG("[WatchStore] https://www.watchstore.vn/products.json")
    while len(rows) < opt.limit and not STOP.is_set():
        data = get_json("https://www.watchstore.vn/products.json", {"limit": 250, "page": page})
        products = (data or {}).get("products", [])
        if not products:
            break
        LOG(f"  trang {page}: {len(products)} san pham")
        for p in products:
            if len(rows) >= opt.limit or STOP.is_set():
                break
            v = p["variants"][0]
            price = float(v.get("price") or 0)
            if price <= 0 or not p.get("images"):
                continue  # bo san pham chua co gia / anh
            compare = float(v.get("compare_at_price") or 0)
            if not opt.accept(p["title"], price, compare):
                continue
            regular, sale = (compare, price) if compare > price else (price, None)
            ptype = p.get("product_type") or ""
            if not ptype:  # Shopify khong co loai -> suy ra tu ten san pham
                t = p["title"].lower()
                ptype = "Đồng hồ nữ" if "nữ" in t else "Đồng hồ nam" if "nam" in t else "Khác"
            attrs = {"Thương hiệu": p.get("vendor", "")}
            for o in p.get("options", []):
                if o["name"] != "Title":
                    attrs[o["name"]] = " | ".join(o["values"])
            body = p.get("body_html") or ""
            row = make_row(
                sku=v.get("sku") or f"WS-{p['id']}", name=p["title"], desc=body,
                short=clean_text(body)[:200], regular=regular, sale=sale,
                category=f"Đồng hồ > {ptype}" if ptype != "Khác" else "Đồng hồ",
                tags=[p.get("vendor"), "WatchStore"],
                images=[im["src"].split("?")[0] for im in p["images"]],
                url=f"https://www.watchstore.vn/products/{p['handle']}", attrs=attrs,
                max_images=opt.max_images)
            rows.append(row)
            LOG(f"   + [{len(rows):3}] {p['title'][:60]} - {price:,.0f}đ")
            if on_item:
                on_item(row, "WatchStore")
        page += 1
        time.sleep(1)
    return rows


def run(sites, categories, opt, on_item=None):
    rows = []
    if "tiki" in sites:
        for c in categories:
            rows += crawl_tiki(c, opt, on_item)
    if "watchstore" in sites:
        rows += crawl_watchstore(opt, on_item)
    return rows


def save_csv(rows, path):
    seen, uniq = set(), []
    for r in rows:  # loai trung SKU
        if r["SKU"] not in seen:
            seen.add(r["SKU"])
            uniq.append(r)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(uniq)
    LOG(f"\n==> Da ghi {len(uniq)} san pham vao {path}")
    return len(uniq)


def main():
    ap = argparse.ArgumentParser(description="Crawler dong ho Tiki + WatchStore -> WooCommerce CSV")
    ap.add_argument("--site", choices=["tiki", "watchstore", "all"], default="all")
    ap.add_argument("--category", type=int, nargs="*", default=[1778, 977],
                    help="ID danh muc Tiki (1778 nam, 977 nu, 11375 tre em)")
    ap.add_argument("--limit", type=int, default=50, help="So san pham moi danh muc/site")
    ap.add_argument("--min-price", type=int, default=0, help="Gia thap nhat (VND)")
    ap.add_argument("--max-price", type=int, default=0, help="Gia cao nhat (VND), 0 = khong gioi han")
    ap.add_argument("--keyword", default="", help="Chi lay san pham co tu khoa trong ten")
    ap.add_argument("--only-sale", action="store_true", help="Chi lay san pham dang giam gia")
    ap.add_argument("--max-images", type=int, default=5, help="So anh toi da moi san pham")
    ap.add_argument("--delay", type=float, default=0.3, help="Nghi giua cac request (giay)")
    ap.add_argument("--out", default="output/woocommerce_watches.csv")
    a = ap.parse_args()
    opt = Options(a.limit, a.min_price, a.max_price, a.keyword, a.max_images, a.delay, a.only_sale)
    sites = ["tiki", "watchstore"] if a.site == "all" else [a.site]
    save_csv(run(sites, a.category, opt), a.out)


if __name__ == "__main__":
    main()
