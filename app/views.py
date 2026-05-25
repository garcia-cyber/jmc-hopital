from django.shortcuts import render , redirect , get_object_or_404
from .forms import *
from .models import *
from django.contrib.auth import authenticate , login as auth_login , logout ,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm ,UserChangeForm
from django.contrib import messages

# Create your views here.


# 1
# ===============================================================
# ===============================================================
# page d'accueil
def home(request):
    return render(request , 'front-end/index.html')


# 2
#
#
# authentification
def login(request):
    # Si l'utilisateur est déjà connecté, on le redirige directement
    if request.user.is_authenticated:
         return redirect('dashboard')
 
    msg = None
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                if user.is_active:
                    auth_login(request, user)
                    return redirect('dashboard')
                else:
                    msg = "Votre compte est désactivé."
            else:
                msg = "Identifiants invalides. Veuillez réessayer. 🤞"
    else:
        form = LoginForm()

    # Note : On passe 'form' tel quel. Si c'est un POST invalide, 
    # il contiendra les erreurs et les données saisies.
    return render(request, 'back-end/login.html', {'form': form, 'msg': msg})

# 3
# ==========================================================================
# DECONNEXION
# ==========================================================================
def deco(request):
    logout(request)
    return redirect('home')

# 4
# ===========================================================================
# dashboard
# ===========================================================================
@login_required
def dashboard(request):
    return render(request, 'back-end/index.html')