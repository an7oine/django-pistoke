# -*- coding: utf-8 -*-

'''Django-välikkeet (Middleware) Websocket-ympäristössä.

HTTP-pyynnöllä ajettava `WebsocketOhjain` asettaa pyynnölle `websocket`-
määreen silloin, kun Websocket-yhteys on käytettävissä, so. pyyntö on
tullut sisään Djangon ASGI-käsittelijän kautta. Silloin on voimassa:
- kun pyydetty osoite on http(s)://palvelimen.osoite,
- määre `request.websocket` on ws(s)://palvelimen.osoite.

Lisäksi tämä moduuli määrittelee (`WEBSOCKET_MIDDLEWARE`) luettelon,
Django-projektiasetuksia mukaillen, välikkeistä jotka voidaan ajaa
saapuville Websocket-pyynnöille.

Käytännössä nämä ovat projektiasetusten mukaiset HTTP-välikkeet ilman
paluusanoman käsittelytoteutusta (`process_response`).

Lisäksi seuraavien välikkeiden toimintaa on mukautettu:
- CsrfMiddleware: ohitetaan POST-datan (jota ei ole) automaattinen,
  oletusarvoinen tarkistus; lisätään pyyntökohtainen
  `request.tarkista_csrf`-metodi.
- OriginTarkistus: ajetaan vain Websocket-pyynnöille, tarkistetaan
  täsmääkö HTTP-`Origin`-otsake Django-`ALLOWED_HOSTS`-luetteloon.
  Tämä tarkistus ohitetaan, mikäli näkymäfunktiolle on asetettu määre
  `origin_poikkeus` (ks. `pistoke.tyokalut.origin_poikkeus`).
'''

import asyncio
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.handlers.asgi import ASGIRequest
from django.http.request import split_domain_port, validate_host
from django.http import HttpResponseForbidden
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.decorators import sync_and_async_middleware
from django.utils.module_loading import import_string
from django.utils.log import log_response

import mmaare


logger = logging.getLogger('django.pistoke.origin')


@sync_and_async_middleware
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
    # Asetetaan tämä ohjain näyttämään ulospäin asynkroniselta silloin,
    # kun signaalitien seuraava ohjain on sellainen.
    if asyncio.iscoroutinefunction(self.get_response):
      self._is_coroutine = asyncio.coroutines._is_coroutine

  def __call__(self, request):
    # Huomaa, että funktiokutsu palauttaa joko synkronisen tuloksen
    # tai asynkronisen alirutiinin sen mukaan, mitä signaalitien
    # seuraava ohjain palauttaa.
    if isinstance(request, ASGIRequest):
      request.websocket = (
        f'{"wss" if request.is_secure() else "ws"}://{request.get_host()}'
      )
    return self.get_response(request)
    # def __call__

  # class WebsocketOhjain


@sync_and_async_middleware
class OriginVaatimus:
  '''
  Ohjain, joka tarkistaa mahdollisen Websocket-pyynnöllä annetun
  Origin-otsakkeen vastaavasti kuin Django-CSRF-ohjain tarkistaa
  sen POST-pyynnöllä.
  '''
  def __init__(self, get_response):
    self.get_response = get_response
    if asyncio.iscoroutinefunction(self.get_response):
      self._is_coroutine = asyncio.coroutines._is_coroutine
    # def __init__

  def __call__(self, request):
    return self.get_response(request)
    # def __call__

  def process_view(self, request, callback, callback_args, callback_kwargs):
    # pylint: disable=unused-argument
    assert request.method == 'Websocket'
    if getattr(callback, 'origin_poikkeus', False):
      return None
    elif 'HTTP_ORIGIN' not in request.META:
      return None
    origin = split_domain_port(
      urlparse(request.META['HTTP_ORIGIN']).netloc.lower()
    )[0]
    if not validate_host(origin, settings.ALLOWED_HOSTS):
      virhe = 'Websocket: Origin=%r ei vastaa ALLOWED_HOSTS-asetusta.' % origin
      response = HttpResponseForbidden(virhe)
      log_response(
        virhe,
        request=request,
        response=response,
        logger=logger,
      )
      return response
      # if not validate_host
    return None
    # def process_view

  # class OriginVaatimus


class OhitaPaluusanoma:
  ''' Saateluokka, joka ohittaa paluusanoman käsittelyn. '''

  def process_response(self, request, response):
    return response

  # class OhitaPaluusanoma


class CsrfOhjain(OhitaPaluusanoma, CsrfViewMiddleware):
  def process_view(self, request, callback, callback_args, callback_kwargs):
    '''
    Ohitetaan tavanomainen CSRF-tarkistus POST-datasta.
    '''
  # class CsrfOhjain


class IstuntoOhjain(OhitaPaluusanoma, SessionMiddleware):
  pass


# Muunnostaulu Websocket-pyyntöihin sovellettavista
# Middleware-ohjaimista.
# Muut kuin tässä mainitut ohjaimet periytetään automaattisesti
# `OhitaPaluusanoma`-saateluokasta.
WEBSOCKET_MIDDLEWARE = {
  # Ohitetaan kokonaan.
  'corsheaders.middleware.CorsMiddleware': False,
  'debug_toolbar.middleware.DebugToolbarMiddleware': False,
  'django.middleware.gzip.GZipMiddleware': False,
  'django.middleware.clickjacking.XFrameOptionsMiddleware': False,
  'django_hosts.middleware.HostsResponseMiddleware': False,

  # Korvataan muunnoksella.
  'django.middleware.csrf.CsrfViewMiddleware': 'pistoke.ohjain.CsrfOhjain',
  'django.contrib.sessions.middleware.SessionMiddleware': \
    'pistoke.ohjain.IstuntoOhjain',

  # Suoritetaan sellaisenaan.
  'pistoke.ohjain.WebsocketOhjain': True,
}


def sovita_ohjain_websocket_pyynnolle(ohjain):
  if isinstance(ohjain, str):
    ohjain = import_string(ohjain)
  assert isinstance(ohjain, type)
  return type(
    ohjain.__name__,
    (OhitaPaluusanoma, ohjain),
    {}
  )
  # def sovita_ohjain_websocket_pyynnolle

@mmaare
def __websocket_ohjaimet(moduuli):
  def _websocket_ohjaimet():
    for ohjain in settings.MIDDLEWARE:
      muunnos = WEBSOCKET_MIDDLEWARE.get(ohjain, None)
      if muunnos is False:
        continue
      elif muunnos is True:
        yield ohjain
        continue
      elif muunnos is not None:
        yield muunnos
        continue
      ohjain = sovita_ohjain_websocket_pyynnolle(ohjain)
      setattr(moduuli, ohjain.__name__, ohjain)
      yield '.'.join((__name__, ohjain.__name__))
    yield 'pistoke.ohjain.OriginVaatimus'
  return list(_websocket_ohjaimet())
  # def __websocket_ohjaimet
