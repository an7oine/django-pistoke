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
def _testinakyma(lk):
  urlpatterns.append(
    path(lk.__name__.lower() + '/', lk.as_view())
  )
  return lk

# Ei protokollaa.
@_testinakyma
class Virheellinen(WebsocketNakyma):
  async def websocket(self, request):
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
class LuokkapohjainenNakyma(SimpleTestCase):
  # pylint: disable=unused-variable

  async_client_class = WebsocketPaate

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
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/luottamuksellinen_lk/') as websocket:
        pass
        # async with self.async_client.websocket as websocket
      # with self.assertRaises
    # async def testaa_luottamuksellinen

  async def testaa_protokolla(self):
    ''' Pyydetty protokolla puuttuu -> 403 (luokka). '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/protokolla_lk/'):
        pass
      # with self.assertRaises
    # async def testaa_protokolla

  # class LuokkapohjainenNakyma
