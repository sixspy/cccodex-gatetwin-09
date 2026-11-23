"""配对超时策略：开腿超时界的权威钉死与缺腿超时扫描（全局唯一口径·乙）。

口径（乙·线路级超时表钉界为准）：
- 开腿落地时按「进站站所属线路」读线路超时表钉死本腿秒数；线路无行则回落站规「最大行程秒」。
- 钉死结果（线路键/超时秒/超时界/超时权威）随开腿行同一 INSERT 物化——装载写开腿与钉界同成败。
- 超时扫描只读开腿行已钉的超时界，禁止改用全局值（站规秒）覆盖已钉线路界；
  判定与旁路写闸同事务同票，在途→已旁路条件更新保证并发扫描/复扫不一腿双判。
- 改站规秒/线路秒只影响此后新钉的开腿；已在途腿的钉界不回改，
  故扫描中途改权威不会半旁路，改权威后复扫不会双判。

对照（甲·仅以站规全局秒钉界）：同刻进站的两腿共享同一全局界，命运必然相同；
乙口径下线1短界腿与线2长界腿可不同命运——夹具「超时权威样例」据此区分两口径。
"""

import json

from app.services import 时间

NAME = "配对超时策略"

来源线路 = "线路超时表"
来源站规 = "站规回落"
权威集 = (来源线路, 来源站规)

口径 = "乙·线路超时表优先，缺省回落站规；开腿落地钉死超时界，扫描只读钉界"


def 站规秒(conn) -> int:
    """站规「最大行程秒」：线路超时的缺省回落。非法即抛错，让装载整批回滚。"""
    r = conn.execute("SELECT 值 FROM 站规 WHERE 键='最大行程秒'").fetchone()
    原 = r["值"] if r else "7200"
    try:
        n = int(str(原).strip())
    except (TypeError, ValueError):
        raise ValueError(f"站规最大行程秒非法:{原}")
    if n <= 0:
        raise ValueError(f"站规最大行程秒须为正整数:{原}")
    return n


def 解析权威(conn, 站点键: str) -> dict:
    """按进站站所属线路解析超时权威：线路超时表优先，缺省回落站规。"""
    站 = conn.execute("SELECT 线路键 FROM 站点 WHERE 站点键=?", (站点键,)).fetchone()
    if not 站:
        raise ValueError(f"未知站点:{站点键}")
    线路键 = 站["线路键"]
    行 = conn.execute(
        "SELECT 超时秒 FROM 线路超时 WHERE 线路键=?", (线路键,)
    ).fetchone()
    if 行 is not None:
        return {"线路键": 线路键, "超时秒": int(行["超时秒"]), "超时权威": 来源线路}
    return {"线路键": 线路键, "超时秒": 站规秒(conn), "超时权威": 来源站规}


def 钉界(conn, 站点键: str, 进站事件时: str) -> dict:
    """开腿落地时物化本腿超时界：返回随开腿行同事务写入的钉死列。"""
    a = 解析权威(conn, 站点键)
    return {
        "线路键": a["线路键"],
        "超时秒": a["超时秒"],
        "超时界": 时间.加秒(进站事件时, a["超时秒"]),
        "超时权威": a["超时权威"],
    }


def 扫缺腿超时(conn, 水位事件时: str, 处理时: str) -> list:
    """缺腿超时扫描：只读开腿行已钉的超时界，判定与旁路写闸同票（调用方事务内）。

    不读站规/线路超时表——扫描中途改权威不影响在扫批次（不得半旁路）；
    在途→已旁路的条件更新保证并发扫描与复扫不会一腿双判；
    钉界缺失的腿不判、不回落全局值，留待贯验报撕裂。返回被旁路明细。
    """
    明细 = []
    rows = list(
        conn.execute("SELECT * FROM 开腿账 WHERE 状态='在途' AND 超时界 IS NOT NULL")
    )
    for leg in rows:
        if 时间.解析(水位事件时) < 时间.解析(leg["超时界"]):
            continue
        cur = conn.execute(
            "UPDATE 开腿账 SET 状态='已旁路', 更新处理时=? WHERE 开腿键=? AND 状态='在途'",
            (处理时, leg["开腿键"]),
        )
        if cur.rowcount != 1:
            continue  # 已被并发扫描判走：同一开腿不得双判
        conn.execute(
            "UPDATE 刷卡点 SET 命运='已旁路' WHERE 事件编号=?",
            (leg["进站事件编号"],),
        )
        载荷 = {
            "开腿键": leg["开腿键"],
            "进站事件时": leg["进站事件时"],
            "水位": 水位事件时,
            "线路键": leg["线路键"],
            "钉死秒": leg["超时秒"],
            "超时界": leg["超时界"],
            "权威来源": leg["超时权威"],
        }
        conn.execute(
            "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
            ("缺腿超时", leg["卡号"], leg["进站事件编号"],
             json.dumps(载荷, ensure_ascii=False), 处理时),
        )
        明细.append({"开腿键": leg["开腿键"], "卡号": leg["卡号"], **载荷})
    return 明细


