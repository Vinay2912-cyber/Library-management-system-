import sqlite3
import os

BASE_DIR = os.path.dirname(__file__)
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'library.db')

if not os.path.exists(INSTANCE_DIR):
    os.makedirs(INSTANCE_DIR)

with sqlite3.connect(DB_PATH) as conn:
    with open('schema.sql', 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

print('Initialized database at', DB_PATH)
