import os
import re
from pathlib import Path
import pymysql


def connect():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3307")),
        user=os.getenv("MYSQL_USER", "wolt"),
        password=os.getenv("MYSQL_PASSWORD", "local-demo-only"),
        database=os.getenv("MYSQL_DATABASE", "wolt_analytics"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        init_command="SET time_zone = '+00:00'",
    )


def execute_file(connection, path: Path):
    # Project SQL deliberately contains no stored routines or semicolons in literals.
    sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
    with connection.cursor() as cursor:
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)


def rows(connection, query, parameters=None):
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        return cursor.fetchall()