def 校验钉界(conn, leg) -> list:
    """结构校验开腿行已钉超时界（不回算当前权威配置）。返回问题表，空表即 valid。"""
    问题 = []
    秒 = leg["超时秒"]
    if 秒 is None or int(秒) <= 0:
        问题.append("钉死秒缺失或非正")
    if not leg["超时界"]:
        问题.append("超时界缺失")
    elif 秒 is not None and int(秒) > 0 and leg["超时界"] != 时间.加秒(leg["进站事件时"], int(秒)):
        问题.append("超时界≠进站事件时+钉死秒")
    if leg["超时权威"] not in 权威集:
        问题.append("权威来源非法")
    站 = conn.execute(
        "SELECT 线路键 FROM 站点 WHERE 站点键=?", (leg["进站站点键"],)
    ).fetchone()
    if not 站:
        问题.append("进站站点不存在")
    elif leg["线路键"] != 站["线路键"]:
        问题.append("钉死线路与进站站所属线路不符")
    return 问题


def 权威视图(conn) -> dict:
    """超时权威只读接口：开腿键、线路、钉死秒、权威来源、timeout_at、valid。"""
    腿 = []
    for leg in conn.execute(
        "SELECT * FROM 开腿账 ORDER BY 状态='在途' DESC, 进站事件时 DESC"
    ):
        问题 = 校验钉界(conn, leg)
        腿.append({
            "开腿键": leg["开腿键"],
            "卡号": leg["卡号"],
            "状态": leg["状态"],
            "线路": leg["线路键"],
            "钉死秒": leg["超时秒"],
            "权威来源": leg["超时权威"],
            "进站事件时": leg["进站事件时"],
            "timeout_at": leg["超时界"],
            "valid": not 问题,
            "问题": 问题,
        })
    try:
        秒 = 站规秒(conn)
        秒错 = ""
    except ValueError as e:
        秒, 秒错 = None, str(e)
    return {
        "口径": 口径,
        "站规秒": 秒,
        "站规秒错误": 秒错,
        "线路超时": [
            dict(r)
            for r in conn.execute("SELECT 线路键, 超时秒 FROM 线路超时 ORDER BY 线路键")
        ],
        "腿": 腿,
    }


def 写站规(conn, 键: str, 值) -> dict:
    """站规写闸：最大行程秒须为正整数（权威回落源，非法即拒）。"""
    值 = str(值)
    if 键 == "最大行程秒":
        try:
            n = int(值.strip())
        except (TypeError, ValueError):
            raise ValueError(f"最大行程秒非法:{值}")
        if n <= 0:
            raise ValueError(f"最大行程秒须为正整数:{值}")
        值 = str(n)
    conn.execute(
        "INSERT INTO 站规(键, 值) VALUES (?, ?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (键, 值),
    )
    return {"键": 键, "值": 值}


def 写线路超时(conn, 线路键: str, 超时秒) -> dict:
    """线路超时表写闸：正整数 upsert；空/非正 → 删行回落站规。只影响此后新钉的开腿。"""
    if not conn.execute("SELECT 1 FROM 线路 WHERE 线路键=?", (线路键,)).fetchone():
        raise ValueError(f"未知线路:{线路键}")
    try:
        n = int(超时秒) if 超时秒 is not None and str(超时秒).strip() != "" else 0
    except (TypeError, ValueError):
        raise ValueError(f"超时秒非法:{超时秒}")
    if n <= 0:
        conn.execute("DELETE FROM 线路超时 WHERE 线路键=?", (线路键,))
        return {"线路键": 线路键, "超时秒": None, "权威来源": 来源站规}
    conn.execute(
        "INSERT INTO 线路超时(线路键, 超时秒) VALUES (?, ?) "
        "ON CONFLICT(线路键) DO UPDATE SET 超时秒=excluded.超时秒",
        (线路键, n),
    )
    return {"线路键": 线路键, "超时秒": n, "权威来源": 来源线路}
