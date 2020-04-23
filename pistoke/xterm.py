# -*- coding: utf-8 -*-

# pylint: disable=invalid-name

import asyncio
import fcntl
import json
import os
import struct
import termios

from django.http import HttpResponse
from django.views import generic

from pistoke.nakyma import WebsocketNakyma
from pistoke.paate import Paateprosessi


class XtermNakyma(WebsocketNakyma, generic.TemplateView):
  '''
  Django-näkymä vuorovaikutteisen Websocket-yhteyden tarjoamiseen.

  Käyttöliittymän luontiin käytetään Xterm.JS-vimpainta.
  '''
  template_name = 'pistoke/xterm.html'

  class js_bool(int):
    ''' Näytetään totuusarvot javascript-muodossa: true/false. '''
    def __repr__(self):
      return repr(bool(self)).lower()
    # class js_bool

  # Xterm-ikkunan alustusparametrit.
  xterm = {
    'cursorBlink': js_bool(True),
    'macOptionIsMeta': js_bool(False),
    'scrollback': 5000,
  }

  def prosessi(self):
    ''' Päätteessä ajettava prosessi. '''
    raise NotImplementedError

  def get(self, request, *args, **kwargs):
    '''
    Varmista, että Websocket-protokolla on saatavilla.
    '''
    if getattr(request, 'websocket', None) is None:
      return HttpResponse(status=503)
    return super().get(request, *args, **kwargs)
    # def get

  @staticmethod
  async def _vastaanotto(receive, fd):
    '''
    Asynkroninen lukutehtävä: lue dataa ja syötä prosessille.
    '''
    while True:
      data = await receive()

      if isinstance(data, bytes):
        # Binäärisanoma: näppäinkoodi.
        # Control-C katkaisee syötteen.
        if data == b'\x03':
          break
        try:
          os.write(fd, data)
        except OSError:
          break

      elif isinstance(data, str):
        # Tekstisanoma: JSON-muotoinen IOCTL-ohjauskomento.
        data = json.loads(data, strict=False)
        if 'cols' in data and 'rows' in data:
          # Asetetaan ikkunan koko.
          fcntl.ioctl(
            fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", data['rows'], data['cols'], 0, 0)
          )
      # while True
    # async def _vastaanotto

  async def websocket(self, request, *args, **kwargs):
    # pylint: disable=unused-argument
    def lahetys(prosessi):
      '''
      Callback-tyyppinen rutiini datan lukemiseksi PTY:ltä.
      Kerää kaikki saatavilla oleva data, lähetä kerralla.
      '''
      data = bytearray()
      while True:
        try:
          data += os.read(prosessi.fd, 4096)
        except (IOError, BlockingIOError):
          break
        if not data:
          return
      asyncio.ensure_future(request.send(data.decode()))
      # def lahetys

    # Alusta pääteprosessi ja datan vastaanottotehtävä.
    paate = await Paateprosessi(self.prosessi, lukija=lahetys)
    tehtavat = {
      paate,
      asyncio.ensure_future(
        self._vastaanotto(request.receive, paate.fd)
      )
    }

    # Odota siksi kunnes joko syöte katkaistaan
    # tai pääteprosessi on valmis.
    try:
      _, tehtavat = await asyncio.wait(
        tehtavat, return_when=asyncio.FIRST_COMPLETED
      )

    # Peruuta kesken jääneet tehtävät ja odota ne loppuun.
    finally:
      for kesken in tehtavat:
        kesken.cancel()
      await asyncio.gather(*tehtavat, return_exceptions=True)
    # async def websocket

  # class XtermNakyma
