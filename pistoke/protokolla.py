# -*- coding: utf-8 -*-

import asyncio
import functools

from .tyokalut import Koriste


class YhteysKatkaistiin(asyncio.CancelledError):
  ''' Yhteys katkaistiin asiakaspäästä (websocket.disconnect). '''


class WebsocketProtokolla(Koriste):
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

  async def _avaa_yhteys(self, request):
    # pylint: disable=protected-access
    avaava_kattely = await request.receive()
    assert avaava_kattely == {
      'type': 'websocket.connect'
    }, 'Avaava kättely epäonnistui: %r' % (
      avaava_kattely
    )
    await request.send({'type': 'websocket.accept'})
    # async def _avaa_yhteys

  async def _sulje_yhteys(self, request):
    await request.send({'type': 'websocket.close'})
    # async def _sulje_yhteys

  async def _vastaanota_sanoma(self, receive):
    sanoma = await receive()
    if sanoma['type'] == 'websocket.receive':
      return sanoma.get('text', sanoma.get('bytes', None))
    elif sanoma['type'] == 'websocket.disconnect':
      raise YhteysKatkaistiin
    else:
      raise TypeError(sanoma['type'])
    # async def _vastaanota_sanoma

  async def _laheta_sanoma(self, send, data):
    '''
    Lähetetään annettu data joko tekstinä tai tavujonona.
    '''
    if isinstance(data, str):
      data = {'type': 'websocket.send', 'text': data}
    elif isinstance(data, bytearray):
      data = {'type': 'websocket.send', 'bytes': bytes(data)}
    elif isinstance(data, bytes):
      data = {'type': 'websocket.send', 'bytes': data}
    else:
      raise TypeError(repr(data))
    return await send(data)
    # async def _laheta_sanoma

  async def __call__(
    self, request, *args, **kwargs
  ):
    # pylint: disable=invalid-name
    if request.method != 'Websocket':
      # pylint: disable=no-member
      return await self.__wrapped__(
        request, *args, **kwargs
      )

    try:
      await self._avaa_yhteys(request)
    except BaseException:
      await self._sulje_yhteys(request)
      raise

    @functools.wraps(request.receive)
    async def receive():
      return await self._vastaanota_sanoma(
        receive.__wrapped__
      )
    @functools.wraps(request.send)
    async def send(s):
      await self._laheta_sanoma(
        send.__wrapped__,
        s
      )
    request.receive = receive
    request.send = send

    katkaistu_asiakaspaasta = False

    try:
      # pylint: disable=no-member
      return await self.__wrapped__(
        request, *args, **kwargs
      )

    except YhteysKatkaistiin:
      # Mikäli yhteys päättyy katkaisuun asiakaspäästä,
      # ohitetaan "websocket.close"-sanoman lähetys.
      katkaistu_asiakaspaasta = True

    finally:
      request.receive = receive.__wrapped__
      request.send = send.__wrapped__
      if not katkaistu_asiakaspaasta:
        await self._sulje_yhteys(request)
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
    avaava_kattely = await request.receive()
    assert avaava_kattely == {
      'type': 'websocket.connect'
    }, 'Avaava kättely epäonnistui: %r' % (
      avaava_kattely
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
        'type': 'websocket.accept',
        'subprotocol': hyvaksytty_protokolla,
      })
      request.protokolla = hyvaksytty_protokolla

    else:
      # Näkymä ei määrittele protokollaa; hyväksytään pyyntö.
      await request.send({'type': 'websocket.accept'})
      request.protokolla = None
    # async def _avaa_yhteys

  # class WebsocketAliprotokolla
