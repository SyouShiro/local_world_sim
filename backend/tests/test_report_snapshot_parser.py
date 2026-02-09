from __future__ import annotations

from app.services.report_snapshot import parse_report_snapshot


def test_parse_report_snapshot_repairs_dangling_key_quote() -> None:
    content = (
        "{"
        "\"title\":\"世界进展月报\","
        "\"time_advance\":\"1个月\","
        "\"summary\":\"局势持续波动。\","
        "\"events\":[{\"category\":\"negative\",\"severity\":\"high\",\"description\":\"边境冲突升级。\"}],"
        "\"risks\":[{\"category\":\"negative\",\"severity\":\"medium\", description\": \"补给线存在中断风险。\"}]"
        "}"
    )
    snapshot = parse_report_snapshot(content, fallback_time_advance="1个月")
    assert snapshot is not None
    assert snapshot["title"] == "世界进展月报"
    assert snapshot["events"][0]["severity"] == "high"
    assert snapshot["risks"][0]["description"] == "补给线存在中断风险。"


def test_parse_report_snapshot_repairs_unquoted_keys_and_trailing_commas() -> None:
    content = (
        "{"
        "title: \"World Report\","
        "time_advance: \"1 month\","
        "summary: \"Signals remain mixed.\","
        "events: [{category: \"positive\", severity: \"medium\", description: \"Trade route reopened.\"},],"
        "risks: [{category: \"negative\", severity: \"high\", description: \"Border escalation likely.\"},],"
        "}"
    )
    snapshot = parse_report_snapshot(content, fallback_time_advance="1 month")
    assert snapshot is not None
    assert snapshot["time_advance"] == "1 month"
    assert snapshot["events"][0]["category"] == "positive"
    assert snapshot["risks"][0]["severity"] == "high"
