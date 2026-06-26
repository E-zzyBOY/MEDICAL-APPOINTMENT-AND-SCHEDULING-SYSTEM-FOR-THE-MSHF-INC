from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from datetime import date, datetime, timedelta
import calendar as calendar_module
from accounts.decorators import role_required
from appointments.models import Appointment, Schedule, AppointmentPatientDetails
from appointments.forms import PatientDetailsForm
from accounts.models import CustomUser, PatientProfile, TERMS_VERSION
from notifications.email_utils import (
    send_booking_confirmation_email, send_cancellation_email, send_reschedule_email
)
from notifications.models import Notification


def _notify(user, message):
    Notification.objects.create(user=user, message=message)


def _compute_month_availability(doctor, year, month):
    """Build a day-by-day availability map for one calendar month, used to
    color the booking calendar green (open slots), red (no schedule on
    this exact date, or every slot already booked), or past (unselectable).

    Returns a list of week rows; each cell is either None (padding outside
    the month) or a dict: {day, date, status} where status is one of
    'available', 'unavailable', 'past'.
    """
    today = date.today()
    first_weekday, days_in_month = calendar_module.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end   = date(year, month, days_in_month)

    # How many 30-min slots does this doctor offer on each specific date
    # this month (across all schedule blocks for that date)?
    schedule_blocks = list(
        Schedule.objects.filter(
            doctor=doctor, specific_date__gte=month_start, specific_date__lte=month_end
        )
    )
    slots_per_date = {}
    for block in schedule_blocks:
        count = 0
        current = datetime.combine(block.specific_date, block.start_time)
        end     = datetime.combine(block.specific_date, block.end_time)
        while current < end:
            count += 1
            current += timedelta(minutes=30)
        slots_per_date[block.specific_date] = slots_per_date.get(block.specific_date, 0) + count
    working_dates = set(slots_per_date.keys())

    # One query for every booked slot this month, bucketed by date, instead
    # of a separate query per day.
    booked_counts = {}
    if working_dates:
        booked_rows = (
            Appointment.objects.filter(
                doctor=doctor,
                appointment_date__gte=month_start,
                appointment_date__lte=month_end,
                status__in=['Scheduled', 'Rescheduled'],
            )
            .values_list('appointment_date', flat=True)
        )
        for d in booked_rows:
            booked_counts[d] = booked_counts.get(d, 0) + 1

    weeks = []
    week = [None] * first_weekday
    for day_num in range(1, days_in_month + 1):
        current_date = date(year, month, day_num)
        if current_date < today:
            status = 'past'
        elif current_date not in working_dates:
            status = 'unavailable'
        elif booked_counts.get(current_date, 0) >= slots_per_date[current_date]:
            status = 'unavailable'
        else:
            status = 'available'
        week.append({'day': day_num, 'date': current_date.isoformat(), 'status': status})
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)

    return weeks


def _build_patient_dashboard_data(request):
    upcoming = Appointment.objects.filter(
        patient=request.user,
        status__in=['Scheduled', 'Rescheduled', 'Pending Reschedule'],
        appointment_date__gte=date.today()
    ).select_related('doctor')[:5]
    past = Appointment.objects.filter(
        patient=request.user,
        status__in=['Completed', 'Cancelled']
    ).select_related('doctor', 'results')[:5]

    return {
        'userName': request.user.get_full_name() or request.user.username,
        'stats': [
            {'label': 'Upcoming Appointments', 'value': upcoming.count()},
            {'label': 'Past Appointments', 'value': past.count()},
        ],
        'appointmentsTitle': 'Upcoming Appointments',
        'appointmentsHref': '/patient/appointments/#upcoming-appointments',
        'appointments': [
            {
                'primary': f'Dr. {a.doctor.get_full_name()}',
                'secondary': a.reason or '',
                'date': a.appointment_date.isoformat(),
                'time': a.appointment_time.strftime('%H:%M'),
                'status': a.status,
            }
            for a in upcoming
        ],
        'pastAppointmentsTitle': 'Recent Past Appointments',
        'pastAppointmentsHref': '/patient/appointments/#past-appointments',
        'pastAppointments': [
            {
                'primary': f'Dr. {a.doctor.get_full_name()}',
                'secondary': (
                    getattr(a.results, 'diagnosis', '') if a.status == 'Completed' else ''
                ) or ('Pending' if a.status == 'Completed' else ''),
                'date': a.appointment_date.isoformat(),
                'status': a.status,
            }
            for a in past
        ],
        'quickActions': [
            {'title': 'Book Appointment', 'description': 'Schedule a new visit', 'href': '/patient/appointments/book/'},
            {'title': 'My Appointments', 'description': 'View upcoming & past', 'href': '/patient/appointments/'},
            {'title': 'Medical Records', 'description': 'View your health history', 'href': '/patient/records/'},
        ],
    }


