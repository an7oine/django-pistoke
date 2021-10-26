# -*- coding: utf-8 -*-

import asyncio
import functools
from types import SimpleNamespace
from urllib.parse import urlparse

# Python 3.7+
try: from contextlib import asynccontextmanager
# Python 3.6
except ImportError: from async_generator import asynccontextmanager

from asgiref.sync import async_to_sync, sync_to_async

from django.core.signals import (
    request_finished, request_started,
)
from django.db import close_old_connections
from django.test.client import AsyncClient

from pistoke.kasittelija import WebsocketKasittelija


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


class WebsocketPaateprotokolla:
  '''
  Käänteinen Websocket-protokolla, so. selaimen / ASGI-palvelimen näkökulma.

  Vrt. `pistoke.protokolla.WebsocketProtokolla`.
  '''
  async def avaa_yhteys(self, receive, send):
    await asyncio.wait_for(send({
      'type': 'websocket.connect'
    }), 0.1)
    kattely = await asyncio.wait_for(receive(), 0.1)
    if not isinstance(kattely, dict) or 'type' not in kattely:
      raise KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    if kattely['type'] == 'websocket.close':
      raise Http403(
        'Palvelin sulki yhteyden.'
      )
    elif kattely['type'] == 'websocket.accept':
      if 'subprotocol' in kattely:
        return kattely['subprotocol']
    else:
      raise KattelyEpaonnistui(
        'Virheellinen kättely: %r' % kattely
      )
    # async def avaa_yhteys

  async def sulje_yhteys(self, receive, send):
    try:
      await send({'type': 'websocket.disconnect'})
    except asyncio.CancelledError:
      # Huomaa, että poikkeukseen päättyneen istunnon
      # päätteeksi ei välttämättä pystytä lähettämään
      # `disconnect`-sanomaa.
      pass
    # async def sulje_yhteys

  async def vastaanota_sanoma(self, receive):
    sanoma = await receive()
    if isinstance(sanoma, BaseException):
      raise sanoma
    assert isinstance(sanoma, dict) and 'type' in sanoma, \
    'Virheellinen sanoma: %r' % sanoma
    if sanoma['type'] == 'websocket.send':
      return sanoma.get('text', sanoma.get('bytes', None))
    elif sanoma['type'] == 'websocket.close':
      raise asyncio.CancelledError
    else:
      raise TypeError(repr(sanoma))
    # async def vastaanota_sanoma

  async def laheta_sanoma(self, send, data):
    '''
    Lähetetään annettu data joko tekstinä tai tavujonona.
    '''
    if isinstance(data, str):
      data = {'type': 'websocket.receive', 'text': data}
    elif isinstance(data, bytearray):
      data = {'type': 'websocket.receive', 'bytes': bytes(data)}
    elif isinstance(data, bytes):
      data = {'type': 'websocket.receive', 'bytes': data}
    else:
      raise TypeError(repr(data))
    return await send(data)
    # async def send

  @asynccontextmanager
  async def __call__(self, scope, receive, send):
    try:
      protokolla = await self.avaa_yhteys(receive, send)
      if protokolla is not None:
        scope['subprotocol'] = protokolla
      yield SimpleNamespace(
        scope=scope,
        receive=functools.partial(
          self.vastaanota_sanoma, receive
        ),
        send=functools.partial(
          self.laheta_sanoma, send
        ),
      )

    finally:
      await self.sulje_yhteys(receive, send)
      # finally
    # def __call__

  # class WebsocketPaateprotokolla


