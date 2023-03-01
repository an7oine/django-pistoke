# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
  setup_requires='git-versiointi>=1.6b9',
  name='django-pistoke',
  description='Django-Websocket-laajennos',
  url='https://github.com/an7oine/django-pistoke.git',
  author='Antti Hautaniemi',
  author_email='antti.hautaniemi@me.com',
  licence='MIT',
  packages=find_packages(exclude=['testit']),
  include_package_data=True,
  python_requires='>=3.6',
  install_requires=[
    'django>=3.2',
    'python-mmaare',
  ],
  extras_require={
    'runserver': ['uvicorn[standard]'],
    'websocket': ['websockets>=8.0'],
  },
  entry_points={'django.asetukset': [
    'pistoke = pistoke.asetukset',
  ]},
  zip_safe=False,
)
