# -*- coding: utf-8 -*-

from django.conf import settings
from django.core.handlers.asgi import ASGIRequest
from django.http import QueryDict
from django import VERSION as django_version


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

  def __init__(self, scope, receive, send):
    # pylint: disable=super-init-not-called
    self.scope = scope
    self.receive = receive
    self.send = send
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

  # Lisätään `tarkista_csrf`-metodin toteutus Django-versiokohtaisesti.
  # pylint: disable=no-name-in-module, undefined-variable
  if django_version >= (4, 1):
    def tarkista_csrf(self, csrf_token):
      ''' Vrt. django.middleware.csrf:CsrfMiddleware._check_token. '''
      # pylint: disable=no-member
      from django.middleware.csrf import (
        _check_token_format,
        _does_token_match,
        InvalidTokenFormat,
      )
      if csrf_token is None:
        return False
      if settings.CSRF_USE_SESSIONS:
        csrf_secret = self.session.get(CSRF_SESSION_KEY)
      else:
        csrf_secret = self.COOKIES[settings.CSRF_COOKIE_NAME]
      if csrf_secret is None:
        return False
      try:
        _check_token_format(csrf_token)
        _check_token_format(csrf_secret)
      except InvalidTokenFormat:
        return False
      return _does_token_match(csrf_token, csrf_secret)
      # def tarkista_csrf
    # if django_version >= 4.1
  else:
    if django_version >= (4, 0):
      from django.middleware.csrf import _does_token_match
    else:
      from django.middleware.csrf import (
        _compare_masked_tokens as _does_token_match
      )
    from django.middleware.csrf import _sanitize_token
    def tarkista_csrf(self, csrf_token):
      return csrf_token \
      and self.META.get('CSRF_COOKIE') \
      and _does_token_match(
        _sanitize_token(csrf_token),
        self.META.get('CSRF_COOKIE'),
      )
    # else (if django_version < 4.1)
  # pylint: enable=no-name-in-module, undefined-variable
  tarkista_csrf.__doc__ = '''
  Tarkista pyyntödatan mukana saatu CSRF-tunniste evästeenä
  annettua tunnistetta vasten.
  '''

  # class WebsocketPyynto
