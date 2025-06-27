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
                            <input type="text" name="first_name" class="form-control" 
                                   value="{config_first_name}" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Last Name</label>
                            <input type="text" name="last_name" class="form-control" 
                                   value="{config_last_name}" required>
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
                        <input type="text" name="post_ids" class="form-control" 
                               value="{config_post_ids}" required>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">Delay between comments (seconds, min 60)</label>
                        <input type="number" name="delay" class="form-control" 
                               value="{config_delay}" min="60" required>
                    </div>
                    
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" name="enable_mention" 
                               id="enableMention" {mention_checked}>
                        <label class="form-check-label" for="enableMention">Enable Mention</label>
                    </div>
                    
                    <div id="mentionFields" {mention_style}>
                        <div class="row">
                            <div class="col-md-6">
                                <label class="form-label">Mention ID</label>
                                <input type="text" name="mention_id" class="form-control" 
                                       value="{config_mention_id}">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Mention Name</label>
                                <input type="text" name="mention_name" class="form-control" 
                                       value="{config_mention_name}">
                            </div>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn btn-primary mt-3">Save Configuration</button>
                </form>
            </div>
        </div>
        
        <div class="card task-card">
            <div class="card-header">Task Control</div>
            <div class="card-body">
                {tasks_html}
                <a href="/create_task" class="btn btn-primary">Create New Task</a>
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
    $('input[name="enable_mention"]').change(function() {{
        $('#mentionFields').toggle(this.checked);
    }});
    
    // Auto-refresh logs every 5 seconds
    setInterval(function() {{
        location.reload();
    }}, 5000);
}});
</script>'''

# ==================== HELPER FUNCTIONS ====================
def add_log(username, message, status='info'):
    user_logs[username].insert(0, {
        'time': time.strftime('%H:%M:%S'),
        'message': message,
        'status': status
    })
    if len(user_logs[username]) > 100:
        user_logs[username].pop()

def render_template(template, **context):
    """Custom template renderer that handles all templates inline"""
    if template == 'base.html':
        return BASE_HTML.format(
            first_name=session.get('first_name', 'User'),
            flashed_messages=''.join([f'<div class="alert alert-info">{msg}</div>' for msg in request.args.getlist('flashed_messages')]),
            content=context.get('content', ''),
            scripts=context.get('scripts', '')
        )
    elif template == 'login.html':
        return BASE_HTML.format(
            first_name='',
            flashed_messages=''.join([f'<div class="alert alert-info">{msg}</div>' for msg in request.args.getlist('flashed_messages')]),
            content=LOGIN_HTML,
            scripts=''
        )
    elif template == 'index.html':
        username = session['username']
        config = user_configs[username]
        
        # Generate tasks HTML
        tasks_html = ''
        if username in tasks_db:
            for task_id, task in tasks_db[username].items():
                tasks_html += f'''
                <div class="mb-3 p-3 border rounded">
                    <h5>Task {task_id}</h5>
                    <p>Status: <span class="badge bg-{'success' if task['running'] else 'secondary'}">
                        {'Running' if task['running'] else 'Stopped'}
                    </span></p>
                    <div class="btn-group">
                        {'<a href="/stop_task/'+task_id+'" class="btn btn-danger">Stop</a>' if task['running'] else '<a href="/start_task/'+task_id+'" class="btn btn-success">Start</a>'}
                        <a href="/delete_task/{task_id}" class="btn btn-outline-secondary">Delete</a>
                    </div>
                </div>'''
        
        # Generate logs HTML
        logs_html = ''
        for log in user_logs.get(username, []):
            logs_html += f'<div class="log-entry log-{log["status"]}">[{log["time"]}] {log["message"]}</div>'
        
        return BASE_HTML.format(
            first_name=session.get('first_name', 'User'),
            flashed_messages=''.join([f'<div class="alert alert-info">{msg}</div>' for msg in request.args.getlist('flashed_messages')]),
            content=INDEX_HTML.format(
                config_first_name=config.get('first_name', ''),
                config_last_name=config.get('last_name', ''),
                config_tokens=config.get('tokens', ''),
                config_comments=config.get('comments', ''),
                config_post_ids=config.get('post_ids', ''),
                config_delay=config.get('delay', 60),
                config_mention_id=config.get('mention_id', ''),
                config_mention_name=config.get('mention_name', ''),
                mention_checked='checked' if config.get('mention_id') else '',
                mention_style='' if config.get('mention_id') else 'style="display:none"',
                tasks_html=tasks_html,
                logs_html=logs_html
            ),
            scripts=''
        )

# ==================== ROUTES ====================
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    
    if request.method == 'POST':
        # Save configuration
        user_configs[username] = {
            'first_name': request.form['first_name'],
            'last_name': request.form['last_name'],
            'tokens': request.form['tokens'],
            'comments': request.form['comments'],
            'post_ids': request.form['post_ids'],
            'delay': request.form['delay'],
            'mention_id': request.form.get('mention_id', ''),
            'mention_name': request.form.get('mention_name', '')
        }
        session['first_name'] = request.form['first_name']
        return redirect(url_for('index', flashed_messages='Configuration saved successfully'))
    
    # Get default config if not exists
    if username not in user_configs:
        user_configs[username] = {
            'first_name': '',
            'last_name': '',
            'tokens': '',
            'comments': '',
            'post_ids': '',
            'delay': 60,
            'mention_id': '',
            'mention_name': ''
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

@app.route('/create_task')
def create_task():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    task_id = str(int(time.time()))
    tasks_db[username][task_id] = {'running': False}
    return redirect(url_for('index', flashed_messages='New task created'))

@app.route('/start_task/<task_id>')
def start_task(task_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    if task_id in tasks_db[username]:
        if not tasks_db[username][task_id]['running']:
            thread = threading.Thread(target=run_bot, args=(username, task_id))
            thread.daemon = True
            thread.start()
            return redirect(url_for('index', flashed_messages='Task started'))
    
    return redirect(url_for('index'))

@app.route('/stop_task/<task_id>')
def stop_task(task_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    if task_id in tasks_db[username]:
        tasks_db[username][task_id]['running'] = False
        return redirect(url_for('index', flashed_messages='Task stopped'))
    
    return redirect(url_for('index'))

@app.route('/delete_task/<task_id>')
def delete_task(task_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    if task_id in tasks_db[username]:
        tasks_db[username][task_id]['running'] = False
        del tasks_db[username][task_id]
        return redirect(url_for('index', flashed_messages='Task deleted'))
    
    return redirect(url_for('index'))

# ==================== BOT FUNCTION ====================
def run_bot(username, task_id):
    config = user_configs[username]
    tasks_db[username][task_id]['running'] = True
    
    try:
        tokens = [t.strip() for t in config['tokens'].split('\n') if t.strip()]
        comments = [c.strip() for c in config['comments'].split('\n') if c.strip()]
        post_ids = [p.strip() for p in config['post_ids'].split(',') if p.strip()]
        delay = int(config['delay'])
        
        add_log(username, f"Task {task_id} started with {len(tokens)} tokens, {len(comments)} comments, {len(post_ids)} targets", 'info')
        
        while tasks_db[username][task_id]['running']:
            for token in tokens:
                if not tasks_db[username][task_id]['running']:
                    break
                    
                # Validate token
                try:
                    resp = requests.get(f'https://graph.facebook.com/me?access_token={token}', timeout=10)
                    if resp.status_code != 200:
                        add_log(username, f"Invalid token: {token[:10]}...", 'error')
                        continue
                    user_info = resp.json()
                except Exception as e:
                    add_log(username, f"Token validation failed: {str(e)}", 'error')
                    continue
                
                for comment in comments:
                    if not tasks_db[username][task_id]['running']:
                        break
                        
                    for post_id in post_ids:
                        if not tasks_db[username][task_id]['running']:
                            break
                            
                        try:
                            # Format comment
                            full_comment = f"{config['first_name']} {comment} {config['last_name']}"
                            if config.get('mention_id'):
                                full_comment = f"@[{config['mention_id']}:{config['mention_name']}] {full_comment}"
                            
                            # Post comment
                            resp = requests.post(
                                f'https://graph.facebook.com/{post_id}/comments',
                                data={'message': full_comment, 'access_token': token},
                                timeout=10
                            )
                            
                            if resp.status_code == 200:
                                add_log(username, f"Posted to {post_id}: {full_comment[:50]}...", 'success')
                            else:
                                error = resp.json().get('error', {}).get('message', 'Unknown error')
                                add_log(username, f"Failed on {post_id}: {error}", 'error')
                            
                            # Random delay
                            sleep_time = random.randint(delay, delay + 30)
                            for _ in range(sleep_time):
                                if not tasks_db[username][task_id]['running']:
                                    break
                                time.sleep(1)
                                
                        except Exception as e:
                            add_log(username, f"Error: {str(e)}", 'error')
                            time.sleep(10)
            
            add_log(username, f"Task {task_id} completed one full cycle", 'info')
    
    except Exception as e:
        add_log(username, f"Task {task_id} crashed: {str(e)}", 'error')
    finally:
        tasks_db[username][task_id]['running'] = False
        add_log(username, f"Task {task_id} stopped", 'info')

# ==================== MAIN ====================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
