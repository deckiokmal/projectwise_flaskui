# chats/controllers/ingestion_pipeline.py

import requests
from flask import Blueprint, current_app, request, jsonify
from utils.logger import get_logger


ingestion_bp = Blueprint("ingestion", __name__)
logger = get_logger(__name__)

MCP_UPLOAD_URL = "http://127.0.0.1:5000/api/upload-kak-tor/"
TIMEOUT = 360  # Waktu tunggu response API


CHECK_STATUS_URL = "http://127.0.0.1:5000/api/check-status?job_id="


def check_status(job_id):
    return f"{CHECK_STATUS_URL}{job_id}"


@ingestion_bp.route("/upload-kak-via-flask/", methods=["POST"])
def upload_kak_via_flask():
    # 1. Tangkap metadata & file dari form
    project_name = request.form.get("project_name")
    pelanggan = request.form.get("pelanggan")
    tahun = request.form.get("tahun")
    kak_file = request.files.get("file")

    # Validasi input
    if not all([project_name, pelanggan, tahun, kak_file]):
        return jsonify({"error": "Semua field wajib diisi."}), 400

    # 2. Prepare payload & files untuk MCP
    data = {
        "project_name": project_name,
        "pelanggan": pelanggan,
        "tahun": tahun,
    }
    files = {"file": (kak_file.filename, kak_file.stream, kak_file.mimetype)}  # type: ignore

    # 3. Kirim ke MCP dan tunggu respons berisi job_id
    try:
        resp = requests.post(
            MCP_UPLOAD_URL,
            data=data,
            files=files,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        current_app.logger.exception("Gagal meng_forward ke MCP")
        return jsonify({"error": "Gagal mengirim ke MCP: " + str(e)}), 502

    # 4. Ambil job_id dari JSON response MCP
    mcp_json = resp.json()
    job_id = mcp_json.get("job_id")
    if not job_id:
        return jsonify({"error": "MCP tidak mengembalikan job_id."}), 502

    # 5. Kembalikan job_id dan URL untuk polling status
    return jsonify(
        {
            "job_id": job_id,
            "status_url": f"/proxy-check-status/{job_id}",
            "message": "Upload diterima, polling status ingestion.",
        }
    ), 202


@ingestion_bp.route("/proxy-check-status/<job_id>", methods=["GET"])
def proxy_check_status(job_id):
    try:
        # 1. Panggil MCP Server
        resp = requests.get(check_status(job_id), timeout=TIMEOUT)
        resp.raise_for_status()

        # 2. Parse JSON
        data = resp.json()
        # data sekarang:
        # {
        #   "status": "success",
        #   "message": "KAK berhasil diingest dan diringkas.",
        #   "result": { ... }
        # }

        # 3. Ambil field–field yang Anda butuhkan
        status = data.get("status")
        message = data.get("message")
        result = data.get("result", {})
        summary = result.get("summary")
        summary_file = result.get("summary_file")

        # 4. Kembalikan ke client sesuai format yang diinginkan
        return jsonify(
            {
                "status": status,
                "message": message,
                "summary": summary,
                "summary_location": summary_file,
            }
        ), 200

    except requests.RequestException as e:
        current_app.logger.exception("Gagal mengambil status dari MCP Server")
        return jsonify({"error": f"Gagal fetch status MCP: {e}"}), 502
