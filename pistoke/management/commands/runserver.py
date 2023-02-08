# -*- coding: utf-8 -*-

# pylint: disable=invalid-name
# pylint: disable=ungrouped-imports

from urllib.parse import urlparse

from django.conf import settings
from django.core.asgi import get_asgi_application
from django.core.handlers.asgi import ASGIHandler
from django.core.management import CommandError

try:
  import uvicorn
except ImportError:
  uvicorn = None

from pistoke.kasittelija import WebsocketKasittelija


if 'django.contrib.staticfiles' in settings.INSTALLED_APPS:
  # Mikäli `staticfiles` on käytössä,
  # (1) periytetään `runserver`-komento
  #     kyseisessä sovelluksessa periytetystä `runserver`-komennosta ja
  # (2) käytetään erillistä ASGI-käsittelijää
  #     staattisten tiedostojen tarjoilemiseen.
  from django.contrib.staticfiles.management.commands.runserver import (
    Command as _Command
  )
  from django.contrib.staticfiles.handlers import StaticFilesHandlerMixin
  from django.utils.cache import add_never_cache_headers
  class static_handler(StaticFilesHandlerMixin, ASGIHandler):
    ''' Vrt. staticfiles.handlers.ASGIStaticFilesHandler '''
    def __init__(self):
      # pylint: disable=super-init-not-called
      # Ei kutsuta `ASGIHandler.__init__`-metodia,
      # joka lataa välikkeet (middleware); niitä ei tarvita.
      self.base_url = urlparse(self.get_base_url())
      # def __init__
    def serve(self, request):
      # Kielletään staattisten tiedostojen paikallinen välimuisti.
      tulos = super().serve(request)
      add_never_cache_headers(tulos)
      return tulos
      # def serve
    # class static_handler
  # if 'django.contrib.staticfiles' in settings.INSTALLED_APPS

else:
  # Muuten periytetään suoraan django.core-versiosta.
  from django.core.management.commands.runserver import (
    Command as _Command
  )
  static_handler = None
  # else


class Kasittelija:
  ''' Käsittele tulevat ASGI-pyynnöt oikean käsittelijän läpi. '''

  def __init__(self, django, websocket, static=False):
    ''' Alusta tyyppikohtaiset käsittelijät. '''
    self.django = django
    self.websocket = websocket
    self.static = static_handler() if static_handler and static else None
    # def __init__

  async def __call__(self, scope, receive, send):
    ''' Välitä pyyntö oikealle käsittelijälle otsaketietojen mukaan. '''
    # pylint: disable=not-callable, protected-access
    if scope['type'] == 'http':
      if self.static and self.static._should_handle(scope['path']):
        return await self.static(scope, receive, send)
      else:
        return await self.django(scope, receive, send)
    elif scope['type'] == 'websocket':
      return await self.websocket(scope, receive, send)
    else:
      raise ValueError(f'tuntematon pyyntö: {scope["type"]}')
    # async def __call__

  # class Kasittelija


# Luodaan kaksi erillistä ASGI-käsittelyfunktiota:
# staticfilesillä ja ilman sitä.
uvicorn_application = Kasittelija(
  django=get_asgi_application(),
  websocket=WebsocketKasittelija(),
)
uvicorn_application_static = Kasittelija(
  django=get_asgi_application(),
  websocket=WebsocketKasittelija(),
  static=True,
)


class Command(_Command):

  def add_arguments(self, parser):
    # pylint: disable=protected-access
    super().add_arguments(parser)
    # Mikäli uvicorn on asennettu, käytetään oletuksena
    # ASGI-palvelinta ja lisätään vipu WSGI:n käyttöön.
    # Lisätään myös uvicorn-lokitustasot mahdollisina
    # komentoriviparametreinä '-v'-vivulle.
    for a in parser._actions:
      if a.dest == 'verbosity':
        a.type = lambda s: int(s) if s in ['0', '1', '2', '3'] else s
        a.choices += [
          'critical', 'error', 'warning', 'info', 'debug', 'trace'
        ]
        break
    # Lisätään parametrit `--wsgi` ja `--asgi` palvelimen tyypin
    # valitsemiseksi.
    oletus_asgi = bool(uvicorn is not None)
    parser.add_argument(
      '--asgi',
      action='store_true',
      dest='asgi',
      default=oletus_asgi,
      help=f'Käynnistä ASGI-palvelin (oletus{"" if oletus_asgi else " WSGI"}).'
    )
    parser.add_argument(
      '--wsgi',
      action='store_false',
      dest='asgi',
      default=oletus_asgi,
      help=f'Käynnistä WSGI-palvelin (oletus{" ASGI" if oletus_asgi else ""}).'
    )
    parser.add_argument(
      '--ssl-keyfile',
      default=getattr(self, 'oletus_ssl_keyfile', None),
      help=f'SSL-avaintiedosto (HTTPS)',
    )
    parser.add_argument(
      '--ssl-certfile',
      default=getattr(self, 'oletus_ssl_certfile', None),
      help=f'SSL-varmennetiedosto (HTTPS)',
    )
    # def add_arguments

  def asgi_run(self, addr, port, asgi_handler, **options):
    if uvicorn is None:
      raise CommandError(
        'ASGI-palvelimen ajaminen edellyttää `uvicorn`-paketin käyttöä.'
        ' Asenna se komennolla `pip install uvicorn`.'
      )
    uvicorn.run(
      asgi_handler,
      host=addr,
      port=port,
      log_level={
        0: 'critical',
        #: 'error',
        #: 'warning',
        1: 'info',
        2: 'debug',
        3: 'trace',
      }.get(options['verbosity'], options['verbosity'] or 'info'),
      reload=options['use_reloader'],
      reload_includes=['*'],
      reload_excludes=['*/.git/*'],
      **(
        {'use_colors': True} if options['force_color']
        else {'use_colors': False} if options['no_color']
        else {}
      ),
      **({
        'ssl_keyfile': options['ssl_keyfile'],
        'ssl_certfile': options['ssl_certfile'],
      } if options['ssl_keyfile'] and options['ssl_certfile'] else {}),
    )
    # def run

  def run(self, **options):
    if options.get('asgi', False) and options['use_reloader']:
      # Ohita mahdollinen automaattinen uudelleenlataus tässä.
      # Käytetään `uvicorn --reload`-parametriä.
      self.inner_run(None, **options)
    else:
      super().run(**options)
    # def run

  class ASGIPalvelin(Exception):
    ''' Poikkeusluokka ASGI-käsittelyn ilmaisemiseksi. '''

  def inner_run(self, *args, **options):
    '''
    Mikäli super() nostaa em. poikkeuksen,
    suoritetaan ASGI-käsittelijä (Uvicorn).
    '''
    try:
      super().inner_run(*args, **options)
    except self.ASGIPalvelin:
      # Poimitaan haluttu sovellus käsillä olevasta moduulista.
      handler = __name__ + (
        ':uvicorn_application_static'
        if options.get('use_static_handler', False) and (
          settings.DEBUG or options['insecure_serving']
        )
        else ':uvicorn_application'
      )
      self.asgi_run(self.addr, int(self.port), handler, **options)
    # def inner_run

  def get_handler(self, *args, **options):
    if options.get('asgi', False):
      # Katkaistaan `super().inner_run`-metodin suoritus ennen
      # WSGI-palvelimen käynnistystä.
      raise self.ASGIPalvelin
    return super().get_handler(*args, **options)
    # def get_handler

  # class Command