@role_required('patient')
def patient_dashboard(request):
    dashboard_data = _build_patient_dashboard_data(request)
    return render(request, 'patient/dashboard.html', {'dashboard_data': dashboard_data})


@role_required('patient')
def patient_dashboard_data(request):
    return JsonResponse(_build_patient_dashboard_data(request))


@role_required('patient')
def appointment_list(request):
    upcoming = Appointment.objects.filter(
        patient=request.user,
        appointment_date__gte=date.today()
    ).exclude(status='Cancelled').select_related('doctor').order_by('appointment_date', 'appointment_time')
    past = Appointment.objects.filter(
        patient=request.user,
        appointment_date__lt=date.today()
    ).select_related('doctor', 'results').order_by('-appointment_date')
    cancelled = Appointment.objects.filter(
        patient=request.user,
        status='Cancelled'
    ).select_related('doctor').order_by('-appointment_date')
    return render(request, 'patient/appointment_list.html', {
        'upcoming': upcoming, 'past': past, 'cancelled': cancelled
    })


@role_required('patient')
def book_step1(request):
    doctors = CustomUser.objects.filter(role='doctor').select_related('doctor_profile')
    return render(request, 'patient/book_step1.html', {'doctors': doctors})


@role_required('patient')
def doctor_profile_view(request, doctor_id):
    doctor = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
    schedules = Schedule.objects.filter(
        doctor=doctor, specific_date__gte=date.today()
    ).order_by('specific_date', 'start_time')
    context = {'doctor': doctor, 'schedules': schedules, 'title': 'Doctor Profile'}
    if request.htmx:
        return render(request, 'patient/_doctor_profile_modal.html', context)
    return render(request, 'patient/doctor_profile.html', context)


def _format_date_str(selected_date_str):
    """Safely turn a 'YYYY-MM-DD' string into a display-friendly date, e.g.
    'Jun 29, 2026'. Django's |date template filter can't parse plain
    strings, so this is done in Python before reaching the template.
    Avoids the '%-d' / '%e' no-leading-zero strftime extensions since
    they aren't supported on Windows, which this project also runs on."""
    if not selected_date_str:
        return ''
    try:
        d = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except ValueError:
        return selected_date_str


def _format_time_str(selected_time_str):
    """Same idea as _format_date_str but for a 'HH:MM:SS' time string,
    e.g. '09:00:00' -> '9:00 AM'."""
    if not selected_time_str:
        return ''
    try:
        t = datetime.strptime(selected_time_str, '%H:%M:%S').time()
        return t.strftime('%I:%M %p').lstrip('0')
    except ValueError:
        return selected_time_str


def _compute_slots(doctor, selected_date_str):
    slots = []
    error = None

    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            return [], 'Invalid date format.', selected_date_str

        if selected_date < date.today():
            error = 'Cannot book an appointment in the past.'
        else:
            schedule_blocks = Schedule.objects.filter(doctor=doctor, specific_date=selected_date)
            if not schedule_blocks.exists():
                error = 'The selected doctor has no schedule on this date.'
            else:
                booked_times = set(
                    Appointment.objects.filter(
                        doctor=doctor,
                        appointment_date=selected_date,
                        status__in=['Scheduled', 'Rescheduled']
                    ).values_list('appointment_time', flat=True)
                )
                for block in schedule_blocks:
                    current = datetime.combine(selected_date, block.start_time)
                    end     = datetime.combine(selected_date, block.end_time)
                    while current < end:
                        t = current.time()
                        slots.append({'time': t, 'available': t not in booked_times})
                        current += timedelta(minutes=30)

    return slots, error, selected_date_str


def _resolve_calendar_month(request, selected_date_str):
    """Decide which year/month the calendar grid should show: an explicit
    ?year=&month= from month-navigation clicks takes priority, then the
    month containing the currently selected date, then today's month."""
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


