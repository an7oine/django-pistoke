# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch
import sys

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management import call_command
from django.test import SimpleTestCase
from django.test.utils import override_settings


@override_settings(
  INSTALLED_APPS=settings.INSTALLED_APPS + ['django.contrib.staticfiles'],
  STATIC_URL='/static/',
)
class RunserverStaticFiles(SimpleTestCase):

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    try:
      del sys.modules['pistoke.management.commands.runserver']
    except KeyError:
      raise
    # def setUpClass

  def testaa_runserver_static_handler(self):
    ''' Alustetaanko `static_handler`-käsittelijä oikein? '''
    from pistoke.management.commands.runserver import static_handler
    self.assertIsNotNone(static_handler)
    # def testaa_runserver_static_handler

  # class RunserverStaticFiles
