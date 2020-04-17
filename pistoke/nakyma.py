# -*- coding: utf-8 -*-

from django.views import generic


class WebsocketNakyma(generic.View):

  @classmethod
  def __init_subclass__(cls, *args, **kwargs):
    super().__init_subclass__(*args, **kwargs)
    if 'websocket' not in cls.http_method_names:
      cls.http_method_names.append('websocket')
    # def __init_subclass__

  async def websocket(self, request, *args, **kwargs):
    raise NotImplementedError

  # class WebsocketNakyma
