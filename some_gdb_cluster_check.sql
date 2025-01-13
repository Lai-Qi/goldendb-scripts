1. 切换策略检查
-- 租户切换策略(查询rdb)
select cluster_id,cluster_name,switch_strategy AS '切换策略：0 - 一致性优先；1 - 服务性优先' ,remote_strategy AS '跨机房切换策略：0 - 手工切换；1 - 自动切换' from mds.cluster_info;

-- gtm切换策略(查询rdb)
select gtm_cluster_id,cluster_name,ifCanbeSwitch  AS '跨机房自动切换配置：0 - 跨机房不自动切换；1 - 跨机房自动切换；2 - 跨机房机房优先级切换' from mds.gtm_cluster_info;

-- manager切换策略，检查所有管理节点manager(管理节点主机下执行)
sed -n '/<city>同城<\/city>/!b;n;n;n;/<electSwitch>[a-z]\+<\/electSwitch>/p' ~zxmanager/ommagent/etc/haconfig.xml |grep -q true && echo '同城manager可自动切换' || echo '无同城manager节点或同城manager非自动切换'

-- omm切换策略，检查所有管理节点的omm(所有管理节点主机下执行)
sed -n '/<city>同城<\/city>/!b;n;n;n;/<electSwitch>[a-z]\+<\/electSwitch>/p' ~zxomm/ommagent/etc/haconfig.xml |grep -q true && echo '同城omm可自动切换' || echo '无同城omm节点或同城omm非自动切换'

2. 备份情况巡检 检查是否有7日内成功的备份（查询rdb）
SELECT
	cluster_id,
	cluster_name,
	start_timestamp,
	end_timestamp,
	CASE
		WHEN  start_timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND result_code = 0 THEN '[SUCCESS] have success backup in 7 days'
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
	FROM
		gdb_cluster_backup_history
) AS ranked
WHERE
ranked.rn = 1
order by cast(cluster_id AS int);

3.insight 全局以及租户级别的监控指标开启情况（insight页面 统计监控-通用采集-通用采集配置 ,统计监控-通用采集-功能采集开关）(查询rdb)
-- 比较每个 clusterId 的 iscollect 参数是否与 clusterId = 1 的相同，并返回那些 不同 的记录
SELECT
	t.clusterId,c.cluster_name,
	t.param_groupId,
	t.frequency, t.timeout, t.iscollect,t1.iscollect,t.device_type,s.group_desc, s.use_type, r.description, r.name,s.paramgroup_type
FROM
	goldendb_insight.insight_cluster_paramgroup t
	JOIN mds.cluster_info c ON c.cluster_id = t.clusterId 
	JOIN goldendb_insight.insight_paramgroup_info s ON t.param_groupId = s.param_groupId
	JOIN goldendb_insight.insight_paramgroup_relation r ON s.param_groupId = r.param_groupId
	JOIN goldendb_insight.insight_cluster_paramgroup t1 ON t.param_groupId = t1.param_groupId AND t1.clusterId = 1
WHERE
	s.use_type IN (1, 2)
	AND t.iscollect != t1.iscollect
	AND t.clusterId != 1
ORDER BY
	t.clusterId,
	s.use_type,
	t.param_groupId;
