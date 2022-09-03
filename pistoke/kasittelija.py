# -*- coding: utf-8 -*-

import asyncio
import json

from asgiref.sync import sync_to_async

import django
from django.conf import settings
from django.core.handlers.asgi import ASGIHandler, logger
from django.core import signals
from django.http import HttpResponse
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
    return super().__new__(cls, *args, **kwargs)
    # def __new__

  async def __call__(self, scope, receive, send):
    '''
    Asynkroninen, pyyntökohtainen kutsu.

    Vrt. django.core.handlers.asgi:ASGIHandler.__call__
    '''
    assert scope['type'] == 'websocket'

    # Tehdään Django-rutiinitoimet per saapuva pyyntö.
    set_script_prefix(self.get_script_prefix(scope))
    await sync_to_async(
      signals.request_started.send,
      thread_sensitive=True
    )(
      sender=self.__class__, scope=scope
    )

    # Muodostetaan WS-pyyntöolio.
    request = WebsocketPyynto(scope)

    # Luodaan jono saapuville syötteille.
    _syote = asyncio.Queue()
    async def syote():
      '''
      Erillinen metodi saapuvan syötteen käsittelyyn.

      Poimitaan ja toteutetaan mahdollinen katkaisupyyntö
      riippumatta siitä, lukeeko näkymärutiini syötettä vai ei.
      '''
      while True:
        sanoma = await receive()
        if sanoma['type'] == 'websocket.receive':
          await _syote.put(sanoma.get('text', sanoma.get('bytes', None)))
        elif sanoma['type'] == 'websocket.disconnect':
          break
        else:
          raise ValueError(sanoma['type'])
        # while True
      # async def syote

    async def _send(data):
      '''
      Lähetetään annettu data joko tekstinä tai tavujonona.
      '''
      if isinstance(data, str):
        return await send({'type': 'websocket.send', 'text': data})
      elif isinstance(data, bytearray):
        return await send({'type': 'websocket.send', 'bytes': bytes(data)})
      elif isinstance(data, bytes):
        return await send({'type': 'websocket.send', 'bytes': data})
      else:
        raise TypeError(str(type(data)))
      # async def _send

    # pylint: disable=attribute-defined-outside-init
    # Odotetaan hyväksyvää Websocket-kättelyä
    # (ks. `_get_response_async` alempana).
    # Mikäli yhteyspyyntöä ei hyväksytty, katkaistaan käsittely.
    async def kattely_receive():
      return await receive()
    async def kattely_send(data):
      await send(data)
      if data['type'] != 'websocket.accept':
        raise asyncio.CancelledError
      # Kääri ASGI-protokollan mukaiset `receive`- ja `send`-metodit
      # Websocket-metodeiksi.
      # Nämä asetetaan kättelyn jälkeen.
      request.receive = _syote.get
      request.send = _send
      # async def _send

    # Asetetaan pyyntökohtaiset `receive`- ja `send`-toteutukset kättelyn ajaksi.
    request.receive = kattely_receive
    request.send = kattely_send

    # Hae käsittelevä näkymärutiini tai mahdollinen virheviesti.
    # Tämä kutsuu mahdollisten avaavien välikkeiden (middleware) ketjua
    # ja lopuksi alla määriteltyä `_get_response_async`-metodia.
    # Metodi suorittaa ensin Websocket-kättelyn loppuun ja sen jälkeen
    # URL-taulun mukaisen näkymäfunktion (async def websocket(...): ...).
    try:
      nakyma = await self.get_response_async(request)
    except asyncio.CancelledError:
      # Yhteyspyyntöä ei hyväksytty.
      await sync_to_async(
        signals.request_finished.send,
        thread_sensitive=True
      )(
        sender=self.__class__
      )
      return
      # except asyncio.CancelledError

    # Palauta virhesanoma, mikäli `dispatch` tuotti alirutiinin
    # sijaan sellaisen.
    if not asyncio.iscoroutine(nakyma):
      nakyma._handler_class = self.__class__
      # Lähetetään HTTP-virhesanoma soveltuvin osin vastauksena
      # Websocket-pyynnölle.
      # Huomaa, että WS-kättely (connect + accept) oletetaan suoritetuksi
      # ennen virhesanoman muodostumista.
      if isinstance(vastaus := nakyma, HttpResponse):
        if hasattr(vastaus, 'is_rendered') and not vastaus.is_rendered:
          vastaus.render()
        await self.send_response(vastaus, send)
      else:
        logger.warning(
          f'Saatiin vastaus {nakyma!r}'
        )
      # Suljetaan yhteys ja tehdään Django-ylläpitotoimet per pyyntö.
      await send({'type': 'websocket.close'})
      await sync_to_async(
        signals.request_finished.send,
        thread_sensitive=True
      )(
        sender=self.__class__
      )
      return
      # if not asyncio.iscoroutine

    # Alustetaan taustalla ajettavat tehtävät.
    tehtavat = {
      asyncio.ensure_future(syote()),
      asyncio.ensure_future(nakyma),
    }

    # Odota siksi kunnes joko syöte katkaistaan
    # tai näkymärutiini on valmis.
    try:
      valmiit, tehtavat = await asyncio.wait(
        tehtavat, return_when=asyncio.FIRST_COMPLETED
      )

    finally:
      # Peruuta kesken jääneet tehtävät.
      for kesken in tehtavat:
        kesken.cancel()

      # Odota molemmat tehtävät loppuun ja poimi niiden tulokset.
      tulokset = await asyncio.gather(
        *valmiit,
        *tehtavat,
        return_exceptions=True
      )

      # Palauta mahdolliset poikkeukset paluusanomana, mikäli käytössä
      # on ohjaimia, jotka määrittelevät `process_exception`-metodin.
      # Muutoin nostetaan poikkeus sellaisenaan tässä.
      # Vrt. `django.core.handlers.base:BaseHandler._get_response_async`.
      try:
        for exc in tulokset:
          if isinstance(exc, asyncio.CancelledError):
            pass
          elif isinstance(exc, BaseException):
            vastaus = await sync_to_async(
              self.process_exception_by_middleware,
              thread_sensitive=True,
            )(exc, request)
            if vastaus is not None:
              await self.send_response(vastaus, request.send)
            else:
              raise exc

      finally:
        # WS-yhteyden sulkeva viesti lähetetään ulompaa käsittelypinossa.
        #await send({'type': 'websocket.close'})
        # Lähetä signaali päättyneestä pyynnöstä.
        # Huomaa, että normaalisti tämä tehdään paluusanoman
        # `close`-metodissa;
        # ks. `django.http.response.HttpResponseBase.close`.
        await sync_to_async(
          signals.request_finished.send,
          thread_sensitive=True
        )(
          sender=self.__class__
        )
        # finally
      # finally
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
    # pylint: disable=not-callable
    callback, callback_args, callback_kwargs = self.resolve_request(request)
    for middleware_method in self._view_middleware:
      await middleware_method(request, callback, callback_args, callback_kwargs)

    # Odotetaan avaavaa Websocket-kättelyä.
    assert (await request.receive())['type'] == 'websocket.connect'

    # Valitaan käytettävä WS-yhteysprotokolla, mikäli
    # näkymä määrittelee käytössä olevat protokollat.
    kaytettavissa_protokolla = getattr(
      callback, '_websocket_protokolla', []
    )
    pyydetty_protokolla = request.scope.get('subprotocols', [])
    if kaytettavissa_protokolla or pyydetty_protokolla:
      # pylint: disable=protected-access, no-member
      if isinstance(kaytettavissa_protokolla, str):
        kaytettavissa_protokolla = [kaytettavissa_protokolla]
      for hyvaksytty_protokolla in pyydetty_protokolla:
        if hyvaksytty_protokolla in kaytettavissa_protokolla:
          break
      else:
        # Yhtään yhteensopivaa protokollaa ei löytynyt (tai pyynnöllä
        # ei ollut annettu yhtään protokollaa).
        # Hylätään yhteyspyyntö.
        return await request.send({'type': 'websocket.close'})
      # Hyväksytään WS-yhteyspyyntö valittua protokollaa käyttäen.
      await request.send({
        # pylint: disable=undefined-loop-variable
        'type': 'websocket.accept',
        'subprotocol': hyvaksytty_protokolla,
      })
    else:
      # Näkymä ei määrittele protokollaa; hyväksytään pyyntö.
      await request.send({'type': 'websocket.accept'})

    # Kutsutaan `dispatch`-metodia synkronisesti, sillä se saattaa
    # aiheuttaa kantakyselyjä.
    # Huomaa, että paluusanomana saadaan `websocket`-metodin
    # palauttama alirutiini, joka palautetaan sellaisenaan.
    return await sync_to_async(callback, thread_sensitive=True)(
      request, *callback_args, **callback_kwargs
    )
    # async def _get_response_async

  async def send_response(self, response, send):
    '''
    Lähetä HTTP-virhesanoma soveltuvin osin
    Websocket-prokollan mukaisesti.

    Vrt. super-toteutus.
    '''
    # pylint: disable=invalid-name
    # Collect cookies into headers. Have to preserve header case as there
    # are some non-RFC compliant clients that require e.g. Content-Type.
    response_headers = []
    for header, value in response.items():
      response_headers.append((header, value))
    for c in response.cookies.values():
      response_headers.append(
        ('Set-Cookie', c.output(header='').strip())
      )
    # Initial response message.
    await send({
      'type': 'websocket.send',
      'text': json.dumps({
        'status': response.status_code,
        'headers': response_headers,
      }),
    })
    # Streaming responses need to be pinned to their iterator.
    if response.streaming:
      # Access `__iter__` and not `streaming_content` directly in case
      # it has been overridden in a subclass.
      for part in response:
        for chunk, _ in self.chunk_bytes(part):
          if chunk:
            await send({
              'type': 'websocket.send',
              'bytes': chunk,
            })
    # Other responses just need chunking.
    else:
      # Yield chunks of response.
      for chunk, _ in self.chunk_bytes(response.content):
        if chunk:
          await send({
            'type': 'websocket.send',
            'bytes': chunk,
          })
    response.close()
    # async def send_response

  # class WebsocketKasittelija
