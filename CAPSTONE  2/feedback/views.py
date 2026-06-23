from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from .models import Feedback
from .forms import FeedbackForm
from appointments.models import Appointment


@role_required('patient')
def feedback_list(request):
    feedbacks = Feedback.objects.filter(patient=request.user).select_related('appointment')
    completed_without_feedback = Appointment.objects.filter(
        patient=request.user, status='Completed'
    ).exclude(pk__in=feedbacks.filter(appointment__isnull=False).values('appointment_id'))
    return render(request, 'feedback/feedback_list.html', {
        'feedbacks': feedbacks,
        'to_review': completed_without_feedback,
    })


@role_required('patient')
def feedback_detail(request, pk):
    fb = get_object_or_404(Feedback.objects.select_related('appointment', 'appointment__doctor'), pk=pk, patient=request.user)
    return render(request, 'feedback/_feedback_detail_modal.html', {
        'fb': fb, 'title': 'Feedback Details',
    })


@role_required('patient')
def submit_feedback(request, appointment_id):
    appointment = get_object_or_404(Appointment, pk=appointment_id, patient=request.user, status='Completed')
    existing = Feedback.objects.filter(patient=request.user, appointment=appointment).first()
    if existing:
        messages.info(request, 'You have already submitted feedback for this appointment.')
        if request.htmx:
            from django.http import HttpResponse
            response = HttpResponse(status=204)
            response['HX-Redirect'] = '/feedback/'
            return response
        return redirect('feedback:list')
    form = FeedbackForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        fb = form.save(commit=False)
        fb.patient     = request.user
        fb.appointment = appointment
        fb.save()
        messages.success(request, 'Thank you for your feedback!')
        if request.htmx:
            response = render(request, 'feedback/_submit_feedback_modal.html', {
                'form': form, 'appointment': appointment, 'title': 'Rate Your Visit',
            })
            response['HX-Redirect'] = '/feedback/'
            return response
        return redirect('feedback:list')
    if request.htmx:
        return render(request, 'feedback/_submit_feedback_modal.html', {
            'form': form, 'appointment': appointment, 'title': 'Rate Your Visit',
        })
    return render(request, 'feedback/submit_feedback.html', {
        'form': form, 'appointment': appointment
    })
