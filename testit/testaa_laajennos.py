# -*- coding: utf-8 -*-

import importlib
from importlib.metadata import entry_points
from sys import version_info

from django.conf import settings
from django.test import SimpleTestCase
from django.test.utils import override_settings


_entry_points = (
  # Ks. https://docs.python.org/3/library/importlib.metadata.html#entry-points.
  entry_points
  if version_info >= (3, 10)
  else lambda *, group: entry_points().get(group, ())
)


class Laajennos(SimpleTestCase):

  def testaa_rekisterointi(self):
    ''' Rekisteröidäänkö `asetukset.py` oikein laajennokseksi? '''
    for entry_point in _entry_points(group='django.asetukset'):
      if entry_point.value == 'pistoke.asetukset':
        break
    else:
      raise AssertionError('Pistoke-asetuslaajennosta ei rekisteröity!')
    # def testaa_rekisterointi

  def testaa_parametrit(self):
    ''' Tuottaako `asetukset.py` oikeat muutokset asetuksiin? '''
    spec = importlib.util.find_spec('pistoke.asetukset')
    self.assertIsNotNone(spec, 'asetuslaajennosta ei löydy')
    with open(spec.origin, encoding='utf-8') as laajennos_mod:
      # pylint: disable=exec-used
      exec(compile(laajennos_mod.read(), spec.origin, 'exec'), {
        'INSTALLED_APPS': settings.INSTALLED_APPS,
        'MIDDLEWARE': settings.MIDDLEWARE,
      })
    self.assertIn(
      'pistoke.Pistoke',
      settings.INSTALLED_APPS,
      msg='sovellusta ei lisätty'
    )
    self.assertIn(
      'pistoke.ohjain.WebsocketOhjain',
      settings.MIDDLEWARE,
      msg='välikettä (middleware) WebsocketOhjain ei lisätty'
    )
    # def testaa_parametrit

  @override_settings(
    INSTALLED_APPS=['django.contrib.staticfiles'],
  )
  def testaa_parametrien_jarjestys(self):
    ''' Tuottaako `asetukset.py` sovellukset oikeaan järjestykseen? '''
    spec = importlib.util.find_spec('pistoke.asetukset')
    self.assertIsNotNone(spec, 'asetuslaajennosta ei löydy')
    with open(spec.origin, encoding='utf-8') as laajennos_mod:
      # pylint: disable=exec-used
      exec(compile(laajennos_mod.read(), spec.origin, 'exec'), {
        'INSTALLED_APPS': settings.INSTALLED_APPS,
        'MIDDLEWARE': settings.MIDDLEWARE,
      })
    self.assertEqual(
      settings.INSTALLED_APPS[0],
      'pistoke.Pistoke',
      msg='sovellusjärjestys on väärä'
    )
    # def testaa_parametrien_jarjestys

  # class Asetukset
