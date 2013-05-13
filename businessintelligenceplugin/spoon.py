from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.db.api import DatabaseManager

import os
import tempfile
import subprocess

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties

class SpoonExecutor(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence spoon', '',
               """Start spoon
               """,
               self._complete_transformation_list, self._do_spoon)

    def _complete_transformation_list(self, args):
        pass

    def _do_spoon(self):
        tempdir = tempfile.mkdtemp()
        write_simple_jndi_properties(DatabaseManager(self.env).connection_uri,
                                     tempdir)

        # execute transform 

        spoon = subprocess.Popen(["./spoon.sh"], 
                                 executable="./spoon.sh",
                                 cwd=resource_filename(__name__, 'pentaho-data-integration'),
                                 env={'PENTAHO_DI_JAVA_OPTIONS': "-Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                      'DISPLAY': os.environ['DISPLAY']})

        spoon.wait()
