from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Avg, Case, When, Value, IntegerField, DateField, F, Q
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from datetime import date, datetime, time, timedelta
import calendar as calendar_module
from accounts.decorators import role_required
from appointments.models import (
    Appointment, Schedule, TIME_NULLS_FIRST,
    DoctorScheduleSettings, ScheduleTemplate, ScheduleException,
)
from appointments.forms import (
    ScheduleForm, RescheduleForm, AssignTimeForm, MultiDateScheduleForm,
    DoctorScheduleSettingsForm, ScheduleTemplateForm,
)
from appointments import services
from accounts.models import CustomUser
from notifications.email_utils import (
    send_cancellation_email, send_reschedule_email, send_booking_received_email, send_time_assigned_email,
    send_reminder_email
)
from notifications.models import Notification
from feedback.models import Feedback


def _notify(user, message):
    Notification.objects.create(user=user, message=message)


def _parse_date_str(value):
    """Parse a YYYY-MM-DD query param into a date, or None if missing/invalid
    (an unparseable date simply disables that end of the filter range)."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mark_exception(doctor, the_date):
    """Marks a date as manually adjusted so the weekly-template sync never
    regenerates/overwrites it — called whenever a doctor or secretary
    touches a specific date through the per-date Add/Edit/Delete tools."""
    ScheduleException.objects.get_or_create(doctor=doctor, date=the_date)


def _notify_assigned_secretaries(doctor, message):
    """Notifies every secretary who currently manages this doctor —
    primary assignees AND covering secretaries (the on-leave scenario;
    see accounts.models.SecretaryCoverage)."""
    from accounts.models import staff_users_for_doctor
    for staff_user in staff_users_for_doctor(doctor):
        if staff_user != doctor:
            _notify(staff_user, message)


def _format_date_str(selected_date_str):
    """Safely turn a 'YYYY-MM-DD' string into a display-friendly date, e.g.
    'Jun 29, 2026'. Mirrors the same helper on the patient booking side."""
    if not selected_date_str:
        return ''
    try:
        d = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except ValueError:
        return selected_date_str


def _resolve_calendar_month(request, selected_date_str):
    """Decide which year/month the schedule calendar grid should show: an
    explicit ?year=&month= from month-navigation clicks takes priority,
    then the month containing the currently selected date, then today's
    month. Mirrors the same helper on the patient booking side."""
    year_param  = request.GET.get('year')
    month_param = request.GET.get('month')
    if year_param and month_param:
        try:
            return int(year_param), int(month_param)
        except ValueError:
            pass
    if selected_date_str:
        try:
            d = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            return d.year, d.month
        except ValueError:
            pass
    today = date.today()
    return today.year, today.month


def _compute_schedule_month(doctor, year, month):
    """Build a day-by-day map for one calendar month, used to color the
    doctor's own 'Add Slot' calendar:
      has_slots = doctor already has one or more Schedule rows that day
      open      = no slot yet, but still a valid day to add one
      past      = before today, not selectable

    Returns a list of week rows; each cell is either None (padding outside
    the month) or a dict: {day, date, status}.
    """
    today = date.today()
    first_weekday, days_in_month = calendar_module.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end   = date(year, month, days_in_month)

    dates_with_slots = set(
        Schedule.objects.filter(
            doctor=doctor,
            specific_date__gte=month_start,
            specific_date__lte=month_end,
        ).values_list('specific_date', flat=True)
    )

    weeks = []
    week = [None] * first_weekday
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d < today:
            status = 'past'
        elif d in dates_with_slots:
            status = 'has_slots'
        else:
            status = 'open'
        week.append({'day': day, 'date': d.isoformat(), 'status': status})
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)
    return weeks


def _compute_schedule_month_with_slots(doctor, year, month):
    """Same grid as _compute_schedule_month, but each cell also carries its
    own actual Schedule rows (up to 3, plus a remaining count) so the
    desktop grid can show every day's time slots inline, always visible,
    without needing a click to reveal them."""
    today = date.today()
    first_weekday, days_in_month = calendar_module.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end   = date(year, month, days_in_month)

    month_slots = Schedule.objects.filter(
        doctor=doctor,
        specific_date__gte=month_start,
        specific_date__lte=month_end,
    ).order_by('specific_date', 'start_time')

    slots_by_date = {}
    for s in month_slots:
        slots_by_date.setdefault(s.specific_date, []).append(s)

    PREVIEW_LIMIT = 3
    weeks = []
    week = [None] * first_weekday
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        day_slots = slots_by_date.get(d, [])
        if d < today:
            status = 'past'
        elif day_slots:
            status = 'has_slots'
        else:
            status = 'open'
        week.append({
            'day': day, 'date': d.isoformat(), 'status': status,
            'slots': day_slots[:PREVIEW_LIMIT],
            'all_slots': day_slots,
            'more_count': max(0, len(day_slots) - PREVIEW_LIMIT),
        })
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)
    return weeks


def _format_hour_label(h):
    h = h % 24
    ampm = 'AM' if h < 12 else 'PM'
    hr = h % 12 or 12
    return f"{hr} {ampm}"


# Pixels per minute for the hourly time-grid (Week/Day views) — 1px/min =
# 60px per hour row, a plain enough ratio that top/height math is just
# "minutes since the axis start", no separate scale factor to carry around.
GRID_PX_PER_MIN = 1


def _time_grid_axis_and_positions(doctor, dates):
    """Shared hour-axis + pixel-positioned blocks/appointments for the
    Week and Day views' hourly time grid (like Google Calendar). Computes
    one axis (in whole hours) covering every Schedule block and booked
    Appointment across `dates`, clamped to at least 8AM-6PM, then positions
    each block/appointment as top/height pixels against that axis so the
    templates can render them as plain absolutely-positioned <div>s — no
    JS/CSS calendar library involved."""
    schedules = list(
        Schedule.objects.filter(doctor=doctor, specific_date__in=dates)
        .order_by('specific_date', 'start_time')
    )
    appts = list(
        Appointment.objects.filter(
            doctor=doctor, appointment_date__in=dates, appointment_time__isnull=False,
            status__in=['Scheduled', 'Confirmed', 'Rescheduled'],
        ).select_related('patient').order_by('appointment_date', 'appointment_time')
    )
    settings_row = DoctorScheduleSettings.for_doctor(doctor)
    default_duration = settings_row.appointment_duration_minutes

    def _appt_duration(a):
        return a.duration_minutes or default_duration

    min_hour, max_hour = None, None
    for s in schedules:
        sh, eh = s.start_time.hour, s.end_time.hour + (1 if s.end_time.minute else 0)
        min_hour = sh if min_hour is None else min(min_hour, sh)
        max_hour = eh if max_hour is None else max(max_hour, eh)
    for a in appts:
        end_dt = datetime.combine(date.min, a.appointment_time) + timedelta(minutes=_appt_duration(a))
        sh = a.appointment_time.hour
        eh = 24 if end_dt.date() != date.min else end_dt.hour + (1 if end_dt.minute else 0)
        min_hour = sh if min_hour is None else min(min_hour, sh)
        max_hour = eh if max_hour is None else max(max_hour, eh)

    if min_hour is None:
        axis_start, axis_end = 8, 18
    else:
        axis_start = max(0, min(min_hour, 8))
        axis_end = min(24, max(max_hour, 18))
        if axis_end <= axis_start:
            axis_end = axis_start + 1
    axis_start_min = axis_start * 60

    blocks_by_date = {}
    for s in schedules:
        start_min = s.start_time.hour * 60 + s.start_time.minute
        end_min = s.end_time.hour * 60 + s.end_time.minute
        blocks_by_date.setdefault(s.specific_date, []).append({
            'obj': s,
            'top': (start_min - axis_start_min) * GRID_PX_PER_MIN,
            'height': max((end_min - start_min) * GRID_PX_PER_MIN, 18),
        })

    appts_by_date = {}
    for a in appts:
        start_min = a.appointment_time.hour * 60 + a.appointment_time.minute
        appts_by_date.setdefault(a.appointment_date, []).append({
            'obj': a,
            'top': (start_min - axis_start_min) * GRID_PX_PER_MIN,
            'height': max(_appt_duration(a) * GRID_PX_PER_MIN, 18),
        })

    # Current-time indicator (like Google Calendar's red line) — only
    # meaningful when today is one of the rendered dates and the current
    # time falls within the axis, so day/week views past "now" simply
    # don't show it.
    now_top = None
    today = date.today()
    if today in dates:
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        if axis_start_min <= now_min <= axis_end * 60:
            now_top = (now_min - axis_start_min) * GRID_PX_PER_MIN

    return {
        'axis_start_hour': axis_start,
        'axis_end_hour': axis_end,
        'hour_rows': [{'hour': h, 'label': _format_hour_label(h)} for h in range(axis_start, axis_end)],
        'total_height': (axis_end - axis_start) * 60 * GRID_PX_PER_MIN,
        'blocks_by_date': blocks_by_date,
        'appts_by_date': appts_by_date,
        'now_top': now_top,
        'show_now_line': now_top is not None,
    }


def _week_grid_context(doctor, anchor):
    """Context for the Week calendar view: an hourly time grid (like
    Google Calendar) spanning Monday-to-Sunday for the week containing
    `anchor` (which is also the selected day), with the doctor's
    availability blocks and booked appointments positioned in their
    correct time slots. Shared by the doctor and secretary calendars."""
    today = date.today()
    week_start = anchor - timedelta(days=anchor.weekday())
    week_end   = week_start + timedelta(days=6)
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    slots_by_date = {}
    for s in Schedule.objects.filter(
        doctor=doctor, specific_date__gte=week_start, specific_date__lte=week_end,
    ).order_by('specific_date', 'start_time'):
        slots_by_date.setdefault(s.specific_date, []).append(s)
    axis = _time_grid_axis_and_positions(doctor, week_dates)
    days = []
    for d in week_dates:
        day_slots = slots_by_date.get(d, [])
        if d < today:
            status = 'past'
        elif day_slots:
            status = 'has_slots'
        else:
            status = 'open'
        days.append({
            'day': d.day, 'date': d.isoformat(),
            'weekday': d.strftime('%a').upper(),
            'status': status, 'slots': day_slots,
            'blocks_pos': axis['blocks_by_date'].get(d, []),
            'appts_pos': axis['appts_by_date'].get(d, []),
        })
    return {
        'view': 'week',
        'week_days': days,
        'range_display': f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}",
        'prev_anchor': (week_start - timedelta(days=7)).isoformat(),
        'next_anchor': (week_start + timedelta(days=7)).isoformat(),
        'selected_date': anchor.isoformat(),
        'today_iso': today.isoformat(),
        'axis_start_hour': axis['axis_start_hour'],
        'axis_end_hour': axis['axis_end_hour'],
        'hour_rows': axis['hour_rows'],
        'total_height': axis['total_height'],
        'now_top': axis['now_top'],
        'show_now_line': axis['show_now_line'],
    }


def _day_time_slots(doctor, the_date):
    """Doctor-facing slot table for the Day view: every duration-stepped
    slot inside the doctor's Schedule blocks for the date — the same step
    grid patients book against (see services.generate_bookable_slots) — each
    flagged with whichever booked Appointment (if any) occupies it. Unlike
    generate_bookable_slots, which filters out past/at-cap slots because
    it's used to decide what a *patient* may still book, this always
    returns every slot in the grid since it's the doctor's own read of
    their day."""
    settings_row = DoctorScheduleSettings.for_doctor(doctor)
    duration = settings_row.appointment_duration_minutes
    step = duration + settings_row.buffer_minutes

    blocks = list(
        Schedule.objects.filter(doctor=doctor, specific_date=the_date)
        .order_by('start_time').values_list('start_time', 'end_time')
    )
    if not blocks:
        return []

    booked_intervals = [
        (*services.slot_interval(a.appointment_time, a.duration_minutes or duration), a)
        for a in Appointment.objects.filter(
            doctor=doctor, appointment_date=the_date,
            appointment_time__isnull=False, status__in=services.OCCUPYING_STATUSES,
        ).select_related('patient')
    ]

    now = datetime.now()
    today = now.date()

    seen_times = set()
    slots = []
    for start, end in blocks:
        cursor = datetime.combine(the_date, start)
        block_end = datetime.combine(the_date, end)
        while cursor + timedelta(minutes=duration) <= block_end:
            t = cursor.time()
            if t in seen_times:
                cursor += timedelta(minutes=step)
                continue
            seen_times.add(t)
            slot_start, slot_end = services.slot_interval(t, duration)

            appt = next(
                (a for b_start, b_end, a in booked_intervals
                 if services.intervals_overlap(slot_start, slot_end, b_start, b_end)),
                None,
            )
            slots.append({
                'start_time': t,
                'end_time': slot_end,
                'appt': appt,
                'is_past': the_date < today or (the_date == today and t <= now.time()),
            })
            cursor += timedelta(minutes=step)

    slots.sort(key=lambda s: s['start_time'])
    return slots


def _day_grid_context(doctor, anchor):
    """Context for the Day calendar view: an hourly time grid for a single
    day, with availability blocks and booked appointments positioned in
    their correct time slots. Shared by the doctor and secretary calendars."""
    today = date.today()
    axis = _time_grid_axis_and_positions(doctor, [anchor])
    return {
        'view': 'day',
        'day_slots': list(
            Schedule.objects.filter(doctor=doctor, specific_date=anchor).order_by('start_time')
        ),
        'day_time_slots': _day_time_slots(doctor, anchor),
        'day_blocks_pos': axis['blocks_by_date'].get(anchor, []),
        'day_appts_pos': axis['appts_by_date'].get(anchor, []),
        'range_display': anchor.strftime('%a, %b %d, %Y'),
        'day_full_display': anchor.strftime('%A, %B %d, %Y'),
        'day_is_past': anchor < today,
        'prev_anchor': (anchor - timedelta(days=1)).isoformat(),
        'next_anchor': (anchor + timedelta(days=1)).isoformat(),
        'selected_date': anchor.isoformat(),
        'today_iso': today.isoformat(),
        'axis_start_hour': axis['axis_start_hour'],
        'axis_end_hour': axis['axis_end_hour'],
        'hour_rows': axis['hour_rows'],
        'total_height': axis['total_height'],
        'now_top': axis['now_top'],
        'show_now_line': axis['show_now_line'],
    }


def _resolve_grid_view(raw):
    """Sanitize a ?view= query/POST value down to the three calendar views."""
    return raw if raw in ('week', 'day') else 'month'


def _build_doctor_dashboard_data(request):
    today_appts = Appointment.objects.filter(
        doctor=request.user,
        appointment_date=date.today(),
        status__in=['Scheduled', 'Confirmed', 'Rescheduled', 'Pending Reschedule']
    ).select_related('patient').order_by('appointment_time')
    upcoming = Appointment.objects.filter(
        doctor=request.user,
        appointment_date__gt=date.today(),
        status__in=['Scheduled', 'Confirmed', 'Rescheduled']
    ).count()
    pending_reschedules = Appointment.objects.filter(
        doctor=request.user, status='Pending Reschedule'
    ).count()

    trend_start = date.today() - timedelta(days=29)
    counts_by_date = {
        row['appointment_date']: row['c']
        for row in Appointment.objects.filter(
            doctor=request.user, appointment_date__gte=trend_start, appointment_date__lte=date.today(),
        ).exclude(
            status='Pending Assignment'
        ).values('appointment_date').annotate(c=Count('id'))
    }
    trend = [
        {'date': (trend_start + timedelta(days=i)).isoformat(),
         'value': counts_by_date.get(trend_start + timedelta(days=i), 0)}
        for i in range(30)
    ]

    return {
        'userName': request.user.get_full_name() or request.user.username,
        'stats': [
            {'label': "Today's Appointments", 'value': today_appts.count()},
            {'label': 'Upcoming Appointments', 'value': upcoming},
            {'label': 'Pending Reschedules', 'value': pending_reschedules},
        ],
        'trend': trend,
        'trendLabel': 'Appointments',
        'appointmentsTitle': "Today's Appointments",
        'appointmentsHref': '/doctor/appointments/',
        'appointments': [
            {
                'primary': a.patient.get_full_name(),
                'date': a.appointment_date.isoformat(),
                'time': a.appointment_time.strftime('%H:%M'),
                'status': a.status,
            }
            for a in today_appts
        ],
        'quickActions': [
            {'title': 'View Schedule', 'description': 'Manage your weekly hours', 'href': '/doctor/schedule/'},
            {'title': 'Appointment Requests', 'description': 'Accept, decline, or reschedule', 'href': '/doctor/appointments/'},
            {'title': 'My Patients', 'description': 'View patient records', 'href': '/doctor/patients/'},
        ],
    }


@role_required('doctor')
def doctor_dashboard(request):
    dashboard_data = _build_doctor_dashboard_data(request)
    return render(request, 'doctor/dashboard.html', {'dashboard_data': dashboard_data})


@role_required('doctor')
def doctor_dashboard_data(request):
    return JsonResponse(_build_doctor_dashboard_data(request))


@role_required('doctor')
def schedule_list(request):
    """Main 'My Schedule' page: a Calendar tab (full calendar-app view —
    mini calendar + grid, mobile falls back to the circle calendar) and an
    Availability & Settings tab (the recurring weekly template editor) —
    mirrors how Google Calendar keeps its main calendar and its bookable-
    schedule editor as two separate screens instead of one stacked page."""
    services.sync_generated_schedule_for_doctor(request.user)
    active_tab = request.GET.get('tab')
    active_tab = active_tab if active_tab in ('calendar', 'availability') else 'calendar'
    selected_date_str = request.GET.get('date') or date.today().isoformat()

    context = {
        'active_tab': active_tab,
        'today_iso': date.today().isoformat(),
        'selected_date': selected_date_str,
        'selected_date_display': _format_date_str(selected_date_str),
    }

    if active_tab == 'calendar':
        year, month = _resolve_calendar_month(request, selected_date_str)
        calendar_weeks = _compute_schedule_month(request.user, year, month)
        calendar_weeks_with_slots = _compute_schedule_month_with_slots(request.user, year, month)

        selected_slots = []
        try:
            the_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            selected_slots = list(
                Schedule.objects.filter(doctor=request.user, specific_date=the_date).order_by('start_time')
            )
        except ValueError:
            pass

        context.update({
            'calendar_weeks': calendar_weeks,
            'calendar_weeks_with_slots': calendar_weeks_with_slots,
            'calendar_year': year, 'calendar_month': month,
            'calendar_month_name': calendar_module.month_name[month],
            'selected_slots': selected_slots,
            'view': 'month',
        })
        # ?view=week|day opens the desktop calendar in that view directly
        # (the same views the Month/Week/Day toggle switches to via htmx).
        view = _resolve_grid_view(request.GET.get('view'))
        if view != 'month':
            try:
                anchor = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                anchor = date.today()
            context.update(
                _week_grid_context(request.user, anchor) if view == 'week'
                else _day_grid_context(request.user, anchor)
            )
        context.update(_panel_context_for_date(request.user, selected_date_str))
    else:
        context.update(_template_editor_context(request.user))

    return render(request, 'doctor/schedule_list.html', context)


def _template_preview_positions(weekday_rows):
    """Pixel top/height for each ScheduleTemplate block per weekday, against
    a shared hour axis (clamped 7AM-7PM, widened to fit any block outside
    that range) — same 1px-per-minute math as _time_grid_axis_and_positions,
    just keyed by weekday instead of date, for the small live week-preview
    next to the Repeat Weekly editor (mirrors Google Calendar's 'Bookable
    appointment schedule' side-by-side preview)."""
    min_hour, max_hour = 7, 19
    for row in weekday_rows:
        for b in row['blocks']:
            min_hour = min(min_hour, b.start_time.hour)
            eh = b.end_time.hour + (1 if b.end_time.minute else 0)
            max_hour = max(max_hour, eh)
    axis_start_min = min_hour * 60

    positioned_rows = []
    for row in weekday_rows:
        blocks_pos = [
            {
                'top': (b.start_time.hour * 60 + b.start_time.minute) - axis_start_min,
                'height': max(
                    (b.end_time.hour * 60 + b.end_time.minute)
                    - (b.start_time.hour * 60 + b.start_time.minute),
                    14,
                ),
            }
            for b in row['blocks']
        ]
        positioned_rows.append({**row, 'blocks_pos': blocks_pos})

    return {
        'preview_weekday_rows': positioned_rows,
        'preview_hour_rows': [{'hour': h, 'label': _format_hour_label(h)} for h in range(min_hour, max_hour)],
        'preview_total_height': (max_hour - min_hour) * 60,
    }


def _template_editor_context(doctor):
    """Weekly 'Repeat weekly' template editor data (7 weekday rows, each
    with its own blocks) plus the doctor's derived-booking-rules settings,
    for the My Schedule page's new sections."""
    blocks_by_weekday = {}
    for tmpl in ScheduleTemplate.objects.filter(doctor=doctor):
        blocks_by_weekday.setdefault(tmpl.weekday, []).append(tmpl)
    weekday_rows = [
        {'weekday': wd, 'name': name, 'blocks': blocks_by_weekday.get(wd, [])}
        for wd, name in ScheduleTemplate.WEEKDAY_CHOICES
    ]
    context = {
        'template_weekday_rows': weekday_rows,
        'today_weekday': date.today().weekday(),
        'schedule_settings': DoctorScheduleSettings.for_doctor(doctor),
        'settings_form': DoctorScheduleSettingsForm(instance=DoctorScheduleSettings.for_doctor(doctor)),
    }
    context.update(_template_preview_positions(weekday_rows))
    return context


@role_required('doctor')
def schedule_calendar_partial(request):
    """Re-renders just the calendar grid on the main schedule page when the
    doctor clicks the prev/next month arrows. The day-detail panel below
    is untouched by this — it's a separate htmx target."""
    selected_date_str = request.GET.get('date', '')
    year, month = _resolve_calendar_month(request, selected_date_str)
    calendar_weeks = _compute_schedule_month(request.user, year, month)
    return render(request, 'doctor/_schedule_main_calendar_fragment.html', {
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_date': selected_date_str,
    })


@role_required('doctor')
def schedule_mini_calendar_partial(request):
    """Re-renders the desktop sidebar's compact 'jump to date' mini
    calendar (month nav only — day clicks navigate the main grid widget
    directly and repaint this one's selection client-side, see
    _schedule_mini_calendar.html)."""
    selected_date_str = request.GET.get('date', '')
    view = _resolve_grid_view(request.GET.get('view'))
    year, month = _resolve_calendar_month(request, selected_date_str)
    calendar_weeks = _compute_schedule_month(request.user, year, month)
    return render(request, 'doctor/_schedule_mini_calendar.html', {
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_date': selected_date_str,
        'view': view,
    })


def _panel_context_for_date(doctor, date_str):
    """Builds the context the sidebar panel needs for a given date: its
    slots, a friendly display string, whether it's today, and the plain
    iso string used for the Add/Edit/Delete links."""
    today = date.today()
    the_date = today
    if date_str:
        try:
            the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            the_date = today
    slots = list(
        Schedule.objects.filter(doctor=doctor, specific_date=the_date).order_by('start_time')
    )
    return {
        'panel_date_iso': the_date.isoformat(),
        'panel_date_display': _format_date_str(the_date.isoformat()),
        'panel_slots': slots,
        'panel_is_today': the_date == today,
    }


@role_required('doctor')
def schedule_grid_partial(request):
    """Desktop-only calendar widget in one of three views (?view=month|
    week|day; see _schedule_grid_desktop / _schedule_grid_week /
    _schedule_grid_day templates). Every day's time slots are always
    visible right inside that day's own cell. Clicking a day (or
    navigating in day view) re-renders this grid (so the clicked day
    shows as selected) AND rides an out-of-band swap along in the same
    response to update the 'Today's Schedule' sidebar with that day's
    full detail (add/edit/delete) — no modal."""
    services.sync_generated_schedule_for_doctor(request.user)
    view = _resolve_grid_view(request.GET.get('view'))
    selected_date_str = request.GET.get('date') or date.today().isoformat()
    try:
        anchor = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        anchor = date.today()
        selected_date_str = anchor.isoformat()

    if view == 'week':
        grid_html = render_to_string('doctor/_schedule_grid_week.html',
                                     _week_grid_context(request.user, anchor), request=request)
    elif view == 'day':
        grid_html = render_to_string('doctor/_schedule_grid_day.html',
                                     _day_grid_context(request.user, anchor), request=request)
    else:
        year, month = _resolve_calendar_month(request, selected_date_str)
        calendar_weeks = _compute_schedule_month_with_slots(request.user, year, month)
        grid_html = render_to_string('doctor/_schedule_grid_desktop.html', {
            'calendar_weeks': calendar_weeks,
            'calendar_year': year, 'calendar_month': month,
            'calendar_month_name': calendar_module.month_name[month],
            'today_iso': date.today().isoformat(),
            'selected_date': selected_date_str,
        }, request=request)
    panel_html = render_to_string('doctor/_schedule_selected_day_panel.html', {
        'oob': True,
        **_panel_context_for_date(request.user, selected_date_str),
    }, request=request)
    return HttpResponse(grid_html + panel_html)


@role_required('doctor')
def schedule_day_detail(request):
    """Action-capable version of the day-info panel: fetched whenever the
    doctor clicks a date on the main schedule calendar. Unlike
    _schedule_day_info.html (read-only, used inside the Add Slot modal),
    this one lets the doctor edit or remove each slot right from the
    panel, and add a new one already scoped to this date."""
    date_str = request.GET.get('date', '')
    slots = []
    if date_str:
        try:
            the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            slots = list(
                Schedule.objects.filter(doctor=request.user, specific_date=the_date).order_by('start_time')
            )
        except ValueError:
            pass
    return render(request, 'doctor/_schedule_day_detail.html', {
        'date_str': date_str,
        'date_display': _format_date_str(date_str),
        'slots': slots,
    })


@role_required('doctor')
def schedule_day_info(request):
    """Returns just the 'existing slots on this date' info panel, fetched
    whenever the doctor clicks a day on the Add Slot calendar. Kept
    separate from the multi-select toggle itself (which is pure
    client-side JS) so clicking a day never re-renders the whole modal or
    loses whatever other days are already selected."""
    date_str = request.GET.get('date', '')
    existing = []
    if date_str:
        try:
            the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            existing = list(
                Schedule.objects.filter(doctor=request.user, specific_date=the_date)
                .order_by('start_time')
            )
        except ValueError:
            pass
    return render(request, 'doctor/_schedule_day_info.html', {
        'date_str': date_str,
        'date_display': _format_date_str(date_str),
        'existing_slots': existing,
    })


@role_required('doctor')
def schedule_day_popover(request):
    """Small 'day preview' popover, like clicking a date in Google
    Calendar: opened from any day cell in the month/week grid, shows that
    day's availability blocks + booked appointments and quick actions,
    without re-rendering the whole grid or losing scroll position."""
    date_str = request.GET.get('date', '')
    today = date.today()
    try:
        the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        the_date = today
        date_str = the_date.isoformat()
    appts = list(
        Appointment.objects.filter(
            doctor=request.user, appointment_date=the_date, appointment_time__isnull=False,
            status__in=['Scheduled', 'Confirmed', 'Rescheduled'],
        ).select_related('patient').order_by('appointment_time')
    )
    context = {
        'title': the_date.strftime('%A, %B %d, %Y'),
        'is_today': the_date == today,
        'is_past': the_date < today,
        'panel_appts': appts,
        **_panel_context_for_date(request.user, date_str),
    }
    return render(request, 'doctor/_schedule_day_popover.html', context)


@role_required('doctor')
def schedule_add(request):
    """Add Slot now accepts MULTIPLE dates at once — the doctor multi-selects
    days on the calendar (pure client-side toggle, see the JS in
    _schedule_calendar_fragment.html) and applies one start/end time to
    all of them in a single submit. Each date is checked for overlap
    independently: a date that already has a conflicting slot is skipped
    (not saved) while every other selected date still gets its slot, and
    the doctor sees exactly which ones succeeded vs were skipped and why.

    Two modes share this view, and they are deliberately opposites so
    neither can do the other's job:
      default ('Add Slot')      — creates slots only on days with NO slot
        yet. Days already added are locked here: changing their time is
        Edit Time's job, adding another block is Add Time's job.
      mode=add_time ('Add Time for This Day') — only days that ALREADY
        have at least one slot are accepted, so it can stack an extra
        time block onto a day the doctor previously added but can never
        plant a slot on a day that was never added."""
    add_time_mode = (request.POST.get('mode') or request.GET.get('mode', '')) == 'add_time'
    selected_dates_str = request.POST.get('dates') or request.GET.get('date', '')
    # GET (just opening the modal) only ever carries one date so far, from
    # a single calendar click — that's fine, it seeds the multi-select
    # with one day already toggled on. Drop seed dates that this mode
    # wouldn't accept anyway (e.g. opening plain Add Slot scoped to a day
    # that already has slots), so the doctor never starts with a
    # pre-selected day the calendar itself renders as locked.
    if request.method != 'POST' and selected_dates_str:
        kept = []
        for part in selected_dates_str.split(','):
            part = part.strip()
            if not part:
                continue
            try:
                d = datetime.strptime(part, '%Y-%m-%d').date()
            except ValueError:
                continue
            day_has_slots = Schedule.objects.filter(
                doctor=request.user, specific_date=d,
            ).exists()
            if day_has_slots == add_time_mode:
                kept.append(part)
        selected_dates_str = ','.join(kept)
    year, month = _resolve_calendar_month(request, selected_dates_str.split(',')[0] if selected_dates_str else '')
    calendar_weeks = _compute_schedule_month(request.user, year, month)

    if request.method == 'POST':
        form = MultiDateScheduleForm(request.POST)
        if form.is_valid():
            target_dates = form.cleaned_data['dates']
            start_time   = form.cleaned_data['start_time']
            end_time     = form.cleaned_data['end_time']

            saved_dates  = []
            skipped      = []  # list of (date, reason) tuples
            with transaction.atomic():
                for d in target_dates:
                    day_has_slots = Schedule.objects.filter(
                        doctor=request.user, specific_date=d,
                    ).exists()
                    if add_time_mode and not day_has_slots:
                        skipped.append((d, "has no slot yet — use Add Slot to schedule that day first"))
                        continue
                    if not add_time_mode and day_has_slots:
                        skipped.append((d, "was already added — use Edit Time to change it, or Add Time for This Day to add another block"))
                        continue
                    overlap = Schedule.objects.filter(
                        doctor=request.user, specific_date=d,
                        start_time__lt=end_time, end_time__gt=start_time,
                    ).exists()
                    if overlap:
                        skipped.append((d, 'overlaps with an existing slot on that date'))
                        continue
                    Schedule.objects.create(
                        doctor=request.user, specific_date=d,
                        start_time=start_time, end_time=end_time,
                        source='manual',
                    )
                    _mark_exception(request.user, d)
                    saved_dates.append(d)

            if saved_dates:
                dates_display = ', '.join(d.strftime('%b %d') for d in saved_dates)
                _notify_assigned_secretaries(
                    request.user,
                    f"Dr. {request.user.get_full_name()} added schedule slots on "
                    f"{dates_display} ({start_time.strftime('%I:%M %p')}–{end_time.strftime('%I:%M %p')})."
                )
            if saved_dates and not skipped:
                messages.success(request, f"Added the slot to {len(saved_dates)} date(s).")
            elif saved_dates and skipped:
                skipped_display = '; '.join(f"{d.strftime('%b %d')} {r}" for d, r in skipped)
                messages.success(
                    request,
                    f"Added the slot to {len(saved_dates)} date(s). "
                    f"Skipped {len(skipped)}: {skipped_display}."
                )
            elif not saved_dates:
                skipped_display = '; '.join(f"{d.strftime('%b %d')} {r}" for d, r in skipped)
                conflict_msg = f"No slots were added: {skipped_display}."
                form.add_error(None, conflict_msg)
                messages.error(request, conflict_msg)

            if saved_dates:
                if request.htmx:
                    response = render(request, 'doctor/_schedule_modal.html', {'form': MultiDateScheduleForm(), 'action': 'Add'})
                    response['HX-Redirect'] = f'/doctor/schedule/?date={saved_dates[-1].isoformat()}'
                    return response
                return redirect(f"{reverse('doctor:schedule_list')}?date={saved_dates[-1].isoformat()}")
            # Nothing saved at all — fall through and re-show the form
            # with the same dates still selected so the doctor can pick a
            # different time without having to re-select every day.
    else:
        form = MultiDateScheduleForm(initial={'dates': selected_dates_str})

    context = {
        'form': form, 'action': 'Add',
        'add_time_mode': add_time_mode,
        'selected_dates': selected_dates_str,
        'selected_dates_list': [s for s in selected_dates_str.split(',') if s],
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
    }
    if request.htmx:
        return render(request, 'doctor/_schedule_modal.html', context)
    return render(request, 'doctor/schedule_form.html', context)


@role_required('doctor')
def schedule_add_calendar_partial(request):
    """Re-renders just the calendar grid inside the Add Slot modal when the
    doctor clicks the prev/next month arrows. The full multi-select set
    (selected_dates, comma-joined) is carried through via querystring so
    navigating months never loses days already picked in another month —
    the selection itself lives in the page via a hidden input the JS
    toggle maintains, this param just lets the freshly-rendered grid know
    which days (if any, in the now-visible month) to paint as selected."""
    selected_dates_str = request.GET.get('selected_dates', '')
    first_date = selected_dates_str.split(',')[0] if selected_dates_str else ''
    year, month = _resolve_calendar_month(request, first_date)
    calendar_weeks = _compute_schedule_month(request.user, year, month)
    return render(request, 'doctor/_schedule_calendar_fragment.html', {
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_dates_list': [s for s in selected_dates_str.split(',') if s],
        'multi_select': True,
        'add_time_mode': request.GET.get('mode', '') == 'add_time',
    })


@role_required('doctor')
def schedule_edit_for_date(request):
    """Entry point for clicking a *different* day (one that already has its
    own slot) inside the Edit Slot popup's calendar. Editing must always
    stay scoped to one specific slot — this resolves the clicked date to
    that date's OWN Schedule row(s) rather than continuing to act on
    whichever slot the doctor originally opened Edit from.

    - Exactly one slot on that date  -> open Edit for that slot directly.
    - More than one slot on that date -> let the doctor pick which one
      (a day can have several time ranges).
    - None (shouldn't normally happen, since this link is only ever shown
      on days with a slot) -> fall back to Add Slot for that date.
    """
    date_str = request.GET.get('date', '')
    the_date = None
    if date_str:
        try:
            the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            the_date = None

    if the_date is None:
        return schedule_add(request)

    day_slots = list(
        Schedule.objects.filter(doctor=request.user, specific_date=the_date).order_by('start_time')
    )

    if len(day_slots) == 0:
        return schedule_add(request)

    if len(day_slots) == 1:
        return schedule_edit(request, pk=day_slots[0].pk)

    return render(request, 'doctor/_schedule_day_slot_picker.html', {
        'date_str': date_str,
        'date_display': _format_date_str(date_str),
        'slots': day_slots,
    })


@role_required('doctor')
def schedule_edit(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk, doctor=request.user)
    selected_date_str = (
        request.POST.get('specific_date')
        or request.GET.get('date')
        or schedule.specific_date.isoformat()
    )
    year, month = _resolve_calendar_month(request, selected_date_str)
    calendar_weeks = _compute_schedule_month(request.user, year, month)

    form = ScheduleForm(request.POST or None, instance=schedule, initial={'specific_date': selected_date_str})
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        # A doctor may only edit an existing slot, never use Edit to
        # plant a slot on a day he never scheduled at all — the target
        # date must already have at least one Schedule row (this one,
        # or another). A day with zero rows is not "his" to edit.
        already_scheduled = Schedule.objects.filter(
            doctor=request.user, specific_date=updated.specific_date,
        ).exists()
        if not already_scheduled:
            form.add_error(None, "You don't have a schedule on that date — Edit can only change a slot you already added. Use Add Slot to create a new day.")
            messages.error(request, 'That date has no existing schedule for you to edit.')
            if request.htmx:
                return render(request, 'doctor/_schedule_modal.html', {
                    'form': form, 'action': 'Edit', 'schedule': schedule,
                    'selected_date': selected_date_str,
                    'selected_date_display': _format_date_str(selected_date_str),
                    'calendar_weeks': calendar_weeks,
                    'calendar_year': year, 'calendar_month': month,
                    'calendar_month_name': calendar_module.month_name[month],
                    'today_iso': date.today().isoformat(),
                })
            return render(request, 'doctor/schedule_form.html', {
                'form': form, 'action': 'Edit', 'schedule': schedule,
                'selected_date': selected_date_str,
                'selected_date_display': _format_date_str(selected_date_str),
                'calendar_weeks': calendar_weeks,
                'calendar_year': year, 'calendar_month': month,
                'calendar_month_name': calendar_module.month_name[month],
                'today_iso': date.today().isoformat(),
            })
        overlap = Schedule.objects.filter(
            doctor=request.user,
            specific_date=updated.specific_date,
            start_time__lt=updated.end_time,
            end_time__gt=updated.start_time,
        ).exclude(pk=pk).exists()
        if overlap:
            form.add_error(None, 'This schedule conflicts with an existing time slot on that date. Please choose a different time.')
            messages.error(request, 'This schedule overlaps with an existing one on that date.')
            if request.htmx:
                return render(request, 'doctor/_schedule_modal.html', {
                    'form': form, 'action': 'Edit', 'schedule': schedule,
                    'selected_date': selected_date_str,
                    'selected_date_display': _format_date_str(selected_date_str),
                    'calendar_weeks': calendar_weeks,
                    'calendar_year': year, 'calendar_month': month,
                    'calendar_month_name': calendar_module.month_name[month],
                    'today_iso': date.today().isoformat(),
                })
        else:
            old_date, old_start, old_end = schedule.specific_date, schedule.start_time, schedule.end_time
            updated.source = 'manual'
            updated.save()
            _mark_exception(request.user, old_date)
            _mark_exception(request.user, updated.specific_date)
            _notify_assigned_secretaries(
                request.user,
                f"Dr. {request.user.get_full_name()} updated a schedule slot: "
                f"{old_date.strftime('%b %d, %Y')} {old_start.strftime('%I:%M %p')}–{old_end.strftime('%I:%M %p')} "
                f"is now {updated.specific_date.strftime('%b %d, %Y')} "
                f"{updated.start_time.strftime('%I:%M %p')}–{updated.end_time.strftime('%I:%M %p')}."
            )
            messages.success(request, 'Schedule updated.')
            if request.htmx:
                response = render(request, 'doctor/_schedule_modal.html', {'form': form, 'action': 'Edit'})
                response['HX-Redirect'] = f'/doctor/schedule/?date={updated.specific_date.isoformat()}'
                return response
            return redirect(f"{reverse('doctor:schedule_list')}?date={updated.specific_date.isoformat()}")

    context = {
        'form': form, 'action': 'Edit', 'schedule': schedule,
        'selected_date': selected_date_str,
        'selected_date_display': _format_date_str(selected_date_str),
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
    }
    if request.htmx:
        return render(request, 'doctor/_schedule_modal.html', context)
    return render(request, 'doctor/schedule_form.html', context)


@role_required('doctor')
def schedule_edit_calendar_partial(request, pk):
    """Re-renders just the calendar grid inside the Edit Slot modal when the
    doctor clicks the prev/next month arrows."""
    schedule = get_object_or_404(Schedule, pk=pk, doctor=request.user)
    selected_date_str = request.GET.get('selected_date', '')
    year, month = _resolve_calendar_month(request, '')
    calendar_weeks = _compute_schedule_month(request.user, year, month)
    return render(request, 'doctor/_schedule_calendar_fragment.html', {
        'calendar_weeks': calendar_weeks,
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_date': selected_date_str,
        'schedule': schedule,
    })


@role_required('doctor')
def schedule_delete(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk, doctor=request.user)
    if request.method == 'POST':
        removed_date, removed_start, removed_end = (
            schedule.specific_date, schedule.start_time, schedule.end_time
        )
        schedule.delete()
        _mark_exception(request.user, removed_date)
        _notify_assigned_secretaries(
            request.user,
            f"Dr. {request.user.get_full_name()} removed the schedule slot on "
            f"{removed_date.strftime('%B %d, %Y')} "
            f"({removed_start.strftime('%I:%M %p')}–{removed_end.strftime('%I:%M %p')})."
        )
        messages.success(request, 'Schedule slot removed.')
        if request.htmx:
            # Don't re-render _schedule_delete_modal.html here: it now builds
            # a URL from schedule.pk, but Django sets pk to None on an
            # instance right after .delete() succeeds, which would throw a
            # NoReverseMatch. HX-Redirect makes htmx navigate away
            # immediately anyway, so the response body just needs to be
            # valid HTML — its content is never shown to the user.
            from django.http import HttpResponse
            response = HttpResponse('')
            response['HX-Redirect'] = f'/doctor/schedule/?date={removed_date.isoformat()}'
            return response
        return redirect(f"{reverse('doctor:schedule_list')}?date={removed_date.isoformat()}")
    
    if request.htmx:
        return render(request, 'doctor/_schedule_delete_modal.html', {'schedule': schedule})
    return render(request, 'doctor/schedule_confirm_delete.html', {'schedule': schedule})


@role_required('doctor')
def schedule_settings(request):
    """Derived-booking-rules settings: appointment duration, buffer time,
    max bookings/day, and the scheduling window (advance days + minimum
    notice). Powers the new server-side slot generation used by the
    assign-time tools and constrains which dates patients can book."""
    settings_row = DoctorScheduleSettings.for_doctor(request.user)
    if request.method == 'POST':
        form = DoctorScheduleSettingsForm(request.POST, instance=settings_row)
        if form.is_valid():
            form.save()
            services.sync_generated_schedule_for_doctor(request.user, force=True)
            _notify_assigned_secretaries(
                request.user,
                f"Dr. {request.user.get_full_name()} updated their scheduling settings."
            )
            messages.success(request, 'Schedule settings updated.')
            if request.htmx:
                response = render(request, 'doctor/_schedule_settings_modal.html', {'form': form})
                response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
                return response
            return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")
    else:
        form = DoctorScheduleSettingsForm(instance=settings_row)

    context = {'form': form, 'title': 'Schedule Settings'}
    if request.htmx:
        return render(request, 'doctor/_schedule_settings_modal.html', context)
    return render(request, 'doctor/schedule_settings_form.html', context)


@role_required('doctor')
def schedule_template_add(request):
    """Adds one recurring weekly block (e.g. every Monday 9-12) to the
    doctor's 'Repeat weekly' template. Overlap is checked against the
    doctor's other blocks on the same weekday, mirroring schedule_add's
    per-date overlap check."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    form = ScheduleTemplateForm(request.POST)
    if form.is_valid():
        new_block = form.save(commit=False)
        overlap = ScheduleTemplate.objects.filter(
            doctor=request.user, weekday=new_block.weekday,
            start_time__lt=new_block.end_time, end_time__gt=new_block.start_time,
        ).exists()
        if overlap:
            messages.error(request, 'That overlaps with an existing block on that day of the week.')
        else:
            new_block.doctor = request.user
            new_block.save()
            services.sync_generated_schedule_for_doctor(request.user, force=True)
            _notify_assigned_secretaries(
                request.user,
                f"Dr. {request.user.get_full_name()} updated their weekly availability template "
                f"({new_block.get_weekday_display()} {new_block.start_time.strftime('%I:%M %p')}"
                f"–{new_block.end_time.strftime('%I:%M %p')})."
            )
            messages.success(request, f'Added to {new_block.get_weekday_display()}.')
    else:
        messages.error(request, 'End time must be after start time.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
        return response
    return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")


@role_required('doctor')
def schedule_template_quick_add(request):
    """Google-style '+' quick-add for the Repeat Weekly editor: creates one
    new block for the given weekday with sensible default hours (9am-5pm,
    or right after that day's last existing block) so the doctor can
    immediately fine-tune the times inline via schedule_template_edit
    instead of filling in a separate add-form first."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        weekday = int(request.POST.get('weekday', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid day.')
        return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")

    existing = list(
        ScheduleTemplate.objects.filter(doctor=request.user, weekday=weekday).order_by('start_time')
    )
    if existing:
        start_time = existing[-1].end_time
        end_dt = datetime.combine(date.min, start_time) + timedelta(hours=1)
        end_time = end_dt.time() if end_dt.date() == date.min else time(23, 59)
    else:
        start_time, end_time = time(9, 0), time(17, 0)

    if start_time >= end_time:
        messages.error(request, "There's no room left in the day to add another block.")
    else:
        new_block = ScheduleTemplate.objects.create(
            doctor=request.user, weekday=weekday, start_time=start_time, end_time=end_time,
        )
        services.sync_generated_schedule_for_doctor(request.user, force=True)
        _notify_assigned_secretaries(
            request.user,
            f"Dr. {request.user.get_full_name()} updated their weekly availability template "
            f"({new_block.get_weekday_display()} {new_block.start_time.strftime('%I:%M %p')}"
            f"–{new_block.end_time.strftime('%I:%M %p')})."
        )
        messages.success(request, f'Added to {new_block.get_weekday_display()}.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
        return response
    return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")


@role_required('doctor')
def schedule_template_edit(request, pk):
    """Inline edit of one weekly template block's times. The Google-style
    editor keeps the time inputs directly on the day row (see
    _schedule_template_editor.html) and auto-submits this on
    hx-trigger="change" instead of a separate add-form popup."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    block = get_object_or_404(ScheduleTemplate, pk=pk, doctor=request.user)
    form = ScheduleTemplateForm(request.POST, instance=block)
    if form.is_valid():
        updated = form.save(commit=False)
        overlap = ScheduleTemplate.objects.filter(
            doctor=request.user, weekday=updated.weekday,
            start_time__lt=updated.end_time, end_time__gt=updated.start_time,
        ).exclude(pk=updated.pk).exists()
        if overlap:
            messages.error(request, 'That overlaps with another block on that day of the week.')
        else:
            updated.save()
            services.sync_generated_schedule_for_doctor(request.user, force=True)
            _notify_assigned_secretaries(
                request.user,
                f"Dr. {request.user.get_full_name()} updated their weekly availability template "
                f"({updated.get_weekday_display()} {updated.start_time.strftime('%I:%M %p')}"
                f"–{updated.end_time.strftime('%I:%M %p')})."
            )
            messages.success(request, f'Updated {updated.get_weekday_display()}.')
    else:
        messages.error(request, 'End time must be after start time.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
        return response
    return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")


@role_required('doctor')
def schedule_template_delete(request, pk):
    """Removes one block from the weekly template. This never touches
    already-generated Schedule rows directly — the next sync will simply
    stop regenerating that block on future (non-exception) dates."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    block = get_object_or_404(ScheduleTemplate, pk=pk, doctor=request.user)
    weekday_display = block.get_weekday_display()
    block.delete()
    services.sync_generated_schedule_for_doctor(request.user, force=True)
    _notify_assigned_secretaries(
        request.user,
        f"Dr. {request.user.get_full_name()} removed a weekly availability block on {weekday_display}."
    )
    messages.success(request, f'Removed from {weekday_display}.')
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
        return response
    return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")


@role_required('doctor')
def schedule_template_duplicate(request):
    """Copies every block from one weekday onto one or more other weekdays
    ('duplicate this day's blocks to other days'). Each target weekday is
    validated independently — a target that already has a conflicting
    block is skipped rather than failing the whole operation."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        source_weekday = int(request.POST.get('source_weekday', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid source day.')
        return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")

    target_weekdays = []
    for raw in request.POST.getlist('target_weekdays'):
        try:
            target_weekdays.append(int(raw))
        except (TypeError, ValueError):
            continue

    source_blocks = list(ScheduleTemplate.objects.filter(doctor=request.user, weekday=source_weekday))
    if not source_blocks:
        messages.error(request, 'That day has no blocks to duplicate.')
    else:
        copied_to = []
        for target in target_weekdays:
            if target == source_weekday:
                continue
            for block in source_blocks:
                overlap = ScheduleTemplate.objects.filter(
                    doctor=request.user, weekday=target,
                    start_time__lt=block.end_time, end_time__gt=block.start_time,
                ).exists()
                if not overlap:
                    ScheduleTemplate.objects.create(
                        doctor=request.user, weekday=target,
                        start_time=block.start_time, end_time=block.end_time,
                    )
                    if target not in copied_to:
                        copied_to.append(target)
        if copied_to:
            services.sync_generated_schedule_for_doctor(request.user, force=True)
            names = ', '.join(dict(ScheduleTemplate.WEEKDAY_CHOICES)[w] for w in copied_to)
            _notify_assigned_secretaries(
                request.user,
                f"Dr. {request.user.get_full_name()} duplicated weekly availability to {names}."
            )
            messages.success(request, f'Duplicated to {names}.')
        else:
            messages.error(request, 'Nothing was duplicated — every target day already had a conflicting block.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('doctor:schedule_list') + '?tab=availability'
        return response
    return redirect(f"{reverse('doctor:schedule_list')}?tab=availability")


@role_required('doctor')
def doctor_appointment_list(request):
    status_filter = request.GET.get('status', 'Scheduled')
    qs = Appointment.objects.filter(doctor=request.user).select_related('patient', 'patient_details')
    if status_filter == 'Scheduled':
        # The "Scheduled" tab is the doctor's active worklist. 'Confirmed'
        # (patient checked in) and 'Rescheduled' appointments must stay
        # visible here until completed — otherwise a secretary confirming
        # a patient makes the appointment vanish from the doctor's view.
        # Past-dated rows that were never closed out move to the "Past"
        # tab instead of lingering here indefinitely.
        qs = qs.filter(status__in=['Scheduled', 'Confirmed', 'Rescheduled'], appointment_date__gte=date.today())
    elif status_filter == 'Past':
        # Anything still non-terminal whose date has already passed —
        # nobody ever marked it Completed/No-Show/Cancelled.
        qs = qs.filter(status__in=Appointment.ACTIVE_STATUSES, appointment_date__lt=date.today())
    elif status_filter:
        qs = qs.filter(status=status_filter)
    else:
        # Active/upcoming appointments only. Completed visits are accessible
        # via the "Completed" tab — excluded from the default view so the
        # doctor sees today's actionable patients first, not old history.
        qs = qs.filter(status__in=['Scheduled', 'Confirmed', 'Rescheduled'], appointment_date__gte=date.today())
    today = date.today()
    # Today's appointments first, then upcoming (soonest first), then past
    # (most recent first). SQLite's JULIANDAY() can't be used here — it
    # doesn't exist on PostgreSQL (the production database) — so the two
    # sort directions are expressed as separate date keys instead: each row
    # populates only the key for its own group, staying NULL (neutral) for
    # the other.
    qs = qs.annotate(
        sort_group=Case(
            When(appointment_date=today, then=Value(0)),
            When(appointment_date__gt=today, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        upcoming_date=Case(
            When(appointment_date__gte=today, then=F('appointment_date')),
            default=None,
            output_field=DateField(),
        ),
        past_date=Case(
            When(appointment_date__lt=today, then=F('appointment_date')),
            default=None,
            output_field=DateField(),
        ),
    ).order_by(
        'sort_group',
        F('upcoming_date').asc(nulls_last=True),
        F('past_date').desc(nulls_last=True),
        TIME_NULLS_FIRST,
    )
    return render(request, 'doctor/appointment_list.html', {
        'appointments': qs, 'status_filter': status_filter
    })


@role_required('doctor')
def appointment_detail(request, pk):
    appt = get_object_or_404(Appointment.objects.select_related('patient', 'patient_details'), pk=pk, doctor=request.user)
    return render(request, 'doctor/_appointment_detail_modal.html', {
        'appt': appt, 'title': 'Appointment Details',
    })


@role_required('doctor')
def resend_reminder(request, pk):
    """Lets the doctor manually re-send the day-before reminder email to
    the patient on demand, instead of only ever firing automatically from
    the send_appointment_reminders cron job."""
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user)
    if request.method == 'POST':
        if not appt.can_resend_reminder:
            messages.error(request, 'Reminders can only be resent for upcoming scheduled appointments.')
        else:
            try:
                send_reminder_email(appt)
            except Exception:
                pass
            _notify(appt.patient,
                    f"Reminder: Dr. {request.user.get_full_name()} resent your appointment reminder for "
                    f"{appt.appointment_date.strftime('%B %d, %Y')}.")
            messages.success(request, 'Reminder email resent to the patient.')
        if request.htmx:
            response = HttpResponse('')
            response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/doctor/appointments/')
            return response
        return redirect('doctor:appointment_list')
    return HttpResponseNotAllowed(['POST'])


def _working_hours_for_date(doctor, the_date):
    """Returns the doctor's Schedule blocks for that date as (start, end)
    tuples, used to validate a staff-assigned time falls within them."""
    return list(
        Schedule.objects.filter(doctor=doctor, specific_date=the_date)
        .values_list('start_time', 'end_time')
    )


def _time_within_working_hours(the_time, blocks, duration_minutes=1):
    """A slot of duration_minutes starting at the_time must fit entirely
    inside at least one block — not just have its start time land inside
    one, which would allow an appointment to run past the doctor's hours."""
    return services.fits_within_blocks(the_time, duration_minutes, blocks)


@role_required('doctor')
def assign_appointment_time(request, pk):
    """Doctor sets the actual time on one of their own appointments that's
    awaiting time assignment. Mirrors secretary_views' version of this
    action — both roles can do this, whichever gets to it first."""
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status='Pending Assignment')
    blocks = _working_hours_for_date(appt.doctor, appt.appointment_date)
    doctor_settings = DoctorScheduleSettings.for_doctor(appt.doctor)
    duration = doctor_settings.appointment_duration_minutes

    if request.method == 'POST':
        form = AssignTimeForm(request.POST)
        if form.is_valid():
            new_time = form.cleaned_data['appointment_time']
            if not blocks:
                messages.error(request, "You have no working hours set for this date.")
            elif not _time_within_working_hours(new_time, blocks, duration):
                hours_display = ', '.join(
                    f"{s.strftime('%I:%M %p')}–{e.strftime('%I:%M %p')}" for s, e in blocks
                )
                messages.error(request, f"That time (plus your {duration}-minute appointment length) doesn't fit within your working hours ({hours_display}).")
            else:
                with transaction.atomic():
                    result = services.check_appointment_conflict(
                        doctor=appt.doctor, patient=appt.patient, the_date=appt.appointment_date,
                        new_time=new_time, duration_minutes=duration,
                        buffer_minutes=doctor_settings.buffer_minutes, exclude_pk=appt.pk,
                    )
                    doctor_conflict = result['doctor_conflict']
                    patient_conflict = result['patient_conflict']
                    conflict = doctor_conflict or patient_conflict
                    if doctor_conflict:
                        messages.error(request, 'You already have another appointment at that time. Choose a different time.')
                    elif patient_conflict:
                        messages.error(request, 'This patient already has another appointment at that time with a different doctor. Choose a different time.')
                    else:
                        appt.appointment_time = new_time
                        appt.duration_minutes = duration
                        appt.status = 'Scheduled'
                        appt.save()

                if not conflict:
                    try:
                        send_time_assigned_email(appt)
                    except Exception:
                        pass
                    _notify(appt.patient,
                            f"Your appointment with Dr. {appt.doctor.get_full_name()} on "
                            f"{appt.appointment_date.strftime('%B %d, %Y')} is confirmed for "
                            f"{new_time.strftime('%I:%M %p')}.")
                    messages.success(request, 'Appointment time assigned. Patient notified.')
                    if request.htmx:
                        response = render(request, 'doctor/_assign_time_modal.html', {
                            'appt': appt, 'form': form, 'blocks': blocks,
                        })
                        response['HX-Redirect'] = '/doctor/appointments/'
                        return response
                    return redirect('doctor:appointment_list')
    else:
        form = AssignTimeForm()

    context = {'appt': appt, 'form': form, 'blocks': blocks, 'title': 'Assign Appointment Time'}
    if request.htmx:
        return render(request, 'doctor/_assign_time_modal.html', context)
    return render(request, 'doctor/assign_time.html', context)


@role_required('doctor')
def get_occupied_times(request, pk):
    """API endpoint — server-generated bookable time slots for a doctor's
    appointment date, derived from the doctor's Schedule blocks and
    DoctorScheduleSettings (duration/buffer/max-per-day/min-notice).
    Replaces the old client-side 30-minute splitting. Returns JSON:
    {'slots': [{'time','time_display','status','patient'}], 'blocks': [...],
     'has_schedule': bool, 'is_past': bool, 'date': 'YYYY-MM-DD', 'appointment_id': pk}"""
    appt = get_object_or_404(
        Appointment, pk=pk, doctor=request.user,
        status__in=['Pending Assignment', 'Scheduled', 'Rescheduled']
    )
    blocks = _working_hours_for_date(request.user, appt.appointment_date)
    slots = services.generate_bookable_slots(request.user, appt.appointment_date, exclude_appointment_pk=appt.pk)
    return JsonResponse({
        'slots': slots,
        'blocks': [f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in blocks],
        'has_schedule': bool(blocks),
        'is_past': appt.appointment_date < date.today(),
        'date': appt.appointment_date.strftime('%Y-%m-%d'),
        'appointment_id': pk,
    })


@role_required('doctor')
def appointment_accept(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status__in=['Scheduled', 'Rescheduled'])
    if request.method == 'POST':
        appt.status = 'Confirmed'
        appt.save()
        _notify(appt.patient,
                f"Dr. {request.user.get_full_name()} has confirmed your appointment on "
                f"{appt.appointment_date.strftime('%B %d, %Y')} at {appt.appointment_time.strftime('%I:%M %p')}.")
        messages.success(request, 'Appointment confirmed.')
        if request.htmx:
            response = render(request, 'doctor/_appointment_action_modal.html', {'appointment': appt, 'action': 'accept'})
            response['HX-Redirect'] = '/doctor/appointments/'
            return response
        return redirect('doctor:appointment_list')
    if request.htmx:
        return render(request, 'doctor/_appointment_action_modal.html', {'appointment': appt, 'action': 'accept'})
    return render(request, 'doctor/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'accept'
    })


@role_required('doctor')
def appointment_decline(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status__in=['Scheduled', 'Rescheduled'])
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        appt.status = 'Cancelled'
        appt.save()
        try:
            send_cancellation_email(appt, reason)
        except Exception:
            pass
        _notify(appt.patient,
                f"Dr. {request.user.get_full_name()} has cancelled your appointment on "
                f"{appt.appointment_date.strftime('%B %d, %Y')}.")
        messages.success(request, 'Appointment declined and patient notified.')
        if request.htmx:
            response = render(request, 'doctor/_appointment_action_modal.html', {'appointment': appt, 'action': 'decline'})
            response['HX-Redirect'] = '/doctor/appointments/'
            return response
        return redirect('doctor:appointment_list')
    if request.htmx:
        return render(request, 'doctor/_appointment_action_modal.html', {'appointment': appt, 'action': 'decline'})
    return render(request, 'doctor/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'decline'
    })


