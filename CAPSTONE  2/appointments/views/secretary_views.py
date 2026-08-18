from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.db import transaction
from datetime import date, datetime, timedelta
import calendar as calendar_module
from django.db.models import Q, Count, Case, When, Value, IntegerField, F, DateField
from accounts.decorators import role_required
from appointments.models import (
    Appointment, Schedule, TIME_NULLS_FIRST,
    DoctorScheduleSettings, ScheduleTemplate, ScheduleException,
)
from appointments.forms import (
    AssignTimeForm, ScheduleForm, DoctorScheduleSettingsForm, ScheduleTemplateForm,
)
from appointments import services
from accounts.models import (
    CustomUser, PatientProfile, SecretaryCoverage, doctors_for_secretary,
    SECRETARY_ACTIVE_DOCTOR_SESSION_KEY,
)
from accounts.forms import WalkInPatientForm
from notifications.email_utils import (
    send_cancellation_email, send_time_assigned_email, send_booking_confirmation_email,
    send_reminder_email
)
from notifications.models import Notification


def _notify(user, message):
    Notification.objects.create(user=user, message=message)


ACTIVE_DOCTOR_SESSION_KEY = SECRETARY_ACTIVE_DOCTOR_SESSION_KEY


def _assigned_doctor(user):
    """The secretary's PRIMARY doctor (SecretaryProfile.assigned_doctor).
    Coverage management uses this; day-to-day views use _active_doctor."""
    profile = getattr(user, 'secretary_profile', None)
    return profile.assigned_doctor if profile else None


def _active_doctor(request):
    """The doctor this secretary is currently working as: her primary
    assigned doctor, unless she used the top-bar switcher to select one of
    the doctors she's covering (see accounts.models.SecretaryCoverage).
    The session selection is re-validated against her allowed set on every
    request, so removing a coverage instantly revokes the access."""
    doctors = doctors_for_secretary(request.user)
    if not doctors:
        return None
    selected_id = request.session.get(ACTIVE_DOCTOR_SESSION_KEY)
    if selected_id:
        for d in doctors:
            if d.pk == selected_id:
                return d
    return doctors[0]


def _build_secretary_dashboard_data(request):
    doctor = _active_doctor(request)
    today_appts = Appointment.objects.filter(
        doctor=doctor,
        appointment_date=date.today(),
        status__in=['Pending Assignment', 'Scheduled', 'Confirmed', 'Rescheduled', 'Pending Reschedule']
    ).select_related('patient', 'doctor').order_by(TIME_NULLS_FIRST) if doctor else Appointment.objects.none()
    total_today = today_appts.count()
    pending_time_count = today_appts.filter(status='Pending Assignment').count() if doctor else 0

    trend_start = date.today() - timedelta(days=29)
    counts_by_date = {
        row['appointment_date']: row['c']
        for row in Appointment.objects.filter(
            doctor=doctor,
            appointment_date__gte=trend_start,
            appointment_date__lte=date.today(),
        ).exclude(
            status='Pending Assignment'
        ).values('appointment_date').annotate(c=Count('id'))
    } if doctor else {}
    trend = [
        {'date': (trend_start + timedelta(days=i)).isoformat(),
         'value': counts_by_date.get(trend_start + timedelta(days=i), 0)}
        for i in range(30)
    ]

    return {
        'userName': request.user.get_full_name() or request.user.username,
        'stats': [
            {'label': "Today's Appointments", 'value': total_today},
            {'label': "Awaiting Time Assignment", 'value': pending_time_count},
        ],
        'trend': trend,
        'trendLabel': 'Appointments',
        'appointmentsTitle': "Today's Appointments",
        'appointmentsHref': '/secretary/appointments/',
        'appointments': [
            {
                'primary': a.patient.get_full_name(),
                'secondary': f'Dr. {a.doctor.get_full_name()}',
                'date': a.appointment_date.isoformat(),
                'time': a.appointment_time.strftime('%H:%M') if a.appointment_time else None,
                'status': a.status,
            }
            for a in today_appts
        ],
        'quickActions': [
            {'title': 'Appointments', 'description': 'Approve or cancel requests', 'href': '/secretary/appointments/'},
            {'title': 'Doctor Profile', 'description': "View your doctor's info & availability", 'href': '/secretary/schedules/'},
            {'title': 'Patients', 'description': 'View patient list', 'href': '/secretary/patients/'},
        ],
    }


@role_required('secretary')
def secretary_dashboard(request):
    dashboard_data = _build_secretary_dashboard_data(request)
    return render(request, 'secretary/dashboard.html', {'dashboard_data': dashboard_data})


@role_required('secretary')
def secretary_dashboard_data(request):
    return JsonResponse(_build_secretary_dashboard_data(request))


@role_required('secretary')
def secretary_appointment_list(request):
    doctor = _active_doctor(request)
    status_filter = request.GET.get('status', 'Pending Assignment')
    date_filter   = request.GET.get('date', '')
    qs = Appointment.objects.filter(doctor=doctor).select_related('patient', 'doctor', 'patient_details') if doctor else Appointment.objects.none()
    if status_filter == 'Past':
        # Anything still non-terminal whose date has already passed —
        # nobody ever marked it Completed/No-Show/Cancelled.
        qs = qs.filter(status__in=Appointment.ACTIVE_STATUSES, appointment_date__lt=date.today())
    elif status_filter:
        qs = qs.filter(status=status_filter)
        if status_filter in Appointment.ACTIVE_STATUSES:
            # Past-dated rows in an active status move to the "Past" tab
            # instead of lingering in their normal status tab forever.
            qs = qs.filter(appointment_date__gte=date.today())
    if date_filter:
        qs = qs.filter(appointment_date=date_filter)
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
    return render(request, 'secretary/appointment_list.html', {
        'appointments': qs,
        'status_filter': status_filter, 'date_filter': date_filter,
        'assigned_doctor': doctor, 'today': today,
    })


@role_required('secretary')
def appointment_detail(request, pk):
    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment.objects.select_related('patient', 'doctor', 'patient_details'), pk=pk, doctor=doctor)
    return render(request, 'secretary/_appointment_detail_modal.html', {
        'appt': appt, 'title': 'Appointment Details', 'today': date.today(),
    })


