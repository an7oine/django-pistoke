# -*- coding: utf-8 -*-

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

from asgiref.sync import async_to_sync, sync_to_async

from django.core.signals import (
  request_finished, request_started,
)
from django.db import close_old_connections
from django.test.client import AsyncClient
from django.test.testcases import SimpleTestCase
from django.utils.functional import classproperty

from pistoke.kasittelija import WebsocketKasittelija
from pistoke.protokolla import _WebsocketProtokolla
from pistoke.pyynto import WebsocketPyynto


class WebsocketPoikkeus:

  class NakymaPaattyi(Exception):
    ''' Näkymä päättyi ennen kuin pääteyhteys alkoi. '''

  class KattelyEpaonnistui(Exception):
    ''' Websocket-kättely epäonnistui. '''

  class Http403(Exception):
    ''' Websocket-yhteyspyyntö epäonnistui. '''

  class PaateyhteysAikakatkaistiin(Exception):
    ''' Websocket-pääteyhteys aikakatkaistiin. '''

  class SyotettaEiLuettu(RuntimeError):
    ''' Websocket-syötettä jäi lukematta näkymän päätyttyä. '''

  class TulostettaEiLuettu(RuntimeError):
    ''' Websocket-tulostetta jäi lukematta pääteyhteyden päätyttyä. '''

  # class WebsocketPoikkeus


class WebsocketPaateKasittelija(WebsocketKasittelija):
  ''' Vrt. AsyncClientHandler '''

  nosta_syotetta_ei_luettu = True

  def __init__(
    self,
    *args,
    enforce_csrf_checks=True,
    **kwargs
  ):
    super().__init__(*args, **kwargs)
    self.enforce_csrf_checks = enforce_csrf_checks
    # def __init__

  async def __call__(self, scope, receive, send):
    request_started.disconnect(close_old_connections)
    try:
      await super().__call__(scope, receive, send)
    finally:
      request_started.connect(close_old_connections)
    # async def __call__

  async def get_response_async(self, request):
    # pylint: disable=protected-access
    request._dont_enforce_csrf_checks = not self.enforce_csrf_checks
    return await super().get_response_async(request)
    # async def get_response_async

  # class WebsocketPaateKasittelija


class WebsocketPaateprotokolla(_WebsocketProtokolla):
  '''
  Käänteinen Websocket-protokolla, so. selaimen / ASGI-palvelimen näkökulma.

  Vrt. `pistoke.protokolla.WebsocketProtokolla`.
  '''
  # Websocket-sanomatyypit ovat päinvastaiset.
  saapuva_kattely = {'type': 'websocket.accept'}
  lahteva_kattely = {'type': 'websocket.connect'}
  saapuva_katkaisu = {'type': 'websocket.close'}
  lahteva_katkaisu = {'type': 'websocket.disconnect'}
  lahteva_sanoma = {'type': 'websocket.receive'}
  saapuva_sanoma = {'type': 'websocket.send'}

  # Nostetaan erillinen poikkeus, kun pääteyhteys ei lue omaa syötettään,
  # so. näkymän tuottamaa tulostetta.
  SyotettaEiLuettu = WebsocketPoikkeus.TulostettaEiLuettu

  async def _avaa_yhteys(self, request):
    ''' Kättelyiden järjestys on päinvastainen. '''
    await request.send(self.lahteva_kattely)
    kattely = await request.receive()
    if not isinstance(kattely, dict) or 'type' not in kattely:
      raise WebsocketPoikkeus.KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    if kattely == self.saapuva_katkaisu:
      request._katkaistu_vastapaasta.set()
      raise WebsocketPoikkeus.Http403(
        'Palvelin sulki yhteyden.'
      )
    elif kattely['type'] == self.saapuva_kattely['type']:
      if 'subprotocol' in kattely:
        request.scope['subprotocol'] = kattely['subprotocol']
    else:
      raise WebsocketPoikkeus.KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    # async def _avaa_yhteys

  async def _sulje_yhteys(self, request):
    '''
    Yhteys suljetaan (disconnect) riippumatta mahdollisesta
    näkymän lähettämästä katkaisusta (close).
    '''
    await request.send(self.lahteva_katkaisu)
    # async def _sulje_yhteys

  @asynccontextmanager
  async def __call__(self, scope, receive, send):
    async with super().__call__(
      WebsocketPyynto(scope, receive, send),
    ) as (request, _receive):
      _task = asyncio.tasks.current_task()
      _receive = asyncio.create_task(_receive())
      _receive.add_done_callback(
        lambda __receive: _task.cancel()
      )
      try:
        yield request
      finally:
        _receive.cancel()
        try:
          await _receive
        except asyncio.CancelledError:
          pass
      # async with super().__call__
    # async def __call__

  # class WebsocketPaateprotokolla


