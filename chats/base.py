import os
import logging
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import asyncio  # noqa: F401
from services.mcp_client import MCPClient

# Konfigurasi
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
alLOWED_EXTENSIONS = {"pdf", "docx"}
# MCP_URL = os.getenv("MCP_SERVER_URL")


def create_app():
    # Inisialisasi Flask
    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Inisialisasi MCP Client
    mcp_client = MCPClient()

    # Cek ekstensi file
    def allowed_file(filename):
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in alLOWED_EXTENSIONS
        )

    @app.before_request
    async def connect_mcp():
        if not mcp_client.is_connected():
            success = await mcp_client.connect()
            if not success:
                logger.error("Gagal connect ke MCP Server")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/chat", methods=["POST"])
    async def chat():
        data = request.get_json()
        message = data.get("message")
        if not message:
            return jsonify({"error": "No message provided"}), 400
        # Pastikan terhubung
        if not mcp_client.is_connected():
            await connect_mcp()
        # Proses query
        response = await mcp_client.process_query(message)
        return jsonify({"response": response})

    @app.route("/upload", methods=["POST"])
    async def upload():
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files["file"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)  # type: ignore
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            # Panggil tool MCP untuk ingestor dokumen
            args = {
                "filename": filename,
                "pelanggan": request.form.get("pelanggan"),
                "project": request.form.get("project"),
                "tahun": request.form.get("tahun"),
            }
            try:
                result = await mcp_client.call_tool("add_kak_tor_knowledge", args)
                return jsonify({"status": "success", "ingest": result})
            except Exception as e:
                logger.error(f"Ingest error: {e}")
                return jsonify({"error": str(e)}), 500
        else:
            return jsonify({"error": "Invalid file type"}), 400

    # Error handler
    @app.errorhandler(Exception)
    def handle_exception(e):
        logger.exception("Unhandled exception")
        return jsonify({"error": "Internal Server Error"}), 500

    return app
