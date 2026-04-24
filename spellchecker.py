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
from rapidfuzz import fuzz
import reports_api

DEFAULT_ENV_PATHS = [Path('.') / '.env', Path('secrets') / '.env']

def check_spelling(word, dictionary, threshold=70):
    ratio_dict = []
    for entry in dictionary:
        ratio = fuzz.token_sort_ratio(word, entry)
        ratio_dict.append((entry, ratio))
    
    # print(f"Spelling Check Results for {word}:\n")
    ratio_dict.sort(key=lambda x: x[1], reverse=True)
    # for entry, ratio in ratio_dict:
    #     print(f"  '{entry}': {ratio}%")
    return ratio_dict[0] if ratio_dict[0] and ratio_dict[0][1] >= threshold else (None, 0)

def guess_spelling(word, dictionary, threshold=70):
    if word in dictionary:
        # print(f"Guessed Spelling for '{word}': '{word}\n")
        return word
    guess_entry = check_spelling(word, dictionary, threshold)
    # print(f"Guessed Spelling for '{word}': '{guess_entry[0]}\n")
    return guess_entry[0] if guess_entry[1] >= threshold else None

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

def parse_args():
    parser = argparse.ArgumentParser(description="Spell Checker for Report Names")
    parser.add_argument('--u', type=str, help='User to spell check')
    return parser.parse_args()

def main():
    env = load_env()
    # print("Read Input")
    conn_params = make_connection_params(env)
    users = []
    with psycopg2.connect(**conn_params) as conn:
        users = reports_api.get_all_users(conn)
    args = parse_args()
    if args.u:
        guess = guess_spelling(args.u, users, 60)
        print(f"Guessed Spelling for '{args.u}': '{guess}\n")

if __name__ == "__main__":
    main()