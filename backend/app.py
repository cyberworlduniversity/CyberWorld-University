import os
from functools import wraps
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY','dev-only-change-me'), MYSQL_HOST=os.getenv('MYSQL_HOST','127.0.0.1'), MYSQL_PORT=int(os.getenv('MYSQL_PORT','3306')), MYSQL_USER=os.getenv('MYSQL_USER','root'), MYSQL_PASSWORD=os.getenv('MYSQL_PASSWORD',''), MYSQL_DB=os.getenv('MYSQL_DATABASE','cwu'), MYSQL_CURSORCLASS='DictCursor', SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
mysql = MySQL(app)
CORS(app, supports_credentials=True)

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current=session.get('user')
            if not current: return jsonify({'error':'Authentication required'}),401
            if role and current.get('role')!=role: return jsonify({'error':'Forbidden'}),403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.get('/api/health')
def health(): return jsonify({'ok':True,'service':'CWU API'})

@app.post('/api/auth/register')
def register():
    data=request.get_json(silent=True) or {}; name=str(data.get('name','')).strip(); email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
    if not name or not email or len(password)<8: return jsonify({'error':'Name, valid email and password of at least 8 characters are required'}),400
    cur=mysql.connection.cursor()
    try:
        cur.execute('SELECT id FROM users WHERE email=%s',(email,))
        if cur.fetchone(): return jsonify({'error':'Email already registered'}),409
        cur.execute("INSERT INTO users (name,email,password_hash,role) VALUES (%s,%s,%s,'student')",(name,email,generate_password_hash(password)))
        mysql.connection.commit(); return jsonify({'message':'Registration successful'}),201
    finally: cur.close()

@app.post('/api/auth/login')
def login():
    data=request.get_json(silent=True) or {}; email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
    cur=mysql.connection.cursor()
    try:
        cur.execute('SELECT id,name,email,password_hash,role FROM users WHERE email=%s',(email,)); user=cur.fetchone()
        if not user or not check_password_hash(user['password_hash'],password): return jsonify({'error':'Invalid email or password'}),401
        session['user']={'id':user['id'],'name':user['name'],'email':user['email'],'role':user['role']}; return jsonify({'user':session['user']})
    finally: cur.close()

@app.post('/api/auth/logout')
def logout(): session.clear(); return jsonify({'message':'Logged out'})

@app.get('/api/auth/me')
def me(): return jsonify({'user':session.get('user')})

@app.get('/api/courses')
def courses():
    cur=mysql.connection.cursor()
    try:
        cur.execute("SELECT c.id,c.title,c.slug,c.description,c.thumbnail,c.level,c.duration_minutes,c.price,c.is_free,c.status,cc.name AS category FROM courses c LEFT JOIN course_categories cc ON cc.id=c.category_id WHERE c.status='published' ORDER BY c.created_at DESC")
        return jsonify({'courses':cur.fetchall()})
    finally: cur.close()

@app.get('/api/courses/<int:course_id>')
def course_detail(course_id):
    cur=mysql.connection.cursor()
    try:
        cur.execute("SELECT * FROM courses WHERE id=%s AND status='published'",(course_id,)); course=cur.fetchone()
        if not course: return jsonify({'error':'Course not found'}),404
        cur.execute('SELECT id,title,description,sort_order,status FROM course_phases WHERE course_id=%s ORDER BY sort_order,id',(course_id,))
        return jsonify({'course':course,'phases':cur.fetchall()})
    finally: cur.close()

@app.post('/api/enrollments')
@login_required('student')
def enroll():
    data=request.get_json(silent=True) or {}
    try:
        course_id=int(data.get('course_id'))
    except (TypeError,ValueError):
        return jsonify({'error':'Valid course_id is required'}),400
    cur=mysql.connection.cursor()
    try:
        cur.execute("SELECT id,title FROM courses WHERE id=%s AND status='published'",(course_id,))
        course=cur.fetchone()
        if not course: return jsonify({'error':'Course not found'}),404
        cur.execute('SELECT id FROM enrollments WHERE user_id=%s AND course_id=%s',(session['user']['id'],course_id))
        if cur.fetchone(): return jsonify({'message':'Already enrolled','course':course})
        cur.execute('INSERT INTO enrollments (user_id,course_id) VALUES (%s,%s)',(session['user']['id'],course_id))
        mysql.connection.commit()
        return jsonify({'message':'Enrollment successful','course':course}),201
    finally: cur.close()

@app.get('/api/student/enrollments')
@login_required('student')
def student_enrollments():
    cur=mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT e.id enrollment_id,c.id course_id,c.title,c.slug,c.thumbnail,c.level,c.duration_minutes,
                   COUNT(DISTINCT l.id) total_lessons,
                   COUNT(DISTINCT CASE WHEN sp.completed=1 THEN l.id END) completed_lessons,
                   CASE WHEN COUNT(DISTINCT l.id)=0 THEN 0
                        ELSE ROUND(100*COUNT(DISTINCT CASE WHEN sp.completed=1 THEN l.id END)/COUNT(DISTINCT l.id),0) END progress_percent
            FROM enrollments e
            JOIN courses c ON c.id=e.course_id
            LEFT JOIN course_phases p ON p.course_id=c.id AND p.status='published'
            LEFT JOIN lessons l ON l.phase_id=p.id AND l.status='published'
            LEFT JOIN student_progress sp ON sp.lesson_id=l.id AND sp.user_id=e.user_id
            WHERE e.user_id=%s
            GROUP BY e.id,c.id,c.title,c.slug,c.thumbnail,c.level,c.duration_minutes
            ORDER BY e.enrolled_at DESC
        """,(session['user']['id'],))
        return jsonify({'enrollments':cur.fetchall()})
    finally: cur.close()

@app.get('/api/admin/stats')
@login_required('admin')
def admin_stats():
    cur=mysql.connection.cursor(); tables=['users','courses','lessons','videos','materials','questions','quizzes','exams','certificates','advertisements']; stats={}
    try:
        for table in tables:
            cur.execute('SELECT COUNT(*) AS count FROM '+table); stats[table]=cur.fetchone()['count']
        return jsonify(stats)
    finally: cur.close()

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=True)
