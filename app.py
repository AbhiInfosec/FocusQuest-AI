from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, json, random
from datetime import datetime, date, timedelta
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'focusquest2024')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'instance', 'focusquest.db')

# ── Groq AI Setup ──────────────────────────────────────────────────────────────
GROQ_KEY = os.environ.get('GROQ_API_KEY', '')
AI_OK = False
groq_client = None

try:
    from groq import Groq
    if GROQ_KEY:
        groq_client = Groq(api_key=GROQ_KEY)
        AI_OK = True
        print(f'[AI] Groq connected OK')
    else:
        print('[AI] No GROQ_API_KEY in .env')
except Exception as e:
    print(f'[AI] Groq error: {e}')

def ask_ai(prompt, fallback=''):
    if not AI_OK or not groq_client:
        return fallback
    try:
        response = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f'[AI] Error: {e}')
        return fallback

def parse_json(text):
    if not text: return None
    text = text.strip()
    if '```' in text:
        for part in text.split('```'):
            part = part.strip().lstrip('json').strip()
            if part.startswith(('[', '{')): text = part; break
    try: return json.loads(text)
    except: return None

# ── DB ──────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as db:
        db.executescript(open(os.path.join(BASE_DIR, 'schema.sql')).read())
        db.commit()

# ── Auth decorators ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'uid' not in session: return redirect(url_for('login'))
        return f(*a, **kw)
    return dec

