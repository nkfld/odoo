#!/usr/bin/env python3
"""
Synchronizacja zamówień WooCommerce z Odoo
Sprawdza nowe zamówienia i zmniejsza stany magazynowe w Odoo
"""

import os
import json
import xmlrpc.client
import requests
from datetime import datetime, timedelta
import base64

class WooCommerceOdooSync:
    def __init__(self):
        # WooCommerce config
        self.wc_url = os.getenv('WC_URL')
        self.wc_consumer_key = os.getenv('WC_CONSUMER_KEY')
        self.wc_consumer_secret = os.getenv('WC_CONSUMER_SECRET')
        
        # Odoo config - sprawdź obie możliwe nazwy dla username
        self.odoo_url = os.getenv('ODOO_URL')
        self.odoo_db = os.getenv('ODOO_DB')
        self.odoo_username = os.getenv('ODOO_USERNAME') or os.getenv('ODOO_USER')  # Obsługa obu nazw
        self.odoo_password = os.getenv('ODOO_PASSWORD')
        
        # Bezpieczne parsowanie ODOO_LOCATION_ID
        location_id_str = os.getenv('ODOO_LOCATION_ID', '8').strip()
        if not location_id_str or location_id_str == '':
            self.odoo_location_id = 8  # Domyślna wartość
        else:
            try:
                self.odoo_location_id = int(location_id_str)
            except ValueError:
                print(f"⚠️ Nieprawidłowa wartość ODOO_LOCATION_ID: '{location_id_str}' - używam domyślnej wartości 8")
                self.odoo_location_id = 8
        
        # Wczytaj mapowanie produktów
        self.product_mapping = self.load_product_mapping()
        
        # Status tracking file
        self.status_file = 'last_sync_status.json'
        
        # Odoo connection
        self.odoo_uid = None
        self.odoo_models = None
        
        print("🚀 WooCommerce to Odoo Sync - uruchomiony")
        print(f"📅 Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🗂️ Załadowano mapowanie dla {len(self.product_mapping)} produktów")
    
    def load_product_mapping(self):
        """Wczytaj mapowanie produktów z pliku JSON"""
        try:
            if os.path.exists('product_mapping.json'):
                with open('product_mapping.json', 'r') as f:
                    mapping = json.load(f)
                print(f"✅ Wczytano mapowanie z pliku product_mapping.json")
                return mapping
            else:
                print("⚠️ Plik product_mapping.json nie istnieje - używam wbudowanego mapowania")
                # Fallback - wbudowane mapowanie
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
    
    def load_last_sync_status(self):
        """Wczytaj status ostatniej synchronizacji"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            return {'last_order_id': 0, 'processed_orders': []}
        except Exception as e:
            print(f"⚠️ Błąd wczytywania statusu: {e}")
            return {'last_order_id': 0, 'processed_orders': []}
    
    def save_sync_status(self, status):
        """Zapisz status synchronizacji"""
        try:
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            print(f"⚠️ Błąd zapisywania statusu: {e}")
    
    def connect_odoo(self):
        """Połącz z Odoo"""
        try:
            print("🔗 Łączenie z Odoo...")
            print(f"📍 URL: {self.odoo_url}")
            print(f"📊 DB: {self.odoo_db}")
            print(f"👤 User: {self.odoo_username}")
            
            # Sprawdź czy wszystkie dane są niepuste
            if not all([self.odoo_url, self.odoo_db, self.odoo_username, self.odoo_password]):
                missing = []
                if not self.odoo_url: missing.append('ODOO_URL')
                if not self.odoo_db: missing.append('ODOO_DB')
                if not self.odoo_username: missing.append('ODOO_USERNAME/ODOO_USER')
                if not self.odoo_password: missing.append('ODOO_PASSWORD')
                raise Exception(f"Puste zmienne Odoo: {missing}")
            
            # Utwórz połączenie z allow_none=True
            common = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/common',
                allow_none=True
            )
            
            # Sprawdź wersję Odoo (test połączenia)
            try:
                version_info = common.version()
                print(f"📋 Wersja Odoo: {version_info.get('server_version', 'nieznana')}")
            except Exception as e:
                print(f"⚠️ Nie można pobrać wersji Odoo: {e}")
                print(f"🔍 Sprawdź czy Odoo jest dostępny pod adresem: {self.odoo_url}")
                raise e
            
            # Uwierzytelnienie
            print("🔐 Próba uwierzytelnienia...")
            auth_result = common.authenticate(
                self.odoo_db, 
                self.odoo_username, 
                self.odoo_password, 
                {}
            )
            
            print(f"🔍 Wynik uwierzytelnienia: {auth_result}")
            
            if not auth_result:
                raise Exception("Błąd uwierzytelniania - sprawdź dane logowania (username/password)")
            
            self.odoo_uid = auth_result
            
            # Utwórz połączenie do modeli
            self.odoo_models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object',
                allow_none=True
            )
            
            print(f"✅ Połączono z Odoo (User ID: {self.odoo_uid})")
            return True
            
        except Exception as e:
            print(f"❌ Błąd połączenia z Odoo: {e}")
            print(f"🔍 Debug info:")
            print(f"   URL: {self.odoo_url}")
            print(f"   DB: {self.odoo_db}")
            print(f"   Username: {self.odoo_username}")
            print(f"   Password length: {len(self.odoo_password) if self.odoo_password else 0}")
            return False
    
    def get_woocommerce_orders(self, after_order_id=0):
        """Pobierz nowe zamówienia z WooCommerce"""
        try:
            print(f"📦 Pobieranie zamówień WooCommerce po ID: {after_order_id}")
            
            # Endpoint WooCommerce REST API
            url = f"{self.wc_url}/wp-json/wc/v3/orders"
            
            # Autoryzacja Basic Auth
            auth = base64.b64encode(
                f"{self.wc_consumer_key}:{self.wc_consumer_secret}".encode()
            ).decode()
            
            headers = {
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/json'
            }
            
            # Parametry - tylko zamówienia "processing" 
            params = {
                'status': 'processing',
                'per_page': 50,
                'orderby': 'id',
                'order': 'desc'  # Od najnowszych do najstarszych
            }
            
            # Jeśli mamy ostatnie ID, pobierz tylko nowsze
            if after_order_id > 0:
                params['after'] = after_order_id
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            orders = response.json()
            print(f"📋 Znaleziono {len(orders)} zamówień do przetworzenia")
            
            return orders
            
        except Exception as e:
            print(f"❌ Błąd pobierania zamówień WooCommerce: {e}")
            return []
    
    def get_barcode_for_product(self, wc_product_id, item_meta_data):
        """
        Pobierz kod kreskowy dla produktu WooCommerce
        TYLKO z mapowania - jeśli nie ma mapowania, zwróć None
        """
        wc_product_id_str = str(wc_product_id)
        
        # Sprawdź mapowanie
        if wc_product_id_str in self.product_mapping:
            barcode = self.product_mapping[wc_product_id_str]
            print(f"    📋 Użyto mapowania: WC ID {wc_product_id} → Odoo {barcode}")
            return barcode
        
        # BRAK MAPOWANIA = STOP
        print(f"    🛑 BRAK MAPOWANIA dla WC ID {wc_product_id} - POMIJAM PRODUKT")
        return None

    def find_product_in_odoo(self, barcode):
        """Znajdź produkt w Odoo po kodzie kreskowym"""
        try:
            products = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'product.product', 'search_read',
                [[['barcode', '=', str(barcode)]]],
                {'fields': ['id', 'name', 'barcode']}
            )
            
            return products[0] if products else None
            
        except Exception as e:
            print(f"❌ Błąd wyszukiwania produktu {barcode}: {e}")
            return None
        """Znajdź produkt w Odoo po kodzie kreskowym"""
        try:
            products = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'product.product', 'search_read',
                [[['barcode', '=', str(barcode)]]],
                {'fields': ['id', 'name', 'barcode']}
            )
            
            return products[0] if products else None
            
        except Exception as e:
            print(f"❌ Błąd wyszukiwania produktu {barcode}: {e}")
            return None
    
    def create_stock_move_out(self, product_id, quantity, order_number):
        """Utwórz wydanie magazynowe w Odoo"""
        try:
            # Pobierz lokalizację klienta
            customer_locations = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.location', 'search',
                [[['usage', '=', 'customer']]],
                {'limit': 1}
            )
            customer_location = customer_locations[0] if customer_locations else 9
            
            # Pobierz typ operacji wydania
            picking_types = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking.type', 'search',
                [[['code', '=', 'outgoing']]],
                {'limit': 1}
            )
            picking_type = picking_types[0] if picking_types else 1
            
            # Pobierz dane produktu
            product_info = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'product.product', 'read',
                [product_id],
                {'fields': ['uom_id', 'name']}
            )
            
            if not product_info:
                raise Exception('Nie znaleziono produktu')
            
            product_uom = product_info[0]['uom_id'][0] if product_info[0]['uom_id'] else 1
            product_name = product_info[0]['name']
            
            # Utwórz dokument magazynowy
            picking_vals = {
                'picking_type_id': picking_type,
                'location_id': self.odoo_location_id,
                'location_dest_id': customer_location,
                'origin': f'WooCommerce #{order_number} - GitHub Sync',
                'state': 'draft'
            }
            
            picking_id = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking', 'create',
                [picking_vals]
            )
            
            # Utwórz linię ruchu
            move_vals = {
                'name': f'WooCommerce wydanie: {product_name}',
                'product_id': product_id,
                'product_uom_qty': quantity,
                'product_uom': product_uom,
                'picking_id': picking_id,
                'location_id': self.odoo_location_id,
                'location_dest_id': customer_location,
                'state': 'draft'
            }
            
            move_id = self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.move', 'create',
                [move_vals]
            )
            
            # Potwierdź i zrealizuj
            self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.picking', 'action_confirm',
                [[picking_id]]
            )
            
            self.odoo_models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_password,
                'stock.move', 'write',
                [[move_id], {'state': 'assigned'}]
            )
            
            try:
                self.odoo_models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_password,
                    'stock.move', '_action_done',
                    [[move_id]]
                )
            except:
                # Fallback
                self.odoo_models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_password,
                    'stock.picking', 'write',
                    [[picking_id], {'state': 'done'}]
                )
                self.odoo_models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_password,
                    'stock.move', 'write',
                    [[move_id], {'state': 'done'}]
                )
            
            return picking_id
            
        except Exception as e:
            print(f"❌ Błąd tworzenia dokumentu magazynowego: {e}")
            raise e
    
    def process_order(self, order):
        """Przetwórz pojedyncze zamówienie"""
        order_id = order['id']
        order_number = order['number']
        order_status = order['status']
        
        print(f"\n📋 Przetwarzanie zamówienia #{order_number} (ID: {order_id}, Status: {order_status})")
        
        results = []
        
        for item in order['line_items']:
            # Używaj tylko product_id
            product_id = item.get('product_id', 0)
            quantity = item['quantity']
            product_name = item['name']
            
            print(f"  🛍️ Produkt: {product_name} (WC ID: {product_id}, ilość: {quantity})")
            
            # Jeśli ID = 0, pomiń produkt
            if product_id == 0:
                result = {
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': 0,
                    'barcode': 'BRAK_ID',
                    'error': f'Product ID = 0 - prawdopodobnie usunięty produkt',
                    'skipped': True
                }
                results.append(result)
                continue
            
            # Pobierz kod kreskowy używając mapowania
            barcode = self.get_barcode_for_product(product_id, item.get('meta_data', []))
            
            # Jeśli brak mapowania - POMIŃ PRODUKT
            if barcode is None:
                result = {
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': product_id,
                    'barcode': 'BRAK_MAPOWANIA',
                    'error': f'Brak mapowania dla WC ID {product_id} - POMIJAM',
                    'skipped': True
                }
                results.append(result)
                continue
            
            # Znajdź produkt w Odoo
            odoo_product = self.find_product_in_odoo(barcode)
            
            if odoo_product:
                try:
                    picking_id = self.create_stock_move_out(
                        odoo_product['id'], 
                        quantity, 
                        order_number
                    )
                    
                    result = {
                        'success': True,
                        'product_name': odoo_product['name'],
                        'wc_product_id': product_id,
                        'barcode': barcode,
                        'quantity': quantity,
                        'picking_id': picking_id
                    }
                    
                    print(f"    ✅ Utworzono dokument wydania #{picking_id}")
                    
                except Exception as e:
                    result = {
                        'success': False,
                        'product_name': product_name,
                        'wc_product_id': product_id,
                        'barcode': barcode,
                        'error': str(e)
                    }
                    print(f"    ❌ Błąd: {e}")
            else:
                result = {
                    'success': False,
                    'product_name': product_name,
                    'wc_product_id': product_id,
                    'barcode': barcode,
                    'error': 'Produkt nie znaleziony w Odoo'
                }
                print(f"    ⚠️ Produkt nie znaleziony w Odoo (kod: {barcode})")
            
            results.append(result)
        
        return results
    
    def add_order_note(self, order_id, note):
        """Dodaj notatkę do zamówienia WooCommerce"""
        try:
            url = f"{self.wc_url}/wp-json/wc/v3/orders/{order_id}/notes"
            
            auth = base64.b64encode(
                f"{self.wc_consumer_key}:{self.wc_consumer_secret}".encode()
            ).decode()
            
            headers = {
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'note': note,
                'customer_note': False
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=15)
            response.raise_for_status()
            
        except Exception as e:
            print(f"⚠️ Nie udało się dodać notatki do zamówienia: {e}")
    
    def run(self):
        """Główna funkcja synchronizacji"""
        try:
            # UWAGA: Usuń plik statusu żeby zacząć od nowa
            if os.path.exists(self.status_file):
                os.remove(self.status_file)
                print("🔄 Resetowanie statusu - zaczynam od najnowszych zamówień")
            
            # Wczytaj ostatni status
            status = self.load_last_sync_status()
            last_order_id = 0  # Zacznij od początku
            processed_orders = []  # Pusta lista
            
            print(f"📊 Sprawdzam najnowsze zamówienia processing")
            
            # Połącz z Odoo
            if not self.connect_odoo():
                return False
            
            # Pobierz nowe zamówienia
            orders = self.get_woocommerce_orders(last_order_id)
            
            if not orders:
                print("✅ Brak nowych zamówień do przetworzenia")
                return True
            
            # Przetwórz każde zamówienie
            new_last_order_id = last_order_id
            total_processed = 0
            
            for order in orders:
                order_id = order['id']
                order_status = order['status']
                
                print(f"\n📦 Sprawdzam zamówienie #{order['number']} (ID: {order_id}, Status: {order_status})")
                
                # SPRAWDŹ STATUS - tylko processing
                if order_status != 'processing':
                    print(f"⏭️ Pomijam - status '{order_status}' (oczekuję 'processing')")
                    continue
                
                # Pomiń już przetworzone zamówienia
                if order_id in processed_orders:
                    print(f"⏭️ Zamówienie #{order['number']} już przetworzone")
                    continue
                
                # Przetwórz zamówienie
                results = self.process_order(order)
                
                # Przygotuj notatkę
                note_lines = [f"🤖 GitHub Actions - Odoo Sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
                
                for result in results:
                    if result.get('skipped'):
                        note_lines.append(f"⏭️ {result['product_name']}: POMINIĘTO - brak mapowania (WC ID: {result['wc_product_id']})")
                    elif result['success']:
                        note_lines.append(f"✅ {result['product_name']}: -{result['quantity']} szt. (WC:{result['wc_product_id']} → {result['barcode']}, Dok: #{result['picking_id']})")
                    else:
                        note_lines.append(f"❌ {result['product_name']}: {result['error']} (WC:{result['wc_product_id']} → {result['barcode']})")
                
                note = "\n".join(note_lines)
                
                # Dodaj notatkę do zamówienia
                self.add_order_note(order_id, note)
                
                # Aktualizuj status
                processed_orders.append(order_id)
                new_last_order_id = max(new_last_order_id, order_id)
                total_processed += 1
                
                print(f"✅ Zamówienie #{order['number']} przetworzone")
            
            # Zapisz nowy status
            new_status = {
                'last_order_id': new_last_order_id,
                'processed_orders': processed_orders[-100:],  # Zachowaj ostatnie 100
                'last_sync': datetime.now().isoformat()
            }
            
            self.save_sync_status(new_status)
            
            print(f"\n🎉 Synchronizacja zakończona!")
            print(f"📈 Przetworzone zamówienia: {total_processed}")
            print(f"📊 Nowe ostatnie ID: {new_last_order_id}")
            
            return True
            
        except Exception as e:
            print(f"💥 Błąd synchronizacji: {e}")
            return False

if __name__ == "__main__":
    sync = WooCommerceOdooSync()
    success = sync.run()
    exit(0 if success else 1)