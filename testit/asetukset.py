# -*- coding: utf-8 -*-

INSTALLED_APPS = [
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'pistoke',
]
MIDDLEWARE = [
  'django.middleware.security.SecurityMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django.middleware.locale.LocaleMiddleware',
  'django.middleware.common.CommonMiddleware',
  'django.middleware.csrf.CsrfViewMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
  'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

SECRET_KEY = 'epäjärjestelmällistyttämättömyydellänsäkäänköhän'

USE_TZ = True
