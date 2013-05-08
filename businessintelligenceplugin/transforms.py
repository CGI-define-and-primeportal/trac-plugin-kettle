from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.db.api import DatabaseManager, _parse_db_str
from trac.versioncontrol.api import RepositoryManager, NoSuchNode
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler
from trac.web.chrome import ITemplateProvider, add_javascript, add_stylesheet
from tracrpc.api import IXMLRPCHandler

from trac_browser_svn_ops.svn_fs import SubversionWriter

import glob
import os
from lxml import etree
import tempfile
import shutil
import subprocess
import thread

from pkg_resources import require, resource_filename, ResolutionError

class TransformExecutor(Component):
    implements(IAdminCommandProvider,
               IXMLRPCHandler,
               IPermissionRequestor,
               IRequestHandler,
               ITemplateProvider)

    # IRequestHandler methods

    def match_request(self, req):
        if req.path_info == "/businessintelligence":
            return True

    def process_request(self, req):
        if req.method == "GET":
            req.perm.require("BUSINESSINTELLIGENCE_TRANSFORMATION_LIST")
            data = {'transformations': self._list_transformation_files()}
            add_stylesheet(req, 'contextmenu/contextmenu.css')
            add_javascript(req, 'contextmenu/contextmenu.js')
            add_stylesheet(req, 'common/css/browser.css')
            return "listtransformations.html", data, None
        elif req.method == "POST":
            req.perm.require("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE")
            if req.args['submitButton'] == "execute_async":
                thread.start_new_thread(self._do_execute_transformation, (req.args['transform'],))
            else:
                self._do_execute_transformation(req.args['transform'])
            req.redirect(req.href.businessintelligence())

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('businessintelligenceplugin', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

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
        print "Generated revisions %s" % self._do_execute_transformation(transformation)

    # IXMLRPCHandler methods
    def xmlrpc_namespace(self):
        return 'businessintelligence'

    def xmlrpc_methods(self):
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_LIST", ((dict,),), self.list_transformations)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((None, str),), self.execute_transformation)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((list, str),), self.execute_transformation_sync)

    def list_transformations(self, req):
        return self._list_transformation_files()

    def execute_transformation(self, req, transformation):
        """Executes transformation (generally to generate ticket report).

        Runs asynchronously as this can take a variable amount of time depending on transformation complexity.

        No useful return code provided."""
        thread.start_new_thread(self._do_execute_transformation, (transformation,))

    def execute_transformation_sync(self, req, transformation):
        """Synchronous executation of transformation"""
        return self._do_execute_transformation(transformation)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ["BUSINESSINTELLIGENCE_TRANSFORMATION_LIST",
                "BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE"]

    #####

    def _do_execute_transformation(self, transformation):
        tempdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tempdir,"simple-jndi"))
        os.mkdir(os.path.join(tempdir, "svn"))

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

        properties = open(os.path.join(os.path.join(tempdir,"simple-jndi"), "default.properties"), 'w')
        properties.write("projectdata/type=javax.sql.DataSource\n")
        properties.write("projectdata/driver=%s\n" % jdbcDriver)
        properties.write("projectdata/url=%s\n" % jdbcConnection)
        properties.write("projectdata/user=%s\n" % jdbcUser)
        properties.write("projectdata/password=%s\n" % jdbcPassword)
        properties.close()

        # execute transform 

        executable = os.path.join(resource_filename(__name__, 'pentaho-data-integration'),"pan.sh")

        params = {'DefineInternal.Input.Directory': os.path.split(self._list_transformation_files()[transformation]['full_path'])[0],
                  'DefineInternal.Output.Directory': os.path.join(tempdir, "svn"),
                  'DefineInternal.Project.ShortName': os.path.split(self.env.path)[1]}

        args = [
            executable,
            "-file", self._list_transformation_files()[transformation]['full_path'],
            "-level", "Detailed",
            ]
        for k, v in params.items():
            args.append("-param:%s=%s" % (k, v))

        self.log.debug("Running %s with %s", executable, args)

        # this bit of Python isn't so good :-( I'll just merge the stdout and stderr streams...

        # http://stackoverflow.com/questions/6809590/merging-a-python-scripts-subprocess-stdout-and-stderr-while-keeping-them-disti
        # http://codereview.stackexchange.com/questions/6567/how-to-redirect-a-subprocesses-output-stdout-and-stderr-to-logging-module
        pan = subprocess.Popen(args, 
                               executable=executable,
                               env={'PENTAHO_DI_JAVA_OPTIONS': "-Djava.awt.headless=true -Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi")},
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                               
        while pan.poll() is None:
            self.log.debug("Pan output: %s", pan.stdout.readline())
        self.log.info("Pan returned %s" % pan.returncode)

        if pan.returncode:
            raise RuntimeError("Business Intelligence subprocess pan failed")

        reponame, repos, path = RepositoryManager(self.env).get_repository_by_path('')
        svn_writer = SubversionWriter(self.env, repos, "reporting")
        revs = []
        for filename in os.listdir(os.path.join(tempdir, "svn")):
            self.log.info("Uploading %s" % filename)
            writer = SubversionWriter(self.env, repos, "reporting")
            file_data = open(os.path.join(os.path.join(tempdir, "svn"), filename)).read()

            for path in ["define-reports", 
                         "define-reports/%s" % os.path.split(transformation)[0]]:
                try:
                    repos.get_node(path)
                except NoSuchNode, e:
                    self.log.warning("Creating %s for the first time" % path)
                    writer.make_dir(path, "Generated by reporting framework")
                    repos.sync()

            repos.sync()
            rev = writer.put_content("define-reports/%s/%s" % (os.path.split(transformation)[0], 
                                                               filename),
                                     file_data, 
                                     "Generated by reporting framework transformation")
            revs.append(rev)

        shutil.rmtree(tempdir)
        return revs

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
                           'version': root.find('info/trans_version').text,
                           'full_path': ktr}
        return d

