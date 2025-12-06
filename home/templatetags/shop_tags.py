from django import template
from wagtail.images.models import Image

register = template.Library()

@register.simple_tag
def get_variant_image(product_id, index):
    # Searches for "cumulophib-{id}-{index}"
    filename = f"cumulophib-{product_id}-{index}"
    return Image.objects.filter(title=filename).first()