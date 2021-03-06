#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2015 CGI, excluding businessintelligenceplugin/pentaho-data-integration
# See businessintelligenceplugin/pentaho-data-integration/LICENSE.txt
# for terms which apply to the contents of that folder.

from setuptools import setup, find_packages

setup(
    name='BusinessIntelligencePlugin', 
    version=0.1,
    description='Support Business Intelligence and Data Warehousing',
    author="Nick Piper", 
    author_email="nick.piper@cgi.com",
    maintainer="CGI CoreTeam",
    maintainer_email="coreteam.service.desk.se@cgi.com",
    contact="CGI CoreTeam",
    contact_email="coreteam.service.desk.se@cgi.com",
    classifiers=['License :: OSI Approved :: BSD License'],
    license='BSD',
    url='http://define.primeportal.com/',
    packages = ['businessintelligenceplugin'],
    package_data={
        'businessintelligenceplugin': [
            'htdocs/js/*.js',
            'templates/*',
            'default-transformation-templates/*/*',
            'job-templates/*/*',
            'pentaho-data-integration/*.sh',
            'pentaho-data-integration/launcher/*.jar',
            'pentaho-data-integration/launcher/*.properties',
            'pentaho-data-integration/launcher/*.xml',
            'pentaho-data-integration/pwd/*.pwd',
            'pentaho-data-integration/pwd/*.xml',
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
            'businessintelligenceplugin.carte = businessintelligenceplugin.carte',
            'businessintelligenceplugin.history = businessintelligenceplugin.history',
            'businessintelligenceplugin.views = businessintelligenceplugin.views',
            'businessintelligenceplugin.logging = businessintelligenceplugin.logging',
        ]
    }
)
