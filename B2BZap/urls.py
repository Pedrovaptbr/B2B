from django.contrib import admin
from django.urls import path, include
from accounts import views as accounts_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', accounts_views.landing_page_view, name='landing_page'),
    path('accounts/', include('accounts.urls')),
    path('app/', include('leads.urls')),
]
