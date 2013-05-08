#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2013 CGI IT UK Ltd

from setuptools import setup, find_packages

setup(
    name='businessintelligenceplugin', 
    version=0.1,
    description='Support Business Intelligence and Data Warehousing',
    author="Nick Piper", 
    author_email="nick.piper@cgi.com",
    license='BSD', 
    url='http://define.primeportal.com/',
    packages = ['businessintelligenceplugin'],
    package_data={
        'businessintelligenceplugin': [
            'default-transformation-templates/*',
        ]
    },
    entry_points = {
        'trac.plugins': [
            'businessintelligenceplugin.transforms = businessintelligenceplugin.transforms',
        ]
    }
)
