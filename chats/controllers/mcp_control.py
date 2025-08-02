from flask import Blueprint, jsonify, current_app
from utils.logger import get_logger


mcp_control_bp = Blueprint("mcp_control", __name__)
logger = get_logger(__name__)


@mcp_control_bp.route("/connect", methods=["POST"])
async def mcp_connect():
    mcp = current_app.extensions["mcp_client"]
    mcp._auto_reconnect = True  # izinkan reconnect
    ok = await mcp.connect()
    return jsonify({"status": "connected" if ok else "failed"})


@mcp_control_bp.route("/disconnect", methods=["POST"])
async def mcp_disconnect():
    mcp = current_app.extensions["mcp_client"]
    mcp._auto_reconnect = False  # matikan auto‐reconnect
    await mcp.cleanup()
    return jsonify(
        {
            "status": "disconnected",
            "message": "Terima kasih! MCP session telah ditutup.",
        }
    )


@mcp_control_bp.route("/status", methods=["GET"])
def mcp_status():
    mcp = current_app.extensions["mcp_client"]
    return jsonify({"connected": mcp.is_connected()})
