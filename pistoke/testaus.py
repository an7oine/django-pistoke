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

from pistoke.kasittelija import WebsocketKasittelija
from pistoke.protokolla import _WebsocketProtokolla
from pistoke.pyynto import WebsocketPyynto


class KattelyEpaonnistui(Exception):
  ''' Websocket-kättely epäonnistui. '''


class Http403(Exception):
  ''' Websocket-yhteyspyyntö epäonnistui. '''


class SyotettaEiLuettu(RuntimeError):
  ''' Websocket-syötettä jäi lukematta näkymän päätyttyä. '''


class TulostettaEiLuettu(RuntimeError):
  ''' Websocket-tulostetta jäi lukematta pääteyhteyden päätyttyä. '''


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
      request._katkaistu_vastapaasta.set()
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

  def __post_init__(self):
    super().__init__()

  @asynccontextmanager
  async def __call__(self):
    kasittelija = WebsocketPaateKasittelija(
      enforce_csrf_checks=self.enforce_csrf_checks
    )
    syote, tuloste = Queue(), Queue()

    nakyma = asyncio.create_task(
      kasittelija(
        self.scope,
        syote.get,
        tuloste.put,
      )
    )

    paate = asyncio.tasks.current_task()
    paatteen_nostama_poikkeus = None

    @nakyma.add_done_callback
    def nakyma_valmis(_nakyma):
      ''' Keskeytä pääteistunto, jos näkymä päättyy. '''
      paate.cancel()

    try:
      # Toteutetaan pääteistunto käänteisen Websocket-protokollan
      # sisällä.
      async with super().__call__(
        self.scope,
        tuloste.get,
        syote.put
      ) as request:
        if paate.cancelled():
          raise asyncio.CancelledError
        yield request

    except asyncio.CancelledError as exc:
      # Mikäli pääteistunto keskeytettiin näkymän päättymisen
      # seurauksena, varmistetaan, että kaikki tuloste luettiin
      # ennen tätä keskeytystä.
      if not tuloste.empty():
        _t = []
        while not tuloste.empty():
          _t.append(await tuloste.get())
        raise TulostettaEiLuettu(_t) from exc

    except Exception as exc:
      paatteen_nostama_poikkeus = exc

    finally:
      try:
        # Anna näkymälle hetki aikaa lukea mahdollinen jäljellä
        # oleva syöte.
        await asyncio.sleep(0.01)
      except asyncio.CancelledError:
        pass
      else:
        # Tarvittaessa näkymän suoritus keskeytetään.
        nakyma.cancel()

      try:
        await nakyma
      except asyncio.CancelledError as exc:
        # Mikäli näkymän suoritus päättyi kesken, varmistetaan,
        # ettei siltä jäänyt syötettä lukematta.
        if not syote.empty():
          _s = []
          while not syote.empty():
            _s.append(await syote.get())
          raise SyotettaEiLuettu(_s) from exc

      except:
        # Nostetaan näkymän nostama poikkeus tässä vain,
        # ellei pääteistunto nostanut omaa poikkeustaan
        # ja vastaava päätteen asetus on päällä.
        if paatteen_nostama_poikkeus is None \
        and self.raise_request_exception:
          raise

      finally:
        # Tyhjennä mahdollinen pääteistunnon päättymisen jälkeen
        # muodostunut tuloste näkymältä.
        while not tuloste.empty():
          tuloste.get_nowait()

        if paatteen_nostama_poikkeus is not None:
          raise paatteen_nostama_poikkeus

        # finally
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

    return WebsocketPaateyhteys(
      websocket_scope(
        self,
        *args,
        **kwargs
      ),
      enforce_csrf_checks=self.handler.enforce_csrf_checks,
      raise_request_exception=self.raise_request_exception,
    )()
    # async def websocket

  # Tarjoa poikkeusluokat metodin määreinä.
  websocket.KattelyEpaonnistui = KattelyEpaonnistui
  websocket.Http403 = Http403
  websocket.SyotettaEiLuettu = SyotettaEiLuettu
  websocket.TulostettaEiLuettu = TulostettaEiLuettu

  # class WebsocketPaate
