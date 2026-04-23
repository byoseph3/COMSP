# COMSP
Company Organization Management System Project


















(Following Documentation was an experimental Product of using Copilot to write Documentation on one script. Will Clean this up later.)
# Postgres User Import Tool

This repository contains a simple Python script to import user data from an Excel file or a delimited text file into a PostgreSQL database.

## Files

- `docker-compose.yml` - starts a PostgreSQL container with a persistent Docker volume.
- `import_users.py` - imports tabular user data into a Postgres table and overwrites the target table.
- `requirements.txt` - Python dependencies for the import script.
- `.env` / `secrets/.env` - database credentials and connection settings.
- `.gitignore` - ignores sensitive files and local environment files.

## Script overview: `import_users.py`

The script does the following:

1. Loads database connection settings from a `.env` file.
   - Supported keys: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, or a single `DATABASE_URL`
   - Searches for `.env` in the workspace root or `secrets/.env`
2. Reads the source file:
   - Excel files (`.xlsx`) using `openpyxl`
   - Text files (`.csv`, `.txt`) using Python's CSV reader
3. Parses the first row as column headers.
4. Normalizes header names into valid PostgreSQL column names.
5. Drops and recreates the target table (`users` by default).
6. Inserts all rows from the source file into the rebuilt table.

## Supported input formats

- Excel: `.xlsx`
- Text/CSV: `.csv`, `.txt`

The script attempts automatic delimiter detection for text files. You can also pass `--delimiter` if needed.

## Setup

1. Create a virtual environment in the repository root:

```powershell
py -m venv .venv
```

2. Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install required packages:

```powershell
pip install -r requirements.txt
```

## Usage

```powershell
python import_users.py path/to/users.xlsx
```

For a CSV file:

```powershell
python import_users.py path/to/users.csv
```

Optional arguments:

- `-t, --table` : target table name (default: `users`)
- `-s, --schema` : target schema (default: `public`)
- `-e, --env-file` : custom `.env` path
- `--sheet` : Excel sheet name (default: active sheet)
- `--delimiter` : delimiter for text files

Example:

```powershell
python import_users.py users.xlsx -t users -s public --sheet Sheet1
```

## Behavior

- The script drops the existing target table if it exists.
- It recreates the table using the source file headers as column names.
- It inserts all rows from the input file into the new table.

## Notes

- Keep `.env` or `secrets/.env` out of source control.
- The script normalizes column names by converting them to lowercase and replacing invalid characters with underscores.
- Empty cells are inserted as SQL `NULL` values.

## Example `.env`

```dotenv
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=...
DB_NAME=...
```
