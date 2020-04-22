# -*- coding: utf-8 -*-

# pylint: disable=invalid-name

import asyncio
import os
import pty
import signal
import termios


class Paateprosessi(asyncio.Future):
  ''' Asynkroninen kääre `pty.fork`-prosessin ajamiseen. '''

  _kaynnissa_olevat_prosessit = {}
  _signaalinkasittelija_asennettu = False

  @classmethod
  def _prosessi_paattyi(cls):
    '''
    Käsittelymetodi `SIGCHLD`-signaalille.
    Merkitään ne prosessit päättyneiksi,
    joiden edustama PID on päättynyt.
    '''
    while True:
      try:
        pid, _ = os.waitpid(-1, os.WNOHANG)
      except OSError:
        break
      if pid <= 0:
        break
      prosessi = cls._kaynnissa_olevat_prosessit.pop(pid, None)
      if prosessi is not None and not prosessi.done():
        prosessi.set_result(0)
      # while True
    # def _prosessi_paattyi

  @classmethod
  def _asenna_signaalinkasittelija(cls):
    '''
    Asenna signaalinkäsittelijä.
    Huom. ajettava prosessin pääsäikeestä.
    '''
    if not cls._signaalinkasittelija_asennettu:
      oletus_sigchld = signal.getsignal(signal.SIGCHLD)
      def tarkistus(*args):
        cls._prosessi_paattyi()
        if callable(oletus_sigchld):
          oletus_sigchld(*args)
      signal.signal(signal.SIGCHLD, tarkistus)
      cls._signaalinkasittelija_asennettu = True
      # if not cls._signaalinkasittelija_asennettu
    # def _asenna_signaalinkasittelija

  @staticmethod
  # pylint: disable=inconsistent-return-statements
  def _kaynnista_prosessi(prosessi):
    '''
    Avaa uusi prosessi ja suorita annettu funktio.
    Huom. ajettava prosessin pääsäikeestä.
    '''
    pid, fd = pty.fork()
    if pid:
      return pid, fd
    try:
      prosessi()
    finally:
      # Suljetaan prosessi riippumatta mahdollisesta poikkeuksesta.
      os._exit(0) # pylint: disable=protected-access
    # def _kaynnista_prosessi

  async def __new__(cls, *args, **kwargs):
    ''' Asenna signaalinkäsittelijä. '''
    # Asenna globaali signaalinkäsittelijä ensimmäisen prosessin
    # luonnin yhteydessä.
    loop = asyncio.get_running_loop()
    loop.call_soon_threadsafe(cls._asenna_signaalinkasittelija)

    # Luo uusi prosessi asynkronisesti.
    prosessi = super().__new__(cls, *args, **kwargs)
    await prosessi.__init__(*args, **kwargs)
    return prosessi
    # def __new__

  async def __init__(
    self, prosessi, *, lukija=None, kirjoittaja=None, **kwargs
  ):
    '''
    Käynnistä aliprosessi.
    '''
    super().__init__(**kwargs)
    loop = self._loop

    # Irrota erillinen prosessi synkronisesti
    # ajossa olevan ohjelman pääsäikeessä.
    self.pid, self.fd = await loop.run_in_executor(
      None, self._kaynnista_prosessi, prosessi
    )

    # Aseta PTY-master-kahva `non-blocking`-tilaan.
    os.set_blocking(self.fd, False)

    # Lisää lukija ja kirjoittaja PTY-master-kahvalle.
    if lukija is not None:
      loop.add_reader(self.fd, lukija, self)
    if kirjoittaja is not None:
      loop.add_writer(self.fd, kirjoittaja, self)

    # Tallenna prosessi luokkakohtaiselle avointen prosessien listalle.
    self._kaynnissa_olevat_prosessit[self.pid] = self

    # Estetään Control-C-painallusta nostamasta SIGINT-signaalia,
    # joka sammuttaa koko ASGI-prosessin.
    t = termios.tcgetattr(self.fd)
    t[6][termios.VINTR] = 0
    termios.tcsetattr(self.fd, termios.TCSANOW, t)

    # pylint: disable=unused-variable
    @self.add_done_callback
    def done_callback(_):
      # Katkaistaan luku ja kirjoitus PTY:ltä, suljetaan kahva.
      self.get_loop().remove_reader(self.fd)
      self.get_loop().remove_writer(self.fd)
      os.close(self.fd)
      # def done_callback

    # def __init__

  def cancel(self):
    if super().cancel():
      try:
        os.kill(self.pid, signal.SIGHUP)
        os.kill(self.pid, signal.SIGKILL)
      except OSError:
        pass
      return True
    return False
    # def cancel

  # class Paateprosessi
