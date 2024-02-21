# -*- coding: utf-8 -*-

import asyncio
from contextlib import asynccontextmanager
import functools
import warnings

from websockets.exceptions import ConnectionClosedOK

from .tyokalut import Koriste


class Kattelyvirhe(asyncio.CancelledError):
  ''' Websocket-kättely epäonnistui. '''


class YhteysKatkaistiin(asyncio.CancelledError):
  ''' Yhteys katkaistiin asiakaspäästä (websocket.disconnect). '''


class _WebsocketKoriste(Koriste):

  def __new__(cls, websocket, **kwargs):
    # pylint: disable=signature-differs
    _websocket = websocket
    while _websocket is not None:
      if isinstance(_websocket, __class__):
        raise ValueError(
          f'Useita sisäkkäisiä Websocket-protokollamäärityksiä:'
          f' {cls}({type(_websocket)}(...))'
        )
      _websocket = getattr(
        _websocket,
        '__wrapped__',
        None
      )
      # while _websocket is not None
    return super().__new__(cls, websocket, **kwargs)
    # def __new__

  # class _WebsocketKoriste


class _WebsocketYhteys:

  saapuva_kattely = {'type': 'websocket.connect'}
  lahteva_kattely = {'type': 'websocket.accept'}
  saapuva_katkaisu = {'type': 'websocket.disconnect'}
  lahteva_katkaisu = {'type': 'websocket.close'}

  async def _avaa_yhteys(self, request):
    # pylint: disable=protected-access
    saapuva_kattely = await request.receive()
    if saapuva_kattely != self.saapuva_kattely:
      request._katkaistu_vastapaasta.set()
      raise Kattelyvirhe(
        'Avaava kättely epäonnistui: %r' % saapuva_kattely
      )
    await request.send(self.lahteva_kattely)
    # async def _avaa_yhteys

  async def _sulje_yhteys(self, request):
    request._katkaistu_tasta_paasta.set()
    await request.send(self.lahteva_katkaisu)
    # async def _sulje_yhteys

  @asynccontextmanager
  async def __call__(
    self, request, *args, **kwargs
  ):
    request._katkaistu_vastapaasta = asyncio.Event()
    request._katkaistu_tasta_paasta = asyncio.Event()

    # pylint: disable=invalid-name
    try:
      await asyncio.shield(self._avaa_yhteys(request))

    except Kattelyvirhe:
      await asyncio.shield(self._sulje_yhteys(request))
      raise

    except asyncio.CancelledError:
      asyncio.tasks.current_task().cancel()

    try:
      yield

    finally:
      if not request._katkaistu_vastapaasta.is_set():
        try:
          await asyncio.shield(self._sulje_yhteys(request))
        except asyncio.CancelledError:
          pass

    # async def __call__

  # class _WebsocketYhteys


class _WebsocketProtokolla(_WebsocketYhteys):

  saapuva_sanoma = {'type': 'websocket.receive'}
  lahteva_sanoma = {'type': 'websocket.send'}

  @asynccontextmanager
  async def __call__(
    self, request, *args, **kwargs
  ):
    # pylint: disable=invalid-name
    async with super().__call__(request):

      syote = asyncio.Queue()

      @functools.wraps(request.receive)
      async def _receive():
        while not request._katkaistu_tasta_paasta.is_set() \
        and not request._katkaistu_vastapaasta.is_set():
          sanoma = await _receive.__wrapped__()
          if sanoma['type'] == self.saapuva_sanoma['type']:
            await syote.put(
              sanoma.get('text', sanoma.get('bytes', None))
            )
          elif sanoma['type'] == self.saapuva_katkaisu['type']:
            request._katkaistu_vastapaasta.set()
            raise asyncio.CancelledError
          else:
            raise TypeError(repr(sanoma))
        # async def _receive

      @functools.wraps(request.receive)
      async def receive():
        data = await syote.get()
        syote.task_done()
        return data
        # async def receive

      @functools.wraps(request.send)
      async def send(data):
        '''
        Lähetetään annettu data joko tekstinä tai tavujonona.
        '''
        if isinstance(data, str):
          data = {**self.lahteva_sanoma, 'text': data}
        elif isinstance(data, bytearray):
          data = {**self.lahteva_sanoma, 'bytes': bytes(data)}
        elif isinstance(data, bytes):
          data = {**self.lahteva_sanoma, 'bytes': data}
        else:
          raise TypeError(repr(data))
        try:
          return await send.__wrapped__(data)
        except ConnectionClosedOK as exc:
          raise YhteysKatkaistiin from exc
        # async def send

      request.receive = receive
      request.send = send

      try:
        yield request, _receive

      except (YhteysKatkaistiin, asyncio.CancelledError):
        pass

      except BaseException as exc:
        print('näkymän suoritus katkesi poikkeukseen:', exc)
        raise

      finally:
        request.receive = receive.__wrapped__
        request.send = send.__wrapped__
    # async def __call__

  # class _WebsocketProtokolla


