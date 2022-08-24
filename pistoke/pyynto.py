# -*- coding: utf-8 -*-

from django.core.handlers.asgi import ASGIRequest
from django.http import QueryDict


class WebsocketPyynto(ASGIRequest):
  '''
  Yksittäisen Websocket-pyynnön (istunnon) tiedot.

  Huomaa, että __init__ ei kutsu super-toteutusta.
  '''
  # pylint: disable=too-many-instance-attributes
  # pylint: disable=method-hidden
  # pylint: disable=invalid-name

  POST = QueryDict()
  FILES = {}

  def __init__(self, scope):
    # pylint: disable=super-init-not-called
    self.scope = scope
    self._post_parse_error = False
    self._read_started = False
    self.resolver_match = None
    self.script_name = self.scope.get('root_path', '')
    if self.script_name and scope['path'].startswith(self.script_name):
      self.path_info = scope['path'][len(self.script_name):]
    else:
      self.path_info = scope['path']
    if self.script_name:
      self.path = '%s/%s' % (
        self.script_name.rstrip('/'),
        self.path_info.replace('/', '', 1),
      )
    else:
      self.path = scope['path']

    self.method = 'Websocket'

    query_string = self.scope.get('query_string', '')
    if isinstance(query_string, bytes):
      query_string = query_string.decode()
    self.META = {
      'REQUEST_METHOD': self.method,
      'QUERY_STRING': query_string,
      'SCRIPT_NAME': self.script_name,
      'PATH_INFO': self.path_info,
      'wsgi.multithread': True,
      'wsgi.multiprocess': True,
    }
    if self.scope.get('client'):
      self.META['REMOTE_ADDR'] = self.scope['client'][0]
      self.META['REMOTE_HOST'] = self.META['REMOTE_ADDR']
      self.META['REMOTE_PORT'] = self.scope['client'][1]
    if self.scope.get('server'):
      self.META['SERVER_NAME'] = self.scope['server'][0]
      self.META['SERVER_PORT'] = str(self.scope['server'][1])
    else:
      self.META['SERVER_NAME'] = 'unknown'
      self.META['SERVER_PORT'] = '0'
    for name, value in self.scope.get('headers', []):
      name = name.decode('latin1')
      corrected_name = 'HTTP_%s' % name.upper().replace('-', '_')
      value = value.decode('latin1')
      if corrected_name in self.META:
        value = self.META[corrected_name] + ',' + value
      self.META[corrected_name] = value

    self.resolver_match = None
    # def __init__

  # class WebsocketPyynto
