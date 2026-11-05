"""DuckDB-backed DB-API adapter shared by the QC server's Python producers.

Every native file handle is protected by the same advisory lock as Rust.
Buffered reads release the file immediately; transactions release it on commit,
rollback or close. SQLite is used only by the explicit legacy import utility.
"""
from collections import deque
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlparse, parse_qs

import duckdb

Error = DatabaseError = OperationalError = duckdb.Error
IntegrityError = duckdb.ConstraintException

DATETIME_SQL = """CREATE MACRO IF NOT EXISTS datetime(value, modifier := NULL) AS
strftime(CAST(current_timestamp AS TIMESTAMP) + COALESCE(TRY_CAST(modifier AS INTERVAL),
INTERVAL '0 second'), '%Y-%m-%d %H:%M:%S')"""


class Row:
    def __init__(self, columns, values):
        self.columns, self.values = columns, values
    def keys(self):
        return list(self.columns)
    def __getitem__(self, key):
        if isinstance(key, str):
            key = [c.lower() for c in self.columns].index(key.lower())
        return self.values[key]
    def __iter__(self):
        return iter(self.values)
    def __len__(self):
        return len(self.values)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = deque()
        self.description = None
        self.rowcount = -1
    def execute(self, sql, parameters=()):
        self.connection._execute(self, sql, parameters)
        return self
    def executemany(self, sql, parameters):
        count = 0
        for values in parameters:
            self.execute(sql, values)
            count += max(0, self.rowcount)
        self.rowcount = count
        return self
    def fetchone(self):
        return self.rows.popleft() if self.rows else None
    def fetchall(self):
        rows = list(self.rows)
        self.rows.clear()
        return rows
    def fetchmany(self, size=1):
        return [self.rows.popleft() for _ in range(min(size,len(self.rows)))]
    def __iter__(self):
        while self.rows:
            yield self.rows.popleft()
    def close(self):
        self.rows.clear()


