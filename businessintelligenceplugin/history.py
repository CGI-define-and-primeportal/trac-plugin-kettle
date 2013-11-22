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
    """trac-admin command provider for business intelligence plugin."""

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
        # history table column names which are not fields from the ticket system
        history_columns = ['isclosed']
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
                    print "Already have data for %s, so can't run with until=%s" % (water_mark, until)
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
                print "Working on (after) %s to (end of) %s for ticket %d" % (water_mark,
                                                                              until,
                                                                              ticket_id)

                # set up a dictionary to hold the value of the ticket fields, which will change as we step forward in time
                ticket_values = {}
                for k in built_in_fields + custom_fields:
                    if k in [c.name for c in self.schema[0].columns]:
                        ticket_values[k] = None
                
                # populate the "initial" values
                if water_mark:
                    history_date = water_mark + datetime.timedelta(days=1)
                    c = db.cursor()
                    # we add ticket fields and history columns otherwise 
                    # we don't get previous values such as isclosed
                    columns = ticket_values.keys() + history_columns
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
                        c.execute("SELECT oldvalue FROM ticket_change WHERE ticket = %s AND field = %s ORDER BY time LIMIT 1",  
                                  (ticket_id, column))
                        result = c.fetchone()
                        if result is None:
                            if column in built_in_fields:
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

                # and then we'll update 'ticket_values' to make a representation of the ticket for the end of each day, and store that into the history database

                def _calculate_totalhours_on_date(date):
                    c.execute("SELECT SUM(seconds_worked)/3600.0 FROM ticket_time WHERE ticket = %s AND time_started < %s",
                              (ticket_values['id'],
                               to_timestamp(startofnextday(history_date))))
                    result = c.fetchone()
                    return result[0] if result else 0

                def _calculate_remaininghours_on_date(date):
                    # find the closest absolute value
                    c.execute("SELECT to_timestamp(time / 1000000), oldvalue FROM ticket_change WHERE "
                              "field = 'remaininghours' AND ticket = %s AND time >= %s ORDER BY time ASC LIMIT 1",
                              (ticket_values['id'],
                               to_utimestamp(startofnextday(date))))
                    next_known = c.fetchone()
                    c.execute("SELECT to_timestamp(time / 1000000), newvalue FROM ticket_change WHERE "
                              "field = 'remaininghours' AND ticket = %s AND time < %s ORDER BY time DESC LIMIT 1",
                              (ticket_values['id'],
                               to_utimestamp(startofnextday(date))))
                    previous_known = c.fetchone()
                    c.execute("SELECT now(), value FROM ticket_custom WHERE ticket = %s AND name = 'remaininghours'",
                              (ticket_values['id'],))
                    currently = c.fetchone()
                    #print "----", date
                    #print next_known
                    #print previous_known
                    #print currently
                    candidates = []
                    try:
                        candidates.append((currently[0] - startofnextday(date), currently[0], float(currently[1])))
                    except (TypeError, ValueError), e:
                        self.log.warning("Invalid float in %s for remaininghours on ticket %s", 
                                         currently, ticket_values['id'])
                    if next_known:
                        try:
                            candidates.append((next_known[0] - startofnextday(date), next_known[0], float(next_known[1])))
                        except (TypeError, ValueError), e:
                            self.log.warning("Invalid float for next_known in %s for remaininghours on ticket %s", 
                                             next_known, ticket_values['id'])
                    if previous_known:
                        try:
                            candidates.append((startofnextday(date) - previous_known[0], previous_known[0], float(previous_known[1])))
                        except (TypeError, ValueError), e:
                            self.log.warning("Invalid float for previous_known in %s for remaininghours on ticket %s", 
                                             previous_known, ticket_values['id'])
                    if not candidates:
                        return 0

                    best_candidate = sorted(candidates)[0]

                    #print best_candidate[0], best_candidate

                    # in these comments, "today" and "current" is
                    # 'date' variable passed in above:

                    # extra heuristic - if we know it's going to be 0,
                    # and that's the first value we know at all,
                    # probably it should be 0 right now (as the hours
                    # plugin wouldn't let it go negative
                    if best_candidate[2] == 0 and not previous_known:
                        return 0

                    if startofnextday(date) < best_candidate[1]:
                        # we've found evidence of what it was at a
                        # future date, so sum up the time spent
                        # between now and then. As that time would be
                        # subtracting from 'remaininghours', then add
                        # it back to find the current 'remaininghours'
                        
                        c.execute("SELECT SUM(seconds_worked) FROM ticket_time WHERE "
                                  "ticket = %s AND time_started >= %s AND time_started < %s",
                                  (ticket_values['id'],
                                   to_timestamp(startofnextday(date)),
                                   to_timestamp(best_candidate[1])))
                        result = c.fetchone()
                        if result and result[0]:
                            return best_candidate[2] + (result[0]/3600.0)
                        else:
                            return best_candidate[2]
                    else:
                        # we've found evidence of what it was in the
                        # past, so sum up time spent between then and
                        # now. As that time would be reducing
                        # 'remaininghours', we'll do that same
                        # reduction to find the value for today
                        c.execute("SELECT SUM(seconds_worked) FROM ticket_time WHERE "
                                  "ticket = %s AND time_started >= %s AND time_started < %s",
                                  (ticket_values['id'],
                                   to_timestamp(best_candidate[1]),
                                   to_timestamp(startofnextday(date))))
                        result = c.fetchone()
                        if result and result[0]:
                            return best_candidate[2] - (result[0]/3600.0)
                        else:
                            return best_candidate[2]

                    return 0

                execute_many_buffer = []
                while history_date <= until:
                    active_changes = {}
                    for time, field, newvalue in ticket_changes:
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
                    # these are pretty hard to calculate,
                    # remaininghours especially as we don't have all
                    # the values it could have taken recorded. We have
                    # some known data-points, and some known
                    # delta-points, but we don't know for sure (for
                    # example) the value when the ticket was new.
                    ticket_values['totalhours'] = _calculate_totalhours_on_date(history_date)
                    ticket_values['remaininghours'] = _calculate_remaininghours_on_date(history_date)

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

