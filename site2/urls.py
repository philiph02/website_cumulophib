from django.conf import settings
from django.urls import include, path
from django.contrib import admin
from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls
from search import views as search_views
from home import views as home_views 

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("search/", search_views.search, name="search"),
    
    # Cart & API
    path("cart/add/<int:product_id>/", home_views.add_to_cart, name="add_to_cart"),
    path("cart/remove_one/<str:product_id>/", home_views.remove_one_from_cart, name="remove_one_from_cart"),
    path("api/update-cart-shipping/", home_views.update_cart_shipping, name="update_cart_shipping"),

    # Checkout
    path("checkout/", home_views.checkout_page, name="checkout"),
    path("checkout/success/", home_views.checkout_success, name="checkout_success"),

    # Auth
    path("login/", home_views.login_view, name="login_view"),
    path("logout/", home_views.logout_view, name="logout_view"),

    # Footer Pages
    path("shipping-information/", home_views.shipping_info_view, name="shipping_information"),
    path("returns/", home_views.returns_view, name="returns"),
    path("imprint/", home_views.imprint_view, name="imprint"),
    path("privacy-policy/", home_views.privacy_view, name="privacy"),
    path("terms-conditions/", home_views.terms_view, name="terms"),

    # Kontakt (Manuell)
    path("contact/", home_views.contact_view, name="contact"),

    # --- HIER IST DIE ÄNDERUNG ---
    # 1. Startseite ("") lädt jetzt direkt den Shop (kein Redirect!)
    path("", home_views.index_shop_view, name="home"), 
    
    # 2. Explizite Pfade für deine anderen Hauptseiten (zur Sicherheit)
    # (Dafür müssen wir gleich kurz in views.py sicherstellen, dass die Funktionen da sind)
    path("about/", home_views.home_view, name="about"),
    path("photography/", home_views.photography_view, name="photography"),

    # Wagtail (Fängt alles andere ab, z.B. Produkt-URLs)
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)