# your_app/chats/controllers/chat.py

# import os
from flask import Blueprint, render_template, request, jsonify, current_app
# from werkzeug.utils import secure_filename
from utils.logger import get_logger

# Ekstensi file yang diizinkan untuk upload
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


chat_bp = Blueprint("chat", __name__)
logger = get_logger(__name__)


@chat_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@chat_bp.route("/chat", methods=["POST"])
async def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    # Ambil instance MCPClient di sini, dalam aplikasi context
    mcp_client = current_app.extensions["mcp_client"]

    # Pastikan terhubung
    if not mcp_client.is_connected():
        connected = await mcp_client.connect()
        if not connected:
            logger.error("Gagal terhubung ke MCP server sebelum chat")
            return jsonify({"error": "Connection to MCP server failed"}), 500

    try:
        response = await mcp_client.process_query(message)
        return jsonify({"response": response})
    except Exception as e:
        logger.error(f"Error saat memproses chat: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


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
