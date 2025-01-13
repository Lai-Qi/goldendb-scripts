#!/usr/bin/env python
# -*- coding: utf-8 -*-
# laiqi20250103

"""
diff_config.py

A script that can:
1) Compare two configuration files (or config vs JSON).
   Usage: python diff_config.py config1.my.cnf config2.my.cnf
          python diff_config.py config1.json config2.my.cnf

2) Convert a configuration file (cnf/ini) to JSON and print to stdout.
   Usage: python diff_config.py get_json config1.my.cnf > config1.json


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
    help_text = """
1) Convert config to JSON and print to stdout:
   python diff_config.py get_json config1.my.cnf > config1.json

2) Compare two files (either config or JSON):
   python diff_config.py file1 file2
    """
    if len(sys.argv) < 2:
        print("Usage:\n  {}".format(usage_text))
        sys.exit(1)
    return sys.argv

def read_config_custom(config_path):
    """
    Read a MySQL (or INI) config, ignoring BOM if present, build dictionary of sections & params,
    excluding certain parameters.
    """
    if not os.path.isfile(config_path):
        print("Error: Configuration file '{}' does not exist.".format(config_path))
        return None

    config_dict = {}
    current_section = None

    # Attempt to handle possible BOM by reading raw bytes first
    try:
        with open(config_path, 'rb') as f:
            rawdata = f.read()
        # Decode with 'utf-8-sig' to remove BOM if present
        text = rawdata.decode('utf-8-sig', errors='replace')
    except Exception as e:
        print("Error opening/decoding file '{}': {}".format(config_path, e))
        return None

    lines = text.splitlines()
    if not lines:
        print("Warning: File '{}' is empty or unreadable.".format(config_path))

    for idx, line in enumerate(lines, start=1):
        line = line.strip()
        # Debug:
        # print("[Debug] line {} => {!r}".format(idx, line))

        # Skip empty/comment lines
        if not line or line.startswith('#') or line.startswith(';'):
            continue

        # Detect section headers
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].strip()
            # Debug:
            # print("Now in section [{}].".format(current_section))
            if current_section not in config_dict:
                config_dict[current_section] = {}
            continue

        if not current_section:
            # If we haven't encountered a [section] yet, skip
            continue

        # Parse key=value
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip()
        else:
            key = line.strip().lower()
            value = True

        # Exclude if in EXCLUDED_PARAMS
        if key in EXCLUDED_PARAMS:
            continue

        config_dict[current_section][key] = value

    # If after reading lines we have an empty config_dict, we might want to check
    if not config_dict:
        # Possibly the file had all lines commented out or was BOM invalid
        # For debug, you can uncomment next line
        # print("[Debug] Final config_dict is empty.")
        return {}

    return config_dict

def write_json_to_stdout(config_dict):
    """
    Convert config_dict to JSON and print to stdout.
    If config_dict is None or empty, output an empty object "{}" instead of "null".
    """
    if not config_dict:
        # If config_dict is None or empty, print "{}"
        print("{}")
    else:
        print(json.dumps(config_dict, indent=4, ensure_ascii=False))

def read_json(json_path):
    """Read a JSON file and return dict. Return None if fail."""
    if not os.path.isfile(json_path):
        print("Error: JSON file '{}' does not exist.".format(json_path))
        return None

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print("Error reading JSON file '{}': {}".format(json_path, e))
        return None

def normalize_value(key, value):
    """
    Handle K/k => *1024, G/g => *1024^3
    Lowercase strings except 'ON','OFF','1','0','sql_mode' special handling
    """
    if isinstance(value, bool):
        return value

    val_str = str(value).strip()

    # Numeric with optional K/G
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

    # Boolean or integer
    val_lower = val_str.lower()
    if val_lower in ['on', '1']:
        return True
    if val_lower in ['off', '0']:
        return False

    # sql_mode => split, sort
    if key == 'sql_mode':
        modes = [m.strip().lower() for m in val_str.split(',')]
        modes_sorted = sorted(modes)
        return ','.join(modes_sorted)

    # default: lowercase
    return val_lower

def compare_configs(config1, config2):
    """
    Return differences, successes
    config1, config2 are dict, can be None => means read failed => treat as {}
    """
    if not config1:
        config1 = {}
    if not config2:
        config2 = {}

    differences = []
    successes = []

    all_sections = set(config1.keys()).union(set(config2.keys()))

    for section in all_sections:
        params1 = config1.get(section, {})
        params2 = config2.get(section, {})
        all_keys = set(params1.keys()).union(set(params2.keys()))

        for key in all_keys:
            val1 = params1.get(key)
            val2 = params2.get(key)
            if val1 is None or val2 is None:
                differences.append((section, key, val1, val2))
            else:
                norm1 = normalize_value(key, val1)
                norm2 = normalize_value(key, val2)
                if norm1 != norm2:
                    differences.append((section, key, val1, val2))
                else:
                    successes.append((section, key, val1, val2))

    return differences, successes

def print_results(differences, successes, file1_name, file2_name, isprint_success=0):
    """Print the comparison outcome."""
    # Print ERROR
    for (section, key, val1, val2) in differences:
        status = "[ERROR]"
        tv = val1 if val1 is not None else "MISSING"
        rv = val2 if val2 is not None else "MISSING"
        print("{} template_json:{} segment:{} parameter:{} template_value:{} | target_file:{} segment:{} parameter:{} target_value:{}".format(
            status, file1_name, section, key, tv,
            file2_name, section, key, rv
        ))
        print("-"*100)
    
    # Print SUCCESS if needed
    if isprint_success:
        for (section, key, val1, val2) in successes:
            status = "[SUCCESS]"
            print("{} template_json:{} segment:{} parameter:{} template_value:{} | target_file:{} segment:{} parameter:{} target_value:{}".format(
                status, file1_name, section, key, val1,
                file2_name, section, key, val2
            ))
    
    # If no diffs & no success lines => final summary
    if not differences and not (isprint_success and successes):
        print("[SUCCESS] No parameters found to compare between '{}' and '{}'.".format(
            file1_name, file2_name
        ))

def main():
    argv = parse_args()

    # If first arg is 'get_json'
    if argv[1] == 'get_json':
        if len(argv) != 3:
            print("Usage: python diff_config.py get_json config1.my.cnf > config1.json")
            sys.exit(1)
        config_path = argv[2]
        config_dict = read_config_custom(config_path)
        write_json_to_stdout(config_dict)
        sys.exit(0)
    else:
        # Expect 2 files
        if len(argv) != 3:
            print("Usage:\n  python diff_config.py get_json config1.my.cnf > config1.json\n"
                  "  python diff_config.py file1 file2")
            sys.exit(1)
        file1 = argv[1]
        file2 = argv[2]

        # detect extension
        ext1 = os.path.splitext(file1)[1].lower()
        ext2 = os.path.splitext(file2)[1].lower()

        if ext1 == '.json':
            config1 = read_json(file1)
        else:
            config1 = read_config_custom(file1)
        if ext2 == '.json':
            config2 = read_json(file2)
        else:
            config2 = read_config_custom(file2)

        # do compare
        differences, successes = compare_configs(config1, config2)

        # by default, isprint_success=0
        isprint_success = 0
        print_results(differences, successes, os.path.basename(file1), os.path.basename(file2), isprint_success)

if __name__ == '__main__':
    main()

