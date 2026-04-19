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
        cur.execute(sql.SQL('SELECT users, small_group, role, is_joonjin, {report} FROM users').format(report=sql.Identifier(report)))
        return cur.fetchall()
    #     columns = [desc[0] for desc in cur.description]
    #     rows = cur.fetchall()
    # return columns, rows

def generate_general_report(conn, report):
    data = get_report_data(conn, report)
    return data

def main():
    env = load_env()
    conn_params = make_connection_params(env)
    with psycopg2.connect(**conn_params) as conn:
        report = reports[0]
        print(f"Generating report: {report}")
        rows = generate_general_report(conn, report)
        for (users, small_group, role, is_joonjin, value) in rows:
            print(f"{users}, {small_group}, {role}, {is_joonjin}, {value}")
            

if __name__ == '__main__':
    main()