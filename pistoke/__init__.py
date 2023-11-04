# -*- coding: utf-8 -*-

from django.apps import AppConfig

from .nakyma import (
  WebsocketNakyma,
)

try:
  from .protokolla import (
    WebsocketProtokolla,
    WebsocketAliprotokolla,
  )
except ImportError:
  pass


class Pistoke(AppConfig):
  name = 'pistoke'
