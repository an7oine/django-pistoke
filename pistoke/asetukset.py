# -*- coding: utf-8 -*-

for i, sovellus in enumerate(INSTALLED_APPS):
  if sovellus == 'django.contrib.staticfiles':
    INSTALLED_APPS.insert(i, 'pistoke.Pistoke')
    break
  elif sovellus == 'pistoke.Pistoke':
    break
else:
  INSTALLED_APPS.append('pistoke.Pistoke')

if 'pistoke.ohjain.WebsocketOhjain' not in MIDDLEWARE:
  MIDDLEWARE.append('pistoke.ohjain.WebsocketOhjain')
