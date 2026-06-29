from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import resolve_url


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or self.is_exempt(request.path):
            return self.get_response(request)
        return redirect_to_login(request.get_full_path(), resolve_url(settings.LOGIN_URL))

    def is_exempt(self, path):
        static_url = settings.STATIC_URL
        if static_url and not static_url.startswith('/'):
            static_url = f'/{static_url}'
        exempt_prefixes = (
            resolve_url(settings.LOGIN_URL),
            resolve_url(settings.LOGOUT_REDIRECT_URL),
            '/accounts/logout/',
            '/admin/',
            static_url,
        )
        return any(path.startswith(prefix) for prefix in exempt_prefixes if prefix)