@role_required('doctor')
def appointment_reschedule_approve(request, pk):
    """Doctor approves a patient's pending reschedule request: the new
    date becomes the appointment's date and the status moves to
    'Pending Assignment' so the doctor or secretary can assign the
    actual time next (same as a fresh booking)."""
    appt = get_object_or_404(Appointment, pk=pk, status='Pending Reschedule', doctor=request.user)
    if request.method == 'POST':
        appt.appointment_date    = appt.requested_date
        appt.appointment_time    = None
        if appt.requested_reason:
            appt.reason = appt.requested_reason
        appt.requested_date      = None
        appt.requested_time      = None
        appt.requested_reason    = ''
        appt.status              = 'Pending Assignment'
        appt.save()

        try:
            send_booking_received_email(appt)
        except Exception:
            pass
        _notify_assigned_secretaries(
            appt.doctor,
            f"Dr. {appt.doctor.get_full_name()} approved {appt.patient.get_full_name()}'s reschedule request to "
            f"{appt.appointment_date.strftime('%B %d, %Y')}. Awaiting time assignment."
        )
        _notify(appt.patient,
                f"Dr. {appt.doctor.get_full_name()} approved your reschedule request. New date: "
                f"{appt.appointment_date.strftime('%B %d, %Y')}. You'll be notified once the time is confirmed.")
        messages.success(request, 'Reschedule approved. Assign a time once ready.')
        if request.htmx:
            response = render(request, 'doctor/_reschedule_action_modal.html', {'appointment': appt, 'action': 'approve'})
            response['HX-Redirect'] = '/doctor/appointments/'
            return response
        return redirect('doctor:appointment_list')
    if request.htmx:
        return render(request, 'doctor/_reschedule_action_modal.html', {'appointment': appt, 'action': 'approve'})
    return render(request, 'doctor/reschedule_confirm_action.html', {'appointment': appt, 'action': 'approve'})


