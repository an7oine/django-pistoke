# -*- coding: utf-8 -*-

import functools
import json


def json_viestiliikenne(*args, **kwargs):
  ''' Lähetä ja vastaanota JSON-muodossa. '''
  def _json_viestiliikenne(websocket, *, loads=None, dumps=None):
    @functools.wraps(websocket)
    async def _websocket(self, request, *args, **kwargs):

      @functools.wraps(request.receive)
      async def receive():
        return json.loads(
          await receive.__wrapped__(), **loads or {}
        )
      request.receive = receive

      @functools.wraps(request.send)
      async def send(viesti):
        return await send.__wrapped__(json.dumps(
          viesti, **dumps or {}
        ))
      request.send = send

      return await _websocket.__wrapped__(self, request, *args, **kwargs)
      # async def websocket

    return _websocket
    # def _json_viestiliikenne
  if args:
    return _json_viestiliikenne(*args, **kwargs)
  else:
    return functools.partial(_json_viestiliikenne, **kwargs)
  # def json_viestiliikenne


def csrf_tarkistus(*args, **kwargs):
  '''
  Tarkista ensimmäisen sanoman mukana toimitettu CSRF-tunniste.

  Jos parametri `csrf_avain` on annettu, poimitaan sanakirjamuotoisesta
  syötteestä.
  '''
  def _csrf_tarkistus(websocket, csrf_avain=None, virhe_avain=None):
    @functools.wraps(websocket)
    async def _websocket(self, request, *args, **kwargs):
      try:
        kattely = await request.receive()
      except ValueError:
        virhe = 'Yhteyden muodostus epäonnistui!'
        return await request.send({
          virhe_avain: virhe
        } if virhe_avain else virhe)

      # Koriste `method_decorator(csrf_exempt)` ohittaa tarkistuksen.
      if not getattr(getattr(self, 'websocket'), 'csrf_exempt', False) \
      and not request.tarkista_csrf(
        kattely.get(csrf_avain) if csrf_avain else kattely
      ):
        virhe = 'CSRF-avain puuttuu tai se on virheellinen!'
        return await request.send({
          virhe_avain: virhe
        } if virhe_avain else virhe)

      self._websocket_kattely = kattely
      return await _websocket.__wrapped__(self, request, *args, **kwargs)
      # async def _websocket

    return _websocket
    # def _csrf_tarkistus
  if args:
    return _csrf_tarkistus(*args, **kwargs)
  else:
    return functools.partial(_csrf_tarkistus, **kwargs)
  # def csrf_tarkistus


def origin_poikkeus(nakyma):
  ''' Ohita Origin-otsakkeen tarkistus Websocket-pyynnön yhteydessä. '''
  @functools.wraps(nakyma)
  def _nakyma(*args, **kwargs):
    return nakyma(*args, **kwargs)
  _nakyma.origin_poikkeus = True
  return _nakyma
  # def origin_poikkeus
