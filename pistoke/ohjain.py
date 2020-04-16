# -*- coding: utf-8 -*-

from django.contrib.sessions.middleware import SessionMiddleware
from django.core.handlers.asgi import ASGIRequest


class WebsocketOhjain:
  '''
  Ohjain, joka asettaa pyynnölle URI-määritteen `websocket` siten,
  että siihen tehdyt pyynnöt ohjataan ajossa olevaan ASGI-käsittelijään.

  Mikäli HTTP-yhteys on salattu (HTTPS),
  käytetään salattua Websocket-yhteyttä (WSS).

  Mikäli pyyntö ei ole ASGI-pohjainen, ei `websocket`-yhteys ole
  käytettävissä eikä em. määritettä aseteta.
  '''
  def __init__(self, get_response):
    self.get_response = get_response

  def __call__(self, request):
    if isinstance(request, ASGIRequest):
      request.websocket = (
        f'{"wss" if request.is_secure() else "ws"}://{request.get_host()}'
      )
    return self.get_response(request)
    # def __call__

  # class WebsocketOhjain


class IstuntoOhjain(SessionMiddleware):
  '''
  Puukotetaan Django-istunto-ohjain siten,
  ettei (olemattoman) paluusanoman määreisiin kosketa.
  '''
  def process_response(self, request, response):
    return response
  # class IstuntoOhjain


# Muunnostaulu Websocket-pyyntöihin sovellettavista
# Middleware-ohjaimista.
# Muiden kuin tässä mainittujen ohjaimien lataus ohitetaan.
WEBSOCKET_MIDDLEWARE = {
  # Ohitetaan.
  'corsheaders.middleware.CorsMiddleware': False,
  'debug_toolbar.middleware.DebugToolbarMiddleware': False,
  'django.middleware.gzip.GZipMiddleware': False,
  'django.middleware.security.SecurityMiddleware' : False,
  'django.middleware.common.CommonMiddleware': False,
  'django.middleware.csrf.CsrfViewMiddleware': False,
  'django.contrib.messages.middleware.MessageMiddleware': False,
  'django.middleware.clickjacking.XFrameOptionsMiddleware': False,
  'django_hosts.middleware.HostsResponseMiddleware': False,

  # Suoritetaan.
  'django_hosts.middleware.HostsRequestMiddleware': True,
  'django.contrib.sessions.middleware.SessionMiddleware': \
    'pistoke.ohjain.IstuntoOhjain',
  'django.contrib.auth.middleware.AuthenticationMiddleware': True,
  'impersonate.middleware.ImpersonateMiddleware': True,
  'silk.middleware.SilkyMiddleware': True,
  'pistoke.ohjain.WebsocketOhjain': True,
}