@role_required('doctor')
def appointment_reschedule_reject(request, pk):
    """Doctor rejects a patient's pending reschedule request: the
    appointment reverts to its original date/time/status, unchanged."""
    appt = get_object_or_404(Appointment, pk=pk, status='Pending Reschedule', doctor=request.user)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        requested_date = appt.requested_date
        appt.requested_date   = None
        appt.requested_time   = None
        appt.requested_reason = ''
        appt.status           = 'Scheduled'
        appt.save()
        original_time_display = (
            f" at {appt.appointment_time.strftime('%I:%M %p')}" if appt.appointment_time else ''
        )
        _notify(appt.patient,
                f"Dr. {appt.doctor.get_full_name()} declined your request to reschedule your appointment to "
                f"{requested_date.strftime('%B %d, %Y') if requested_date else ''}. "
                f"{('Reason: ' + reason) if reason else ''} Your original appointment on "
                f"{appt.appointment_date.strftime('%B %d, %Y')}{original_time_display} stays as is.")
        messages.success(request, 'Reschedule request declined. Patient notified, original appointment kept.')
        if request.htmx:
            response = render(request, 'doctor/_reschedule_action_modal.html', {'appointment': appt, 'action': 'reject'})
            response['HX-Redirect'] = '/doctor/appointments/'
            return response
        return redirect('doctor:appointment_list')
    if request.htmx:
        return render(request, 'doctor/_reschedule_action_modal.html', {'appointment': appt, 'action': 'reject'})
    return render(request, 'doctor/reschedule_confirm_action.html', {'appointment': appt, 'action': 'reject'})


