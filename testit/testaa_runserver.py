# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError
from django.core.management import call_command
from django.test import SimpleTestCase


class Runserver(SimpleTestCase):

  @patch('django.core.management.commands.runserver.Command.execute')
  @patch('pistoke.management.commands.runserver.Command.execute')
  def testaa_runserver_toteutus(self, mock1, mock2):
    ''' Suorittaako `python manage.py runserver` oikean toteutuksen? '''
    call_command('runserver')
    mock1.assert_called_once()
    mock2.assert_not_called()
    # def testaa_runserver_toteutus

  @patch('django.core.management.commands.runserver.Command.check_migrations', lambda self: None)
  def testaa_runserver_asgi_ei_uvicornia(self):
    ''' Nostaako `runserver --asgi` poikkeuksen ilman Uvicorn-asennusta? '''
    with self.assertRaises(
      CommandError,
      msg='komento `manage.py runserver --asgi` ei nosta poikkeusta'
    ) as konteksti:
      call_command('runserver', '--asgi')
    self.assertIn(
      'pip install uvicorn',
      str(konteksti.exception),
      msg='poikkeustekstissä ei mainita `pip install uvicorn`-komentoa'
    )
    # def testaa_runserver_asgi_ei_uvicornia

  @patch('django.core.management.commands.runserver.Command.check_migrations', lambda self: None)
  @patch('pistoke.management.commands.runserver.uvicorn')
  def testaa_runserver_asgi_uvicorn(self, mock):
    ''' Käynnistääkö `runserver --asgi` uvicorn-palvelimen? '''
    mock.run = MagicMock()
    call_command('runserver', '--asgi')
    mock.run.assert_called_once()
    # def testaa_runserver_asgi_uvicorn

  @patch('django.core.management.commands.runserver.Command.check_migrations', lambda self: None)
  @patch('django.core.management.commands.runserver.run')
  def testaa_runserver_wsgi(self, mock):
    ''' Käynnistääkö `runserver --wsgi` tavanomaisen Django-palvelimen? '''
    call_command('runserver', '--wsgi', '--noreload')
    mock.assert_called_once()
    # def testaa_runserver_wsgi

  # class Runserver
