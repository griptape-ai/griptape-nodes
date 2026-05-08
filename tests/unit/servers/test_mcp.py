from griptape_nodes.servers.mcp import _summarize_result_details, _trim_response


class TestSummarizeResultDetails:
    def test_returns_none_for_none(self) -> None:
        assert _summarize_result_details(None) is None

    def test_passes_strings_through(self) -> None:
        assert _summarize_result_details("already a string") == "already a string"

    def test_joins_messages_from_nested_result_details(self) -> None:
        payload = {
            "result_details": [
                {"level": 20, "message": "first"},
                {"level": 10, "message": "second"},
            ]
        }

        assert _summarize_result_details(payload) == "first\nsecond"

    def test_returns_inner_list_when_all_messages_empty(self) -> None:
        payload = {"result_details": [{"level": 20, "message": ""}]}

        # Fall back to the raw list so we never hide data we did not recognize.
        assert _summarize_result_details(payload) == [{"level": 20, "message": ""}]

    def test_returns_input_unchanged_for_unrecognized_shape(self) -> None:
        payload = {"something_else": 1}

        assert _summarize_result_details(payload) == payload


class TestTrimResponse:
    def test_drops_envelope_noise_and_flattens_details(self) -> None:
        raw = {
            "engine_id": "engine-1",
            "session_id": "session-1",
            "request": {"node_type": "Probe", "library": "demo"},
            "request_id": "abc",
            "response_topic": "response",
            "retained_mode": "cmd.create_node(...)",
            "event_type": "EventResultSuccess",
            "request_type": "CreateNodeRequest",
            "result_type": "CreateNodeResultSuccess",
            "result": {
                "result_details": {
                    "result_details": [
                        {"level": 10, "message": "Created node 'Probe_1'"},
                    ]
                },
                "altered_workflow_state": True,
                "node_name": "Probe_1",
            },
        }

        trimmed = _trim_response(raw)

        assert trimmed == {
            "ok": True,
            "details": "Created node 'Probe_1'",
            "altered_workflow_state": True,
            "node_name": "Probe_1",
        }

    def test_marks_failures_with_ok_false(self) -> None:
        raw = {
            "result_type": "CreateNodeResultFailure",
            "result": {
                "result_details": {
                    "result_details": [{"level": 40, "message": "boom"}],
                },
                "altered_workflow_state": False,
            },
        }

        trimmed = _trim_response(raw)

        assert trimmed["ok"] is False
        assert trimmed["details"] == "boom"
        assert trimmed["altered_workflow_state"] is False

    def test_handles_missing_result_gracefully(self) -> None:
        trimmed = _trim_response({"result_type": "SomethingSuccess"})

        assert trimmed == {"ok": True}
