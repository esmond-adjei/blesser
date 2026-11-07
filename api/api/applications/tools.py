from api.agent.tools.context import ToolContext
from api.applications import notes as application_notes
from api.applications import schemas as application_schemas
from api.applications import service as application_service


async def handle_save_application(tool_input: dict, ctx: ToolContext) -> dict:
    """Index a researched graduate application into the student's tracker.

    The research agent (metered) gets one save per task and may only create rows or
    fill rows it created (source=agent): a page it read must not plant links or
    notes in a student's entry. User-approved Gradis saves keep the full upsert.
    """
    agent = getattr(ctx, "metered", True)
    if agent and getattr(ctx, "applications_saved", 0) >= 1:
        return {
            "error": (
                "Application budget reached: one save_application per task. "
                "Write your final summary instead."
            )
        }
    format_error = application_notes.verify_application_notes(tool_input)
    if format_error is not None:
        return {"error": format_error}
    data = application_schemas.AgentApplicationIn(**tool_input)
    app, created, updated = await application_service.upsert_for_agent(
        ctx.session, ctx.user_id, ctx.run.id, data, agent_rows_only=agent
    )
    if agent:
        ctx.applications_saved = getattr(ctx, "applications_saved", 0) + 1
    return {
        "application_id": app["id"],
        "created": created,
        "updated_fields": updated,
    }