@role_required('doctor')
def appointment_reschedule(request, pk):
    """Doctor directly moves one of their own appointments to a new date
    (separate from approving a patient's reschedule *request*). Date-only
    — the new appointment lands in 'Pending Assignment' just like a
    fresh booking, since RescheduleForm's clean_appointment_date already
    rejects past dates."""
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status__in=['Scheduled', 'Rescheduled'])
    form = RescheduleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        new_date = form.cleaned_data['appointment_date']
        new_reason = form.cleaned_data.get('reason') or appt.reason

        appt.status = 'Rescheduled'
        appt.save()
        new_appt = Appointment.objects.create(
            patient=appt.patient, doctor=request.user,
            appointment_date=new_date, appointment_time=None,
            status='Pending Assignment', reason=new_reason
        )
        try:
            send_booking_received_email(new_appt)
        except Exception:
            pass
        _notify_assigned_secretaries(
            request.user,
            f"Dr. {request.user.get_full_name()} rescheduled {appt.patient.get_full_name()}'s appointment to "
            f"{new_date.strftime('%B %d, %Y')}. Awaiting time assignment."
        )
        _notify(appt.patient,
                f"Dr. {request.user.get_full_name()} rescheduled your appointment to "
                f"{new_date.strftime('%B %d, %Y')}. You'll be notified once the time is confirmed.")
        messages.success(request, 'Appointment rescheduled. Assign a time once ready.')
        return redirect('doctor:appointment_list')
    return render(request, 'doctor/appointment_reschedule.html', {'form': form, 'appointment': appt})


