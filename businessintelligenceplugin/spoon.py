from trac.admin import IAdminCommandProvider
from trac.core import Component, implements

import os
import tempfile
import subprocess
import shutil

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties

class SpoonExecutor(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence spoon', '[connection-uri] [ip]',
               """Start spoon. To connect to a different project's data, supply a connection-uri (same form as trac.ini has it). To override the hostname from that connection-uri, you can supply an IP address. This is useful to connect over an ssh tunnel to a remote database.
               """,
               None, self._do_spoon)
        yield ('businessintelligence simple-jndi', '[connection-uri] [ip]',
               """Write a JDNI properties file to "$HOME/.pentaho/simple-jndi". This is useful before starting report-designer/report-designer.sh, To connect to a different project's data, supply a connection-uri (same form as trac.ini has it). To override the hostname from that connection-uri, you can supply an IP address. This is useful to connect over an ssh tunnel to a remote database.
               """,
               None, self._do_jndi)

    def _do_spoon(self, connection_uri=None, ip=None):
        tempdir = tempfile.mkdtemp()

        write_simple_jndi_properties(self.env, tempdir, connection_uri, ip)

        # execute transform 

        spoon = subprocess.Popen(["/bin/sh", "./spoon.sh"], 
                                 executable="/bin/sh",
                                 cwd=resource_filename(__name__, 'pentaho-data-integration'),
                                 env={'PENTAHO_DI_JAVA_OPTIONS': "-Dfile.encoding=utf8 -Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                      'DISPLAY': os.environ['DISPLAY'],
                                      'HOME': os.environ['HOME']})

        spoon.wait()

        shutil.rmtree(tempdir)

    def _do_jndi(self, connection_uri=None, ip=None):
        write_simple_jndi_properties(self.env, os.path.expanduser("~/.pentaho"),
                                     connection_uri, ip)

