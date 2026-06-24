from django import template

register = template.Library()

DOCTOR_COLORS = [
    {'name': 'emerald', 'border': 'border-emerald-500', 'bg': 'bg-emerald-50', 'text': 'text-emerald-700',
     'badge': 'bg-emerald-100 text-emerald-800', 'ring': 'ring-emerald-500/20', 'dot': 'bg-emerald-500'},
    {'name': 'blue', 'border': 'border-blue-500', 'bg': 'bg-blue-50', 'text': 'text-blue-700',
     'badge': 'bg-blue-100 text-blue-800', 'ring': 'ring-blue-500/20', 'dot': 'bg-blue-500'},
    {'name': 'purple', 'border': 'border-purple-500', 'bg': 'bg-purple-50', 'text': 'text-purple-700',
     'badge': 'bg-purple-100 text-purple-800', 'ring': 'ring-purple-500/20', 'dot': 'bg-purple-500'},
    {'name': 'amber', 'border': 'border-amber-500', 'bg': 'bg-amber-50', 'text': 'text-amber-700',
     'badge': 'bg-amber-100 text-amber-800', 'ring': 'ring-amber-500/20', 'dot': 'bg-amber-500'},
    {'name': 'rose', 'border': 'border-rose-500', 'bg': 'bg-rose-50', 'text': 'text-rose-700',
     'badge': 'bg-rose-100 text-rose-800', 'ring': 'ring-rose-500/20', 'dot': 'bg-rose-500'},
    {'name': 'cyan', 'border': 'border-cyan-500', 'bg': 'bg-cyan-50', 'text': 'text-cyan-700',
     'badge': 'bg-cyan-100 text-cyan-800', 'ring': 'ring-cyan-500/20', 'dot': 'bg-cyan-500'},
    {'name': 'indigo', 'border': 'border-indigo-500', 'bg': 'bg-indigo-50', 'text': 'text-indigo-700',
     'badge': 'bg-indigo-100 text-indigo-800', 'ring': 'ring-indigo-500/20', 'dot': 'bg-indigo-500'},
    {'name': 'teal', 'border': 'border-teal-500', 'bg': 'bg-teal-50', 'text': 'text-teal-700',
     'badge': 'bg-teal-100 text-teal-800', 'ring': 'ring-teal-500/20', 'dot': 'bg-teal-500'},
]


@register.filter
def doctor_color(doctor_id):
    idx = hash(str(doctor_id)) % len(DOCTOR_COLORS)
    return DOCTOR_COLORS[idx]
