# -*- coding: utf-8 -*-

import setuptools

setuptools._install_setup_requires({'setup_requires': ['git-versiointi']})
from versiointi import asennustiedot

setuptools.setup(
  name='django-pistoke',
  description='Django-Websocket-laajennos',
  url='https://github.com/an7oine/django-pistoke.git',
  author='Antti Hautaniemi',
  author_email='antti.hautaniemi@pispalanit.fi',
  packages=setuptools.find_packages(),
  include_package_data=True,
  zip_safe=False,
  extras_require={
    'runserver': ['uvicorn'],
  },
  **asennustiedot(__file__),
)
