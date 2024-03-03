import asyncio
from decimal import Decimal
import json

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import path
from django.utils.decorators import method_decorator

from pistoke.nakyma import WebsocketNakyma
from pistoke.protokolla import WebsocketProtokolla
from pistoke.testaus import WebsocketPaate


###############
#
# TESTINÄKYMÄT.

urlpatterns = []
def _testinakyma(nakyma):
  urlpatterns.append(
    path(
      nakyma.__name__.lower() + '/',
      nakyma.as_view() if isinstance(nakyma, type) else nakyma
    )
  )
  return nakyma


@_testinakyma
@WebsocketProtokolla
async def tyhja(request):
  pass


@_testinakyma
@WebsocketProtokolla
async def paattymaton_luku(request):
  async for __ in request:
    await asyncio.sleep(10)


@_testinakyma
@WebsocketProtokolla
async def kertakirjoitus(request):
  await request.send('42')


@_testinakyma
@WebsocketProtokolla
async def paattymaton_kirjoitus(request):
  while True:
    await request.send('42')
    await asyncio.sleep(1)


@_testinakyma
@WebsocketProtokolla
async def poikkeus_viiveella(request):
  try:
    await asyncio.sleep(0.2)
  finally:
    raise KeyError


###############
# TESTIMETODIT.

@override_settings(
  ROOT_URLCONF=__name__,
)
class Testaus(SimpleTestCase):
  # pylint: disable=unused-variable

  async_client_class = WebsocketPaate

  def setUp(self):
    super().setUp()
    self.async_client_lyhyt = self.async_client_class(
      websocket_aikakatkaisu=0.1,
    )
    self.async_client_pitka = self.async_client_class(
      websocket_aikakatkaisu=10.0,
    )
    self.async_client_ei_poikkeusta = self.async_client_class(
      raise_request_exception=False
    )
    # def setUp

  async def testaa_aikakatkaisu_lyhyt(self):
    ''' Aikakatkaistaanko pääteyhteys annetun ajan (0,1 s) kuluttua? '''
    with self.assertRaises(self.async_client.PaateyhteysAikakatkaistiin):
      async with self.async_client_lyhyt.websocket(
        '/paattymaton_luku/'
      ) as websocket:
        await asyncio.wait_for(websocket.receive(), timeout=0.2)
    # async def testaa_aikakatkaisu_lyhyt

  async def testaa_aikakatkaisu_oletus(self):
    ''' Aikakatkaistaanko pääteyhteys oletusarvon (1 s) kuluttua? '''
    with self.assertRaises(self.async_client.PaateyhteysAikakatkaistiin):
      async with self.async_client.websocket('/paattymaton_luku/') as websocket:
        await websocket.receive()
    # async def testaa_aikakatkaisu_oletus

  async def testaa_aikakatkaisu_pitka(self):
    ''' Kestääkö pääteyhteys annetun pituuden? '''
    async with self.async_client_pitka.websocket(
      '/paattymaton_luku/'
    ) as websocket:
      with self.assertRaises(asyncio.TimeoutError):
        await asyncio.wait_for(websocket.receive(), timeout=1.1)
    # async def testaa_aikakatkaisu_pitka

  async def testaa_keskeytys_luettaessa(self):
    ''' Nouseeko poikkeus, kun tulostetta jää lukematta? '''
    with self.assertRaises(self.async_client.TulostettaEiLuettu):
      async with self.async_client.websocket(
        '/kertakirjoitus/'
      ) as websocket:
        await asyncio.sleep(10.01)
    # async def testaa_keskeytys_luettaessa

  async def testaa_keskeytys_kirjoitettaessa(self):
    ''' Nouseeko poikkeus, kun syötettä jää lukematta? '''
    with self.assertRaises(self.async_client.SyotettaEiLuettu):
      async with self.async_client.websocket(
        '/tyhja/'
      ) as websocket:
        await websocket.send('42')
    # async def testaa_keskeytys_kirjoitettaessa

  async def testaa_poikkeus_nakymassa(self):
    ''' Nouseeko näkymän nostama poikkeus? '''
    with self.assertRaises(KeyError):
      async with self.async_client.websocket(
        '/poikkeus_viiveella/'
      ) as websocket:
        pass
    # async def testaa_poikkeus_nakymassa

  async def testaa_poikkeus_paatteessa(self):
    ''' Nouseeko pääteyhteyden (ennen näkymää) nostama poikkeus? '''
    with self.assertRaises(ValueError):
      async with self.async_client.websocket(
        '/poikkeus_viiveella/'
      ) as websocket:
        await asyncio.sleep(0.1)
        raise ValueError
    # async def testaa_poikkeus_paatteessa

  # class Testaus
