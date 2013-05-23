from trac.admin import IAdminCommandProvider
from trac.core import Component, implements

import os
import tempfile
import subprocess
import shutil

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties

class CarteExecutor(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence carte', '',
               """Start carte
               """,
               self._complete_args_list, self._do_carte)

    def _complete_args_list(self, args):
        pass

    def _do_carte(self):
        tempdir = tempfile.mkdtemp()
        write_simple_jndi_properties(self.env, tempdir)

        # execute transform 

        spoon = subprocess.Popen(["/bin/sh", "./carte.sh", "127.0.0.1", "8080"], # should come from args sometime maybe...
                                 executable="/bin/sh",
                                 cwd=resource_filename(__name__, 'pentaho-data-integration'),
                                 env={'PENTAHO_DI_JAVA_OPTIONS': "-Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                      'DISPLAY': os.environ['DISPLAY']})

        spoon.wait()

        shutil.rmtree(tempdir)