@role_required('doctor')
def appointment_complete(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status__in=['Scheduled', 'Rescheduled', 'Confirmed'])
    if request.method == 'POST':
        appt.status = 'Completed'
        appt.save()
        messages.success(request, 'Appointment marked as completed.')
        return redirect('doctor:add_results', pk=appt.pk)
    return render(request, 'doctor/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'complete'
    })


@role_required('doctor')
def add_consultation_results(request, pk):
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user, status='Completed')
    from records.models import ResultsConsultation, MedicalRecords
    from records.forms import ResultsConsultationForm
    existing = getattr(appt, 'results', None)
    if request.method == 'GET' and existing and 'edit' not in request.GET:
        prescriptions = existing.prescriptions.all()
        return render(request, 'doctor/_consultation_readonly.html', {
            'appointment': appt, 'results': existing, 'prescriptions': prescriptions
        })
    form = ResultsConsultationForm(request.POST or None, instance=existing)
    if request.method == 'POST' and form.is_valid():
        result = form.save(commit=False)
        result.appointment = appt
        result.save()
        MedicalRecords.objects.get_or_create(
            doctor=request.user, patient=appt.patient,
            results=result, defaults={'visit_date': appt.appointment_date}
        )
        messages.success(request, 'Consultation results saved.')
        return redirect('doctor:add_prescription', pk=appt.pk)
    return render(request, 'doctor/consultation_form.html', {
        'form': form, 'appointment': appt, 'existing': existing
    })