@role_required('patient')
def book_step2_slots(request, doctor_id):
    doctor = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
    selected_date_str = request.GET.get('date', '')
    slots, error, selected_date_str = _compute_slots(doctor, selected_date_str)
    year, month = _resolve_calendar_month(request, selected_date_str)
    calendar_weeks = _compute_month_availability(doctor, year, month)

    context = {
        'doctor': doctor,
        'slots': slots,
        'selected_date': selected_date_str,
        'selected_date_display': _format_date_str(selected_date_str),
        'error': error,
        'title': 'Choose a Time Slot',
        'calendar_weeks': calendar_weeks,
        'calendar_year': year,
        'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
    }
    if request.htmx:
        return render(request, 'patient/_book_step2_modal.html', context)
    return render(request, 'patient/book_step2_slots.html', context)


@role_required('patient')
def book_step2_slots_partial(request, doctor_id):
    doctor = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
    selected_date_str = request.GET.get('date', '')
    slots, error, selected_date_str = _compute_slots(doctor, selected_date_str)
    year, month = _resolve_calendar_month(request, selected_date_str)
    calendar_weeks = _compute_month_availability(doctor, year, month)
    return render(request, 'patient/_slot_grid_fragment.html', {
        'doctor': doctor, 'slots': slots, 'selected_date': selected_date_str,
        'selected_date_display': _format_date_str(selected_date_str),
        'error': error,
        'calendar_weeks': calendar_weeks,
        'calendar_year': year,
        'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'oob_calendar': True,
    })


@role_required('patient')
def book_step2_calendar_partial(request, doctor_id):
    """Re-renders just the calendar grid when the patient clicks the prev/next
    month arrows, without touching the (now stale) time-slot grid below it."""
    doctor = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
    year, month = _resolve_calendar_month(request, '')
    calendar_weeks = _compute_month_availability(doctor, year, month)
    return render(request, 'patient/_calendar_widget_fragment.html', {
        'doctor': doctor,
        'calendar_weeks': calendar_weeks,
        'calendar_year': year,
        'calendar_month': month,
        'calendar_month_name': calendar_module.month_name[month],
        'today_iso': date.today().isoformat(),
        'selected_date': request.GET.get('selected_date', ''),
    })


def _patient_details_initial(user):
    """Builds initial form data for the Patient Details step from whatever
    the logged-in patient already has on file. Missing fields are simply
    left blank so the patient fills them in once and (per the spec) only
    has to type the chief complaint if everything else is already complete."""
    profile = getattr(user, 'patient_profile', None)
    initial = {
        'first_name':  user.first_name,
        'last_name':   user.last_name,
        'email':       user.email,
    }
    if profile:
        initial.update({
            'middle_name':   profile.middle_name,
            'date_of_birth': profile.date_of_birth,
            'gender':        profile.gender,
            'address':       profile.address,
            'mobile_number': profile.contact_number,
        })
    return initial


def _apply_patient_details_to_profile(user, cleaned_data):
    """Writes the editable identity/contact fields back onto the live
    CustomUser / PatientProfile, per the spec's requirement that the
    patient's profile stays in sync with anything changed during booking.
    Does not touch chief_complaint or terms_accepted — those are
    per-appointment, not part of the profile."""
    user.first_name = cleaned_data['first_name']
    user.last_name  = cleaned_data['last_name']
    if cleaned_data.get('email'):
        user.email = cleaned_data['email']
    user.save(update_fields=['first_name', 'last_name', 'email'])

    profile, _created = PatientProfile.objects.get_or_create(user=user)
    profile.middle_name    = cleaned_data.get('middle_name', '')
    profile.date_of_birth  = cleaned_data['date_of_birth']
    profile.gender         = cleaned_data['gender']
    profile.address        = cleaned_data['address']
    profile.contact_number = cleaned_data['mobile_number']
    profile.save()


def _patient_already_consented(user):
    profile = getattr(user, 'patient_profile', None)
    return bool(
        profile and profile.terms_accepted_at and profile.terms_accepted_version == TERMS_VERSION
    )


