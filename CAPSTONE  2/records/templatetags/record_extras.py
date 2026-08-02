from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup in templates: {{ my_dict|get_item:key }} — used to pull a
    visit's vitals list out of the visit_vitals mapping keyed by appointment id."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None
