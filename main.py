import csv
import re
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import psycopg2
from psycopg2 import sql
from openpyxl import load_workbook

DEFAULT_ENV_PATHS = [Path('.') / '.env', Path('secrets') / '.env']

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
    if 'DATABASE_URL' in env:
        return parse_database_url(env['DATABASE_URL'])
    required_keys = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']
    if all(key in env for key in required_keys):
        return {key: env[key] for key in required_keys}
    raise ValueError("Database connection information is missing. Please provide either DATABASE_URL or all of DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, and DB_NAME.")

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
        content = f.read()

    # Extract report day and type
    header_match = re.match(r'...... \((.*?)\) - (.*?) Report', content)
    if not header_match:
        raise ValueError("Report header is not in the expected format.")
    report_day = header_match.group(1).strip()
    report_type = header_match.group(2).strip()

    # Extract report name
    name_match = re.search(r'🟢 (.*)', content)
    if not name_match:
        raise ValueError("Report name is not in the expected format.")
    report_name = name_match.group(1).strip()

    # Extract sections
    sections = {}
    section_pattern = r'.. (.*?)\n(.*?)(?=\n.. |\Z)'
    for match in re.finditer(section_pattern, content, re.DOTALL):
        section_name = match.group(1).strip()
        section_content = match.group(2).strip()
        sections[section_name] = section_content

    #Extract full name and reason for each section
    for section, content in sections.items():
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if '/' in line:
                name, reason = line.split('/', 1)
                lines[i] = f"{name.strip()} / {reason.strip()}"
        sections[section] = '\n'.join(lines)

    return {
        'report_day': report_day,
        'report_type': report_type,
        'report_name': report_name,
        'sections': sections
    }

def main():
    env = load_env()
    print("Read Input")
    conn_params = make_connection_params(env)
    
    #Read all files in inputs directory
    input_dir = Path('secrets/inputs')
    report_files = list(input_dir.glob('*.txt'))

    for file_path in report_files:
        report_data = parse_individual_report(file_path)
        print(f"Processing {file_path.name}:")
        for report_data['sections'], content in report_data['sections'].items():
            print(f"  {report_data['report_name']} - {report_data['report_type']} - {report_data['report_day']} - {report_data['sections']}:")
            print(content)
        # for key, value in report_data.items():
        #     print(f"  {key}: {value}")
        print()

if __name__ == "__main__":
    main()