# -*- coding: utf-8 -*-

# pylint: disable=invalid-name

import asyncio
import concurrent
import fcntl
import json
import os
import pty
import signal
import struct
import termios

from pistoke.nakyma import WebsocketNakyma


class XtermNakyma(WebsocketNakyma):
  '''
  Django-näkymä vuorovaikutteisen Websocket-yhteyden tarjoamiseen.

  Käyttöliittymän luontiin käytetään Xterm.JS-vimpainta.
  '''

  class js_bool(int):
    ''' Näytetään totuusarvot javascript-muodossa: true/false. '''
    def __repr__(self):
      return repr(bool(self)).lower()
    # class js_bool

  template_name = 'pistoke/xterm.html'

  # Xterm-ikkunan alustusparametrit.
  xterm = {
    'cursorBlink': js_bool(True),
    'macOptionIsMeta': js_bool(False),
    'scrollback': 5000,
  }

  def prosessi(self):
    raise NotImplementedError

  async def websocket(self, request, *args, **kwargs):
    # pylint: disable=unused-argument
    loop = asyncio.get_running_loop()

    def kaynnista():
      '''
      Erillinen, synkroninen funktio aliprosessin
      käynnistämiseksi.

      Tarvitaan, koska `fork()`-kutsu asynkronisesta kontekstista
      aiheuttaa poikkeuksen.
      '''
      # Avaa erillinen prosessi.
      (child_pid, fd) = pty.fork()
      if child_pid == 0:
        # pylint: disable=protected-access
        self.prosessi()
        os._exit(0)
        # if child_pid == 0

      # Aseta PTY-master-kahva `non-blocking`-tilaan.
      fcntl.fcntl(
        fd,
        fcntl.F_SETFL,
        fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK
      )
      # Aseta alustava ikkunan koko.
      fcntl.ioctl(
        fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 50, 0, 0)
      )
      return child_pid, fd
      # def kaynnista

    # Käynnistä aliprosessi synkronisesti.
    child_pid, fd = await loop.run_in_executor(None, kaynnista)

    async def vastaanotto():
      '''
      Asynkroninen lukutehtävä: lue dataa ja syötä prosessille.
      '''
      while True:
        data = await request.receive()

        if isinstance(data, bytes):
          # Binäärisanoma: näppäinkoodi.
          try:
            os.write(fd, data)
          except OSError:
            break

        elif isinstance(data, str):
          # Tekstisanoma: JSON-muotoinen IOCTL-ohjauskomento.
          data = json.loads(data, strict=False)
          if 'cols' in data and 'rows' in data:
            fcntl.ioctl(
              fd,
              termios.TIOCSWINSZ,
              struct.pack("HHHH", data['rows'], data['cols'], 0, 0)
            )
        # while True
      # async def vastaanotto
    vastaanotto_tehtava = asyncio.ensure_future(vastaanotto())

    # Luettelo, johon kerätään kaikki aloitetut lähetystehtävät.
    lahetystehtavat = []
    def lahetys():
      '''
      Callback-tyyppinen rutiini datan lukemiseksi PTY:ltä.
      Kerää kaikki saatavilla oleva data, lähetä kerralla.
      '''
      data = bytearray()
      while True:
        try:
          data += os.read(fd, 4096)
        except (IOError, BlockingIOError):
          break
      if data:
        lahetystehtavat.append(asyncio.ensure_future(
          request.send(data.decode())
        ))
      # def lahetys
    loop.add_reader(fd, lahetys)

    def odota():
      ''' Synkroninen rutiini aliprosessin odottelemiseen. '''
      # Odota aliprosessin päättymistä, mikäli se on
      # käynnissä.
      try:
        os.waitpid(child_pid, 0)
      except OSError:
        pass
      # Katkaistaan luku ja kirjoitus PTY:ltä, suljetaan kahva.
      loop.remove_reader(fd)
      loop.remove_writer(fd)
      os.close(fd)
      # def odota

    # Suorita aliprosessi.
    try:
      # Odota aliprosessin päättymistä synkronisesti erillisessä
      # suoritussäikeessä.
      await loop.run_in_executor(
        concurrent.futures.ThreadPoolExecutor(), odota
      )
    finally:
      # Katkaise aliprosessin pääteyhteys,
      # mikäli se on vielä käynnissä.
      try:
        os.kill(child_pid, signal.SIGHUP)
      except OSError:
        pass
      # Odota IO-tehtävien päättymistä.
      vastaanotto_tehtava.cancel()
      await asyncio.gather(
        vastaanotto_tehtava,
        *lahetystehtavat,
        return_exceptions=True
      )
    # async def websocket

  # class XtermNakyma
