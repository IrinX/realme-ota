#!/usr/bin/python3

from setuptools import setup

setup(name='realme-ota',
      version='5.0',
      description="CLI tool to query OTA updates for RealmeUI / ColorOS / OxygenOS (BBK OTA endpoint).",
      author='Roger Ortiz & contributors',
      author_email='',
      install_requires=['requests', 'pycryptodome'],
      url='https://github.com/IrinX/realme-ota',
      packages=['realme_ota', 'realme_ota.utils'],
      scripts=['realme-ota']
)
