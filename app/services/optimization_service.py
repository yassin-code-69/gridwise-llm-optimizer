"""End-to-end orchestration service coordinating all processing stages."""

import logging
import time
from typing import Optional
from app.config import settings
from app.core.constraint_compiler import compile_constraints
from app.core.optimizer import solve_energy_schedule
from app.core.reconstruction import reconstruct_hourly_plan
from app.core.replay_validator import validate_hourly_plan_replay
from app.core.summary import generate_plan_summary
from app.core.totals import recalculate_totals
from app.llm.interpreter import LLMInterpreter
from app.schemas.request import OptimizationRequest
from app.schemas.response import OptimizationResponse

logger = logging.getLogger(__name__)


class OptimizationService:
    """Orchestrates interpretation, validation, continuous LP solving, replay verification, and response assembly."""

    def __init__(self, interpreter: Optional[LLMInterpreter] = None):
        self.interpreter = interpreter or LLMInterpreter()

    async def optimize(
        self,
        request: OptimizationRequest,
        request_id: Optional[str] = None,
    ) -> OptimizationResponse:
        """Executes the complete optimization pipeline for an incoming scenario request."""
        t_start = time.perf_counter()
        req_tag = f"[{request_id}] " if request_id else ""
        logger.info(
            f"{req_tag}Starting energy optimization for scenario={request.scenario_id} "
            f"notes_count={len(request.operator_notes)} provider={settings.LLM_PROVIDER} model={settings.LLM_MODEL}"
        )

        # 1. LLM Semantic Interpretation & Deterministic Guardrails
        t0 = time.perf_counter()
        validated_directives = await self.interpreter.interpret_and_validate(
            request.operator_notes, request.battery
        )
        llm_ms = (time.perf_counter() - t0) * 1000.0
        logger.debug(f"{req_tag}LLM interpretation completed in {llm_ms:.1f}ms: {len(validated_directives)} directives parsed")

        # 2. Compile Constraints into 24-hour mathematical upper/lower bounds
        t0 = time.perf_counter()
        effective_constraints = compile_constraints(request, validated_directives)
        compile_ms = (time.perf_counter() - t0) * 1000.0

        # 3. Exact 24-Hour Continuous Linear Program Optimization
        t0 = time.perf_counter()
        raw_result = solve_energy_schedule(request, effective_constraints)
        solver_ms = (time.perf_counter() - t0) * 1000.0

        # 4. Hourly Plan Output Reconstruction
        t0 = time.perf_counter()
        hourly_plan = reconstruct_hourly_plan(request, raw_result)
        reconstruction_ms = (time.perf_counter() - t0) * 1000.0

        # 5. Independent Deterministic Replay Validator
        t0 = time.perf_counter()
        validate_hourly_plan_replay(request, effective_constraints, hourly_plan, validated_directives)
        replay_ms = (time.perf_counter() - t0) * 1000.0

        # 6. Deterministic Totals Recalculation from finalized hourly plan
        total_grid_kwh, total_cost_bdt, peak_grid_kwh = recalculate_totals(
            hourly_plan, request.hours
        )

        # 7. Deterministic Plan Summary Generation
        plan_summary = generate_plan_summary(
            validated_directives, hourly_plan, request.hours, request.battery
        )

        total_ms = (time.perf_counter() - t_start) * 1000.0
        logger.info(
            f"{req_tag}Optimization SUCCESS for scenario={request.scenario_id} in {total_ms:.1f}ms | "
            f"llm_ms={llm_ms:.1f}, compile_ms={compile_ms:.1f}, solver_ms={solver_ms:.1f}, "
            f"recon_ms={reconstruction_ms:.1f}, replay_ms={replay_ms:.1f} | "
            f"cost={total_cost_bdt:.2f} BDT, grid={total_grid_kwh:.2f} kWh, peak={peak_grid_kwh:.2f} kWh | "
            f"solver_status=Optimal result_status=SUCCESS"
        )

        return OptimizationResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=validated_directives,
            hourly_plan=hourly_plan,
            total_grid_kwh=total_grid_kwh,
            total_cost_bdt=total_cost_bdt,
            peak_grid_kwh=peak_grid_kwh,
            plan_summary=plan_summary,
        )


optimization_service = OptimizationService()
