import json
import stripe
from django.shortcuts import redirect, render
from django.http import HttpResponseBadRequest, JsonResponse
from django.conf import settings 
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, logout
from .models import ProductPage, Order, OrderItem, PrintSizePrice, HomePage, IndexShopPage, PhotographyPage
from django.core.mail import send_mail

def get_eu_countries(): return ['BE', 'BG', 'CZ', 'DK', 'DE', 'EE', 'IE', 'GR', 'ES', 'FR', 'HR', 'IT', 'CY', 'LV', 'LT', 'LU', 'HU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SI', 'SK', 'FI', 'SE']
def get_europe_non_eu(): return ['CH', 'GB', 'NO', 'IS', 'LI', 'AL', 'AD', 'BA', 'ME', 'MK', 'RS', 'TR']

def calculate_cart_shipping(cart_session, country_code):
    has_heavy_item = False
    for k, item in cart_session.items():
        if isinstance(item, dict):
            size = item.get('size_name', '')
            finish = item.get('finish', '')
            is_large = '60x40' in str(size).upper() or 'A2' in str(size).upper()
            is_framed = 'Shadow Gap' in str(finish)
            if is_large or is_framed: has_heavy_item = True
    price_cents = 2990
    label = "International Shipping"
    if country_code == 'AT':
        price_cents = 0 if has_heavy_item else 490
        label = "Free Shipping (Austria)" if has_heavy_item else "Standard Shipping (Austria)"
    elif country_code in get_eu_countries():
        price_cents = 1690 if has_heavy_item else 1290
        label = "Standard Shipping (EU)"
    elif country_code in get_europe_non_eu():
        price_cents = 1990
        label = "Shipping (Europe Non-EU)"
    return price_cents, label

def index_shop_view(request):
    shop_page = IndexShopPage.objects.live().first()
    products = ProductPage.objects.live().public().descendant_of(shop_page)
    cheapest = PrintSizePrice.objects.all().order_by('price_fine_art').first()
    cheapest_price = cheapest.price_fine_art if cheapest else 0
    context = {'page': shop_page, 'grid_products': products, 'cheapest_price': cheapest_price, 'featured_slider_items': shop_page.featured_products.all() if shop_page else []}
    return render(request, 'home/index_shop.html', context)

def home_view(request): return render(request, 'home/about.html', {'page': HomePage.objects.live().first()})
def photography_view(request): return render(request, 'home/photography.html', {'page': PhotographyPage.objects.live().first()})

def add_to_cart(request, product_id):
    try: product = ProductPage.objects.get(id=product_id)
    except: return HttpResponseBadRequest("Product not found")
    cart = request.session.get('cart', {})
    
    quantity = int(request.POST.get('quantity', 1))
    size_id = request.POST.get('size_variant')
    finish_type = request.POST.get('finish_variant', 'fine_art') 
    has_borders = (request.POST.get('add_borders', 'false') == 'true')
    frame_color = request.POST.get('frame_color', '')

    if finish_type != 'shadow_gap': frame_color = ''
    elif not frame_color: frame_color = 'White'

    size_name = "Standard"
    price_to_add = 0
    finish_name = "Fine Art Print"
    
    if size_id:
        try:
            v = PrintSizePrice.objects.get(id=size_id)
            size_name = v.size_name
            if finish_type == 'alu_dibond': 
                price_to_add = v.price_alu_dibond
                finish_name = "Alu-Dibond Frameless"
            elif finish_type == 'shadow_gap': 
                price_to_add = v.price_shadow_gap
                finish_name = "Alu-Dibond + Shadow Gap Frame"
            else: 
                price_to_add = v.price_fine_art
                finish_name = "Fine Art Print"
        except: pass
    
    if price_to_add == 0:
        v = PrintSizePrice.objects.first()
        if v: price_to_add = v.price_fine_art

    cart_key = f"{product.id}_{size_id}_{finish_type}_{has_borders}_{frame_color}"
    if cart_key in cart: cart[cart_key]['quantity'] += quantity
    else:
        cart[cart_key] = {
            'product_id': product.id, 'product_title': product.title, 'size_name': size_name, 
            'finish': finish_name, 'framed': (finish_type == 'shadow_gap'), 'has_borders': has_borders, 
            'frame_color': frame_color, 'quantity': quantity, 'price': str(price_to_add)
        }
    request.session['cart'] = cart
    request.session.modified = True
    messages.success(request, f"Added {product.title} to cart")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def remove_one_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    if product_id in cart: del cart[product_id]
    request.session['cart'] = cart
    request.session.modified = True
    return redirect(request.META.get('HTTP_REFERER', '/'))

