# -*- coding: utf-8 -*-

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from asgiref.sync import async_to_sync, sync_to_async

from django.core.signals import (
  request_finished, request_started,
)
from django.db import close_old_connections
from django.test.client import AsyncClient

from pistoke.kasittelija import WebsocketKasittelija
from pistoke.protokolla import _WebsocketProtokolla
from pistoke.pyynto import WebsocketPyynto


class KattelyEpaonnistui(Exception):
  ''' Websocket-kättely epäonnistui. '''


class Http403(Exception):
  ''' Websocket-yhteyspyyntö epäonnistui. '''


class Queue(asyncio.Queue):
  '''
  Laajennettu jonototeutus, joka
  - merkitsee haetut paketit käsitellyiksi,
  - nostaa jonoon asetetut poikkeukset haettaessa ja
  - nostaa nostamiseen liittyvät poikkeukset
    asetettaessa.
  '''
  def katkaise_get(self):
    self._put(asyncio.CancelledError())

  def katkaise_put(self):
    self._getters.append(asyncio.CancelledError())

  async def get(self):
    viesti = await super().get()
    self.task_done()
    if isinstance(viesti, BaseException):
      raise viesti
    else:
      return viesti
    # async def get

  async def put(self, item):
    if self._getters \
    and isinstance(self._getters[0], BaseException):
      raise self._getters.popleft()
    return await super().put(item)
    # async def put

  # class Queue


class WebsocketPaateKasittelija(WebsocketKasittelija):
  ''' Vrt. AsyncClientHandler '''

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
  saapuva_kattely = {'type': 'websocket.accept'}
  lahteva_kattely = {'type': 'websocket.connect'}
  saapuva_katkaisu = {'type': 'websocket.close'}
  lahteva_katkaisu = {'type': 'websocket.disconnect'}
  lahteva_sanoma = {'type': 'websocket.receive'}
  saapuva_sanoma = {'type': 'websocket.send'}

  async def _avaa_yhteys(self, request):
    await asyncio.wait_for(request.send(self.lahteva_kattely), 0.1)
    kattely = await asyncio.wait_for(request.receive(), 0.1)
    if not isinstance(kattely, dict) or 'type' not in kattely:
      raise KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    if kattely == self.saapuva_katkaisu:
      raise Http403(
        'Palvelin sulki yhteyden.'
      )
    elif kattely['type'] == self.saapuva_kattely['type']:
      if 'subprotocol' in kattely:
        request.scope['subprotocol'] = kattely['subprotocol']
    else:
      raise KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    # async def _avaa_yhteys

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
      yield request
      _receive.cancel()
      await _receive

    # def __call__

  # class WebsocketPaateprotokolla


class WebsocketYhteys:

  def __init__(self, scope, *, enforce_csrf_checks):
    self.scope = scope
    self.syote, self.tuloste = Queue(), Queue()
    self.enforce_csrf_checks = enforce_csrf_checks

  async def __aenter__(self):
    kasittelija = WebsocketPaateKasittelija(
      enforce_csrf_checks=self.enforce_csrf_checks
    )

    # Async context:
    nakyma = asyncio.ensure_future(
      kasittelija(
        self.scope,
        self.syote.get,
        self.tuloste.put,
      )
    )
    paate = asyncio.tasks.current_task()
    @nakyma.add_done_callback
    def nakyma_valmis(_nakyma):
      ''' Katkaise syötteen kirjoitus ja tulosteen luku. '''
      self.syote.katkaise_put()
      self.tuloste.katkaise_get()
      try:
        if poikkeus := _nakyma.exception():
          paate.set_exception(poikkeus)
      except asyncio.CancelledError:
        pass

    # Tee avaava kättely, odota hyväksyntää.
    protokolla = WebsocketPaateprotokolla()(
      self.scope,
      self.tuloste.get,
      self.syote.put,
    )
    self._nakyma = nakyma
    self._protokolla = protokolla
    return await protokolla.__aenter__()
    # async def __aenter__

  async def __aexit__(self, *exc):
    # Kun testi on valmis, odotetaan siksi kunnes
    # näkymä päättyy tai kaikki syöte on luettu.
    nakyma = self._nakyma
    await self._protokolla.__aexit__(*exc)
    kesken = (
      asyncio.ensure_future(self.syote.join()),
      nakyma,
    )
    valmis, kesken = await asyncio.wait(
      kesken,
      return_when=asyncio.FIRST_COMPLETED,
    )
    if kesken:
      for _kesken in kesken:
        _kesken.cancel()
      _valmis, kesken = await asyncio.wait(kesken)
      valmis = valmis | _valmis
    for _valmis in valmis:
      try:
        if poikkeus := _valmis.exception():
          raise poikkeus
      except asyncio.CancelledError:
        pass
      # else
    # async def __aexit__

  # class WebsocketYhteys


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


class WebsocketPaate(AsyncClient):

  def websocket(self, *args, **kwargs):
    '''
    Käyttö asynkronisena kontekstina:
      >>> class Testi(SimpleTestCase):
      >>>
      >>>   async_client_class = WebsocketPaate
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

    return WebsocketYhteys(
      websocket_scope(
        self,
        *args,
        **kwargs
      ),
      enforce_csrf_checks=self.handler.enforce_csrf_checks,
    )
    # async def websocket

  # Tarjoa poikkeusluokat metodin määreinä.
  websocket.KattelyEpaonnistui = KattelyEpaonnistui
  websocket.Http403 = Http403

  # class WebsocketPaate
