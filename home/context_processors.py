from decimal import Decimal, InvalidOperation
from .models import ProductPage, HomePage, PhotographyPage, IndexShopPage 

def global_pages(request):
    """
    Stellt sicher, dass die Links für Shop, Photography und About Me
    auf JEDER Seite verfügbar sind (auch auf manuellen Django-Views wie Contact).
    """
    try:
        # Wir holen die erste Live-Seite jedes Typs
        about_page = HomePage.objects.live().first()
        photography_page = PhotographyPage.objects.live().first()
        index_shop_page = IndexShopPage.objects.live().first()
    except Exception:
        # Fallback, falls Datenbank noch leer ist
        about_page = None
        photography_page = None
        index_shop_page = None

    return {
        'about_page': about_page,
        'photography_page': photography_page,
        # WICHTIG: Der Key muss 'shop_page' heißen, damit er zur base.html passt
        'shop_page': index_shop_page,
    }

def cart_context(request):
    """
    Berechnet den Warenkorb-Inhalt (Anzahl & Preis) für den Header auf allen Seiten.
    Verhindert Abstürze bei alten/kaputten Session-Daten.
    """
    cart_session = request.session.get('cart', {})
    
    total_price = Decimal(0)
    total_quantity = 0
    cart_items = []
    
    # 1. Filtere nur gültige Einträge (Schutz gegen 'int object is not subscriptable')
    valid_cart_items = {}
    for key, item in cart_session.items():
        if isinstance(item, dict) and 'product_id' in item and 'price' in item:
            valid_cart_items[key] = item
    
    # 2. Hole alle Produkte aus der Datenbank (optimiert: nur 1 Abfrage)
    product_ids = [item['product_id'] for item in valid_cart_items.values()]
    products = ProductPage.objects.filter(id__in=product_ids).specific()
    product_map = {str(p.id): p for p in products}

    # 3. Berechne Summen
    for cart_key, item_details in valid_cart_items.items():
        try:
            price_per_item = Decimal(item_details['price'])
            quantity = int(item_details['quantity'])
            
            total_price += price_per_item * quantity
            total_quantity += quantity

            product = product_map.get(str(item_details['product_id']))
            
            if product:
                cart_items.append({
                    'product': product,
                    'quantity': quantity,
                    'cart_key': cart_key,
                    'item_total': (price_per_item * quantity).quantize(Decimal('0.01')),
                    'price_per_item': price_per_item,
                    'size_name': item_details.get('size_name', ''),
                    'framed': item_details.get('framed', False)
                })

        except (InvalidOperation, TypeError, KeyError, ValueError):
            # Ignoriere kaputte Items statt abzustürzen
            continue

    return {
        'cart_items': cart_items,
        'cart_total_price': total_price,
        'cart_total_count': total_quantity, 
    }