class WebsocketYhteys:

  def __init__(self, scope, *, enforce_csrf_checks):
    self.scope = scope
    self.syote, self.tuloste = Queue(), Queue()
    self.enforce_csrf_checks = enforce_csrf_checks

  def __call__(self, paate):
    assert asyncio.iscoroutinefunction(paate)

    @functools.wraps(paate)
    async def _paate():
      async def paate_taustalla():
        async with WebsocketPaateprotokolla()(
          self.scope,
          self.tuloste.get,
          self.syote.put,
        ) as request:
          return await paate(request)
      paate_taustalla = asyncio.ensure_future(
        paate_taustalla()
      )

      kasittelija = WebsocketPaateKasittelija(
        enforce_csrf_checks=self.enforce_csrf_checks
      )
      nakyma = kasittelija(
        self.scope,
        self.syote.get,
        self.tuloste.put,
      )

      @paate_taustalla.add_done_callback
      def paate_valmis(_paate_taustalla):
        '''
        Katkaise syötteen luku ja tulosteen kirjoitus.
        '''
        self.syote.katkaise_get()
        self.tuloste.katkaise_put()
        nakyma.throw(RuntimeError, 'Yhteys katkaistiin')
        # def paate_valmis

      try:
        await nakyma
      finally:
        # Kun näkymä on valmis, odotetaan siksi kunnes
        # testi päättyy tai kaikki tuloste on luettu.
        await asyncio.wait(
          (
            asyncio.ensure_future(self.tuloste.join()),
            paate_taustalla,
          ),
          return_when=asyncio.FIRST_COMPLETED
        )
        try:
          poikkeus = paate_taustalla.exception()
        except asyncio.CancelledError:
          # Mikäli pääte keskeytettiin, nostetaan
          # tämä poikkeus alempana.
          pass
        except asyncio.InvalidStateError:
          # Mikäli pääte on edelleen kesken,
          # keskeytetään se ja nostetaan mahdollinen
          # muu kuin keskeytykseen liittyvä poikkeus.
          paate_taustalla.cancel()
          try:
            await paate_taustalla
          except asyncio.CancelledError:
            pass
        else:
          if poikkeus is not None:
            raise poikkeus
          # else
        # Palautetaan päätteen tulos (tai nostetaan
        # CancelledError).
        return paate_taustalla.result()
        # finally
      # async def _paate
    return _paate
    # def __call__

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
    @nakyma.add_done_callback
    def nakyma_valmis(_nakyma):
      ''' Katkaise syötteen kirjoitus ja tulosteen luku. '''
      self.syote.katkaise_put()
      self.tuloste.katkaise_get()

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
    await asyncio.wait(
      (
        asyncio.ensure_future(self.syote.join()),
        nakyma,
      ),
      return_when=asyncio.FIRST_COMPLETED
    )
    try:
      poikkeus = nakyma.exception()
    except asyncio.CancelledError:
      pass
    except asyncio.InvalidStateError:
      nakyma.cancel()
      try:
        await nakyma
      except asyncio.CancelledError:
        pass
    else:
      if poikkeus is not None:
        raise poikkeus
        # if poikkeus is not None
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
    Avaa Websocket-yhteys, suorita päätefunktio:
      >>> class Testi(TestCase):
      >>>   async def testaa_X(self):
      >>>     @self.async_client.websocket(...)
      >>>     async def yhteys(websocket):
      >>>       websocket.send(...)
      >>>       ... = await websocket.receive()
      >>>       return True
      >>>     self.assertTrue(await yhteys())

    Tällöin annettu funktio (`yhteys()`) suoritetaan
    tausta-ajona (asyncio.Task) ja testattava näkymä
    ympäröivässä kontekstissa.

    Metodia voidaan käyttää myös asynkronisena
    kontekstina:
      >>>   async def testaa_Y(self):
      >>>     async with self.async_client.websocket(
      >>>       ...
      >>>     ) as websocket:
      >>>       websocket.send(...)
      >>>       ... = await websocket.receive()

    Huomaa, että tässä funktio ajetaan ympäröivässä
    kontekstissa ja itse näkymä tausta-ajona. Tällä erolla saattaa olla
    merkitystä lähinnä tietokantakyselyiden yhteydessä.

    Args:
      *args, **kwargs: pyynnön parametrit

    Returns:
      websocket: koriste tai asynkroninen konteksti
    '''
    # pylint: disable=protected-access

    return WebsocketYhteys(
      websocket_scope(
        self,
        *args,
        **kwargs
      ),
      enforce_csrf_checks
      =self.handler.enforce_csrf_checks,
    )
    # async def websocket

  # Tarjoa poikkeusluokat metodin määreinä.
  websocket.KattelyEpaonnistui = KattelyEpaonnistui
  websocket.Http403 = Http403

  # class WebsocketPaate
