from django.urls import path
from . import views

app_name = 'feedback'

urlpatterns = [
    path('',                                    views.feedback_list,   name='list'),
    path('<int:pk>/detail/',                    views.feedback_detail, name='detail'),
    path('submit/<int:appointment_id>/',        views.submit_feedback, name='submit'),
]