@role_required('patient')
def book_step4_details(request, doctor_id):
    """Step 4 of booking: Patient Details. Sits between slot selection and
    the review/confirm step. Nothing is written to the database here —
    validated field values are carried forward as hidden form fields into
    the review step, where the actual Appointment row (and the permanent
    AppointmentPatientDetails snapshot) gets created on final confirm."""
    doctor = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
    appointment_date = request.POST.get('appointment_date') or request.GET.get('appointment_date', '')
    appointment_time = request.POST.get('appointment_time') or request.GET.get('appointment_time', '')

    if not (appointment_date and appointment_time):
        # Can't proceed without knowing which slot this is for.
        return redirect('patient:book_step2', doctor_id=doctor.pk)

    already_consented = _patient_already_consented(request.user)

    if request.method == 'POST':
        form = PatientDetailsForm(request.POST)
        # If the patient already has valid consent on file, don't force a
        # re-check on every booking — but if they're a first-time/legacy
        # patient or the policy version changed, the box is required.
        if already_consented:
            form.fields['terms_accepted'].required = False
        if form.is_valid():
            context = {
                'doctor': doctor,
                'appointment_date': appointment_date,
                'appointment_time': appointment_time,
                'details': form.cleaned_data,
                'already_consented': already_consented,
                'title': 'Review Appointment',
            }
            if request.htmx:
                return render(request, 'patient/_book_step3_modal.html', context)
            return render(request, 'patient/book_step3_confirm.html', context)
        # Validation failed — redisplay with errors AND whatever the patient
        # already typed (Django forms keep submitted values automatically).
        messages.error(request, 'Please complete all required fields before continuing.')
    else:
        form = PatientDetailsForm(initial=_patient_details_initial(request.user))

    context = {
        'doctor': doctor,
        'appointment_date': appointment_date,
        'appointment_time': appointment_time,
        'appointment_time_display': _format_time_str(appointment_time),
        'form': form,
        'already_consented': already_consented,
        'title': 'Patient Details',
    }
    if request.htmx:
        return render(request, 'patient/_book_step4_modal.html', context)
    return render(request, 'patient/book_step4_details.html', context)


