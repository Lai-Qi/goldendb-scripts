-- Script_name: get_mysql_md5.sql
-- Author: laiqi
-- Usage: MySQL迁移至goldendb单分片（或者MySQL）时的数据校验，这里介绍了4种校验方式

-- Method1. 使用mysql提供的内置SQL命令 checksum table your_tablename 进行校验。优点：快速 , 缺点：字符集不同时无法比较 
-- Method2. 使用pt-table-checksum进行校验。优点：可以检测具体那一行不一致 可以配置pt-table-sync修复 ,缺点：需要更多权限和限制，如需要binlog_format=STATEMENT 
-- Method3. 如果你只需要校验某一张表MD5的话,直接通过下面SQL就可以完成校验， 优点：简单 ,缺点：效率不如 checksum table 命令 消耗时间约为checksum table的两倍
SET @schema = 'your_databasename';
SET @table  = 'your_tablename';
SET SESSION group_concat_max_len = 1073741824;
SELECT GROUP_CONCAT(
    CONCAT('IFNULL(CONVERT(`', COLUMN_NAME, '` USING utf8mb4), '''')')
    ORDER BY ORDINAL_POSITION
    SEPARATOR ', '
)
INTO @fields
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = @schema
  AND TABLE_NAME   = @table;
SET @sql = CONCAT(
    'SELECT MD5(GROUP_CONCAT(row_md5 ORDER BY row_md5)) AS final_md5 FROM (',
      'SELECT MD5(CONCAT_WS(\',\', ', @fields, ')) AS row_md5 ',
      'FROM `', @schema, '`.`', @table, '`',
    ') AS row_hashes'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Method4. 将Method3的操作封装存储过程，方便调用，可以方便校验整个库

DROP PROCEDURE IF EXISTS get_mysql_md5;

DELIMITER $$

CREATE PROCEDURE get_mysql_md5(
    IN db_name VARCHAR(64),
    IN tbl_list TEXT
)
BEGIN
    DECLARE done INT DEFAULT 0;
    DECLARE t_name VARCHAR(64);

    -- 声明游标
    DECLARE cur_tables CURSOR FOR
        SELECT TABLE_NAME
          FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = db_name
           AND (
                 tbl_list = ''  -- 若空表示全部表
              OR FIND_IN_SET(TABLE_NAME, tbl_list) > 0
           );

    -- 遇到游标读取完毕则设定标记
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

    -- 临时表：存储所有表的（表名, 表MD5）
    DROP TEMPORARY TABLE IF EXISTS tmp_table_md5;
    CREATE TEMPORARY TABLE tmp_table_md5 (
        table_name VARCHAR(64),
        table_md5  CHAR(32)
    );

    -- 避免被截断
    SET SESSION group_concat_max_len = 4294967295;

    -- 打开游标
    OPEN cur_tables;

    read_loop: LOOP
        FETCH cur_tables INTO t_name;
        IF done THEN
            LEAVE read_loop;
        END IF;

        -- 动态获取该表所有列，并加上 CONVERT USING utf8mb4
        SET @col_list = NULL;
        SELECT GROUP_CONCAT(
                 CONCAT('IFNULL(CONVERT(`', COLUMN_NAME, '` USING utf8mb4), '''')')
                 ORDER BY ORDINAL_POSITION SEPARATOR ', '
               )
          INTO @col_list
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = db_name
           AND TABLE_NAME   = t_name;

        -- 动态 SQL：对表每行做 MD5，再拼接所有行的 MD5 后再做一次 MD5
        SET @sql = CONCAT(
            "INSERT INTO tmp_table_md5 (table_name, table_md5) ",
            "SELECT '", t_name, "', ",
            "MD5(GROUP_CONCAT(row_md5 ORDER BY row_md5 SEPARATOR '')) AS final_md5 ",
            "FROM (",
               "SELECT MD5(CONCAT_WS(',', ", @col_list, ")) AS row_md5 ",
               "FROM `", db_name, "`.`", t_name, "`",
            ") AS t"
        );

        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END LOOP;

    CLOSE cur_tables;

    -- ================ 输出 1：每个表的 MD5 ================
    SELECT table_name, table_md5
      FROM tmp_table_md5
     ORDER BY table_name;

    -- ================ 输出 2：所有表的综合 MD5（当tbl_list为空） ================
    IF tbl_list = '' THEN
        SELECT MD5(GROUP_CONCAT(table_md5 ORDER BY table_name SEPARATOR '')) AS database_final_md5
          FROM tmp_table_md5;
    END IF;


-- ==============================
-- 使用示例：
-- 检查整个test数据库：
-- CALL get_mysql_md5('test', '');
-- 只检查test库中的 test_table：
-- CALL get_mysql_md5('test', 'test_table');
-- 只检查test库中的 table1,table2：
-- CALL get_mysql_md5('test', 'table1,table2');
-- ==============================


END$$

DELIMITER ;

