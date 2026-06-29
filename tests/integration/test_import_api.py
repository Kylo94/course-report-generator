"""批量导入 API 集成测试。"""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

pytestmark = pytest.mark.asyncio


def _make_csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _make_xlsx_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


class TestImportCSV:
    async def test_import_valid_csv(self, api_client) -> None:
        csv_content = (
            "姓名,年龄,性别,基础水平,性格特点\n"
            "张三,10,男,入门,内向|喜欢挑战\n"
            "李四,11,女,初级,大胆\n"
        )
        files = {"file": ("students.csv", _make_csv_bytes(csv_content), "text/csv")}
        resp = await api_client.post("/api/import/students", files=files)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["success"] == 2
        assert data["failed"] == 0
        assert len(data["created_ids"]) == 2

    async def test_import_partial_failure(self, api_client) -> None:
        csv_content = (
            "姓名,年龄,性别,基础水平\n"
            "张三,10,男,入门\n"
            ",11,女,入门\n"  # 姓名为空，应失败
            "李四,abc,男,入门\n"  # 年龄"abc"被宽容地转为 None，仍可导入
        )
        files = {"file": ("students.csv", _make_csv_bytes(csv_content), "text/csv")}
        resp = await api_client.post("/api/import/students", files=files)

        data = resp.json()
        assert data["total"] == 3
        # 宽容策略：非法年龄转为 None → 2 成功；空姓名 → 1 失败
        assert data["success"] == 2
        assert data["failed"] == 1
        assert len(data["errors"]) == 1
        assert "姓名" in data["errors"][0]["error"]


class TestImportXLSX:
    async def test_import_valid_xlsx(self, api_client) -> None:
        xlsx_bytes = _make_xlsx_bytes([
            ["姓名", "年龄", "性别", "基础水平"],
            ["张三", 10, "男", "入门"],
            ["李四", 11, "女", "初级"],
            ["王五", 12, "男", "中级"],
        ])
        files = {
            "file": (
                "students.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        resp = await api_client.post("/api/import/students", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] == 3

    async def test_import_xlsx_with_invalid_level(self, api_client) -> None:
        xlsx_bytes = _make_xlsx_bytes([
            ["姓名", "基础水平"],
            ["张三", "入门"],
            ["李四", "高级"],  # 非法水平
        ])
        files = {
            "file": ("students.xlsx", xlsx_bytes, "application/vnd.ms-excel")
        }
        resp = await api_client.post("/api/import/students", files=files)
        data = resp.json()
        assert data["success"] == 1
        assert data["failed"] == 1


class TestImportErrorHandling:
    async def test_unsupported_format(self, api_client) -> None:
        files = {"file": ("test.txt", b"hello", "text/plain")}
        resp = await api_client.post("/api/import/students", files=files)
        assert resp.status_code == 400
        assert "xlsx" in resp.json()["detail"].lower()

    async def test_empty_file(self, api_client) -> None:
        # 空 xlsx
        wb = Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        files = {"file": ("empty.xlsx", buf.getvalue(), "application/vnd.ms-excel")}
        resp = await api_client.post("/api/import/students", files=files)
        data = resp.json()
        assert data["total"] == 0
        assert data["success"] == 0
