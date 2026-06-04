from titan_echo.echo_api import _parsed_record_status_and_reason


def test_runtime_status_parser_reads_authoritative_runtime_health():
    status, reason = _parsed_record_status_and_reason(
        {
            "mode": "WEEKEND_MODE",
            "status": None,
            "overall_status": None,
            "authoritative_runtime_health": {
                "overall_status": "WARNING",
            },
        }
    )

    assert status == "WARNING"
    assert reason == "parsed key authoritative_runtime_health.overall_status"


def test_runtime_status_parser_prefers_authoritative_runtime_health():
    status, reason = _parsed_record_status_and_reason(
        {
            "status": "STALE_TOP_LEVEL",
            "overall_status": "WARNING_TOP_LEVEL",
            "authoritative_runtime_health": {
                "overall_status": "WARNING",
            },
        }
    )

    assert status == "WARNING"
    assert reason == "parsed key authoritative_runtime_health.overall_status"


def test_trade_diagnostic_parser_reads_top_level_status():
    status, reason = _parsed_record_status_and_reason(
        {
            "schema": "titan.echo.trade_contract_diagnostics.v1",
            "status": "EVIDENCE_PRESENT",
            "reason": "FILTER_DIAGNOSTICS_PARSED",
        }
    )

    assert status == "EVIDENCE_PRESENT"
    assert reason == "parsed key status"


def test_csv_row_parser_is_not_unknown():
    status, reason = _parsed_record_status_and_reason([{"symbol": "RELIANCE"}])

    assert status == "ROWS_PRESENT"
    assert reason == "CSV_OR_JSONL_ROW_COUNT_PARSED"
