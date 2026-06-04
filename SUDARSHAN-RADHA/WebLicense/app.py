import sys
sys.path.insert(0, '/home/user/flask_install')

import os
import json
import hashlib
import datetime
import random
import string
import sqlite3

from flask import (Flask, render_template, request, redirect,
                   url_for, send_file, session, g)

from questions import QUESTIONS, PASS_SCORE, TOTAL, COOLDOWN_DAYS
from license_gen import generate_license

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, 'weblicense.db')
LICENSE_DIR = os.path.join(BASE_DIR, 'licenses')
GCS_AUTH    = os.path.join(BASE_DIR, '..', 'GCS', 'auth.json')

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    os.makedirs(LICENSE_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute('''
        CREATE TABLE IF NOT EXISTS attempts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            name       TEXT NOT NULL,
            score      INTEGER,
            total      INTEGER,
            passed     INTEGER DEFAULT 0,
            taken_at   TEXT,
            license_id INTEGER
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            license_number TEXT UNIQUE,
            attempt_id     INTEGER,
            name           TEXT,
            email          TEXT,
            username       TEXT,
            password_hash  TEXT,
            issued_at      TEXT,
            valid_until    TEXT,
            pdf_path       TEXT
        )
    ''')
    db.commit()
    db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def gen_license_number() -> str:
    today  = datetime.date.today().strftime('%Y%m%d')
    suffix = ''.join(random.choices(string.digits, k=4))
    return f'EA-SUDARSHAN-{today}-{suffix}'


def cooldown_for(email: str, db) -> datetime.datetime | None:
    """Return the datetime the candidate becomes eligible again, or None."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(days=COOLDOWN_DAYS)).isoformat()
    row = db.execute(
        'SELECT taken_at FROM attempts WHERE email=? AND passed=0 AND taken_at > ?'
        ' ORDER BY taken_at DESC LIMIT 1',
        (email, cutoff)
    ).fetchone()
    if row:
        taken = datetime.datetime.fromisoformat(row['taken_at'])
        return taken + datetime.timedelta(days=COOLDOWN_DAYS)
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', pass_score=PASS_SCORE)


@app.route('/test', methods=['POST'])
def start_test():
    email = request.form.get('email', '').strip().lower()
    name  = request.form.get('name', '').strip()
    if not email or not name:
        return render_template('index.html', pass_score=PASS_SCORE,
                               error="Name and email are required.")

    db         = get_db()
    eligible   = cooldown_for(email, db)
    if eligible:
        return render_template('index.html', pass_score=PASS_SCORE,
                               cooldown=True,
                               eligible=eligible.strftime('%d %B %Y at %H:%M UTC'))

    shuffled = random.sample(QUESTIONS, len(QUESTIONS))
    session['email'] = email
    session['name']  = name
    session['qids']  = [q['id'] for q in shuffled]
    return render_template('test.html', questions=shuffled, total=TOTAL)


@app.route('/submit', methods=['POST'])
def submit():
    email = session.get('email')
    name  = session.get('name')
    qids  = session.get('qids')
    if not email or not qids:
        return redirect(url_for('index'))

    q_map = {q['id']: q for q in QUESTIONS}
    score = sum(
        1 for qid in qids
        if (ans := request.form.get(f'q{qid}')) is not None
        and int(ans) == q_map[qid]['correct']
    )

    passed   = 1 if score >= PASS_SCORE else 0
    taken_at = datetime.datetime.utcnow().isoformat()

    db  = get_db()
    cur = db.execute(
        'INSERT INTO attempts (email, name, score, total, passed, taken_at)'
        ' VALUES (?,?,?,?,?,?)',
        (email, name, score, TOTAL, passed, taken_at)
    )
    attempt_id = cur.lastrowid
    db.commit()

    session.pop('qids', None)
    return redirect(url_for('result', attempt_id=attempt_id))


@app.route('/result/<int:attempt_id>')
def result(attempt_id):
    db  = get_db()
    row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
    if not row:
        return redirect(url_for('index'))
    pct = int(row['score'] / row['total'] * 100)
    return render_template('result.html', attempt=row, pct=pct,
                           pass_score=PASS_SCORE, cooldown_days=COOLDOWN_DAYS)


@app.route('/signup/<int:attempt_id>')
def signup(attempt_id):
    db  = get_db()
    row = db.execute('SELECT * FROM attempts WHERE id=? AND passed=1',
                     (attempt_id,)).fetchone()
    if not row:
        return redirect(url_for('index'))
    lic = db.execute('SELECT id FROM licenses WHERE attempt_id=?',
                     (attempt_id,)).fetchone()
    if lic:
        return redirect(url_for('success', attempt_id=attempt_id))
    return render_template('signup.html', attempt=row)


@app.route('/signup', methods=['POST'])
def do_signup():
    attempt_id = int(request.form.get('attempt_id', 0))
    username   = request.form.get('username', '').strip()
    password   = request.form.get('password', '').strip()
    password2  = request.form.get('password2', '').strip()

    db  = get_db()
    row = db.execute('SELECT * FROM attempts WHERE id=? AND passed=1',
                     (attempt_id,)).fetchone()
    if not row:
        return redirect(url_for('index'))

    errors = []
    if not username or len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if not password or len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if password != password2:
        errors.append("Passwords do not match.")
    if db.execute('SELECT id FROM licenses WHERE username=?',
                  (username,)).fetchone():
        errors.append("That username is already taken — choose another.")

    if errors:
        return render_template('signup.html', attempt=row, errors=errors)

    license_number = gen_license_number()
    issued         = datetime.date.today()
    valid_until    = issued + datetime.timedelta(days=365)
    pdf_name       = f'{license_number}.pdf'
    pdf_path       = os.path.join(LICENSE_DIR, pdf_name)

    generate_license(pdf_path, row['name'], row['email'],
                     row['score'], row['total'],
                     license_number, issued, valid_until)

    pw_hash = sha256(password)

    cur = db.execute(
        'INSERT INTO licenses'
        ' (license_number, attempt_id, name, email, username, password_hash,'
        '  issued_at, valid_until, pdf_path)'
        ' VALUES (?,?,?,?,?,?,?,?,?)',
        (license_number, attempt_id, row['name'], row['email'],
         username, pw_hash, issued.isoformat(), valid_until.isoformat(), pdf_path)
    )
    db.execute('UPDATE attempts SET license_id=? WHERE id=?',
               (cur.lastrowid, attempt_id))
    db.commit()

    # Write credentials to GCS auth.json
    auth_dir = os.path.dirname(os.path.abspath(GCS_AUTH))
    os.makedirs(auth_dir, exist_ok=True)
    with open(GCS_AUTH, 'w') as f:
        json.dump({"username": username, "password_hash": pw_hash}, f, indent=2)

    return redirect(url_for('success', attempt_id=attempt_id))


@app.route('/success/<int:attempt_id>')
def success(attempt_id):
    db  = get_db()
    row = db.execute(
        'SELECT a.id, a.name, a.email, a.score, a.total,'
        '       l.license_number, l.username, l.valid_until'
        ' FROM attempts a JOIN licenses l ON l.attempt_id = a.id'
        ' WHERE a.id=?',
        (attempt_id,)
    ).fetchone()
    if not row:
        return redirect(url_for('index'))
    return render_template('success.html', data=row)


@app.route('/license/<int:attempt_id>.pdf')
def download_license(attempt_id):
    db  = get_db()
    row = db.execute(
        'SELECT pdf_path, license_number FROM licenses WHERE attempt_id=?',
        (attempt_id,)
    ).fetchone()
    if not row or not os.path.exists(row['pdf_path']):
        return "License not found.", 404
    return send_file(row['pdf_path'], as_attachment=True,
                     download_name=f"{row['license_number']}.pdf",
                     mimetype='application/pdf')


@app.route('/admin')
def admin():
    db       = get_db()
    attempts = db.execute(
        'SELECT a.id, a.name, a.email, a.score, a.total, a.passed, a.taken_at,'
        '       l.license_number, l.username'
        ' FROM attempts a LEFT JOIN licenses l ON l.attempt_id = a.id'
        ' ORDER BY a.taken_at DESC'
    ).fetchall()
    total_attempts = len(attempts)
    total_passed   = sum(1 for a in attempts if a['passed'])
    return render_template('admin.html', attempts=attempts,
                           total_attempts=total_attempts,
                           total_passed=total_passed)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
