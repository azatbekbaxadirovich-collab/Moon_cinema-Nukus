from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, uuid
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'moon.db')
UPLOAD = os.path.join(BASE, 'static', 'uploads')
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'moon-cinema-change-this-secret'
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

ALLOWED_IMG = {'jpg','jpeg','png','webp'}
ALLOWED_VIDEO = {'mp4','webm','mov','m4v'}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db(); c = con.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY, address TEXT, landmark TEXT, hours TEXT,
        call_hours TEXT, phone1 TEXT, phone2 TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, original_title TEXT,
        genre TEXT, age TEXT, duration TEXT, year TEXT, description TEXT,
        cover TEXT, video TEXT, featured INTEGER DEFAULT 0, tag TEXT DEFAULT ''
    )''')
    if not c.execute('SELECT 1 FROM settings WHERE id=1').fetchone():
        c.execute('INSERT INTO settings VALUES (1,?,?,?,?,?,?)', (
            'г. Нукус, Молодёжный центр (Jaslar Orayi), напротив Молодёжного технопарка',
            'Ориентир — гостиница «Ташкент»', '20:30–00:00',
            'Звонки принимаются с 12:00 до 00:00', '+998 91 303 30 77', '+998 88 746 29 29'))
    if not c.execute('SELECT 1 FROM movies LIMIT 1').fetchone():
        demo = [
            ('MIDNIGHT STORY','MIDNIGHT STORY','Драма','16+','2 ч 08 мин','2026','История, которая начинается после наступления темноты.','', '',1,'ПРЕМЬЕРА'),
            ('THE LAST LIGHT','THE LAST LIGHT','Фантастика','12+','1 ч 52 мин','2026','Последний свет. Последний шанс.','', '',0,'СЕГОДНЯ'),
            ('CITY OF DREAMS','CITY OF DREAMS','Комедия','12+','1 ч 47 мин','2026','Большой город, большие мечты и слишком много приключений.','', '',0,'ПОПУЛЯРНОЕ')]
        c.executemany('INSERT INTO movies(title,original_title,genre,age,duration,year,description,cover,video,featured,tag) VALUES(?,?,?,?,?,?,?,?,?,?,?)', demo)
    con.commit(); con.close()

init_db()

def ext(name): return name.rsplit('.',1)[-1].lower() if '.' in name else ''
def save_file(f, allowed):
    if not f or not f.filename: return ''
    e = ext(f.filename)
    if e not in allowed: return ''
    name = f'{uuid.uuid4().hex}.{e}'
    f.save(os.path.join(UPLOAD, name))
    return f'/static/uploads/{name}'

def auth(): return session.get('admin') is True

@app.route('/')
def home():
    con=db(); settings=con.execute('SELECT * FROM settings WHERE id=1').fetchone(); movies=[dict(r) for r in con.execute('SELECT * FROM movies ORDER BY featured DESC, id DESC').fetchall()]; con.close()
    return render_template('index.html', settings=settings, movies=movies)

@app.route('/admin/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        if request.form.get('username')=='admin' and request.form.get('password')=='moon123':
            session['admin']=True; return redirect(url_for('admin'))
        flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/admin/logout')
def logout(): session.clear(); return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not auth(): return redirect(url_for('login'))
    con=db(); settings=con.execute('SELECT * FROM settings WHERE id=1').fetchone(); movies=[dict(r) for r in con.execute('SELECT * FROM movies ORDER BY id DESC').fetchall()]; con.close()
    return render_template('admin.html', settings=settings, movies=movies)

@app.post('/admin/settings')
def settings_save():
    if not auth(): return redirect(url_for('login'))
    con=db(); con.execute('UPDATE settings SET address=?,landmark=?,hours=?,call_hours=?,phone1=?,phone2=? WHERE id=1', (
        request.form.get('address',''),request.form.get('landmark',''),request.form.get('hours',''),request.form.get('call_hours',''),request.form.get('phone1',''),request.form.get('phone2',''))); con.commit(); con.close(); flash('Настройки сохранены'); return redirect(url_for('admin'))

@app.post('/admin/movie/save')
def movie_save():
    if not auth(): return redirect(url_for('login'))
    mid=request.form.get('id')
    cover=save_file(request.files.get('cover'), ALLOWED_IMG)
    video=save_file(request.files.get('video'), ALLOWED_VIDEO)
    fields=(request.form.get('title',''),request.form.get('original_title',''),request.form.get('genre',''),request.form.get('age',''),request.form.get('duration',''),request.form.get('year',''),request.form.get('description',''))
    con=db()
    if mid:
        old=con.execute('SELECT cover,video FROM movies WHERE id=?',(mid,)).fetchone()
        cover=cover or (old['cover'] if old else '')
        video=video or (old['video'] if old else '')
        con.execute('UPDATE movies SET title=?,original_title=?,genre=?,age=?,duration=?,year=?,description=?,cover=?,video=?,featured=?,tag=? WHERE id=?', fields+(cover,video,1 if request.form.get('featured') else 0,request.form.get('tag',''),mid))
    else:
        con.execute('INSERT INTO movies(title,original_title,genre,age,duration,year,description,cover,video,featured,tag) VALUES(?,?,?,?,?,?,?,?,?,?,?)', fields+(cover,video,1 if request.form.get('featured') else 0,request.form.get('tag','')))
    con.commit(); con.close(); flash('Фильм сохранён'); return redirect(url_for('admin'))

@app.post('/admin/movie/delete/<int:mid>')
def movie_delete(mid):
    if not auth(): return redirect(url_for('login'))
    con=db(); row=con.execute('SELECT cover,video FROM movies WHERE id=?',(mid,)).fetchone(); con.execute('DELETE FROM movies WHERE id=?',(mid,)); con.commit(); con.close()
    if row:
        for p in (row['cover'],row['video']):
            if p:
                fp=os.path.join(BASE,p.lstrip('/').replace('/',os.sep))
                if os.path.exists(fp):
                    try: os.remove(fp)
                    except OSError: pass
    return redirect(url_for('admin'))

@app.get('/api/movies')
def api_movies():
    con=db(); rows=[dict(r) for r in con.execute('SELECT * FROM movies ORDER BY featured DESC,id DESC')]; con.close(); return jsonify(rows)

if __name__=='__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
