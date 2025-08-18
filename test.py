#!/usr/bin/env python3
import json
import requests
import xmlrpc.client

# ---------------- KONFIG ----------------
mapping_path = "product_mapping.json"

# Odoo
odoo_url = "http://212.244.158.38:8071"
odoo_db = "odoo17_prod"
odoo_user = "admin"
odoo_pwd = "admin"

# WooCommerce
wc_url = "https://konik.ai"
wc_ck = "ck_128c9e2b6b642e9394dd2ba331eba38a85b055a3"
wc_cs = "cs_1f308bf584564db809e16d8f41a95749c604dcc9"
# ----------------------------------------

def show_wc_odoo_names():
    # --- Wczytaj mapowanie (Woo product_id -> Odoo barcode)
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)  # np. { "123": "5901111111111", "124": "5902222222222" }

    # --- WooCommerce produkty (po ID)
    wc_products = {}
    for wc_id in mapping.keys():
        r = requests.get(f"{wc_url}/wp-json/wc/v3/products/{wc_id}",
                         auth=(wc_ck, wc_cs))
        r.raise_for_status()
        p = r.json()
        wc_products[str(p["id"])] = p["name"]

    # --- Odoo produkty (po barcode)
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
    uid = common.authenticate(odoo_db, odoo_user, odoo_pwd, {})
    if not uid:
        raise RuntimeError("Nieudane logowanie do Odoo")
    models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")

    barcodes = list(mapping.values())
    odoo_products = models.execute_kw(
        odoo_db, uid, odoo_pwd,
        'product.product', 'search_read',
        [[['barcode', 'in', barcodes]]],
        {'fields': ['barcode', 'name']}
    )
    odoo_map = {p['barcode']: p['name'] for p in odoo_products if p.get('barcode')}

    # --- Wypisz pary nazw
    print("Woo → Odoo")
    print("----------")
    for wc_id, barcode in mapping.items():
        wc_name = wc_products.get(str(wc_id), "❌ brak w Woo")
        odoo_name = odoo_map.get(barcode, "❌ brak w Odoo")
        print(f"{wc_name}  →  {odoo_name}")

if __name__ == "__main__":
    show_wc_odoo_names()
