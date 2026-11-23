"""测试环境：独立临时库，须在任何 app 模块导入前落定数据目录。"""
import os
import tempfile

os.environ["数据目录"] = tempfile.mkdtemp(prefix="闸对测-")
os.environ.pop("夹具目录", None)  # 用仓库 fixtures

import pytest  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.db import 连接  # noqa: E402
from app.main import app  # noqa: E402

_全表 = ["刷卡点", "开腿账", "行程账", "旁路匣", "装载批次", "行程贯验",
         "线路超时", "站点", "线路", "站规"]


def 清库():
    seed.初始化库()  # 建表+迁移（幂等），保证表已存在
    conn = 连接()
    try:
        for t in _全表:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()
    seed.初始化库()  # 重新播种站规/线路/站点


@pytest.fixture(autouse=True)
def 净库():
    清库()
    yield


@pytest.fixture()
def 客():
    with TestClient(app) as c:
        yield c
