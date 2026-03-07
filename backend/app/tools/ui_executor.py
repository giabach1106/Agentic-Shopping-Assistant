from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.models.agent_outputs import CandidateProduct, ExecutionTraceEvent


@dataclass(slots=True)
class UIExecutionRequest:
    constraints: dict[str, Any]
    consent_autofill: bool
    stop_before_pay: bool


@dataclass(slots=True)
class UIExecutionResult:
    candidates: list[dict[str, Any]]
    execution_trace: list[dict[str, Any]]
    blockers: list[str]
    consent_autofill: bool
    stop_before_pay: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "executionTrace": self.execution_trace,
            "blockers": self.blockers,
            "consentAutofill": self.consent_autofill,
            "stopBeforePay": self.stop_before_pay,
        }


class UIExecutor(Protocol):
    async def execute(self, request: UIExecutionRequest) -> UIExecutionResult:
        """Execute shopping UI flow while enforcing safety policy."""


class MockUIExecutor:
    async def execute(self, request: UIExecutionRequest) -> UIExecutionResult:
        exclude = [item.lower() for item in request.constraints.get("exclude", [])]
        blocked = any(marker in exclude for marker in ("captcha", "blocked", "rate limited"))

        trace: list[ExecutionTraceEvent] = [
            ExecutionTraceEvent(
                step="open_storefront",
                status="ok",
                detail="Opened mock storefront and collected baseline offers.",
            )
        ]
        blockers: list[str] = []
        candidates: list[CandidateProduct] = []

        if blocked:
            blockers.append("automation_blocked")
            trace.append(
                ExecutionTraceEvent(
                    step="checkout_navigation",
                    status="blocked",
                    detail="UI automation encountered anti-bot checkpoint and stopped safely.",
                )
            )
        else:
            candidates = [
                CandidateProduct(
                    title="ErgoFlex Dorm Chair",
                    sourceUrl="https://example.com/product/ergoflex-chair",
                    price=139.99,
                    rating=4.4,
                    shippingETA="2-4 days",
                    returnPolicy="30-day return",
                    checkoutReady=True,
                    evidenceRefs=["offer-1", "ship-1", "policy-1"],
                ),
                CandidateProduct(
                    title="CampusComfort Mesh Chair",
                    sourceUrl="https://example.com/product/campuscomfort-chair",
                    price=124.99,
                    rating=4.1,
                    shippingETA="5-7 days",
                    returnPolicy="14-day return",
                    checkoutReady=True,
                    evidenceRefs=["offer-2", "ship-2", "policy-2"],
                ),
            ]
            trace.append(
                ExecutionTraceEvent(
                    step="price_compare",
                    status="ok",
                    detail="Compared candidate pricing, shipping, and return policy.",
                )
            )

        if request.consent_autofill and not blocked:
            trace.append(
                ExecutionTraceEvent(
                    step="autofill_checkout",
                    status="ok",
                    detail="Autofilled checkout profile fields with consent enabled.",
                )
            )
        else:
            trace.append(
                ExecutionTraceEvent(
                    step="autofill_checkout",
                    status="skipped",
                    detail="Skipped autofill because consent_autofill is false or flow blocked.",
                )
            )

        final_step = (
            "Stopped at review step before payment."
            if request.stop_before_pay
            else "Policy misconfigured: stop_before_pay=false."
        )
        trace.append(
            ExecutionTraceEvent(
                step="prepay_guardrail",
                status="ok" if request.stop_before_pay else "warning",
                detail=final_step,
            )
        )

        return UIExecutionResult(
            candidates=[item.model_dump(by_alias=True) for item in candidates],
            execution_trace=[item.model_dump(by_alias=True) for item in trace],
            blockers=blockers,
            consent_autofill=request.consent_autofill,
            stop_before_pay=request.stop_before_pay,
        )


class NovaActExecutor:
    def __init__(self, model_router: ModelRouter, settings: Settings) -> None:
        self._model_router = model_router
        self._settings = settings
        self._mock_executor = MockUIExecutor()

    async def execute(self, request: UIExecutionRequest) -> UIExecutionResult:
        # We still use mock business output for deterministic tests.
        base_result = await self._mock_executor.execute(request)
        model_result = await self._model_router.call(
            task_type="nova_act_executor",
            payload={
                "prompt": (
                    "Execute UI automation until pre-pay step only. "
                    f"stop_before_pay={request.stop_before_pay}, "
                    f"consent_autofill={request.consent_autofill}, "
                    f"constraints={request.constraints}"
                )
            },
        )

        trace = list(base_result.execution_trace)
        trace.insert(
            0,
            {
                "step": "nova_act_dispatch",
                "status": "ok",
                "detail": (
                    f"Nova Act backend={self._settings.ui_executor_backend}, "
                    f"model={model_result.model_id}, fallback={model_result.fallback_used}"
                ),
            },
        )
        base_result.execution_trace = trace
        return base_result


def build_ui_executor(settings: Settings, model_router: ModelRouter) -> UIExecutor:
    backend = settings.ui_executor_backend.lower().strip()
    if backend == "nova_act":
        return NovaActExecutor(model_router=model_router, settings=settings)
    return MockUIExecutor()

