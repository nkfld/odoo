from woocommerce import API
import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

# --- Config from .env ---
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

WC_URL = os.getenv("WC_URL")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")

# --- Connect to Odoo ---
common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

# --- Connect to WooCommerce ---
wcapi = API(
    url=WC_URL,
    consumer_key=WC_CONSUMER_KEY,
    consumer_secret=WC_CONSUMER_SECRET,
    version="wc/v3",
    timeout=30
)

# --- Mapping WooCommerce ID -> Odoo barcode ---
product_map = {
    # Przykład: 101: "5901234567890",
    13782: "202500000059",
    13783: "202500000053",
    13784: "202500000061",
    13787: "202500000059",
    13788: "202500000059",
    13806: "202500000065",
    13807: "202500000066",
    13808: "202500000078",
    13809: "202500000067",
    13810: "202500000055",
    13811: "202500000052",
    13812: "202500000073",
    13813: "202500000066",
    13815: "202500000069",
    13816: "202500000070",
    13817: "202500000061",
    13818: "202500000062",
    13820: "202500000058",
    13835: "202500000061",
    13836: "202500000062",
    13849: "202500000063",
    14050: "202500000081",
    14051: "202500000082",
    14052: "202500000079",
    14053: "202500000079",
    14054: "202500000082",
    14055: "202500000079",
    14056: "202500000082",
    14057: "202500000079",
    14058: "202500000082",
    14059: "202500000084",
    14060: "202500000081",
    14061: "202500000081",
    14062: "202500000081",
    14063: "202500000083",
    14064: "202500000083",
    14065: "202500000080",
    14066: "202500000080",
    14067: "202500000080",
    14068: "202500000085",
    14069: "202500000086",
    14070: "202500000087",
    14234: "202500000077",
    14240: "202500000060",
    14970: "202500000062",
    15427: "202500000086",
    15428: "202500000087",

}

# --- Pobierz dane z Odoo ---
barcodes = list(product_map.values())
odoo_products = models.execute_kw(
    ODOO_DB, uid, ODOO_PASSWORD,
    'product.product', 'search_read',
    [[['barcode', 'in', barcodes]]],
    {'fields': ['barcode', 'qty_available']}
)

# Zamień na słownik: barcode -> qty
stock_by_barcode = {p['barcode']: p['qty_available'] for p in odoo_products}

# --- Synchronizuj z WooCommerce ---
for wc_id, barcode in product_map.items():
    qty = stock_by_barcode.get(barcode)
    if qty is not None:
        response = wcapi.put(f"products/{wc_id}", {
            "stock_quantity": int(qty),
            "manage_stock": True
        })
        print(f"✅ Zaktualizowano produkt {wc_id} (barcode: {barcode}) -> stock: {qty}")
    else:
        print(f"⚠️ Nie znaleziono produktu w Odoo z barcode: {barcode}")
