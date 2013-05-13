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
            'default-transformation-templates/*/*',
            'pentaho-data-integration/*.sh',
            'pentaho-data-integration/launcher/*.jar',
            'pentaho-data-integration/launcher/*.properties',
            'pentaho-data-integration/launcher/*.xml',
            'pentaho-data-integration/lib/*.jar',
            'pentaho-data-integration/libswt/*.jar',
            'pentaho-data-integration/libswt/linux/x86/*.jar',
            'pentaho-data-integration/libswt/linux/x86_64/*.jar',
            'pentaho-data-integration/libext/*.jar',
            'pentaho-data-integration/libext/jersey/*.jar',
            'pentaho-data-integration/libext/JDBC/*.jar',
            'pentaho-data-integration/libext/web/*.jar',
            'pentaho-data-integration/libext/webservices/*.jar',
            'pentaho-data-integration/libext/spring/*.jar',
            'pentaho-data-integration/libext/salesforce/*.jar',
            'pentaho-data-integration/libext/rules/*.jar',
            'pentaho-data-integration/libext/mondrian/*.jar',
            'pentaho-data-integration/libext/mondrian/config/*.properties',
            'pentaho-data-integration/libext/jfree/*.jar',
            'pentaho-data-integration/libext/commons/*.jar',
            'pentaho-data-integration/libext/reporting/*.jar',
            'pentaho-data-integration/libext/feeds/*.jar',
            'pentaho-data-integration/libext/eobjects/*.jar',
            'pentaho-data-integration/libext/poi/*.jar',
            'pentaho-data-integration/libext/elasticsearch/*.jar',
            'pentaho-data-integration/libext/google/*.jar',
            'pentaho-data-integration/libext/pentaho/*.jar',
        ]
    },
    entry_points = {
        'trac.plugins': [
            'businessintelligenceplugin.transforms = businessintelligenceplugin.transforms',
            'businessintelligenceplugin.spoon = businessintelligenceplugin.spoon',
        ]
    }
)
