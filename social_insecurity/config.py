"""Provides the configuration for the Social Insecurity application.

This file is used to set the configuration for the application.

Example:
    from flask import Flask
    from social_insecurity.config import Config

    app = Flask(__name__)
    app.config.from_object(Config)

    # Use the configuration
    secret_key = app.config["SECRET_KEY"]
"""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "FK0kZokVorHtu29BfrT7JuQuljKFqAcH"  # TODO: Use this with wtforms
    SQLITE3_DATABASE_PATH = "sqlite3.db"  # Path relative to the Flask instance folder
    UPLOADS_FOLDER_PATH = "uploads"  # Path relative to the Flask instance folder
    ALLOWED_EXTENSIONS = {".jpeg", ".jpg", ".gif", ".png", ".webp"}
    WTF_CSRF_ENABLED = False  # TODO: I should probably implement this wtforms feature, but it's not a priority
    COOLDOWN_MS = 1000
    UPLOAD_LIMIT = 5
    UPLOAD_WINDOW = 60
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_COOLDOWN = 3600 # 1 hour
    MAX_CONTENT_LENGTH = 1024 * 1024 # 1 MB