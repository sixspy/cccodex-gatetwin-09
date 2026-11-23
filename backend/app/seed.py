from datetime import datetime, timezone

from app.db import 连接

建表 = """
CREATE TABLE IF NOT EXISTS 站规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 线路 (
  线路键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点 (
  站点键 TEXT PRIMARY KEY,
  线路键 TEXT NOT NULL REFERENCES 线路(线路键),
  站名 TEXT NOT NULL,
  站序 INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS 线路超时 (
  线路键 TEXT PRIMARY KEY REFERENCES 线路(线路键),
  超时秒 INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS 刷卡点 (
  事件编号 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  方向 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已入流',
  行程键 TEXT NOT NULL DEFAULT '',
  批次编号 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 开腿账 (
  开腿键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  状态 TEXT NOT NULL DEFAULT '在途',
  更新处理时 TEXT NOT NULL,
  线路键 TEXT,
  超时秒 INTEGER,
  超时界 TEXT,
  超时权威 TEXT
);
CREATE TABLE IF NOT EXISTS 行程账 (
  行程键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  出站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  出站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  出站事件时 TEXT NOT NULL,
  历时秒 INTEGER NOT NULL DEFAULT 0,
  状态 TEXT NOT NULL DEFAULT '已成对',
  版本 INTEGER NOT NULL DEFAULT 1,
  处理时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 旁路匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  原因 TEXT NOT NULL,
  卡号 TEXT NOT NULL DEFAULT '',
  事件编号 TEXT NOT NULL DEFAULT '',
  载荷 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 行程贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  刷卡数 INTEGER NOT NULL,
  行程数 INTEGER NOT NULL,
  开腿数 INTEGER NOT NULL,
  旁路数 INTEGER NOT NULL,
  是否通过 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
"""

开腿钉界列 = {"线路键": "TEXT", "超时秒": "INTEGER", "超时界": "TEXT", "超时权威": "TEXT"}


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 迁移(conn) -> None:
    """老库补开腿钉界列；存量在途腿按当前权威补钉（新腿一律落地即钉）。"""
    已有 = {r["name"] for r in conn.execute("PRAGMA table_info(开腿账)")}
    for 名, 型 in 开腿钉界列.items():
        if 名 not in 已有:
            conn.execute(f"ALTER TABLE 开腿账 ADD COLUMN {名} {型}")
    from app.modules.配对超时策略 import 钉界

    for leg in conn.execute("SELECT * FROM 开腿账 WHERE 超时界 IS NULL").fetchall():
        try:
            钉 = 钉界(conn, leg["进站站点键"], leg["进站事件时"])
        except ValueError:
            continue  # 站点已不可解析的残腿留给贯验报撕裂
        conn.execute(
            "UPDATE 开腿账 SET 线路键=?, 超时秒=?, 超时界=?, 超时权威=? WHERE 开腿键=?",
            (钉["线路键"], 钉["超时秒"], 钉["超时界"], 钉["超时权威"], leg["开腿键"]),
        )


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    迁移(conn)
    if conn.execute("SELECT COUNT(*) AS c FROM 站规").fetchone()["c"] == 0:
        for k, v in {
            "站名": "闸对",
            "最大行程秒": "7200",
            "同站进出": "允许",
            "重复进站策略": "旧腿旁路并开新腿",
            "配对策略": "同卡先进后出",
            "骨架": "刷卡点装载→同卡进站出站成对物化→缺腿异向超时旁路→行程账与刷卡点互证",
        }.items():
            conn.execute("INSERT INTO 站规(键, 值) VALUES (?, ?)", (k, v))
    conn.execute(
        "INSERT OR IGNORE INTO 站规(键, 值) VALUES (?, ?)",
        ("超时权威", "乙·线路超时表优先，缺省回落站规；开腿落地钉死超时界，扫描只读钉界"),
    )
    for 线路键, 名称, 站表 in (
        ("线1", "一号线", [("站A", "城东站"), ("站B", "中心站"), ("站C", "河西站")]),
        ("线2", "二号线", [("站D", "渡口站"), ("站E", "云台站"), ("站F", "西岭站")]),
    ):
        if conn.execute("SELECT 1 FROM 线路 WHERE 线路键=?", (线路键,)).fetchone():
            continue
        conn.execute("INSERT INTO 线路(线路键, 名称) VALUES (?, ?)", (线路键, 名称))
        for i, (k, n) in enumerate(站表, start=1):
            conn.execute(
                "INSERT OR IGNORE INTO 站点(站点键, 线路键, 站名, 站序) VALUES (?,?,?,?)",
                (k, 线路键, n, i),
            )
    conn.commit()
    conn.close()
