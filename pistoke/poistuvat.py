# -*- coding: utf-8 -*-

import warnings


def json_viestiliikenne(*args, **kwargs):
  ''' Lähetä ja vastaanota JSON-muodossa. '''
  from pistoke.tyokalut import JsonLiikenne
  warnings.warn(
    'pistoke.tyokalut.json_viestiliikenne() on poistunut käytöstä.'
    ' Korvaava koriste: pistoke.tyokalut.JsonLiikenne.',
    DeprecationWarning,
    stacklevel=2,
  )
  return JsonLiikenne(*args, **kwargs)
  # def json_viestiliikenne


def protokolla(*ws_protokolla):
  from pistoke.protokolla import WebsocketAliprotokolla
  warnings.warn(
    'pistoke.tyokalut.protokolla() on poistunut käytöstä.'
    ' Korvaava protokolla: pistoke.protokolla.WebsocketAliprotokolla.',
    DeprecationWarning,
    stacklevel=2,
  )
  return WebsocketAliprotokolla(*ws_protokolla)
  # def protokolla


def csrf_tarkistus(*args, **kwargs):
  '''
  Tarkista ensimmäisen sanoman mukana toimitettu CSRF-tunniste.

  Jos parametri `csrf_avain` on annettu, poimitaan sanakirjamuotoisesta
  syötteestä.
  '''
  from pistoke.tyokalut import CsrfKattely
  warnings.warn(
    'pistoke.tyokalut.csrf_tarkistus() on poistunut käytöstä.'
    ' Korvaava koriste: pistoke.tyokalut.CsrfKattely.',
    DeprecationWarning,
    stacklevel=2,
  )
  return CsrfKattely(*args, **kwargs)
  # def csrf_tarkistus
