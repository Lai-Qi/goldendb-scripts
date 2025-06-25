#!/usr/bin/env python
# -*- coding: utf-8 -*

from __future__ import absolute_import, division, print_function, unicode_literals
import pymysql
import requests
import os
import sys
import logging
import argparse
import time
import signal

# -------------------- config begin --------------------

DEFAULT_RDB_HOST = '127.0.0.1'
DEFAULT_RDB_PORT = 3309
DEFAULT_RDB_USER = 'xxx'
DEFAULT_RDB_PASSWORD = 'xxx'
DEFAULT_DB_NAME = 'goldendb_omm'

IAPASSWORD = 'xxx'
IA_USER = 'xxx'
API_PORT = 8021
# -------------------- config end --------------------

host_name = os.uname()[1]
DEFAULT_OUTPUT_DIR = host_name + '_downloaded_files'

APP_KEY = '1'
COMPARE_ID = '2'
STREAM_NO = '3'
DEFAULT_CONNECT_TIMEOUT = 10
if API_PORT == 8021:
    API_ENDPOINT_TEMPLATE = ("http://{device_ip}:{port}/api/insightAgent/goldenDbInstall/downloadFile")
elif API_PORT == 8024:
    API_ENDPOINT_TEMPLATE = ("https://{device_ip}:{port}/api/insightAgent/goldenDbInstall/downloadFile")
else:
    API_ENDPOINT_TEMPLATE = ("http://{device_ip}:{port}/api/insightAgent/goldenDbInstall/downloadFile")

# ---- 组件信息 ----
USER_TYPES_CONFIG = {
    'DB': {
        'device_type': 1,
        'sql_query': """
            SELECT DISTINCT c.cluster_id,
                   d.cluster_name,
                   a.device_ip,
                   a.apply_user,
                   b.appuser_dir
            FROM goldendb_omm.gdb_device_info a
            LEFT JOIN goldendb_omm.gdb_cityinstall_db b
                   ON a.device_ip = b.host_ip
                  AND a.agent_port = b.listen_port
            JOIN mds.db_info c
                  ON c.db_ip = a.device_ip
                 AND c.db_port = a.device_port
            JOIN mds.cluster_info d
                  ON c.cluster_id = d.cluster_id
            WHERE a.device_type = 1;
        """
    },
    'DBPROXY': {
        'device_type': 2,
        'sql_query': """
            SELECT DISTINCT
                d.cluster_id,
                e.cluster_name,
                a.device_ip,
                a.apply_user,
                b.appuser_dir
            FROM goldendb_omm.gdb_device_info a
            LEFT JOIN goldendb_omm.gdb_cityinstall_dbproxy b
                   ON a.device_ip = b.host_ip
                  AND a.device_port = b.listen_port
            JOIN mds.proxy_info c
                 ON c.proxy_ip = a.device_ip
                AND c.proxy_port = a.device_port
            JOIN mds.cluster_proxy_bind_info d
                 ON c.proxy_id = d.proxy_id
            JOIN mds.cluster_info e
                 ON d.cluster_id = e.cluster_id
            WHERE a.device_type = 2;
        """
    },
    'GTM': {
        'device_type': 3,
        'sql_query': """
            SELECT DISTINCT
                d.db_cluster_id AS cluster_id,
                e.cluster_name,
                a.device_ip,
                a.apply_user,
                b.appuser_dir
            FROM goldendb_omm.gdb_device_info a
            LEFT JOIN goldendb_omm.gdb_cityinstall_gtm b
                   ON a.device_ip = b.host_ip
                  AND a.device_port = b.listen_port
            JOIN mds.gtm_info c
                 ON a.device_ip = c.gtm_ip
                AND a.device_port = c.gtm_port
            JOIN mds.gtm_db_bind_info d
                 ON c.gtm_cluster_id = d.gtm_cluster_id
            JOIN mds.cluster_info e
                 ON d.db_cluster_id = e.cluster_id
            WHERE a.device_type = 3;
        """
    }
}

# ---- 统一下载清单 ----
DOWNLOAD_TARGETS = {
    'DB': {
        'CONFIG': ['etc/my.cnf','etc/os.ini'],
        'LOG':    ['log/mysqld1.log', 'log/dbagent.log','log/slow.log','log/general.log']
    },
    'DBPROXY': {
        'CONFIG': ['etc/proxy.ini','etc/os.ini'],
        'LOG':    ['log/dbproxy.log','log/slow_query.log','log/general_query.log']
    },
    'GTM': {
        'CONFIG': ['etc/gtm.ini','etc/os.ini'],
        'LOG':    ['log/gtm.log']
    }
}


MAX_RETRIES = 1
RETRY_DELAY = 0.5
stop_flag = False


def sigint_handler(signum, frame):
    global stop_flag
    logging.warning("Received Ctrl-C. Exiting after current device.")
    stop_flag = True


