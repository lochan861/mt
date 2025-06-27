# app.py — All-in-One Flask + Celery + SQLite Facebook Auto Commenter

import os
import time
import random
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.utils import secure_filename
import requests
from celery import Celery

# Configuration

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Init DB

db = SQLAlchemy(app)

# Celery setup

app.config['CELERY_BROKER_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = app.config['CELERY_BROKER_URL']
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Flask-Login setup

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class TaskStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(100), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    celery_id = db.Column(db.String(100))
    status = db.Column(db.String(20))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Utility functions

def allowed_file(filename):
    return filename.endswith('.txt')

def read_lines(path):
    with open(path, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def validate_token(token):
    try:
        r = requests.get(f'https://graph.facebook.com/me?access_token={token}')
        return r.status_code == 200 and 'name' in r.json()
    except:
        return False

def format_comment(comment, first, last, mention_id=None, mention_name=None):
    name_part = f"{first} {comment} {last}".strip()
    if mention_id and mention_name:
        return f"@[ {mention_id}:{mention_name} ] {name_part}"
    return name_part

# Celery Task

@celery.task(bind=True)
def start_commenting_task(self, user_id, task_id, tokens, comments, post_ids, mention_id, mention_name, delay):
    token_index = 0
    comment_index = 0
    while TaskStatus.query.filter_by(task_id=task_id, user_id=user_id, status="running").first():
        token = tokens[token_index % len(tokens)]
        comment = comments[comment_index % len(comments)]
        post_id = post_ids[comment_index % len(post_ids)]
        msg = format_comment(comment, '', '', mention_id, mention_name)
        try:
            requests.post(
                f'https://graph.facebook.com/{post_id}/comments/',
                data={'message': msg, 'access_token': token}
            )
        except Exception:
            pass
        comment_index += 1
        token_index += 1
        time.sleep(random.randint(delay, delay + 10))

@app.route('/')
@login_required
def dashboard():
    tasks = TaskStatus.query.filter_by(user_id=current_user.id).all()
    return render_template_string(DASHBOARD_TEMPLATE, tasks=tasks)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'warning')
            return redirect(url_for('register'))
        db.session.add(User(email=email, password=password))
        db.session.commit()
        flash('Registered, login now', 'success')
        return redirect(url_for('login'))
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/start', methods=['POST'])
@login_required
def start():
    token_file = request.files['token_file']
    comment_file = request.files['comment_file']
    post_ids = request.form['post_ids'].split(',')
    first = request.form.get('first_name', '').strip()
    last = request.form.get('last_name', '').strip()
    mention_id = request.form.get('mention_id')
    mention_name = request.form.get('mention_name')
    delay = int(request.form.get('delay', 60))

    if not allowed_file(token_file.filename) or not allowed_file(comment_file.filename):
        flash('Only .txt files allowed', 'danger')
        return redirect(url_for('dashboard'))

    token_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(token_file.filename))
    comment_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(comment_file.filename))
    token_file.save(token_path)
    comment_file.save(comment_path)

    tokens = read_lines(token_path)
    comments = read_lines(comment_path)

    task_id = f"task_{int(time.time())}"
    celery_task = start_commenting_task.apply_async(
        args=[current_user.id, task_id, tokens, comments, post_ids, mention_id, mention_name, delay]
    )
    db.session.add(TaskStatus(
        task_id=task_id,
        user_id=current_user.id,
        celery_id=celery_task.id,
        status="running"
    ))
    db.session.commit()

    flash(f'Task started with ID {task_id}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/stop/<task_id>')
@login_required
def stop(task_id):
    task = TaskStatus.query.filter_by(task_id=task_id, user_id=current_user.id).first()
    if task:
        task.status = 'stopped'
        db.session.commit()
        flash(f'Task {task_id} stopped', 'info')
    return redirect(url_for('dashboard'))

LOGIN_TEMPLATE = '''
<form method="POST">
  Email: <input type="text" name="email"><br>
  Password: <input type="password" name="password"><br>
  <input type="submit" value="Login">
</form>
'''

REGISTER_TEMPLATE = '''
<form method="POST">
  Email: <input type="text" name="email"><br>
  Password: <input type="password" name="password"><br>
  <input type="submit" value="Register">
</form>
'''

DASHBOARD_TEMPLATE = '''
<h2>Dashboard</h2>
<form method="POST" action="/start" enctype="multipart/form-data">
  Token File: <input type="file" name="token_file"><br>
  Comment File: <input type="file" name="comment_file"><br>
  Post IDs: <input type="text" name="post_ids"><br>
  First Name: <input type="text" name="first_name"><br>
  Last Name: <input type="text" name="last_name"><br>
  Mention ID: <input type="text" name="mention_id"><br>
  Mention Name: <input type="text" name="mention_name"><br>
  Delay (seconds): <input type="number" name="delay" min="60" value="60"><br>
  <input type="submit" value="Start Task">
</form>

<h3>Your Tasks</h3>
<ul>
{% for t in tasks %}
  <li>{{ t.task_id }} - {{ t.status }} <a href="/stop/{{ t.task_id }}">Stop</a></li>
{% endfor %}
</ul>
'''

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