def api_auth(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'uid' not in session: return jsonify({'error': 'Not authenticated'}), 401
        return f(*a, **kw)
    return dec

# ── XP & Levels ─────────────────────────────────────────────────────────────────
LEVELS = [
    (0,'Cadet'),(300,'Explorer'),(700,'Scout'),(1200,'Navigator'),
    (2000,'Pilot'),(3200,'Commander'),(5000,'Captain'),(7500,'Admiral'),
    (11000,'Fleet Admiral'),(15000,'Galactic Master'),(20000,'Universe Champion')
]
BADGES = {
    'first_topic':  {'name':'First Launch',   'icon':'🚀','desc':'Complete your first topic'},
    'streak_3':     {'name':'Orbit Lock',      'icon':'🔥','desc':'3-day streak'},
    'streak_7':     {'name':'Week Warrior',    'icon':'⚡','desc':'7-day streak'},
    'streak_30':    {'name':'Galaxy Master',   'icon':'💎','desc':'30-day streak'},
    'xp_500':       {'name':'Star Hunter',     'icon':'⭐','desc':'Earn 500 XP'},
    'xp_2000':      {'name':'Nova Legend',     'icon':'🏆','desc':'Earn 2000 XP'},
    'quiz_ace':     {'name':'Quiz Ace',        'icon':'🧠','desc':'Pass 10 quizzes'},
    'night_owl':    {'name':'Night Owl',       'icon':'🦉','desc':'Study after 10 PM'},
    'subject_5':    {'name':'Multi-Tasker',    'icon':'📚','desc':'Add 5 subjects'},
    'speed_5':      {'name':'Speed Demon',     'icon':'💨','desc':'Score 5+ in Speed Quiz'},
    'ai_user':      {'name':'AI Scholar',      'icon':'🤖','desc':'Use Study AI feature'},
    'daily_champ':  {'name':'Daily Champion',  'icon':'🎖️','desc':'Complete daily challenge'},
}

def calc_level(xp):
    lvl, name = 1, 'Cadet'
    for i, (t, n) in enumerate(LEVELS):
        if xp >= t: lvl, name = i+1, n
    return lvl, name

def level_info(xp):
    lvl, name = calc_level(xp)
    ct = LEVELS[lvl-1][0]
    nt = LEVELS[lvl][0] if lvl < len(LEVELS) else LEVELS[-1][0]
    pct = min(100, round((xp-ct)/max(1,nt-ct)*100))
    return {'level':lvl,'name':name,'xp':xp,'next_xp':nt,'current_xp':ct,'progress':pct,'xp_needed':max(0,nt-xp)}

def award_xp(db, uid, amount):
    db.execute('UPDATE user_stats SET xp=xp+? WHERE user_id=?', (amount, uid))
    row = db.execute('SELECT xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if row:
        lvl, _ = calc_level(row['xp'])
        db.execute('UPDATE user_stats SET level=? WHERE user_id=?', (lvl, uid))

def update_streak(db, uid):
    today = date.today().isoformat()
    yesterday = (date.today()-timedelta(days=1)).isoformat()
    s = db.execute('SELECT streak,last_study_date FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if not s or s['last_study_date'] == today: return
    new_streak = (s['streak']+1) if s['last_study_date'] == yesterday else 1
    db.execute('UPDATE user_stats SET streak=?,last_study_date=? WHERE user_id=?', (new_streak, today, uid))
    award_xp(db, uid, 20)

def check_badges(db, uid):
    s = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if not s: return []
    earned = json.loads(s['badges'] or '[]')
    new_b = []
    tc = db.execute('SELECT COUNT(*) c FROM topics WHERE user_id=? AND completed=1', (uid,)).fetchone()['c']
    qc = db.execute('SELECT COUNT(*) c FROM quiz_results WHERE user_id=? AND passed=1', (uid,)).fetchone()['c']
    sc = db.execute('SELECT COUNT(*) c FROM subjects WHERE user_id=?', (uid,)).fetchone()['c']
    hr = datetime.now().hour
    checks = [
        ('first_topic', tc >= 1), ('streak_3', s['streak'] >= 3),
        ('streak_7', s['streak'] >= 7), ('streak_30', s['streak'] >= 30),
        ('xp_500', s['xp'] >= 500), ('xp_2000', s['xp'] >= 2000),
        ('quiz_ace', qc >= 10), ('subject_5', sc >= 5),
        ('night_owl', hr >= 22 and tc > 0),
    ]
    for key, cond in checks:
        if cond and key not in earned:
            earned.append(key); new_b.append(key)
    db.execute('UPDATE user_stats SET badges=? WHERE user_id=?', (json.dumps(earned), uid))
    return new_b

# ── Pages ───────────────────────────────────────────────────────────────────────
@app.route('/')
def index(): return redirect(url_for('dashboard') if 'uid' in session else url_for('login'))

@app.route('/login')
def login(): return redirect(url_for('dashboard')) if 'uid' in session else render_template('login.html')

@app.route('/register')
def register(): return redirect(url_for('dashboard')) if 'uid' in session else render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard(): return render_template('dashboard.html')

@app.route('/daily')
@login_required
def daily(): return render_template('daily.html')

@app.route('/exam')
@login_required
def exam(): return render_template('exam.html')

@app.route('/timer/<int:tid>')
@login_required
def timer(tid): return render_template('timer.html', topic_id=tid)

@app.route('/analytics')
@login_required
def analytics(): return render_template('analytics.html')

@app.route('/coach')
@login_required
def coach(): return render_template('coach.html')

@app.route('/badges')
@login_required
def badges(): return render_template('badges.html')

@app.route('/leaderboard')
@login_required
def leaderboard(): return render_template('leaderboard.html')

@app.route('/profile')
@login_required
def profile(): return render_template('profile.html')

@app.route('/notes')
@login_required
def notes(): return render_template('notes.html')

@app.route('/games')
@login_required
def games(): return render_template('games.html')

@app.route('/study-ai')
@login_required
def study_ai(): return render_template('study_ai.html')

@app.route('/flashcards')
@login_required
def flashcards_page(): return render_template('flashcards.html')

@app.route('/speed-quiz')
@login_required
def speed_quiz_page(): return render_template('speed_quiz.html')

# ── Auth API ────────────────────────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def api_register():
    d = request.json
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip().lower()
    pw = d.get('password', '')
    if not name or not email or not pw: return jsonify({'error': 'All fields required'}), 400
    if len(pw) < 6: return jsonify({'error': 'Password min 6 characters'}), 400
    with get_db() as db:
        if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
            return jsonify({'error': 'Email already registered'}), 409
        cur = db.execute('INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)',
                         (name, email, generate_password_hash(pw), datetime.now().isoformat()))
        uid = cur.lastrowid
        db.execute('INSERT INTO user_stats(user_id) VALUES(?)', (uid,))
        db.commit()
    session['uid'] = uid; session['uname'] = name
    return jsonify({'success': True, 'name': name})

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    d = request.json
    email = (d.get('email') or '').strip().lower()
    pw = d.get('password', '')
    with get_db() as db:
        u = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not u or not check_password_hash(u['password_hash'], pw):
        return jsonify({'error': 'Invalid email or password'}), 401
    session['uid'] = u['id']; session['uname'] = u['name']
    return jsonify({'success': True, 'name': u['name']})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout(): session.clear(); return jsonify({'success': True})

@app.route('/api/auth/me')
@api_auth
def api_me():
    with get_db() as db:
        u = db.execute('SELECT id,name,email FROM users WHERE id=?', (session['uid'],)).fetchone()
        s = db.execute('SELECT * FROM user_stats WHERE user_id=?', (session['uid'],)).fetchone()
    if not u: return jsonify({'error': 'Not found'}), 404
    xp = s['xp'] if s else 0
    li = level_info(xp)
    return jsonify({**dict(u), 'xp': xp, 'level': s['level'] if s else 1,
                    'streak': s['streak'] if s else 0,
                    'total_hours': round((s['total_minutes'] or 0)/60, 1) if s else 0,
                    'level_name': li['name'], 'level_info': li,
                    'badges': json.loads(s['badges'] or '[]') if s else []})

# ── Subjects API ────────────────────────────────────────────────────────────────
@app.route('/api/subjects', methods=['GET', 'POST'])
@api_auth
def subjects_api():
    uid = session['uid']
    if request.method == 'GET':
        with get_db() as db:
            rows = db.execute('SELECT * FROM subjects WHERE user_id=? ORDER BY created_at DESC', (uid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.json
    name = (d.get('name') or '').strip()
    color = d.get('color', '#6366f1')
    if not name: return jsonify({'error': 'Name required'}), 400
    with get_db() as db:
        cur = db.execute('INSERT INTO subjects(user_id,name,color,created_at) VALUES(?,?,?,?)',
                         (uid, name, color, datetime.now().isoformat()))
        db.commit()
        check_badges(db, uid); db.commit()
    return jsonify({'id': cur.lastrowid, 'name': name, 'color': color})

@app.route('/api/subjects/<int:sid>', methods=['DELETE'])
@api_auth
def del_subject(sid):
    with get_db() as db:
        db.execute('DELETE FROM subjects WHERE id=? AND user_id=?', (sid, session['uid'])); db.commit()
    return jsonify({'success': True})

# ── Topics API ──────────────────────────────────────────────────────────────────
@app.route('/api/topics', methods=['GET', 'POST'])
@api_auth
def topics_api():
    uid = session['uid']
    if request.method == 'GET':
        date_f = request.args.get('date', date.today().isoformat())
        with get_db() as db:
            rows = db.execute(
                'SELECT t.*,s.name subject_name,s.color subject_color FROM topics t JOIN subjects s ON t.subject_id=s.id WHERE t.user_id=? AND t.study_date=? ORDER BY t.position,t.created_at',
                (uid, date_f)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.json
    name = (d.get('name') or '').strip()
    sid = d.get('subject_id')
    dt = d.get('study_date', date.today().isoformat())
    mins = int(d.get('required_minutes', 20))
    exam_id = d.get('exam_id')
    if not name or not sid: return jsonify({'error': 'Name and subject required'}), 400
    with get_db() as db:
        cur = db.execute(
            'INSERT INTO topics(user_id,subject_id,name,study_date,required_minutes,exam_id,created_at) VALUES(?,?,?,?,?,?,?)',
            (uid, sid, name, dt, mins, exam_id, datetime.now().isoformat()))
        db.commit()
        t = db.execute('SELECT t.*,s.name subject_name,s.color subject_color FROM topics t JOIN subjects s ON t.subject_id=s.id WHERE t.id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(t))

@app.route('/api/topics/reorder', methods=['POST'])
@api_auth
def reorder_topics():
    order = request.json.get('order', [])
    with get_db() as db:
        for i, tid in enumerate(order):
            db.execute('UPDATE topics SET position=? WHERE id=? AND user_id=?', (i, tid, session['uid']))
        db.commit()
    return jsonify({'success': True})

@app.route('/api/topics/<int:tid>/start', methods=['POST'])
@api_auth
def start_timer(tid):
    with get_db() as db:
        t = db.execute('SELECT * FROM topics WHERE id=? AND user_id=?', (tid, session['uid'])).fetchone()
        if not t: return jsonify({'error': 'Not found'}), 404
        if not t['timer_started_at']:
            db.execute('UPDATE topics SET timer_started_at=? WHERE id=?', (datetime.now().isoformat(), tid)); db.commit()
    return jsonify({'success': True, 'required_minutes': t['required_minutes']})

@app.route('/api/topics/<int:tid>/status')
@api_auth
def timer_status(tid):
    with get_db() as db:
        t = db.execute('SELECT t.*,s.name subject_name,s.color subject_color FROM topics t JOIN subjects s ON t.subject_id=s.id WHERE t.id=? AND t.user_id=?', (tid, session['uid'])).fetchone()
    if not t: return jsonify({'error': 'Not found'}), 404
    elapsed = 0; unlocked = False
    if t['timer_started_at']:
        elapsed = (datetime.now()-datetime.fromisoformat(t['timer_started_at'])).total_seconds()/60
        unlocked = elapsed >= t['required_minutes']
    return jsonify({**dict(t), 'elapsed_minutes': round(elapsed, 2), 'unlocked': unlocked})

@app.route('/api/topics/<int:tid>/complete', methods=['POST'])
@api_auth
def complete_topic(tid):
    uid = session['uid']
    with get_db() as db:
        t = db.execute('SELECT * FROM topics WHERE id=? AND user_id=?', (tid, uid)).fetchone()
        if not t: return jsonify({'error': 'Not found'}), 404
        if t['completed']: return jsonify({'error': 'Already completed'}), 400
        if not t['timer_started_at']: return jsonify({'error': 'Start timer first'}), 400
        elapsed = (datetime.now()-datetime.fromisoformat(t['timer_started_at'])).total_seconds()/60
        if elapsed < t['required_minutes']: return jsonify({'error': f'Need more time'}), 400
        db.execute('UPDATE topics SET completed=1,completed_at=? WHERE id=?', (datetime.now().isoformat(), tid))
        db.execute('INSERT INTO study_sessions(user_id,topic_id,subject_id,minutes,session_date,created_at) VALUES(?,?,?,?,?,?)',
                   (uid, tid, t['subject_id'], t['required_minutes'], date.today().isoformat(), datetime.now().isoformat()))
        db.execute('UPDATE user_stats SET total_minutes=total_minutes+? WHERE user_id=?', (t['required_minutes'], uid))
        award_xp(db, uid, 50); update_streak(db, uid)
        nb = check_badges(db, uid); db.commit()
    return jsonify({'success': True, 'xp_earned': 50, 'new_badges': nb or []})

# ── Quiz API ────────────────────────────────────────────────────────────────────
QUIZ_BANK = {
    'java': [
        {'q':'Default value of int?','o':['null','-1','0','undefined'],'a':2},
        {'q':'Keyword to inherit?','o':['implements','extends','inherits','super'],'a':1},
        {'q':'Which allows duplicates?','o':['Set','Map','List','HashSet'],'a':2},
        {'q':'What is encapsulation?','o':['Hiding data','Inheriting','Multiple instances','Overriding'],'a':0},
        {'q':'Entry point of Java?','o':['start()','run()','main()','init()'],'a':2},
    ],
    'dsa': [
        {'q':'Binary search complexity?','o':['O(n)','O(n2)','O(log n)','O(1)'],'a':2},
        {'q':'LIFO structure?','o':['Queue','Stack','Array','LinkedList'],'a':1},
        {'q':'QuickSort worst case?','o':['O(n log n)','O(n)','O(n2)','O(log n)'],'a':2},
        {'q':'Hash table avg search?','o':['O(n)','O(log n)','O(1)','O(n2)'],'a':2},
    ],
    'default': [
        {'q':'Best study strategy?','o':['Re-reading','Active recall','Watch only','Memorize'],'a':1},
        {'q':'Pomodoro technique?','o':['Speed reading','25min+5min break','Group study','Mind map'],'a':1},
        {'q':'Spaced repetition?','o':['Daily cramming','Reviewing at intervals','One time study','Skipping'],'a':1},
        {'q':'Active recall means?','o':['Re-reading','Testing yourself','Highlighting','Summarizing'],'a':1},
    ]
}

@app.route('/api/quiz/generate', methods=['POST'])
@api_auth
def gen_quiz():
    d = request.json
    topic = d.get('topic_name', '')
    subject = d.get('subject_name', '')
    count = int(d.get('count', 2))
    if AI_OK:
        prompt = f"""Generate {count} MCQ quiz questions about "{topic}" in "{subject}".
Return ONLY valid JSON array:
[{{"question":"Q?","options":["A","B","C","D"],"correct_index":0}}]
Exactly 4 options, correct_index 0-3."""
        result = ask_ai(prompt)
        parsed = parse_json(result)
        if parsed and isinstance(parsed, list):
            valid = [q for q in parsed if 'question' in q and 'options' in q and len(q.get('options',[])) == 4]
            if len(valid) >= count: return jsonify({'questions': valid[:count], 'ai_generated': True})
    combined = (topic+subject).lower()
    if any(k in combined for k in ['java','oop']): bank = QUIZ_BANK['java']
    elif any(k in combined for k in ['dsa','algorithm','tree','stack']): bank = QUIZ_BANK['dsa']
    else: bank = QUIZ_BANK['default']
    sel = random.sample(bank, min(count, len(bank)))
    return jsonify({'questions': [{'question':q['q'],'options':q['o'],'correct_index':q['a']} for q in sel], 'ai_generated': False})

@app.route('/api/quiz/submit', methods=['POST'])
@api_auth
def submit_quiz():
    d = request.json; tid = d.get('topic_id'); score = d.get('score', 0); total = d.get('total', 2)
    passed = score >= (total * 0.5); uid = session['uid']
    with get_db() as db:
        db.execute('INSERT INTO quiz_results(user_id,topic_id,score,total,passed,created_at) VALUES(?,?,?,?,?,?)',
                   (uid, tid, score, total, int(passed), datetime.now().isoformat()))
        if passed:
            award_xp(db, uid, 30)
            if tid: db.execute('UPDATE topics SET quiz_passed=1 WHERE id=? AND user_id=?', (tid, uid))
        nb = check_badges(db, uid); db.commit()
    return jsonify({'passed': passed, 'score': score, 'total': total, 'xp_earned': 30 if passed else 0, 'new_badges': nb or []})

# ── Exams API ───────────────────────────────────────────────────────────────────
TOPIC_PLANS = {
    'java':    ['OOP Basics','Inheritance','Collections','Exception Handling','File I/O','Threads','Streams','Mock Test','Full Revision'],
    'python':  ['Data Types','Functions','OOP','File Handling','Modules','Error Handling','Libraries','Mock Test','Full Revision'],
    'dsa':     ['Arrays','Linked Lists','Stacks & Queues','Binary Search','Sorting','Trees','Graphs','DP','Mock Test','Full Revision'],
    'web':     ['HTML5','CSS Basics','Flexbox','JavaScript','DOM','Fetch API','React Basics','Mock Project','Full Revision'],
    'default': ['Introduction','Core Concepts 1','Core Concepts 2','Advanced 1','Advanced 2','Practice','Mock Test','Full Revision']
}

def gen_schedule(name, days):
    if AI_OK:
        prompt = f"""Create a {min(days,12)}-day study schedule for "{name}" exam in {days} days.
Return ONLY valid JSON array, no other text:
[{{"day":1,"topic":"Topic Name","minutes":30}}]
Rules: {min(days,12)} entries, topics specific to {name}, last day = Full Revision."""
        result = ask_ai(prompt)
        parsed = parse_json(result)
        if parsed and isinstance(parsed, list) and len(parsed) >= 3:
            return [{'day': int(s.get('day',i+1)), 'topic': str(s.get('topic','Study')), 'minutes': int(s.get('minutes',30))}
                    for i, s in enumerate(parsed)]
    combined = name.lower()
    if 'java' in combined: topics = TOPIC_PLANS['java']
    elif 'python' in combined: topics = TOPIC_PLANS['python']
    elif any(k in combined for k in ['dsa','data','algorithm']): topics = TOPIC_PLANS['dsa']
    elif any(k in combined for k in ['web','html','css']): topics = TOPIC_PLANS['web']
    else: topics = TOPIC_PLANS['default']
    total = min(days, 15); step = max(1, total//len(topics)); day = 1; schedule = []
    for i, t in enumerate(topics):
        if day > total: break
        if i == len(topics)-1: day = total
        schedule.append({'day': day, 'topic': t, 'minutes': 45 if 'revision' in t.lower() or 'mock' in t.lower() else 30})
        day += step
    return schedule

@app.route('/api/exams', methods=['GET', 'POST'])
@api_auth
def exams_api():
    uid = session['uid']
    if request.method == 'GET':
        with get_db() as db:
            rows = db.execute('SELECT * FROM exams WHERE user_id=? ORDER BY exam_date', (uid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.json
    name = (d.get('name') or '').strip()
    edate = d.get('exam_date', '')
    sid = d.get('subject_id')
    try: sid = int(sid) if sid else None
    except: sid = None
    if not name or not edate: return jsonify({'error': 'Name and date required'}), 400
    try: exam_date = date.fromisoformat(edate)
    except: return jsonify({'error': 'Invalid date'}), 400
    days = (exam_date - date.today()).days
    if days <= 0: return jsonify({'error': 'Date must be in future'}), 400
    schedule = gen_schedule(name, days)
    with get_db() as db:
        # Use first subject if no subject selected
        if not sid:
            first_subj = db.execute('SELECT id FROM subjects WHERE user_id=? LIMIT 1', (uid,)).fetchone()
            if first_subj: sid = first_subj['id']
        if not sid:
            # Create default subject
            cur2 = db.execute('INSERT INTO subjects(user_id,name,color,created_at) VALUES(?,?,?,?)',
                              (uid, name, '#6366f1', datetime.now().isoformat()))
            sid = cur2.lastrowid
        cur = db.execute('INSERT INTO exams(user_id,subject_id,name,exam_date,created_at) VALUES(?,?,?,?,?)',
                         (uid, sid, name, edate, datetime.now().isoformat()))
        exam_id = cur.lastrowid
        for s in schedule:
            study_date = (date.today()+timedelta(days=s['day']-1)).isoformat()
            db.execute('INSERT INTO topics(user_id,subject_id,name,study_date,required_minutes,exam_id,created_at) VALUES(?,?,?,?,?,?,?)',
                       (uid, sid, s['topic'], study_date, s['minutes'], exam_id, datetime.now().isoformat()))
        db.commit()
    return jsonify({'id': exam_id, 'name': name, 'schedule': schedule, 'days': days, 'success': True})

@app.route('/api/exams/<int:eid>', methods=['DELETE'])
@api_auth
def del_exam(eid):
    with get_db() as db:
        db.execute('DELETE FROM topics WHERE exam_id=? AND user_id=?', (eid, session['uid']))
        db.execute('DELETE FROM exams WHERE id=? AND user_id=?', (eid, session['uid'])); db.commit()
    return jsonify({'success': True})

@app.route('/api/exams/<int:eid>/topics')
@api_auth
def exam_topics(eid):
    with get_db() as db:
        rows = db.execute('SELECT t.*,s.name subject_name,s.color subject_color FROM topics t LEFT JOIN subjects s ON t.subject_id=s.id WHERE t.exam_id=? AND t.user_id=? ORDER BY t.study_date', (eid, session['uid'])).fetchall()
    return jsonify([dict(r) for r in rows])

# ── Study AI API ────────────────────────────────────────────────────────────────
@app.route('/api/study-ai/generate', methods=['POST'])
@api_auth
def generate_study_material():
    uid = session['uid']
    d = request.json
    syllabus = (d.get('syllabus') or '').strip()
    title = (d.get('title') or 'Study Material').strip()
    subject_id = d.get('subject_id')
    try: subject_id = int(subject_id) if subject_id else None
    except: subject_id = None
    exam_date = d.get('exam_date', '')
    if not syllabus: return jsonify({'error': 'Syllabus required'}), 400

    days = 30
    if exam_date:
        try: days = max(1, (date.fromisoformat(exam_date)-date.today()).days)
        except: pass

    short_notes = long_notes = practice_q = ''
    quiz_q = '[]'; schedule = '[]'

    if AI_OK:
        short_notes = ask_ai(
            f'Create short bullet-point revision notes for this syllabus: "{syllabus}". Max 300 words. Plain text only.',
            f'Key topics:\n{syllabus}')

        long_notes = ask_ai(
            f'Create detailed study notes for this syllabus: "{syllabus}". Include definitions, examples, explanations. Plain text only.',
            f'Study these topics carefully:\n{syllabus}')

        practice_q = ask_ai(
            f'Generate 5 practice questions with answers for: "{syllabus}". Format: Q1: ... A1: ... Plain text only.',
            f'Practice Q:\n1. Explain main concepts of {syllabus[:80]}\n2. Give examples\n3. Compare topics\n4. Apply concepts\n5. Summarize key points')

        quiz_result = ask_ai(
            f'Generate 5 MCQ questions for: "{syllabus}". Return ONLY JSON: [{{"question":"Q?","options":["A","B","C","D"],"correct_index":0,"explanation":"reason"}}]')
        parsed_quiz = parse_json(quiz_result)
        if parsed_quiz: quiz_q = json.dumps(parsed_quiz)

        sched = gen_schedule(title, days)
        schedule = json.dumps(sched)
    else:
        short_notes = f'Topics to study:\n{syllabus}'
        long_notes = short_notes
        practice_q = short_notes

    # Ensure subject exists
    if not subject_id:
        with get_db() as db:
            first = db.execute('SELECT id FROM subjects WHERE user_id=? LIMIT 1', (uid,)).fetchone()
            if first: subject_id = first['id']

    with get_db() as db:
        cur = db.execute(
            'INSERT INTO study_materials(user_id,subject_id,title,syllabus_text,short_notes,long_notes,practice_questions,quiz_questions,schedule,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid, subject_id, title, syllabus, short_notes, long_notes, practice_q, quiz_q, schedule, datetime.now().isoformat()))
        # Badge
        s = db.execute('SELECT badges FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        if s:
            earned = json.loads(s['badges'] or '[]')
            if 'ai_user' not in earned:
                earned.append('ai_user')
                db.execute('UPDATE user_stats SET badges=? WHERE user_id=?', (json.dumps(earned), uid))
                award_xp(db, uid, 25)
        db.commit()

    return jsonify({'id': cur.lastrowid, 'title': title, 'short_notes': short_notes,
                    'long_notes': long_notes, 'practice_questions': practice_q,
                    'quiz_questions': quiz_q, 'schedule': schedule, 'ai_powered': AI_OK})

@app.route('/api/study-ai/list')
@api_auth
def list_study_materials():
    with get_db() as db:
        rows = db.execute('SELECT id,title,created_at FROM study_materials WHERE user_id=? ORDER BY created_at DESC', (session['uid'],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/study-ai/<int:mid>', methods=['GET'])
@api_auth
def get_study_material(mid):
    with get_db() as db:
        row = db.execute('SELECT * FROM study_materials WHERE id=? AND user_id=?', (mid, session['uid'])).fetchone()
    if not row: return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))

@app.route('/api/study-ai/<int:mid>', methods=['DELETE'])
@api_auth
def del_study_material(mid):
    with get_db() as db:
        db.execute('DELETE FROM study_materials WHERE id=? AND user_id=?', (mid, session['uid'])); db.commit()
    return jsonify({'success': True})

# ── Flashcards API ──────────────────────────────────────────────────────────────
@app.route('/api/flashcards/generate', methods=['POST'])
@api_auth
def gen_flashcards():
    d = request.json
    topic = d.get('topic', ''); subject = d.get('subject', ''); count = int(d.get('count', 10))
    if AI_OK:
        result = ask_ai(f'Generate {count} flashcards for "{topic}" in "{subject}". Return ONLY JSON: [{{"front":"Term or question","back":"Answer or definition"}}]')
        parsed = parse_json(result)
        if parsed and isinstance(parsed, list) and len(parsed) >= 3:
            return jsonify({'flashcards': parsed[:count], 'ai_generated': True})
    defaults = [
        {'front': f'What is {topic}?', 'back': f'{topic} is a key concept in {subject}.'},
        {'front': f'Why is {topic} important?', 'back': f'It is fundamental to understanding {subject}.'},
        {'front': f'Give an example of {topic}', 'back': 'Think of a real-world application.'},
        {'front': f'Types of {topic}?', 'back': 'Review your notes for classification.'},
        {'front': f'How does {topic} work?', 'back': 'Recall the step-by-step process.'},
    ]
    return jsonify({'flashcards': defaults[:count], 'ai_generated': False})

# ── Games API ───────────────────────────────────────────────────────────────────
@app.route('/api/games/daily-challenge')
@api_auth
def daily_challenge():
    uid = session['uid']; today = date.today().isoformat()
    with get_db() as db:
        topic = db.execute('SELECT t.*,s.name sname FROM topics t JOIN subjects s ON t.subject_id=s.id WHERE t.user_id=? AND t.study_date=? AND t.completed=0 LIMIT 1', (uid, today)).fetchone()
        done = db.execute('SELECT COUNT(*) c FROM topics WHERE user_id=? AND completed=1 AND study_date=?', (uid, today)).fetchone()['c']
        stats = db.execute('SELECT streak FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    return jsonify({'challenge_topic': dict(topic) if topic else None, 'completed_today': done,
                    'streak': stats['streak'] if stats else 0, 'bonus_xp': 100, 'challenge_date': today})

@app.route('/api/games/complete-challenge', methods=['POST'])
@api_auth
def complete_challenge():
    uid = session['uid']
    with get_db() as db:
        award_xp(db, uid, 100)
        s = db.execute('SELECT badges FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        if s:
            earned = json.loads(s['badges'] or '[]')
            if 'daily_champ' not in earned:
                earned.append('daily_champ')
                db.execute('UPDATE user_stats SET badges=? WHERE user_id=?', (json.dumps(earned), uid))
        db.commit()
    return jsonify({'success': True, 'xp_earned': 100})

@app.route('/api/games/speed-quiz', methods=['POST'])
@api_auth
def speed_quiz_result():
    uid = session['uid']; data = request.json; score = data.get('score', 0); xp = min(score*10, 100)
    with get_db() as db:
        award_xp(db, uid, xp)
        if score >= 5:
            s = db.execute('SELECT badges FROM user_stats WHERE user_id=?', (uid,)).fetchone()
            if s:
                earned = json.loads(s['badges'] or '[]')
                if 'speed_5' not in earned:
                    earned.append('speed_5')
                    db.execute('UPDATE user_stats SET badges=? WHERE user_id=?', (json.dumps(earned), uid))
        db.commit()
    return jsonify({'success': True, 'xp_earned': xp})

@app.route('/api/games/tournament')
@api_auth
def tournament():
    ws = (date.today()-timedelta(days=date.today().weekday())).isoformat()
    with get_db() as db:
        players = db.execute(
            'SELECT u.name,COALESCE(SUM(ss.minutes),0) study_mins,us.xp,us.streak FROM users u JOIN user_stats us ON u.id=us.user_id LEFT JOIN study_sessions ss ON ss.user_id=u.id AND ss.session_date>=? GROUP BY u.id ORDER BY study_mins DESC LIMIT 20',
            (ws,)).fetchall()
    return jsonify({'tournament': [dict(p) for p in players],
                    'week_start': ws,
                    'week_end': (date.today()+timedelta(days=6-date.today().weekday())).isoformat(),
                    'prize_xp': 500})

# ── Dashboard API ───────────────────────────────────────────────────────────────
@app.route('/api/dashboard')
@api_auth
def dashboard_api():
    uid = session['uid']; today = date.today().isoformat()
    with get_db() as db:
        stats = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        topics = db.execute('SELECT t.*,s.name subject_name,s.color subject_color FROM topics t JOIN subjects s ON t.subject_id=s.id WHERE t.user_id=? AND t.study_date=? ORDER BY t.position,t.created_at', (uid, today)).fetchall()
        subjects = db.execute('SELECT * FROM subjects WHERE user_id=? LIMIT 6', (uid,)).fetchall()
        exams = db.execute('SELECT * FROM exams WHERE user_id=? AND exam_date>=? ORDER BY exam_date LIMIT 4', (uid, today)).fetchall()
        streak_days = []
        DAYS = ['Mo','Tu','We','Th','Fr','Sa','Su']
        for i in range(6, -1, -1):
            d = (date.today()-timedelta(days=i)).isoformat()
            studied = db.execute('SELECT COUNT(*) c FROM study_sessions WHERE user_id=? AND session_date=?', (uid, d)).fetchone()['c'] > 0
            streak_days.append({'date': d, 'studied': studied, 'day': DAYS[(date.today()-timedelta(days=i)).weekday()]})

    # Quote from AI or fallback
    QUOTES = [
        '"The secret of getting ahead is getting started." — Mark Twain',
        '"Success is the sum of small efforts, repeated day in and day out." — Robert Collier',
        '"The expert in anything was once a beginner." — Helen Hayes',
        '"An investment in knowledge pays the best interest." — Benjamin Franklin',
        '"Do something today that your future self will thank you for." — Unknown',
        '"The harder you work, the greater you feel when you achieve it." — Unknown',
        '"Small daily improvements lead to stunning results." — Robin Sharma',
        '"Believe you can and you\'re halfway there." — Theodore Roosevelt',
        '"Education is the most powerful weapon you can use to change the world." — Nelson Mandela',
        '"Don\'t stop when you\'re tired. Stop when you\'re done." — Unknown',
    ]
    quote = QUOTES[(date.today().day + date.today().month) % len(QUOTES)]

    xp = stats['xp'] if stats else 0
    return jsonify({
        'stats': dict(stats) if stats else {'xp':0,'level':1,'streak':0,'total_minutes':0},
        'level_info': level_info(xp),
        'today_topics': [dict(t) for t in topics],
        'subjects': [dict(s) for s in subjects],
        'exams': [dict(e) for e in exams],
        'streak_days': streak_days,
        'quote': quote,
        'badges': json.loads(stats['badges'] or '[]') if stats else [],
    })

# ── Analytics API ───────────────────────────────────────────────────────────────
@app.route('/api/analytics')
@api_auth
def analytics_api():
    uid = session['uid']
    with get_db() as db:
        stats = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        weekly = []
        for i in range(6, -1, -1):
            d = (date.today()-timedelta(days=i)).isoformat()
            mins = db.execute('SELECT COALESCE(SUM(minutes),0) m FROM study_sessions WHERE user_id=? AND session_date=?', (uid, d)).fetchone()['m']
            weekly.append({'date': d, 'minutes': mins, 'hours': round(mins/60, 2)})
        monthly = []
        for w in range(3, -1, -1):
            start = (date.today()-timedelta(days=(w+1)*7)).isoformat()
            end = (date.today()-timedelta(days=w*7)).isoformat()
            mins = db.execute('SELECT COALESCE(SUM(minutes),0) m FROM study_sessions WHERE user_id=? AND session_date>=? AND session_date<?', (uid, start, end)).fetchone()['m']
            monthly.append({'week': f'W{4-w}', 'hours': round(mins/60, 1)})
        subjects = db.execute('SELECT s.name,s.color,COUNT(t.id) total,SUM(CASE WHEN t.completed=1 THEN 1 ELSE 0 END) done,COALESCE(SUM(ss.minutes),0) mins FROM subjects s LEFT JOIN topics t ON t.subject_id=s.id AND t.user_id=s.user_id LEFT JOIN study_sessions ss ON ss.subject_id=s.id AND ss.user_id=s.user_id WHERE s.user_id=? GROUP BY s.id ORDER BY mins DESC', (uid,)).fetchall()
        qs = db.execute('SELECT COUNT(*) total,SUM(passed) passed,ROUND(AVG(CAST(score AS REAL)/total)*100,1) avg FROM quiz_results WHERE user_id=?', (uid,)).fetchone()
        ts = db.execute('SELECT COUNT(*) total,SUM(completed) done FROM topics WHERE user_id=?', (uid,)).fetchone()
    return jsonify({
        'stats': dict(stats) if stats else {},
        'weekly': weekly, 'monthly': monthly,
        'subjects': [dict(s) for s in subjects],
        'quiz_stats': dict(qs) if qs else {},
        'topic_stats': dict(ts) if ts else {},
        'level_info': level_info(stats['xp'] if stats else 0),
    })

# ── Coach API ───────────────────────────────────────────────────────────────────
@app.route('/api/coach/insights')
@api_auth
def coach_insights():
    uid = session['uid']
    with get_db() as db:
        stats = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        subjects = db.execute('SELECT s.name,COUNT(t.id) total,SUM(CASE WHEN t.completed=1 THEN 1 ELSE 0 END) done,COALESCE(SUM(ss.minutes),0) mins FROM subjects s LEFT JOIN topics t ON t.subject_id=s.id AND t.user_id=s.user_id LEFT JOIN study_sessions ss ON ss.subject_id=s.id AND ss.user_id=s.user_id WHERE s.user_id=? GROUP BY s.id', (uid,)).fetchall()
        week_mins = db.execute('SELECT COALESCE(SUM(minutes),0) m FROM study_sessions WHERE user_id=? AND session_date>=?', (uid, (date.today()-timedelta(days=7)).isoformat())).fetchone()['m']
    streak = stats['streak'] if stats else 0
    xp = stats['xp'] if stats else 0
    level = stats['level'] if stats else 1
    week_h = round(week_mins/60, 1)
    subj_list = [dict(s) for s in subjects]
    if AI_OK:
        subj_summary = ', '.join([f"{s['name']}({s['done']}/{s['total']} topics)" for s in subj_list]) or 'None'
        prompt = f"""You are an AI study coach. Student data: streak={streak} days, xp={xp}, level={level}, this week={week_h}h studied, subjects={subj_summary}.
Generate 4 personalized insights. Return ONLY valid JSON:
[{{"type":"success","icon":"emoji","title":"short title","message":"2-3 helpful sentences","action":"button text or null","action_url":"/daily or null"}}]
Types: success/warning/info/tip"""
        result = ask_ai(prompt)
        parsed = parse_json(result)
        if parsed and isinstance(parsed, list) and len(parsed) >= 3:
            return jsonify({'insights': parsed[:5], 'ai_powered': True})
    insights = []
    if streak == 0:
        insights.append({'type':'warning','icon':'⚡','title':'Start your streak today!','message':'Complete one topic to begin your habit. Even 20 minutes counts!','action':'Go Study','action_url':'/daily'})
    else:
        insights.append({'type':'success','icon':'🔥','title':f'{streak}-day streak!','message':f'Amazing! Keep going — {7-streak if streak<7 else 0} more days for Week Warrior badge!','action':None,'action_url':None})
    if week_h < 2:
        insights.append({'type':'warning','icon':'⏰','title':'Low study time this week','message':f'Only {week_h}h this week. Target 7h for best results!','action':'Study now','action_url':'/daily'})
    else:
        insights.append({'type':'success','icon':'📚','title':f'{week_h}h studied this week!','message':'Great progress! Keep this momentum going.','action':None,'action_url':None})
    insights.append({'type':'tip','icon':'🧠','title':'Try Study AI!','message':'Upload your syllabus and get instant notes, quiz, and schedule powered by AI!','action':'Try Now','action_url':'/study-ai'})
    insights.append({'type':'info','icon':'🏆','title':f'Level {level} — {xp} XP','message':'Topics +50 XP, Quizzes +30 XP, Streaks +20 XP, Daily Challenge +100 XP!','action':'View Badges','action_url':'/badges'})
    return jsonify({'insights': insights, 'ai_powered': False})

@app.route('/api/coach/chat', methods=['POST'])
@api_auth
def coach_chat():
    msg = (request.json.get('message') or '').strip()
    if not msg: return jsonify({'error': 'Message required'}), 400
    uid = session['uid']
    with get_db() as db:
        stats = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if AI_OK:
        prompt = f"""You are an AI study coach in FocusQuest app.
Student stats: xp={stats['xp'] if stats else 0}, level={stats['level'] if stats else 1}, streak={stats['streak'] if stats else 0} days.
Student message: "{msg}"
Reply in 3-4 sentences. Be specific, encouraging, and mention relevant app features (Study AI, Speed Quiz, Daily Challenge). Plain text only."""
        reply = ask_ai(prompt)
        if reply: return jsonify({'reply': reply, 'ai_powered': True})
    m = msg.lower()
    if any(w in m for w in ['plan','study','what should']):
        return jsonify({'reply': 'Start by adding your subjects in Daily Study, then use Study AI to upload your syllabus and get an instant study plan! Complete the Daily Challenge for +100 bonus XP.', 'ai_powered': False})
    elif any(w in m for w in ['exam','test','prepare']):
        return jsonify({'reply': 'Use Exam Mode to create a day-by-day AI study schedule, or try Study AI to get instant notes and quiz from your syllabus!', 'ai_powered': False})
    else:
        return jsonify({'reply': f'Keep studying consistently! Use Study AI for instant notes, Speed Quiz to test yourself, and maintain your daily streak for bonus XP!', 'ai_powered': False})

# ── Profile API ─────────────────────────────────────────────────────────────────
@app.route('/api/profile')
@api_auth
def get_profile():
    uid = session['uid']
    with get_db() as db:
        u = db.execute('SELECT id,name,email,created_at FROM users WHERE id=?', (uid,)).fetchone()
        s = db.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        tc = db.execute('SELECT COUNT(*) c FROM topics WHERE user_id=? AND completed=1', (uid,)).fetchone()['c']
        sc = db.execute('SELECT COUNT(*) c FROM subjects WHERE user_id=?', (uid,)).fetchone()['c']
        qc = db.execute('SELECT COUNT(*) c FROM quiz_results WHERE user_id=? AND passed=1', (uid,)).fetchone()['c']
        th = db.execute('SELECT COALESCE(SUM(minutes),0) m FROM study_sessions WHERE user_id=?', (uid,)).fetchone()['m']
    xp = s['xp'] if s else 0
    return jsonify({'user': dict(u) if u else {}, 'stats': dict(s) if s else {},
                    'level_info': level_info(xp), 'topic_count': tc, 'subj_count': sc,
                    'quiz_count': qc, 'total_hours': round(th/60, 1),
                    'badges': json.loads(s['badges'] or '[]') if s else [],
                    'streak_best': s['streak'] if s else 0})

@app.route('/api/profile/update', methods=['POST'])
@api_auth
def update_profile():
    name = (request.json.get('name') or '').strip()
    if not name: return jsonify({'error': 'Name required'}), 400
    with get_db() as db:
        db.execute('UPDATE users SET name=? WHERE id=?', (name, session['uid'])); db.commit()
    session['uname'] = name
    return jsonify({'success': True, 'name': name})

# ── Notes API ───────────────────────────────────────────────────────────────────
@app.route('/api/notes', methods=['GET', 'POST'])
@api_auth
def notes_api():
    uid = session['uid']
    if request.method == 'GET':
        sid = request.args.get('subject_id')
        with get_db() as db:
            if sid:
                rows = db.execute('SELECT n.*,s.name sname,s.color scolor FROM notes n JOIN subjects s ON n.subject_id=s.id WHERE n.user_id=? AND n.subject_id=? ORDER BY n.created_at DESC', (uid, sid)).fetchall()
            else:
                rows = db.execute('SELECT n.*,s.name sname,s.color scolor FROM notes n JOIN subjects s ON n.subject_id=s.id WHERE n.user_id=? ORDER BY n.created_at DESC', (uid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.json
    title = (d.get('title') or '').strip()
    content = (d.get('content') or '').strip()
    sid = d.get('subject_id')
    if not title or not content or not sid: return jsonify({'error': 'All fields required'}), 400
    with get_db() as db:
        cur = db.execute('INSERT INTO notes(user_id,subject_id,title,content,created_at) VALUES(?,?,?,?,?)',
                         (uid, sid, title, content, datetime.now().isoformat())); db.commit()
    return jsonify({'id': cur.lastrowid, 'success': True})

@app.route('/api/notes/<int:nid>', methods=['DELETE'])
@api_auth
def del_note(nid):
    with get_db() as db:
        db.execute('DELETE FROM notes WHERE id=? AND user_id=?', (nid, session['uid'])); db.commit()
    return jsonify({'success': True})

# ── Leaderboard API ─────────────────────────────────────────────────────────────
@app.route('/api/leaderboard')
@api_auth
def leaderboard_api():
    with get_db() as db:
        rows = db.execute('SELECT u.name,us.xp,us.level,us.streak,(SELECT COUNT(*) FROM topics WHERE user_id=u.id AND completed=1) topics_done FROM users u JOIN user_stats us ON u.id=us.user_id ORDER BY us.xp DESC LIMIT 20').fetchall()
    return jsonify({'leaderboard': [dict(r) for r in rows], 'my_uid': session['uid']})

# ── Badges API ──────────────────────────────────────────────────────────────────
@app.route('/api/badges')
@api_auth
def badges_api():
    with get_db() as db:
        s = db.execute('SELECT badges FROM user_stats WHERE user_id=?', (session['uid'],)).fetchone()
    earned = json.loads(s['badges'] or '[]') if s else []
    result = [{**info, 'key': key, 'earned': key in earned} for key, info in BADGES.items()]
    return jsonify({'badges': result, 'earned_count': len(earned), 'total': len(BADGES)})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)