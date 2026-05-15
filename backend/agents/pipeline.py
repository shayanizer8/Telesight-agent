import logging
import math
from collections import Counter
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from db import pipeline_status

logger = logging.getLogger(__name__)


class PipelineState(TypedDict):
    run_id: str
    csv_records: List[dict]
    pdf_text: str
    json_data: dict
    article_text: str
    live_feed_event: dict
    temporal_analysis: dict
    contradiction_report: dict
    insight_report: dict
    action_plan: dict
    errors: List[str]


def _ensure_errors(state: Dict[str, Any]) -> List[str]:
    errors = state.get("errors")
    if not isinstance(errors, list):
        errors = []
        state["errors"] = errors
    return errors


def _append_error(state: Dict[str, Any], message: str) -> None:
    _ensure_errors(state).append(message)


def _safe_update_pipeline_status(run_id: str, state: Dict[str, Any], **updates: Any) -> None:
    if pipeline_status is None:
        _append_error(state, "MongoDB pipeline_status collection is not available")
        return

    try:
        pipeline_status.update_one({"run_id": run_id}, {"$set": updates})
    except Exception as exc:
        error_message = f"Failed to update pipeline_status for run_id={run_id}: {exc}"
        logger.warning(error_message)
        _append_error(state, error_message)


def _get_numeric_values(records: List[dict], field_name: str) -> List[float]:
    values: List[float] = []
    for record in records:
        try:
            value = float(record.get(field_name, 0) or 0)
        except (TypeError, ValueError):
            value = 0.0
        values.append(value)
    return values


def _safe_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def ingest_node(state: PipelineState) -> PipelineState:
    run_id = state["run_id"]
    _safe_update_pipeline_status(run_id, state, status="processing", current_step="ingest")

    if pipeline_status is not None:
        try:
            document = pipeline_status.find_one({"run_id": run_id})
            if document is None:
                _append_error(state, f"Pipeline status document not found for run_id={run_id}")
            else:
                ingested_data = document.get("ingested_data", {})
                required_keys = ["pdf_text_length", "json_data", "live_feed_event"]
                missing_keys = [key for key in required_keys if key not in ingested_data]
                if missing_keys:
                    _append_error(state, f"Missing ingested data fields: {', '.join(missing_keys)}")
                if not state.get("pdf_text"):
                    _append_error(state, "pdf_text missing from pipeline state")
                if not state.get("json_data"):
                    _append_error(state, "json_data missing from pipeline state")
                if not state.get("live_feed_event"):
                    _append_error(state, "live_feed_event missing from pipeline state")
        except Exception as exc:
            _append_error(state, f"Failed to verify ingested pipeline data: {exc}")

    return state


def temporal_node(state: PipelineState) -> PipelineState:
    run_id = state["run_id"]
    _safe_update_pipeline_status(run_id, state, current_step="temporal")

    records = state.get("csv_records", [])
    try:
        last_month_values = _get_numeric_values(records, "data_usage_mb_last_month")
        two_months_values = _get_numeric_values(records, "data_usage_mb_2_months_ago")
        this_month_values = _get_numeric_values(records, "data_usage_mb_this_month")

        avg_last_month = _safe_mean(last_month_values)
        avg_two_months = _safe_mean(two_months_values)
        avg_this_month = _safe_mean(this_month_values)

        avg_usage_drop_last_month_pct = 0.0
        if avg_last_month:
            avg_usage_drop_last_month_pct = ((avg_last_month - avg_this_month) / avg_last_month) * 100

        avg_usage_drop_2_months_pct = 0.0
        if avg_two_months:
            avg_usage_drop_2_months_pct = ((avg_two_months - avg_this_month) / avg_two_months) * 100

        days_no_recharge_count = 0
        for record in records:
            try:
                if float(record.get("days_since_recharge", 0) or 0) > 30:
                    days_no_recharge_count += 1
            except (TypeError, ValueError):
                continue

        pct_customers_no_recharge_30_days = 0.0
        if records:
            pct_customers_no_recharge_30_days = (days_no_recharge_count / len(records)) * 100

        high_risk_regions = Counter(
            record.get("region", "unknown")
            for record in records
            if str(record.get("churn_risk", "")).lower() == "high"
        )
        highest_risk_region = high_risk_regions.most_common(1)[0][0] if high_risk_regions else "unknown"

        if avg_usage_drop_2_months_pct > avg_usage_drop_last_month_pct + 5:
            trend = "accelerating"
        elif avg_usage_drop_last_month_pct <= 0 and avg_usage_drop_2_months_pct <= 0:
            trend = "improving"
        else:
            trend = "stable"

        state["temporal_analysis"] = {
            "avg_usage_drop_last_month_pct": float(avg_usage_drop_last_month_pct),
            "avg_usage_drop_2_months_pct": float(avg_usage_drop_2_months_pct),
            "pct_customers_no_recharge_30_days": float(pct_customers_no_recharge_30_days),
            "highest_risk_region": highest_risk_region,
            "trend": trend,
        }
    except Exception as exc:
        _append_error(state, f"Temporal analysis failed: {exc}")
        state["temporal_analysis"] = {
            "avg_usage_drop_last_month_pct": 0.0,
            "avg_usage_drop_2_months_pct": 0.0,
            "pct_customers_no_recharge_30_days": 0.0,
            "highest_risk_region": "unknown",
            "trend": "stable",
        }

    return state


