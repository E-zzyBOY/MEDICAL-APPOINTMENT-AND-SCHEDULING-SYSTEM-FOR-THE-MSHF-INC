"""Shared scheduling logic used by both doctor_views and secretary_views so
the two staff roles never drift on conflict-checking or slot generation.

Covers:
  - duration/buffer-aware interval overlap (replaces the old exact-time
    equality conflict check)
  - server-side bookable-slot generation (replaces the hardcoded 30-minute
    client-side splitting in the assign-time modals)
  - weekly ScheduleTemplate -> per-date Schedule materialization, so the
    rest of the app (which all reads Schedule directly) never has to know
    a recurring template exists at all.
"""
from datetime import datetime, timedelta, date as date_cls

from django.db import transaction
from django.utils import timezone

from .models import Appointment, DoctorScheduleSettings, Schedule, ScheduleException, ScheduleTemplate

# Appointment statuses that occupy a real slot on the doctor's calendar.
OCCUPYING_STATUSES = ['Scheduled', 'Confirmed', 'Rescheduled']


def slot_interval(the_time, duration_minutes):
    """(start, end) as plain datetime.time, for one slot of the given
    duration starting at the_time. Uses date.min as a throwaway anchor date
    purely so timedelta arithmetic is available on a time-of-day value."""
    anchor = datetime.combine(date_cls.min, the_time)
    end = anchor + timedelta(minutes=duration_minutes)
    return the_time, end.time()


def intervals_overlap(a_start, a_end, b_start, b_end):
    """True if [a_start, a_end) and [b_start, b_end) overlap at all — no
    buffer involved, pure interval overlap."""
    return a_start < b_end and a_end > b_start


def _to_minutes(t):
    return t.hour * 60 + t.minute


def too_close(a_start, a_end, b_start, b_end, buffer_minutes):
    """True if [a_start, a_end) and [b_start, b_end) overlap OR are closer
    together than buffer_minutes. The buffer is the required GAP between
    two appointments, applied once regardless of which one comes first —
    padding both intervals independently before an overlap check would
    double-count the gap, so this compares raw intervals directly instead."""
    a_start_m, a_end_m = _to_minutes(a_start), _to_minutes(a_end)
    b_start_m, b_end_m = _to_minutes(b_start), _to_minutes(b_end)
    return not (a_end_m + buffer_minutes <= b_start_m or b_end_m + buffer_minutes <= a_start_m)


def _appointment_duration(appt, doctor_settings=None):
    """An existing appointment's effective duration: its own snapshot if
    set, otherwise the doctor's CURRENT default (covers legacy rows created
    before duration_minutes existed, and rows assigned before the doctor
    last changed their default)."""
    if appt.duration_minutes:
        return appt.duration_minutes
    settings_row = doctor_settings or DoctorScheduleSettings.for_doctor(appt.doctor)
    return settings_row.appointment_duration_minutes


def check_appointment_conflict(doctor, patient, the_date, new_time, duration_minutes,
                                buffer_minutes=0, exclude_pk=None):
    """Duration/buffer-aware replacement for the old exact-time-equality
    conflict check. Returns {'doctor_conflict': bool, 'patient_conflict': bool}.

    Caller is responsible for the transaction.atomic()/select_for_update()
    locking around this — this function only does the interval math."""
    new_start, new_end = slot_interval(new_time, duration_minutes)

    doctor_conflict = False
    same_day_doctor = Appointment.objects.select_for_update().filter(
        doctor=doctor, appointment_date=the_date, status__in=OCCUPYING_STATUSES,
    ).exclude(pk=exclude_pk)
    doctor_settings = DoctorScheduleSettings.for_doctor(doctor)
    for existing in same_day_doctor:
        if not existing.appointment_time:
            continue
        e_start, e_end = slot_interval(
            existing.appointment_time, _appointment_duration(existing, doctor_settings),
        )
        if too_close(new_start, new_end, e_start, e_end, buffer_minutes):
            doctor_conflict = True
            break

    # A patient may see several different doctors, just never at an
    # overlapping/too-close time.
    patient_conflict = False
    same_day_patient = Appointment.objects.select_for_update().filter(
        patient=patient, appointment_date=the_date, status__in=OCCUPYING_STATUSES,
    ).exclude(pk=exclude_pk)
    for existing in same_day_patient:
        if not existing.appointment_time:
            continue
        existing_settings = (
            doctor_settings if existing.doctor_id == doctor.pk
            else DoctorScheduleSettings.for_doctor(existing.doctor)
        )
        e_start, e_end = slot_interval(
            existing.appointment_time, _appointment_duration(existing, existing_settings),
        )
        # A patient-side conflict only needs plain overlap, not the
        # doctor's buffer — buffer is a per-doctor pacing preference
        # between their own appointments, not a rule about the patient's
        # schedule across different doctors.
        if intervals_overlap(new_start, new_end, e_start, e_end):
            patient_conflict = True
            break

    return {'doctor_conflict': doctor_conflict, 'patient_conflict': patient_conflict}


def fits_within_blocks(the_time, duration_minutes, blocks):
    """True if a slot of duration_minutes starting at the_time fits
    entirely inside at least one (start, end) working-hours block —
    stricter than the old start<=t<end check, which ignored duration."""
    slot_start, slot_end = slot_interval(the_time, duration_minutes)
    for start, end in blocks:
        if start <= slot_start and slot_end <= end:
            return True
    return False


