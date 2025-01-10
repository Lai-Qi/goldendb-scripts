#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
diff_config.py

A script to generate JSON templates from MySQL (or INI) configuration files and compare configuration files against templates or directly with each other.

Requirements:
    - Python 2.7 or Python 3.x
"""

import sys
import os
import argparse
import json
import re

# List of parameters to exclude from comparison (all in lowercase)
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

# Regular expression to detect numerical values with optional K suffix
NUMERIC_K_PATTERN = re.compile(r'^(\d+)([kK])?$')

def parse_args():
    """Parse command-line arguments with customized help output."""
    usage_text = "diff_config.py  {get_json,diff} ..."
    help_text = """
1. Generate JSON template: 
   python diff_config.py get_json config1.my.cnf config1.json 

2. Compare two configuration files directly: 
   python diff_config.py diff config1.my.cnf config2.my.cnf 

3. Compare a configuration file against a JSON:
   python diff_config.py diff config1.json config2.my.cnf
    """

    parser = argparse.ArgumentParser(
        usage=usage_text,
        description=help_text,
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Sub-commands')

    # Sub-parser for get_json
    parser_get = subparsers.add_parser('get_json', help='Generate JSON template from configuration file')
    parser_get.add_argument('config_file', help='Path to the MySQL (or INI) configuration file (e.g., config1.my.cnf)')
    parser_get.add_argument('json_file', help='Path to the output JSON file (e.g., config1.json)')

    # Sub-parser for diff
    parser_diff = subparsers.add_parser('diff', help='Compare two configuration files or a configuration file with a JSON template')
    parser_diff.add_argument('file1', help='Path to the first file (either a config file or a JSON template)')
    parser_diff.add_argument('file2', help='Path to the second file (either a config file or a JSON template)')

    return parser.parse_args()

def read_config_custom(config_path):
    """
    Read a MySQL (or INI) configuration file and return a dictionary excluding certain parameters.
    Handles both 'key = value' and standalone flags.
    """
    if not os.path.isfile(config_path):
        print("Error: Configuration file '{}' does not exist.".format(config_path))
        sys.exit(1)

    config_dict = {}
    current_section = None

    try:
        with open(config_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#') or line.startswith(';'):
                    continue
                # Detect section headers
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].strip()
                    if current_section not in config_dict:
                        config_dict[current_section] = {}
                    continue
                # Ensure we are within a section
                if not current_section:
                    print("Warning: Line {} is outside of any section and will be skipped.".format(line_num))
                    continue
                # Parse key-value pairs or flags
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip().lower()
                    value = value.strip()
                else:
                    key = line.strip().lower()
                    value = True  # Flags are set to True
                # Exclude parameters as needed
                if key in EXCLUDED_PARAMS:
                    continue
                config_dict[current_section][key] = value
    except IOError as e:
        print("Error reading configuration file '{}': {}".format(config_path, e))
        sys.exit(1)

    return config_dict

def write_json(config_dict, json_path):
    """Write the configuration dictionary to a JSON file."""
    try:
        with open(json_path, 'w') as json_file:
            json.dump(config_dict, json_file, indent=4, ensure_ascii=False)
        print("JSON template successfully written to '{}'.".format(json_path))
    except IOError as e:
        print("Error writing JSON file '{}': {}".format(json_path, e))
        sys.exit(1)

def read_json(json_path):
    """Read a JSON file and return its contents as a dictionary."""
    if not os.path.isfile(json_path):
        print("Error: JSON file '{}' does not exist.".format(json_path))
        sys.exit(1)

    try:
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)
        return data
    except ValueError as e:
        print("Error reading JSON file '{}': {}".format(json_path, e))
        sys.exit(1)

def normalize_value(key, value):
    """
    Normalize the configuration parameter value for comparison.
    - Convert numerical values with K suffix to integers.
    - Compare strings case-insensitively.
    - Treat 'ON'/'1' as True, 'OFF'/'0' as False.
    - For 'sql_mode', sort the modes.
    """
    # Handle boolean flags
    if isinstance(value, bool):
        return value

    # Handle numerical values with K suffix
    match = NUMERIC_K_PATTERN.match(str(value))
    if match:
        number = int(match.group(1))
        suffix = match.group(2)
        if suffix:
            number *= 1024
        return number

    # Handle 'ON', 'OFF', '1', '0'
    value_lower = str(value).lower()
    if value_lower in ['on', '1']:
        return True
    if value_lower in ['off', '0']:
        return False

    # Handle 'sql_mode' by sorting the modes
    if key == 'sql_mode':
        modes = [mode.strip().lower() for mode in str(value).split(',')]
        modes_sorted = sorted(modes)
        return ','.join(modes_sorted)

    # Default case: lowercase the string for case-insensitive comparison
    return str(value).lower()

def compare_configs(config1, config2):
    """
    Compare two configuration dictionaries and return two lists:
    - differences: list of tuples (section, key, config1_value, config2_value) where values differ or missing
    - successes: list of tuples (section, key, config1_value, config2_value) where values are the same
    """
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
                # One of the parameters is missing
                differences.append((section, key, val1, val2))
            else:
                norm_val1 = normalize_value(key, val1)
                norm_val2 = normalize_value(key, val2)
                if norm_val1 != norm_val2:
                    differences.append((section, key, val1, val2))
                else:
                    successes.append((section, key, val1, val2))
    
    return differences, successes

def print_results(differences, successes, file1_name, file2_name, isprint_success=0):
    """Print the differences and successes in the specified log format.
    
    Args:
        differences (list): List of tuples containing differences.
        successes (list): List of tuples containing successes.
        file1_name (str): Name of the first file (template or config).
        file2_name (str): Name of the second file (target config or template).
        isprint_success (int, optional): Flag to print [SUCCESS] logs. 0 = No, 1 = Yes. Defaults to 0.
    """
    # 打印 [ERROR] 日志
    for diff in differences:
        section, key, val1, val2 = diff
        template_val = val1 if val1 is not None else "MISSING"
        target_val = val2 if val2 is not None else "MISSING"
        status = "[ERROR]"
        print("{} template_json:{} segment:{} parameter:{} template_value:{} | target_file:{} segment:{} parameter:{} target_value:{}".format(
            status, file1_name, section, key, template_val,
            file2_name, section, key, target_val
        ))
        print("-" * 100)
    
    # 根据 isprint_success 决定是否打印 [SUCCESS] 日志
    if isprint_success:
        for success in successes:
            section, key, val1, val2 = success
            status = "[SUCCESS]"
            print("{} template_json:{} segment:{} parameter:{} template_value:{} | target_file:{} segment:{} parameter:{} target_value:{}".format(
                status, file1_name, section, key, val1,
                file2_name, section, key, val2
            ))
    
    # 如果没有差异且不打印成功日志，提示无可比较的参数
    if not differences and not (isprint_success and successes):
        print("[SUCCESS] No parameters found to compare between '{}' and '{}'.".format(
            file1_name, file2_name
        ))

def main():
    args = parse_args()

    if args.command == 'get_json':
        # 生成 JSON 模板
        config_dict = read_config_custom(args.config_file)
        write_json(config_dict, args.json_file)

    elif args.command == 'diff':
        file1 = args.file1
        file2 = args.file2

        # 自动识别文件类型
        file1_ext = os.path.splitext(file1)[1].lower()
        file2_ext = os.path.splitext(file2)[1].lower()

        # 情况 1: 两个文件都是 JSON
        if file1_ext == '.json' and file2_ext == '.json':
            config1 = read_json(file1)
            config2 = read_json(file2)
        # 情况 2: 一个是 JSON，另一个是配置文件
        elif file1_ext == '.json' and file2_ext in ['.cnf', '.ini']:
            config1 = read_json(file1)
            config2 = read_config_custom(file2)
        elif file1_ext in ['.cnf', '.ini'] and file2_ext == '.json':
            config1 = read_config_custom(file1)
            config2 = read_json(file2)
        # 情况 3: 两个都是配置文件
        elif file1_ext in ['.cnf', '.ini'] and file2_ext in ['.cnf', '.ini']:
            config1 = read_config_custom(file1)
            config2 = read_config_custom(file2)
        else:
            print("Error: Unsupported file types. Supported types are '.json', '.cnf', '.ini'.")
            sys.exit(1)

        differences, successes = compare_configs(config1, config2)
        
        # 设置是否打印 [SUCCESS] 日志
        # 根据需要将 isprint_success 设置为 1 或 0
        isprint_success = 0  # 设置为 1 以打印 [SUCCESS] 日志，0 则不打印

        print_results(differences, successes, os.path.basename(file1), os.path.basename(file2), isprint_success)
    else:
        print("Error: No valid sub-command provided. Use 'get_json' or 'diff'.")
        sys.exit(1)

if __name__ == '__main__':
    main()