@role_required('patient')
def book_step3_confirm(request):
    if request.method == 'POST':
        doctor_id  = request.POST.get('doctor_id')
        date_str   = request.POST.get('appointment_date')
        time_str   = request.POST.get('appointment_time')

        try:
            doctor           = get_object_or_404(CustomUser, pk=doctor_id, role='doctor')
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time_str, '%H:%M:%S').time()
        except (ValueError, TypeError):
            messages.error(request, 'Invalid booking data. Please try again.')
            return redirect('patient:book_step1')

        # Re-validate the patient-details fields here too, server-side —
        # the review screen only carries these as hidden inputs, so a
        # tampered or replayed POST must not be able to skip Step 4's
        # validation (required fields, DOB not in the future, mobile
        # number format, T&C checkbox).
        already_consented = _patient_already_consented(request.user)
        form = PatientDetailsForm(request.POST)
        if already_consented:
            form.fields['terms_accepted'].required = False
        if not form.is_valid():
            messages.error(request, 'Some patient details are missing or invalid. Please review and try again.')
            response_ctx = {
                'doctor': doctor,
                'appointment_date': date_str,
                'appointment_time': time_str,
                'appointment_time_display': _format_time_str(time_str),
                'form': form,
                'already_consented': already_consented,
                'title': 'Patient Details',
            }
            if request.htmx:
                return render(request, 'patient/_book_step4_modal.html', response_ctx)
            return render(request, 'patient/book_step4_details.html', response_ctx)

        details = form.cleaned_data

        with transaction.atomic():
            doctor_conflict = Appointment.objects.select_for_update().filter(
                doctor=doctor,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                status__in=['Scheduled', 'Rescheduled']
            ).exists()
            if doctor_conflict:
                messages.error(request, 'This time slot was just taken. Please choose another.')
                if request.htmx:
                    slots, _ignored_error, selected_date_str = _compute_slots(doctor, date_str)
                    return render(request, 'patient/_book_step2_modal.html', {
                        'doctor': doctor, 'slots': slots, 'selected_date': selected_date_str,
                        'error': 'This time slot was just taken. Please choose another.',
                        'title': 'Choose a Time Slot',
                    })
                return redirect('patient:book_step2', doctor_id=doctor.pk)

            # A patient can only have one active appointment at a given
            # date/time, even across different doctors — checked separately
            # from the doctor-scoped conflict above so the two cases can
            # show a message that actually explains what happened.
            patient_conflict = Appointment.objects.select_for_update().filter(
                patient=request.user,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                status__in=['Scheduled', 'Rescheduled']
            ).exists()
            if patient_conflict:
                error_msg = 'You already have an appointment at this date and time. Please choose another.'
                messages.error(request, error_msg)
                if request.htmx:
                    slots, _ignored_error, selected_date_str = _compute_slots(doctor, date_str)
                    return render(request, 'patient/_book_step2_modal.html', {
                        'doctor': doctor, 'slots': slots, 'selected_date': selected_date_str,
                        'error': error_msg,
                        'title': 'Choose a Time Slot',
                    })
                return redirect('patient:book_step2', doctor_id=doctor.pk)

            appointment = Appointment.objects.create(
                patient          = request.user,
                doctor           = doctor,
                appointment_date = appointment_date,
                appointment_time = appointment_time,
                status           = 'Scheduled',
                reason           = details['reason'],
            )

            terms_timestamp = timezone.now()
            AppointmentPatientDetails.objects.create(
                appointment      = appointment,
                first_name       = details['first_name'],
                middle_name      = details.get('middle_name', ''),
                last_name        = details['last_name'],
                date_of_birth    = details['date_of_birth'],
                gender           = details['gender'],
                address          = details['address'],
                mobile_number    = details['mobile_number'],
                email            = details.get('email', ''),
                chief_complaint  = details['reason'],
                terms_accepted_at = terms_timestamp,
            )

            _apply_patient_details_to_profile(request.user, details)
            if not already_consented:
                profile = request.user.patient_profile
                profile.terms_accepted_at      = terms_timestamp
                profile.terms_accepted_version = TERMS_VERSION
                profile.save(update_fields=['terms_accepted_at', 'terms_accepted_version'])

        try:
            send_booking_confirmation_email(appointment)
        except Exception:
            pass
        _notify(request.user,
                f"Your appointment with Dr. {doctor.get_full_name()} on "
                f"{appointment_date.strftime('%B %d, %Y')} at "
                f"{appointment_time.strftime('%I:%M %p')} has been booked.")

        messages.success(request, 'Appointment booked successfully! A confirmation email has been sent.')
        if request.htmx:
            response = render(request, 'patient/_book_step3_modal.html', {
                'doctor': doctor, 'appointment_date': date_str, 'appointment_time': time_str,
                'title': 'Confirm Appointment',
            })
            response['HX-Redirect'] = '/patient/appointments/'
            return response
        return redirect('patient:appointment_list')

    # GET: redirect back into the flow at Step 4 (Patient Details) — this
    # view no longer accepts a direct GET with just doctor/date/time, since
    # patient details must be collected first. Carries the date/time
    # through so the patient doesn't have to re-pick the slot.
    doctor_id  = request.GET.get('doctor_id')
    date_str   = request.GET.get('appointment_date')
    time_str   = request.GET.get('appointment_time')
    if not all([doctor_id, date_str, time_str]):
        return redirect('patient:book_step1')
    return redirect(
        f"{reverse('patient:book_step4', kwargs={'doctor_id': doctor_id})}"
        f"?appointment_date={date_str}&appointment_time={time_str}"
    )


