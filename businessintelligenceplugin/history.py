from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.db import Table, Column, Index, DatabaseManager, with_transaction
from trac.env import IEnvironmentSetupParticipant
from trac.ticket.api import TicketSystem
import psycopg2
import datetime
import types
from trac.util.datefmt import from_utimestamp, to_utimestamp, to_timestamp, utc, utcmax
from logicaordertracker.controller import LogicaOrderController

class HistoryStorageSystem(Component):
    """trac-admin command provider for ticketchangesets plugin."""

    implements(IEnvironmentSetupParticipant,
               IAdminCommandProvider)

    # IEnvironmentSetupParticipant
    _schema_version = 3
    schema = [
        # Ticket changesets
        Table('ticket_bi_historical')[
            Column('_snapshottime', type='date'), # UTC, END of the day
            Column('_resolutiontime', type='timestamp with time zone'),
            Column('isclosed', type='int'),
            Column('id', type='int64'),
            Column('type'),
            Column('time', type='timestamp with time zone'),
            Column('changetime', type='timestamp with time zone'),
            Column('component'),
            Column('severity'),
            Column('priority'),
            Column('owner'),
            Column('reporter'),
            Column('version'),
            Column('milestone'),
            Column('status'),
            Column('resolution'),
            Column('keywords'),
            Column('effort', type='double precision'),
            Column('estimatedhours', type='double precision'),
            Column('totalhours', type='double precision'),
            Column('remaininghours', type='double precision'),
            Index(['_snapshottime']),
            Index(['_snapshottime','milestone','isclosed']),
            ]
        ]
    
    def environment_created(self):
        self.upgrade_environment(self.env.get_db_cnx())

    def _check_schema_version(self, db):
        cursor = db.cursor()
        cursor.execute("select value from system where name = 'bi_history_schema'")
        row = cursor.fetchone()
        if row:
            return int(row[0])
        else:
            return None

    def environment_needs_upgrade(self, db):
        found_version = self._check_schema_version(db)
        if not found_version:
            self.log.debug("Initial schema needed for businessintelligence plugin for history table")
            return True
        else:
            if found_version < self._schema_version:
                self.log.debug("Upgrade schema from %d to %d needed for businessintelligence plugin for history table",
                               found_version,
                               self._schema_version)
                return True
        return False

    def upgrade_environment(self, db):
        self.log.debug("Upgrading schema for bi history plugin")
        
        cursor = db.cursor()
        db_connector, _ = DatabaseManager(self.env).get_connector()
        
        found_version = self._check_schema_version(db)
        if not found_version:
            # Create tables
            for table in self.schema:
                for statement in db_connector.to_sql(table):
                    cursor.execute(statement)

            # system values are strings
            cursor.execute("INSERT INTO system (name, value) VALUES ('bi_history_schema',%s)", 
                           (str(self._schema_version),))

        elif found_version == 2:
            # We've not released anywhere yet, so this seems more practical 
            # than writing a database-agnostic way to convert the isclosed column
            cursor.execute("DROP table ticket_bi_historical")
            for table in self.schema:
                for statement in db_connector.to_sql(table):
                    cursor.execute(statement)
            cursor.execute("UPDATE system SET value = %s WHERE name = 'bi_history_schema'", 
                           (str(self._schema_version),))
        


    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('businessintelligence history capture', '[YYYY-MM-DD] [ticket number]',
               """Catch up history capture tables. 
Run data capture up to end of yesterday, UTC.
Optional argument to collect date until end of YYYY-MM-DD.
Can then also be limited to just one ticket for debugging purposes, but will not function properly if used again with a different ticket number.""",
               None, self.capture)
        yield ('businessintelligence history clear', '[force]',
               """Clear up history capture tables - deletes data""",
               None, self.clear)
               
               
    # Internal methods
    
    def capture(self, until_str=None, only_ticket=None):

        yesterday = datetime.date.today() - datetime.timedelta(days = 1)
        if not until_str:
            until = yesterday
        else:
            until = datetime.datetime.strptime(until_str, "%Y-%m-%d").date()
            if until > yesterday:
                raise ValueError("Can't process any newer than %s" % yesterday)

        def startofday(date):
            return datetime.datetime.combine(date, datetime.time(tzinfo=utc)) if date else None

        def startofnextday(date):
            return datetime.datetime.combine(date + datetime.timedelta(days = 1),
                                             datetime.time(tzinfo=utc)) if date else None

        ts = TicketSystem(self.env)
        custom_fields = []
        empty_means_zero = []
        built_in_fields = []
        for field in ts.fields:
            if 'custom' in field:
                custom_fields.append(field['name'])
            elif 'link' in field:
                pass
            else:
                built_in_fields.append(field['name'])

            if field.get('datatype','float') in ('float', 'integer'):
                empty_means_zero.append(field['name'])

        @with_transaction(self.env)
        def _capture(db):
            water_mark_cursor = db.cursor()
            water_mark_cursor.execute("SELECT _snapshottime FROM ticket_bi_historical ORDER BY _snapshottime DESC LIMIT 1")
            water_mark_result = water_mark_cursor.fetchone()
            del water_mark_cursor
            if water_mark_result:
                water_mark = water_mark_result[0]
                print "Last successful run was at %s" % water_mark

                if until <= water_mark:
                    print "Already have data up to %s, so can't run with until=%s" % (water_mark, until)
                    return False
            else:
                water_mark = None
                print "No previous runs"

            # Get statuses we consider to be closed for each ticket type
            controller = LogicaOrderController(self.env)
            closed_statuses = controller.type_and_statuses_for_closed_statusgroups()

            if only_ticket:
                ticket_ids = [(int(only_ticket),)]
            else:
                ticket_ids = db.cursor()
                ticket_ids.execute("SELECT id FROM ticket GROUP BY id ORDER BY id")
            for ticket_id, in ticket_ids:
                print "Working on %s to %s (stopping before %s) for ticket %d" % (water_mark,
                                                                                  until,
                                                                                  startofnextday(until),
                                                                                  ticket_id)

                # set up a dictionary to hold the value of the ticket fields, which will change as we step forward in time
                ticket_values = {}
                for k in built_in_fields + custom_fields:
                    if k in [c.name for c in self.schema[0].columns]:
                        ticket_values[k] = None
                
                # populate the "initial" values
                if water_mark:
                    history_date = water_mark
                    c = db.cursor()
                    columns = ticket_values.keys()
                    c.execute("SELECT %s FROM ticket_bi_historical WHERE id = %%s AND _snapshottime = %%s" %  ",".join(columns), 
                              (ticket_id, water_mark))

                    values = c.fetchone()
                    if not values:
                        print "No historical data for ticket %s on %s?" % (ticket_id, water_mark)
                        continue

                    ticket_values.update(dict(zip(columns, values)))

                    # original storage for custom_fields can only store strings, so pretend we had a string
                    for k, v in ticket_values.items():
                        if k in custom_fields:
                            if v:
                                ticket_values[k] = str(v)
                            else:
                                ticket_values[k] = ''

                    ticket_values['id'] = ticket_id

                else:
                    # first seen changes will be from the very first information we have about this ticket
                    c = db.cursor()
                    c.execute("SELECT time FROM ticket WHERE id = %s", (ticket_id,))
                    ticket_created = from_utimestamp(c.fetchone()[0])
                    history_date = ticket_created.date()

                    # find original values for the ticket
                    for column in ticket_values.keys():
                        if column in ("totalhours", ):
                            # these are never in the ticket_change table, they are in ticket_time table but we can anyway assume they started without a value
                            ticket_values[column] = ''
                            continue
                        c.execute("SELECT oldvalue FROM ticket_change WHERE ticket = %s AND field = %s ORDER BY time LIMIT 1",  
                                  (ticket_id, column))
                        result = c.fetchone()
                        if result is None:
                            # column has never changed
                            if column in ("remaininghours",):
                                # could have changed via ticket_time table, so current value isn't necessarily the first value
                                # so we'll count back to guess what it was
                                c.execute("SELECT value FROM ticket_custom WHERE ticket = %s AND name = 'remaininghours'", 
                                          (ticket_id,))
                                current_remaininghours = c.fetchone()
                                c.execute("SELECT SUM(seconds_worked) FROM ticket_time WHERE ticket = %s", (ticket_id,))
                                total_tickethours = c.fetchone()
                                if current_remaininghours and total_tickethours:
                                    if total_tickethours[0] == None:
                                        total_tickethours = (0,)
                                    result = [str(float(current_remaininghours[0]) + total_tickethours[0]/3600.0)]
                                else:
                                    # ok, maybe guess that estimatedhours has never changed so was the first remaininghours
                                    # although I expect this won't be run - 
                                    c.execute("SELECT value FROM ticket_custom WHERE ticket = %s AND name = 'estimatedhours'", 
                                          (ticket_id,))
                                    result = c.fetchone()
                            elif column in built_in_fields:
                                c.execute("SELECT %s FROM ticket WHERE id = %%s" % column, (ticket_id,))
                                result = c.fetchone()
                            else:
                                c.execute("SELECT value FROM ticket_custom WHERE ticket = %s AND name = %s", (ticket_id, column))
                                result = c.fetchone()
                            if result:
                                ticket_values[column] = result[0]
                            else:
                                ticket_values[column] = None
                        else:
                            ticket_values[column] = result[0]

                    ticket_values['id'] = ticket_id
                    ticket_values['time'] = ticket_created
                    ticket_values['changetime'] = ticket_created
                    ticket_values['_resolutiontime'] = None
                    # assumption that you cannot create a ticket in status closed
                    # so we give isclosed a false value from the off
                    ticket_values['isclosed'] = 0

                    # PROBLEM: How can we detect when a milestone was renamed (and
                    # tickets updated) - this isn't mentioned in the ticket_change
                    # table.
                    # Maybe we have to search the log file for strings?!  
                    # source:trunk/trac/trac/ticket/model.py@8937#L1192

                # now we're going to get a list of all the changes that this ticket goes through

                ticket_changes = []
                # Unsure about this - got to be a safer way to generate the IN expression? Concerned about SQL injection if users create new customfield names?
                c.execute("SELECT time, field, newvalue FROM ticket_change WHERE ticket = %%s AND field in (%s) AND time >= %%s AND time < %%s ORDER BY time" % (
                        ",".join(["'%s'" % k for k in ticket_values.keys()]),),
                          (ticket_id,
                           to_utimestamp(startofday(history_date)),
                           to_utimestamp(startofnextday(until))))
                for result in c:
                    ticket_changes.append((from_utimestamp(result[0]), result[1], result[2]))

                # now we'll also get the changes from the ticket_time table
                # we could use http://www.postgresql.org/docs/current/static/tutorial-window.html
                # but I'll calculate the running totals in Python for now so it's DB agnostic
                totalhours = float(ticket_values['totalhours']) if ticket_values['totalhours'].strip() else 0
                remaininghours = float(ticket_values['remaininghours']) if ticket_values['remaininghours'].strip() else 0
                c.execute("SELECT time_started, seconds_worked FROM ticket_time WHERE ticket = %s AND time_started >= %s AND time_started < %s ORDER BY time_started", 
                          (ticket_id,
                           to_timestamp(startofday(history_date)),
                           to_timestamp(startofnextday(until))))
                for result in c:
                    totalhours = totalhours + result[1]/3600.0
                    remaininghours = max(0,remaininghours - result[1]/3600.0)
                    ticket_changes.append((datetime.datetime.fromtimestamp(result[0], tz=utc), "totalhours", totalhours))
                    ticket_changes.append((datetime.datetime.fromtimestamp(result[0], tz=utc), "remaininghours", remaininghours))
                
                # and then we'll update 'ticket_values' to make a representation of the ticket for the end of each day, and store that into the history database

                execute_many_buffer = []

                while history_date <= until:
                    active_changes = {}
                    for time, field, newvalue in sorted(ticket_changes):
                        if time < startofnextday(history_date):
                            # finding the newest change for each field, which is older than or equal to history_date
                            #print "Setting %s to %s" % (field, newvalue)
                            active_changes[field] = newvalue
                            active_changes['changetime'] = time
                            if field == "resolution":
                                active_changes['_resolutiontime'] = time
                            # work out if the new status is in a statusgroup with the attr closed='True'
                            if field == 'status':
                                if newvalue in closed_statuses[ticket_values['type']]:
                                    active_changes['isclosed'] = 1
                                else:
                                    active_changes['isclosed'] = 0

                    ticket_values.update(active_changes)

                    for k in ticket_values:
                        if k in empty_means_zero and not ticket_values[k]:
                            ticket_values[k] = "0"

                    insert_buffer = []
                    ticket_values["_snapshottime"] = history_date
                    for column in self.schema[0].columns:
                        if column.name in ticket_values:
                            insert_buffer.append(ticket_values[column.name])
                        else:
                            insert_buffer.append(None)

                    execute_many_buffer.append(insert_buffer)

                    history_date = history_date + datetime.timedelta(days=1)

                #print "Inserting..."
                # we do as much as possible of the transformations in SQL, so that it matches the ticket_bi_current view
                # and avoids any small differences in Python vs. SQL functions

                c.executemany("INSERT INTO ticket_bi_historical (%s) VALUES (%s)" % (
                        ",".join(db.quote(c.name) for c in self.schema[0].columns),
                        ",".join(["%s"] * len(self.schema[0].columns))),
                              execute_many_buffer)

    def clear(self, force=False):
        if force != "force":
            print "Will only actually clear if 'force' is passed as additional argument"
            return 

        @with_transaction(self.env)
        def _clear(db):
            cursor = db.cursor()
            cursor.execute("DELETE from ticket_bi_historical")

