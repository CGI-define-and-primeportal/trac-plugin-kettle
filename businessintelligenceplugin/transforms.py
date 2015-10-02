from trac.admin import IAdminCommandProvider
from trac.core import Component, implements, TracError
from trac.versioncontrol.api import RepositoryManager, NoSuchNode
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler, RequestDone, HTTPNotFound 
from trac.web.chrome import ITemplateProvider, add_script, add_stylesheet, add_ctxtnav
from trac.util import content_disposition
from trac.util.datefmt import to_utimestamp, utc
from trac.util.presentation import to_json
from trac.env import IEnvironmentSetupParticipant

from tracrpc.api import IXMLRPCHandler, Binary

from genshi.builder import tag

from trac_browser_svn_ops.svn_fs import SubversionWriter
from contextmenu.contextmenu import ISourceBrowserContextMenuProvider

from datetime import datetime
import json
import uuid
import types
import glob
import os
import errno
from lxml import etree
import tempfile
import shutil
import subprocess
import thread
import mimetypes

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties
from zipfile import ZipFile

class TransformExecutor(Component):
    implements(IAdminCommandProvider,
               IXMLRPCHandler,
               IPermissionRequestor,
               IRequestHandler,
               ITemplateProvider,
               IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipant
    def _create_folders(self):
        for d in ("job-templates", "transformation-templates"):
            try:
                os.mkdir(os.path.join(self.env.path, d))
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise
    
    def environment_created(self):
        self._create_folders()

    def environment_needs_upgrade(self, db):
        for d in ("job-templates", "transformation-templates"):
            if not os.path.exists(os.path.join(self.env.path, d)):
                return True
        return False

    def upgrade_environment(self, db):
        self._create_folders()


    # IRequestHandler methods

    def match_request(self, req):
        if req.path_info == "/businessintelligence":
            return True

    def process_request(self, req):
        if 'action' in req.args:
            transform_id = self._generate_running_transformation_id()
            parameters = {}
            for k in req.args:
                if k.startswith("parameter:"):
                    parameter_name = k.split(":",2)[1]
                    parameter_value = req.args[k]
                    parameters[parameter_name] = parameter_value
            req.perm.require("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE")
            if req.args['action'] == "execute_async":
                # execute the transformation 
                thread.start_new_thread(self._do_execute_transformation, 
                                        (req.args['transform'],), 
                                        {'transformation_id': transform_id, 'parameters': parameters})
                # send transform_id generated via uuid back to JS via JSON
                # we have to do this after we invoke a new thread as req.send()
                # returns from this function and stops further flow control
                req.send(to_json({'transform_id': transform_id}), 'text/json')
            elif req.args['action'] == "execute_download":
                filename, stat, filestream = self._do_execute_transformation(req.args['transform'], transformation_id=transform_id, store=False, return_bytes_handle=True, parameters=parameters)
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
                self._do_execute_transformation(req.args['transform'], transformation_id=transform_id, parameters=parameters)
            elif req.args['action'] == 'check_status':
                if 'uuid' not in req.args:
                    raise KeyError
                running_transformations = json.loads(req.args['uuid'])
                req.send(to_json(self._generate_status_response(running_transformations)), 'text/json')
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
            data = {'transformations': self._list_transformation_files(listall=False)}
            add_script(req, 'contextmenu/contextmenu.js')
            add_script(req, 'businessintelligenceplugin/js/business-intelligence.js')
            add_stylesheet(req, 'common/css/browser.css')
            add_ctxtnav(req, tag.a(tag.i(class_="fa fa-upload"), ' Upload Transformations', id="uploadbutton"))
            add_ctxtnav(req, tag.a(tag.i(class_="fa fa-calendar"), ' Schedule Transformations', id="schedulebutton"))
            add_ctxtnav(req, tag.a(tag.i(class_="fa fa-cog"), ' Running Transformations', id="runningbutton"))

            return "listtransformations.html", data, None

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('businessintelligenceplugin', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence transformation list', 'all',
               """List available transformations
               """,
               self._complete_transformation_list, self._do_list)
        yield ('businessintelligence transformation execute', '<transformation> [ <param1 name> <param1 value> ] [ <param2 name> <param2 value> ]',
               """Execute a particular transformation
               """,
               self._complete_transformation_execute, self._do_execute)

    def _complete_transformation_list(self, args):
        pass

    def _complete_transformation_execute(self, args):
        return self._list_transformation_files().keys()
    
    def _do_list(self, all=False):
        listall = all and all == "all"
        for ktr, details in self._list_transformation_files(listall=listall).items():
            print ktr
            for k, v in details.items():
                if isinstance(v, types.DictType):
                    print " ", k
                    for k, v in v.items():
                        if "default_value" in v and "description" in v:
                            print "  - %s; default: %s description: %s" % (k, repr(v['default_value']), v['description'])
                        else:
                            print "  - ", k, v

                else:
                    print " ", k, v

    def _do_execute(self, transformation, *args):
        # change to a safe CWD (as subversion commit hooks will want to "chdir(.)" before they execute
        parameters = dict(zip(args[::2], args[1::2]))
        transformation_id = self._generate_running_transformation_id()
        print "Generated revisions %s" % self._do_execute_transformation(transformation, transformation_id=transformation_id,
                                                                         listall=True, changecwd=True, parameters=parameters)

    # IXMLRPCHandler methods
    def xmlrpc_namespace(self):
        return 'businessintelligence'

    def xmlrpc_methods(self):
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_LIST", ((dict,),), self.list_transformations)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((None, str),), self.execute_transformation)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((list, str),), self.execute_transformation_sync)
        yield ("BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE", ((Binary, str),), self.execute_transformation_download)

    def list_transformations(self, req):
        return self._list_transformation_files(listall=False)

    def execute_transformation(self, req, transformation):
        """Executes transformation (generally to generate ticket report).

        Runs asynchronously as this can take a variable amount of time depending on transformation complexity.

        No useful return code provided."""
        transformation_id = self._generate_running_transformation_id()
        thread.start_new_thread(self._do_execute_transformation, (transformation,), {'transformation_id': transformation_id})

    def execute_transformation_sync(self, req, transformation):
        """Synchronous execution of transformation."""
        transformation_id = self._generate_running_transformation_id()
        return self._do_execute_transformation(transformation, transformation_id=transformation_id)

    def execute_transformation_download(self, req, transformation):
        """Synchronous execution of transformation, without storing the result and returning the content over the API"""
        transformation_id = self._generate_running_transformation_id()
        filename, stat, filestream = self._do_execute_transformation(transformation, store=False, 
                                    return_bytes_handle=True, transformation_id=transformation_id)
        return Binary(filestream.read())

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ["BUSINESSINTELLIGENCE_TRANSFORMATION_LIST",
                "BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE",
                "BUSINESSINTELLIGENCE_TRANSFORMATION_UPLOAD"]

    #####

    def _do_execute_transformation(self, transformation, transformation_id=None, 
                                   store=True, return_bytes_handle=False, 
                                   changecwd=False, listall=False, parameters=None):
        tempdir = tempfile.mkdtemp()
        if changecwd:
            os.chdir(tempdir)
        os.mkdir(os.path.join(tempdir, "svn"))

        write_simple_jndi_properties(self.env, tempdir)

        # execute transform 


        transform = self._list_transformation_files(listall)[transformation]

        if parameters:
            for parameter in parameters:
                if parameter not in transform['parameters']:
                    raise KeyError("%s is not valid parameter" % parameter)
        else:
            parameters = {}
        parameters['DefineInternal.Project.ShortName'] = os.path.split(self.env.path)[1]

        scriptfilename = {'transformation': 'pan.sh',
                          'job': 'kitchen.sh'}[transform['type']]

        executable = os.path.join(resource_filename(__name__, 'pentaho-data-integration'), scriptfilename)

        args = [
            "/bin/sh",
            executable,
            "-file", transform['full_path'],
            "-level", "Detailed",
            ]
        for k, v in parameters.items():
            if "=" in k:
                raise ValueError("Unable to support = symbol in parameter key named %s" % k)
            args.append("-param:%s=%s" % (k.encode('utf-8'), v.encode('utf-8')))

        self.log.debug("Running %s with %s", executable, args)

        if transformation_id:
            # See https://d4.define.logica.com/ticket/4375#comment:7
            db = self.env.get_read_db()
            @self.env.with_transaction()
            def do_insert(db):
                cursor = db.cursor()
                self.env.log.debug("Updating running_transformations - inserting new row for %s",
                                    transformation_id)
                cursor.execute("""INSERT INTO running_transformations (transformation_id, status, started)
                                  VALUES (%s, %s, %s)""", (transformation_id, "running", to_utimestamp(datetime.now(utc))))

        # this bit of Python isn't so good :-( I'll just merge the stdout and stderr streams...

        # http://stackoverflow.com/questions/6809590/merging-a-python-scripts-subprocess-stdout-and-stderr-while-keeping-them-disti
        # http://codereview.stackexchange.com/questions/6567/how-to-redirect-a-subprocesses-output-stdout-and-stderr-to-logging-module
        script = subprocess.Popen(args, 
                               executable="/bin/sh",
                               cwd=os.path.join(tempdir, "svn"),
                               env={'PENTAHO_DI_JAVA_OPTIONS': "-Dfile.encoding=utf8 -Dnet.sf.ehcache.skipUpdateCheck=true -Djava.awt.headless=true -Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                    'LANG': "en_US.UTF-8",
                                    'KETTLE_HOME': os.path.join(tempdir,"kettle")},
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                               
        while script.poll() is None:
            # this can go to the database later (natively, by pdi)
            # keeping here, as info level for now.
            self.log.info("Script output: %s", script.stdout.readline())
        self.log.info("Script returned %s", script.returncode)

        if script.returncode:

            # transform has failed to complete - update running_transformations table
            if transformation_id:
                @self.env.with_transaction()
                def do_insert(db):
                    cursor = db.cursor()
                    self.env.log.debug("Updating running_transformations - %s failed to complete",
                                        transformation_id)
                    cursor.execute("""UPDATE running_transformations
                                      SET transformation_id=%s, status=%s, ended=%s
                                      WHERE transformation_id=%s""", (transformation_id, "error", to_utimestamp(datetime.now(utc)), transformation_id))

            raise RuntimeError("Business Intelligence subprocess script failed")

        # We know assume that the transform has finished successfully
        # so we update the running_transformations table to represent this
        if transformation_id:
            @self.env.with_transaction()
            def do_insert(db):
                cursor = db.cursor()
                self.env.log.debug("Updating running_transformations - %s completed",
                                    transformation_id)
                cursor.execute("""UPDATE running_transformations
                                  SET transformation_id=%s, status=%s, ended=%s
                                  WHERE transformation_id=%s""", (transformation_id, "success", to_utimestamp(datetime.now(utc)), transformation_id))

        if store:
            reponame, repos, path = RepositoryManager(self.env).get_repository_by_path('')
            svn_writer = SubversionWriter(self.env, repos, "reporting")
            revs = []
            for filename_encoded in os.listdir(os.path.join(tempdir, "svn")):
                filename = filename_encoded.decode('utf-8') # we wrote the filename out ourselves
                self.log.info("Uploading %s", filename)
                writer = SubversionWriter(self.env, repos, "reporting")
                file_data = open(os.path.join(os.path.join(tempdir, "svn"), filename)).read()

                for path in ["define-reports", 
                             "define-reports/%s" % transformation]:
                    try:
                        repos.sync()
                        repos.get_node(path)
                    except NoSuchNode, e:
                        self.log.warning("Creating %s for the first time",
                                         path)
                        writer.make_dir(path, "Generated by reporting framework")

                repos.sync()
                properties = {'define:generated-by-transformation': transformation}
                for k, v in parameters.items():
                    if not k.startswith("DefineInternal"):
                        properties[u"define:parameter:%s" % k] = v
                
                rev = writer.put_content([("define-reports/%s/%s" % (transformation, filename), file_data)],
                                         "Generated by reporting framework transformation",
                                         properties=properties,
                                         clearproperties=True)
                revs.append(rev)

        if return_bytes_handle:

            src = os.path.abspath(os.path.join(tempdir,'svn'))
            files = sorted(os.listdir(src))

            if len(files) == 0:
                raise HTTPNotFound("Operation did not create any output")                    

            elif len(files) == 1:
                filename = files[0]
                fullpath = os.path.join(src,filename)
                returndata = filename, os.stat(fullpath), open(fullpath,'r')

            elif len(files) > 1:
                output_filename = transform['name'].replace(" ", "-") + '-archive.zip'
                output_path = os.path.abspath(os.path.join(src,output_filename))
                z = ZipFile(output_path, 'w')
                for dirname, dirs, files in os.walk(src):
                    for f in files:
                        if not output_filename in f:
                            absname = os.path.abspath(os.path.join(dirname, f.decode('utf-8')))
                            arcname = absname[len(src) + 1:]
                            z.write(absname,arcname)
                z.close()
                returndata = output_filename, os.stat(output_path), open(output_path,'r')


        else:
            returndata = revs

        shutil.rmtree(tempdir)
        return returndata

    ### 
    def _list_transformation_files(self, listall=False):
        statusstr = {0: "",
                     1: "draft",
                     2: "production"}
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
            try:
                status = int(root.find('info/trans_status').text)
            except Exception:
                status = 0
            if listall or status > 0:
                d[ktr_name] = {'name': root.find('info/name').text,
                               'description': root.find('info/description').text,
                               'extended_description': root.find('info/extended_description').text,
                               'version': root.find('info/trans_version').text,
                               'full_path': ktr,
                               'type': 'transformation',
                               'status': statusstr[status]}
                for i in root.findall('info/parameters/parameter'):
                    if not i.find('name').text.startswith("DefineInternal"):
                        d[ktr_name].setdefault("parameters",{})[i.find('name').text] = {'default_value': i.find('default_value').text,
                                                                                        'description': i.find('description').text}

        for kjb in glob.glob(os.path.join(
            os.path.join(self.env.path, 'job-templates'),
            "*/*.kjb")) + \
            glob.glob(os.path.join(
                    resource_filename(__name__, 
                                      'default-job-templates'),
                    "*/*.kjb")):
            # refer to the kjb by the final folder and job filename
            kjb_name = kjb.split(os.sep)[-2]
            tree = etree.parse(kjb)
            root = tree.getroot()
            try:
                status = int(root.find('job_status').text)
            except Exception:
                status = 0
            if listall or status > 0:
                d[kjb_name] = {'name': root.find('name').text,
                               'description': root.find('description').text,
                               'extended_description': root.find('extended_description').text,
                               'version': root.find('job_version').text,
                               'full_path': kjb,
                               'status': statusstr[status],
                               'type': 'job'}
                for i in root.findall('parameters/parameter'):
                    if not i.find('name').text.startswith("DefineInternal"):
                        d[kjb_name].setdefault("parameters",{})[i.find('name').text] = {'default_value': i.find('default_value').text,
                                                                                        'description': i.find('description').text}
        return d

    def _generate_running_transformation_id(self):
        """
        Generate an id for each running transformation using a the uuid module.
        Note this does not uniqely identify each transformation, it is used 
        to identify each running transformation in the running_transformation 
        table.
        """

        return str(uuid.uuid4())

    def _generate_status_response(self, transformation_ids):
        """
        Queries the running_transformation table to return the status of 
        transformation currently being executed.

        Note that we expect transformation_ids to be a iterable (even if it 
        only contains one UUID). If this iterable contains 'all', we return 
        every row which has a status 'running'.

        Returns a list of dictionaries which we send back as to client as JSON.
        """

        db = self.env.get_read_db()
        cursor = db.cursor()

        if 'all' in transformation_ids:
            cursor.execute("""SELECT transformation_id, status, started 
                              FROM running_transformations
                              WHERE status='running'
                           """)
        else:
            cursor.execute("""SELECT transformation_id, status, started 
                              FROM running_transformations 
                              WHERE transformation_id IN ({0})
                           """.format(db.parammarks(len(transformation_ids))),
                              transformation_ids)

        return [{
                 'id': row[0],
                 'status': row[1],
                 'started': row[2]
                } for row in cursor]


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
                return tag.a(tag.i(class_="fa fa-cog"),
                             ' Regenerate with %s (default parameters)' % transform, 
                             href=req.href.businessintelligence(action='execute',
                                                                transform=transform,
                                                                returnto=req.href.browser(entry.path)))

class TransformWithParametersContextMenu(Component):
    implements(ISourceBrowserContextMenuProvider)
    
    # IContextMenuProvider methods
    def get_order(self, req):
        return 11

    def get_draw_separator(self, req):
        return True
    
    def get_content(self, req, entry, data):
        if 'BUSINESSINTELLIGENCE_TRANSFORMATION_EXECUTE' in req.perm:
            if entry.path.startswith("define-reports/"):
                transform = entry.path.split("/")[1]
                return tag.a(tag.i(class_="fa fa-cog"),
                             ' Regenerate with %s (provide parameters)' % transform, 
                             href=req.href.businessintelligence() + "#" + transform)
            
