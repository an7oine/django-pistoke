# -*- coding: utf-8 -*-

from django.views import generic


class WebsocketNakyma(generic.View):
  '''
  Lisää kunkin periytetyn näkymäluokan `http_method_names`-luetteloon
  tyyppi "websocket".

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

  async def websocket(self, request, *args, **kwargs):
    raise NotImplementedError

  # class WebsocketNakyma
