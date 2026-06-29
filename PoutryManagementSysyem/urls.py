from django.urls import path

from . import views


app_name = 'poultry'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('payments/mobile-money/providers/', views.mobile_money_providers, name='mobile_money_providers'),
    path('payments/mobile-money/request/', views.request_mobile_money_payment, name='request_mobile_money_payment'),
    path('payments/mobile-money/status/<str:transaction_id>/', views.mobile_money_payment_status, name='mobile_money_payment_status'),
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_create, name='user_create'),
    path('users/<int:pk>/roles/', views.user_assign_roles, name='user_assign_roles'),
    path('roles/', views.role_list, name='role_list'),
    path('roles/add/', views.role_create, name='role_create'),
    path('roles/<int:pk>/edit/', views.role_update, name='role_update'),
    path('records/', views.crud_index, name='crud_index'),
    path('records/<slug:model_slug>/', views.record_list, name='record_list'),
    path('records/<slug:model_slug>/add/', views.record_create, name='record_create'),
    path('records/<slug:model_slug>/<int:pk>/', views.record_detail, name='record_detail'),
    path('records/<slug:model_slug>/<int:pk>/edit/', views.record_update, name='record_update'),
    path('records/<slug:model_slug>/<int:pk>/delete/', views.record_delete, name='record_delete'),
]
