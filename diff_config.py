#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# laiqi20250103

"""
diff_config.py

A script that can:
1) Convert a configuration file (cnf/ini) to JSON and print to stdout.
   Usage: python diff_config.py get_json config1.my.cnf > config1.json

2) Compare two configuration files (or config vs JSON).
   Usage: python diff_config.py config1.my.cnf config2.my.cnf
          python diff_config.py config1.json config2.my.cnf

Also handles K/k or G/g suffix for numeric values (e.g., 512K => 524288, 1G => 1073741824).
"""

import sys
import os
import json
import re

# ========== Excluded parameters ==========
EXCLUDED_PARAMS = [
    'innodb_buffer_pool_size',
    'keyring_file_data',
    'port',
    'socket',
    'bind_address',
    'datadir',
    'log-error',
    'pid-file',
    'innodb_data_home_dir',
    'innodb_log_group_home_dir',
    'innodb_undo_directory',
    'server-id',
    'basedir',
    'tmpdir',
    'report_host',
    'report_port',
    'innodb_lock_wait_log_dir',
    'slow_query_log_file',
    'trx_query_log_file',
    'general_log_file',
    'rpl_semi_sync_master_group1',
    'rpl_semi_sync_master_group2',
    'rpl_semi_sync_master_group3',
    'rpl_semi_sync_master_group4',
    'rpl_semi_sync_master_group5',
    'rpl_semi_sync_master_group6',
    'rpl_semi_sync_master_group7',
    'rpl_semi_sync_master_group8',
    'rpl_semi_sync_master_group9',
    'rpl_semi_sync_master_group10',
    'rpl_semi_sync_master_enabled',
    'rpl_semi_sync_master_timeout_ratio',
    'rpl_semi_sync_slave_enabled',
    'rpl_semi_sync_master_wait_cond_lwm',
    'rpl_semi_sync_master_wait_cond_hwm',
    'read_only',
    'kafka_libdir',
    'zk_libdir',
    'gateway',
    'alarmfiledir',
    'seq_backup_dir',
    'metadataserver_ip',
    'gtm_handlethread_num',
    'zk_host_ip',
]

# ========== Regex for numeric values with optional K/k/G/g suffix ==========
NUMERIC_KG_PATTERN = re.compile(r'^(\d+)([kKgG])?$')

def parse_args():
    usage_text = "diff_config.py get_json config.my.cnf > config.json  OR  diff_config.py file1 file2"
    if len(sys.argv) < 2:
        print("Usage:\n  {}".format(usage_text))
        sys.exit(1)
    return sys.argv


def read_config_custom(config_path):
    if not os.path.isfile(config_path):
        print("Error: Configuration file '{}' does not exist.".format(config_path))
        return None

    config_dict = {}
    current_section = None

    try:
        with open(config_path, 'rb') as f:
            rawdata = f.read()
        text = rawdata.decode('utf-8-sig', errors='replace')
    except Exception as e:
        print("Error opening/decoding file '{}': {}".format(config_path, e))
        return None

    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].strip()
            if current_section not in config_dict:
                config_dict[current_section] = {}
            continue
        if not current_section:
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip()
        else:
            key = line.strip().lower()
            value = True
        if key in EXCLUDED_PARAMS:
            continue
        config_dict[current_section][key] = value

    return config_dict or {}


def write_json_to_stdout(config_dict):
    if not config_dict:
        print("{}")
    else:
        print(json.dumps(config_dict, indent=4, ensure_ascii=False))


def read_json(json_path):
    if not os.path.isfile(json_path):
        print("Error: JSON file '{}' does not exist.".format(json_path))
        return None
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print("Error reading JSON file '{}': {}".format(json_path, e))
        return None


def normalize_value(key, value):
    """
    Handle K/k => *1024, G/g => *1024^3
    Lowercase strings except booleans and sql_mode special handling
    Treat literal 'None' (case-insensitive) as empty
    """
    if isinstance(value, bool):
        return value

    val_str = str(value).strip()
    if val_str.lower() == 'none':
        return ''

    match = NUMERIC_KG_PATTERN.match(val_str)
    if match:
        number = int(match.group(1))
        suffix = match.group(2)
        if suffix:
            if suffix.lower() == 'k':
                number *= 1024
            elif suffix.lower() == 'g':
                number *= (1024 ** 3)
        return number

    val_lower = val_str.lower()
    if val_lower in ['on', '1']:
        return True
    if val_lower in ['off', '0']:
        return False

    if key == 'sql_mode':
        modes = [m.strip().lower() for m in val_str.split(',')]
        return ','.join(sorted(modes))

    return val_lower


def compare_configs(config1, config2):
    if not config1:
        config1 = {}
    if not config2:
        config2 = {}

    differences = []
    successes = []
    all_sections = set(config1.keys()) | set(config2.keys())

    for section in all_sections:
        params1 = config1.get(section, {})
        params2 = config2.get(section, {})
        all_keys = set(params1.keys()) | set(params2.keys())

        for key in all_keys:
            val1 = params1.get(key)
            val2 = params2.get(key)
            norm1 = normalize_value(key, val1) if val1 is not None else normalize_value(key, '')
            norm2 = normalize_value(key, val2) if val2 is not None else normalize_value(key, '')
            if norm1 != norm2:
                differences.append((section, key, val1, val2))
            else:
                successes.append((section, key, val1, val2))

    return differences, successes


def print_results(differences, successes, file1_name, file2_name):
    """Print the comparison outcome in the new compact format."""
    for section, key, val1, val2 in differences:
        tv = val1 if val1 is not None else ''
        rv = val2 if val2 is not None else ''
        print("{}|{}|{}|{} ~ {}|{}|{}|{}".format(file1_name, section, key, tv,file2_name, section, key, rv))

def main():
    argv = parse_args()

    if argv[1] == 'get_json':
        if len(argv) != 3:
            print("Usage: python diff_config.py get_json config1.my.cnf > config1.json")
            sys.exit(1)
        config_dict = read_config_custom(argv[2])
        write_json_to_stdout(config_dict)
        sys.exit(0)
    else:
        if len(argv) != 3:
            print("Usage:\n  python diff_config.py get_json config1.my.cnf > config1.json\n"
                  "  python diff_config.py file1 file2")
            sys.exit(1)
        file1, file2 = argv[1], argv[2]
        ext1 = os.path.splitext(file1)[1].lower()
        ext2 = os.path.splitext(file2)[1].lower()

        config1 = read_json(file1) if ext1 == '.json' else read_config_custom(file1)
        config2 = read_json(file2) if ext2 == '.json' else read_config_custom(file2)

        diffs, succs = compare_configs(config1, config2)
        print_results(diffs, succs, os.path.basename(file1), os.path.basename(file2))

if __name__ == '__main__':
    main()
