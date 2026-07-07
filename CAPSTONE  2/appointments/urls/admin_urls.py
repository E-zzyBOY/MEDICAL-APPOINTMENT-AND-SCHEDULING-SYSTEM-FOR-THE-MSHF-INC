from django.urls import path
from appointments.views import admin_views as v

app_name = 'admin_panel'

urlpatterns = [
    path('',                          v.admin_dashboard,    name='dashboard'),
    path('dashboard/data/',           v.admin_dashboard_data, name='dashboard_data'),
    path('users/',                    v.user_list,          name='user_list'),
    path('users/create/',             v.user_create,        name='user_create'),
    path('users/<int:pk>/detail/',    v.user_detail,        name='user_detail'),
    path('users/<int:pk>/edit/',      v.user_edit,          name='user_edit'),
    path('users/<int:pk>/delete/',    v.user_delete,        name='user_delete'),
    path('appointments/',             v.admin_appointment_list, name='appointment_list'),
    path('appointments/<int:pk>/detail/', v.admin_appointment_detail, name='appointment_detail'),
    path('appointments/<int:pk>/edit/',   v.admin_appointment_edit,   name='appointment_edit'),
    path('feedback/',                    v.admin_feedback_list,       name='feedback_list'),
    path('feedback/doctor/<int:pk>/',    v.admin_feedback_by_doctor, name='feedback_by_doctor'),
    path('feedback/<int:pk>/detail/',    v.admin_feedback_detail,    name='feedback_detail'),
]
