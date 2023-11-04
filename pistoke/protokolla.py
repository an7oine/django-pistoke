# -*- coding: utf-8 -*-

import asyncio
from contextlib import asynccontextmanager
import functools
import traceback

from websockets.exceptions import ConnectionClosedOK

from .tyokalut import Koriste


class YhteysKatkaistiin(asyncio.CancelledError):
  ''' Yhteys katkaistiin asiakaspäästä (websocket.disconnect). '''


class _WebsocketProtokolla:
  saapuva_kattely = {'type': 'websocket.connect'}
  lahteva_kattely = {'type': 'websocket.accept'}
  saapuva_katkaisu = {'type': 'websocket.disconnect'}
  lahteva_katkaisu = {'type': 'websocket.close'}
  saapuva_sanoma = {'type': 'websocket.receive'}
  lahteva_sanoma = {'type': 'websocket.send'}

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._jono = asyncio.Queue()
    # def __init__

  async def _avaa_yhteys(self, request):
    # pylint: disable=protected-access
    saapuva_kattely = await request.receive()
    assert saapuva_kattely == self.saapuva_kattely, (
      'Avaava kättely epäonnistui: %r'
    ) % (
      saapuva_kattely
    )
    await request.send(self.lahteva_kattely)
    # async def _avaa_yhteys

  async def _sulje_yhteys(self, request):
    await request.send(self.lahteva_katkaisu)
    # async def _sulje_yhteys

  async def _vastaanota_sanoma(self):
    sanoma = await self._jono.get()
    self._jono.task_done()
    return sanoma
    # async def _vastaanota_sanoma

  async def _laheta_sanoma(self, send, data):
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
      return await send(data)
    except ConnectionClosedOK as exc:
      raise YhteysKatkaistiin from exc
    # async def _laheta_sanoma

  @asynccontextmanager
  async def __call__(
    self, request, *args, **kwargs
  ):
    # pylint: disable=invalid-name
    try:
      await self._avaa_yhteys(request)
    except BaseException:
      await self._sulje_yhteys(request)
      raise

    katkaistu_asiakaspaasta = asyncio.Event()

    @functools.wraps(request.receive)
    async def _receive():
      while True:
        sanoma = await _receive.__wrapped__()
        if sanoma['type'] == self.saapuva_sanoma['type']:
          await self._jono.put(
            sanoma.get('text', sanoma.get('bytes', None))
          )
        elif sanoma['type'] == self.saapuva_katkaisu['type']:
          katkaistu_asiakaspaasta.set()
          raise asyncio.CancelledError
        else:
          raise TypeError(repr(sanoma))
      # async def _receive

    @functools.wraps(request.receive)
    async def receive():
      return await self._vastaanota_sanoma()
    @functools.wraps(request.send)
    async def send(s):
      await self._laheta_sanoma(
        send.__wrapped__,
        s
      )
    request.receive = receive
    request.send = send

    try:
      yield request, _receive

    except (YhteysKatkaistiin, asyncio.CancelledError):
      pass

    except BaseException as exc:
      print('näkymän suoritus katkesi poikkeukseen:', exc)
      traceback.print_exc()
      raise

    finally:
      request.receive = receive.__wrapped__
      request.send = send.__wrapped__
      if not katkaistu_asiakaspaasta.is_set():
        await self._sulje_yhteys(request)
    # async def __call__

  # class _WebsocketProtokolla


class WebsocketProtokolla(_WebsocketProtokolla, Koriste):
  '''
  Sallitaan vain yksi protokolla per metodi.
  '''
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
      kesken = (
        asyncio.create_task(kaaritty),
        asyncio.create_task(_receive()),
      )
      try:
        # pylint: disable=unused-variable
        __valmis, kesken = await asyncio.wait(
          kesken,
          return_when=asyncio.FIRST_COMPLETED
        )
      finally:
        for _kesken in kesken:
          _kesken.cancel()
          await _kesken

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
    assert saapuva_kattely == self.saapuva_kattely, (
      'Avaava kättely epäonnistui: %r'
    ) % (
      saapuva_kattely
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
        raise asyncio.CancelledError
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