@dataclass
class WebsocketPaateyhteys(WebsocketPaateprotokolla):

  scope: dict
  enforce_csrf_checks: bool
  raise_request_exception: bool
  aikakatkaisu: float

  def __post_init__(self):
    super().__init__()

  @asynccontextmanager
  async def __call__(self):
    kasittelija = WebsocketPaateKasittelija(
      enforce_csrf_checks=self.enforce_csrf_checks
    )
    syote, tuloste = asyncio.Queue(), asyncio.Queue()

    nakyma = asyncio.create_task(
      kasittelija(
        self.scope,
        syote.get,
        tuloste.put,
      )
    )

    async def aikakatkaistu_nakyma():
      valmis, kesken = await asyncio.wait(
        (nakyma, ),
        timeout=self.aikakatkaisu,
      )
      if valmis:
        await nakyma
      else:  # if kesken
        nakyma.cancel()
        try:
          await nakyma
        except asyncio.CancelledError:
          pass
        raise WebsocketPoikkeus.PaateyhteysAikakatkaistiin
      # async def aikakatkaistu_nakyma
    aikakatkaistu_nakyma = asyncio.create_task(aikakatkaistu_nakyma())

    paate = asyncio.tasks.current_task()
    paatteen_nostama_poikkeus = None

    @aikakatkaistu_nakyma.add_done_callback
    def nakyma_valmis(_nakyma):
      ''' Keskeytä pääteistunto, jos näkymä päättyy. '''
      paate.cancel()

    # Anna näkymälle hetki aikaa ennen pääteyhteyden avaamista.
    # Mikäli näkymä ehti päättyä, nostetaan poikkeus.
    try:
      await asyncio.sleep(0.01)
    except asyncio.CancelledError:
      try:
        if poikkeus := aikakatkaistu_nakyma.exception():
          raise poikkeus from None
      except asyncio.CancelledError:
        pass
      raise WebsocketPoikkeus.NakymaPaattyi from None

    try:
      # Toteutetaan pääteistunto käänteisen Websocket-protokollan
      # sisällä.
      async with super().__call__(
        self.scope,
        tuloste.get,
        syote.put
      ) as request:
        yield request

    except Exception as exc:
      paatteen_nostama_poikkeus = exc

    finally:
      # Annetaan näkymälle hetki aikaa päättyä.
      try:
        await asyncio.sleep(0.01)
      except asyncio.CancelledError:
        pass

      aikakatkaistu_nakyma.cancel()

      # Odotetaan, kunnes näkymän suoritus on päättynyt.
      try:
        await aikakatkaistu_nakyma
      except asyncio.CancelledError:
        pass
      except _WebsocketProtokolla.SyotettaEiLuettu as exc:
        raise WebsocketPoikkeus.SyotettaEiLuettu from exc

      finally:
        if paatteen_nostama_poikkeus is not None:
          raise paatteen_nostama_poikkeus

      # async with super.__call__
    # async def __call__

  # class WebsocketPaateyhteys


def websocket_scope(
  paate,
  path,
  secure=False,
  protokolla=None,
  **extra
):
  '''
  Muodosta Websocket-pyyntökonteksti (scope).

  Vrt. `django.test.client:AsyncRequestFactory`:
  metodit `_base_scope` ja `generic`.
  '''
  # pylint: disable=protected-access
  parsed = urlparse(str(path))  # path can be lazy.
  request = {
    'path': paate._get_path(parsed),
    'server': ('127.0.0.1', '443' if secure else '80'),
    'scheme': 'wss' if secure else 'ws',
    'headers': [(b'host', b'testserver')],
  }
  request['headers'] += [
    (key.lower().encode('ascii'), value.encode('latin1'))
    for key, value in extra.items()
  ]
  if not request.get('query_string'):
    request['query_string'] = parsed[4]
  if protokolla is not None:
    request['subprotocols'] = (
      [protokolla] if isinstance(protokolla, str)
      else list(protokolla)
    )
  return {
    'type': 'websocket',
    'asgi': {'version': '3.0', 'spec_version': '2.1'},
    'scheme': 'ws',
    'server': ('testserver', 80),
    'client': ('127.0.0.1', 0),
    'headers': [
      (b'sec-websocket-version', b'13'),
      (b'connection', b'keep-alive, Upgrade'),
      *paate.defaults.pop('headers', ()),
      *request.pop('headers', ()),
      (b'cookie', b'; '.join(sorted(
        ('%s=%s' % (morsel.key, morsel.coded_value)).encode('ascii')
        for morsel in paate.cookies.values()
      ))),
      (b'upgrade', b'websocket')
    ],
    **paate.defaults,
    **request,
  }
  # def websocket_scope


class WebsocketPaate(WebsocketPoikkeus, AsyncClient):

  websocket_aikakatkaisu: float = 1.0

  def __init__(self, *args, **kwargs):
    try:
      self.websocket_aikakatkaisu = kwargs.pop('websocket_aikakatkaisu')
    except KeyError:
      pass
    super().__init__(*args, **kwargs)
    # def __init__

  def websocket(self, *args, **kwargs):
    '''
    Käyttö asynkronisena kontekstina:
    >>> class Testi(WebsocketTesti):
    >>>
    >>>   async def testaa_X(self):
    >>>     async with self.async_client.websocket(
    >>>       '/.../'
    >>>     ) as websocket:
    >>>       websocket.send(...)
    >>>       ... = await websocket.receive()

    Annettu testirutiini suoritetaan ympäröivässä kontekstissa
    ja testattava näkymä tausta-ajona (asyncio.Task).
    '''
    # pylint: disable=protected-access

    return WebsocketPaateyhteys(
      websocket_scope(
        self,
        *args,
        **kwargs
      ),
      enforce_csrf_checks=self.handler.enforce_csrf_checks,
      raise_request_exception=self.raise_request_exception,
      aikakatkaisu=self.websocket_aikakatkaisu,
    )()
    # async def websocket

  # class WebsocketPaate


class WebsocketTesti(SimpleTestCase):

  websocket_aikakatkaisu: float = 1.0

  @classproperty
  def async_client_class(cls):
    # pylint: disable=no-self-argument
    class _WebsocketPaate(WebsocketPaate, super().async_client_class):
      websocket_aikakatkaisu = cls.websocket_aikakatkaisu
    return _WebsocketPaate
    # def async_client_class

  # class WebsocketTesti
