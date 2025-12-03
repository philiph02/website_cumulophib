import json
import stripe
from django.shortcuts import redirect, render
from django.http import HttpResponseBadRequest, JsonResponse
from django.conf import settings 
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm

from .models import ProductPage, Order, OrderItem, PrintSizePrice, HomePage, IndexShopPage, PhotographyPage
from django.core.mail import send_mail

# --- Helper: Country Lists ---
def get_eu_countries():
    return ['BE', 'BG', 'CZ', 'DK', 'DE', 'EE', 'IE', 'GR', 'ES', 'FR', 'HR', 'IT', 'CY', 'LV', 'LT', 'LU', 'HU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SI', 'SK', 'FI', 'SE']

def get_europe_non_eu():
    return ['CH', 'GB', 'NO', 'IS', 'LI', 'AL', 'AD', 'BA', 'ME', 'MK', 'RS', 'TR']

def get_world_countries():
    return ['US', 'CA', 'AU', 'NZ', 'JP', 'SG', 'AE', 'QA', 'KR', 'CN', 'HK', 'IN']

def calculate_cart_shipping(cart_session, country_code):
    has_heavy_item = False
    for k, item in cart_session.items():
        if isinstance(item, dict):
            size = item.get('size_name', '')
            finish = item.get('finish', '')
            
            # Logic: If 60x40 (formerly A2) OR Shadow Gap Frame is selected -> Heavy shipping
            is_large = '60x40' in str(size).upper() or 'A2' in str(size).upper()
            is_framed = 'Shadow Gap' in str(finish)
            
            if is_large or is_framed:
                has_heavy_item = True
    
    price_cents = 2990
    label = "International Shipping"

    if country_code == 'AT':
        if has_heavy_item: price_cents = 0; label = "Free Shipping (Austria)"
        else: price_cents = 490; label = "Standard Shipping (Austria)"
    elif country_code in get_eu_countries():
        price_cents = 1690 if has_heavy_item else 1290
        label = "Standard Shipping (EU)"
    elif country_code in get_europe_non_eu():
        price_cents = 1990
        label = "Shipping (Europe Non-EU)"
        
    return price_cents, label

# --- MANUELLE VIEWS ---

def index_shop_view(request):
    shop_page = IndexShopPage.objects.live().first()
    products = ProductPage.objects.live().public().descendant_of(shop_page)
    cheapest = PrintSizePrice.objects.all().order_by('price_fine_art').first()
    cheapest_price = cheapest.price_fine_art if cheapest else 0
    
    context = {
        'page': shop_page,
        'grid_products': products,
        'cheapest_price': cheapest_price,
        'featured_slider_items': shop_page.featured_products.all() if shop_page else [],
    }
    return render(request, 'home/index_shop.html', context)

def home_view(request):
    about_page = HomePage.objects.live().first()
    return render(request, 'home/about.html', {'page': about_page})

def photography_view(request):
    photo_page = PhotographyPage.objects.live().first()
    return render(request, 'home/photography.html', {'page': photo_page})

def add_to_cart(request, product_id):
    try: product = ProductPage.objects.get(id=product_id)
    except: return HttpResponseBadRequest("Product not found")
    cart = request.session.get('cart', {})
    
    quantity = 1
    if request.method == 'POST':
        try: quantity = int(request.POST.get('quantity', 1))
        except: quantity = 1
            
    size_id = request.POST.get('size_variant')
    finish_type = request.POST.get('finish_variant', 'fine_art') 
    has_borders = (request.POST.get('add_borders', 'false') == 'true')
    
    size_name = "Standard"
    price_to_add = 0
    finish_name = "Fine Art Print"
    
    if size_id:
        try:
            v = PrintSizePrice.objects.get(id=size_id)
            size_name = v.size_name
            
            # --- USE ABSOLUTE PRICES ---
            if finish_type == 'alu_dibond':
                price_to_add = v.price_alu_dibond
                finish_name = "Alu-Composite Frameless"
            elif finish_type == 'shadow_gap':
                price_to_add = v.price_shadow_gap
                finish_name = "Alu-Composite + Shadow Gap Frame"
            else: # fine_art
                price_to_add = v.price_fine_art
                finish_name = "Fine Art Print"
                
        except: pass
    if price_to_add == 0:
        v = PrintSizePrice.objects.first()
        if v: price_to_add = v.price_fine_art

    cart_key = f"{product.id}_{size_id}_{finish_type}_{has_borders}"
    
    if cart_key in cart:
        cart[cart_key]['quantity'] += quantity
    else:
        cart[cart_key] = {
            'product_id': product.id, 
            'product_title': product.title, 
            'size_name': size_name, 
            'finish': finish_name,
            'framed': (finish_type == 'shadow_gap'),
            'has_borders': has_borders,
            'quantity': quantity, 
            'price': str(price_to_add)
        }
    
    request.session['cart'] = cart
    request.session.modified = True
    messages.success(request, f"Added {product.title} to cart")

    from urllib.parse import urlparse, urlunparse
    from django.http import QueryDict
    referer = request.META.get('HTTP_REFERER', '/')
    if referer:
        parsed = urlparse(referer)
        query = QueryDict(parsed.query, mutable=True)
        query['size'] = size_id
        query['finish'] = finish_type
        query['borders'] = 'true' if has_borders else 'false'
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query.urlencode(), parsed.fragment))
        return redirect(new_url)
        
    return redirect(referer)

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
    
    cart = request.session.get('cart', {})
    shipping_cents, label = calculate_cart_shipping(cart, country)
    
    product_total = 0
    for k, item in cart.items():
        if isinstance(item, dict): product_total += float(item['price']) * int(item['quantity'])
            
    total = product_total + (shipping_cents / 100)
    
    return JsonResponse({
        'shipping_cost': f"{shipping_cents/100:.2f}",
        'total': f"{total:.2f}",
        'label': label
    })