@role_required('doctor')
def add_prescription(request, pk):
    from datetime import date
    appt = get_object_or_404(Appointment, pk=pk, doctor=request.user)
    from records.models import ResultsConsultation, Prescription
    from records.forms import PrescriptionForm
    try:
        results = appt.results
    except ResultsConsultation.DoesNotExist:
        messages.error(request, 'Please add consultation results first.')
        return redirect('doctor:add_results', pk=pk)
    form = PrescriptionForm(request.POST or None, request.FILES or None, initial={'date_issued': date.today()})
    if request.method == 'POST' and form.is_valid():
        prescription = form.save(commit=False)
        prescription.results_consultation = results
        prescription.save()
        messages.success(request, 'Prescription saved.')
        return redirect('doctor:appointment_list')
    prescriptions = results.prescriptions.all()
    return render(request, 'doctor/prescription_form.html', {
        'form': form, 'appointment': appt, 'prescriptions': prescriptions
    })


@role_required('doctor')
def doctor_patient_list(request):
    from django.db.models import Max
    patient_ids = Appointment.objects.filter(
        doctor=request.user
    ).values_list('patient_id', flat=True).distinct()
    patients = CustomUser.objects.filter(pk__in=patient_ids)
    return render(request, 'doctor/patient_list.html', {'patients': patients})