@role_required('secretary')
def resend_reminder(request, pk):
    """Lets the secretary manually re-send the day-before reminder email to
    the patient on demand, instead of only ever firing automatically from
    the send_appointment_reminders cron job."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment, pk=pk, doctor=doctor)
    if request.method == 'POST':
        if not appt.can_resend_reminder:
            messages.error(request, 'Reminders can only be resent for upcoming scheduled appointments.')
        else:
            try:
                send_reminder_email(appt)
            except Exception:
                pass
            _notify(appt.patient,
                    f"Reminder: your appointment reminder for "
                    f"{appt.appointment_date.strftime('%B %d, %Y')} was resent.")
            messages.success(request, 'Reminder email resent to the patient.')
        if request.htmx:
            response = HttpResponse('')
            response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/secretary/appointments/')
            return response
        return redirect('secretary:appointment_list')
    return HttpResponseNotAllowed(['POST'])


def _working_hours_for_date(doctor, the_date):
    """Returns a list of (start_time, end_time) tuples — the doctor's
    Schedule blocks for that date — used to validate a staff-assigned time
    actually falls within working hours."""
    return list(
        Schedule.objects.filter(doctor=doctor, specific_date=the_date)
        .values_list('start_time', 'end_time')
    )


def _time_within_working_hours(the_time, blocks):
    return any(start <= the_time < end for start, end in blocks)


@role_required('secretary')
def assign_appointment_time(request, pk):
    """Secretary sets the actual time on an appointment that's either
    awaiting its first time assignment or had a reschedule date approved
    (both land in 'Pending Time Assignment'). Validates the chosen time
    falls within the doctor's working hours that day and doesn't conflict
    with another appointment, the same two things doctor_views' version of
    this action checks — both staff roles can do this."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(
        Appointment, pk=pk, doctor=doctor, status__in=['Pending Assignment', 'Scheduled', 'Rescheduled']
    )
    # The modal's date picker may have moved the appointment to a different
    # (future) date — carry that through the whole validation so a request
    # whose original date has already passed can still be resolved.
    the_date = appt.appointment_date
    if request.method == 'POST':
        date_str = request.POST.get('appointment_date')
        if date_str:
            try:
                the_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                the_date = appt.appointment_date
    blocks = _working_hours_for_date(appt.doctor, the_date)

    if request.method == 'POST':
        form = AssignTimeForm(request.POST)
        if form.is_valid():
            new_time = form.cleaned_data['appointment_time']
            if the_date < date.today():
                messages.error(request, "You can't assign a time on a date that's already passed.")
            elif not blocks:
                messages.error(request, "The doctor has no working hours set for this date.")
            elif not _time_within_working_hours(new_time, blocks):
                hours_display = ', '.join(
                    f"{s.strftime('%I:%M %p')}–{e.strftime('%I:%M %p')}" for s, e in blocks
                )
                messages.error(request, f"That time is outside the doctor's working hours ({hours_display}).")
            else:
                with transaction.atomic():
                    doctor_conflict = Appointment.objects.select_for_update().filter(
                        doctor=appt.doctor,
                        appointment_date=the_date,
                        appointment_time=new_time,
                        status__in=['Scheduled', 'Rescheduled'],
                    ).exclude(pk=appt.pk).exists()
                    # A patient is free to have appointments with several
                    # different doctors — that's expected and allowed.
                    # What must never happen is the SAME patient ending up
                    # double-booked at the same date/time, even across two
                    # different doctors.
                    patient_conflict = Appointment.objects.select_for_update().filter(
                        patient=appt.patient,
                        appointment_date=the_date,
                        appointment_time=new_time,
                        status__in=['Scheduled', 'Rescheduled'],
                    ).exclude(pk=appt.pk).exists()
                    conflict = doctor_conflict or patient_conflict
                    if doctor_conflict:
                        messages.error(request, 'The doctor already has another appointment at that time. Choose a different time.')
                    elif patient_conflict:
                        messages.error(request, 'This patient already has another appointment at that time with a different doctor. Choose a different time.')
                    else:
                        appt.appointment_date = the_date
                        appt.appointment_time = new_time
                        appt.status = 'Scheduled'
                        appt.secretary = request.user
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
                        response = render(request, 'secretary/_assign_time_modal.html', {
                            'appt': appt, 'form': form, 'blocks': blocks,
                        })
                        response['HX-Redirect'] = '/secretary/appointments/'
                        return response
                    return redirect('secretary:appointment_list')
    else:
        form = AssignTimeForm()

    context = {'appt': appt, 'form': form, 'blocks': blocks, 'title': 'Assign Appointment Time',
               'selected_date': (the_date if request.method == 'POST' else appt.appointment_date)}
    if request.htmx:
        return render(request, 'secretary/_assign_time_modal.html', context)
    return render(request, 'secretary/assign_time.html', context)


@role_required('secretary')
def appointment_reschedule(request, pk):
    """Secretary reschedules a Scheduled appointment to a new date.
    This proactively changes the appointment date/time without requiring
    patient approval, different from patient-initiated reschedule requests."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(
        Appointment, pk=pk, status__in=['Scheduled', 'Rescheduled'], doctor=doctor
    )
    blocks = _working_hours_for_date(appt.doctor, appt.appointment_date)

    if request.method == 'POST':
        new_date_str = request.POST.get('new_date')
        new_time_str = request.POST.get('new_time')
        if not new_date_str:
            messages.error(request, 'Please select a new date.')
        else:
            from datetime import datetime
            try:
                new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date format.')
                new_date = None

            if new_date:
                new_blocks = _working_hours_for_date(appt.doctor, new_date)
                if not new_blocks:
                    messages.error(request, f"Doctor has no working hours set for {new_date.strftime('%B %d, %Y')}.")
                elif new_time_str:
                    new_time = datetime.strptime(new_time_str, '%H:%M').time()
                    if not _time_within_working_hours(new_time, new_blocks):
                        hours_display = ', '.join(
                            f"{s.strftime('%I:%M %p')}–{e.strftime('%I:%M %p')}" for s, e in new_blocks
                        )
                        messages.error(request, f"That time is outside working hours ({hours_display}).")
                    else:
                        with transaction.atomic():
                            doctor_conflict = Appointment.objects.select_for_update().filter(
                                doctor=appt.doctor,
                                appointment_date=new_date,
                                appointment_time=new_time,
                                status__in=['Scheduled', 'Rescheduled'],
                            ).exclude(pk=appt.pk).exists()
                            patient_conflict = Appointment.objects.select_for_update().filter(
                                patient=appt.patient,
                                appointment_date=new_date,
                                appointment_time=new_time,
                                status__in=['Scheduled', 'Rescheduled'],
                            ).exclude(pk=appt.pk).exists()
                            conflict = doctor_conflict or patient_conflict
                            if doctor_conflict:
                                messages.error(request, 'Doctor already has an appointment at that time.')
                            elif patient_conflict:
                                messages.error(request, 'This patient already has another appointment at that time with a different doctor.')
                            else:
                                appt.appointment_date = new_date
                                appt.appointment_time = new_time
                                appt.status = 'Rescheduled'
                                appt.secretary = request.user
                                appt.save()
                                try:
                                    send_time_assigned_email(appt)
                                except Exception:
                                    pass
                                _notify(appt.patient,
                                        f"Your appointment with Dr. {appt.doctor.get_full_name()} has been rescheduled to "
                                        f"{appt.appointment_date.strftime('%B %d, %Y')} at {appt.appointment_time.strftime('%I:%M %p')}.")
                                messages.success(request, 'Appointment rescheduled. Patient notified.')
                                if request.htmx:
                                    response = render(request, 'secretary/_appointment_action_modal.html', {'appointment': appt, 'action': 'reschedule'})
                                    response['HX-Redirect'] = '/secretary/appointments/'
                                    return response
                                return redirect('secretary:appointment_list')
                else:
                    messages.error(request, 'Please select a time.')

    context = {'appt': appt, 'title': 'Reschedule Appointment'}
    if request.htmx:
        return render(request, 'secretary/_appointment_reschedule_modal.html', context)
    return render(request, 'secretary/appointment_reschedule.html', context)


@role_required('secretary')
def appointment_confirm(request, pk):
    """Secretary confirms the patient has arrived at the hospital.
    This action is only available for 'Scheduled' appointments and moves
    the status to 'Confirmed', signalling that the patient is present,
    vital signs assessment can begin, and the doctor consultation can proceed."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment, pk=pk, status='Scheduled', doctor=doctor)
    if request.method == 'POST':
        appt.status = 'Confirmed'
        appt.secretary = request.user
        appt.save()
        _notify(appt.patient,
                f"You have been checked in for your appointment with Dr. {appt.doctor.get_full_name()} on "
                f"{appt.appointment_date.strftime('%B %d, %Y')} at "
                f"{appt.appointment_time.strftime('%I:%M %p') if appt.appointment_time else 'the scheduled time'}. "
                f"Please proceed for vital signs assessment.")
        messages.success(request, 'Patient confirmed as arrived. Vital signs assessment can now begin.')
        vitals_url = reverse('secretary:vitals_add', kwargs={'patient_id': appt.patient.pk})
        vitals_url += f'?appointment={appt.pk}'
        if request.htmx:
            response = render(request, 'secretary/_appointment_confirm_modal.html', {'appt': appt, 'action': 'confirm'})
            response['HX-Redirect'] = vitals_url
            return response
        return redirect(vitals_url)
    if request.htmx:
        return render(request, 'secretary/_appointment_confirm_modal.html', {'appt': appt, 'action': 'confirm'})
    return render(request, 'secretary/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'confirm'
    })


