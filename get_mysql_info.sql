-- 执行的时候替换('db1','db2')为实际的库名
-- 查看版本
select version();

-- 查看字符集
-- show create database your_database_name;
-- show create table your_table_name;
select table_schema,table_collation from information_schema.tables where table_type='BASE TABLE' and table_schema in ('db1','db2') group by table_schema,table_collation;

-- 查看一些重要参数 
-- some variables relates to COMPATIBILITY
show variables like 'character_set%';
show variables like '%collation%';
show variables like 'sql_mode'; 
show variables like 'binlog_format';
show variables like 'gtid_mode';
show variables like 'innodb_page_size';
show variables like 'max_allowed_packet';
show variables like 'innodb_lock_wait_timeout';
show variables like 'lock_wait_timeout';
show variables like 'max_connections';

show variables like 'log_bin_trust_function_creators';
show variables like 'local_infile';
show variables like 'default_storage_engine';

-- some variables relates to PERFORMANCE 
show variables like 'innodb_buffer_pool_size'; 
show variables like 'innodb_buffer_pool_instances';
show variables like 'innodb_log_buffer_size';

show variables like 'sort_buffer_size';
show variables like 'read_buffer_size';
show variables like 'read_rnd_buffer_size';
show variables like 'join_buffer_size';
show variables like 'thread_stack';
show variables like 'binlog_cache_size';
show variables like 'tmp_table_size';


--有主键表信息

select t1.table_schema,t1.table_name,t1.table_rows,t1.table_collation,t1.data_length/1024/1024 as data_mb, index_length/1024/1024 AS index_mb from information_schema.tables t1
left outer join information_schema.table_constraints t2
on t1.table_schema = t2.table_schema and t1.table_name=t2.table_name  and t2.constraint_type = 'PRIMARY KEY'
where t2.table_name is not null
AND t1.table_type='BASE TABLE'
AND t1.table_schema in ('db1','db2')
order by t1.table_rows;


--无主键表信息
select t1.table_schema,t1.table_name,t1.table_rows,t1.table_collation,t1.data_length/1024/1024 as data_mb, index_length/1024/1024 AS index_mb from information_schema.tables t1
left outer join information_schema.table_constraints t2
on t1.table_schema = t2.table_schema and t1.table_name=t2.table_name  and t2.constraint_type = 'PRIMARY KEY'
where t2.table_name is null
and t1.table_type='BASE TABLE'
AND t1.TABLE_SCHEMA in ('db1','db2')
order by t1.table_rows;


--查看外键信息
SELECT CONSTRAINT_SCHEMA,TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA in ('db1','db2');

-- 查看存储过程函数触发器信息
select routine_schema,routine_name,routine_type from information_schema.routines where routine_schema  in ('db1','db2');
select table_schema,TABLE_NAME from information_schema.views where table_schema  in ('db1','db2');
select trigger_schema,trigger_name from information_schema.triggers where trigger_schema in ('db1','db2');
select event_schema,event_name from information_schema.events where event_schema in ('db1','db2');


-- 还有一些查看MySQL运行状态的内容，这里先写个提纲之后再补充^_^

1. 在 MySQL 中查看业务高峰期
1.1 慢查询日志分析
1.2 使用 information_schema 查询表的访问量
1.3 查询status变量


2. 备份任务运行情况，备份时间，备份恢复耗时等

