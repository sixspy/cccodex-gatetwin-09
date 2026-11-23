import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接, 写事务
from app.seed import 此刻
from app.services import 装载, 贯验, 目录
from app.modules import 配对超时策略

路由 = APIRouter(prefix="/api")


class 装载请求(BaseModel):
    批次编号: str = ""
    事件: list = Field(default_factory=list)
    站规: dict = Field(default_factory=dict)
    线路超时: dict = Field(default_factory=dict)


class 站规写(BaseModel):
    键: str
    值: str


class 线路超时写(BaseModel):
    线路键: str
    超时秒: int | None = None


class 扫描请求(BaseModel):
    水位事件时: str = ""


@路由.get("/健康")
def 健康():
    return {
        "正常": True,
        "项目": "闸对",
        "骨架": "刷卡点装载→同卡进站出站成对物化→缺腿异向超时旁路→行程账与刷卡点互证",
    }


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/站规")
def 站规():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
    finally:
        conn.close()


@路由.get("/线路")
def 列线路():
    conn = 连接()
    try:
        lines = [dict(r) for r in conn.execute("SELECT * FROM 线路 ORDER BY 线路键")]
        for ln in lines:
            ln["站点"] = [
                dict(s)
                for s in conn.execute(
                    "SELECT * FROM 站点 WHERE 线路键=? ORDER BY 站序", (ln["线路键"],)
                )
            ]
        return lines
    finally:
        conn.close()


@路由.get("/刷卡点")
def 列刷卡(命运: str = ""):
    conn = 连接()
    try:
        if 命运:
            rows = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 命运=? ORDER BY 事件时 DESC LIMIT 200",
                (命运,),
            )
        else:
            rows = conn.execute("SELECT * FROM 刷卡点 ORDER BY 事件时 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/开腿账")
def 列开腿(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 开腿账 WHERE 状态=? ORDER BY 进站事件时 DESC", (状态,)
            )
        else:
            rows = conn.execute("SELECT * FROM 开腿账 ORDER BY 进站事件时 DESC")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/行程账")
def 列行程():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 行程账 ORDER BY 处理时 DESC LIMIT 200")]
    finally:
        conn.close()


@路由.get("/旁路匣")
def 列旁路():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 旁路匣 ORDER BY 编号 DESC LIMIT 100")]
    finally:
        conn.close()


@路由.get("/批次")
def 列批次():
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 装载批次 ORDER BY 时刻 DESC LIMIT 30"):
            d = dict(r)
            try:
                d["报告"] = json.loads(d["报告"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.post("/装载")
def 做装载(体: 装载请求):
    try:
        return 装载.装一批(体.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@路由.post("/装载/夹具")
def 装夹具(名: str = "成对样例"):
    路径 = 夹具目录 / f"{名}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{名}")
    try:
        return 装载.装一批(json.loads(路径.read_text(encoding="utf-8")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@路由.get("/超时权威")
def 超时权威视图():
    """超时权威只读接口：开腿键、线路、钉死秒、权威来源、timeout_at、valid。"""
    conn = 连接()
    try:
        return 配对超时策略.权威视图(conn)
    finally:
        conn.close()


@路由.post("/站规")
def 写站规(体: 站规写):
    """站规写闸：改最大行程秒只影响此后新钉的开腿，已在途腿钉界不回改。"""
    try:
        with 写事务() as conn:
            return 配对超时策略.写站规(conn, 体.键, 体.值)
    except ValueError as e:
        raise HTTPException(400, str(e))


@路由.get("/线路超时")
def 列线路超时():
    """各线超时权威：钉线秒或回落站规。回落源非法时照常列出（生效秒置空），留待贯验报撕裂。"""
    conn = 连接()
    try:
        try:
            回落 = 配对超时策略.站规秒(conn)
        except ValueError:
            回落 = None
        行 = []
        for ln in conn.execute("SELECT 线路键, 名称 FROM 线路 ORDER BY 线路键"):
            t = conn.execute(
                "SELECT 超时秒 FROM 线路超时 WHERE 线路键=?", (ln["线路键"],)
            ).fetchone()
            行.append({
                "线路键": ln["线路键"],
                "名称": ln["名称"],
                "超时秒": t["超时秒"] if t else None,
                "权威来源": 配对超时策略.来源线路 if t else 配对超时策略.来源站规,
                "生效秒": (t["超时秒"] if t else 回落),
            })
        return 行
    finally:
        conn.close()


@路由.post("/线路超时")
def 写线路超时(体: 线路超时写):
    """线路超时写闸：正整数钉线秒；空/非正删行回落站规。只影响此后新钉的开腿。"""
    try:
        with 写事务() as conn:
            return 配对超时策略.写线路超时(conn, 体.线路键, 体.超时秒)
    except ValueError as e:
        raise HTTPException(400, str(e))


@路由.post("/超时扫描")
def 做超时扫描(体: 扫描请求):
    """超时扫描旁路写闸：只读已钉超时界，判定与旁路写闸同一事务同票。"""
    with 写事务() as conn:
        水位 = 体.水位事件时
        if not 水位:
            r = conn.execute("SELECT MAX(事件时) AS m FROM 刷卡点").fetchone()
            水位 = r["m"] or 此刻()
        明细 = 配对超时策略.扫缺腿超时(conn, 水位, 此刻())
        return {"水位事件时": 水位, "超时旁路": len(明细), "明细": 明细}


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 行程贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()


@路由.get("/空桩")
def 列空桩():
    from pathlib import Path
    import importlib

    root = Path(__file__).resolve().parent.parent / "modules"
    names = sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    )
    out = []
    for n in names:
        try:
            m = importlib.import_module(f"app.modules.{n}")
            out.append({"名": n, "导出": getattr(m, "NAME", n)})
        except Exception as e:
            out.append({"名": n, "错误": str(e)})
    return out
