# -*- coding: utf-8 -*-

from django.utils.functional import classproperty
from django.views import generic


class WebsocketNakyma(generic.View):
  '''
  Saateluokka; suora yksilöinti on kielletty.

  Lisää kunkin periytetyn näkymäluokan `http_method_names`-luetteloon
  tyyppi "websocket".

  Ohita (aina asynkroninen) `websocket`-metodi HTTP-metodien mahdollista
  asynkronisuutta tarkasteltaessa (Django 4.1+).

  Aseta kunkin periytetyn näkymäluokan `dispatch`-metodille määre
  `_websocket_protokolla` silloin, kun luokan `websocket`-metodi
  määrittelee käyttämänsä protokollan.
  '''

  @classmethod
  def __init_subclass__(cls, *args, **kwargs):
    super().__init_subclass__(*args, **kwargs)

    if 'websocket' not in cls.http_method_names:
      cls.http_method_names.append('websocket')

    if hasattr(cls, 'dispatch') \
    and hasattr(cls.websocket, 'protokolla'):
      # pylint: disable=protected-access, no-member
      cls.dispatch._websocket_protokolla = cls.websocket.protokolla
    # def __init_subclass__

  @classproperty
  def view_is_async(cls):
    # pylint: disable=no-self-argument
    http_method_names, cls.http_method_names = cls.http_method_names, [
      http for http in cls.http_method_names
      if http != 'websocket'
    ]
    paluu = super().view_is_async
    cls.http_method_names = http_method_names
    return paluu
    # def view_is_async

  def __new__(cls, *args, **kwargs):
    if cls == __class__:
      raise NotImplementedError
    return super().__new__(cls, *args, **kwargs)
    # def __new__

  async def websocket(self, request, *args, **kwargs):
    raise NotImplementedError

  # class WebsocketNakyma