@role_required('doctor')
def patient_quickview(request, patient_id):
    patient = get_object_or_404(CustomUser, pk=patient_id, role='patient')
    has_appt = Appointment.objects.filter(doctor=request.user, patient=patient).exists()
    if not has_appt:
        messages.error(request, 'You do not have access to this patient.')
        return redirect('doctor:patient_list')
    profile = getattr(patient, 'patient_profile', None)
    last_visit = Appointment.objects.filter(doctor=request.user, patient=patient).order_by('-appointment_date').first()
    return render(request, 'doctor/_patient_quickview_modal.html', {
        'patient': patient, 'profile': profile, 'last_visit': last_visit, 'title': 'Patient Summary',
    })


@role_required('doctor')
def doctor_patient_records(request, patient_id):
    # Doctor may only view records for patients who have had appointments with them
    patient = get_object_or_404(CustomUser, pk=patient_id, role='patient')
    has_appt = Appointment.objects.filter(doctor=request.user, patient=patient).exists()
    if not has_appt:
        messages.error(request, 'You do not have access to this patient.')
        return redirect('doctor:patient_list')
    from records.models import MedicalRecords
    from records.views import partition_vitals

    q         = (request.GET.get('q') or '').strip()
    from_date = _parse_date_str(request.GET.get('from_date'))
    to_date   = _parse_date_str(request.GET.get('to_date'))
    doctor_pk = _parse_int(request.GET.get('doctor'))
    has_filters = bool(q or from_date or to_date or doctor_pk)

    base = MedicalRecords.objects.filter(patient=patient).select_related('results', 'doctor')
    filtered = base
    if q:
        filtered = filtered.filter(
            Q(results__diagnosis__icontains=q)
            | Q(results__prescriptions__notes__icontains=q)
            | Q(results__prescriptions__treatment__icontains=q)
        ).distinct()
    if from_date:
        filtered = filtered.filter(visit_date__gte=from_date)
    if to_date:
        filtered = filtered.filter(visit_date__lte=to_date)
    if doctor_pk:
        filtered = filtered.filter(doctor_id=doctor_pk)
    filtered = filtered.order_by('-visit_date')

    total_count = filtered.count()

    # A filtered view returns every match (a doctor searching a chronic
    # patient wants the whole set); only the unfiltered history is paginated
    # (10 at a time, "Load more" via htmx).
    if has_filters:
        visible_records = filtered
        limit           = total_count
        has_more        = False
        load_more_url   = None
    else:
        limit         = _parse_int(request.GET.get('limit'), 10)
        visible_records = filtered[:limit]
        has_more      = total_count > limit
        load_more_url = None
        if has_more:
            params = request.GET.copy()
            params['limit'] = str(limit + 10)
            load_more_url = reverse(
                'doctor:patient_records', kwargs={'patient_id': patient.pk}
            ) + '?' + params.urlencode()

    # Partition vitals against the FULL records set (not the filtered one) so
    # readings belonging to filtered-out visits never leak into General Vitals —
    # their visit cards simply aren't rendered.
    visit_vitals, general_vitals = partition_vitals(patient, base)

    profile = getattr(patient, 'patient_profile', None)
    doctors = CustomUser.objects.filter(
        pk__in=MedicalRecords.objects.filter(patient=patient)
        .values_list('doctor_id', flat=True).distinct()
    ).order_by('last_name', 'first_name')

    context = {
        'patient': patient,
        'records': visible_records,
        'total_count': total_count,
        'limit': limit,
        'has_more': has_more,
        'load_more_url': load_more_url,
        'visit_vitals': visit_vitals,
        'general_vitals': general_vitals,
        'profile': profile,
        'doctors': doctors,
        'q': q,
        'from_date': request.GET.get('from_date', ''),
        'to_date': request.GET.get('to_date', ''),
        'selected_doctor_id': doctor_pk,
        'has_filters': has_filters,
    }
    if request.htmx:
        return render(request, 'doctor/_records_list.html', context)
    return render(request, 'doctor/patient_records.html', context)


