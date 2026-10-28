from django.conf import settings
from django.utils import translation


class CookieLocaleMiddleware:
    """Activates the language the user picked with the switch, English otherwise.

    Django's LocaleMiddleware would also follow the browser's Accept-Language,
    so an interviewer with a Slovak browser (and every screenshot) would land
    on a random language. Here only the cookie written by set_language counts.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.supported = dict(settings.LANGUAGES)

    def __call__(self, request):
        language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language not in self.supported:
            language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language

        response = self.get_response(request)

        response.headers.setdefault("Content-Language", language)
        return response
