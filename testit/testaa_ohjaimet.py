# -*- coding: utf-8 -*-

from unittest.mock import patch
from unittest import skipUnless

from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import path
from django import VERSION

from pistoke.protokolla import WebsocketProtokolla
from pistoke.tyokalut import OriginPoikkeus
from pistoke.testaus import WebsocketPaate


###############
#
# TESTINÄKYMÄT.

def _testinakyma(f):
  return path(f.__name__.lower() + '/', f)

urlpatterns = []

@urlpatterns.append
@_testinakyma
async def post_nakyma(request):
  assert request.method == 'POST'
  return HttpResponse('ok')

@urlpatterns.append
@_testinakyma
@csrf_exempt
def post_poikkeus(request):
  # Huom. synkroninen, jotta `csrf_exempt` toimii oikein.
  assert request.method == 'POST'
  return HttpResponse('ok')

@urlpatterns.append
@_testinakyma
@WebsocketProtokolla
async def websocket_nakyma(request):
  assert request.method == 'Websocket'
  sanoma = await request.receive()
  await request.send(sanoma)

@urlpatterns.append
@_testinakyma
@OriginPoikkeus
@WebsocketProtokolla
async def websocket_poikkeus(request):
  assert request.method == 'Websocket'
  sanoma = await request.receive()
  await request.send(sanoma)

#
# TESTIT.

@override_settings(
  DEBUG=False,
  ROOT_URLCONF=__name__,
  ALLOWED_HOSTS=['testserver', 'sallittu-lahde', ],
  CSRF_TRUSTED_ORIGINS=['https://sallittu-lahde', ],
)
class TestaaWebsocketOhjaimet(SimpleTestCase):
  # pylint: disable=unused-variable

  async_client_class = WebsocketPaate

  def testaa_websocket_ohjaimet(self):
    # pylint: disable=no-name-in-module
    from pistoke.ohjain import websocket_ohjaimet
    self.assertEqual(
      websocket_ohjaimet,
      [
        # Vrt. testit/asetukset.py.
        'pistoke.ohjain.SecurityMiddleware',
        'pistoke.ohjain.IstuntoOhjain',
        'pistoke.ohjain.LocaleMiddleware',
        'pistoke.ohjain.CommonMiddleware',
        'pistoke.ohjain.CsrfOhjain',
        'pistoke.ohjain.AuthenticationMiddleware',
        'pistoke.ohjain.WebsocketOhjain',
        'pistoke.ohjain.OriginVaatimus',
      ],
      msg='Websocket-ohjaimet (Middleware) alustettiin väärin!'
    )
    # def testaa_websocket_ohjaimet

  # Origin-tarkistus testataan vain Django 4.0+ -ympäristössä.
  # Ohitetaan itse CSRF-tunnisteen tarkistus; tarkistetaan vain Origin.
  @skipUnless(VERSION >= (4, ), 'Django 4.0+')
  @patch(
    'django.middleware.csrf.CsrfViewMiddleware._check_token',
    lambda *args: True
  )
  async def testaa_post_pyynto(self):
    # Ajetaan Host/Origin/Referer-tarkistus.
    self.async_client.handler.enforce_csrf_checks = True

    tulos = await self.async_client.post(
      '/post_nakyma/',
      {},
      Origin='https://ei-sallittu-lahde',
    )
    self.assertEqual(
      tulos.status_code,
      403,
      msg='Origin-validointi ohitettiin!',
    )
    tulos = await self.async_client.post(
      '/post_nakyma/',
      {},
      Origin='https://sallittu-lahde',
    )
    self.assertEqual(
      tulos.status_code,
      200,
      msg='Origin-validointi epäonnistui!',
    )
    tulos = await self.async_client.post(
      '/post_poikkeus/',
      {},
      Origin='https://ei-sallittu-lahde',
    )
    self.assertEqual(
      tulos.status_code,
      200,
      msg='Origin-validointi suoritettiin virheellisesti!',
    )
    # async def testaa_post_pyynto

  async def testaa_websocket_pyynto(self):
    # Ei Origin-otsaketta: tarkistus ohitetaan.
    async with self.async_client.websocket(
      '/websocket_nakyma/',
      {}
    ) as ws:
      await ws.send('sanoma')

    # Ei-sallittu Origin: tarkistus hylkää pyynnön.
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket(
        '/websocket_nakyma/',
        {},
        Origin='htts://ei-sallittu-lahde',
      ) as ws:
        await ws.send('sanoma')

    # Sallittu Origin: tarkistus sallii pyynnön.
    async with self.async_client.websocket(
      '/websocket_nakyma/',
      {},
      Origin='htts://sallittu-lahde',
    ) as ws:
      await ws.send('sanoma')

    # Poikkeus: ohitetaan tarkistus.
    async with self.async_client.websocket(
      '/websocket_poikkeus/',
      {},
      Origin='htts://ei-sallittu-lahde',
    ) as ws:
      await ws.send('sanoma')
    # async def testaa_websocket_pyynto

  # class TestaaWebsocketOhjaimet
