from trac.core import Component, TracError, implements
from trac.db import Table, Column, Index, DatabaseManager, with_transaction
from trac.env import IEnvironmentSetupParticipant
from trac.util.presentation import to_json
from trac.web import IRequestHandler


class BusinessIntelligenceLogging(Component):

    implements(IEnvironmentSetupParticipant, IRequestHandler)

    # IEnvironmentSetupParticipant
    _schema_version = 1
    schema = [
        Table('running_transformations')[
            Column('transformation_id'),
            Column('status',), # running, finished, aborted
            Column('started', type='int64'),
            Column('ended', type='int64'),
            Index(['transformation_id']),
            ]
        ]
    
    def environment_created(self):
        db_connector, _ = DatabaseManager(self.env).get_connector()
        @self.env.with_transaction()
        def do_create(db):
            cursor = db.cursor()
            for table in self.schema:
                for statement in db_connector.to_sql(table):
                    cursor.execute(statement)

            # system values are strings
            cursor.execute("INSERT INTO system (name, value) "
                           "VALUES ('running_transformations', %s)", 
                           (str(self._schema_version),))

    def _check_schema_version(self, db):
        cursor = db.cursor()
        cursor.execute("select value from system where name = 'running_transformations'")
        row = cursor.fetchone()
        if row:
            return int(row[0])
        else:
            return None

    def environment_needs_upgrade(self, db):
        found_version = self._check_schema_version(db)
        if not found_version:
            self.log.debug("Initial schema needed for businessintelligence plugin for logging table")
            return True
        else:
            if found_version < self._schema_version:
                self.log.debug("Upgrade schema from %d to %d needed for businessintelligence plugin for logging table",
                               found_version,
                               self._schema_version)
                return True
        return False

    def upgrade_environment(self, db):
        self.log.debug("Upgrading schema for business intelligence logging table")
        
        cursor = db.cursor()
        db_connector, _ = DatabaseManager(self.env).get_connector()
        
        found_version = self._check_schema_version(db)
        if not found_version:
            # Create tables
            self.environment_created()

    # IRequestHandler methods

    def match_request(self, req):
        # maybe use a different URL here
        return req.path_info.startswith("/ajax/businessintelligence")

    def process_request(self, req):

        if not req.get_header('X-Requested-With') == 'XMLHttpRequest':
            raise TracError("We only accept XMLHttpRequests to his URL.")

        transformation_id = req.args.get('uuid')
        if transformation_id:
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute("""SELECT status
                              FROM running_transformations
                              WHERE transformation_id=%s""",
                              (transformation_id,))

            row = cursor.fetchone()
            if row:
                data = {
                    'status': row[0],
                }
            else:
                data = {
                    'status': None,
                }
            req.send(to_json(data), 'text/json')
