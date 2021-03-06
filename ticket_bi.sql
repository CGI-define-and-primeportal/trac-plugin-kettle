CREATE VIEW ticket_bi_current AS 
SELECT
"ticket"."id", 
"ticket"."type", 

TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second' AS "time",
date_part('year',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_day",

TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second' AS "changetime",
date_part('year'  ,  TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_day",

TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET) /1000000 * INTERVAL '1 second' AS "resolutiontime",
date_part('year',    TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_day",

"ticket"."summary",
"ticket"."description",
"ticket"."cc",

"ticket"."component", 
"ticket"."severity", 
"ticket"."priority", 

"ticket"."owner", 
"ownername"."value" as "owner_name",

"ticket"."reporter", 
"reportername"."value" as "reporter_name",

"qualityassurancecontact"."value" AS "qualityassurancecontact", 
"qualityassurancecontactname"."value" as "qualityassurancecontact_name",

"ticket"."version", 
substring("ticket"."version" from '([\\d]+)\.[\\d]+\.[\\d]+') as "version_major",
substring("ticket"."version" from '[\\d]+\.([\\d]+)\.[\\d]+') as "version_minor",
substring("ticket"."version" from '[\\d]+\.[\\d]+\.([\\d]+)') as "version_point",
substring("ticket"."version" from '[\\d]+\.[\\d]+\.[\\d]+(.+)') as "version_patch",

"resolvedinversion"."value" AS "resolvedinversion", 
substring("resolvedinversion"."value" from '([\\d]+)\.[\\d]+\.[\\d]+') as "resolvedinversion_major",
substring("resolvedinversion"."value" from '[\\d]+\.([\\d]+)\.[\\d]+') as "resolvedinversion_minor",
substring("resolvedinversion"."value" from '[\\d]+\.[\\d]+\.([\\d]+)') as "resolvedinversion_point",
substring("resolvedinversion"."value" from '[\\d]+\.[\\d]+\.[\\d]+(.+)') as "resolvedinversion_patch",

"ticket"."milestone", 
"ticket"."status", 
"ticket"."resolution", 
"ticket"."keywords", 
CASE WHEN btrim("estimatedhours"."value")~E'^[\\d\\.]+$' THEN "estimatedhours"."value"::double precision ELSE 0.0 END AS "estimatedhours", 
CASE WHEN btrim("totalhours"."value")~E'^[\\d\\.]+$' THEN "totalhours"."value"::double precision ELSE 0.0 END AS "totalhours", 
CASE WHEN btrim("remaininghours"."value")~E'^[\\d\\.]+$' THEN "remaininghours"."value"::double precision ELSE 0.0 END AS "remaininghours"

FROM "ticket" "ticket" 
LEFT OUTER JOIN "ticket_custom" "resolvedinversion" 
  ON ("ticket"."id" = "resolvedinversion"."ticket" AND "resolvedinversion"."name" = 'resolvedinversion')
LEFT OUTER JOIN "ticket_custom" "qualityassurancecontact" 
  ON ("ticket"."id" = "qualityassurancecontact"."ticket" AND "qualityassurancecontact"."name" = 'qualityassurancecontact')
LEFT OUTER JOIN "ticket_custom" "remaininghours" 
  ON ("ticket"."id" = "remaininghours"."ticket" AND "remaininghours"."name" = 'remaininghours')
LEFT OUTER JOIN "ticket_custom" "totalhours" 
  ON ("ticket"."id" = "totalhours"."ticket" AND "totalhours"."name" = 'totalhours')
LEFT OUTER JOIN "ticket_custom" "estimatedhours" 
  ON ("ticket"."id" = "estimatedhours"."ticket" AND "estimatedhours"."name" = 'estimatedhours')
LEFT OUTER JOIN "session_attribute" "ownername"
  ON ("ticket"."owner" = "ownername"."sid" AND "ownername"."name" = 'name')
LEFT OUTER JOIN "session_attribute" "reportername"
  ON ("ticket"."reporter" = "reportername"."sid" AND "reportername"."name" = 'name')
LEFT OUTER JOIN "session_attribute" "qualityassurancecontactname"
  ON ("qualityassurancecontact"."value" = "qualityassurancecontactname"."sid" AND "qualityassurancecontactname"."name" = 'name');

CREATE TABLE ticket_bi_historical (
    snapshottime date,
    snapshottime_year double precision,
    snapshottime_quarter double precision,
    snapshottime_month double precision,
    snapshottime_week double precision,
    snapshottime_day double precision,
    id integer,
    type text,
    "time" timestamp with time zone,
    time_year double precision,
    time_quarter double precision,
    time_month double precision,
    time_week double precision,
    time_day double precision,
    changetime timestamp with time zone,
    changetime_year double precision,
    changetime_quarter double precision,
    changetime_month double precision,
    changetime_week double precision,
    changetime_day double precision,
    resolutiontime timestamp with time zone,
    resolutiontime_year double precision,
    resolutiontime_quarter double precision,
    resolutiontime_month double precision,
    resolutiontime_week double precision,
    resolutiontime_day double precision,
    component text,
    severity text,
    priority text,
    owner text,
    reporter text,
    qualityassurancecontact text,
    version text,
    version_major text,
    version_minor text,
    version_point text,
    version_patch text,
    resolvedinversion text,
    resolvedinversion_major text,
    resolvedinversion_minor text,
    resolvedinversion_point text,
    resolvedinversion_patch text,
    milestone text,
    status text,
    resolution text,
    keywords text,
    estimatedhours double precision,
    totalhours double precision,
    remaininghours double precision
);
CREATE INDEX ticket_bi_historical_idx_snapshottime ON ticket_bi_historical(snapshottime);
CREATE INDEX ticket_bi_historical_idx_snapshottime_year ON ticket_bi_historical(snapshottime_year);
CREATE INDEX ticket_bi_historical_idx_snapshottime_quarter ON ticket_bi_historical(snapshottime_quarter);
CREATE INDEX ticket_bi_historical_idx_snapshottime_month ON ticket_bi_historical(snapshottime_month);
CREATE INDEX ticket_bi_historical_idx_snapshottime_day ON ticket_bi_historical(snapshottime_day);

CREATE INDEX ticket_bi_historical_idx_milestone ON ticket_bi_historical(milestone);
CREATE INDEX ticket_bi_historical_idx_status ON ticket_bi_historical(status);
CREATE INDEX ticket_bi_historical_idx_type ON ticket_bi_historical(type);

INSERT INTO ticket_bi_historical 
SELECT 
current_date as "snapshottime",
date_part('year', current_date) AS "snapshottime_year",
date_part('quarter', current_date) AS "snapshottime_quarter",
date_part('month', current_date) AS "snapshottime_month",
date_part('week', current_date) AS "snapshottime_week",
date_part('day', current_date) AS "snapshottime_day",
id,
type,
"time",
time_year,
time_quarter,
time_month,
time_week,
time_day,
changetime,
changetime_year,
changetime_quarter,
changetime_month,
changetime_week,
changetime_day,
resolutiontime,
resolutiontime_year,
resolutiontime_quarter,
resolutiontime_month,
resolutiontime_week,
resolutiontime_day,
component,
severity,
priority,
owner,
reporter,
qualityassurancecontact,
version,
version_major,
version_minor,
version_point,
version_patch,
resolvedinversion,
resolvedinversion_major,
resolvedinversion_minor,
resolvedinversion_point,
resolvedinversion_patch,
milestone,
status,
resolution,
keywords,
estimatedhours,
totalhours,
remaininghours
FROM ticket_bi_current;


SELECT snapshottime, SUM(remaininghours) FROM ticket_bi_historical WHERE milestone like 'Crimson (v4.6)%' and resolution is null GROUP BY snapshottime ORDER BY snapshottime;

as define_master:
CREATE ROLE "define_d4_bi_readonly" PASSWORD 'xxxx' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT LOGIN;

as define_d4:
GRANT SELECT ON ticket_bi_current TO "define_d4_bi_readonly";
GRANT SELECT ON ticket_bi_historical TO "define_d4_bi_readonly";
GRANT SELECT ON ticket_links TO "define_d4_bi_readonly";