class WebsocketProtokolla(_WebsocketProtokolla, _WebsocketKoriste):
  '''
  Sallitaan vain yksi protokolla per metodi.
  '''
  def _nakyma(self, request, *args, **kwargs):
    return self.__wrapped__(request, *args, **kwargs)

  async def __call__(
    self, request, *args, **kwargs
  ):
    # pylint: disable=invalid-name
    if request.method != 'Websocket':
      # pylint: disable=no-member
      return await self._nakyma(
        request, *args, **kwargs
      )

    async with super().__call__(
      request, *args, **kwargs
    ) as (request, _receive):
      kaaritty = self.__wrapped__(request, *args, **kwargs)
      receive = asyncio.create_task(_receive())

      valmis, kesken = set(), {
        asyncio.create_task(kaaritty),
        receive,
      }
      try:
        # pylint: disable=unused-variable
        valmis, kesken = await asyncio.wait(
          kesken,
          return_when=asyncio.FIRST_COMPLETED
        )
      finally:
        for _valmis in valmis:
          try:
            if exc := _valmis.exception():
              raise exc
          except asyncio.CancelledError:
            pass
        for _kesken in kesken:
          _kesken.cancel()
          try:
            await _kesken
          except asyncio.CancelledError:
            pass

    # async def __call__

  # class WebsocketProtokolla


class WebsocketAliprotokolla(WebsocketProtokolla):

  protokolla = []

  def __new__(cls, *args, **kwargs):
    if not args or not callable(args[0]):
      def wsp(websocket):
        return cls(websocket, *args, **kwargs)
      return wsp
    return super().__new__(cls, args[0])
    # def __new__

  def __init__(self, websocket, *protokolla, **kwargs):
    super().__init__(websocket, **kwargs)
    self.protokolla = protokolla
    # def __init__

  async def _avaa_yhteys(self, request):
    saapuva_kattely = await request.receive()
    if saapuva_kattely != self.saapuva_kattely:
      request._katkaistu_vastapaasta.set()
      request.protokolla = None
      raise Kattelyvirhe(
        'Avaava kättely epäonnistui: %r' % saapuva_kattely
      )

    pyydetty_protokolla = request.scope.get(
      'subprotocols', []
    )
    if self.protokolla or pyydetty_protokolla:
      # pylint: disable=protected-access, no-member
      # pylint: disable=undefined-loop-variable
      for hyvaksytty_protokolla in pyydetty_protokolla:
        if hyvaksytty_protokolla in self.protokolla:
          break
      else:
        # Yhtään yhteensopivaa protokollaa ei löytynyt (tai pyynnöllä
        # ei ollut annettu yhtään protokollaa).
        # Hylätään yhteyspyyntö.
        request.protokolla = None
        raise Kattelyvirhe(
          'Ei yhteensopivaa protokollaa: %r vs. %r' % (
            self.protokolla, pyydetty_protokolla
          )
        )
      # Hyväksytään WS-yhteyspyyntö valittua protokollaa käyttäen.
      await request.send({
        **self.lahteva_kattely,
        'subprotocol': hyvaksytty_protokolla,
      })
      request.protokolla = hyvaksytty_protokolla

    else:
      # Näkymä ei määrittele protokollaa; hyväksytään pyyntö.
      await request.send(self.lahteva_kattely)
      request.protokolla = None
    # async def _avaa_yhteys

  # class WebsocketAliprotokolla
