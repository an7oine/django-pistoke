# -*- coding: utf-8 -*-

import functools
import json

# pylint: disable=unused-import
from .poistuvat import (
  csrf_tarkistus,
  json_viestiliikenne,
  protokolla,
)
# pylint: enable=unused-import


class Koriste:

  def __new__(cls, f=None, **kwargs):
    '''
    Kääritään olio annetun `f`-toteutuksen mukaan.
    Mikäli tätä ei annettu, palautetaan olion sijaan sulkeuma.
    '''
    if f is None:
      return functools.partial(cls, **kwargs)
    return functools.wraps(
      f
    )(super().__new__(cls))
    # def __new__

  def __init__(self, websocket):
    '''
    Parametriä `f` käytetään vain `__new__`-metodissa.
    '''
    # pylint: disable=unused-argument
    super().__init__()
    # def __init__

  def __call__(self, request, *args, **kwargs):
    return self.__wrapped__(request, *args, **kwargs)
    # def __call__

  # class Koriste


class OriginPoikkeus(Koriste):
  ''' Ohita Origin-otsakkeen tarkistus Websocket-pyynnön yhteydessä. '''
  origin_poikkeus = True
  # def origin_poikkeus


class JsonLiikenne(Koriste):

  def __init__(
    self,
    websocket, *,
    loads=None,
    dumps=None,
  ):
    super().__init__(websocket)
    self.loads = loads or {}
    self.dumps = dumps or {}
    # def __init__

  async def __call__(self, request, *args, **kwargs):
    @functools.wraps(request.receive)
    async def receive():
      return json.loads(
        await receive.__wrapped__(),
        **self.loads
      )
    @functools.wraps(request.send)
    async def send(s):
      return await send.__wrapped__(
        json.dumps(s, **self.dumps)
      )
    request.receive = receive
    request.send = send
    try:
      return await self.__wrapped__(
        request, *args, **kwargs
      )
    finally:
      request.receive = receive.__wrapped__
      request.send = send.__wrapped__
    # async def __call__

  # class JsonLiikenne


class CsrfKattely(Koriste):

  def __init__(
    self,
    websocket, *,
    csrf_avain=None,
    virhe_avain=None
  ):
    super().__init__(websocket)
    self.csrf_avain = csrf_avain
    self.virhe_avain = virhe_avain
    # def __init__

  async def __call__(self, request, *args, **kwargs):
    try:
      kattely = await request.receive()
    except ValueError:
      virhe = 'Yhteyden muodostus epäonnistui!'
      return await request.send({
        self.virhe_avain: virhe
      } if self.virhe_avain is not None else virhe)
    if not request.tarkista_csrf(
      kattely.get(self.csrf_avain)
      if self.csrf_avain else kattely
    ):
      virhe = 'CSRF-avain puuttuu tai se on virheellinen!'
      return await request.send({
        self.virhe_avain: virhe
      } if self.virhe_avain else virhe)

    request._csrf_kattely = kattely
    return await self.__wrapped__(
      request, *args, **kwargs
    )
    # async def __call__

  # class CsrfKattely