@csrf_exempt
def update_cart_shipping(request):
    if request.method != 'POST': return JsonResponse({'error': 'POST required'}, status=400)
    data = json.loads(request.body)
    country = data.get('country')
    request.session['shipping_country'] = country
    request.session.modified = True
    shipping_cents, label = calculate_cart_shipping(request.session.get('cart', {}), country)
    product_total = sum(float(item['price']) * int(item['quantity']) for k, item in request.session.get('cart', {}).items() if isinstance(item, dict))
    return JsonResponse({'shipping_cost': f"{shipping_cents/100:.2f}", 'total': f"{product_total + (shipping_cents / 100):.2f}", 'label': label})

def checkout_page(request):
    cart = request.session.get('cart', {})
    if not cart: return redirect('/')
    country = request.session.get('shipping_country', 'AT')
    items = []
    for k, item in cart.items():
        if isinstance(item, dict):
            desc = f"{item['product_title']} ({item.get('size_name')}) - {item.get('finish')}"
            if item.get('frame_color'): desc += f" [{item.get('frame_color')}]"
            if item.get('has_borders'): desc += " [With Borders]"
            items.append({'price_data': {'currency': 'eur', 'product_data': {'name': desc}, 'unit_amount': int(float(item['price']) * 100)}, 'quantity': int(item['quantity'])})
    shipping_cents, label = calculate_cart_shipping(cart, country)
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            ui_mode='embedded', line_items=items, mode='payment',
            return_url=f"{request.scheme}://{request.get_host()}{reverse('checkout_success')}?session_id={{CHECKOUT_SESSION_ID}}",
            allow_promotion_codes=True, shipping_address_collection={'allowed_countries': [country]},
            shipping_options=[{'shipping_rate_data': {'type': 'fixed_amount', 'fixed_amount': {'amount': shipping_cents, 'currency': 'eur'}, 'display_name': label}}]
        )
    except Exception as e: messages.error(request, f"Error: {e}"); return redirect('/')
    return render(request, 'home/checkout.html', {'client_secret': session.client_secret, 'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY})

def checkout_success(request):
    if not request.GET.get('session_id'): return redirect('/')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(request.GET.get('session_id'))
        cust, ship = session.customer_details, session.shipping_details or session.customer_details
        if Order.objects.filter(stripe_pid=session.payment_intent).exists(): return render(request, 'home/checkout_done.html', {'order': Order.objects.get(stripe_pid=session.payment_intent)})
        order = Order.objects.create(first_name=cust.name.split()[0] if cust.name else "Guest", last_name=" ".join(cust.name.split()[1:]) if cust.name else "", email=cust.email, address=f"{ship.address.line1}, {ship.address.city}", postal_code=ship.address.postal_code, city=ship.address.city, country=ship.address.country, stripe_pid=session.payment_intent, paid=True)
        cart = request.session.get('cart', {})
        products = {str(p.id): p for p in ProductPage.objects.filter(id__in=[k.split('_')[0] for k in cart.keys()])}
        for k, item in cart.items():
            if isinstance(item, dict) and str(item['product_id']) in products:
                OrderItem.objects.create(order=order, product=products[str(item['product_id'])], price=item['price'], quantity=item['quantity'], size_name=item.get('size_name', ''), finish=item.get('finish', ''), has_borders=item.get('has_borders', False), framed=item.get('framed', False), frame_color=item.get('frame_color', ''))
        request.session['cart'] = {}
        return render(request, 'home/checkout_done.html', {'order': order})
    except Exception as e: return HttpResponseBadRequest(f"Error: {e}")

# --- Footer & Auth ---
def login_view(r): return redirect('/')
def logout_view(r): return redirect('/')
def shipping_info_view(r): return render(r, 'home/footer/shipping.html')
def returns_view(r): return render(r, 'home/footer/returns.html')
def imprint_view(r): return render(r, 'home/footer/imprint.html')
def privacy_view(r): return render(r, 'home/footer/privacy.html')
def terms_view(r): return render(r, 'home/footer/terms.html')
def contact_view(r):
    if r.method == "POST":
        try:
            send_mail(f"Contact: {r.POST.get('name')}", r.POST.get('message'), settings.DEFAULT_FROM_EMAIL, ['hello@cumulophib.com'])
            messages.success(r, "Sent!")
        except: messages.error(r, "Error sending.")
        return redirect('contact')
    return render(r, 'home/footer/contact.html')