def generate_bookable_slots(doctor, the_date, exclude_appointment_pk=None):
    """Server-side replacement for the client-side `for (m += 30)` slot
    splitting. Returns an ordered list of:
        {'time': 'HH:MM', 'time_display': '9:00 AM', 'status':
         'available'|'occupied'|'past'|'blocked_by_cap', 'patient': str|None}
    covering every Schedule block for that date, stepped by
    appointment_duration_minutes + buffer_minutes."""
    settings_row = DoctorScheduleSettings.for_doctor(doctor)
    duration = settings_row.appointment_duration_minutes
    buffer_minutes = settings_row.buffer_minutes
    step = duration + buffer_minutes

    blocks = list(
        Schedule.objects.filter(doctor=doctor, specific_date=the_date)
        .order_by('start_time').values_list('start_time', 'end_time')
    )
    if not blocks:
        return []

    booked = list(
        Appointment.objects.filter(
            doctor=doctor, appointment_date=the_date,
            appointment_time__isnull=False, status__in=OCCUPYING_STATUSES,
        ).exclude(pk=exclude_appointment_pk).select_related('patient')
    )
    booked_intervals = []
    for appt in booked:
        b_start, b_end = slot_interval(appt.appointment_time, _appointment_duration(appt, settings_row))
        booked_intervals.append((b_start, b_end, appt))

    now_dt = timezone.localtime()
    earliest_bookable = now_dt + timedelta(hours=settings_row.min_notice_hours)

    at_cap = False
    if settings_row.max_bookings_per_day is not None:
        booked_count = Appointment.objects.filter(
            doctor=doctor, appointment_date=the_date, status__in=OCCUPYING_STATUSES + ['Pending Assignment'],
        ).exclude(pk=exclude_appointment_pk).count()
        at_cap = booked_count >= settings_row.max_bookings_per_day

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
            slot_start, slot_end = slot_interval(t, duration)

            occupying_patient = None
            for b_start, b_end, appt in booked_intervals:
                if too_close(slot_start, slot_end, b_start, b_end, buffer_minutes):
                    occupying_patient = appt.patient.get_full_name()
                    break

            slot_dt = timezone.make_aware(datetime.combine(the_date, t))

            status = 'available'
            if slot_dt < earliest_bookable:
                status = 'past'
            elif occupying_patient is not None:
                status = 'occupied'
            elif at_cap:
                status = 'blocked_by_cap'

            slots.append({
                'time': t.strftime('%H:%M'),
                'time_display': t.strftime('%I:%M %p').lstrip('0'),
                'status': status,
                'patient': occupying_patient,
            })
            cursor += timedelta(minutes=step)

    slots.sort(key=lambda s: s['time'])
    return slots


@transaction.atomic
def sync_generated_schedule_for_doctor(doctor, *, force=False):
    """Materializes a doctor's recurring ScheduleTemplate into real Schedule
    rows for the upcoming window, so every existing Schedule-reading code
    path (patient availability, staff calendars, slot generation) keeps
    working unchanged. No-ops immediately for any doctor who hasn't set up
    a weekly template — zero effect on doctors using only the legacy
    per-date tools.

    Never touches:
      - dates covered by a ScheduleException (doctor explicitly adjusted them)
      - Schedule rows with source='manual' (never auto-created/removed)
      - any date/time range that would overlap an existing row of either
        source, template or manual (defense in depth even without an
        exception row)
    """
    if not ScheduleTemplate.objects.filter(doctor=doctor).exists():
        return

    settings_row = DoctorScheduleSettings.for_doctor(doctor)
    today = timezone.localdate()
    if not force and settings_row.last_synced_date == today:
        return

    horizon_end = today + timedelta(days=settings_row.advance_booking_days)
    exception_dates = set(
        ScheduleException.objects.filter(
            doctor=doctor, date__gte=today, date__lte=horizon_end,
        ).values_list('date', flat=True)
    )

    templates_by_weekday = {}
    for tmpl in ScheduleTemplate.objects.filter(doctor=doctor):
        templates_by_weekday.setdefault(tmpl.weekday, []).append(tmpl)

    existing_rows = list(
        Schedule.objects.filter(
            doctor=doctor, specific_date__gte=today, specific_date__lte=horizon_end,
        )
    )
    existing_by_date = {}
    for row in existing_rows:
        existing_by_date.setdefault(row.specific_date, []).append(row)

    cursor = today
    while cursor <= horizon_end:
        if cursor not in exception_dates:
            day_templates = templates_by_weekday.get(cursor.weekday(), [])
            day_existing = existing_by_date.get(cursor, [])

            # Remove stale template rows that no longer match any template
            # block for this weekday.
            template_keys = {(t.start_time, t.end_time) for t in day_templates}
            for row in day_existing:
                if row.source == 'template' and (row.start_time, row.end_time) not in template_keys:
                    row.delete()
            day_existing = [
                r for r in day_existing
                if not (r.source == 'template' and (r.start_time, r.end_time) not in template_keys)
            ]

            # Create missing template rows, never overlapping anything
            # already on that date (manual or template).
            for tmpl in day_templates:
                key = (tmpl.start_time, tmpl.end_time)
                if any((r.start_time, r.end_time) == key for r in day_existing):
                    continue
                overlaps = any(
                    r.start_time < tmpl.end_time and r.end_time > tmpl.start_time
                    for r in day_existing
                )
                if overlaps:
                    continue
                new_row = Schedule.objects.create(
                    doctor=doctor, specific_date=cursor,
                    start_time=tmpl.start_time, end_time=tmpl.end_time,
                    source='template',
                )
                day_existing.append(new_row)
        cursor += timedelta(days=1)

    settings_row.last_synced_date = today
    settings_row.save(update_fields=['last_synced_date'])
