from .models import doctors_for_secretary, SECRETARY_ACTIVE_DOCTOR_SESSION_KEY


def secretary_context(request):
    """Feeds the secretary top-bar doctor switcher on every secretary page:
    the doctors she may manage (primary + covered) and the one currently
    active. No-ops (empty dict) for anonymous users and every other role."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or getattr(user, 'role', '') != 'secretary':
        return {}
    doctors = doctors_for_secretary(user)
    active = None
    selected_id = request.session.get(SECRETARY_ACTIVE_DOCTOR_SESSION_KEY)
    if selected_id:
        for d in doctors:
            if d.pk == selected_id:
                active = d
                break
    if active is None and doctors:
        active = doctors[0]
    return {
        'secretary_doctors': doctors,
        'secretary_active_doctor': active,
    }
