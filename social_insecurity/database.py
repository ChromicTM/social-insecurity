"""Provides a SQLite3 database extension for Flask.

This extension provides a simple interface to the SQLite3 database.

Example:
    from flask import Flask
    from social_insecurity.database import SQLite3

    app = Flask(__name__)
    db = SQLite3(app)
"""

from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path
from typing import Any, Optional, cast

from flask import Flask, current_app, g


class SQLite3:
    """Provides a SQLite3 database extension for Flask.

    This class provides a simple interface to the SQLite3 database.
    It also initializes the database if it does not exist yet.

    Example:
        from flask import Flask
        from social_insecurity.database import SQLite3

        app = Flask(__name__)
        db = SQLite3(app)

        # Use the database
        # db.query("SELECT * FROM Users;")
        # db.query("SELECT * FROM Users WHERE id = 1;", one=True)
        # db.query("INSERT INTO Users (name, email) VALUES ('John', 'test@test.net');")
    """

    def __init__(
        self,
        app: Optional[Flask] = None,
        *,
        path: Optional[PathLike | str] = None,
        schema: Optional[PathLike | str] = None,
    ) -> None:
        """Initializes the extension.

        params:
            app: The Flask application to initialize the extension with.
            path (optional): The path to the database file. Is relative to the instance folder.
            schema (optional): The path to the schema file. Is relative to the application root folder.

        """
        if app is not None:
            self.init_app(app, path=path, schema=schema)

    def init_app(
        self,
        app: Flask,
        *,
        path: Optional[PathLike | str] = None,
        schema: Optional[PathLike | str] = None,
    ) -> None:
        """Initializes the extension.

        params:
            app: The Flask application to initialize the extension with.
            path (optional): The path to the database file. Is relative to the instance folder.
            schema (optional): The path to the schema file. Is relative to the application root folder.

        """
        if not hasattr(app, "extensions"):
            app.extensions = {}

        if "sqlite3" not in app.extensions:
            app.extensions["sqlite3"] = self
        else:
            raise RuntimeError("Flask SQLite3 extension already initialized")

        instance_path = Path(app.instance_path)
        database_path = path or app.config.get("SQLITE3_DATABASE_PATH")

        if database_path:
            if ":memory:" in str(database_path):
                self._path = Path(database_path)
            else:
                self._path = instance_path / database_path
        else:
            raise ValueError("No database path provided to SQLite3 extension")

        if not self._path.exists():
            self._path.parent.mkdir(parents=True)

        if schema and not self._path.exists():
            with app.app_context():
                self._init_database(schema)

        app.teardown_appcontext(self._close_connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """Returns the connection to the SQLite3 database."""
        conn = getattr(g, "flask_sqlite3_connection", None)
        if conn is None:
            conn = g.flask_sqlite3_connection = sqlite3.connect(self._path)
            conn.row_factory = sqlite3.Row
        return conn

    def get_user_data(self, username: Optional[str] = None, id: Optional[int] = None) -> Optional[dict]:
        """Returns the user with the given username from the database."""

        response = None

        if id is not None:
            query = "SELECT username, id, first_name, last_name, education, employment, music, movie, nationality, birthday FROM Users WHERE id = ?"
            cursor = self.connection.execute(query, (id,))
            response = cursor.fetchone()
        else:
            query = "SELECT username, id, first_name, last_name, education, employment, music, movie, nationality, birthday FROM Users WHERE username = ?"
            cursor = self.connection.execute(query, (username,))
            response = cursor.fetchone()

        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return None
        
        user = dict(response)

        return user

    def get_user_password(self, username: Optional[str]) -> Optional[str]:
        """Returns the password of the user with the given username from the database."""

        query = "SELECT password FROM Users WHERE username = ?"

        cursor = self.connection.execute(query, (username,))
        response = cursor.fetchone()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return None

        return response[0]

    def get_user_id(self, username: Optional[str]) -> Optional[int]:
        """Returns the id of the user with the given username from the database."""

        query = "SELECT id FROM Users WHERE username = ?"

        cursor = self.connection.execute(query, (username,))
        response = cursor.fetchone()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return None

        return response[0]

    def get_post(self, p_id) -> Optional[dict]:
        query = "SELECT * FROM Posts AS p JOIN Users AS u ON p.u_id = u.id WHERE p.id = ?"

        cursor = self.connection.execute(query, (p_id,))
        response = cursor.fetchone()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return None

        post = dict(response)

        return post

    def get_posts(self, u_id) -> list[dict]:
        query = """
            SELECT p.*, u.*, (SELECT COUNT(*) FROM Comments WHERE p_id = p.id) AS cc
            FROM Posts AS p JOIN Users AS u ON u.id = p.u_id
            WHERE p.u_id IN (SELECT u_id FROM Friends WHERE f_id = ?) OR p.u_id IN (SELECT f_id FROM Friends WHERE u_id = ?) OR p.u_id = ?
            ORDER BY p.creation_time DESC
        """

        cursor = self.connection.execute(query, (u_id, u_id, u_id))
        response = cursor.fetchall()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return []

        posts = [dict(post) for post in response]

        return posts

    def get_comments(self, p_id) -> list[dict]:
        query = """
            SELECT DISTINCT *
            FROM Comments AS c JOIN Users AS u ON c.u_id = u.id
            WHERE c.p_id=?
            ORDER BY c.creation_time DESC
        """

        cursor = self.connection.execute(query, (p_id,))
        response = cursor.fetchall()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return []

        comments = [dict(comment) for comment in response]

        return comments

    def get_friends(self, u_id) -> list[dict]:
        query = "SELECT * FROM Friends WHERE u_id = ?"

        cursor = self.connection.execute(query, (u_id,))
        response = cursor.fetchall()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return []

        friends = [dict(friend) for friend in response]

        return friends

    def get_friend_datas(self, u_id) -> list[dict]:
        query = "SELECT * FROM Friends AS f JOIN Users as u ON f.f_id = u.id WHERE f.u_id = ? AND f.f_id != ?"

        cursor = self.connection.execute(query, (u_id, u_id))
        response = cursor.fetchall()
        cursor.close()
        self.connection.commit()

        if response is None or len(response) == 0:
            return []

        friends = [dict(friend) for friend in response]

        return friends

    def create_user(self, username: Optional[str], first_name: Optional[str], last_name: Optional[str], password: Optional[str]) -> bool:
        """Creates a new user in the database."""

        try:
            query = "INSERT INTO Users (username, first_name, last_name, password) VALUES (?, ?, ?, ?)"

            cursor = self.connection.execute(query, (username, first_name, last_name, password))
            cursor.close()
            self.connection.commit()

            return True

        except sqlite3.Error as e:
            print(e)
            return False

    def create_post(self, u_id, content, image) -> bool:
        try:
            query = "INSERT INTO Posts (u_id, content, image, creation_time) VALUES (?, ?, ?, CURRENT_TIMESTAMP)"

            cursor = self.connection.execute(query, (u_id, content, image))
            cursor.close()
            self.connection.commit()

            return True

        except sqlite3.Error as e:
            print(e)
            return False

    def create_comment(self, p_id, u_id, comment) -> bool:
        try:
            query = "INSERT INTO Comments (p_id, u_id, comment, creation_time) VALUES (?, ?, ?, CURRENT_TIMESTAMP)"

            cursor = self.connection.execute(query, (p_id, u_id, comment))
            cursor.close()
            self.connection.commit()

            return True

        except sqlite3.Error as e:
            print(e)
            return False

    def update_profile(self, username, education, employment, music, movie, nationality, birthday) -> bool:
        try:
            query = "UPDATE Users SET education = ?, employment = ?, music = ?, movie = ?, nationality = ?, birthday = ? WHERE username = ?"

            cursor = self.connection.execute(query, (education, employment, music, movie, nationality, birthday, username))
            cursor.close()
            self.connection.commit()

            return True

        except sqlite3.Error as e:
            print(e)
            return False

    def add_friend(self, u_id, f_id) -> bool:
        try:
            query = "INSERT INTO Friends (u_id, f_id) VALUES (?, ?)"

            cursor = self.connection.execute(query, (u_id, f_id))
            cursor.close()
            self.connection.commit()

            return True

        except sqlite3.Error as e:
            print(e)
            return False

    def _init_database(self, schema: PathLike | str) -> None:
        """Initializes the database with the supplied schema if it does not exist yet."""
        with current_app.open_resource(str(schema), mode="r") as file:
            self.connection.executescript(file.read())
            self.connection.commit()

    def _close_connection(self, exception: Optional[BaseException] = None) -> None:
        """Closes the connection to the database."""
        conn = cast(sqlite3.Connection, getattr(g, "flask_sqlite3_connection", None))
        if conn is not None:
            conn.close()
