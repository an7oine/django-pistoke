# -*- coding: utf-8 -*-

for i, sovellus in enumerate(INSTALLED_APPS):
  if sovellus == 'django.contrib.staticfiles':
    INSTALLED_APPS.insert(i, 'pistoke.Pistoke')
    break
else:
  INSTALLED_APPS.append('pistoke.Pistoke')

MIDDLEWARE.append('pistoke.ohjain.WebsocketOhjain')
MIDDLEWARE.append('pistoke.ohjain.OriginVaatimus')