@role_required('secretary')
def appointment_cancel(request, pk):
    doctor = _active_doctor(request)
    appt = get_object_or_404(
        Appointment, pk=pk, status__in=['Pending Assignment', 'Scheduled'], doctor=doctor
    )
    mode = request.POST.get('mode') or request.GET.get('mode') or 'cancel'
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        # "Cancelled" = called off before the date; "No-Show" = the patient
        # simply didn't arrive for the appointment.
        appt.status = 'No-Show' if mode == 'no_show' else 'Cancelled'
        appt.secretary = request.user
        appt.save()
        try:
            send_cancellation_email(appt, reason)
        except Exception:
            pass
        if mode == 'no_show':
            _notify(appt.patient,
                    f"Your appointment with Dr. {appt.doctor.get_full_name()} on "
                    f"{appt.appointment_date.strftime('%B %d, %Y')} was marked as No-Show.")
            messages.success(request, 'Appointment marked as No-Show.')
        else:
            reason_note = f" Reason: {reason}" if reason.strip() else ''
            _notify(appt.patient,
                    f"Your appointment with Dr. {appt.doctor.get_full_name()} on "
                    f"{appt.appointment_date.strftime('%B %d, %Y')} was cancelled.{reason_note}")
            messages.success(request, 'Appointment cancelled and patient notified.')
        if request.htmx:
            response = render(request, 'secretary/_appointment_action_modal.html', {'appointment': appt, 'action': 'cancel', 'mode': mode})
            response['HX-Redirect'] = '/secretary/appointments/'
            return response
        return redirect('secretary:appointment_list')
    if request.htmx:
        return render(request, 'secretary/_appointment_action_modal.html', {'appointment': appt, 'action': 'cancel', 'mode': mode})
    return render(request, 'secretary/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'cancel', 'mode': mode
    })


