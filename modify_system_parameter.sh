#!/bin/bash
#scripts: modify_system_parameter.sh

# Function to add or modify a parameter in /etc/sysctl.conf
update_sysctl_param() {
    local param=$1
    local value=$2

    # Check if the parameter exists; modify it if it does, append it if not
    if grep -q "^${param}=" /etc/sysctl.conf; then
        sed -i "s|^${param}=.*|${param}=${value}|" /etc/sysctl.conf
    else
        echo "${param}=${value}" >> /etc/sysctl.conf
    fi

    # Apply the parameter immediately
    sysctl -w "${param}=${value}" > /dev/null 2>&1
}

modify_sysctl_param(){
    # Ensure /etc/sysctl.conf exists
    if [ ! -f /etc/sysctl.conf ]; then
        echo "[ERROR] file /etc/sysctl.conf not exists!"
        exit 1
    fi

    MemTotal=0
    ShmMaxSizecfg=0
    MemTotal=$(cat /proc/meminfo |grep MemTotal |awk '{print $2}')
    if [ -f /usr/bin/bc ]
    then
        ShmMaxSizecfg=$(echo "$MemTotal * 1024 * 2 / 3" | bc)
    else
        ShmMaxSizecfg=$(expr $MemTotal \* 1024 \* 2 / 3)
    fi

    [ $MemTotal -ge 6291456 ] && ShmMaxSizecfg=4294967295
    ## avoid value greater than 4G, and result in the invalid setting of shmmax

    # Static sysctl parameters to be updated
    declare -A SYSCTL_PARAMS=(
        ["kernel.shmmax"]="$ShmMaxSizecfg"
        ["kernel.shmall"]="$ShmMaxSizecfg"
        ["kernel.shmmni"]="4096"
        ["kernel.msgmni"]="2048"
        ["kernel.msgmnb"]="163840"
        ["kernel.msgmax"]="56383"
        ["kernel.sem"]="250 50000 100 200"
        ["net.ipv4.ip_local_port_range"]="10240 65000"
        ["net.core.rmem_max"]="1048576"
        ["net.core.rmem_default"]="1048576"
        ["net.core.wmem_max"]="262144"
        ["net.core.wmem_default"]="262144"
        ["net.ipv4.tcp_retries2"]="9"
        ["fs.file-max"]="6815744"
        ["vm.swappiness"]="0"
        ["vm.overcommit_memory"]="0"
        ["net.ipv4.tcp_keepalive_time"]="15"
        ["net.ipv4.tcp_keepalive_intvl"]="2"
        ["net.ipv4.tcp_keepalive_probes"]="10"
        ["net.core.somaxconn"]="1280"
    )

    # Update static parameters
    for param in "${!SYSCTL_PARAMS[@]}"; do
        update_sysctl_param "$param" "${SYSCTL_PARAMS[$param]}"
    done

    # Dynamic parameters
    LINUX_TYPE=$(uname -a | grep -i kylin)
    if [ "$LINUX_TYPE" ]; then
        update_sysctl_param "fs.aio-max-nr" "256000"
    fi

    # Adjust kernel.threads-max and kernel.pid_max based on current values
    THREADS_MAX=$(cat /proc/sys/kernel/threads-max)
    if [ "$THREADS_MAX" -lt 65535 ]; then
        update_sysctl_param "kernel.threads-max" "65535"
    fi

    PID_MAX=$(cat /proc/sys/kernel/pid_max)
    if [ "$PID_MAX" -lt 204800 ]; then
        update_sysctl_param "kernel.pid_max" "204800"
    fi

    # Adjust vm.min_free_kbytes based on total memory
    TOTAL_MEM=$(free -m | awk '/Mem/ {print $2}')
    SIZE_16G_IN_K=$((16 * 1024 * 1024))
    SIZE_4G_IN_K=$((4 * 1024 * 1024))

    if [ "$TOTAL_MEM" -ge 262144 ]; then
        update_sysctl_param "vm.min_free_kbytes" "$SIZE_16G_IN_K"
    else
        update_sysctl_param "vm.min_free_kbytes" "$SIZE_4G_IN_K"
    fi

    # Reload sysctl configuration
    sysctl -p > /dev/null 2>&1

    echo "[INFO] Sysctl parameters have been updated and applied successfully."
}

modify_system_limits(){
    sed -i '/^\s*\*\s*soft\s*nofile\s*[0-9]\+/d' /etc/security/limits.conf
    sed -i '/^\s*\*\s*hard\s*nofile\s*[0-9]\+/d' /etc/security/limits.conf
    sed -i '/^\s*\*\s*soft\s*nproc\s*[0-9]\+/d' /etc/security/limits.conf
    sed -i '/^\s*\*\s*hard\s*nproc\s*[0-9]\+/d' /etc/security/limits.conf
    echo "*                hard    nofile          65536" >> /etc/security/limits.conf
    echo "*                soft    nofile          65535" >> /etc/security/limits.conf
    echo "*                hard    nproc           65535" >> /etc/security/limits.conf
    echo "*                soft    nproc           65536" >> /etc/security/limits.conf

    if [ -f /etc/security/limits.d/90-nproc.conf ]
    then
        sed -i '/^\s*\*\s*soft\s*nproc\s*[0-9]\+/d' /etc/security/limits.d/90-nproc.conf
        echo "*          soft    nproc     65535" >> /etc/security/limits.d/90-nproc.conf
    fi
	
	if [ -f /etc/security/limits.d/20-nproc.conf ]
    then
        sed -i '/^\s*\*\s*soft\s*nproc\s*[0-9]\+/d' /etc/security/limits.d/20-nproc.conf
        echo "*          soft    nproc     65535" >> /etc/security/limits.d/20-nproc.conf
    fi

    if [ -f /etc/pam.d/su ]
    then
        if ! grep -q "^[     ]*session[     ]*required[     ]*pam_limits.so" /etc/pam.d/su
        then
            echo "session  required       pam_limits.so" >>/etc/pam.d/su
        fi
    fi

    if [ -f /etc/pam.d/xdm ]
    then
        if ! grep -q "^[     ]*session[     ]*required[     ]*pam_limits.so" /etc/pam.d/xdm
        then
            echo "session  required       pam_limits.so" >>/etc/pam.d/xdm
        fi
    fi

    echo "[INFO] limits config have been modified successfully."
}

