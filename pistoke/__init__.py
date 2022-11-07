# -*- coding: utf-8 -*-

from django.apps import AppConfig

from .nakyma import (
  WebsocketNakyma,
)
from .protokolla import (
  WebsocketProtokolla,
  WebsocketAliprotokolla,
)


class Pistoke(AppConfig):
  name = 'pistoke'
