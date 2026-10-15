from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, uuid
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
# Render: /data is a persistent disk. Locally, it stays inside the project.
DATA = os.environ.get('MOON_DATA_DIR', os.path.join(BASE, 'data'))
DB = os.path.join(DATA, 'moon.db')
UPLOAD = os.path.join(DATA, 'uploads')
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-moon-cinema-secret-change-me')
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
    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, booking_code TEXT UNIQUE, booking_type TEXT NOT NULL DEFAULT 'standard',
        movie_id INTEGER, suggested_movie TEXT, customer_name TEXT NOT NULL, phone TEXT NOT NULL,
        people INTEGER NOT NULL DEFAULT 1, show_date TEXT NOT NULL, show_time TEXT NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'cash', payment_status TEXT NOT NULL DEFAULT 'pending',
        status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, admin_note TEXT DEFAULT ''
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
    con=db(); settings=con.execute('SELECT * FROM settings WHERE id=1').fetchone(); movies=[dict(r) for r in con.execute('SELECT * FROM movies ORDER BY featured DESC, id DESC').fetchall()]
    counts = {r['movie_id']: r['people'] for r in con.execute("SELECT movie_id, SUM(people) AS people FROM bookings WHERE status IN ('new','confirmed') AND booking_type='standard' AND movie_id IS NOT NULL GROUP BY movie_id")}
    con.close()
    return render_template('index.html', settings=settings, movies=movies, booked_counts=counts)

@app.post('/booking/create')
def booking_create():
    booking_type = request.form.get('booking_type', 'standard')
    if booking_type not in ('standard', 'group'):
        booking_type = 'standard'
    name = request.form.get('customer_name', '').strip()[:100]
    phone = request.form.get('phone', '').strip()[:40]
    date = request.form.get('show_date', '').strip()
    show_time = request.form.get('show_time', '').strip()
    try:
        people = int(request.form.get('people', '1'))
    except (TypeError, ValueError):
        people = 1
    if not name or not phone or not date or not show_time or people < 1 or people > 100:
        flash('Заполни имя, телефон, дату, время и количество гостей. Допустимо от 1 до 100 человек.')
        return redirect(url_for('home') + '#booking')
    if booking_type == 'group' and people < 10:
        flash('Для группового показа нужно указать минимум 10 человек.')
        return redirect(url_for('home') + '#booking')
    movie_id = request.form.get('movie_id') or None
    if booking_type == 'standard' and not movie_id:
        flash('Выбери фильм для бронирования.')
        return redirect(url_for('home') + '#booking')
    if movie_id:
        try:
            movie_id = int(movie_id)
        except ValueError:
            movie_id = None
    suggested = request.form.get('suggested_movie', '').strip()[:160]
    payment = request.form.get('payment_method', 'cash')
    if payment not in ('cash', 'click_payme'):
        payment = 'cash'
    code = 'MOON-' + uuid.uuid4().hex[:8].upper()
    con = db()
    if movie_id and not con.execute('SELECT 1 FROM movies WHERE id=?', (movie_id,)).fetchone():
        con.close()
        flash('Этот фильм уже недоступен. Выбери другой фильм.')
        return redirect(url_for('home') + '#booking')
    con.execute('''INSERT INTO bookings(booking_code,booking_type,movie_id,suggested_movie,customer_name,phone,people,show_date,show_time,payment_method,payment_status,status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (code, booking_type, movie_id, suggested, name, phone, people, date, show_time, payment, 'pending', 'new'))
    con.commit(); con.close()
    flash(f'Заявка отправлена! Номер: {code}. Администратор подтвердит бронь по телефону. Онлайн-оплата пока не подключена, поэтому статус оплаты не изменён.')
    return redirect(url_for('home') + '#booking')

@app.post('/admin/booking/update/<int:bid>')
def booking_update(bid):
    if not auth():
        return redirect(url_for('login'))
    status = request.form.get('status', 'new')
    payment_status = request.form.get('payment_status', 'pending')
    if status not in ('new', 'confirmed', 'cancelled'):
        status = 'new'
    if payment_status not in ('pending', 'paid', 'not_required'):
        payment_status = 'pending'
    note = request.form.get('admin_note', '').strip()[:500]
    con=db(); con.execute('UPDATE bookings SET status=?, payment_status=?, admin_note=? WHERE id=?', (status, payment_status, note, bid)); con.commit(); con.close()
    flash('Заявка обновлена')
    return redirect(url_for('admin') + '#bookings')

@app.route('/admin/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        if request.form.get('username') == os.environ.get('ADMIN_USERNAME', 'admin') and request.form.get('password') == os.environ.get('ADMIN_PASSWORD', 'moon123'):
            session['admin']=True; return redirect(url_for('admin'))
        flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/admin/logout')
def logout(): session.clear(); return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not auth(): return redirect(url_for('login'))
    con=db(); settings=con.execute('SELECT * FROM settings WHERE id=1').fetchone(); movies=[dict(r) for r in con.execute('SELECT * FROM movies ORDER BY id DESC').fetchall()]
    bookings=[dict(r) for r in con.execute('SELECT b.*, m.title AS movie_title FROM bookings b LEFT JOIN movies m ON m.id=b.movie_id ORDER BY b.id DESC LIMIT 200').fetchall()]
    totals=[dict(r) for r in con.execute("SELECT m.id, m.title, COALESCE(SUM(CASE WHEN b.status IN ('new','confirmed') AND b.booking_type='standard' THEN b.people ELSE 0 END),0) AS people FROM movies m LEFT JOIN bookings b ON b.movie_id=m.id GROUP BY m.id ORDER BY m.title").fetchall()]
    con.close()
    return render_template('admin.html', settings=settings, movies=movies, bookings=bookings, booking_totals=totals)

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', host='0.0.0.0', port=port)
