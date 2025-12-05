from django.db import models
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.models import User

from wagtail.models import Page, Orderable
from wagtail.fields import RichTextField
from wagtail.snippets.models import register_snippet
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, InlinePanel, FieldRowPanel
from modelcluster.fields import ParentalKey
from wagtail.contrib.forms.models import AbstractEmailForm, AbstractFormField
from django.core.mail import send_mail

# --- 1. PRICING SNIPPET ---
@register_snippet
class PrintSizePrice(models.Model):
    size_name = models.CharField(max_length=100)
    
    # Absolute Prices
    price_fine_art = models.DecimalField(decimal_places=2, max_digits=10, default=0, verbose_name="Price: Fine Art Print")
    price_alu_dibond = models.DecimalField(decimal_places=2, max_digits=10, default=0, verbose_name="Price: Alu-Composite")
    price_shadow_gap = models.DecimalField(decimal_places=2, max_digits=10, default=0, verbose_name="Price: Shadow Gap Frame")

    # Recommendation Logic
    recommend_shadow_gap = models.BooleanField(default=False, verbose_name="Show 'Recommended' badge on this size when Shadow Gap is picked?")

    panels = [
        FieldPanel('size_name'),
        FieldRowPanel([
            FieldPanel('price_fine_art'), 
            FieldPanel('price_alu_dibond'),
            FieldPanel('price_shadow_gap')
        ]),
        FieldPanel('recommend_shadow_gap')
    ]
    def __str__(self):
        return f"{self.size_name}"

# --- 2. PAGES ---
class HomePage(Page):
    template = "home/about.html"

class PhotographyPage(Page):
    template = "home/photography.html"

# -- New: Product Gallery Images (Extra slides) --
class ProductGalleryImage(Orderable):
    page = ParentalKey('ProductPage', related_name='gallery_images', on_delete=models.CASCADE)
    image = models.ForeignKey("wagtailimages.Image", on_delete=models.CASCADE, related_name="+")
    caption = models.CharField(blank=True, max_length=250)
    panels = [FieldPanel('image'), FieldPanel('caption')]

class ProductPage(Page):
    template = "home/details.html"
    
    # Main Image (Fine Art Default)
    product_image = models.ForeignKey("wagtailimages.Image", null=True, blank=False, on_delete=models.SET_NULL, related_name="+", verbose_name="Main Image (Fine Art / Default)")
    
    # Variant Specific Images
    image_fine_art_border = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Image: Fine Art + White Border")
    image_alu_dibond = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Image: Alu-Composite")
    image_shadow_gap = models.ForeignKey("wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Image: Shadow Gap Frame")

    orientation = models.CharField(max_length=20, choices=[('horizontal', 'Horizontal'), ('vertical', 'Vertical'), ('squared', 'Squared')], default='vertical')
    description_text = models.TextField(blank=True)
    
    # Checkbox to control default border state for 60x40
    default_border_large = models.BooleanField(default=True, verbose_name="Default 'Borders' checked for 60x40?")

    content_panels = Page.content_panels + [
        MultiFieldPanel([
            FieldPanel("product_image"),
            FieldPanel("image_fine_art_border"),
            FieldPanel("image_alu_dibond"),
            FieldPanel("image_shadow_gap"),
            FieldPanel("orientation"),
            FieldPanel("default_border_large")
        ], heading="Product Details"),
        InlinePanel('gallery_images', label="Extra Gallery Images"),
        FieldPanel("description_text")
    ]
    parent_page_types = ['home.IndexShopPage']
    
    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context['related_products'] = ProductPage.objects.live().exclude(pk=self.pk).order_by('?')[:3]
        context['all_variants'] = PrintSizePrice.objects.all().order_by('price_fine_art')
        return context

# --- 3. SHOP INDEX ---
class FeaturedProduct(Orderable):
    page = ParentalKey('home.IndexShopPage', related_name='featured_products')
    product_to_link = models.ForeignKey('home.ProductPage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    slider_image = models.ForeignKey("wagtailimages.Image", null=True, on_delete=models.SET_NULL, related_name="+")
    slider_title = RichTextField()
    slider_subtitle = models.CharField(max_length=255, blank=True)
    slider_description = models.TextField(blank=True)
    image_caption_title = models.CharField(max_length=100, blank=True)
    image_caption_subtitle = models.CharField(max_length=100, blank=True)
    panels = [FieldPanel('product_to_link'), FieldPanel('slider_image'), FieldPanel('slider_title'), FieldPanel('slider_subtitle'), FieldPanel('slider_description'), FieldPanel('image_caption_title'), FieldPanel('image_caption_subtitle')]

class IndexShopPage(Page):
    template = "home/index_shop.html"
    content_panels = Page.content_panels + [MultiFieldPanel([InlinePanel('featured_products', label="Slider Slides")], heading="Slider Content")]
    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context['grid_products'] = ProductPage.objects.child_of(self).live().specific()
        cheapest = PrintSizePrice.objects.all().order_by('price_fine_art').first()
        context['cheapest_price'] = cheapest.price_fine_art if cheapest else 0
        context['featured_slider_items'] = self.featured_products.all()
        return context

# --- 5. CHECKOUT (Unchanged) ---
class Order(models.Model):
    country = models.CharField(max_length=100, default='Austria')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    address = models.CharField(max_length=250)
    postal_code = models.CharField(max_length=20)
    city = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True)
    paid = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    stripe_pid = models.CharField(max_length=255, blank=True, null=True)
    class Meta: ordering = ['-created']
    def __str__(self): return f'Order {self.id}'

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(ProductPage, related_name='order_items', on_delete=models.CASCADE) 
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    size_name = models.CharField(max_length=100, blank=True, default='')
    finish = models.CharField(max_length=100, default='Fine Art Print')
    has_borders = models.BooleanField(default=False)
    framed = models.BooleanField(default=False) 
    def __str__(self): return f"{self.order.id} - {self.product.title}"

# --- 6. CONTACT PAGE (Unchanged) ---
class FormField(AbstractFormField):
    page = ParentalKey('ContactPage', on_delete=models.CASCADE, related_name='form_fields')

class ContactPage(AbstractEmailForm):
    template = "home/footer/contact.html"
    intro = RichTextField(blank=True)
    thank_you_text = RichTextField(blank=True)
    content_panels = AbstractEmailForm.content_panels + [
        FieldPanel('intro'),
        InlinePanel('form_fields', label="Form fields"),
        FieldPanel('thank_you_text'),
        MultiFieldPanel([
            FieldPanel('from_address'),
            FieldPanel('to_address'),
            FieldPanel('subject'),
        ], "Email Settings"),
    ]

    def process_form_submission(self, form):
        submission = super().process_form_submission(form)
        try:
            user_email = form.cleaned_data.get('email')
            user_name = form.cleaned_data.get('name', 'Besucher')
            if user_email:
                send_mail(
                    subject="Eingangsbestätigung: Deine Nachricht an Cumulophib",
                    message=f"Hallo {user_name},\n\ndanke für deine Nachricht! Ich habe sie erhalten und melde mich so schnell wie möglich bei dir.\n\nBeste Grüße,\nPhilip",
                    from_email='pheinrich210@gmail.com',
                    recipient_list=[user_email],
                    fail_silently=True
                )
        except Exception as e:
            print(f"MAIL ERROR: {e}", flush=True)
        return submission