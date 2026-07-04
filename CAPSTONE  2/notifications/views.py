from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Notification


ROLE_TEMPLATES = {
    'patient': 'notifications/notification_list_patient.html',
    'doctor': 'notifications/notification_list_doctor.html',
    'secretary': 'notifications/notification_list_secretary.html',
    'admin': 'notifications/notification_list_admin.html',
}


@login_required(login_url='/accounts/login/')
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)
    # Bell icon opens this as a modal (htmx request); the sidebar/menu link
    # is a normal navigation and still gets the full page below.
    if getattr(request, 'htmx', False):
        return render(request, 'notifications/_notification_list_modal.html', {
            'notifications': notifications, 'title': 'Notifications',
        })
    template = ROLE_TEMPLATES.get(request.user.role, 'notifications/notification_list_patient.html')
    return render(request, template, {
        'notifications': notifications
    })


@login_required(login_url='/accounts/login/')
def notification_detail(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    return render(request, 'notifications/_notification_detail_modal.html', {
        'notification': notif, 'title': 'Notification',
    })


@login_required(login_url='/accounts/login/')
def mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    if request.htmx:
        response = render(request, 'notifications/_notification_detail_modal.html', {'notification': notif})
        response['HX-Redirect'] = '/notifications/'
        return response
    return redirect('notifications:list')


@login_required(login_url='/accounts/login/')
def notification_dismiss(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.delete()
    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Redirect'] = '/notifications/'
        return response
    return redirect('notifications:list')


@login_required(login_url='/accounts/login/')
def mark_all_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    # When triggered from inside the notifications modal, stay in the modal
    # with the refreshed (all-read) list instead of navigating away.
    if getattr(request, 'htmx', False):
        return render(request, 'notifications/_notification_list_modal.html', {
            'notifications': Notification.objects.filter(user=request.user),
            'title': 'Notifications',
        })
    return redirect('notifications:list')
