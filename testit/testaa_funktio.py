# -*- coding: utf-8 -*-

import asyncio

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import path
from django.utils.decorators import method_decorator

from pistoke.nakyma import WebsocketNakyma
from pistoke.protokolla import (
  WebsocketProtokolla,
  WebsocketAliprotokolla,
)
from pistoke.tyokalut import OriginPoikkeus
from pistoke.testaus import WebsocketPaate


###############
#
# TESTINÄKYMÄT.

urlpatterns = []
def _testinakyma(f):
  urlpatterns.append(
    path(
      f.__name__.lower() + '/',
      f.as_view() if hasattr(f, 'as_view') else f
    )
  )
  return f

# Ei protokollaa.
@_testinakyma
class Virheellinen(WebsocketNakyma):
  async def websocket(self, request):
    await request.send('pelkkää dataa')


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
  assert await request.receive() == {'type': 'websocket.disconnect'}
  await request.send({
    'type': 'websocket.close',
  })
  # async def protokolla_kasin


@_testinakyma
@OriginPoikkeus
@WebsocketProtokolla
async def kaiku_f(request):
  assert request.method == 'Websocket'
  sanoma = await request.receive()
  await request.send(sanoma)

@_testinakyma
@method_decorator(
  WebsocketProtokolla,
  name='websocket',
)
class Kaiku_LK(WebsocketNakyma):
  async def websocket(self, request):
    while True:
      kysymys = await request.receive()
      await request.send(kysymys)
  # class Kaiku_LK


@_testinakyma
class Tunnussana(WebsocketNakyma):
  @method_decorator(WebsocketProtokolla)
  async def websocket(self, request):
    while True:
      assert await request.receive() == b'tuli'
      await request.send(b'leimaus')

@_testinakyma
@WebsocketProtokolla
async def tyhja(request):
  pass


@_testinakyma
@permission_required(
  perm='sovellus.oikeus',
  login_url='/',
  raise_exception=True
)
@WebsocketProtokolla
async def luottamuksellinen_f(request):
  pass

@_testinakyma
@method_decorator(
  WebsocketProtokolla,
  name='websocket',
)
class Luottamuksellinen_LK(
  PermissionRequiredMixin,
  WebsocketNakyma
):
  permission_required = 'sovellus.oikeus'
  login_url = '/'
  raise_exception = True
  async def websocket(self, request):
    pass
  # class Luottamuksellinen_LK


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

@_testinakyma
@method_decorator(
  WebsocketAliprotokolla('yhta-suurempi', 'yhta-pienempi'),
  name='dispatch'
)
class Protokolla_LK(WebsocketNakyma):
  async def websocket(self, request):
    if request.protokolla == 'yhta-suurempi':
      d = 1
    elif request.protokolla == 'yhta-pienempi':
      d = -1
    else:
      raise RuntimeError(request.protokolla)
    await request.send(f'{int(await request.receive()) + d}')
    # async def websocket
  # class Protokolla_LK


###############
# TESTIMETODIT.