@role_required('patient')
def reschedule_appointment(request, pk):
    appointment = get_object_or_404(
        Appointment, pk=pk, patient=request.user, status__in=['Scheduled', 'Rescheduled']
    )
    if request.method == 'POST':
        date_str = request.POST.get('appointment_date')
        time_str = request.POST.get('appointment_time')
        reason   = request.POST.get('reason', appointment.reason)
        try:
            new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            new_time = datetime.strptime(time_str, '%H:%M').time()
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date/time.')
            if request.htmx:
                return render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
            return render(request, 'patient/reschedule.html', {'appointment': appointment})

        if new_date < date.today():
            messages.error(request, 'Cannot reschedule to a past date.')
            if request.htmx:
                return render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
            return render(request, 'patient/reschedule.html', {'appointment': appointment})

        with transaction.atomic():
            doctor_conflict = Appointment.objects.select_for_update().filter(
                doctor=appointment.doctor,
                appointment_date=new_date,
                appointment_time=new_time,
                status__in=['Scheduled', 'Rescheduled']
            ).exclude(pk=appointment.pk).exists()
            if doctor_conflict:
                messages.error(request, 'That slot is already taken. Choose another time.')
                if request.htmx:
                    return render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
                return render(request, 'patient/reschedule.html', {'appointment': appointment})

            # A patient can only have one active appointment at a given
            # date/time, even across different doctors — checked separately
            # from the doctor-scoped conflict above. Excludes this same
            # appointment since it's the one being moved.
            patient_conflict = Appointment.objects.select_for_update().filter(
                patient=appointment.patient,
                appointment_date=new_date,
                appointment_time=new_time,
                status__in=['Scheduled', 'Rescheduled']
            ).exclude(pk=appointment.pk).exists()
            if patient_conflict:
                messages.error(request, 'You already have another appointment at this date and time. Choose another time.')
                if request.htmx:
                    return render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
                return render(request, 'patient/reschedule.html', {'appointment': appointment})

            # Don't apply the new date/time yet — the original appointment is
            # left untouched and flagged as pending until the doctor
            # reviews and approves the request.
            appointment.status            = 'Pending Reschedule'
            appointment.requested_date    = new_date
            appointment.requested_time    = new_time
            appointment.requested_reason  = reason
            appointment.save()

        _notify(appointment.doctor,
                f"{appointment.patient.get_full_name()} requested to reschedule their appointment to "
                f"{new_date.strftime('%B %d, %Y')} at {new_time.strftime('%I:%M %p')}. Awaiting your approval.")
        _notify(request.user,
                f"Your reschedule request for {new_date.strftime('%B %d, %Y')} at "
                f"{new_time.strftime('%I:%M %p')} has been sent to Dr. {appointment.doctor.get_full_name()} for approval.")
        messages.success(request, 'Reschedule request sent. It will take effect once the doctor approves it.')
        if request.htmx:
            response = render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
            response['HX-Redirect'] = '/patient/appointments/'
            return response
        return redirect('patient:appointment_list')

    if request.htmx:
        return render(request, 'patient/_reschedule_modal.html', {'appointment': appointment, 'title': 'Reschedule Appointment'})
    return render(request, 'patient/reschedule.html', {'appointment': appointment})


@role_required('patient')
def appointment_detail(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor', 'doctor__doctor_profile', 'results'), pk=pk, patient=request.user
    )
    medical_record = None
    if appointment.status == 'Completed':
        from records.models import ResultsConsultation
        try:
            medical_record = appointment.results.medical_records.first()
        except ResultsConsultation.DoesNotExist:
            medical_record = None
    return render(request, 'patient/_appointment_detail_modal.html', {
        'appointment': appointment, 'medical_record': medical_record, 'title': 'Appointment Details',
    })


@role_required('patient')
def cancel_appointment(request, pk):
    appointment = get_object_or_404(
        Appointment, pk=pk, patient=request.user, status__in=['Scheduled', 'Rescheduled']
    )
    if request.method == 'POST':
        appointment.status = 'Cancelled'
        appointment.save()
        try:
            send_cancellation_email(appointment)
        except Exception:
            pass
        _notify(request.user,
                f"Your appointment with Dr. {appointment.doctor.get_full_name()} on "
                f"{appointment.appointment_date.strftime('%B %d, %Y')} has been cancelled.")
        messages.success(request, 'Appointment cancelled.')
        if request.htmx:
            response = render(request, 'patient/_cancel_confirm_modal.html', {'appointment': appointment})
            response['HX-Redirect'] = '/patient/appointments/'
            return response
        return redirect('patient:appointment_list')
    if request.htmx:
        return render(request, 'patient/_cancel_confirm_modal.html', {'appointment': appointment})
    return render(request, 'patient/cancel_confirm.html', {'appointment': appointment})


@role_required('patient')
def medical_records(request):
    from records.models import MedicalRecords
    records = MedicalRecords.objects.filter(
        patient=request.user
    ).select_related('doctor', 'results').order_by('-visit_date')
    return render(request, 'patient/medical_records.html', {'records': records})


@role_required('patient')
def medical_record_detail(request, pk):
    from records.models import MedicalRecords
    record = get_object_or_404(
        MedicalRecords.objects.select_related('doctor', 'results').prefetch_related('results__prescriptions'),
        pk=pk, patient=request.user
    )
    return render(request, 'patient/_medical_record_detail_modal.html', {
        'record': record, 'title': 'Medical Record',
    })


@role_required('patient')
def patient_notifications(request):
    return redirect('/notifications/')
