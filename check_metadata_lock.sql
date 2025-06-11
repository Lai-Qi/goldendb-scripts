/* show waiting SQL + blocking SQL + 5-statement history for the blocker */
SELECT
    w.OBJECT_SCHEMA,
    w.OBJECT_NAME,

    w.LOCK_TYPE                             AS waiting_lock_type,
    tw.PROCESSLIST_ID                       AS waiting_thread_id,
    COALESCE(esw.SQL_TEXT, 'N/A')           AS waiting_sql,

    h.LOCK_TYPE                             AS blocking_lock_type,
    th.PROCESSLIST_ID                       AS blocking_thread_id,
    COALESCE(esh.SQL_TEXT, 'N/A')           AS blocking_sql,

    /* last 5 statements executed by the blocking thread */
    COALESCE((
        SELECT GROUP_CONCAT(SQL_TEXT
                            ORDER BY EVENT_ID DESC
                            SEPARATOR '\n---\n')
        FROM (
            SELECT SQL_TEXT, EVENT_ID
            FROM   performance_schema.events_statements_history
            WHERE  THREAD_ID = th.THREAD_ID
            ORDER  BY EVENT_ID DESC
            LIMIT 5
        ) AS t
    ), 'N/A')                               AS blocking_sql_executed

FROM performance_schema.metadata_locks           AS w
JOIN performance_schema.threads                  AS tw
      ON tw.THREAD_ID = w.OWNER_THREAD_ID
LEFT JOIN performance_schema.events_statements_current AS esw
      ON esw.THREAD_ID = tw.THREAD_ID

JOIN performance_schema.metadata_locks           AS h
      ON  h.OBJECT_SCHEMA = w.OBJECT_SCHEMA
      AND h.OBJECT_NAME  = w.OBJECT_NAME
      AND h.LOCK_STATUS  = 'GRANTED'
JOIN performance_schema.threads                  AS th
      ON th.THREAD_ID = h.OWNER_THREAD_ID
LEFT JOIN performance_schema.events_statements_current AS esh
      ON esh.THREAD_ID = th.THREAD_ID

WHERE w.LOCK_STATUS = 'PENDING';
