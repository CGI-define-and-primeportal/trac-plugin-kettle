from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.versioncontrol.api import RepositoryManager, NoSuchNode
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler, RequestDone
from trac.web.chrome import ITemplateProvider, add_script, add_stylesheet, add_ctxtnav
from trac.util import content_disposition

from tracrpc.api import IXMLRPCHandler, Binary

from genshi.builder import tag

from trac_browser_svn_ops.svn_fs import SubversionWriter
from contextmenu.contextmenu import ISourceBrowserContextMenuProvider

import glob
import os
from lxml import etree
import tempfile
import shutil
import subprocess
import thread
import mimetypes

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties

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
        if 'action' in req.args:
            req.perm.require("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE")
            if req.args['action'] == "execute_async":
                thread.start_new_thread(self._do_execute_transformation, (req.args['transform'],))
            elif req.args['action'] == "execute_download":
                filename, stat, filestream = self._do_execute_transformation(req.args['transform'], store=False, return_bytes_handle=True)
                req.send_response(200)
                req.send_header('Content-Type', mimetypes.guess_type(filename)[0] or 'application/octet-stream')
                req.send_header('Content-Length', stat.st_size)
                req.send_header('Content-Disposition', content_disposition('attachment', filename))
                req.end_headers()
                while True:
                    bytes = filestream.read(4096)
                    if not bytes:
                        break
                    req.write(bytes)
                filestream.close()
                raise RequestDone

            elif req.args['action'] == "execute":
                self._do_execute_transformation(req.args['transform'])
            else:
                add_warning(req, "No valid action found")
                req.redirect(req.href.businessintelligence())
            if req.get_header('X-Requested-With') == 'XMLHttpRequest':
                req.send_response(200)
                req.send_header('Content-Length', 0)
                req.end_headers()
                return
            else:
                if 'returnto' in req.args:
                    req.redirect(req.args['returnto'])
                else:
                    req.redirect(req.href.businessintelligence())
        else:
            req.perm.require("BUSINESSINTELLIGENCE_TRANSFORMATION_LIST")
            data = {'transformations': self._list_transformation_files()}
            add_script(req, 'contextmenu/contextmenu.js')
            add_script(req, 'businessintelligenceplugin/js/business-intelligence.js')
            add_stylesheet(req, 'common/css/browser.css')
            add_ctxtnav(req, tag.a(tag.i(class_="icon-upload"), ' Upload Transformations', id="uploadbutton"))
            add_ctxtnav(req, tag.a(tag.i(class_="icon-calendar"), ' Schedule Transformations', id="schedulebutton"))

            return "listtransformations.html", data, None

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
        # change to a safe CWD (as subversion commit hooks will want to "chdir(.)" before they execute
        print "Generated revisions %s" % self._do_execute_transformation(transformation, changecwd=True)

    # IXMLRPCHandler methods
    def xmlrpc_namespace(self):
        return 'businessintelligence'

    def xmlrpc_methods(self):
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_LIST", ((dict,),), self.list_transformations)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((None, str),), self.execute_transformation)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((list, str),), self.execute_transformation_sync)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((Binary, str),), self.execute_transformation_download)

    def list_transformations(self, req):
        return self._list_transformation_files()

    def execute_transformation(self, req, transformation):
        """Executes transformation (generally to generate ticket report).

        Runs asynchronously as this can take a variable amount of time depending on transformation complexity.

        No useful return code provided."""
        thread.start_new_thread(self._do_execute_transformation, (transformation,))

    def execute_transformation_sync(self, req, transformation):
        """Synchronous execution of transformation."""
        return self._do_execute_transformation(transformation)

    def execute_transformation_download(self, req, transformation):
        """Synchronous execution of transformation, without storing the result and returning the content over the API"""
        filename, stat, filestream = self._do_execute_transformation(transformation, store=False, return_bytes_handle=True)
        return Binary(filestream.read())

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ["BUSINESSINTELLIGENCE_TRANSFORMATION_LIST",
                "BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE",
                "BUSINESSINTELLIGENCE_TRANSFORMATION_UPLOAD"]

    #####

    def _do_execute_transformation(self, transformation, store=True, return_bytes_handle=False, changecwd=False):
        tempdir = tempfile.mkdtemp()
        if changecwd:
            os.chdir(tempdir)
        os.mkdir(os.path.join(tempdir, "svn"))

        write_simple_jndi_properties(self.env, tempdir)

        # execute transform 

        executable = os.path.join(resource_filename(__name__, 'pentaho-data-integration'),"pan.sh")

        params = {'DefineInternal.Project.ShortName': os.path.split(self.env.path)[1]}

        args = [
            "/bin/sh",
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
                               executable="/bin/sh",
                               cwd=os.path.join(tempdir, "svn"),
                               env={'PENTAHO_DI_JAVA_OPTIONS': "-Dnet.sf.ehcache.skipUpdateCheck=true -Djava.awt.headless=true -Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                    'KETTLE_HOME': os.path.join(tempdir,"kettle")},
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                               
        while pan.poll() is None:
            # this can go to the database later (natively, by pdi)
            # keeping here, as info level for now.
            self.log.info("Pan output: %s", pan.stdout.readline())
        self.log.info("Pan returned %s" % pan.returncode)

        if pan.returncode:
            raise RuntimeError("Business Intelligence subprocess pan failed")

        if store:
            reponame, repos, path = RepositoryManager(self.env).get_repository_by_path('')
            svn_writer = SubversionWriter(self.env, repos, "reporting")
            revs = []
            for filename in os.listdir(os.path.join(tempdir, "svn")):
                self.log.info("Uploading %s" % filename)
                writer = SubversionWriter(self.env, repos, "reporting")
                file_data = open(os.path.join(os.path.join(tempdir, "svn"), filename)).read()

                for path in ["define-reports", 
                             "define-reports/%s" % transformation]:
                    try:
                        repos.sync()
                        repos.get_node(path)
                    except NoSuchNode, e:
                        self.log.warning("Creating %s for the first time" % path)
                        writer.make_dir(path, "Generated by reporting framework")

                repos.sync()
                rev = writer.put_content("define-reports/%s/%s" % (transformation, filename),
                                         file_data, 
                                         "Generated by reporting framework transformation")
                revs.append(rev)

        if return_bytes_handle:
            filename = sorted(os.listdir(os.path.join(tempdir,'svn')))[0]
            fullpath = os.path.join(tempdir,'svn',filename)
            returndata = filename, os.stat(fullpath), open(fullpath,'r')
        else:
            returndata = revs

        shutil.rmtree(tempdir)
        return returndata

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
            ktr_name = ktr.split(os.sep)[-2]
            tree = etree.parse(ktr)
            root = tree.getroot()
            d[ktr_name] = {'name': root.find('info/name').text,
                           'description': root.find('info/description').text,
                           'extended_description': root.find('info/extended_description').text,
                           'version': root.find('info/trans_version').text,
                           'full_path': ktr}
        return d


class TransformContextMenu(Component):
    implements(ISourceBrowserContextMenuProvider)
    
    # IContextMenuProvider methods
    def get_order(self, req):
        return 10

    def get_draw_separator(self, req):
        return True
    
    def get_content(self, req, entry, data):
        if 'BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE' in req.perm:
            if entry.path.startswith("define-reports/"):
                transform = entry.path.split("/")[1]
                return tag.a(tag.i(class_="icon-cog"),
                             ' Regenerate with %s' % transform, 
                             href=req.href.businessintelligence(action='execute',
                                                                transform=transform,
                                                                returnto=req.href.browser(entry.path)))
