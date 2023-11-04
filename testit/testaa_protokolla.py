# -*- coding: utf-8 -*-

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import path
from django.utils.decorators import method_decorator

from pistoke.nakyma import WebsocketNakyma
from pistoke.protokolla import (
  WebsocketProtokolla,
  WebsocketAliprotokolla,
)
from pistoke.testaus import WebsocketPaate


urlpatterns = []
def _nakyma(luokka_tai_funktio):
  ''' Muodosta näkymä ja lisää osoitteistoon. '''
  nakyma = (
    luokka_tai_funktio.as_view()
    if isinstance(luokka_tai_funktio, type)
    else luokka_tai_funktio
  )
  urlpatterns.append(
    path(f'{luokka_tai_funktio.__name__.lower()}/', nakyma),
  )
  return luokka_tai_funktio
  # def _nakyma


# Puuttuva protokolla.
@_nakyma
async def puuttuva_f(request):
  await request.send(await request.receive())

@_nakyma
class Puuttuva_LK(WebsocketNakyma):
  async def websocket(self, request):
    await request.send(await request.receive())


# Tyhjä protokolla, käsin toteutettu.
@_nakyma
async def kasikaytto_f(request):
  assert await request.receive() == {'type': 'websocket.connect'}
  await request.send({'type': 'websocket.accept'})
  data = await request.receive()
  await request.send({
    **data,
    'type': 'websocket.send'
  })
  await request.send({'type': 'websocket.close'})

@_nakyma
class Kasikaytto_LK(WebsocketNakyma):
  async def websocket(self, request):
    assert await request.receive() == {'type': 'websocket.connect'}
    await request.send({'type': 'websocket.accept'})
    data = await request.receive()
    await request.send({
      **data,
      'type': 'websocket.send'
    })
    await request.send({'type': 'websocket.close'})


# Perusprotokolla.
@_nakyma
@WebsocketProtokolla
async def protokolla_f(request):
  await request.send(await request.receive())

@_nakyma
@method_decorator(
  WebsocketProtokolla,
  name='websocket',
)
class Protokolla_LK(WebsocketNakyma):
  async def websocket(self, request):
    await request.send(await request.receive())


# Pääsynhallinta protokollan ulkopuolella.
@_nakyma
@permission_required(
  perm='sovellus.oikeus',
  login_url='/',
  raise_exception=True
)
@WebsocketProtokolla
async def paasy_ulkopuolella_f(request):
  await request.send(await request.receive())

@_nakyma
@method_decorator(
  WebsocketProtokolla,
  name='websocket',
)
class PaasyUlkopuolella_LK(
  PermissionRequiredMixin,
  WebsocketNakyma
):
  permission_required = 'sovellus.oikeus'
  login_url = '/'
  raise_exception = True
  async def websocket(self, request):
    await request.send(await request.receive())


# Pääsynhallinta protokollan sisällä.
@_nakyma
@WebsocketProtokolla
@permission_required(
  perm='sovellus.oikeus',
  login_url='/',
  raise_exception=True
)
async def paasy_sisapuolella_f(request):
  await request.send(await request.receive())

@_nakyma
@method_decorator(
  WebsocketProtokolla,
  name='websocket',
)
@method_decorator(
  permission_required(
    perm='sovellus.oikeus',
    login_url='/',
    raise_exception=True
  ),
  name='websocket',
)
class Paasy_Sisapuolella_LK(
  WebsocketNakyma
):
  async def websocket(self, request):
    await request.send(await request.receive())


# Websocket-aliprotokolla.
@_nakyma
@WebsocketAliprotokolla('yhta-suurempi', 'yhta-pienempi')
async def aliprotokolla_f(request):
  if request.protokolla == 'yhta-suurempi':
    d = 1
  elif request.protokolla == 'yhta-pienempi':
    d = -1
  else:
    raise RuntimeError(request.protokolla)
  await request.send(f'{int(await request.receive()) + d}')

@_nakyma
@method_decorator(
  WebsocketAliprotokolla('yhta-suurempi', 'yhta-pienempi'),
  name='websocket'
)
class Aliprotokolla_LK(WebsocketNakyma):
  async def websocket(self, request):
    if request.protokolla == 'yhta-suurempi':
      d = 1
    elif request.protokolla == 'yhta-pienempi':
      d = -1
    else:
      raise RuntimeError(request.protokolla)
    await request.send(f'{int(await request.receive()) + d}')