@override_settings(
  ROOT_URLCONF=__name__,
)
class TestaaWebsocketNakyma(SimpleTestCase):
  # pylint: disable=unused-variable

  async_client_class = WebsocketPaate

  async def testaa_olematon_403(self):
    ''' Palauttaako WS-pyyntö tuntemattomaan osoitteeseen 403-sanoman? '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/ei-ole/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_403

  async def testaa_virheellinen(self):
    '''
    Nostaako WS-pyyntö virheelliseen (ei protokollaa) näkymään poikkeuksen
    ASGI-rajapinnassa?
    '''
    with self.assertRaises(self.async_client.websocket.KattelyEpaonnistui):
      async with self.async_client.websocket('/virheellinen/') as websocket:
        await websocket.send('data')
      # with self.assertRaises
    # async def testaa_virheellinen

  async def testaa_protokolla_kasin(self):
    '''
    Toimiiko WS-pyyntö käsin määriteltyyn protokollaan oikein?
    '''
    async with self.async_client.websocket('/protokolla_kasin/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    # async def testaa_protokolla_kasin

  async def testaa_luottamuksellinen_f(self):
    ''' Palauttaako tunnistautumaton WS-pyyntö 403-sanoman? '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/luottamuksellinen_f/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luottamuksellinen_a

  async def testaa_luottamuksellinen_lk(self):
    ''' Palauttaako tunnistautumaton WS-pyyntö 403-sanoman? '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/luottamuksellinen_lk/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luottamuksellinen_a

  async def testaa_funktio(self):
    ''' Toimiiko funktiopohjainen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_f/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
      # async with self.async_client.websocket as websocket
    # async def testaa_funktio_1

  async def testaa_luokka_a(self):
    ''' Toimiiko luokkapohjainen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_lk/') as websocket:
      await websocket.send('Hei,')
      self.assertEqual(await websocket.receive(), 'Hei,')
      await websocket.send(' maailma.')
      self.assertEqual(await websocket.receive(), ' maailma.')
      # async with async_client.websocket as websocket
    # async def testaa_luokka_a

  async def testaa_luokka_b(self):
    ''' Nouseeko näkymän nostama poikkeus? '''
    # Huomaa, että näkymän nostama poikkeus nousee kutsuvaan
    # koodiin vasta ensin mainitun suorituksen päätyttyä.
    with self.assertRaises(AssertionError):
      async with self.async_client.websocket('/tunnussana/') as websocket:
        await websocket.send(b'tuli')
        self.assertEqual(await websocket.receive(), b'leimaus')
        await websocket.send('vesi')
        # async with async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luokka_b

  async def testaa_tyhja_a(self):
    ''' Onnistuuko tiedonsiirto tyhjään WS-näkymään? '''
    async with self.async_client.websocket('/tyhja/') as websocket:
      pass
    # async def testaa_tyhja_a

  async def testaa_tyhja_b(self):
    ''' Nostaako vastaanotto päättyneestä WS-näkymästä poikkeuksen? '''
    with self.assertRaises(asyncio.CancelledError):
      async with self.async_client.websocket('/tyhja/') as websocket:
        await asyncio.sleep(0.01)
        await websocket.receive()
      # async with self.async_client.websocket as websocket
    # async def testaa_tyhja_b

  async def testaa_tyhja_c(self):
    ''' Nostaako lähetys päättyneeseen WS-näkymään poikkeuksen? '''
    with self.assertRaises(asyncio.CancelledError):
      async with self.async_client.websocket('/tyhja/') as websocket:
        await asyncio.sleep(0.01)
        await websocket.send('abc')
    # async def testaa_tyhja_c

  async def testaa_protokolla_a(self):
    ''' Pyydetty protokolla puuttuu -> 403 (funktio). '''
    with self.assertRaises(self.async_client.websocket.Http403):
      # Ei pyydettyä protokollaa -> 403.
      async with self.async_client.websocket('/protokolla_f/'):
        pass
      # with self.assertRaises
    # async def testaa_protokolla_a

  async def testaa_protokolla_b(self):
    ''' Pyydetty protokolla puuttuu -> 403 (luokka). '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/protokolla_lk/'):
        pass
      # with self.assertRaises
    # async def testaa_protokolla_b

  async def testaa_protokolla_c(self):
    ''' Ei yhteensopivaa protokollaa -> 403. '''
    with self.assertRaises(self.async_client.websocket.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/protokolla_f/',
        protokolla='yhtasuuri',
      ): pass
      # with self.assertRaises
    # async def testaa_protokolla_c

  async def testaa_protokolla_d(self):
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
    # async def testaa_protokolla_d

  async def testaa_protokolla_e(self):
    ''' Poimitaanko yhteensopiva protokolla? '''
    async with self.async_client.websocket(
      '/protokolla_f/',
      protokolla=['yhtasuuri', 'yhta-suurempi']
    ) as websocket:
      await websocket.send('0')
      self.assertEqual(await websocket.receive(), '1')
      # async with self.async_client.websocket as websocket
    # async def testaa_protokolla

  async def testaa_protokolla_f(self):
    ''' Ei pyydettyä protokollaa -> 403. '''
    with self.assertRaises(self.async_client.websocket.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/protokolla_f/',
      ): pass
      # with self.assertRaises
    # async def testaa_protokolla_c

  # class TestaaWebsocketNakyma