def setup_logging(script_dir):
    log_file = os.path.join(script_dir, 'batch_download.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


def connect_to_database(host, port, user, password, db_name):
    try:
        db = pymysql.connect(
            host=host,
            port=port,
            user=user,
            passwd=password,
            db=db_name,
            charset="utf8",
            cursorclass=pymysql.cursors.Cursor
        )
        logging.info("Connected to MySQL.")
        return db
    except pymysql.MySQLError as e:
        logging.error("MySQL connection error: %s", e)
        sys.exit(1)


def fetch_device_info(db, query):
    try:
        cursor = db.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        logging.info("Fetched %d devices.", len(rows))
        return rows
    except pymysql.MySQLError as e:
        logging.error("Query error: %s", e)
        sys.exit(1)


def download_files(cluster_id, cluster_name, device_type,
                   device_ip, apply_user, appuser_dir,
                   output_dir, categories):
    """
    下载指定类别（CONFIG / LOG）的目标文件。
    """
    api_endpoint = API_ENDPOINT_TEMPLATE.format(device_ip=device_ip, port=API_PORT)
    auth = (IA_USER, IAPASSWORD)

    for category, rel_paths in DOWNLOAD_TARGETS[device_type].items():
        if category not in categories:
            continue

        for rel_path in rel_paths:
            if stop_flag:
                return

            download_file_path = os.path.join(appuser_dir, rel_path)
            fname = os.path.basename(rel_path)
            out_filename = "{0}_{1}_{2}_{3}_{4}_{5}_{6}".format(
                cluster_id, cluster_name, device_type, category,
                device_ip, apply_user, fname
            )
            out_path = os.path.join(output_dir, out_filename)

            params = {
                'appKey': APP_KEY,
                'compareID': COMPARE_ID,
                'streamNo': STREAM_NO,
                'downloadFilePath': download_file_path
            }

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logging.info("[%s] %s → %s (try %d)",
                                 category, download_file_path, out_path, attempt)

                    resp = requests.get(
                        api_endpoint,
                        params=params,
                        auth=auth,
                        timeout=DEFAULT_CONNECT_TIMEOUT,
                        verify=False
                    )

                    if resp.status_code == 200:
                        with open(out_path, 'wb') as f:
                            f.write(resp.content)
                        logging.info("Saved: %s", out_path)
                        break
                    else:
                        logging.error("HTTP %s %s | %s",
                                      resp.status_code, resp.reason, resp.url)
                        logging.error("Content: %s", resp.text)
                except requests.exceptions.RequestException as e:
                    logging.error("Error: %s", e)

                if attempt < MAX_RETRIES:
                    logging.info("Retrying in %.1f s…", RETRY_DELAY)
                    time.sleep(RETRY_DELAY)
                else:
                    logging.error("Failed: %s", download_file_path)


def main():
    parser = argparse.ArgumentParser(
    description='Batch download CONFIG/LOG files.',
    epilog='''\
Examples
--------
# 所有组件，所有类型
python download_config_log.py --components DB DBPROXY GTM
# 下载CONFIG和LOG
python download_config_log.py --components DBPROXY --type CONFIG LOG
# 指定cluster-id
python download_config_log.py --type CONFIG LOG --components DB DBPROXY GTM --cluster-id 1
# 指定密码交互
python download_config_log.py --components DB --type CONFIG LOG --ask-password
''',
    formatter_class=argparse.RawTextHelpFormatter
)
    parser.add_argument('--components', '-c', nargs='+',
                        choices=list(USER_TYPES_CONFIG.keys()),
                        default=['DB', 'DBPROXY', 'GTM'],
                        help='Component types to process, e.g. DB DBPROXY GTM.')

    parser.add_argument('--type', '-T', nargs='+',
                        choices=['CONFIG', 'LOG'],
                        default=['CONFIG'],
                        help='File categories to download: CONFIG, LOG, or both.')

    parser.add_argument('--rdb-host', default=DEFAULT_RDB_HOST)
    parser.add_argument('--rdb-port', type=int, default=DEFAULT_RDB_PORT)
    parser.add_argument('--rdb-user', default=DEFAULT_RDB_USER)
    parser.add_argument('--rdb-password', default=DEFAULT_RDB_PASSWORD)
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--cluster-id', nargs='*',
                        help='Download only these cluster_id(s).')
    parser.add_argument('-a', '--ask-password', action='store_true',
                        help='Prompt for RDB password interactively')

    args = parser.parse_args()

    # 统一转大写，防意外大小写
    categories = [c.upper() for c in args.type]

    if args.ask_password:
        from getpass import getpass
        rdb_password = getpass("RDB password: ")
    else:
        rdb_password = args.rdb_password

    script_dir = os.path.abspath(os.path.dirname(__file__))
    setup_logging(script_dir)
    logging.info("=== Batch download script started ===")
    logging.info("Categories to download: %s", categories)

    signal.signal(signal.SIGINT, sigint_handler)

    db = connect_to_database(args.rdb_host, args.rdb_port,
                             args.rdb_user, rdb_password, DEFAULT_DB_NAME)

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    specified_clusters = set(args.cluster_id) if args.cluster_id else None
    if specified_clusters:
        logging.info("Specified clusters: %s", specified_clusters)

    for comp_type in args.components:
        if stop_flag:
            break
        cfg = USER_TYPES_CONFIG[comp_type]
        logging.info("Processing component: %s", comp_type)
        rows = fetch_device_info(db, cfg['sql_query'])
        if not rows:
            logging.warning("No devices for %s", comp_type)
            continue

        for row in rows:
            if stop_flag:
                break
            if len(row) < 5:
                logging.warning("Incomplete row: %s", row)
                continue

            cluster_id   = str(row[0] or 'None')
            cluster_name = row[1] or 'None'
            device_ip    = row[2]
            apply_user   = row[3]
            appuser_dir  = row[4]

            if not all([device_ip, apply_user, appuser_dir]):
                logging.warning("Missing data: %s", row)
                continue
            if specified_clusters and cluster_id not in specified_clusters:
                continue

            download_files(cluster_id, cluster_name, comp_type,
                           device_ip, apply_user, appuser_dir,
                           args.output_dir, categories)

    db.close()
    logging.info("=== Batch download script finished ===")


if __name__ == '__main__':
    main()