def contradiction_node(state: PipelineState) -> PipelineState:
    run_id = state["run_id"]
    _safe_update_pipeline_status(run_id, state, current_step="contradiction")

    try:
        article_text = (state.get("article_text") or "").lower()
        pdf_text = (state.get("pdf_text") or "").lower()
        positive_keywords = ["satisfaction", "improved", "improvement", "positive", "growth", "stronger"]
        article_source_available = bool(article_text)
        article_keyword_hit = any(keyword in article_text for keyword in positive_keywords) if article_source_available else False
        pdf_keyword_hit = any(keyword in pdf_text for keyword in positive_keywords)

        high_risk_customers = sum(
            1
            for record in state.get("csv_records", [])
            if str(record.get("churn_risk", "")).lower() == "high"
        )

        conflict_detected = (article_keyword_hit or pdf_keyword_hit) and high_risk_customers > 2000
        if conflict_detected:
            conflict_source = "article" if article_keyword_hit else "PDF"
            conflict_description = (
                f"{conflict_source.capitalize()} sentiment suggests improving telecom satisfaction while CSV data shows a large high-risk churn segment."
            )
            resolution_path = "Prioritize churn signals from CSV and validate the article context manually."
        else:
            conflict_description = "No material contradiction detected across article, survey, and churn signals."
            resolution_path = "Continue monitoring all sources for alignment."

        state["contradiction_report"] = {
            "conflict_detected": conflict_detected,
            "conflict_description": conflict_description,
            "csv_credibility_score": 0.91,
            "article_credibility_score": 0.54,
            "article_source_available": article_source_available,
            "resolution_path": resolution_path,
        }
    except Exception as exc:
        _append_error(state, f"Contradiction analysis failed: {exc}")
        state["contradiction_report"] = {
            "conflict_detected": False,
            "conflict_description": "Contradiction analysis unavailable.",
            "csv_credibility_score": 0.91,
            "article_credibility_score": 0.54,
            "article_source_available": bool((state.get("article_text") or "")),
            "resolution_path": "Re-run analysis after data validation.",
        }

    return state


def insight_node(state: PipelineState) -> PipelineState:
    run_id = state["run_id"]
    _safe_update_pipeline_status(run_id, state, current_step="insight")

    try:
        records = state.get("csv_records", [])
        high_risk_records = [
            record for record in records if str(record.get("churn_risk", "")).lower() == "high"
        ]
        total_high_risk_customers = len(high_risk_records)

        high_risk_by_region = dict(Counter(record.get("region", "unknown") for record in high_risk_records))

        avg_days_no_recharge = _safe_mean(
            [float(record.get("days_since_recharge", 0) or 0) for record in high_risk_records]
        )
        avg_complaints = _safe_mean(
            [float(record.get("complaints_last_30_days", 0) or 0) for record in high_risk_records]
        )

        projected_revenue_loss_pkr = float(340 * total_high_risk_customers * 0.65)

        if total_high_risk_customers >= 3000 or projected_revenue_loss_pkr >= 700000:
            severity = "critical"
        elif total_high_risk_customers >= 2000 or projected_revenue_loss_pkr >= 400000:
            severity = "high"
        else:
            severity = "medium"

        if avg_days_no_recharge >= 30 and avg_complaints >= 2:
            primary_churn_signal = "usage_drop_and_recharge_delay"
        elif avg_complaints >= 2:
            primary_churn_signal = "complaint_pressure"
        else:
            primary_churn_signal = "usage_decline"

        state["insight_report"] = {
            "total_high_risk_customers": total_high_risk_customers,
            "high_risk_by_region": high_risk_by_region,
            "avg_days_no_recharge": float(avg_days_no_recharge),
            "avg_complaints": float(avg_complaints),
            "projected_revenue_loss_pkr": projected_revenue_loss_pkr,
            "primary_churn_signal": primary_churn_signal,
            "severity": severity,
        }
    except Exception as exc:
        _append_error(state, f"Insight generation failed: {exc}")
        state["insight_report"] = {
            "total_high_risk_customers": 0,
            "high_risk_by_region": {},
            "avg_days_no_recharge": 0.0,
            "avg_complaints": 0.0,
            "projected_revenue_loss_pkr": 0.0,
            "primary_churn_signal": "usage_decline",
            "severity": "medium",
        }

    return state


