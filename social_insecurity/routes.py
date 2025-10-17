"""Provides all routes for the Social Insecurity application.

This file contains the routes for the application. It is imported by the social_insecurity package.
It also contains the SQL queries used for communicating with the database.
"""

from pathlib import Path

from flask import current_app as app, session, request
from flask import flash, jsonify, redirect, render_template, send_from_directory, url_for
import time

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from social_insecurity import Config, sqlite
from social_insecurity.forms import CommentsForm, FriendsForm, IndexForm, PostForm, ProfileForm

from typing import Optional

last_post_times = {}
upload_history = {}
login_attempts = {}

def is_logged_in() -> bool:
    """Checks if the user is logged in.
    
    Returns:
        out (bool): True if logged in, False otherwise.
    """
    return "user_id" in session

def get_current_user_data() -> Optional[dict]:
    """Returns the current user's data from the database.

    Returns:
        out (dict): The user's data.
    """
    return sqlite.get_user_data(id=session["user_id"])

@app.before_request
def rate_limit_post_requests():
    if request.method != "POST":
        return
    
    if is_logged_in():
        user_id = session["user_id"]
    else:
        user_id = request.remote_addr
    
    now = time.time() * 1000
    last_time = last_post_times.get(user_id, 0)
    if now - last_time < app.config["COOLDOWN_MS"]:
        wait_time = int(app.config["COOLDOWN_MS"] - (now - last_time))
        return jsonify({
            "error": f"Rate limit: wait {wait_time}ms before next POST."
        }), 429
    last_post_times[user_id] = now

@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    """Provides the index page for the application.

    It reads the composite IndexForm and based on which form was submitted,
    it either logs the user in or registers a new user.

    If no form was submitted, it simply renders the index page.
    """
    if is_logged_in():
        user = get_current_user_data()

        if user is None:
            return redirect(url_for("logout"))
        
        return redirect(url_for("stream", username=user["username"]))
    
    index_form = IndexForm()
    login_form = index_form.login
    register_form = index_form.register

    if login_form.is_submitted() and login_form.submit.data:
        if not login_form.username.data or not login_form.password.data:
            flash("Please fill out all fields!", category="warning")
            return redirect(url_for("index"))

        user_password = sqlite.get_user_password(login_form.username.data)
        user_id = sqlite.get_user_id(login_form.username.data)

        if user_password is None:
            flash("Wrong username or password!", category="warning")
        elif login_attempts.get(login_form.username.data, {}).get("attempts", 0) >= app.config["MAX_LOGIN_ATTEMPTS"]:
            if login_attempts[login_form.username.data]["last_attempt"] < time.time() + app.config["LOGIN_COOLDOWN"]:
                flash("Too many login attempts, please try again later.", category="danger")
            else:
                login_attempts[login_form.username.data] = {
                    "attempts": 0,
                    "last_attempt": 0
                }
        elif not check_password_hash(user_password, login_form.password.data):
            flash("Wrong username or password!", category="warning")
        else:
            session["user_id"] = user_id     # Store the user's ID in the session
            return redirect(url_for("stream", username=login_form.username.data))

    elif register_form.is_submitted() and register_form.submit.data:
        if not register_form.username.data or not register_form.password.data or not register_form.first_name.data or not register_form.last_name.data:
            flash("Please fill out all fields!", category="warning")
            return redirect(url_for("index"))

        pw_hash = generate_password_hash(register_form.password.data)
        ok = sqlite.create_user(register_form.username.data, register_form.first_name.data, register_form.last_name.data, pw_hash)

        if not ok:
            flash("Failed to create user!", category="warning")
            return redirect(url_for("index"))
        
        flash("User successfully created!", category="success")
        return redirect(url_for("index"))

    return render_template("index.html", title="Welcome", form=index_form)


