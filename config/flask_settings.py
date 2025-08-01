import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class FlaskConfig:
    SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'chat_memory.sqlite')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