def action_node(state: PipelineState) -> PipelineState:
    run_id = state["run_id"]
    _safe_update_pipeline_status(run_id, state, current_step="action")

    try:
        budget_pkr = 50000
        sms_rate_limit_per_hour = 500
        time_window_hours = 48
        cost_per_sms_pkr = 25
        max_sms_affordable = int(budget_pkr / cost_per_sms_pkr)

        total_high_risk_customers = int(state.get("insight_report", {}).get("total_high_risk_customers", 0) or 0)
        customers_to_target = min(total_high_risk_customers, max_sms_affordable)
        batches_needed = math.ceil(customers_to_target / sms_rate_limit_per_hour) if customers_to_target else 0
        time_to_complete_hours = float(batches_needed)

        state["action_plan"] = {
            "constraints_applied": {
                "budget_pkr": budget_pkr,
                "max_sms_affordable": max_sms_affordable,
                "rate_limit_per_hour": sms_rate_limit_per_hour,
                "batches_needed": batches_needed,
                "time_to_complete_hours": time_to_complete_hours,
            },
            "actions": [
                {
                    "step": 1,
                    "name": "diagnose_cause",
                    "status": "pending",
                    "output": "Primary churn driver: usage drop + no recharge in high risk segment",
                },
                {
                    "step": 2,
                    "name": "notify_manager",
                    "status": "pending",
                    "output": "Alert drafted for regional manager",
                },
                {
                    "step": 3,
                    "name": "update_crm",
                    "status": "pending",
                    "output": f"{total_high_risk_customers} customers to be tagged churn-risk-april-2026",
                },
                {
                    "step": 4,
                    "name": "launch_sms_campaign",
                    "status": "pending",
                    "output": "SMS campaign batched per rate limit",
                },
                {
                    "step": 5,
                    "name": "schedule_monitor",
                    "status": "pending",
                    "output": "7-day follow-up monitor scheduled",
                },
            ],
        }

        _safe_update_pipeline_status(run_id, state, status="ready_for_execution", current_step="action")
    except Exception as exc:
        _append_error(state, f"Action planning failed: {exc}")
        state["action_plan"] = {
            "constraints_applied": {
                "budget_pkr": 50000,
                "max_sms_affordable": 0,
                "rate_limit_per_hour": 500,
                "batches_needed": 0,
                "time_to_complete_hours": 0.0,
            },
            "actions": [],
        }

    return state


graph = StateGraph(PipelineState)
graph.add_node("ingest", ingest_node)
graph.add_node("temporal", temporal_node)
graph.add_node("contradiction", contradiction_node)
graph.add_node("insight", insight_node)
graph.add_node("action", action_node)

graph.set_entry_point("ingest")
graph.add_edge("ingest", "temporal")
graph.add_edge("temporal", "contradiction")
graph.add_edge("contradiction", "insight")
graph.add_edge("insight", "action")
graph.add_edge("action", END)

pipeline_graph = graph.compile()


def run_pipeline(run_id: str, state_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        initial_state: Dict[str, Any] = {
            "run_id": run_id,
            "csv_records": [],
            "pdf_text": "",
            "json_data": {},
            "article_text": "",
            "live_feed_event": {},
            "temporal_analysis": {},
            "contradiction_report": {},
            "insight_report": {},
            "action_plan": {},
            "errors": [],
        }
        initial_state.update(state_data or {})
        initial_state["run_id"] = run_id

        final_state = pipeline_graph.invoke(initial_state)
        return final_state
    except Exception as exc:
        logger.exception("TeleSight pipeline failed for run_id=%s", run_id)
        fallback_state: Dict[str, Any] = {
            "run_id": run_id,
            "csv_records": [],
            "pdf_text": "",
            "json_data": {},
            "article_text": "",
            "live_feed_event": {},
            "temporal_analysis": {},
            "contradiction_report": {},
            "insight_report": {},
            "action_plan": {},
            "errors": [f"Pipeline execution failed: {exc}"],
        }
        return fallback_state