class Connection:
    def __init__(self, database, *, uri=False, timeout=30, **kwargs):
        value = str(database)
        self.read_only = False
        if uri:
            parsed = urlparse(value)
            value = unquote(parsed.path)
            mode = parse_qs(parsed.query).get('mode',['rwc'])[0]
            self.read_only = mode=='ro'
        else:
            mode = 'rwc'
        self.memory = value==':memory:'
        self.path = Path(value).resolve() if not self.memory else None
        if not self.memory and mode in ['ro','rw'] and not self.path.is_file():
            raise OperationalError(f'Database does not exist: {self.path}')
        self.row_factory = None
        self._native = self._access = None
        self._transaction = self._context = False
        self._closed = False

    def _open(self):
        if self._closed:
            raise OperationalError('Connection is closed')
        if self._native is not None:
            return
        if not self.memory:
            self._access = open(str(self.path)+'.access.lock','a+b')
            os.chmod(self._access.name,0o600)
            fcntl.flock(self._access,fcntl.LOCK_EX)
        try:
            self._native = duckdb.connect(':memory:' if self.memory else str(self.path), read_only=self.read_only)
            self._native.execute("SET TimeZone='UTC'")
            if not self.read_only:
                self._native.execute(DATETIME_SQL)
                self._native.execute("CREATE TABLE IF NOT EXISTS _qc_storage_meta(key VARCHAR PRIMARY KEY,value VARCHAR)")
            if self.path:
                os.chmod(self.path,0o600)
        except BaseException:
            self._release()
            raise

    def _release(self, force=False):
        if self.memory and not force:
            return
        if self._native is not None:
            self._native.close()
            self._native = None
        if self._access is not None:
            self._access.close()
            self._access = None

    def _translate(self, sql):
        sql = re.sub(r'\bREAL\b','DOUBLE',sql,flags=re.I)
        if re.match(r'^\s*PRAGMA\s+(busy_timeout|journal_mode|synchronous|wal_autocheckpoint)',sql,re.I):
            return 'SELECT 0 WHERE false'
        if re.match(r'^\s*PRAGMA\s+user_version\s*$',sql,re.I):
            return "SELECT CAST(COALESCE((SELECT value FROM _qc_storage_meta WHERE key='user_version'),'0') AS BIGINT)"
        match=re.match(r'^\s*PRAGMA\s+user_version\s*=\s*(\d+)',sql,re.I)
        if match:
            return "INSERT OR REPLACE INTO _qc_storage_meta VALUES ('user_version','"+match[1]+"')"
        # Preserve SQLite INTEGER PRIMARY KEY allocation for strategy-owned DDL.
        pattern=re.compile(r'(CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\()(.*?)(\);|$)',re.I|re.S)
        def table(match):
            head,name,body,tail=match.groups()
            if re.search(r'\bINTEGER\s+PRIMARY\s+KEY\b',body,re.I):
                sequence=name+'_id_seq'
                self._native.execute(f'CREATE SEQUENCE IF NOT EXISTS "{sequence}" START 1')
                body=re.sub(r'\bINTEGER\s+PRIMARY\s+KEY(?:\s+AUTOINCREMENT)?',
                    f"BIGINT PRIMARY KEY DEFAULT nextval('{sequence}')",body,flags=re.I)
            return head+body+tail
        return re.sub(r'\bINTEGER\b','BIGINT',pattern.sub(table,sql),flags=re.I)

    def _align_sequence(self, sql):
        match=re.match(r'\s*INSERT(?: OR \w+)? INTO\s+(\w+)',sql,re.I)
        if not match:
            return
        table=match[1]
        sequence=table+'_id_seq'
        row=self._native.execute('SELECT start_value,last_value FROM duckdb_sequences() WHERE sequence_name=?',[sequence]).fetchone()
        if row:
            maximum=self._native.execute(f'SELECT max(id) FROM "{table}"').fetchone()[0]
            next_id=row[0] if row[1] is None else row[1]+1
            if maximum is not None and next_id<=maximum:
                self._native.execute(f"SELECT nextval('{sequence}') FROM range(?)",[maximum-next_id+1]).fetchall()

    def _execute(self, cursor, sql, parameters):
        self._open()
        try:
            write = not re.match(r'^\s*(SELECT|WITH|EXPLAIN|SHOW|DESCRIBE|PRAGMA\s+table_info)\b',sql,re.I)
            if (write or self._context) and not self._transaction and not self.read_only:
                self._native.execute('BEGIN TRANSACTION')
                self._transaction=True
            translated=self._translate(sql)
            self._align_sequence(translated)
            # A duplicate insert is a statement failure in existing producers.
            # Prevent DuckDB from aborting their entire outer transaction.
            duplicate_guard=bool(re.match(r'^\s*INSERT INTO\b',translated,re.I)
                and re.search(r'\bVALUES\b',translated,re.I)
                and not re.search(r'\b(ON CONFLICT|RETURNING|SELECT)\b',translated,re.I)
                and not re.search(r'\)\s*,\s*\(',translated))
            if duplicate_guard:
                table=re.match(r'^\s*INSERT INTO\s+(\w+)',translated,re.I)[1]
                duplicate_guard=bool(self._native.execute("SELECT count(*) FROM duckdb_constraints() WHERE table_name=? AND constraint_type IN ('UNIQUE','PRIMARY KEY')",[table]).fetchone()[0])
            if duplicate_guard:
                translated=translated.rstrip().rstrip(';')+' ON CONFLICT DO NOTHING RETURNING *'
            result=self._native.execute(translated,parameters)
            cursor.description=result.description
            values=result.fetchall()
            if duplicate_guard:
                if not values:
                    raise IntegrityError('Duplicate key in insert')
                cursor.description=None
                cursor.rowcount=len(values)
                cursor.rows=deque()
                return
            columns=[d[0] for d in cursor.description] if cursor.description else []
            cursor.rowcount = int(values[0][0]) if write and columns==['Count'] and values else (len(values) if write else -1)
            cursor.rows=deque(Row(columns,row) if self.row_factory is Row else row for row in values)
        except BaseException:
            if not self._transaction:
                self._release()
            raise
        if not self._transaction and not self._context:
            self._release()

    def cursor(self):
        return Cursor(self)
    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql,parameters)
    def executemany(self, sql, parameters):
        return self.cursor().executemany(sql,parameters)
    def executescript(self, sql):
        return self.execute(sql)
    def commit(self):
        if self._transaction:
            self._native.execute('COMMIT')
            self._transaction=False
        self._release()
    def rollback(self):
        if self._transaction:
            self._native.execute('ROLLBACK')
            self._transaction=False
        self._release()
    def close(self):
        self.rollback()
        self._release(force=True)
        self._closed=True
    def __enter__(self):
        self._context=True
        return self
    def __exit__(self, kind, value, trace):
        try:
            self.rollback() if kind else self.commit()
        finally:
            self._context=False


def connect(database, **kwargs):
    return Connection(database,**kwargs)


def snapshot(source, destination):
    """Checkpoint and copy a consistent native database under the access lock."""
    with connect(source) as c:
        c._open()
        c._native.execute('CHECKPOINT')
        shutil.copy2(source,destination)
        os.chmod(destination,0o600)