@role_required('doctor')
def doctor_feedback(request):
    """My Feedback — the doctor's own aggregate rating and anonymized
    patient comments. Deliberately a SEPARATE page from My Patients: that
    list is clinical (records/vitals) and mixing in ratings could bias how
    a doctor treats a patient based on a past review. Mirrors the same
    feedback/ratings data powering Admin's Feedback & Logs, scoped to only
    this doctor. Patient names are masked here (first 3 letters + ***),
    same convention as the admin feedback view."""
    feedback_qs = Feedback.objects.filter(
        appointment__doctor=request.user
    ).select_related('appointment', 'patient').order_by('-date_submitted')

    avg_rating = feedback_qs.aggregate(avg=Avg('rating'))['avg']
    count      = feedback_qs.count()

    # Mask names in the view instead of the template so the raw patient
    # object is never available to the page — anonymization is enforced at
    # the data boundary, not just by display convention.
    feedbacks = [
        {
            'masked_name': f"{fb.patient.get_full_name()[:3]}***",
            'rating':      fb.rating,
            'comment':     fb.comment,
            'date':        fb.date_submitted,
        }
        for fb in feedback_qs
    ]

    return render(request, 'doctor/feedback.html', {
        'feedbacks':   feedbacks,
        'avg_rating':  avg_rating,
        'review_count': count,
    })


@role_required('doctor')
def patient_critical_info(request, patient_id):
    """GET returns the Edit Critical Info modal; POST saves it. Same access
    rule as the doctor's Patient Records page — the doctor must have had an
    appointment with the patient."""
    patient = get_object_or_404(CustomUser, pk=patient_id, role='patient')
    has_appt = Appointment.objects.filter(doctor=request.user, patient=patient).exists()
    if not has_appt:
        messages.error(request, 'You do not have access to this patient.')
        return redirect('doctor:patient_list')
    from accounts.forms import CriticalInfoForm
    profile = getattr(patient, 'patient_profile', None)
    if request.method == 'POST':
        form = CriticalInfoForm(request.POST or None, instance=profile)
        if form.is_valid():
            if profile is None:
                profile = form.save(commit=False)
                profile.user = patient
            profile.save()
            messages.success(request, 'Critical info saved.')
            if request.htmx:
                response = HttpResponse('')
                response['HX-Redirect'] = reverse('doctor:patient_records', kwargs={'patient_id': patient.pk})
                return response
            return redirect('doctor:patient_records', patient_id=patient.pk)
    else:
        form = CriticalInfoForm(instance=profile)
    return render(request, 'doctor/_critical_info_modal.html', {
        'form': form, 'patient': patient, 'title': 'Edit Critical Info',
    })


@role_required('doctor')
def doctor_notifications(request):
    return redirect('/notifications/')
