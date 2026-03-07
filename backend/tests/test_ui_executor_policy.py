from __future__ import annotations

import asyncio

from app.tools.ui_executor import MockUIExecutor, UIExecutionRequest


def test_mock_ui_executor_enforces_prepay_guardrail() -> None:
    async def run_test() -> None:
        executor = MockUIExecutor()
        result = await executor.execute(
            UIExecutionRequest(
                constraints={"category": "ergonomic chair"},
                consent_autofill=False,
                stop_before_pay=True,
            )
        )
        trace = result.to_public_dict()["executionTrace"]
        assert any(event["step"] == "prepay_guardrail" for event in trace)
        assert result.stop_before_pay is True

    asyncio.run(run_test())


def test_mock_ui_executor_respects_autofill_consent() -> None:
    async def run_test() -> None:
        executor = MockUIExecutor()
        with_consent = await executor.execute(
            UIExecutionRequest(
                constraints={"category": "ergonomic chair"},
                consent_autofill=True,
                stop_before_pay=True,
            )
        )
        without_consent = await executor.execute(
            UIExecutionRequest(
                constraints={"category": "ergonomic chair"},
                consent_autofill=False,
                stop_before_pay=True,
            )
        )

        trace_with = with_consent.to_public_dict()["executionTrace"]
        trace_without = without_consent.to_public_dict()["executionTrace"]
        assert any(
            event["step"] == "autofill_checkout" and event["status"] == "ok"
            for event in trace_with
        )
        assert any(
            event["step"] == "autofill_checkout" and event["status"] == "skipped"
            for event in trace_without
        )

    asyncio.run(run_test())

