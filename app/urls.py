from django.urls import path 
from .views import * 


urlpatterns = [
    path('', home , name = 'home') ,
    path('login/' , login , name='login') , 
    path('deco/' , deco , name = 'deco') ,
    path('dashboard/' , dashboard , name = 'dashboard') ,
    
]
