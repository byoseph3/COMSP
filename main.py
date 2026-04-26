import csv
import re
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import psycopg2
from psycopg2 import sql
from openpyxl import load_workbook
import reports_api, spellchecker

DEFAULT_ENV_PATHS = [Path('.') / '.env', Path('secrets') / '.env']

with open('secrets/reports_arr.json', 'r') as f:
    reports = json.load(f)['Reports']

def parse_env_file(path):
    values = {}
    with path.open('r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            values[key] = value
    return values

def load_env(env_file=None):
    if env_file:
        path = Path(env_file)
        if not path.exists():
            raise FileNotFoundError(f"Environment file not found: {path}")
        return parse_env_file(path)

    for path in DEFAULT_ENV_PATHS:
        if path.exists():
            return parse_env_file(path)
    return {}

def parse_database_url(database_url):
    result = urlparse(database_url)
    user = result.username
    password = result.password
    host = result.hostname or 'localhost'
    port = result.port or 5432
    dbname = result.path.lstrip('/') if result.path else None
    return {
        'DB_USER': user,
        'DB_PASSWORD': password,
        'DB_HOST': host,
        'DB_PORT': str(port),
        'DB_NAME': dbname,
    }

def make_connection_params(env):
    if 'DATABASE_URL' in env and env.get('DB_USER') is None:
        env.update(parse_database_url(env['DATABASE_URL']))

    params = {
        'user': env.get('DB_USER'),
        'password': env.get('DB_PASSWORD'),
        'host': env.get('DB_HOST', 'localhost'),
        'port': env.get('DB_PORT', '5432'),
        'dbname': env.get('DB_NAME'),
    }

    missing = [k for k, v in params.items() if not v]
    if missing:
        raise ValueError(f"Missing database connection values: {', '.join(missing)}")

    return params

# Input will have text files of individual reports, and a .env file with the database connection info. The .env file should be in the same directory as the script, or in a 'secrets' subdirectory. The .env file should have the following variables:
# Format of the individual report:
'''

###### (<Report Day>) - <Report Type> Report

🟢 <Report Name>

<Small Group> | ##

## IP Live 
Name

## ON Live
Name/Reason

## IP Makeup 
Name/Reason

## ON Makeup
Name/Reason

## Absent
Name/Reason
———————————————

'''

def parse_individual_report(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    
    result = {
        "report_type": None, # Alpha Omega
        "class": None, # Sunday Morning Education
        "ao": None, # Alpha or Omega
        "groups": {
            "IP Live": [], # Names and Reasons
            "ON Live": [],
            "IP Makeup": [],
            "ON Makeup": [],
            "Absent": []
        }
    }

    # --- 1. Header ---
    header_match = re.match(r"(\d{6}) \((.*?)\) - (.*) (.*)", lines[0])
    if header_match:
        result["date"] = header_match.group(1)
        result["day"] = header_match.group(2)
        result["report_type"] = header_match.group(3)
    class_match = re.match(r". (.*)", lines[1])
    if class_match:
        result["class"] = class_match.group(1)

    print(result["class"])
    selector = "IP Live"
    for line in lines:
        if "IP Live" in line:
            selector = "IP Live"
        if "ON Live" in line:
            selector = "ON Live"
        if "IP Makeup" in line:
            selector = "IP Makeup"
        if "ON Makeup" in line:
            selector = "ON Makeup"
        if "Absent" in line:
            selector = "Absent"
        if "/" in line:
            result["groups"][selector].append({
                "name": line.split('/')[0].strip(),
                "reason": line.split('/')[1].strip() if line.split('/')[1].strip() else None
            })

    return result

def request_with_reports_api(conn_params, request_type, env, api_params=None):
    report, ao, name, value, reason, report_name, m_flag = None, None, None, None, None, None, False
    if api_params is not None:
        report = api_params.get('report')
        ao = api_params.get('ao')
        user = api_params.get('user')
        m_flag = api_params.get('m_flag', False)
        if user is not None:
            name = user.get('user')
            value = user.get('value')
            reason = user.get('reason')
        if report is not None:
            report_name = report.get('name')

    with psycopg2.connect(**conn_params) as conn:
        if request_type == "users":
            return reports_api.get_all_users(conn)
        elif request_type == "report":
            return reports_api.generate_general_report(conn, report, ao, env.get("TEAM"), m_flag)
        elif request_type == "update_user":
            return reports_api.update_user_field(conn, report_name, ao, name, value, reason)

def clear_all_reports():
    env = load_env()
    conn_params = make_connection_params(env)
    with psycopg2.connect(**conn_params) as conn:
        for report in reports:
            reports_api.clear_all_reports(conn, report)

def parse_args():
    parser = argparse.ArgumentParser(description='Generate reports from the database.')
    parser.add_argument('--c', action='store_true', help='Clear the database (reset for week)')
    parser.add_argument('--m', action='store_true', help='Generate missing report with members instead of teams.')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.c:
            clear_all_reports()
            print("Cleared all reports in the database.")
            return
    env = load_env()
    print("Read Input")
    conn_params = make_connection_params(env)
    users = request_with_reports_api(conn_params, "users", env, {})
    #Read all files in inputs directory
    input_dir = Path('secrets/inputs')
    report_files = list(input_dir.glob('*.txt'))

    for file_path in report_files:
        report_data = parse_individual_report(file_path)
        print(f"Processing {file_path.name}:")
        report_name = report_data.get("class")
        print(f"Report For: {report_name}")

        api_report = {}
        api_report['name'] = report_name
        api_report['type'] = report_data.get("report_type")
        for data in report_data['groups']:
            # Determine if the name given is valid, or who the name might be referring to.
            # This is done via vector searching
            value = ""
            if data == "IP Live":
                value = "IP1"
            elif data == "ON Live":
                value = "ON1"
            elif data == "IP Makeup":
                value = "IP3"
            elif data == "ON Makeup":
                value = "ON2"
            elif data == "Absent":
                value = "ABS"
            for entry in report_data['groups'][data]:
                name = spellchecker.guess_spelling(entry['name'], users, 60)
                reason = entry['reason']
                api_user = {}
                api_user['user'] = name
                api_user['value'] = value
                api_user['reason'] = reason
                request_with_reports_api(conn_params, "update_user", env, {
                    'report': api_report,
                    'user': api_user,
                    'ao': report_data.get("report_type")
                })
    # Write output of each report to an individual file
    for report in reports:
        output = request_with_reports_api(conn_params, "report", env, {
            'report': reports[report],
            'ao': "Alpha",
            "m_flag": args.m
        })
        output_path = Path('secrets/outputs') / f"{reports[report]['name']}_Alpha.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output)
        output = request_with_reports_api(conn_params, "report", env, {
            'report': reports[report],
            'ao': "Omega",
            "m_flag": args.m
        })
        output_path = Path('secrets/outputs') / f"{reports[report]['name']}_Omega.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output)

if __name__ == "__main__":
    main()