def checkout_page(request):
    cart_session = request.session.get('cart', {})
    if not cart_session: return redirect('/')

    country = request.session.get('shipping_country', 'AT')
    stripe_line_items = []
    for k, item in cart_session.items():
        if isinstance(item, dict):
            desc = f"{item['product_title']} ({item.get('size_name')}) - {item.get('finish')}"
            if item.get('has_borders'):
                desc += " [With Borders]"
                
            stripe_line_items.append({
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': desc},
                    'unit_amount': int(float(item['price']) * 100),
                },
                'quantity': int(item['quantity']),
            })

    shipping_cents, shipping_label = calculate_cart_shipping(cart_session, country)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            line_items=stripe_line_items,
            mode='payment',
            return_url=f"{request.scheme}://{request.get_host()}{reverse('checkout_success')}?session_id={{CHECKOUT_SESSION_ID}}",
            allow_promotion_codes=True,
            shipping_address_collection={'allowed_countries': [country]},
            shipping_options=[{
                'shipping_rate_data': {
                    'type': 'fixed_amount',
                    'fixed_amount': {'amount': shipping_cents, 'currency': 'eur'},
                    'display_name': shipping_label,
                }
            }]
        )
    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('/')

    return render(request, 'home/checkout.html', {
        'client_secret': session.client_secret,
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY
    })

def checkout_success(request):
    session_id = request.GET.get('session_id')
    if not session_id: return redirect('/')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        cust = session.customer_details
        ship = session.shipping_details or cust
        
        if Order.objects.filter(stripe_pid=session.payment_intent).exists():
            order = Order.objects.get(stripe_pid=session.payment_intent)
            return render(request, 'home/checkout_done.html', {'order': order})

        order = Order.objects.create(
            first_name=cust.name.split()[0] if cust.name else "Guest",
            last_name=" ".join(cust.name.split()[1:]) if cust.name else "",
            email=cust.email,
            address=f"{ship.address.line1}, {ship.address.city}",
            postal_code=ship.address.postal_code, city=ship.address.city, country=ship.address.country,
            stripe_pid=session.payment_intent, paid=True
        )
        cart = request.session.get('cart', {})
        real_ids = [k.split('_')[0] for k in cart.keys()]
        products = {str(p.id): p for p in ProductPage.objects.filter(id__in=real_ids)}
        
        for k, item in cart.items():
            if isinstance(item, dict) and str(item['product_id']) in products:
                OrderItem.objects.create(
                    order=order, 
                    product=products[str(item['product_id'])], 
                    price=item['price'], 
                    quantity=item['quantity'], 
                    size_name=item.get('size_name', ''), 
                    finish=item.get('finish', 'Fine Art Print'),
                    has_borders=item.get('has_borders', False),
                    framed=item.get('framed', False)
                )
        request.session['cart'] = {}
        return render(request, 'home/checkout_done.html', {'order': order})
    except Exception as e:
        return HttpResponseBadRequest(f"Error: {e}")

def login_view(request): return redirect('/')
def logout_view(request): return redirect('/')
def shipping_info_view(request): return render(request, 'home/footer/shipping.html')
def returns_view(request): return render(request, 'home/footer/returns.html')
def imprint_view(request): return render(request, 'home/footer/imprint.html')
def privacy_view(request): return render(request, 'home/footer/privacy.html')
def terms_view(request): return render(request, 'home/footer/terms.html')

def contact_view(request):
    if request.method == "POST":
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        sender_name = "Cumulophib"
        sender_email = settings.DEFAULT_FROM_EMAIL
        full_sender = f"{sender_name} <{sender_email}>"

        try:
            send_mail(
                subject=f"New Contact: {name}",
                message=f"New message received via website.\n\nName: {name}\nEmail: {email}\n\nMessage:\n{message}",
                from_email=full_sender,
                recipient_list=['hello@cumulophib.com'],
                fail_silently=False,
            )
            visitor_subject = "We received your message | Cumulophib"
            visitor_message = f"""Hi {name},\n\nThank you for reaching out to Cumulophib! \n\nI have received your message and will get back to you as soon as possible.\n\n--------------------------------------------------\nPhilip Heinrich\nCumulophib \nWebsite: https://www.cumulophib.com\nEmail: hello@cumulophib.com\n--------------------------------------------------"""
            send_mail(
                subject=visitor_subject,
                message=visitor_message,
                from_email=full_sender,
                recipient_list=[email],
                fail_silently=True,
            )
            messages.success(request, "Message sent successfully!")
            return redirect('contact')
        except Exception as e:
            messages.error(request, f"Error sending message: {str(e)}")
    return render(request, 'home/footer/contact.html')