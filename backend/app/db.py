import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "闸对.db"

# 单进程多线程下 SQLite 写者串行：改权威（站规/线路超时）与装载扫描的写事务
# 经此锁排队，从根上杜绝写锁 convoy 与共享锁升级死锁造成的半旁路。
_写锁 = threading.Lock()


def 连接() -> sqlite3.Connection:
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    # WAL：读写不互堵；busy_timeout：跨进程写者兜底串行
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA busy_timeout = 5000")
    return c


@contextmanager
def 写事务():
    """写闸：装载/改权威/超时扫描/贯验落库共用。同成败——正常退出提交，异常回滚。"""
    with _写锁:
        conn = 连接()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