modify_core_pattern(){
    # check if core-pattern is default or not
    if grep -q systemd-coredump /proc/sys/kernel/core_pattern;then
        echo "current core_pattern is '$(cat /proc/sys/kernel/core_pattern)'"
        echo "changing core_pattern to 'core-%e-%p-%t'"
        sysctl -w kernel.core_pattern='core-%e-%p-%t'
        update_sysctl_param kernel.core_pattern 'core-%e-%p-%t'
    fi
    # set core file size limit to unlimit 
    if [ "$(ulimit -c)" != "unlimited" ]; then
        ulimit -c unlimited && ulimit -Hc unlimited 
        if ! grep -q "^ulimit.*unlimited" /etc/profile; then  
        echo 'ulimit -c unlimited' >> /etc/profile
        echo 'ulimit -Hc unlimited' >> /etc/profile
        fi
    fi

    #check if core_pattern was generated correctly
    cat  <<-EOF > test_corefile.c
    #include <signal.h>
    int main(){
	raise(SIGSEGV);
	return 0;
    }
EOF
    gcc test_corefile.c -o test_corefile 
    if [ $? -eq 0 ]; then
    {
     ./test_corefile > /dev/null 2>&1
    } 2>/dev/null
    fi

    if [ -f core-test_corefile* ];then
    echo "[INFO] core file generated successfully!" && rm -f core-test_corefile*
    else
    echo "[ERROR] core file generated failed"
    fi
    rm -f test_corefile.c
    rm -f test_corefile
}
modify_io_scheduler(){
    v_devices=$(lsblk -d -n -o name,type | awk '$2 == "disk" && $1 ~ /^(sd|nvme|vd)/ {print $1}')
	for v_device in $v_devices
	do
        scheduler_file="/sys/block/$v_device/queue/scheduler"
        current_scheduler=$(grep -o '\[.*\]' "$scheduler_file" | tr -d '[]') 
        if [ -f "$scheduler_file" ]; then
            if [[ "$current_scheduler" == "deadline" || "$current_scheduler" == "mq-deadline" ]]; then
                echo "[INFO] IO scheduler for /dev/$v_device is $current_scheduler"
            else
                echo "[ERROR] IO scheduler for /dev/$v_device is not deadline or mq-deadline (current: $current_scheduler)"
            fi
        else
            echo "[ERROR] Scheduler file not found for /dev/$v_device"
        fi
    done
}

modify_performance_profile(){
    current_profile=$(tuned-adm active)
    if ! echo "$current_profile" | grep -iq 'performance'; then
        echo "[INFO] current profile is $current_profile and changing to 'throughput-performance'"
        tuned-adm profile throughput-performance
    fi
    new_profile=$(tuned-adm active)
    if echo "$new_profile" | grep -iq 'throughput-performance'; then
        echo "[INFO] changed performance profile to 'throughput-performance' success"
    else
        echo "[ERROR] changed performance profile to 'throughput-performance' failed"
    fi

}

check_swap() {
    if swapon --show | grep -q .; then
        echo "[ERROR] Swap is enabled."
        if [[ "$1" == "swapoff" ]]; then
            echo "[INFO] Attempting to disable Swap..."
            sudo swapoff -a
            if swapon --show | grep -q .; then 
                echo "[ERROR] Failed to disable Swap."   
            else
                echo "[INFO] Swap has been disabled successfully." 
                fi
            fi
    else
        echo "[INFO] Swap is not enabled."
    fi        
}

check_ntp(){
    if systemctl is-active --quiet ntpd; then
        echo "[INFO] ntpd is running"
    else
        echo "[ERROR] ntpd is not running"
    fi
}

check_firewalld(){
    if systemctl is-active --quiet firewalld; then
        echo "[ERROR] firewalld is running"
        if [[ "$1" == "stop" ]]; then
            echo "[INFO] Attempting to stop firewalld..."
            sudo systemctl stop firewalld
            sudo systemctl disable firewalld
            if systemctl is-active --quiet firewalld; then
                echo "[ERROR] Trying to firewalld failed"
            else
                echo "[INFO] Stopping firewalld success"
            fi
        fi
    else
        echo "[INFO] firewalld is not running"
    fi
}


main(){
if [ $LOGNAME != "root" ];then echo "[ERROR] logname is not root!" ;exit 1 ;fi

modify_sysctl_param
modify_system_limits
modify_core_pattern
modify_performance_profile
modify_io_scheduler
check_swap
check_ntp
check_firewalld
}

main
