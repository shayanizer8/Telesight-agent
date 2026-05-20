import logging
import uuid
from datetime import datetime, timezone, timedelta
from time import sleep
from fastapi import APIRouter, HTTPException

from db import action_logs, pipeline_status, campaigns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions")


@router.post("/execute/{run_id}")
def execute_actions(run_id: str) -> dict:
    # Validate database connection and collections
    if pipeline_status is None or action_logs is None or campaigns is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection is not configured or collections are missing.",
        )

    # Fetch pipeline_status document
    pipeline_doc = pipeline_status.find_one({"run_id": run_id})
    if not pipeline_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline status document for run_id '{run_id}' not found.",
        )

    # Extract fields explicitly as requested
    insight_report = pipeline_doc.get("insight_report", {})
    action_plan = pipeline_doc.get("action_plan", {})
    constraints = action_plan.get("constraints_applied", {})

    total_high_risk = insight_report.get("total_high_risk_customers", 0)
    projected_loss = insight_report.get("projected_revenue_loss_pkr", 0)
    severity = insight_report.get("severity", "unknown")
    primary_signal = insight_report.get("primary_churn_signal", "unknown")
    highest_region = insight_report.get("high_risk_by_region", {})
    avg_days = insight_report.get("avg_days_no_recharge", 0)
    avg_complaints = insight_report.get("avg_complaints", 0)
    max_sms = constraints.get("max_sms_affordable", 0)
    batches = constraints.get("batches_needed", 0)
    rate_limit = constraints.get("rate_limit_per_hour", 500)

    # Determine highest risk region for Action 1
    highest_risk_region = "unknown"
    if highest_region:
        highest_risk_region = max(highest_region, key=highest_region.get)
    else:
        # Fallback to temporal analysis highest risk region if high_risk_by_region is empty
        temporal_analysis = pipeline_doc.get("temporal_analysis", {})
        highest_risk_region = temporal_analysis.get("highest_risk_region", "unknown")

    # ----------------------------------------------------
    # ACTION 1 — diagnose_cause
    # ----------------------------------------------------
    pipeline_status.update_one(
        {"run_id": run_id},
        {"$set": {"current_step": "executing_action_1"}},
    )

    diagnosis_string = (
        f"Primary churn driver: {primary_signal}. "
        f"{total_high_risk} customers at risk in "
        f"{highest_risk_region} region. Avg days without "
        f"recharge: {avg_days}. "
        f"Avg complaints: {avg_complaints}."
    )

    action_logs.insert_one({
        "run_id": run_id,
        "step": 1,
        "action_name": "diagnose_cause",
        "status": "success",
        "output": diagnosis_string,
        "timestamp": datetime.now(timezone.utc),
        "retry_count": 0,
    })

    # ----------------------------------------------------
    # ACTION 2 — notify_manager
    # ----------------------------------------------------
    pipeline_status.update_one(
        {"run_id": run_id},
        {"$set": {"current_step": "executing_action_2"}},
    )

    manager_alert = {
        "alert_type": "churn_risk_critical",
        "region": "Lahore",
        "at_risk_customers": total_high_risk,
        "projected_loss_pkr": projected_loss,
        "severity": severity,
        "recommended_action": "Launch SMS retention campaign",
        "generated_at": datetime.now(timezone.utc),
    }

    action_logs.insert_one({
        "run_id": run_id,
        "step": 2,
        "action_name": "notify_manager",
        "status": "success",
        "output": manager_alert,
        "timestamp": datetime.now(timezone.utc),
        "retry_count": 0,
    })

    # ----------------------------------------------------
    # ACTION 3 — update_crm (DELIBERATELY FAIL THIS)
    # ----------------------------------------------------
    pipeline_status.update_one(
        {"run_id": run_id},
        {"$set": {"current_step": "executing_action_3"}},
    )

    try:
        raise Exception("Mock CRM API returned HTTP 500: Internal Server Error")
    except Exception as exc:
        action_logs.insert_one({
            "run_id": run_id,
            "step": 3,
            "action_name": "update_crm",
            "status": "failed",
            "error_message": str(exc),
            "timestamp": datetime.now(timezone.utc),
            "retry_count": 0,
        })

        # Wait 2 seconds then retry once
        sleep(2)

        try:
            raise Exception("Mock CRM API returned HTTP 500: Internal Server Error")
        except Exception as retry_exc:
            action_logs.insert_one({
                "run_id": run_id,
                "step": 3,
                "action_name": "update_crm",
                "status": "rolled_back",
                "error_message": "Retry failed. State rolled back.",
                "timestamp": datetime.now(timezone.utc),
                "retry_count": 1,
            })
            pipeline_status.update_one(
                {"run_id": run_id},
                {"$set": {"current_step": "action_3_failed_rolling_back"}},
            )

    # ----------------------------------------------------
    # ACTION 4 — launch_sms_campaign
    # ----------------------------------------------------
    pipeline_status.update_one(
        {"run_id": run_id},
        {"$set": {"current_step": "executing_action_4"}},
    )

    gemini_sms_template = action_plan.get("gemini_sms_template", "")
    sms_template = (
        gemini_sms_template if gemini_sms_template else
        "Dear valued Telenor customer, we noticed you haven't recharged recently. "
        "Recharge today and get 3GB bonus data free. Valid for 7 days. Reply STOP to opt out."
    )

    campaign_id = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    scheduled_batches = []
    remaining_sms = max_sms

    for b in range(1, batches + 1):
        customer_count = min(rate_limit, remaining_sms)
        scheduled_batches.append({
            "batch_number": b,
            "scheduled_at": current_time + timedelta(hours=b - 1),
            "customer_count": customer_count,
        })
        remaining_sms -= customer_count

    campaigns.insert_one({
        "campaign_id": campaign_id,
        "run_id": run_id,
        "created_at": current_time,
        "target_count": max_sms,
        "batch_count": batches,
        "sms_per_batch": rate_limit,
        "status": "launched",
        "sms_template": sms_template,
        "scheduled_batches": scheduled_batches,
    })

    action_logs.insert_one({
        "run_id": run_id,
        "step": 4,
        "action_name": "launch_sms_campaign",
        "status": "success",
        "output": {
            "campaign_id": campaign_id,
            "customers_targeted": max_sms,
            "batches_scheduled": batches,
            "sms_template": sms_template,
        },
        "timestamp": datetime.now(timezone.utc),
        "retry_count": 0,
    })

    # ----------------------------------------------------
    # ACTION 5 — schedule_monitor
    # ----------------------------------------------------
    pipeline_status.update_one(
        {"run_id": run_id},
        {"$set": {"current_step": "executing_action_5"}},
    )

    monitor_task = {
        "monitor_type": "retention_followup",
        "scheduled_for": datetime.now(timezone.utc) + timedelta(days=7),
        "check_metric": "recharge_rate_among_targeted_customers",
        "alert_threshold": "if less than 40% recharge, escalate",
    }

    action_logs.insert_one({
        "run_id": run_id,
        "step": 5,
        "action_name": "schedule_monitor",
        "status": "success",
        "output": monitor_task,
        "timestamp": datetime.now(timezone.utc),
        "retry_count": 0,
    })

    # ----------------------------------------------------
    # AFTER ALL ACTIONS: update pipeline status outcome
    # ----------------------------------------------------
    outcome = {
        "before_state": {
            "at_risk_customers": total_high_risk,
            "active_campaigns": 0,
            "projected_loss_pkr": projected_loss,
        },
        "after_state": {
            "campaign_launched": True,
            "customers_targeted": max_sms,
            "sms_batches_scheduled": batches,
            "crm_update": "partial - manual review needed",
            "estimated_recovery_pkr": round(max_sms * 340 * 0.68),
        },
        "actions_succeeded": 3,
        "actions_failed": 0,
        "actions_rolled_back": 1,
        "projected_retention_pct": 68,
        "execution_completed_at": datetime.now(timezone.utc),
    }

    pipeline_status.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "status": "complete",
                "current_step": "complete",
                "outcome": outcome,
            }
        },
    )

    return {
        "status": "complete",
        "run_id": run_id,
        "outcome": outcome,
    }


@router.get("/logs/{run_id}")
def get_action_logs(run_id: str) -> list[dict]:
    if action_logs is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection is not configured or action_logs collection is missing.",
        )

    logs = list(action_logs.find({"run_id": run_id}).sort("step", 1))

    for log in logs:
        if "_id" in log:
            log["_id"] = str(log["_id"])

    return logs
