#!/usr/bin/env python3
import argparse
import csv
import re
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import psycopg2
from psycopg2 import sql
from openpyxl import load_workbook

DEFAULT_ENV_PATHS = [Path('.') / '.env', Path('secrets') / '.env']

# Need to move this to a config file or something, but for now this is fine.
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

def get_report_data(conn, report):
    with conn.cursor() as cur:
        cur.execute(sql.SQL('SELECT users, small_group, role, is_officer, {report}, {reason} FROM users').format(report=sql.Identifier(report.get('name')), reason=sql.Identifier(f'{report.get('name')} Reason')))
        return cur.fetchall()
    #     columns = [desc[0] for desc in cur.description]
    #     rows = cur.fetchall()
    # return columns, rows

def get_all_users(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT users FROM users')
        return [row[0] for row in cur.fetchall()]

def generate_general_report(conn, report, ao, team, members=False):
    data = get_report_data(conn, report)
    ip1_arr = []
    on1_arr = []
    ip3_arr = []
    on2_arr = []
    abs_arr = []
    pending_arr = []
    missing_small_groups_arr = []

    for (users, small_group, role, is_officer, value, reason) in data:
        if (reason and reason.lower() != 'none'):
            full_user_info = f"{users}/{reason}"
        else:
            full_user_info = users
        if value == 'IP1':
            ip1_arr.append(full_user_info)
        elif value == 'ON1':
            on1_arr.append(full_user_info)
        elif value == 'IP3':
            ip3_arr.append(full_user_info)
        elif value == 'ON2':
            on2_arr.append(full_user_info)
        elif value == 'ABS':
            abs_arr.append(full_user_info)
        else:
            pending_arr.append(full_user_info)
            if small_group not in missing_small_groups_arr:
                missing_small_groups_arr.append(small_group)

    # Logic for numbers (and some metadata farming)
    ip1_count = len(ip1_arr)
    on1_count = len(on1_arr)
    ip3_count = len(ip3_arr)
    on2_count = len(on2_arr)
    abs_count = len(abs_arr)
    pending_count = len(pending_arr)
    present_count = ip1_count + on1_count + ip3_count + on2_count
    total_count = present_count + abs_count + pending_count
    percentage = (present_count / total_count * 100) if total_count > 0 else 0 
    dot = '🟢' if pending_count == 0 else '🟡'

    ret = '''430000 ({}) - {} Report

{} {}
    
{} | {:02d} | {:02d} | {:02.1f}%

{:02d} IP Live
{:02d} ON Live
{:02d} IP Makeup
{:02d} ON Makeup
___
    
{:02d} IP Live
{}
    
{:02d} ON Live
{}
    
{:02d} IP Makeup
{}
    
{:02d} ON Makeup
{}
    
{:02d} Absent
{}
———————————————
‼️ {:02d} Missing
{}
    '''.format(
        report.get('day'),
        ao,
        dot,
        report.get('type'),
        team,
        present_count,
        total_count,
        percentage,
        ip1_count,
        on1_count,
        ip3_count,
        on2_count,
        ip1_count,
        '\n'.join(ip1_arr) if ip1_arr else '',
        on1_count,
        '\n'.join(on1_arr) if on1_arr else '',
        ip3_count,
        '\n'.join(ip3_arr) if ip3_arr else '',
        on2_count,
        '\n'.join(on2_arr) if on2_arr else '',
        abs_count,
        '\n'.join(abs_arr) if abs_arr else '',
        pending_count,
        'Missing ' + '\nMissing '.join(missing_small_groups_arr) if missing_small_groups_arr else '',
        #'\n'.join(pending_arr) if pending_arr else ''
    )
    return ret

def update_user_field(conn, report_name, name, value, reason=None):
    with conn.cursor() as cur:
        if reason:
            cur.execute(sql.SQL('UPDATE users SET {report} = {value}, {reason} = {reason_val} WHERE users = {name}').format(
                report=sql.Identifier(report_name),
                value=sql.Literal(value),
                reason_val=sql.Literal(reason),
                reason=sql.Identifier(f'{report_name} Reason'),
                name=sql.Literal(name)
            ))
        else:
            cur.execute(sql.SQL('UPDATE users SET {report} = {value} WHERE users = {name}').format(
                report=sql.Identifier(report_name),
                value=sql.Literal(value),
                name=sql.Literal(name)
            ))
    conn.commit()

def clear_all_reports(conn, report_name):
    with conn.cursor() as cur:
        cur.execute(sql.SQL('UPDATE users SET {report} = NULL, {reason} = NULL').format(
            report=sql.Identifier(report_name),
            reason=sql.Identifier(f'{report_name} Reason')
        ))
    conn.commit()

def parse_args():
    parser = argparse.ArgumentParser(description='Generate reports from the database.')
    parser.add_argument('--env-file', type=str, help='Path to the environment file')
    parser.add_argument('--report', type=str, help='Name of the report to generate')
    parser.add_argument('--ao', type=str, help='Alpha/Omega designation for the report')
    # parser.add_argument('--team', type=str, help='Team name for the report')
    parser.add_argument('--u', type=str, help='Update a user\'s report status. Format: name=value[:reason]')
    return parser.parse_args()

# def main():
#     args = parse_args()
#     env = load_env()
#     conn_params = make_connection_params(env)
#     with psycopg2.connect(**conn_params) as conn:
#         if args.u:
#             # Parse the update argument
#             name, value = args.u.split('=', 1)
#             if ':' in value:
#                 value, reason = value.split(':', 1)
#             else:
#                 reason = None
#             update_user_field(conn, args.report, name, value, reason)
#         else:
#             report = reports.get(args.report)
#             print(f"Generating report: {report.get('name')}")
#             output = generate_general_report(conn, report, args.ao, env.get("TEAM"))
#             print(output)

# if __name__ == '__main__':
#     main()