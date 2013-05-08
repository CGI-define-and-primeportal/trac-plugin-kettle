from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.db.api import DatabaseManager, _parse_db_str

import glob
import os
from lxml import etree
import tempfile
import shutil


from pkg_resources import require, resource_filename, ResolutionError

class TransformExecutor(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence transformation list', '',
               """List available transformations
               """,
               self._complete_transformation_list, self._do_list)
        yield ('businessintelligence transformation execute', '<transformation>',
               """Execute a particular transformation
               """,
               self._complete_transformation_execute, self._do_execute)

    def _complete_transformation_list(self, args):
        pass

    def _complete_transformation_execute(self, args):
        return self._list_transformation_files().keys()
    
    def _do_list(self):
        for ktr, details in self._list_transformation_files().items():
            print ktr
            for k, v in details.items():
                print " ", k, v

    def _do_execute(self, transformation):
        tempdir = tempfile.mkdtemp()


        connection_uri = DatabaseManager(self.env).connection_uri
        scheme, args = _parse_db_str(connection_uri)
        if scheme == 'sqlite':
            if not args['path'].startswith('/'):
                args['path'] = os.path.join(self.env.path, args['path'].lstrip('/'))
            jdbcDriver = "org.sqlite.JDBC"
            jdbcConnection = "jdbc:sqlite:%s" % args['path']
            jdbcUser = ""
            jdbcPassword = ""
        elif scheme == 'postgres':
            jdbcDriver = "org.postgresql.Driver"
            args['path'] = args['path'].strip("/")
            jdbcConnection = "jdbc:postgresql://%(host)s/%(path)s" % args
            jdbcUser = args['user']
            jdbcPassword = args['password']
        else:
            raise KeyError("Unknown database scheme %s" % scheme)

        os.mkdir(os.path.join(tempdir,"simple-jndi"))
        properties = open(os.path.join(os.path.join(tempdir,"simple-jndi"),"default.properties"),'w')
        properties.write("projectdata/type=javax.sql.DataSource\n")
        properties.write("projectdata/driver=%s\n" % jdbcDriver)
        properties.write("projectdata/url=%s\n" % jdbcConnection)
        properties.write("projectdata/user=%s\n" % jdbcUser)
        properties.write("projectdata/password=%s\n" % jdbcPassword)
        properties.close()

        # check out old results from SVN
        # execute transform 
        # check in new results to SVN

        shutil.rmtree(tempdir)

    ### 
    def _list_transformation_files(self):
        d = dict()
        for ktr in glob.glob(os.path.join(
            os.path.join(self.env.path, 'transformation-templates'),
            "*/*.ktr")) + \
            glob.glob(os.path.join(
                    resource_filename(__name__, 
                                      'default-transformation-templates'),
                    "*/*.ktr")):
            # refer to the ktr by the final folder and transformation filename
            ktr_name = "/".join(ktr.split(os.sep)[-2:])
            tree = etree.parse(ktr)
            root = tree.getroot()
            d[ktr_name] = {'name': root.find('info/name').text,
                           'description': root.find('info/description').text,
                           'version': root.find('info/trans_version').text}
        return d

