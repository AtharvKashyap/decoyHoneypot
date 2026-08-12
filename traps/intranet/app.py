"""Fake internal portal for the AI Deception Grid.

A believable "Meridian Logistics Intranet" login/landing page. This is a
cosmetic decoy only: it does not authenticate anyone against anything real,
and no credentials submitted here are stored or forwarded anywhere. It exists
to make the deception network feel like a real small-business intranet to
anyone who stumbles onto it.
"""

from __future__ import annotations

from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)

LOGIN_PAGE = """
<!doctype html>
<html>
<head>
  <title>Meridian Logistics &mdash; Intranet</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; background: #f4f6f8; margin: 0; }
    .header { background: #0b3d63; color: white; padding: 18px 32px; font-size: 20px; }
    .card { max-width: 360px; margin: 60px auto; background: white; padding: 32px;
            border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
    h2 { margin-top: 0; color: #0b3d63; }
    label { display: block; margin-top: 14px; font-size: 13px; color: #333; }
    input { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box;
            border: 1px solid #ccc; border-radius: 4px; }
    button { margin-top: 20px; width: 100%; padding: 10px; background: #0b3d63;
             color: white; border: none; border-radius: 4px; cursor: pointer; }
    .footer { text-align: center; color: #999; font-size: 12px; margin-top: 40px; }
  </style>
</head>
<body>
  <div class="header">Meridian Logistics &mdash; Employee Intranet</div>
  <div class="card">
    <h2>Sign in</h2>
    <form method="post" action="{{ url_for('login') }}">
      <label>Username</label>
      <input type="text" name="username" autofocus>
      <label>Password</label>
      <input type="password" name="password">
      <button type="submit">Sign in</button>
    </form>
  </div>
  <div class="footer">Meridian Logistics Intranet &copy; 2026 &mdash; Internal use only</div>
</body>
</html>
"""

LANDING_PAGE = """
<!doctype html>
<html>
<head>
  <title>Meridian Logistics &mdash; Home</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; background: #f4f6f8; margin: 0; }
    .header { background: #0b3d63; color: white; padding: 18px 32px; font-size: 20px; }
    .content { max-width: 700px; margin: 40px auto; background: white; padding: 32px;
               border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
    ul { line-height: 1.8; }
    a { color: #0b3d63; }
  </style>
</head>
<body>
  <div class="header">Meridian Logistics &mdash; Employee Intranet</div>
  <div class="content">
    <h2>Welcome back</h2>
    <p>Quick links:</p>
    <ul>
      <li><a href="#">Finance &mdash; vendor payments &amp; forecasts</a></li>
      <li><a href="#">IT &mdash; server inventory &amp; helpdesk</a></li>
      <li><a href="#">HR &mdash; org chart &amp; payroll</a></li>
      <li><a href="\\\\fileserver\\company">File share (\\\\fileserver\\company)</a></li>
    </ul>
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(LOGIN_PAGE)


@app.route("/login", methods=["POST"])
def login():
    # Cosmetic only: no credential is validated or persisted. This is a
    # decoy landing page, not a real auth flow.
    request.form.get("username", "")
    return redirect(url_for("home"))


@app.route("/home", methods=["GET"])
def home():
    return render_template_string(LANDING_PAGE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
