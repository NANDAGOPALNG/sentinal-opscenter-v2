from __future__ import annotations

import os
import json
from typing import Any

import httpx
import streamlit as st


DEFAULT_API_URL = os.getenv("SENTINAL_API_URL", "http://localhost:8001")


st.set_page_config(
    page_title="Sentinal OpsCenter V2",
    page_icon="Sentinal",
    layout="wide",
)


def api_get(path: str) -> Any:
    response = httpx.get(f"{st.session_state.api_url}{path}", timeout=20.0)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any], secret: str = "") -> Any:
    body = json.dumps(payload, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    if secret:
        import hashlib
        import hmac

        signature = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={signature}"
    response = httpx.post(
        f"{st.session_state.api_url}{path}",
        content=body,
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def render_status_cards() -> None:
    cols = st.columns(3)
    try:
        health = api_get("/health")
    except Exception as exc:
        health = {"status": "error", "detail": str(exc)}
    try:
        github = api_get("/github/status")
    except Exception as exc:
        github = {"configured": False, "detail": str(exc)}
    try:
        notifications = api_get("/notifications/status")
    except Exception as exc:
        notifications = {"discord_configured": False, "detail": str(exc)}

    cols[0].metric("API", health.get("status", "unknown"))
    cols[1].metric("GitHub", "connected" if github.get("authenticated") else "not connected")
    cols[2].metric("Notifier", "discord" if notifications.get("discord_configured") else "log")

    with st.expander("System Status Details"):
        st.json({"health": health, "github": github, "notifications": notifications})


def render_trigger_form() -> None:
    st.subheader("Trigger Demo Incident")
    with st.form("trigger_incident"):
        repository = st.text_input("Repository", value="NANDAGOPALNG/sentinal-opscenter-v2")
        message = st.text_input("Message", value="Synthetic latency spike from dashboard demo")
        severity = st.selectbox("Severity", ["warning", "info", "critical"], index=0)
        files = st.text_input("Files", value="README.md,Dockerfile,apps/api/main.py")
        webhook_secret = st.text_input("Webhook Secret", value="", type="password")
        submitted = st.form_submit_button("Start Workflow")

    if submitted:
        payload = {
            "event_type": "dashboard_demo",
            "service": "api",
            "severity": severity,
            "message": message,
            "repository": repository,
            "files": [item.strip() for item in files.split(",") if item.strip()],
        }
        try:
            result = api_post("/webhook", payload, webhook_secret)
            st.success("Workflow accepted")
            st.json(result)
        except Exception as exc:
            st.error(f"Failed to trigger workflow: {exc}")


def render_workflow_details(workflow: dict[str, Any]) -> None:
    st.subheader("Workflow Details")
    cols = st.columns(5)
    cols[0].metric("Status", workflow.get("status", "unknown"))
    cols[1].metric("Event", workflow.get("event_type", "unknown"))
    cols[2].metric("Step", workflow.get("current_step") or "n/a")
    cols[3].metric("Retries", workflow.get("retry_count", 0))
    cols[4].metric("Validated", str(workflow.get("validation_passed")))

    st.caption(f"Trace: {workflow.get('trace_id') or 'n/a'}")
    st.caption(f"Dedupe: {workflow.get('dedupe_key') or 'n/a'}")

    tab_plan, tab_findings, tab_fix, tab_payload = st.tabs(
        ["Plan", "Findings", "Fix Proposal", "Payload"]
    )
    with tab_plan:
        plan = workflow.get("plan") or []
        if plan:
            for index, step in enumerate(plan, start=1):
                st.write(f"{index}. {step}")
        else:
            st.info("No plan recorded.")

    findings = workflow.get("findings") or {}
    with tab_findings:
        st.markdown("**Validation**")
        st.json(findings.get("validation"))
        st.markdown("**Web Search**")
        st.json(findings.get("web_search"))
        st.markdown("**GitHub Context**")
        st.json(findings.get("github_context"))
        st.markdown("**GitHub Files**")
        for file_item in findings.get("github_files") or []:
            label = file_item.get("path", "file")
            with st.expander(label):
                st.json({k: v for k, v in file_item.items() if k != "content"})
                st.code(file_item.get("content") or "", language="text")
        st.markdown("**Notifications**")
        st.json(findings.get("notifications"))

    with tab_fix:
        st.markdown(workflow.get("fix_proposal") or "No fix proposal recorded.")

    with tab_payload:
        st.json(workflow.get("payload"))


def main() -> None:
    st.title("Sentinal OpsCenter V2")
    st.caption("Autonomous multi-agent SRE workflow dashboard")

    if "api_url" not in st.session_state:
        st.session_state.api_url = DEFAULT_API_URL

    with st.sidebar:
        st.header("Connection")
        st.session_state.api_url = st.text_input("API URL", value=st.session_state.api_url)
        if st.button("Refresh"):
            st.rerun()

    render_status_cards()
    render_trigger_form()

    st.subheader("Recent Workflows")
    try:
        workflows = api_get("/workflows")
    except Exception as exc:
        st.error(f"Unable to load workflows: {exc}")
        return

    if not workflows:
        st.info("No workflows yet.")
        return

    selected_id = st.selectbox(
        "Select workflow",
        options=[workflow["id"] for workflow in workflows],
        format_func=lambda workflow_id: next(
            (
                f"{item['status']} | {item['event_type']} | {workflow_id}"
                for item in workflows
                if item["id"] == workflow_id
            ),
            workflow_id,
        ),
    )
    workflow = api_get(f"/workflows/{selected_id}")
    render_workflow_details(workflow)


if __name__ == "__main__":
    main()
