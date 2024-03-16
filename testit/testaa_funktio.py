# -*- coding: utf-8 -*-

import asyncio

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import path
from django.utils.decorators import method_decorator
from django import VERSION as django_versio

from pistoke.nakyma import WebsocketNakyma
from pistoke.protokolla import (
  WebsocketProtokolla,
  WebsocketAliprotokolla,
)
from pistoke.tyokalut import OriginPoikkeus
from pistoke.testaus import WebsocketTesti


###############
#
# TESTINÄKYMÄT.

urlpatterns = []
def _testinakyma(f):
  urlpatterns.append(
    path(f.__name__.lower() + '/', f)
  )
  return f

# Protokolla toteutettu käsin.
@_testinakyma
async def protokolla_kasin(request):
  assert await request.receive() == {'type': 'websocket.connect'}
  await request.send({'type': 'websocket.accept'})
  sanoma = await request.receive()
  assert isinstance(sanoma, dict) \
  and sanoma.get('type') == 'websocket.receive' \
  and sanoma.get('text') is not None
  await request.send({
    'type': 'websocket.send',
    'text': sanoma.get('text')
  })
  await request.send({
    'type': 'websocket.close',
  })
  assert await request.receive() == {'type': 'websocket.disconnect'}
  # async def protokolla_kasin


@_testinakyma
@OriginPoikkeus
@WebsocketProtokolla
async def kaiku_1(request):
  assert request.method == 'Websocket'
  sanoma = await request.receive()
  await request.send(sanoma)
  # async def kaiku_1


@_testinakyma
@OriginPoikkeus
@WebsocketProtokolla
async def kaiku_2(request):
  assert request.method == 'Websocket'
  sanoma = await request.receive()
  await request.send(sanoma)
  await asyncio.sleep(0.01)
  # async def kaiku_2


@_testinakyma
@WebsocketProtokolla
async def kaiku_iter(request):
  async for sanoma in request:
    await request.send(sanoma)
  # async def kaiku_iter


@_testinakyma
@WebsocketProtokolla
async def tyhja(request):
  pass
  # async def tyhja


@_testinakyma
@permission_required(
  perm='sovellus.oikeus',
  login_url='/',
  raise_exception=True
)
@WebsocketProtokolla
async def luottamuksellinen_f(request):
  pass
  # async def luottamuksellinen_f


@_testinakyma
@WebsocketAliprotokolla('yhta-suurempi', 'yhta-pienempi')
async def protokolla_f(request):
  if request.protokolla == 'yhta-suurempi':
    d = 1
  elif request.protokolla == 'yhta-pienempi':
    d = -1
  else:
    raise RuntimeError(request.protokolla)
  await request.send(f'{int(await request.receive()) + d}')
  # async def protokolla


###############
# TESTIMETODIT.

@override_settings(
  ROOT_URLCONF=__name__,
)
class FunktiopohjainenNakyma(WebsocketTesti):
  # pylint: disable=unused-variable

  async def testaa_protokolla_kasin(self):
    '''
    Toimiiko WS-pyyntö käsin määriteltyyn protokollaan oikein?
    '''
    async with self.async_client.websocket('/protokolla_kasin/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    # async def testaa_protokolla_kasin

  async def testaa_luottamuksellinen(self):
    '''
    Palauttaako tunnistautumaton WS-pyyntö 403-sanoman?

    Django 5.1+ nostaa `permission_required`-koristeessa PermissionDenied-
    poikkeuksen; ks. https://code.djangoproject.com/ticket/35030.
    '''
    with self.assertRaises(
      PermissionDenied if django_versio >= (5, 1)
      else self.async_client.Http403
    ):
      async with self.async_client.websocket('/luottamuksellinen_f/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luottamuksellinen

  async def testaa_kaiku_1(self):
    ''' Toimiiko funktiopohjainen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_1/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
      # async with self.async_client.websocket as websocket
    # async def testaa_kaiku_1

  async def testaa_kaiku_2(self):
    ''' Toimiiko funktiopohjainen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_2/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
      # async with self.async_client.websocket as websocket
    # async def testaa_kaiku_2

  async def testaa_iterointi_1(self):
    ''' Toimiiko iteraattorimuotoinen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_iter/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
      # async with self.async_client.websocket as websocket
    # async def testaa_iterointi_1

  async def testaa_iterointi_2(self):
    ''' Toimiiko iteraattorimuotoinen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_iter/') as websocket:
      await websocket.send('data')
      async for sanoma in websocket:
        self.assertEqual(sanoma, 'data')
        break
      # async with self.async_client.websocket as websocket
    # async def testaa_iterointi_2

  async def testaa_tyhja_a(self):
    ''' Onnistuuko tiedonsiirto tyhjään WS-näkymään? '''
    async with self.async_client.websocket('/tyhja/') as websocket:
      pass
    # async def testaa_tyhja_a

  async def testaa_tyhja_b(self):
    ''' Päättykö yhteys automaattisesti näkymän päättyessä? '''
    async with self.async_client.websocket('/tyhja/') as websocket:
      await websocket.receive()
    # async def testaa_tyhja_b

  async def testaa_tyhja_c(self):
    ''' Päättykö yhteys automaattisesti näkymän päättyessä? '''
    with self.assertRaises(self.async_client.SyotettaEiLuettu):
      async with self.async_client.websocket('/tyhja/') as websocket:
        await websocket.send('abc')
    # async def testaa_tyhja_c

  async def testaa_protokolla_a(self):
    ''' Pyydetty protokolla puuttuu -> 403 (funktio). '''
    with self.assertRaises(self.async_client.Http403):
      # Ei pyydettyä protokollaa -> 403.
      async with self.async_client.websocket('/protokolla_f/'):
        pass
      # with self.assertRaises
    # async def testaa_protokolla_a

  async def testaa_protokolla_b(self):
    ''' Ei yhteensopivaa protokollaa -> 403. '''
    with self.assertRaises(self.async_client.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/protokolla_f/',
        protokolla='yhtasuuri',
      ): pass
      # with self.assertRaises
    # async def testaa_protokolla_b

  async def testaa_protokolla_c(self):
    ''' Poimitaanko ensimmäinen pyydetty protokolla? '''
    async with self.async_client.websocket(
      '/protokolla_f/',
      protokolla=['yhta-pienempi', 'yhta-suurempi'],
    ) as websocket:
      # Asiakaspään (testi) antama protokollien
      # järjestys ratkaisee, joten tulos on -1.
      await websocket.send('42')
      self.assertEqual(await websocket.receive(), '41')
      # async with self.async_client.websocket as websocket
    # async def testaa_protokolla_c

  async def testaa_protokolla_d(self):
    ''' Poimitaanko yhteensopiva protokolla? '''
    async with self.async_client.websocket(
      '/protokolla_f/',
      protokolla=['yhtasuuri', 'yhta-suurempi']
    ) as websocket:
      await websocket.send('0')
      self.assertEqual(await websocket.receive(), '1')
      # async with self.async_client.websocket as websocket
    # async def testaa_protokolla_d

  async def testaa_protokolla_e(self):
    ''' Ei pyydettyä protokollaa -> 403. '''
    with self.assertRaises(self.async_client.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/protokolla_f/',
      ): pass
      # with self.assertRaises
    # async def testaa_protokolla_e

  # class TestaaWebsocketNakyma