@override_settings(
  ROOT_URLCONF=__name__,
)
class WebsocketProtokollaTesti(SimpleTestCase):
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

  async def testaa_puuttuva(self):
    ''' Toimiiko puuttuva WS-protokolla oikein: poikkeus? '''
    with self.assertRaises(self.async_client.websocket.KattelyEpaonnistui):
      async with self.async_client.websocket('/puuttuva_f/') as websocket:
        await websocket.send('data')
        self.assertEqual(await websocket.receive(), 'data')
    with self.assertRaises(self.async_client.websocket.KattelyEpaonnistui):
      async with self.async_client.websocket('/puuttuva_lk/') as websocket:
        await websocket.send('data')
        self.assertEqual(await websocket.receive(), 'data')
      # with self.assertRaises
    # async def testaa_puuttuva

  async def testaa_kasikaytto(self):
    ''' Toimiiko käsin toteutettu WS-protokolla? '''
    async with self.async_client.websocket('/kasikaytto_f/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    async with self.async_client.websocket('/kasikaytto_lk/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    # async def testaa_protokolla

  async def testaa_protokolla(self):
    ''' Toimiiko WS-perusprotokolla? '''
    async with self.async_client.websocket('/protokolla_f/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    async with self.async_client.websocket('/protokolla_lk/') as websocket:
      await websocket.send('data')
      self.assertEqual(await websocket.receive(), 'data')
    # async def testaa_protokolla

  async def testaa_paasynhallinta_ulkopuolella(self):
    ''' Pääsynhallinta WS-protokollan ulkopuolella -> HTTP 403? '''
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/paasy_ulkopuolella_f/') as websocket:
        pass
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/paasy_ulkopuolella_lk/') as websocket:
        pass
    # async def testaa_paasynhallinta_ulkopuolella

  async def testaa_paasynhallinta_sisapuolella(self):
    ''' Pääsynhallinta WS-protokollan sisäpuolella -> WS 1001? '''
    with self.assertRaises(PermissionDenied):
      async with self.async_client.websocket('/paasy_sisapuolella_f/') as websocket:
        await websocket.receive()
    with self.assertRaises(PermissionDenied):
      async with self.async_client.websocket('/paasy_sisapuolella_lk/') as websocket:
        await websocket.receive()
    # async def testaa_paasynhallinta_sisapuolella

  async def testaa_puuttuva_aliprotokolla(self):
    ''' Hylätäänkö yhteyspyyntö, ellei aliprotokollaa ole määritetty? '''
    # Pyydetty protokolla puuttuu -> 403.
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/aliprotokolla_f/'):
        pass
    with self.assertRaises(self.async_client.websocket.Http403):
      async with self.async_client.websocket('/aliprotokolla_lk/'):
        pass
    # async def testaa_puuttuva_aliprotokolla

  async def testaa_epayhteensopiva_aliprotokolla(self):
    ''' Hylätäänkö yhteyspyyntö ilman yhteensopivaa aliprotokollaa? '''
    with self.assertRaises(self.async_client.websocket.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/aliprotokolla_f/',
        protokolla=['yhtasuuri', 'kahta-pienempi'],
      ):
        pass
    with self.assertRaises(self.async_client.websocket.Http403):
      # Ei yhteensopivaa protokollaa -> 403.
      async with self.async_client.websocket(
        '/aliprotokolla_lk/',
        protokolla=['yhtasuuri', 'kahta-pienempi'],
      ):
        pass
    # async def testaa_epayhteensopiva_aliprotokolla

  async def testaa_yhteensopiva_aliprotokolla(self):
    ''' Poimitaanko ensisijainen, yhteensopiva aliprotokolla? '''
    # Asiakaspään (testi) pyytämien protokollien järjestys ratkaisee,
    # joten protokollaksi valitaan "yhta-pienempi".
    async with self.async_client.websocket(
      '/aliprotokolla_f/',
      protokolla=['yhtasuuri', 'yhta-pienempi', 'yhta-suurempi'],
    ) as websocket:
      await websocket.send('42')
      self.assertEqual(await websocket.receive(), '41')
    async with self.async_client.websocket(
      '/aliprotokolla_lk/',
      protokolla=['yhtasuuri', 'yhta-pienempi', 'yhta-suurempi'],
    ) as websocket:
      await websocket.send('42')
      self.assertEqual(await websocket.receive(), '41')
    # async def testaa_yhteensopiva_aliprotokolla

  # class WebsocketProtokollaTesti
