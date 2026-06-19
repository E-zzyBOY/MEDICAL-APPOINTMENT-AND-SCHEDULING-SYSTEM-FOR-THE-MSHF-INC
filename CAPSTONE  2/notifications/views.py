from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
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
    template = ROLE_TEMPLATES.get(request.user.role, 'notifications/notification_list_patient.html')
    return render(request, template, {
        'notifications': notifications
    })


@login_required(login_url='/accounts/login/')
def mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    return redirect('notifications:list')


@login_required(login_url='/accounts/login/')
def mark_all_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notifications:list')
