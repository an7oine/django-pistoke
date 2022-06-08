# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
  setup_requires='git-versiointi>=1.6b4',
  name='django-pistoke',
  description='Django-Websocket-laajennos',
  url='https://github.com/an7oine/django-pistoke.git',
  author='Antti Hautaniemi',
  author_email='antti.hautaniemi@pispalanit.fi',
  licence='MIT',
  packages=find_packages(),
  include_package_data=True,
  zip_safe=False,
  install_requires=[
    'django>=3.1',
    'websockets>=8.0',
  ],
  extras_require={
    'runserver': ['uvicorn[standard]'],
  },
  entry_points={'django.asetukset': [
    'pistoke = pistoke.asetukset',
  ]},
)
