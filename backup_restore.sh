#!/bin/bash
#script backup_restore.sh
#Author:laiqi
#Date: 20250325
#功能: 备份一个小租户恢复到目标租户，再备份一个大租户恢复到目标租户(这个命令是同集群恢复，跨集群恢复命令有些差别)
#使用：修改config，将脚本放到zxmanager用户下执行sh backup_restore.sh
##########config begin########
restore_cluster_id="2"
backup_root_dir="/data/gdb_backup"
restore_cluster_user="xxxxxx"
restore_cluster_pass="xxxxxxx"
restore_cluster_name="cluster3"

src_backup_max_limit_seconds=7200

src_cluster_id_small="3"
src_cluster_backup_room_id_small="1"
src_cluster_backup_type_small="inrc"

src_cluster_id_big="1"
src_cluster_backup_room_id_big="1"
src_cluster_backup_type_big="inrc"

rdb_user="xxxxxx"
rdb_pass="xxxxx"

manager_user="$(awk -F":" '/manager/{print $(1)}' /etc/passwd)"
manager_user_home="$(awk -F":" '/manager/{print $(NF-1)}' /etc/passwd)"
log_dir=$manager_user_home/backup_restore_log
mkdir -p $log_dir
log_file=${log_dir}/backup_restore_cluster_data_info_${src_cluster_id_big}_to_${restore_cluster_id}.log

#############config end##########

prepare(){
#source manager user profile
source ${manager_user_home}/.goldendb_bash_profile
if [[ ${USER} != ${manager_user} ]]; then
    echo "The current user is not an manager user, exit the script"
    exit 1
else
	dbtool -cm -ls &>/dev/null || exit 1
fi
}


backup_byroom(){
local src_cluster_id=$1
local src_cluster_backup_room_id=$2
local src_cluster_backup_type=$3
echo start backup CMD: dbtool -cm -backup -strategy=room -clusterid=${src_cluster_id} -groupid=all -roomid=${src_cluster_backup_room_id} -auto-adjust=yes -type=${src_cluster_backup_type} -backup-start-binlog=yes 
local backup_task_id=$(${manager_user_home}/bin/dbtool -cm -backup -strategy=room -clusterid=${src_cluster_id} -groupid=all -roomid=${src_cluster_backup_room_id} -auto-adjust=yes -type=${src_cluster_backup_type} -backup-start-binlog=yes | grep -A 1 "response:" | tail -1 | sed -n 's# ##g p')
sleep 5
local backup_success=0
for i in $(seq 1 $((src_backup_max_limit_seconds/10))) ;do 
	dbtool -cm -query-backup-task -taskid=${backup_task_id}
	dbtool -cm -query-backup-task -taskid=${backup_task_id} |grep 'backup success' && backup_success=1 && break
	dbtool -cm -query-backup-task -taskid=${backup_task_id} |grep 'ResultDesc'|grep -iE 'fail|error ' && exit 1
	sleep 10
done
if [[ $backup_success -ne 1 ]];then echo backup cluster ${src_cluster_id} failed ; exit 1;fi
}

backup_byslave(){
local src_cluster_id=$1
local src_cluster_backup_room_id=$2 #第二个变量随便填
local src_cluster_backup_type=$3
echo start backup CMD: dbtool -cm -backup -strategy=slave -clusterid=${src_cluster_id} -groupid=all -auto-adjust=yes -type=${src_cluster_backup_type} -backup-start-binlog=yes 
local backup_task_id=$(${manager_user_home}/bin/dbtool -cm -backup -strategy=slave -clusterid=${src_cluster_id} -groupid=all -auto-adjust=yes -type=${src_cluster_backup_type} -backup-start-binlog=yes | grep -A 1 "response:" | tail -1 | sed -n 's# ##g p')

local backup_success=0
for i in $(seq 1 $((src_backup_max_limit_seconds/10))) ;do 
	dbtool -cm -query-backup-task -taskid=${backup_task_id}
		${backup_task_id} |grep 'backup success' && backup_success=1 && break
	dbtool -cm -query-backup-task -taskid=${backup_task_id} |grep 'ResultDesc'|grep -iE 'fail|error ' && exit 1
	sleep 10
done
if [[ $backup_success -ne 1 ]];then echo backup cluster ${src_cluster_id} failed ; exit 1;fi
}

restore(){
local src_cluster_id=$1
local restore_cluster_id=$2
local restore_cluster_name=$3
local restore_cluster_user=$4
local restore_cluster_pass=$5
local backup_root_dir=$6

local backup_task_id=$(mysql -u$rdb_user -p$rdb_pass -P3309 -h$(hostname -I) -Ne "select backup_id from goldendb_omm.gdb_cluster_backup_history where cluster_id=${src_cluster_id} and result_code=0 order by end_timestamp desc limit 1")
#restore cluster restore data from src cluster backup data,record it in a log file
local restore_need_resultsinfo_file=$(dbtool -cm -query-backup-task -taskid=${backup_task_id} | awk -F ':' '/BackupResultFile/{print $2}')
#backup_start_time
local restore_time="$(awk 'END{print $3,$4}' ${restore_need_resultsinfo_file})"
#backup_end_time
#resotre_time="$(awk 'NR==1{print $(NF-3),$(NF-2)}' ${restore_need_resultsinfo_file})"
local restore_cmd="dbtool -mds -restore -bc=${src_cluster_id} -rc=${restore_cluster_id} -t=\"${restore_time}\" -d="${backup_root_dir}" -f="${restore_need_resultsinfo_file}" -user="${restore_cluster_user}" -password="${restore_cluster_pass}""


#check
local ret_cluster_name=$(mysql -u$rdb_user -p$rdb_pass -P3309 -h$(hostname -I)  -s -Ne "select cluster_name from mds.cluster_info a where cluster_id=$restore_cluster_id")
if [[ $ret_cluster_name != $restore_cluster_name ]]; then
   echo "WARNING: target cluster name is not correct!!!"
   exit 1;
fi

echo "starting restore: $restore_cmd"
dbtool -mds -restore -bc=${src_cluster_id} -rc=${restore_cluster_id} -t="${restore_time}" -d="${backup_root_dir}" -f="${restore_need_resultsinfo_file}" -user="${restore_cluster_user}" -password="${restore_cluster_pass}"
sleep 10
local err_code=$(mysql -u$rdb_user -p$rdb_pass -P3309 -h$(hostname -I) -Ne "select err_code from goldendb_omm.gdb_cluster_restore_task_info where restore_cluster_id=$restore_cluster_id  order by end_time desc limit 1")
if [[ $err_code -eq 0 ]];then
	echo "restore from ${src_cluster_id} to cluster:$restore_cluster_id cluster_name:$restore_cluster_name success"
else 
	echo restore error,error info:$(mysql -u$rdb_user -p$rdb_pass -P3309 -h$(hostname -I) -Ne "select err_desc from goldendb_omm.gdb_cluster_restore_task_info where restore_cluster_id=$restore_cluster_id  order by end_time desc limit 1" 2>/dev/null) 
fi
}

main(){
prepare 
backup_byroom $src_cluster_id_small $src_cluster_backup_room_id_small $src_cluster_backup_type_small
restore $src_cluster_id_small $restore_cluster_id $restore_cluster_name $restore_cluster_user $restore_cluster_pass $backup_root_dir
backup_byroom $src_cluster_id_big $src_cluster_backup_room_id_big $src_cluster_backup_type_big
restore $src_cluster_id_big $restore_cluster_id $restore_cluster_name $restore_cluster_user $restore_cluster_pass $backup_root_dir
} 
main |tee -a $log_file
