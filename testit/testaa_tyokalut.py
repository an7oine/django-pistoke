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
from pistoke.protokolla import (
  WebsocketProtokolla,
  WebsocketAliprotokolla,
)
from pistoke.tyokalut import (
  CsrfKattely,
  JsonLiikenne,
)
from pistoke.testaus import WebsocketPaate


class JSONKoodain(json.JSONEncoder):
  ''' Koodataan desimaaliluvut JSON-liukulukuesityksenä. '''

  class Desimaali(float):
    def __init__(self, value):
      # pylint: disable=super-init-not-called
      self._value = value
    def __repr__(self):
      return str(self._value)
    # class Desimaali

  def default(self, o):
    if isinstance(o, Decimal):
      return self.Desimaali(o)
    return super().default(o)
    # def default

  # class JSONKoodain


class JSONLatain(json.JSONDecoder):
  ''' Tulkitaan JSON-liukulukuesitykset desimaalilukuina. '''

  def __init__(self, *args, **kwargs):
    kwargs['parse_float'] = Decimal
    super().__init__(*args, **kwargs)
    # def __init__

  # class JSONLatain


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
@CsrfKattely
async def csrf(request):
  await request.send('ok')


@_testinakyma
@method_decorator(
  WebsocketAliprotokolla('summa', 'erotus'),
  name='websocket',
)
@method_decorator(
  JsonLiikenne(loads={'cls': JSONLatain}, dumps={'cls': JSONKoodain}),
  name='websocket'
)
@method_decorator(
  CsrfKattely(csrf_avain='csrfmiddlewaretoken', virhe_avain='virhe'),
  name='websocket',
)
class Aritmetiikkaa(WebsocketNakyma):
  async def websocket(self, request):
    async for termi_a in request:
      termi_b = await request.receive()
      await request.send(
        termi_a + termi_b if request.protokolla == 'summa'
        else termi_a - termi_b  # if request.protokolla == 'erotus'
      )
      # async for termi_a in request
    # async def websocket
  # class Aritmetiikkaa


###############
# TESTIMETODIT.

@override_settings(
  ROOT_URLCONF=__name__,
)
class Tyokalut(SimpleTestCase):
  # pylint: disable=unused-variable

  async_client_class = WebsocketPaate

  def setUp(self):
    super().setUp()
    self.async_client_csrf = self.async_client_class(
      enforce_csrf_checks=True
    )
    # def setUp

  async def testaa_virheellinen_csrf_a(self):
    '''
    Sulkeutuuko yhteys, kun sellaisenaan annettu CSRF ei täsmää?
    '''
    async with self.async_client_csrf.websocket('/csrf/') as websocket:
      await websocket.send('42')
      self.assertEqual(
        await websocket.receive(),
        'CSRF-avain puuttuu tai se on virheellinen!'
      )
      # async with self.async_client.websocket as websocket
    # async def testaa_virheellinen_csrf_a

  async def testaa_virheellinen_csrf_b(self):
    '''
    Sulkeutuuko yhteys, kun sellaisenaan annettu CSRF ei täsmää?
    '''
    async with self.async_client_csrf.websocket('/csrf/') as websocket:
      await websocket.send('virheellinen_csrf')
      self.assertEqual(
        await websocket.receive(),
        'CSRF-avain puuttuu tai se on virheellinen!'
      )
      # async with self.async_client.websocket as websocket
    # async def testaa_virheellinen_csrf_b

  async def testaa_puuttuva_aliprotokolla(self):
    '''
    Sulkeutuuko yhteys, kun protokolla puuttuu?
    '''
    with self.assertRaises(self.async_client_csrf.Http403):
      async with self.async_client.websocket(
        '/aritmetiikkaa/',
      ) as websocket:
        pass
    # async def testaa_puuttuva_aliprotokolla

  async def testaa_virheellinen_csrf_json_a(self):
    '''
    Sulkeutuuko yhteys, kun lähetetään epäkelpoa dataa?
    '''
    async with self.async_client_csrf.websocket(
      '/aritmetiikkaa/',
      protokolla='summa',
    ) as websocket:
      await websocket.send(b'jotain aivan muuta')
      self.assertEqual(await websocket.receive(), json.dumps({
        'virhe': 'Yhteyden muodostus epäonnistui!'
      }))
    # async def testaa_virheellinen_csrf_json_a

  async def testaa_virheellinen_csrf_json_b(self):
    '''
    Sulkeutuuko yhteys, kun JSON-muodossa lähetetään puuttuva CSRF?
    '''
    async with self.async_client_csrf.websocket(
      '/aritmetiikkaa/',
      protokolla='summa',
    ) as websocket:
      await websocket.send(json.dumps({'jotain': 'aivan muuta'}))
      self.assertEqual(await websocket.receive(), json.dumps({
        'virhe': 'CSRF-avain puuttuu tai se on virheellinen!'
      }))
    # async def testaa_virheellinen_csrf_json_b

  async def testaa_virheellinen_csrf_json_c(self):
    '''
    Sulkeutuuko yhteys, kun JSON-muodossa annettu CSRF ei täsmää?
    '''
    async with self.async_client_csrf.websocket(
      '/aritmetiikkaa/',
      protokolla='summa',
    ) as websocket:
      await websocket.send(json.dumps({
        'csrfmiddlewaretoken': 'virheellinen_csrf'
      }))
      self.assertEqual(await websocket.receive(), json.dumps({
        'virhe': 'CSRF-avain puuttuu tai se on virheellinen!'
      }))
    # async def testaa_virheellinen_csrf_json_c

  async def testaa_tasmaava_csrf(self):
    '''
    Avautuuko yhteys, kun JSON-muodossa annettu CSRF ei täsmää?
    '''
    async with self.async_client.websocket(
      '/aritmetiikkaa/',
      protokolla='summa',
    ) as websocket:
      await websocket.send(json.dumps({
        'csrfmiddlewaretoken': 'csrf'
      }))
      with self.assertRaises(asyncio.TimeoutError):
        # Huomaa, että näkymä odottaa dataa.
        await asyncio.wait_for(websocket.receive(), timeout=0.1)
      await websocket.send('123.45')
      with self.assertRaises(asyncio.TimeoutError):
        # Huomaa, että näkymä odottaa edelleen dataa.
        await asyncio.wait_for(websocket.receive(), timeout=0.1)
      # async with self.async_client.websocket
    # async def testaa_tasmaava_csrf

  async def testaa_summa(self):
    '''
    Laskeeko näkymä oikein?
    '''
    async with self.async_client.websocket(
      '/aritmetiikkaa/',
      protokolla='summa',
    ) as websocket:
      await websocket.send(json.dumps({
        'csrfmiddlewaretoken': 'csrf'
      }))
      await websocket.send('123.45')
      await websocket.send('54.321')
      self.assertEqual(await websocket.receive(), '177.771')
    # async def testaa_summa

  async def testaa_erotus(self):
    '''
    Laskeeko näkymä oikein?
    '''
    async with self.async_client.websocket(
      '/aritmetiikkaa/',
      protokolla='erotus',
    ) as websocket:
      await websocket.send(json.dumps({
        'csrfmiddlewaretoken': 'csrf'
      }))
      await websocket.send('123.45')
      await websocket.send('54.321')
      self.assertEqual(await websocket.receive(), '69.129')
      with self.assertRaises(asyncio.TimeoutError):
        # Huomaa, että näkymä odottaa uutta dataa.
        await asyncio.wait_for(websocket.receive(), timeout=0.1)
    # async def testaa_summa

  # class Tyokalut
