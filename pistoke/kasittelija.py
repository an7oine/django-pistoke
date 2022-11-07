# -*- coding: utf-8 -*-

import asyncio
import json

# Python 3.7+
try: from contextlib import asynccontextmanager
# Python 3.6
except ImportError: from async_generator import asynccontextmanager

from asgiref.sync import sync_to_async

import django
from django.conf import settings
from django.core.handlers.asgi import ASGIHandler
from django.core import signals
from django.test.utils import override_settings
from django.urls import set_script_prefix, set_urlconf

from pistoke.ohjain import WEBSOCKET_MIDDLEWARE
from pistoke.pyynto import WebsocketPyynto


class WebsocketVirhe(RuntimeError):
  ''' Virheellinen konteksti Websocket-pyynnön käsittelyssä (WSGI). '''


class WebsocketKasittelija(ASGIHandler):
  '''
  Saapuvien Websocket-pyyntöjen (istuntojen) käsittelyrutiini.
  '''
  def __new__(cls, *args, **kwargs):
    '''
    Alusta Django ennen käsittelyrutiinin luontia.

    Vrt. get_asgi_application().
    '''
    django.setup(set_prefix=False)
    return super().__new__(cls)
    # def __new__

  @asynccontextmanager
  async def _django_pyynto(self, scope):
    # Tehdään Django-rutiinitoimet per saapuva pyyntö.
    await sync_to_async(
      signals.request_started.send,
      thread_sensitive=True
    )(
      sender=self.__class__, scope=scope
    )
    try:
      yield
    finally:
      await sync_to_async(
        signals.request_finished.send,
        thread_sensitive=True
      )(
        sender=self.__class__
      )
    # def _django_pyynto

  async def __call__(self, scope, receive, send):
    '''
    Asynkroninen, pyyntökohtainen kutsu.

    Vrt. django.core.handlers.asgi:ASGIHandler.__call__
    '''
    assert scope['type'] == 'websocket'
    set_script_prefix(self.get_script_prefix(scope))

    # Tehdään Django-rutiinitoimet per saapuva pyyntö.
    async with self._django_pyynto(scope):
      # Muodostetaan WS-pyyntöolio.
      request = WebsocketPyynto(scope, receive, send)

      # Hae käsittelevä näkymärutiini tai mahdollinen virheviesti.
      # Tämä kutsuu mahdollisten avaavien välikkeiden (middleware) ketjua
      # ja lopuksi alla määriteltyä `_get_response_async`-metodia.
      # Metodi suorittaa ensin Websocket-kättelyn loppuun ja sen jälkeen
      # URL-taulun mukaisen näkymäfunktion (async def websocket(...): ...).
      nakyma = await self.get_response_async(request)

      if asyncio.iscoroutine(nakyma):
        await nakyma

      else:
        # Ota yhteyspyyntö vastaan ja evää se.
        # Tällöin asiakaspäähän palautuu HTTP 403 Forbidden.
        avaus = await request.receive()
        assert avaus.get('type') == 'websocket.connect'
        await request.send({'type': 'websocket.close'})
        # if not asyncio.iscoroutine
      # async with self._django_pyynto
    # async def __call__

  def load_middleware(self, is_async=False):
    '''
    Ajetaan vain muunnostaulun mukaiset Websocket-pyynnölle käyttöön
    otettavat ohjaimet.
    '''
    with override_settings(MIDDLEWARE=list(filter(None, (
      ws_ohjain if isinstance(ws_ohjain, str)
      else ohjain if ws_ohjain else None
      for ohjain, ws_ohjain in (
        (ohjain, WEBSOCKET_MIDDLEWARE.get(ohjain, False))
        for ohjain in settings.MIDDLEWARE
      )
    )))):
      super().load_middleware(is_async=is_async)
    # def load_middleware

  # Synkroniset pyynnöt nostavat poikkeuksen.
  def get_response(self, request):
    raise WebsocketVirhe
  def _get_response(self, request):
    raise WebsocketVirhe

  async def get_response_async(self, request):
    ''' Ohitetaan paluusanoman käsittelyyn liittyvät funktiokutsut. '''
    set_urlconf(settings.ROOT_URLCONF)
    return await self._middleware_chain(request)
    # async def get_response_async

  async def _get_response_async(self, request):
    ''' Ohitetaan paluusanoman käsittelyyn liittyvät funktiokutsut. '''
    # pylint: disable=not-callable, protected-access
    callback, callback_args, callback_kwargs = self.resolve_request(request)
    for middleware_method in self._view_middleware:
      vastaus = await middleware_method(
        request, callback, callback_args, callback_kwargs
      )
      if vastaus is not None:
        return await self.send_response(
          request, vastaus
        )
      # for middleware_method in self._view_middleware

    # Mikäli `callback` on asynkroninen funktio (tai kääre),
    # palautetaan sen tuottama alirutiini.
    if asyncio.iscoroutinefunction(callback) \
    or asyncio.iscoroutinefunction(
      getattr(callback, '__call__', callback)
    ):
      return callback(
        request, *callback_args, **callback_kwargs
      )

    # Mikäli `callback` on synkroninen funktio (View.dispatch tai vastaava),
    # kutsutaan sitä pääsäikeessä.
    if callable(callback):
      nakyma = await sync_to_async(
        callback,
        thread_sensitive=True
      )(
        request, *callback_args, **callback_kwargs
      )
      # Tuloksena tulee palautua `async def websocket(...)`-metodin
      # tuottama alirutiini.
      if asyncio.iscoroutine(nakyma):
        return nakyma
      # Muussa tapauksessa kyse on ohjelmointivirheestä.
      raise ValueError(
        'Näkymä %r palautti alirutiinin sijaan arvon %r.' % (
          callback,
          nakyma,
        )
      )
    else:
      raise ValueError(
        'Näkymä %r ei ole kelvollinen funktio.' % (
          callback,
        )
      )

    # async def _get_response_async

  # class WebsocketKasittelija
