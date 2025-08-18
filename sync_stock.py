#!/usr/bin/env python3
"""
Synchronizacja zamówień WooCommerce z Odoo
Sprawdza zamówienia w statusie 'processing' i tworzy wydania magazynowe w Odoo.
"""

import os
import json
import xmlrpc.client
import requests
from datetime import datetime
import base64


class WooCommerceOdooSync:
    def __init__(self):
        # WooCommerce config (z ENV)
        self.wc_url = os.getenv('WC_URL')
        self.wc_consumer_key = os.getenv('WC_CONSUMER_KEY')
        self.wc_consumer_secret = os.getenv('WC_CONSUMER_SECRET')

        # Odoo config (z ENV)
        self.odoo_url = os.getenv('ODOO_URL')
        self.odoo_db = os.getenv('ODOO_DB')
        self.odoo_username = os.getenv('ODOO_USERNAME') or os.getenv('ODOO_USER')
        self.odoo_password = os.getenv('ODOO_PASSWORD')

        # Lokalizacja źródłowa (magazyn) — bezpieczne parsowanie
        location_id_str = (os.getenv('ODOO_LOCATION_ID', '8') or '8').strip()
        try:
            self.odoo_location_id = int(location_id_str)
        except ValueError:
            print(f"⚠️ Nieprawidłowa wartość ODOO_LOCATION_ID: '{location_id_str}' - używam domyślnej 8")
            self.odoo_location_id = 8

        # Wczytaj mapowanie produktów (WC variation_id/product_id -> Odoo barcode)
        self.product_mapping = self.load_product_mapping()

        # Status (jeśli chcesz trzymać historię – aktualnie resetujemy na starcie run())
        self.status_file = 'last_sync_status.json'

        # Odoo connection
        self.odoo_uid = None
        self.odoo_models = None

        print("🚀 WooCommerce → Odoo Sync uruchomiony")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🗂️ Załadowano mapowanie dla {len(self.product_mapping)} pozycji")

    # -------------------- MAPOWANIE --------------------
    def load_product_mapping(self):
        """Wczytaj mapowanie z pliku product-mapping.json (WC ID -> Odoo barcode)."""
        try:
            path = 'product-mapping.json'  # <= NAZWA Z MYŚLNIKIEM
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                print("✅ Wczytano mapowanie z pliku product-mapping.json")
                return mapping
            else:
                print("⚠️ Brak product-mapping.json – używam wbudowanego, przykładowego mapowania")
                # Fallback – wstaw tu własne ID wariantów/produktów → barcode
                return {
                    '13782': '202500000059',
                    '13783': '202500000053',
                    '13787': '202500000059',
                    '13825': '202500000059',
                    '13785': '202500000055',
                    '13788': '202500000059',
                    '13806': '202500000065',
                    '13807': '202500000068',
                    '13808': '202500000078',
                    '13809': '202500000067',
                    '13810': '202500000055',
                    '13811': '202500000052',
                    '13812': '202500000073',
                    '13813': '202500000066',
                    '13815': '202500000069',
                    '13816': '202500000070',
                    '13817': '202500000061',
                    '13818': '202500000062',
                    '13820': '202500000058',
                    '13835': '202500000061',
                    '13836': '202500000062',
                    '13849': '202500000063',
                    '14050': '202500000081',
                    '14051': '202500000082',
                    '14052': '202500000079',
                    '14053': '202500000079',
                    '14054': '202500000082',
                    '14055': '202500000079',
                    '14056': '202500000082',
                    '14057': '202500000079',
                    '14058': '202500000082',
                    '14059': '202500000084',
                    '14060': '202500000081',
                    '14061': '202500000081',
                    '14062': '202500000081',
                    '14063': '202500000083',
                    '14064': '202500000083',
                    '14065': '202500000080',
                    '14066': '202500000080',
                    '14067': '202500000080',
                    '14068': '202500000085',
                    '14069': '202500000086',
                    '14070': '202500000087',
                    '14234': '202500000077',
                    '14240': '202500000060',
                    '15427': '202500000086',
                    '15428': '202500000087',
                    '16085': '202500000061',
                    '16086': '202500000062'
                }
        except Exception as e:
            print(f"❌ Błąd wczytywania mapowania: {e}")
            return {}

    # -------------------- ODOO --------------------
    def connect_odoo(self):
        """Połącz z Odoo (XML-RPC)."""
        try:
            print("🔗 Łączenie z Odoo…")
            print(f"📍 URL: {self.odoo_url}")
            print(f"📊 DB: {self.odoo_db}")
            print(f"👤 User: {self.odoo_username}")

            # Walidacja danych
            missing = []
            if not self.odoo_url: missing.append('ODOO_URL')
            if not self.odoo_db: missing.append('ODOO_DB')
            if not self.odoo_username: missing.append('ODOO_USERNAME/ODOO_USER')
            if not self.odoo_password: missing.append('ODOO_PASSWORD')
            if missing:
                raise Exception(f"Puste zmienne Odoo: {missing}")

            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common', allow_none=True)
            try:
                version_info = common.version()
                print(f"📋 Wersja Odoo: {version_info.get('server_version', 'nieznana')}")
            except Exception as e:
                print(f"⚠️ Nie można pobrać wersji Odoo: {e}")
                raise

            print("🔐 Próba uwierzytelnienia…")
            uid = common.authenticate(self.odoo_db, self.odoo_username, self.odoo_password, {})
            print(f"🔍 Wynik uwierzytelnienia: {uid}")
            if not uid:
                raise Exception("Błędne dane logowania do Odoo")

            self.odoo_uid = uid
            self.odoo_models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)
            print(f"✅ Połączono z Odoo (User ID: {self.odoo_uid})")
            return True

        except Exception as e:
            print(f"❌ Błąd połączenia z Odoo: {e}")
            print("🔍 Debug info:")
            print(f"   URL: {self.odoo_url}")
            print(f"   DB: {self.odoo_db}")
            print(f"   Username: {self.odoo_username}")
            print(f"   Password length: {len(self.odoo_password) if self.odoo_password else 0}")
            return False

    def get_customer_location(self):
        """ID lokalizacji klienta (usage = 'customer')."""
        try:
            locations = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.location', 'search',
                [[['usage', '=', 'customer']]],
                {'limit': 1}
            )
            return locations[0] if locations else 9
        except Exception:
            return 9

    def get_picking_type(self, operation_type):
        """Pobiera typ operacji magazynowej ('incoming' lub 'outgoing')."""
        try:
            picking_types = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking.type', 'search',
                [[['code', '=', operation_type]]],
                {'limit': 1}
            )
            return picking_types[0] if picking_types else 1
        except Exception:
            return 1

    def find_product_in_odoo(self, barcode):
        """Znajdź produkt w Odoo po kodzie kreskowym."""
        try:
            products = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'product.product', 'search_read',
                [[['barcode', '=', str(barcode)]]],
                {'fields': ['id', 'name', 'barcode'], 'limit': 1}
            )
            return products[0] if products else None
        except Exception as e:
            print(f"❌ Błąd wyszukiwania produktu {barcode}: {e}")
            return None

    def create_stock_move_out(self, product_id, quantity, order_number):
        """
        Wydanie towaru w Odoo 17.
        Ustawiamy wykonaną ilość na stock.move.line poprzez pole 'quantity'.
        """
        try:
            print(f"    🔄 Tworzenie wydania dla produktu {product_id}, ilość: {quantity}")

            source_location = self.odoo_location_id
            dest_location = self.get_customer_location()
            picking_type = self.get_picking_type('outgoing')

            print(f"    📍 Source: {source_location}, Dest: {dest_location}, Type: {picking_type}")

            # 1) Picking
            picking_vals = {
                'picking_type_id': picking_type,
                'location_id': source_location,
                'location_dest_id': dest_location,
                'origin': f'WooCommerce #{order_number} - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'state': 'draft',
            }
            picking_id = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking', 'create', [picking_vals]
            )
            print(f"    ✅ Utworzono picking ID: {picking_id}")

            # 2) Move
            move_vals = {
                'name': 'WooCommerce wydanie',
                'product_id': product_id,
                'product_uom_qty': quantity,
                'product_uom': 1,  # załóżmy, że to odpowiednia UoM
                'picking_id': picking_id,
                'location_id': source_location,
                'location_dest_id': dest_location,
                'state': 'draft',
            }
            move_id = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.move', 'create', [move_vals]
            )
            print(f"    ✅ Utworzono move ID: {move_id}")

            # 3) Confirm
            self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking', 'action_confirm', [picking_id]
            )
            print("    ✅ Picking potwierdzony")

            # 4) Ustaw wykonane ilości na move line (Odoo 17 -> pole 'quantity')
            move_lines = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.move.line', 'search_read',
                [[['move_id', '=', move_id]]],
                {'fields': ['id', 'product_id']}
            )

            if move_lines:
                for line in move_lines:
                    self.odoo_models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_password,
                        'stock.move.line', 'write',
                        [line['id'], {'quantity': quantity}]
                    )
                    print(f"    ✅ Ustawiono quantity={quantity} na move_line #{line['id']}")
            else:
                print("    🔄 Brak move_lines – tworzę ręcznie")
                move_line_vals = {
                    'move_id': move_id,
                    'picking_id': picking_id,
                    'product_id': product_id,
                    'location_id': source_location,
                    'location_dest_id': dest_location,
                    'quantity': quantity,
                    'product_uom_id': 1,
                }
                move_line_id = self.odoo_models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_password,
                    'stock.move.line', 'create', [move_line_vals]
                )
                print(f"    ✅ Utworzono move_line #{move_line_id} z quantity={quantity}")

            # 5) Walidacja
            print("    🔄 Walidacja pickingu…")
            self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking', 'button_validate', [picking_id]
            )
            print(f"    ✅ Picking zwalidowany! ID: {picking_id}")
            return picking_id

        except Exception as e:
            print("    ❌ BŁĄD w create_stock_move_out:")
            print(f"    ❌ Typ błędu: {type(e)}")
            print(f"    ❌ Komunikat: {str(e)}")
            if hasattr(e, 'faultString'):
                print(f"    ❌ XML-RPC Fault: {e.faultString}")
            raise

    # -------------------- WOO --------------------
    def get_woocommerce_orders(self, _after_order_id=0):
        """
        Pobierz zamówienia WooCommerce w statusie 'processing'.
        (Bez filtra 'after' po ID – to pole oczekuje daty, nie liczby).
        """
        try:
            print("📦 Pobieranie zamówień WooCommerce…")

            url = f"{self.wc_url}/wp-json/wc/v3/orders"
            auth = base64.b64encode(f"{self.wc_consumer_key}:{self.wc_consumer_secret}".encode()).decode()
            headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}

            params = {
                'status': 'processing',
                'per_page': 50,
                'orderby': 'id',
                'order': 'desc'
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            orders = response.json()
            print(f"📋 Znaleziono {len(orders)} zamówień do przetworzenia")
            return orders

        except Exception as e:
            print(f"❌ Błąd pobierania zamówień WooCommerce: {e}")
            return []

    def get_barcode_for_wc_key(self, wc_key, _item_meta_data=None):
        """
        Zwróć barcode z mapowania dla klucza WC (variation_id albo product_id).
        """
        key = str(wc_key)
        if key in self.product_mapping:
            barcode = self.product_mapping[key]
            print(f"    📋 Mapowanie: WC ID {wc_key} → Odoo {barcode}")
            return barcode
        print(f"    🛑 BRAK MAPOWANIA dla WC ID {wc_key} – pomijam")
        return None

    # -------------------- PRZETWARZANIE --------------------
    def process_order(self, order):
        """Przetwórz pojedyncze zamówienie."""
        order_id = order['id']
        order_number = order['number']
        order_status = order['status']

        print(f"\n📋 Przetwarzanie zamówienia #{order_number} (ID: {order_id}, Status: {order_status})")

        results = []

        for item in order['line_items']:
            # Klucze z Woo
            prod_id = item.get('product_id', 0)
            var_id = item.get('variation_id') or 0
            wc_key = var_id or prod_id  # preferuj variation_id

            quantity = item.get('quantity', 0)
            product_name = item.get('name', '')

            print(
                f"  🛍️ Produkt: {product_name} "
                f"(WC KEY: {wc_key}, product_id={prod_id}, variation_id={var_id}, ilość: {quantity})"
            )

            if wc_key == 0 or quantity <= 0:
                result = {
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': wc_key,
                    'barcode': 'BRAK_ID_LUB_QTY',
                    'error': 'Brak ID lub ilość <= 0',
                    'skipped': True
                }
                results.append(result)
                continue

            # Mapowanie WC -> Odoo barcode
            barcode = self.get_barcode_for_wc_key(wc_key, item.get('meta_data', []))
            if barcode is None:
                results.append({
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': wc_key,
                    'barcode': 'BRAK_MAPOWANIA',
                    'error': f'Brak mapowania dla WC ID {wc_key}',
                    'skipped': True
                })
                continue

            # Znajdź produkt w Odoo
            odoo_product = self.find_product_in_odoo(barcode)
            if not odoo_product:
                results.append({
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': wc_key,
                    'barcode': barcode,
                    'error': 'Produkt nie znaleziony w Odoo'
                })
                print(f"    ⚠️ Produkt nie znaleziony w Odoo (barcode: {barcode})")
                continue

            # Utwórz wydanie
            try:
                picking_id = self.create_stock_move_out(odoo_product['id'], quantity, order_number)
                results.append({
                    'success': True,
                    'product_name': odoo_product['name'],
                    'wc_product_id': wc_key,
                    'barcode': barcode,
                    'quantity': quantity,
                    'picking_id': picking_id
                })
                print(f"    ✅ Utworzono dokument wydania #{picking_id}")
            except Exception as e:
                results.append({
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': wc_key,
                    'barcode': barcode,
                    'error': str(e)
                })
                print(f"    ❌ Błąd: {e}")

        return results

    def add_order_note(self, order_id, note):
        """Dodaj notatkę do zamówienia WooCommerce."""
        try:
            url = f"{self.wc_url}/wp-json/wc/v3/orders/{order_id}/notes"
            auth = base64.b64encode(f"{self.wc_consumer_key}:{self.wc_consumer_secret}".encode()).decode()
            headers = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'}
            data = {'note': note, 'customer_note': False}
            response = requests.post(url, headers=headers, json=data, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"⚠️ Nie udało się dodać notatki do zamówienia: {e}")

    # -------------------- RUN --------------------
    def run(self):
        """Główna pętla synchronizacji."""
        try:
            # (Opcjonalnie) Reset statusu – zaczynamy od bieżącego zestawu zamówień
            if os.path.exists(self.status_file):
                os.remove(self.status_file)
                print("🔄 Reset statusu – start od najnowszych zamówień")

            print("📊 Sprawdzam zamówienia w statusie 'processing'")

            if not self.connect_odoo():
                return False

            orders = self.get_woocommerce_orders()
            if not orders:
                print("✅ Brak zamówień do przetworzenia")
                return True

            total_processed = 0
            processed_orders = []

            for order in orders:
                order_id = order['id']
                order_status = order.get('status')

                print(f"\n📦 Sprawdzam zamówienie #{order.get('number')} (ID: {order_id}, Status: {order_status})")

                if order_status != 'processing':
                    print(f"⏭️ Pomijam – status '{order_status}' (oczekuję 'processing')")
                    continue

                if order_id in processed_orders:
                    print(f"⏭️ Zamówienie #{order.get('number')} już przetworzone")
                    continue

                # Przetwórz pozycje
                results = self.process_order(order)

                # Notatka do zamówienia
                note_lines = [f"🤖 Odoo Sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
                for r in results:
                    if r.get('skipped'):
                        note_lines.append(f"⏭️ {r['product_name']}: POMINIĘTO – {r['error']}")
                    elif r['success']:
                        note_lines.append(
                            f"✅ {r['product_name']}: -{r['quantity']} szt. "
                            f"(WC:{r['wc_product_id']} → {r['barcode']}, Dok: #{r['picking_id']})"
                        )
                    else:
                        note_lines.append(
                            f"❌ {r['product_name']}: {r['error']} "
                            f"(WC:{r['wc_product_id']} → {r['barcode']})"
                        )
                note = "\n".join(note_lines)
                self.add_order_note(order_id, note)

                processed_orders.append(order_id)
                total_processed += 1
                print(f"✅ Zamówienie #{order.get('number')} przetworzone")

            # Zapisz prosty status (ostatnie 100)
            new_status = {
                'last_order_id': max(processed_orders) if processed_orders else 0,
                'processed_orders': processed_orders[-100:],
                'last_sync': datetime.now().isoformat()
            }
            try:
                with open(self.status_file, 'w', encoding='utf-8') as f:
                    json.dump(new_status, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Błąd zapisu statusu: {e}")

            print("\n🎉 Synchronizacja zakończona")
            print(f"📈 Przetworzone zamówienia: {total_processed}")
            print(f"📊 Nowe ostatnie ID: {new_status['last_order_id']}")
            return True

        except Exception as e:
            print(f"💥 Błąd synchronizacji: {e}")
            return False


if __name__ == "__main__":
    sync = WooCommerceOdooSync()
    success = sync.run()
    exit(0 if success else 1)
