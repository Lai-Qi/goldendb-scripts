#!/bin/bash
# Filename: check_goldendb_in_rdb.sh
# Author: laiqi
# Date: 20250114

# ========== Modify RDB connection info here ==========
HOST="127.0.0.1"
PORT="3309"
USER="xxxxxx"
PASSWORD="xxxxxxx"
DATABASE="goldendb_omm"
CHARSET="utf8"
# ================================================

# The single output file where everything goes
OUTPUT_FILE="$(hostname)_$(date +%F)_check_results.txt"

# ------------------------------------------------
# Helper function to append a query result
# with a title block
# ------------------------------------------------
run_query_with_separator() {
  local check_title="$1"
  local query="$2"

  echo "============================================" >> "$OUTPUT_FILE"
  echo "$check_title" >> "$OUTPUT_FILE"
  echo "============================================" >> "$OUTPUT_FILE"

  # Run query in tab-separated mode, pipe to column for alignment
  mysql -h"$HOST" \
        -u"$USER" \
        -p"$PASSWORD" \
        -P"$PORT" \
        --database="$DATABASE" \
        --default-character-set="$CHARSET" \
        --batch \
        -e "$query" \
  | column -t -s $'\t' >> "$OUTPUT_FILE"

  echo "" >> "$OUTPUT_FILE"  # blank line after each section
}

# Remove old output if it exists
rm -f "$OUTPUT_FILE"

############################################
# 1. 切换策略检查 - 租户切换策略
############################################
run_query_with_separator \
"1. 切换策略检查 - 租户切换策略" \
"
SELECT
  cluster_id,
  cluster_name,
  switch_strategy AS '切换策略：0 - 一致性优先；1 - 服务性优先',
  remote_strategy AS '跨机房切换策略：0 - 手工切换；1 - 自动切换'
FROM mds.cluster_info;
"

############################################
# 1. 切换策略检查 - gtm切换策略
############################################
run_query_with_separator \
"1. 切换策略检查 - gtm切换策略" \
"
SELECT
  gtm_cluster_id,
  gtm_group_id,
  hwm,
  lwm,
  ifMastercount,
  cfgWIncFile,
  ifCanbeSwitch AS '跨机房自动切换配置：0 - 跨机房不自动切换；1 - 跨机房自动切换；2 - 跨机房机房优先级切换'
FROM mds.gtm_group_info;
"

############################################
# 2. 备份情况巡检
############################################
run_query_with_separator \
"2. 备份情况巡检" \
"
SELECT
  cluster_id,
  cluster_name,
  start_timestamp,
  end_timestamp,
  CASE
    WHEN start_timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
         AND result_code = 0
    THEN '[SUCCESS] have success backup in 7 days'
    ELSE '[ERROR] do not have success backup in 7 days'
  END AS backup_status
FROM (
  SELECT
    backup_id,
    cluster_id,
    cluster_name,
    result_code,
    result_desc,
    backup_type,
    backup_task_type,
    create_time,
    start_timestamp,
    end_timestamp,
    group_num,
    stream_no,
    backup_strategy,
    force_backup_master,
    ROW_NUMBER() OVER (PARTITION BY cluster_id ORDER BY start_timestamp DESC) AS rn
  FROM goldendb_omm.gdb_cluster_backup_history
) AS ranked
WHERE ranked.rn = 1
ORDER BY CAST(cluster_id AS SIGNED);
"

############################################
# 3. insight 全局&租户级别监控指标开启情况
############################################
run_query_with_separator \
"3. insight 全局&租户级别监控指标开启情况" \
"
SELECT
  t.clusterId,
  c.cluster_name,
  t.param_groupId,
  t.frequency,
  t.timeout,
  t.iscollect,
  t1.iscollect,
  t.device_type,
  s.group_desc,
  s.use_type,
  r.description,
  r.name,
  s.paramgroup_type
FROM goldendb_insight.insight_cluster_paramgroup t
JOIN mds.cluster_info c ON c.cluster_id = t.clusterId
JOIN goldendb_insight.insight_paramgroup_info s ON t.param_groupId = s.param_groupId
JOIN goldendb_insight.insight_paramgroup_relation r ON s.param_groupId = r.param_groupId
JOIN goldendb_insight.insight_cluster_paramgroup t1
     ON t.param_groupId = t1.param_groupId AND t1.clusterId = 1
WHERE s.use_type IN (1, 2)
  AND t.iscollect != t1.iscollect
  AND t.clusterId != 1
ORDER BY t.clusterId, s.use_type, t.param_groupId;
"

############################################
# 4. 水位检查 - DN水位检查
############################################
run_query_with_separator \
"4. 水位检查 - DN水位检查" \
"
SELECT
  cluster_id,
  hwm,
  lwm,
  h_included,
  l_included
FROM mds.waterlevel_info
WHERE city_id = 1;
"

############################################
# 5. RDB SEMI-SYNC CHECK
#    Query device_ip/device_port from gdb_device_info
#    then loop through each RDB instance.
############################################

echo "============================================" >> "$OUTPUT_FILE"
echo "5. RDB SEMI-SYNC CHECK" >> "$OUTPUT_FILE"
echo "============================================" >> "$OUTPUT_FILE"

# 5.1 Query your metadata DB to retrieve device_ip/port
#     for RDB devices (device_type=11)
devices=$(mysql -h"$HOST" \
                -u"$USER" \
                -p"$PASSWORD" \
                -P"$PORT" \
                --default-character-set="$CHARSET" \
                --batch \
                --skip-column-names \
                -e '
SELECT a.device_ip,
       a.device_port,
       a.city_id,
       a.room_id
FROM gdb_device_info a
LEFT JOIN gdb_cityinstall_omm b
       ON a.device_ip = b.ip
      AND a.device_port = b.rdb_port
WHERE a.device_type = 11
ORDER BY room_id;
' "$DATABASE")

# 5.2 Loop over each device, connect, run 'SHOW VARIABLES'
while IFS=$'\t' read -r device_ip device_port city_id room_id; do
  
  # Append device info
  {
    echo "----------------------------------------------"
    echo "Device IP:    $device_ip"
    echo "Device Port:  $device_port"
    echo "City ID:      $city_id"
    echo "Room ID:      $room_id"
    echo "----------------------------------------------"
  } >> "$OUTPUT_FILE"

  # Connect to each device and show semi-sync variables
  mysql -h"$device_ip" \
        -u"$USER" \
        -p"$PASSWORD" \
        -P"$device_port" \
        --batch \
        --skip-column-names \
        -e 'SHOW VARIABLES LIKE "rpl_semi_sync_master_wait_cond%";' 2>/dev/null \
  | column -t >> "$OUTPUT_FILE"

  echo "" >> "$OUTPUT_FILE"
done <<< "$devices"

echo "===== ALL CHECKS DONE =====" >> "$OUTPUT_FILE"
echo "Done! Please check $OUTPUT_FILE for full results."
