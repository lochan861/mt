from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
import requests
import time
import random
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ====== Utility Functions =======
def validate_token(token):
    try:
        response = requests.get(f'https://graph.facebook.com/me?access_token={token}')
        data = response.json()
        if response.status_code == 200 and "name" in data:
            return "profile", data.get("name")
        return None, None
    except:
        return None, None

def post_comment(post_id, comment, token, mention_id=None, mention_name=None):
    if mention_id and mention_name:
        comment = f"@[{mention_id}:{mention_name}] {comment}"
    try:
        response = requests.post(
            f'https://graph.facebook.com/{post_id}/comments/',
            data={'message': comment, 'access_token': token},
            timeout=10
        )
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def read_file_lines(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

# ====== HTML Templates =======
index_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>MENTION-POST</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
</head>
<body class="bg-light">
  <div class="container mt-5">
    <div class="card shadow">
      <div class="card-header bg-primary text-white">
        <h4>Facebook Comment Poster</h4>
      </div>
      <div class="card-body">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <form method="POST" enctype="multipart/form-data">
          <div class="mb-3">
            <label class="form-label">Access Token File (.txt)</label>
            <input type="file" name="token_file" class="form-control" accept=".txt" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Comments File (.txt)</label>
            <input type="file" name="comment_file" class="form-control" accept=".txt" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Post IDs (comma-separated)</label>
            <input type="text" name="post_ids" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Mention ID (optional)</label>
            <input type="text" name="mention_id" class="form-control">
          </div>
          <div class="mb-3">
            <label class="form-label">Mention Name (optional)</label>
            <input type="text" name="mention_name" class="form-control">
          </div>
          <div class="mb-3">
            <label class="form-label">Delay (seconds, default 60)</label>
            <input type="number" name="delay" class="form-control" min="60" value="60">
          </div>
          <button type="submit" class="btn btn-success">Start Commenting</button>
        </form>
      </div>
    </div>
  </div>
</body>
</html>
'''

result_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Results</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
</head>
<body class="bg-light">
  <div class="container mt-5">
    <div class="card shadow">
      <div class="card-header bg-success text-white">
        <h4>Results</h4>
      </div>
      <div class="card-body">
        {% for r in results %}
          <div class="border p-3 mb-2">
            <strong>Post ID:</strong> {{ r.post_id }}<br>
            <strong>Comment:</strong> {{ r.comment }}<br>
            <strong>Result:</strong> {{ r.result | tojson(indent=2) }}
          </div>
        {% endfor %}
        <a href="/" class="btn btn-primary">Back</a>
      </div>
    </div>
  </div>
</body>
</html>
'''

# ====== Routes =======
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        token_file = request.files.get('token_file')
        comment_file = request.files.get('comment_file')

        if not token_file or not comment_file:
            flash("Both token and comment files are required.", "danger")
            return redirect(url_for('index'))

        token_path = os.path.join(app.config['UPLOAD_FOLDER'], token_file.filename)
        comment_path = os.path.join(app.config['UPLOAD_FOLDER'], comment_file.filename)
        token_file.save(token_path)
        comment_file.save(comment_path)

        tokens = read_file_lines(token_path)
        comments = read_file_lines(comment_path)
        post_ids = request.form.get('post_ids').strip().split(',')
        mention_id = request.form.get('mention_id').strip()
        mention_name = request.form.get('mention_name').strip()
        delay = int(request.form.get('delay') or 60)

        valid_tokens = []
        for token in tokens:
            profile_type, profile_name = validate_token(token)
            if profile_name:
                valid_tokens.append((token, profile_name))

        if not valid_tokens:
            flash("No valid tokens found.", "danger")
            return redirect(url_for('index'))

        results = []
        comment_index = 0
        token_index = 0

        while comment_index < len(comments):
            token, profile_name = valid_tokens[token_index % len(valid_tokens)]
            comment = comments[comment_index % len(comments)]
            post_id = post_ids[comment_index % len(post_ids)]

            result = post_comment(post_id, comment, token, mention_id, mention_name)
            results.append({"post_id": post_id, "comment": comment, "result": result})

            comment_index += 1
            token_index += 1
            time.sleep(random.randint(delay, delay + 10))

        return render_template_string(result_template, results=results)

    return render_template_string(index_template)

@app.route('/test-token', methods=['GET'])
def test_token():
    token = request.args.get('token')
    profile_type, name = validate_token(token)
    return jsonify({"valid": bool(name), "name": name or ""})

# ====== Run =======
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
