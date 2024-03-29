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
from pistoke.testaus import WebsocketTesti


###############
#
# TESTINÄKYMÄT.

urlpatterns = []
def _testinakyma(lk):
  urlpatterns.append(
    path(lk.__name__.lower() + '/', lk.as_view())
  )
  return lk


# Abstraktit näkymät.
_testinakyma(WebsocketNakyma)

@_testinakyma
class Abstrakti(WebsocketNakyma):
  pass


# Ei protokollaa.
@_testinakyma
class Virheellinen_A(WebsocketNakyma):
  async def websocket(self, request):
    await request.send('pelkkää dataa')
@_testinakyma
class Virheellinen_B(WebsocketNakyma):
  async def websocket(self, request):
    await asyncio.sleep(0.1)
    await request.send('pelkkää dataa')


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
class LuokkapohjainenNakyma(WebsocketTesti):
  # pylint: disable=unused-variable

  async def testaa_abstrakti(self):
    with self.assertRaises(self.async_client.Http403):
      async with self.async_client.websocket('/websocketnakyma/') as websocket:
        pass
    with self.assertRaises(NotImplementedError):
      async with self.async_client.websocket('/abstrakti/') as websocket:
        pass
    # async def testaa_abstrakti

  async def testaa_virheellinen_a(self):
    '''
    Nostaako WS-pyyntö virheelliseen (ei protokollaa), heti päättyvään
    näkymään poikkeuksen?
    '''
    with self.assertRaises(self.async_client.NakymaPaattyi):
      async with self.async_client.websocket('/virheellinen_a/') as websocket:
        pass
      # with self.assertRaises
    # async def testaa_virheellinen_a

  async def testaa_virheellinen_b(self):
    '''
    Nostaako WS-pyyntö virheelliseen (ei protokollaa), hetken kestävään
    näkymään poikkeuksen?
    '''
    with self.assertRaises(self.async_client.KattelyEpaonnistui):
      async with self.async_client.websocket('/virheellinen_b/') as websocket:
        pass
      # with self.assertRaises
    # async def testaa_virheellinen_b

  async def testaa_kaiku(self):
    ''' Toimiiko luokkapohjainen WS-näkymä virheittä? '''
    async with self.async_client.websocket('/kaiku_lk/') as websocket:
      await websocket.send('Hei,')
      self.assertEqual(await websocket.receive(), 'Hei,')
      await websocket.send(' maailma.')
      self.assertEqual(await websocket.receive(), ' maailma.')
      # async with async_client.websocket as websocket
    # async def testaa_kaiku

  async def testaa_tunnussana(self):
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
    # async def testaa_tunnussana

  async def testaa_luottamuksellinen(self):
    ''' Palauttaako tunnistautumaton WS-pyyntö 403-sanoman? '''
    with self.assertRaises(self.async_client.Http403):
      async with self.async_client.websocket('/luottamuksellinen_lk/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luottamuksellinen

  async def testaa_protokolla(self):
    ''' Pyydetty protokolla puuttuu -> 403 (luokka). '''
    with self.assertRaises(self.async_client.Http403):
      async with self.async_client.websocket('/protokolla_lk/'):
        pass
      # with self.assertRaises
    # async def testaa_protokolla

  # class LuokkapohjainenNakyma
