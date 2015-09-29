from trac.core import Component, implements
from trac.db import Table, Column, Index, DatabaseManager
from trac.env import IEnvironmentSetupParticipant


class BusinessIntelligenceLogging(Component):

    implements(IEnvironmentSetupParticipant)

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
        
        db.cursor()
        db_connector, _ = DatabaseManager(self.env).get_connector()
        
        found_version = self._check_schema_version(db)
        if not found_version:
            # Create tables
            self.environment_created()