@role_required('secretary')
def appointment_complete(request, pk):
    """Secretary marks a Confirmed appointment as Completed after the
    consultation has finished. Only valid from 'Confirmed' status."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment, pk=pk, status='Confirmed', doctor=doctor)
    if request.method == 'POST':
        appt.status = 'Completed'
        appt.secretary = request.user
        appt.save()
        _notify(appt.patient,
                f"Your appointment with Dr. {appt.doctor.get_full_name()} on "
                f"{appt.appointment_date.strftime('%B %d, %Y')} has been completed. "
                f"Thank you for visiting MSHFI Medical Clinic.")
        messages.success(request, 'Appointment marked as completed.')
        if request.htmx:
            response = render(request, 'secretary/_appointment_complete_modal.html', {'appt': appt})
            response['HX-Redirect'] = '/secretary/appointments/'
            return response
        return redirect('secretary:appointment_list')
    if request.htmx:
        return render(request, 'secretary/_appointment_complete_modal.html', {'appt': appt})
    return render(request, 'secretary/appointment_confirm_action.html', {
        'appointment': appt, 'action': 'complete'
    })


@role_required('secretary')
def appointment_reschedule_approve(request, pk):
    """Secretary approves a patient's pending reschedule request, scoped to
    their assigned doctor. Mirrors doctor_views' version: the new date
    becomes the appointment's date and status moves to
    'Pending Assignment' for someone to assign a time next."""

    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment, pk=pk, status='Pending Reschedule', doctor=doctor)
    if request.method == 'POST':
        appt.appointment_date = appt.requested_date
        appt.appointment_time = None
        if appt.requested_reason:
            appt.reason = appt.requested_reason
        appt.requested_date   = None
        appt.requested_time   = None
        appt.requested_reason = ''
        appt.status           = 'Pending Assignment'
        appt.secretary         = request.user
        appt.save()

        try:
            send_booking_received_email(appt)
        except Exception:
            pass
        _notify(appt.doctor,
                f"{request.user.get_full_name()} approved {appt.patient.get_full_name()}'s reschedule request to "
                f"{appt.appointment_date.strftime('%B %d, %Y')}. Awaiting time assignment.")
        _notify(appt.patient,
                f"Your reschedule request has been approved. New date: "
                f"{appt.appointment_date.strftime('%B %d, %Y')}. You'll be notified once the time is confirmed.")
        messages.success(request, 'Reschedule approved. Assign a time once ready.')
        if request.htmx:
            response = render(request, 'secretary/_reschedule_action_modal.html', {'appointment': appt, 'action': 'approve'})
            response['HX-Redirect'] = '/secretary/appointments/'
            return response
        return redirect('secretary:appointment_list')
    if request.htmx:
        return render(request, 'secretary/_reschedule_action_modal.html', {'appointment': appt, 'action': 'approve'})
    return render(request, 'secretary/reschedule_confirm_action.html', {'appointment': appt, 'action': 'approve'})


@role_required('secretary')
def appointment_reschedule_reject(request, pk):
    """Secretary rejects a patient's pending reschedule request: the
    appointment reverts to its original date/time/status, unchanged."""
    doctor = _active_doctor(request)
    appt = get_object_or_404(Appointment, pk=pk, status='Pending Reschedule', doctor=doctor)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        requested_date = appt.requested_date
        appt.requested_date   = None
        appt.requested_time   = None
        appt.requested_reason = ''
        appt.status           = 'Scheduled'
        appt.secretary         = request.user
        appt.save()
        original_time_display = (
            f" at {appt.appointment_time.strftime('%I:%M %p')}" if appt.appointment_time else ''
        )
        _notify(appt.patient,
                f"Your request to reschedule your appointment to "
                f"{requested_date.strftime('%B %d, %Y') if requested_date else ''} was declined. "
                f"{('Reason: ' + reason) if reason else ''} Your original appointment on "
                f"{appt.appointment_date.strftime('%B %d, %Y')}{original_time_display} stays as is.")
        messages.success(request, 'Reschedule request declined. Patient notified, original appointment kept.')
        if request.htmx:
            response = render(request, 'secretary/_reschedule_action_modal.html', {'appointment': appt, 'action': 'reject'})
            response['HX-Redirect'] = '/secretary/appointments/'
            return response
        return redirect('secretary:appointment_list')
    if request.htmx:
        return render(request, 'secretary/_reschedule_action_modal.html', {'appointment': appt, 'action': 'reject'})
    return render(request, 'secretary/reschedule_confirm_action.html', {'appointment': appt, 'action': 'reject'})


@role_required('secretary')
def vitals_add(request, patient_id):
    patient = _get_accessible_patient_or_deny(request, patient_id)
    if patient is None:
        return redirect('secretary:patient_list')
    from records.forms import VitalSignForm
    from records.models import VitalSign

    # When arriving from the check-in flow (?appointment=<pk>), pre-link the
    # reading to that specific visit. The pk is validated against the
    # secretary's own appointments so a tampered value can't link vitals to
    # another secretary's patient.
    initial = {'date_taken': date.today()}
    pre_linked_appointment = None
    appointment_param = request.GET.get('appointment')
    if appointment_param:
        appt = Appointment.objects.filter(
            pk=appointment_param, patient=patient, doctor=_active_doctor(request)
        ).first()
        if appt:
            initial['appointment'] = appt
            pre_linked_appointment = appt

    form = VitalSignForm(request.POST or None, initial=initial)
    form.fields['appointment'].queryset = Appointment.objects.filter(
        patient=patient, doctor=_active_doctor(request)
    ).order_by('-appointment_date')
    if request.method == 'POST' and form.is_valid():
        vital = form.save(commit=False)
        vital.patient   = patient
        vital.secretary = request.user
        # When arriving from the check-in flow the appointment comes via the
        # ?appointment= query param; the dropdown on the rendered form still
        # carries it, but a partial/tampered POST may omit it, so fall back
        # to the pre-linked appointment to keep the visit link intact.
        if vital.appointment is None and pre_linked_appointment is not None:
            vital.appointment = pre_linked_appointment
        vital.save()
        messages.success(request, 'Vital signs recorded.')
        return redirect('secretary:patient_records', patient_id=patient.pk)
    vitals = VitalSign.objects.filter(patient=patient).order_by('-date_taken')
    return render(request, 'secretary/vitals_form.html', {
        'form': form, 'patient': patient, 'vitals': vitals,
        'pre_linked_appointment': pre_linked_appointment,
    })


def _schedule_calendar_context(doctor, year=None, month=None):
    """Build the same month-grid (with inline slots) that the doctor's
    'My Schedule' calendar uses, but read-only for the secretary."""
    from calendar import month_name
    from appointments.views.doctor_views import _compute_schedule_month_with_slots
    today = date.today()
    year = year or today.year
    month = month or today.month
    return {
        'calendar_weeks': _compute_schedule_month_with_slots(doctor, year, month) if doctor else [],
        'calendar_year': year,
        'calendar_month': month,
        'calendar_month_name': month_name[month],
        'today_iso': today.isoformat(),
    }


@role_required('secretary')
def view_all_schedules(request):
    """Main 'Doctor Profile & Schedule' page: a Calendar tab (doctor
    profile/coverage card + mini calendar in the sidebar, full-height grid,
    click a day to manage its slots in a popover) and an Availability &
    Settings tab (just the recurring weekly template editor) — mirrors the
    same Calendar/Availability split doctor_views.schedule_list uses,
    adapted for the secretary's ASSIGNED/ACTIVE doctor instead of
    request.user."""
    from appointments.views.doctor_views import (
        _resolve_grid_view, _resolve_calendar_month, _compute_schedule_month,
        _week_grid_context, _day_grid_context,
    )
    doctor = _active_doctor(request)
    if doctor:
        services.sync_generated_schedule_for_doctor(doctor)

    active_tab = request.GET.get('tab')
    active_tab = active_tab if active_tab in ('calendar', 'availability') else 'calendar'
    selected_date_str = request.GET.get('date') or date.today().isoformat()

    context = {'doctor': doctor, 'active_tab': active_tab, 'selected_date': selected_date_str}

    if active_tab == 'calendar':
        try:
            anchor = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            anchor = date.today()

        # Mini-calendar month context is independent of which grid view
        # (month/week/day) is on screen, same as the doctor's page.
        year, month = _resolve_calendar_month(request, selected_date_str)
        context.update({
            'calendar_weeks': _compute_schedule_month(doctor, year, month) if doctor else [],
            'calendar_year': year, 'calendar_month': month,
            'calendar_month_name': calendar_module.month_name[month],
            'today_iso': date.today().isoformat(),
        })

        view = _resolve_grid_view(request.GET.get('view'))
        context['view'] = view
        if view == 'week':
            context.update(_week_grid_context(doctor, anchor) if doctor else {'view': 'week', 'week_days': []})
        elif view == 'day':
            context.update(_day_grid_context(doctor, anchor) if doctor else {'view': 'day', 'day_slots': []})
        else:
            context['calendar_weeks_with_slots'] = _schedule_calendar_context(doctor, year, month)['calendar_weeks']

        # Doctor profile card (sidebar, above the mini calendar): coverage
        # section needs the colleagues she can hand her doctor to, plus
        # every active coverage that involves her (she covers someone, or
        # someone covers HER doctor).
        my_doctor = _assigned_doctor(request.user)
        involvement = Q(secretary=request.user)
        if my_doctor:
            involvement |= Q(doctor=my_doctor)
        context.update({
            'primary_doctor': my_doctor,
            'colleagues': CustomUser.objects.filter(role='secretary', is_active=True)
                                            .exclude(pk=request.user.pk)
                                            .order_by('first_name', 'last_name'),
            'coverages': SecretaryCoverage.objects.filter(involvement)
                                                  .select_related('secretary', 'doctor'),
        })
    elif doctor:
        from appointments.views.doctor_views import _template_editor_context
        context.update(_template_editor_context(doctor))

    return render(request, 'secretary/schedules.html', context)


def _grid_html_for_view(request, doctor, view, anchor, oob=False):
    """Render the secretary's availability calendar in the requested view
    ('month', 'week' or 'day' — context builders shared with the doctor's
    calendar). `oob=True` marks the widget for an htmx out-of-band swap,
    used to refresh whichever view is on screen after a slot change."""
    from appointments.views.doctor_views import _week_grid_context, _day_grid_context
    context = {'doctor': doctor, 'oob': oob}
    if view == 'week':
        context.update(_week_grid_context(doctor, anchor) if doctor else {'view': 'week', 'week_days': []})
        template = 'secretary/_schedule_grid_week.html'
    elif view == 'day':
        context.update(_day_grid_context(doctor, anchor) if doctor else {'view': 'day', 'day_slots': []})
        template = 'secretary/_schedule_grid_day.html'
    else:
        context.update(_schedule_calendar_context(doctor, anchor.year, anchor.month))
        template = 'secretary/_schedule_grid_month.html'
    return render_to_string(template, context, request=request)


@role_required('secretary')
def schedule_grid_partial(request):
    """htmx endpoint: re-render the availability calendar. Month view
    navigates with ?year=&month= (Prev/Next a month at a time); week and
    day views (?view=week|day) anchor on ?date= instead."""
    doctor = _active_doctor(request)
    from appointments.views.doctor_views import _resolve_grid_view
    view = _resolve_grid_view(request.GET.get('view'))
    if view != 'month':
        anchor = _panel_date(request.GET.get('date'))
        return HttpResponse(_grid_html_for_view(request, doctor, view, anchor))
    try:
        year = int(request.GET.get('year'))
        month = int(request.GET.get('month'))
    except (TypeError, ValueError):
        today = date.today()
        year, month = today.year, today.month
    context = {'doctor': doctor}
    context.update(_schedule_calendar_context(doctor, year, month))
    return render(request, 'secretary/_schedule_grid_month.html', context)


@role_required('secretary')
def schedule_mini_calendar_partial(request):
    """Re-renders the desktop sidebar's compact 'jump to date' mini
    calendar (month nav only — day clicks navigate the main grid widget
    directly, see secretary/_schedule_mini_calendar.html). Mirrors
    doctor_views.schedule_mini_calendar_partial, scoped to the active doctor."""
    from appointments.views.doctor_views import (
        _resolve_grid_view, _resolve_calendar_month, _compute_schedule_month,
    )
    doctor = _active_doctor(request)
    selected_date_str = request.GET.get('date', '')
    view = _resolve_grid_view(request.GET.get('view'))
    year, month = _resolve_calendar_month(request, selected_date_str)
    return render(request, 'secretary/_schedule_mini_calendar.html', {
        'calendar_weeks': _compute_schedule_month(doctor, year, month) if doctor else [],
        'calendar_year': year, 'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_date': selected_date_str,
        'view': view,
    })


def _panel_date(raw):
    """Resolve the day-panel's ?date=/POSTed date to a real date, falling
    back to today for anything missing or malformed."""
    if raw:
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def _day_panel_context(doctor, the_date, *, add_form=None, edit_form=None,
                       edit_pk=None, panel_message='', grid_view='month'):
    """Context for the manage-capable Selected Day panel on the secretary's
    Doctor Profile & Schedule page. Mirrors the doctor's own day-detail
    sidebar but acts on the ASSIGNED doctor's slots. `grid_view` records
    which calendar view (month/week/day) the panel was opened from, so a
    slot change can refresh that same view. Also includes that day's
    booked appointments (read-only, listed individually) so clicking a day
    shows the same broken-out occupied times the doctor's own popover
    does, instead of just one undifferentiated availability block."""
    from appointments.views.doctor_views import _format_date_str
    panel_appts = list(
        Appointment.objects.filter(
            doctor=doctor, appointment_date=the_date, appointment_time__isnull=False,
            status__in=['Scheduled', 'Confirmed', 'Rescheduled'],
        ).select_related('patient').order_by('appointment_time')
    ) if doctor else []
    return {
        'doctor': doctor,
        'panel_date_iso': the_date.isoformat(),
        'panel_date_display': _format_date_str(the_date.isoformat()),
        'panel_slots': list(
            Schedule.objects.filter(doctor=doctor, specific_date=the_date).order_by('start_time')
        ) if doctor else [],
        'panel_appts': panel_appts,
        'panel_is_past': the_date < date.today(),
        'add_form': add_form or ScheduleForm(initial={'specific_date': the_date}),
        'edit_form': edit_form,
        'edit_pk': edit_pk,
        'panel_message': panel_message,
        'grid_view': grid_view,
    }


def _render_day_panel(request, doctor, the_date, *, with_grid_oob=False,
                      grid_view='month', **panel_kwargs):
    """Render the Selected Day panel; after a successful add/edit/delete the
    calendar grid is stale too, so ride an out-of-band swap of the grid —
    in whichever view is currently on screen — along in the same response
    (same trick the doctor's schedule page uses for its sidebar)."""
    panel_html = render_to_string(
        'secretary/_schedule_day_panel.html',
        _day_panel_context(doctor, the_date, grid_view=grid_view, **panel_kwargs),
        request=request,
    )
    if with_grid_oob:
        panel_html += _grid_html_for_view(request, doctor, grid_view, the_date, oob=True)
    return HttpResponse(panel_html)


@role_required('secretary')
def schedule_day_panel(request):
    """htmx endpoint: clicking a day on the availability calendar loads that
    day's slots with add/edit/remove controls. ?view= records which
    calendar view the click came from (month/week/day)."""
    from appointments.views.doctor_views import _resolve_grid_view
    doctor = _active_doctor(request)
    the_date = _panel_date(request.GET.get('date'))
    grid_view = _resolve_grid_view(request.GET.get('view'))
    return _render_day_panel(request, doctor, the_date, grid_view=grid_view)


@role_required('secretary')
def schedule_day_popover(request):
    """Opens the manage-capable Selected Day panel as a small popover
    anchored at the clicked day — like clicking a date in Google Calendar
    — instead of it living as a persistent sidebar panel. Every add/edit/
    delete action inside still targets #day-details by id and swaps in
    place (see schedule_slot_add/_edit/_delete), so the popover just
    updates its own content — no separate popover-specific CRUD logic."""
    from appointments.views.doctor_views import _resolve_grid_view
    doctor = _active_doctor(request)
    the_date = _panel_date(request.GET.get('date'))
    grid_view = _resolve_grid_view(request.GET.get('view'))
    return render(
        request, 'secretary/_schedule_day_popover.html',
        _day_panel_context(doctor, the_date, grid_view=grid_view),
    )


@role_required('secretary')
def schedule_slot_add(request):
    """Secretary adds a schedule slot to the ASSIGNED doctor's calendar.
    Same validation as the doctor's own Add Slot: ScheduleForm (end after
    start, no past dates) plus an overlap check against that day's
    existing slots."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    from appointments.views.doctor_views import _resolve_grid_view
    doctor = _active_doctor(request)
    the_date = _panel_date(request.POST.get('specific_date'))
    grid_view = _resolve_grid_view(request.POST.get('grid_view'))
    if not doctor:
        return _render_day_panel(request, doctor, the_date, grid_view=grid_view)
    form = ScheduleForm(request.POST)
    if form.is_valid():
        new_slot = form.save(commit=False)
        overlap = Schedule.objects.filter(
            doctor=doctor, specific_date=new_slot.specific_date,
            start_time__lt=new_slot.end_time, end_time__gt=new_slot.start_time,
        ).exists()
        if overlap:
            form.add_error(None, 'This overlaps with an existing time slot on that date.')
        else:
            new_slot.doctor = doctor
            new_slot.save()
            _notify(
                doctor,
                f"{request.user.get_full_name()} (secretary) added a schedule slot for you on "
                f"{new_slot.specific_date.strftime('%b %d, %Y')} "
                f"({new_slot.start_time.strftime('%I:%M %p')}–{new_slot.end_time.strftime('%I:%M %p')})."
            )
            return _render_day_panel(
                request, doctor, new_slot.specific_date, with_grid_oob=True,
                panel_message='Time slot added.', grid_view=grid_view,
            )
        the_date = new_slot.specific_date
    return _render_day_panel(request, doctor, the_date, add_form=form, grid_view=grid_view)


@role_required('secretary')
def schedule_slot_edit(request, pk):
    """Secretary changes the time of one of the assigned doctor's existing
    slots. The date stays fixed (hidden field) — the panel is always
    scoped to one selected day."""
    from appointments.views.doctor_views import _resolve_grid_view
    doctor = _active_doctor(request)
    slot = get_object_or_404(Schedule, pk=pk, doctor=doctor)
    if request.method == 'POST':
        grid_view = _resolve_grid_view(request.POST.get('grid_view'))
        form = ScheduleForm(request.POST, instance=slot)
        if form.is_valid():
            updated = form.save(commit=False)
            overlap = Schedule.objects.filter(
                doctor=doctor, specific_date=updated.specific_date,
                start_time__lt=updated.end_time, end_time__gt=updated.start_time,
            ).exclude(pk=pk).exists()
            if overlap:
                form.add_error(None, 'This overlaps with an existing time slot on that date.')
            else:
                old_start, old_end = slot.start_time, slot.end_time
                updated.save()
                _notify(
                    doctor,
                    f"{request.user.get_full_name()} (secretary) updated your schedule slot on "
                    f"{updated.specific_date.strftime('%b %d, %Y')}: "
                    f"{old_start.strftime('%I:%M %p')}–{old_end.strftime('%I:%M %p')} is now "
                    f"{updated.start_time.strftime('%I:%M %p')}–{updated.end_time.strftime('%I:%M %p')}."
                )
                return _render_day_panel(
                    request, doctor, updated.specific_date, with_grid_oob=True,
                    panel_message='Time slot updated.', grid_view=grid_view,
                )
        return _render_day_panel(request, doctor, slot.specific_date,
                                 edit_form=form, edit_pk=pk, grid_view=grid_view)
    # GET: re-render the panel with this slot's row swapped for an inline
    # edit form.
    grid_view = _resolve_grid_view(request.GET.get('view'))
    form = ScheduleForm(instance=slot)
    return _render_day_panel(request, doctor, slot.specific_date,
                             edit_form=form, edit_pk=pk, grid_view=grid_view)


@role_required('secretary')
def schedule_slot_delete(request, pk):
    """Secretary removes one of the assigned doctor's schedule slots
    (confirmation happens client-side via hx-confirm)."""
    from appointments.views.doctor_views import _resolve_grid_view
    doctor = _active_doctor(request)
    slot = get_object_or_404(Schedule, pk=pk, doctor=doctor)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    grid_view = _resolve_grid_view(request.POST.get('grid_view'))
    removed_date, removed_start, removed_end = slot.specific_date, slot.start_time, slot.end_time
    slot.delete()
    _notify(
        doctor,
        f"{request.user.get_full_name()} (secretary) removed your schedule slot on "
        f"{removed_date.strftime('%b %d, %Y')} "
        f"({removed_start.strftime('%I:%M %p')}–{removed_end.strftime('%I:%M %p')})."
    )
    return _render_day_panel(
        request, doctor, removed_date, with_grid_oob=True,
        panel_message='Time slot removed.', grid_view=grid_view,
    )


@role_required('secretary')
def schedule_settings(request):
    """Secretary version of the doctor's derived-booking-rules settings —
    acts on the assigned/active doctor, mirrors doctor_views.schedule_settings."""
    doctor = _active_doctor(request)
    if not doctor:
        return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")
    settings_row = DoctorScheduleSettings.for_doctor(doctor)
    if request.method == 'POST':
        form = DoctorScheduleSettingsForm(request.POST, instance=settings_row)
        if form.is_valid():
            form.save()
            services.sync_generated_schedule_for_doctor(doctor, force=True)
            _notify(doctor, f"{request.user.get_full_name()} (secretary) updated your scheduling settings.")
            messages.success(request, 'Schedule settings updated.')
            if request.htmx:
                response = render(request, 'secretary/_schedule_settings_modal.html', {'form': form, 'doctor': doctor})
                response['HX-Redirect'] = reverse('secretary:schedule_view') + '?tab=availability'
                return response
            return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")
    else:
        form = DoctorScheduleSettingsForm(instance=settings_row)

    context = {'form': form, 'doctor': doctor, 'title': 'Schedule Settings'}
    if request.htmx:
        return render(request, 'secretary/_schedule_settings_modal.html', context)
    return render(request, 'secretary/schedule_settings_form.html', context)


@role_required('secretary')
def schedule_template_add(request):
    """Secretary adds a recurring weekly block to the active doctor's
    'Repeat weekly' template. Mirrors doctor_views.schedule_template_add."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    doctor = _active_doctor(request)
    if not doctor:
        return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")
    form = ScheduleTemplateForm(request.POST)
    if form.is_valid():
        new_block = form.save(commit=False)
        overlap = ScheduleTemplate.objects.filter(
            doctor=doctor, weekday=new_block.weekday,
            start_time__lt=new_block.end_time, end_time__gt=new_block.start_time,
        ).exists()
        if overlap:
            messages.error(request, 'That overlaps with an existing block on that day of the week.')
        else:
            new_block.doctor = doctor
            new_block.save()
            services.sync_generated_schedule_for_doctor(doctor, force=True)
            _notify(
                doctor,
                f"{request.user.get_full_name()} (secretary) updated your weekly availability template "
                f"({new_block.get_weekday_display()} {new_block.start_time.strftime('%I:%M %p')}"
                f"–{new_block.end_time.strftime('%I:%M %p')})."
            )
            messages.success(request, f'Added to {new_block.get_weekday_display()}.')
    else:
        messages.error(request, 'End time must be after start time.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('secretary:schedule_view') + '?tab=availability'
        return response
    return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")


@role_required('secretary')
def schedule_template_delete(request, pk):
    """Mirrors doctor_views.schedule_template_delete, scoped to the active doctor."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    doctor = _active_doctor(request)
    block = get_object_or_404(ScheduleTemplate, pk=pk, doctor=doctor)
    weekday_display = block.get_weekday_display()
    block.delete()
    services.sync_generated_schedule_for_doctor(doctor, force=True)
    _notify(doctor, f"{request.user.get_full_name()} (secretary) removed a weekly availability block on {weekday_display}.")
    messages.success(request, f'Removed from {weekday_display}.')
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('secretary:schedule_view') + '?tab=availability'
        return response
    return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")


@role_required('secretary')
def schedule_template_duplicate(request):
    """Mirrors doctor_views.schedule_template_duplicate, scoped to the active doctor."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    doctor = _active_doctor(request)
    if not doctor:
        return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")
    try:
        source_weekday = int(request.POST.get('source_weekday', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid source day.')
        return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")

    target_weekdays = []
    for raw in request.POST.getlist('target_weekdays'):
        try:
            target_weekdays.append(int(raw))
        except (TypeError, ValueError):
            continue

    source_blocks = list(ScheduleTemplate.objects.filter(doctor=doctor, weekday=source_weekday))
    if not source_blocks:
        messages.error(request, 'That day has no blocks to duplicate.')
    else:
        copied_to = []
        for target in target_weekdays:
            if target == source_weekday:
                continue
            for block in source_blocks:
                overlap = ScheduleTemplate.objects.filter(
                    doctor=doctor, weekday=target,
                    start_time__lt=block.end_time, end_time__gt=block.start_time,
                ).exists()
                if not overlap:
                    ScheduleTemplate.objects.create(
                        doctor=doctor, weekday=target,
                        start_time=block.start_time, end_time=block.end_time,
                    )
                    if target not in copied_to:
                        copied_to.append(target)
        if copied_to:
            services.sync_generated_schedule_for_doctor(doctor, force=True)
            names = ', '.join(dict(ScheduleTemplate.WEEKDAY_CHOICES)[w] for w in copied_to)
            _notify(doctor, f"{request.user.get_full_name()} (secretary) duplicated weekly availability to {names}.")
            messages.success(request, f'Duplicated to {names}.')
        else:
            messages.error(request, 'Nothing was duplicated — every target day already had a conflicting block.')

    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = reverse('secretary:schedule_view') + '?tab=availability'
        return response
    return redirect(f"{reverse('secretary:schedule_view')}?tab=availability")


def _accessible_patient_ids(request):
    """Patients the secretary may see: only those who have (or had) an
    appointment with the doctor she's currently working as."""
    doctor = _active_doctor(request)
    if not doctor:
        return Appointment.objects.none().values_list('patient_id', flat=True)
    return Appointment.objects.filter(doctor=doctor).values_list('patient_id', flat=True).distinct()


def _get_accessible_patient_or_deny(request, patient_id):
    """Fetch a patient only if they belong to the secretary's active
    doctor; otherwise return None (caller redirects with an error)."""
    patient = get_object_or_404(CustomUser, pk=patient_id, role='patient')
    if patient.pk not in set(_accessible_patient_ids(request)):
        messages.error(request, 'You do not have access to this patient.')
        return None
    return patient


@role_required('secretary')
def secretary_patient_list(request):
    search = request.GET.get('q', '')
    patients = CustomUser.objects.filter(role='patient', pk__in=_accessible_patient_ids(request))
    if search:
        patients = patients.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search)
        )
    return render(request, 'secretary/patient_list.html', {
        'patients': patients.distinct(), 'search': search
    })


@role_required('secretary')
def walkin_register(request):
    """Registers a patient who walked in with no account, generating them
    a temporary login (see WalkInPatientForm), and checks them straight
    into an appointment with the secretary's active doctor — mirroring
    what appointment_confirm does for a normally-scheduled check-in."""
    doctor = _active_doctor(request)
    form = WalkInPatientForm(request.POST or None)
    if request.method == 'POST' and doctor and form.is_valid():
        with transaction.atomic():
            user, temp_password = form.save()
            appt = Appointment.objects.create(
                patient=user,
                doctor=doctor,
                secretary=request.user,
                appointment_date=date.today(),
                appointment_time=None,
                status='Confirmed',
                reason=form.cleaned_data['reason'],
            )
        _notify(doctor, f"{request.user.get_full_name()} (secretary) checked in a walk-in patient: {user.get_full_name()}.")
        vitals_url = reverse('secretary:vitals_add', kwargs={'patient_id': user.pk})
        vitals_url += f'?appointment={appt.pk}'
        context = {
            'patient': user, 'username': user.username, 'temp_password': temp_password, 'vitals_url': vitals_url,
            'title': 'Patient Registered & Checked In',
        }
        template = 'secretary/_walkin_credentials_modal.html' if request.htmx else 'secretary/walkin_credentials.html'
        return render(request, template, context)

    context = {
        'form': form, 'assigned_doctor': doctor,
        'title': 'Register Walk-In Patient',
    }
    template = 'secretary/_walkin_register_modal.html' if request.htmx else 'secretary/walkin_register.html'
    return render(request, template, context)


@role_required('secretary')
def patient_quickview(request, patient_id):
    patient = _get_accessible_patient_or_deny(request, patient_id)
    if patient is None:
        return redirect('secretary:patient_list')
    profile = getattr(patient, 'patient_profile', None)
    last_visit = Appointment.objects.filter(patient=patient).order_by('-appointment_date').first()
    return render(request, 'secretary/_patient_quickview_modal.html', {
        'patient': patient, 'profile': profile, 'last_visit': last_visit, 'title': 'Patient Summary',
    })


@role_required('secretary')
def secretary_patient_records(request, patient_id):
    patient = _get_accessible_patient_or_deny(request, patient_id)
    if patient is None:
        return redirect('secretary:patient_list')
    from records.models import MedicalRecords
    from records.views import partition_vitals
    records = MedicalRecords.objects.filter(patient=patient).select_related('results', 'doctor')
    visit_vitals, general_vitals = partition_vitals(patient, records)
    appts   = Appointment.objects.filter(patient=patient).select_related('doctor').order_by('-appointment_date')
    profile = getattr(patient, 'patient_profile', None)
    return render(request, 'secretary/patient_records.html', {
        'patient': patient, 'records': records,
        'visit_vitals': visit_vitals, 'general_vitals': general_vitals,
        'appts': appts, 'profile': profile,
    })


@role_required('secretary')
def secretary_notifications(request):
    return redirect('/notifications/')


@role_required('secretary')
def get_occupied_times(request, pk):
    """API endpoint returning occupied appointment times for a doctor on a
    specific date. Accepts an optional '?date=YYYY-MM-DD' to look up a date
    other than the appointment's currently-requested one (used by the date
    picker the assign-time modal now offers). Returns JSON with:
    {'occupied_times': [{'time': 'HH:MM', 'patient': 'Name', 'status': ...}],
     'patient_conflicts': [...], 'blocks': ['HH:MM-HH:MM', ...],
     'is_past': bool, 'has_schedule': bool, 'date': 'YYYY-MM-DD'}"""
    doctor = _active_doctor(request)
    appt = get_object_or_404(
        Appointment, pk=pk, doctor=doctor, status__in=['Pending Assignment', 'Scheduled', 'Rescheduled']
    )

    # Resolve the date being inspected: explicit ?date= param, else the
    # appointment's current date. Invalid input falls back to the default.
    the_date = appt.appointment_date
    date_param = request.GET.get('date')
    if date_param:
        try:
            the_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            the_date = appt.appointment_date

    occupied = Appointment.objects.filter(
        doctor=appt.doctor,
        appointment_date=the_date,
        appointment_time__isnull=False,
        status__in=['Scheduled', 'Rescheduled', 'Confirmed'],
    ).exclude(pk=appt.pk).select_related('patient').values_list(
        'appointment_time', 'patient__first_name', 'patient__last_name', 'status'
    ).order_by('appointment_time')

    occupied_list = [
        {
            'time': time.strftime('%H:%M'),
            'time_display': time.strftime('%I:%M %p'),
            'patient': f"{first_name} {last_name}",
            'status': status,
        }
        for time, first_name, last_name, status in occupied
    ]

    # Times where THIS patient is already booked with a different doctor —
    # mirrors the patient_conflict check in assign_appointment_time so the
    # slot grid can flag the conflict before the form is ever submitted.
    patient_conflicts = Appointment.objects.filter(
        patient=appt.patient,
        appointment_date=the_date,
        appointment_time__isnull=False,
        status__in=['Scheduled', 'Rescheduled'],
    ).exclude(pk=appt.pk).exclude(doctor=appt.doctor).select_related('doctor').values_list(
        'appointment_time', 'doctor__first_name', 'doctor__last_name', 'status'
    ).order_by('appointment_time')

    patient_conflict_list = [
        {
            'time': time.strftime('%H:%M'),
            'time_display': time.strftime('%I:%M %p'),
            'doctor': f"Dr. {first_name} {last_name}",
            'status': status,
        }
        for time, first_name, last_name, status in patient_conflicts
    ]

    blocks = _working_hours_for_date(appt.doctor, the_date)
    return JsonResponse({
        'occupied_times': occupied_list,
        'patient_conflicts': patient_conflict_list,
        'blocks': [
            f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in blocks
        ],
        'is_past': the_date < date.today(),
        'has_schedule': bool(blocks),
        'date': the_date.strftime('%Y-%m-%d'),
        'appointment_id': pk,
    })


@role_required('secretary')
def switch_doctor(request):
    """Top-bar doctor switcher: sets which of the secretary's doctors
    (primary + covered) her pages currently operate on. The selection only
    sticks if the doctor is actually in her allowed set."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        doctor_id = int(request.POST.get('doctor_id', ''))
    except (TypeError, ValueError):
        doctor_id = None
    if doctor_id in {d.pk for d in doctors_for_secretary(request.user)}:
        request.session[ACTIVE_DOCTOR_SESSION_KEY] = doctor_id
    else:
        messages.error(request, "You can only switch to a doctor you're assigned to or covering.")
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('secretary:dashboard')
    return redirect(next_url)


@role_required('secretary')
def coverage_add(request):
    """Secretary hands her OWN primary doctor over to a colleague (e.g.
    before going on leave), so the colleague temporarily manages that
    doctor too. Admins have their own unrestricted endpoint in
    admin_views.coverage_add."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    my_doctor = _assigned_doctor(request.user)
    if not my_doctor:
        messages.error(request, 'You have no assigned doctor to hand over.')
        return redirect('secretary:schedule_view')
    colleague = CustomUser.objects.filter(
        role='secretary', is_active=True, pk=request.POST.get('secretary_id'),
    ).exclude(pk=request.user.pk).first()
    if not colleague:
        messages.error(request, 'Please select a valid colleague to cover your doctor.')
        return redirect('secretary:schedule_view')
    if _assigned_doctor(colleague) == my_doctor:
        messages.info(request, f'{colleague.get_full_name()} is already assigned to Dr. {my_doctor.get_full_name()}.')
        return redirect('secretary:schedule_view')
    coverage, created = SecretaryCoverage.objects.get_or_create(
        secretary=colleague, doctor=my_doctor,
        defaults={'created_by': request.user},
    )
    if created:
        _notify(colleague, (
            f"You are now covering Dr. {my_doctor.get_full_name()}'s appointments "
            f"(handed over by {request.user.get_full_name()}). Use the doctor "
            f"switcher in your top bar to manage them."
        ))
        _notify(my_doctor, (
            f"{colleague.get_full_name()} will also manage your appointments "
            f"while {request.user.get_full_name()} is away."
        ))
        messages.success(request, f'Dr. {my_doctor.get_full_name()} is now also covered by {colleague.get_full_name()}.')
    else:
        messages.info(request, f'{colleague.get_full_name()} is already covering Dr. {my_doctor.get_full_name()}.')
    return redirect('secretary:schedule_view')


@role_required('secretary')
def coverage_remove(request, pk):
    """Ends a coverage the secretary is involved in: either she is the one
    covering, or the covered doctor is her own primary doctor."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    coverage = get_object_or_404(SecretaryCoverage, pk=pk)
    my_doctor = _assigned_doctor(request.user)
    involves_me = (
        coverage.secretary_id == request.user.pk
        or (my_doctor is not None and coverage.doctor_id == my_doctor.pk)
    )
    if not involves_me:
        messages.error(request, 'You can only end coverage that involves you or your doctor.')
        return redirect('secretary:schedule_view')
    covering_secretary, covered_doctor = coverage.secretary, coverage.doctor
    coverage.delete()
    if covering_secretary != request.user:
        _notify(covering_secretary, f"You are no longer covering Dr. {covered_doctor.get_full_name()}'s appointments.")
    _notify(covered_doctor, f"{covering_secretary.get_full_name()} no longer covers your appointments.")
    messages.success(request, f'{covering_secretary.get_full_name()} no longer covers Dr. {covered_doctor.get_full_name()}.')
    return redirect('secretary:schedule_view')
