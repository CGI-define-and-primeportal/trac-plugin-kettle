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
            'htdocs/*',
            'templates/*',
            'default-transformation-templates/*',
            'pentaho-data-integration/*',
            'pentaho-data-integration/launcher/*',
            'pentaho-data-integration/lib/*',
            'pentaho-data-integration/libswt/*',
            'pentaho-data-integration/libswt/linux/x86/*',
            'pentaho-data-integration/libswt/linux/x86_64/*',
            'pentaho-data-integration/libext/*',
            'pentaho-data-integration/libext/jersey/*',
            'pentaho-data-integration/libext/JDBC/*',
            'pentaho-data-integration/libext/web/*',
            'pentaho-data-integration/libext/webservices/*',
            'pentaho-data-integration/libext/spring/*',
            'pentaho-data-integration/libext/salesforce/*',
            'pentaho-data-integration/libext/rules/*',
            'pentaho-data-integration/libext/mondrian/*',
            'pentaho-data-integration/libext/mondrian/config/*',
            'pentaho-data-integration/libext/jfree/*',
            'pentaho-data-integration/libext/commons/*',
            'pentaho-data-integration/libext/reporting/*',
            'pentaho-data-integration/libext/feeds/*',
            'pentaho-data-integration/libext/eobjects/*',
            'pentaho-data-integration/libext/poi/*',
            'pentaho-data-integration/libext/elasticsearch/*',
            'pentaho-data-integration/libext/google/*',
            'pentaho-data-integration/libext/pentaho/*',
        ]
    },
    entry_points = {
        'trac.plugins': [
            'businessintelligenceplugin.transforms = businessintelligenceplugin.transforms',
        ]
    }
)
