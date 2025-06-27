import os
import time
import random
import threading
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# Database simulation
users_db = {
    'admin': {
        'password': generate_password_hash('admin'),
        'first_name': 'Admin',
        'last_name': 'User'
    }
}

tasks_db = defaultdict(dict)
user_configs = defaultdict(dict)
user_logs = defaultdict(list)

# ==================== HTML TEMPLATES ====================
BASE_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>FB Comment Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; background-color: #f8f9fa; }
        .log-entry { padding: 8px; margin: 4px 0; border-radius: 4px; }
        .log-success { background-color: #d4edda; border-left: 4px solid #28a745; }
        .log-error { background-color: #f8d7da; border-left: 4px solid #dc3545; }
        .log-info { background-color: #e2e3e5; border-left: 4px solid #6c757d; }
        #log-container { max-height: 400px; overflow-y: auto; }
        .task-card { margin-bottom: 20px; }
        .form-section { margin-bottom: 30px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
        <div class="container">
            <a class="navbar-brand" href="/">FB Comment Bot</a>
            <div class="navbar-nav">
                <span class="nav-item nav-link">Welcome, {first_name}</span>
                <a class="nav-item nav-link" href="/logout">Logout</a>
            </div>
        </div>
    </nav>
    <div class="container">
        {flashed_messages}
        {content}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    {scripts}
</body>
</html>'''

LOGIN_HTML = '''<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">Login</div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Username</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Login</button>
                </form>
            </div>
        </div>
    </div>
</div>'''

INDEX_HTML = '''<div class="row">
    <div class="col-md-8">
        <div class="card form-section">
            <div class="card-header">Comment Configuration</div>
            <div class="card-body">
                <form method="POST">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">First Name</label>
                            <input type="text" name="first_name" class="form-control" value="{config_first_name}" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Last Name</label>
                            <input type="text" name="last_name" class="form-control" value="{config_last_name}" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Access Tokens (one per line)</label>
                        <textarea name="tokens" class="form-control" rows="3" required>{config_tokens}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Comments (one per line)</label>
                        <textarea name="comments" class="form-control" rows="3" required>{config_comments}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Post IDs (comma separated)</label>
                        <input type="text" name="post_ids" class="form-control" value="{config_post_ids}" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Delay between comments (seconds, min 60)</label>
                        <input type="number" name="delay" class="form-control" value="{config_delay}" min="60" required>
                    </div>
                    <button type="submit" class="btn btn-primary mt-3">Save Configuration</button>
                </form>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">Activity Logs</div>
            <div class="card-body">
                <div id="log-container">
                    {logs_html}
                </div>
            </div>
        </div>
    </div>
</div>
<script>
$(document).ready(function() {{
    setInterval(function() {{
        location.reload();
    }}, 5000);
}});
</script>'''

def add_log(username, message, status='info'):
    user_logs[username].insert(0, {
        'time': time.strftime('%H:%M:%S'),
        'message': message,
        'status': status
    })
    if len(user_logs[username]) > 100:
        user_logs[username].pop()

def render_template(template_name, **context):
    if template_name == 'login.html':
        content = LOGIN_HTML
    elif template_name == 'index.html':
        username = session['username']
        config = user_configs[username]
        logs_html = ''.join(
            f'<div class="log-entry log-{log["status"]}">[{log["time"]}] {log["message"]}</div>'
            for log in user_logs.get(username, [])
        )
        content = INDEX_HTML.format(
            config_first_name=config.get('first_name', ''),
            config_last_name=config.get('last_name', ''),
            config_tokens=config.get('tokens', ''),
            config_comments=config.get('comments', ''),
            config_post_ids=config.get('post_ids', ''),
            config_delay=config.get('delay', 60),
            logs_html=logs_html
        )
    
    flashed_messages = ''.join(
        f'<div class="alert alert-info">{msg}</div>'
        for msg in request.args.getlist('flashed_messages')
    )
    
    return BASE_HTML.format(
        first_name=session.get('first_name', 'User'),
        flashed_messages=flashed_messages,
        content=content,
        scripts=''
    )

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    
    if request.method == 'POST':
        user_configs[username] = {
            'first_name': request.form['first_name'],
            'last_name': request.form['last_name'],
            'tokens': request.form['tokens'],
            'comments': request.form['comments'],
            'post_ids': request.form['post_ids'],
            'delay': request.form['delay']
        }
        session['first_name'] = request.form['first_name']
        return redirect(url_for('index', flashed_messages='Configuration saved successfully'))
    
    if username not in user_configs:
        user_configs[username] = {
            'first_name': '',
            'last_name': '',
            'tokens': '',
            'comments': '',
            'post_ids': '',
            'delay': 60
        }
    
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in users_db and check_password_hash(users_db[username]['password'], password):
            session['username'] = username
            session['first_name'] = users_db[username]['first_name']
            return redirect(url_for('index'))
        
        return redirect(url_for('login', flashed_messages='Invalid username or password'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
