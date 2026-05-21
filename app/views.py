from django.shortcuts import render ,redirect , get_object_or_404

# Create your views here.


# 1
# ===============================================================
# ===============================================================
# page d'accueil
def home(request):
    return render(request , 'front-end/index.html')
