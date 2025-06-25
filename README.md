这里收集的是我在日常维护GoldenDB时编写的脚本、SQL 以及使用文档，欢迎大家使用和提建议。
---
# check_goldendb_in_rdb.sh
Shell 脚本。查询RDB检查 GoldenDB集群健康状态

# download_config_log.py
批量下载GoldenDB组件的配置文件或日志。支持按组件、文件类型、集群 ID 过滤。

# diff_config.py
对比两份配置文件，适用于新增CN、DN或者新增租户后与将配置文件与基线模板进行参数比对

# check_metadata_lock.sql
快速找出阻塞 DDL 或长事务的 metadata lock的sql，列出持锁线程和被阻塞线程的详细信息。

# get_mysql_info.sql
查询mysql的信息的SQL，用于迁移到GoldenDB之前的源库信息收集

# get_mysql_md5.sql 
提供了MySQL迁移至goldendb单分片(集中式)时的一种数据校验方案

# loader安装使用.txt
goldendb导出工具loader（loadserver免安装版）的安装和使用方式，用于从goldendb中将数据导出成csv

# modify_system_parameter.sh
goldendb服务器的参数检查和修改脚本

