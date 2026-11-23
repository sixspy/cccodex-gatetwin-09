"""配对超时策略（乙口径）主链测试。

夹具「超时权威样例」：线1 钉 1800（线路超时表），线2 无行回落站规 7200；
卡21/卡22 同刻 08:00 进站，卡23 09:00 进站推水位到 09:00——只过线1短界。
乙：仅卡21（短线腿）旁路；甲（仅全局秒）：同刻两腿同命运——两口径可区分。
"""
import json
import threading

import httpx

from app.db import 连接

夹具 = {
    "批次编号": "批-超时权威",
    "站规": {"最大行程秒": "7200"},
    "线路超时": {"线1": 1800},
    "事件": [
        {"事件编号": "ta1", "卡号": "卡21", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-23T08:00:00Z", "处理时": "2026-11-23T08:00:01Z"},
        {"事件编号": "tb1", "卡号": "卡22", "站点键": "站D", "方向": "进站",
         "事件时": "2026-11-23T08:00:00Z", "处理时": "2026-11-23T08:00:01Z"},
        {"事件编号": "tc1", "卡号": "卡23", "站点键": "站B", "方向": "进站",
         "事件时": "2026-11-23T09:00:00Z", "处理时": "2026-11-23T09:00:01Z"},
    ],
}


def 灌夹具(客):
    r = 客.post("/api/装载", json=夹具)
    assert r.status_code == 200, r.text
    return r.json()


def 腿(客, 开腿键):
    行 = [r for r in 客.get("/api/开腿账").json() if r["开腿键"] == 开腿键]
    assert len(行) == 1, f"开腿{开腿键}不存在"
    return 行[0]


def 缺腿超时旁路(客, 事件编号):
    return [r for r in 客.get("/api/旁路匣").json()
            if r["原因"] == "缺腿超时" and r["事件编号"] == 事件编号]


def test_乙口径_仅短线腿旁路(客):
    报告 = 灌夹具(客)
    assert 报告["开腿"] == 3
    assert 报告["超时旁路"] == 1

    # 开腿落地即钉界：线1 走线路超时表 1800，线2 回落站规 7200
    a = 腿(客, "腿-ta1")
    assert a["状态"] == "已旁路"
    assert (a["线路键"], a["超时秒"], a["超时权威"]) == ("线1", 1800, "线路超时表")
    assert a["超时界"] == "2026-11-23T08:30:00Z"
    b = 腿(客, "腿-tb1")
    assert b["状态"] == "在途"
    assert (b["线路键"], b["超时秒"], b["超时权威"]) == ("线2", 7200, "站规回落")
    assert b["超时界"] == "2026-11-23T10:00:00Z"
    c = 腿(客, "腿-tc1")
    assert c["状态"] == "在途" and c["超时界"] == "2026-11-23T09:30:00Z"

    # 旁路载荷记录钉界，与开腿账一致
    匣 = 缺腿超时旁路(客, "ta1")
    assert len(匣) == 1
    载 = json.loads(匣[0]["载荷"])
    assert 载["钉死秒"] == 1800 and 载["超时界"] == "2026-11-23T08:30:00Z"
    assert 载["权威来源"] == "线路超时表"

    # 甲对照：ta1/tb1 同刻进站、同水位——任何单一全局秒下两腿同命运，
    # 乙口径两腿命运不同，即可区分两口径
    差秒 = 3600  # 08:00 → 09:00 水位
    for 全局秒 in (1800, 3600, 7200):
        甲命运 = {"ta1": 差秒 >= 全局秒, "tb1": 差秒 >= 全局秒}  # 甲：同一全局界
        assert 甲命运["ta1"] == 甲命运["tb1"]  # 两腿同命运，复现不出乙的结果
    assert (a["状态"] == "已旁路") != (b["状态"] == "已旁路")  # 乙：仅短线旁路

    assert 客.post("/api/贯验").json()["是否通过"]


def test_超时权威只读接口字段(客):
    灌夹具(客)
    视图 = 客.get("/api/超时权威").json()
    assert 视图["站规秒"] == 7200
    assert 视图["线路超时"] == [{"线路键": "线1", "超时秒": 1800}]
    腿表 = {r["开腿键"]: r for r in 视图["腿"]}
    for 键, 行 in 腿表.items():
        for 字段 in ("开腿键", "线路", "钉死秒", "权威来源", "timeout_at", "valid"):
            assert 字段 in 行, f"{键}缺字段{字段}"
        assert 行["valid"] is True and 行["问题"] == []
    assert 腿表["腿-ta1"]["钉死秒"] == 1800
    assert 腿表["腿-tb1"]["权威来源"] == "站规回落"


def test_改权威后复扫不一腿双判(客):
    灌夹具(客)
    # 改权威：站规秒改小、线1 改更短——只影响此后新钉的开腿
    assert 客.post("/api/站规", json={"键": "最大行程秒", "值": "60"}).status_code == 200
    assert 客.post("/api/线路超时", json={"线路键": "线1", "超时秒": 30}).status_code == 200
    # 复扫：已钉界不回改，在途腿不得被新权威半旁路
    r = 客.post("/api/超时扫描", json={"水位事件时": "2026-11-23T09:00:00Z"})
    assert r.status_code == 200 and r.json()["超时旁路"] == 0
    assert 腿(客, "腿-tb1")["状态"] == "在途"
    assert 腿(客, "腿-tc1")["状态"] == "在途"
    # 已旁路的 ta1 不得双判：旁路匣仍只有一条
    assert len(缺腿超时旁路(客, "ta1")) == 1
    # 装载新批再扫（水位微进）同样不得双判；新腿按新权威钉界
    r = 客.post("/api/装载", json={"事件": [
        {"事件编号": "td1", "卡号": "卡24", "站点键": "站C", "方向": "进站",
         "事件时": "2026-11-23T09:00:30Z", "处理时": "2026-11-23T09:00:31Z"}]})
    assert r.status_code == 200
    assert len(缺腿超时旁路(客, "ta1")) == 1
    assert 腿(客, "腿-td1")["超时秒"] == 30
    assert 客.post("/api/贯验").json()["是否通过"]


def test_扫描只认已钉界_到界才旁路(客):
    灌夹具(客)
    # 界前不旁路、到界即旁路：扫描只读钉死界，与当下全局值无关
    r = 客.post("/api/超时扫描", json={"水位事件时": "2026-11-23T09:29:59Z"})
    assert r.json()["超时旁路"] == 0
    r = 客.post("/api/超时扫描", json={"水位事件时": "2026-11-23T09:30:00Z"})
    assert r.json()["超时旁路"] == 1  # tc1 界 09:30 到期
    assert 腿(客, "腿-tc1")["状态"] == "已旁路"
    assert 腿(客, "腿-tb1")["状态"] == "在途"
    r = 客.post("/api/超时扫描", json={"水位事件时": "2026-11-23T09:59:59Z"})
    assert r.json()["超时旁路"] == 0
    r = 客.post("/api/超时扫描", json={"水位事件时": "2026-11-23T10:00:00Z"})
    assert r.json()["超时旁路"] == 1  # tb1 界 10:00 到期
    assert 腿(客, "腿-tb1")["状态"] == "已旁路"
    assert 客.post("/api/贯验").json()["是否通过"]


def test_线路超时写闸_钉线删行回落(客):
    # 缺省回落站规
    r = 客.post("/api/装载", json={"事件": [
        {"事件编号": "w1", "卡号": "卡31", "站点键": "站D", "方向": "进站",
         "事件时": "2026-11-23T08:00:00Z"}]})
    assert 腿(客, "腿-w1")["超时权威"] == "站规回落"
    assert 腿(客, "腿-w1")["超时秒"] == 7200
    # 钉线秒
    assert 客.post("/api/线路超时", json={"线路键": "线2", "超时秒": 500}).status_code == 200
    r = 客.post("/api/装载", json={"事件": [
        {"事件编号": "w2", "卡号": "卡32", "站点键": "站D", "方向": "进站",
         "事件时": "2026-11-23T08:01:00Z"}]})
    assert (腿(客, "腿-w2")["超时秒"], 腿(客, "腿-w2")["超时权威"]) == (500, "线路超时表")
    # 旧腿钉界不回改
    assert 腿(客, "腿-w1")["超时秒"] == 7200
    # 删行回落
    assert 客.post("/api/线路超时", json={"线路键": "线2", "超时秒": None}).status_code == 200
    r = 客.post("/api/装载", json={"事件": [
        {"事件编号": "w3", "卡号": "卡33", "站点键": "站D", "方向": "进站",
         "事件时": "2026-11-23T08:02:00Z"}]})
    assert (腿(客, "腿-w3")["超时秒"], 腿(客, "腿-w3")["超时权威"]) == (7200, "站规回落")
    # 非法写闸被拒
    assert 客.post("/api/线路超时", json={"线路键": "线9", "超时秒": 100}).status_code == 400
    assert 客.post("/api/站规", json={"键": "最大行程秒", "值": "abc"}).status_code == 400
    assert 客.post("/api/站规", json={"键": "最大行程秒", "值": "0"}).status_code == 400
    行 = {r["线路键"]: r for r in 客.get("/api/线路超时").json()}
    assert 行["线1"]["权威来源"] == "站规回落" and 行["线1"]["生效秒"] == 7200


def test_装载写开腿与钉界同成败(客):
    # 批内权威配置非法 → 整批回滚：不开腿、不入流、不落配置
    r = 客.post("/api/装载", json={
        "线路超时": {"线9": 100},
        "事件": [{"事件编号": "x1", "卡号": "卡41", "站点键": "站A", "方向": "进站",
                  "事件时": "2026-11-23T08:00:00Z"}]})
    assert r.status_code == 400
    assert 客.get("/api/开腿账").json() == []
    assert 客.get("/api/刷卡点").json() == []
    assert 客.get("/api/超时权威").json()["线路超时"] == []
    # 回落源（站规秒）被直接改烂 → 回落线开腿失败，整批回滚
    conn = 连接()
    conn.execute("UPDATE 站规 SET 值='烂' WHERE 键='最大行程秒'")
    conn.commit()
    conn.close()
    r = 客.post("/api/装载", json={"事件": [
        {"事件编号": "x2", "卡号": "卡42", "站点键": "站D", "方向": "进站",
         "事件时": "2026-11-23T08:00:00Z"}]})
    assert r.status_code == 400
    assert 客.get("/api/开腿账").json() == []
    assert 客.get("/api/刷卡点").json() == []
    assert not 客.post("/api/贯验").json()["是否通过"]  # 贯验抓站规秒非法
    客.post("/api/站规", json={"键": "最大行程秒", "值": "7200"})
    assert 客.post("/api/贯验").json()["是否通过"]


def test_贯验抓钉界撕裂与双判(客):
    灌夹具(客)
    # 撕裂：在途腿钉界被改烂 → 贯验报钉界无效
    conn = 连接()
    conn.execute("UPDATE 开腿账 SET 超时界='1999-01-01T00:00:00Z' WHERE 开腿键='腿-tb1'")
    conn.commit()
    conn.close()
    r = 客.post("/api/贯验").json()
    assert not r["是否通过"] and "钉界无效" in r["说明"]
    视图 = 客.get("/api/超时权威").json()
    坏 = [x for x in 视图["腿"] if x["开腿键"] == "腿-tb1"][0]
    assert 坏["valid"] is False
    # 修复后双判：同一进站事件两条缺腿超时旁路 → 贯验报双判
    conn = 连接()
    conn.execute(
        "UPDATE 开腿账 SET 超时界='2026-11-23T10:00:00Z' WHERE 开腿键='腿-tb1'")
    conn.execute(
        "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES ('缺腿超时','卡21','ta1','{}','2026-11-23T09:00:02Z')")
    conn.commit()
    conn.close()
    r = 客.post("/api/贯验").json()
    assert not r["是否通过"] and "双判" in r["说明"]


def test_并发改秒与扫描不得半旁路(客):
    import uvicorn

    客.post("/api/线路超时", json={"线路键": "线1", "超时秒": 1800})
    配置 = uvicorn.Config("app.main:app", host="127.0.0.1", port=11599, log_level="error")
    服务 = uvicorn.Server(配置)
    线 = threading.Thread(target=服务.run, daemon=True)
    线.start()
    try:
        import time
        for _ in range(200):
            try:
                if httpx.get("http://127.0.0.1:11599/api/健康", timeout=1).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.05)
        故障 = []

        def 改权威():
            with httpx.Client(base_url="http://127.0.0.1:11599", timeout=10) as h:
                for i in range(40):
                    for r in (h.post("/api/站规", json={"键": "最大行程秒", "值": str(300 + i * 137)}),
                              h.post("/api/线路超时", json={"线路键": "线1", "超时秒": 600 + i * 61})):
                        if r.status_code != 200:
                            故障.append(f"改权威{r.status_code}:{r.text}")

        def 装载扫描(tid):
            with httpx.Client(base_url="http://127.0.0.1:11599", timeout=10) as h:
                for i in range(40):
                    站 = "站A" if i % 2 == 0 else "站D"
                    时 = f"2026-11-23T{8 + i // 60:02d}:{i % 60:02d}:00Z"
                    r = h.post("/api/装载", json={"事件": [
                        {"事件编号": f"p{tid}-{i}", "卡号": f"卡5{tid}{i:02d}", "站点键": 站,
                         "方向": "进站", "事件时": 时}]})
                    if r.status_code != 200:
                        故障.append(f"装载{r.status_code}:{r.text}")

        线程 = [threading.Thread(target=改权威) for _ in range(2)] + \
               [threading.Thread(target=装载扫描, args=(t,)) for t in range(2)]
        for t in 线程:
            t.start()
        for t in 线程:
            t.join()
        assert not 故障, 故障[:5]
    finally:
        服务.should_exit = True
        线.join(timeout=10)

    # 不得半旁路：贯验全绿——钉界有效、无一腿双判、旁路载荷与钉界一致
    r = 客.post("/api/贯验").json()
    assert r["是否通过"], r["说明"]
    视图 = 客.get("/api/超时权威").json()
    assert all(x["valid"] for x in 视图["腿"])
    腿表 = {x["开腿键"]: x for x in 客.get("/api/开腿账").json()}
    for 匣 in 客.get("/api/旁路匣").json():
        if 匣["原因"] != "缺腿超时":
            continue
        载 = json.loads(匣["载荷"])
        被钉 = 腿表[载["开腿键"]]
        assert 载["钉死秒"] == 被钉["超时秒"] and 载["超时界"] == 被钉["超时界"]
        assert 载["水位"] >= 载["超时界"]  # 判据只认钉死界


def test_既有夹具口径不变(客):
    r = 客.post("/api/装载/夹具?名=成对样例")
    assert r.status_code == 200 and r.json()["成对"] == 2
    r = 客.post("/api/装载/夹具?名=缺腿超时样例")
    报 = r.json()
    assert 报["超时旁路"] == 1  # t1 卡09 超 7200 站规回落界被旁路
    a = 腿(客, "腿-t1")
    assert a["超时权威"] == "站规回落" and a["超时秒"] == 7200
    assert a["超时界"] == "2026-11-22T08:00:00Z"
    r = 客.post("/api/装载/夹具?名=出站孤儿样例")
    assert r.json()["旁路"] >= 1
    r = 客.post("/api/装载/夹具?名=重复进站样例")
    assert r.status_code == 200
    assert 客.post("/api/贯验").json()["是否通过"]
