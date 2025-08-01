# your_app/chat/base.py

from flask import Flask
# from flask_sqlalchemy import SQLAlchemy
from utils.logger import get_logger
from chats.controllers.chat import chat_bp, mcp_control_bp
from services.mcp_client import MCPClient
from config.mcp_settings import MCPSettings
# from config.flask_settings import FlaskConfig


# db = SQLAlchemy()


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    if config_object:
        app.config.from_object(config_object)

    logger = get_logger(app.import_name)
    logger.info("Logger aplikasi diinisialisasi")

    # Inisialisasi MCPClient
    mcp_set = MCPSettings()
    model_name = app.config.get(mcp_set.llm_model, "gpt-4o")
    mcp = MCPClient(model=model_name)
    app.extensions["mcp_client"] = mcp
    logger.info("MCPClient instance created")

    # Init DB
    # db.init_app(app)
    # with app.app_context():
    #     db.create_all()

    # Register blueprints
    app.register_blueprint(chat_bp)
    app.register_blueprint(mcp_control_bp)
    logger.info("Blueprints registered: chat, mcp_control")

    @app.before_request
    async def initial_connect_async():
        ok = await mcp.connect()
        logger.info("Connected" if ok else "Connect failed")

    return app