@app.route("/stream/<string:username>", methods=["GET", "POST"])
def stream(username: str):
    """Provides the stream page for the application.

    If a form was submitted, it reads the form data and inserts a new post into the database.

    Otherwise, it reads the username from the URL and displays all posts from the user and their friends.
    """

    if not is_logged_in():
        return redirect(url_for("index"))

    post_form = PostForm()
    user = sqlite.get_user_data(username)

    if user is None or session["user_id"] != user["id"]:
        user_data = get_current_user_data()

        if user_data is None:
            return redirect(url_for("index"))

        return redirect(url_for("stream", username=user_data["username"]))

    if post_form.is_submitted():

        filename = secure_filename(post_form.image.data.filename)

        extension = Path(filename).suffix
        if filename and extension not in app.config["ALLOWED_EXTENSIONS"]:
            flash("Illegal file extension", category="warning")
            return redirect(url_for("stream", username=username))

        if post_form.image.data:
            user_id = session["user_id"]
            now = time.time()
            
            timestamps = upload_history.get(user_id, [])
            timestamps = [t for t in timestamps if now - t < app.config["UPLOAD_WINDOW"]]
            upload_limit = app.config["UPLOAD_LIMIT"]
            if len(timestamps) >= upload_limit:
                return jsonify({
                    "error": "Too many uploads",
                    "message": f"Limit is {upload_limit} uploads per {upload_limit} seconds."
                }), 429
            timestamps.append(now)
            upload_history[user_id] = timestamps
            
            path = Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"] / filename
            post_form.image.data.save(path)

        ok = sqlite.create_post(user["id"], post_form.content.data, filename)

        if not ok:
            flash("Failed to create post!", category="warning")

        return redirect(url_for("stream", username=username))

    posts = sqlite.get_posts(user["id"])
    return render_template("stream.html", title="Stream", username=username, form=post_form, posts=posts)


@app.route("/comments/<string:username>/<int:post_id>", methods=["GET", "POST"])
def comments(username: str, post_id: int):
    """Provides the comments page for the application.

    If a form was submitted, it reads the form data and inserts a new comment into the database.

    Otherwise, it reads the username and post id from the URL and displays all comments for the post.
    """
    if not is_logged_in():
        return redirect(url_for("index"))

    comments_form = CommentsForm()
    user = sqlite.get_user_data(username)

    if user is None or session["user_id"] != user["id"]:
        user_data = get_current_user_data()

        if user_data is None:
            return redirect(url_for("index"))

        return redirect(url_for("stream", username=user_data["username"]))

    if comments_form.is_submitted():
        sqlite.create_comment(post_id, user["id"], comments_form.comment.data)

    post = sqlite.get_post(post_id)
    comments = sqlite.get_comments(post_id)
    return render_template(
        "comments.html", title="Comments", username=username, form=comments_form, post=post, comments=comments
    )


@app.route("/friends/<string:username>", methods=["GET", "POST"])
def friends(username: str):
    """Provides the friends page for the application.

    If a form was submitted, it reads the form data and inserts a new friend into the database.

    Otherwise, it reads the username from the URL and displays all friends of the user.
    """

    if not is_logged_in():
        return redirect(url_for("index"))

    friends_form = FriendsForm()
    user = sqlite.get_user_data(username)

    if user is None or session["user_id"] != user["id"]:
        user_data = get_current_user_data()

        if user_data is None:
            return redirect(url_for("index"))

        return redirect(url_for("friends", username=user_data["username"]))

    if friends_form.is_submitted():
        friend = sqlite.get_user_data(friends_form.username.data)
        friends = sqlite.get_friends(user["id"])

        if friend is None:
            flash("User does not exist!", category="warning")
        elif friend["id"] == user["id"]:
            flash("You cannot be friends with yourself!", category="warning")
        elif friend["id"] in [friend["f_id"] for friend in friends]:
            flash("You are already friends with this user!", category="warning")
        else:
            ok = sqlite.add_friend(user["id"], friend["id"])

            if not ok:
                flash("Failed to add friend!", category="warning")
                return redirect(url_for("friends", username=username))

            flash("Friend successfully added!", category="success")

    friends = sqlite.get_friend_datas(user["id"])
    return render_template("friends.html", title="Friends", username=username, friends=friends, form=friends_form)


@app.route("/profile/<string:username>", methods=["GET", "POST"])
def profile(username: str):
    """Provides the profile page for the application.

    If a form was submitted, it reads the form data and updates the user's profile in the database.

    Otherwise, it reads the username from the URL and displays the user's profile.
    """

    if not is_logged_in():
        return redirect(url_for("index"))

    profile_form = ProfileForm()
    user = sqlite.get_user_data(username)

    if user is None:
        return redirect(url_for("index"))
    
    is_current_user = session["user_id"] == user["id"]

    if profile_form.is_submitted() and is_current_user:
        ok = sqlite.update_profile(username, profile_form.education.data, profile_form.employment.data, profile_form.music.data, profile_form.movie.data, profile_form.nationality.data, profile_form.birthday.data)
        
        if not ok:
            flash("Failed to update profile!", category="warning")
            return redirect(url_for("profile", username=username))
        
        return redirect(url_for("profile", username=username))

    return render_template("profile.html", title="Profile", username=username, user=user, form=profile_form, show_edit=is_current_user)


@app.route("/uploads/<string:filename>")
def uploads(filename):
    """Provides an endpoint for serving uploaded files."""
    return send_from_directory(Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"], filename)


@app.route("/logout")
def logout():
    """Logs the user out of the application."""
    session.clear()
    return redirect(url_for("index"))
