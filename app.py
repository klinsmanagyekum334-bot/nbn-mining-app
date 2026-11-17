from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'nbn_mining_super_secret_secure_key_2026'
VALID_PASSWORDS = ['0987654321', 'Klinsman@ophyser1', '9999']

# --- PWA ROUTES ---
@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('static', 'manifest.json')

@app.route('/service-worker.js')
def serve_sw(): return send_from_directory('static', 'service-worker.js')

# --- SECURITY & SPLASH LOGIC ---
@app.before_request
def require_login():
    allowed_routes = ['login', 'static', 'splash', 'serve_manifest', 'serve_sw']
    if request.endpoint and request.endpoint not in allowed_routes and 'logged_in' not in session:
        return redirect(url_for('splash'))

@app.route('/splash')
def splash():
    return render_template('splash.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form['password']
        if password in VALID_PASSWORDS:
            session['logged_in'] = True
            return redirect(url_for('home'))
        else:
            error = "Access Denied! Invalid Password."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('splash'))

# Database setup
def get_db():
    conn = sqlite3.connect('mining.db')
    conn.row_factory = sqlite3.Row
    return conn

with get_db() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS costs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, item TEXT, amount REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS earnings (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE, grams REAL, amount REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS equipment (id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER, item TEXT, quantity INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS workers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id INTEGER, date TEXT, status TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS fraud_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT, grams REAL, amount REAL)''')
    try:
        conn.execute('ALTER TABLE workers ADD COLUMN work_id TEXT')
        conn.execute('ALTER TABLE workers ADD COLUMN contact TEXT')
        conn.execute('ALTER TABLE workers ADD COLUMN picture_url TEXT')
    except sqlite3.OperationalError: pass

# --- MAIN ROUTES (same as before) ---
@app.route('/')
def home(): return render_template('index.html')

@app.route('/logistics', methods=['GET', 'POST'])
def logistics():
    if request.method == 'POST' and 'add_site' in request.form:
        site_name = request.form['site_name']
        with get_db() as conn:
            try: conn.execute('INSERT INTO sites (name) VALUES (?)', (site_name,))
            except sqlite3.IntegrityError: pass
        return redirect(url_for('logistics'))

    search_query = request.args.get('search', '')
    with get_db() as conn:
        if search_query:
            sites_query = '''SELECT DISTINCT s.* FROM sites s LEFT JOIN equipment e ON s.id = e.site_id WHERE s.name LIKE ? OR e.item LIKE ? ORDER BY s.name'''
            sites_list = conn.execute(sites_query, (f'%{search_query}%', f'%{search_query}%')).fetchall()
        else:
            sites_list = conn.execute('SELECT * FROM sites ORDER BY name').fetchall()

        equipment_list = conn.execute('SELECT * FROM equipment ORDER BY item').fetchall()
        equipment_dict = {}
        for eq in equipment_list:
            if eq['site_id'] not in equipment_dict: equipment_dict[eq['site_id']] = []
            equipment_dict[eq['site_id']].append(eq)
    return render_template('logistics.html', sites=sites_list, equipment=equipment_dict, search_query=search_query)

@app.route('/add_equipment/<int:site_id>', methods=['POST'])
def add_equipment(site_id):
    item = request.form['item']
    quantity = int(request.form['quantity'])
    with get_db() as conn: conn.execute('INSERT INTO equipment (site_id, item, quantity) VALUES (?, ?, ?)', (site_id, item, quantity))
    return redirect(url_for('logistics'))

@app.route('/delete_equipment/<int:id>')
def delete_equipment(id):
    with get_db() as conn: conn.execute('DELETE FROM equipment WHERE id=?', (id,))
    return redirect(url_for('logistics'))

@app.route('/workers', methods=['GET', 'POST'])
def workers():
    search_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    is_today = (search_date == datetime.now().strftime("%Y-%m-%d"))
    date_obj = datetime.strptime(search_date, "%Y-%m-%d")
    display_date = date_obj.strftime("%d/%m/%Y")
    day_name = date_obj.strftime("%A")

    if request.method == 'POST' and 'add_worker' in request.form:
        name = request.form['name']
        with get_db() as conn:
            try: conn.execute('INSERT INTO workers (name) VALUES (?)', (name,))
            except sqlite3.IntegrityError: pass
        return redirect(url_for('workers'))

    if request.method == 'POST' and 'save_attendance' in request.form:
        with get_db() as conn:
            conn.execute('DELETE FROM attendance WHERE date = ?', (search_date,))
            workers_list = conn.execute('SELECT id FROM workers').fetchall()
            for worker in workers_list:
                worker_id = str(worker['id'])
                status = request.form.get(f'status_{worker_id}', 'Absent')
                conn.execute('INSERT INTO attendance (worker_id, date, status) VALUES (?, ?, ?)', (worker_id, search_date, status))
        return redirect(url_for('workers', date=search_date))

    with get_db() as conn:
        workers_list = conn.execute('SELECT * FROM workers ORDER BY name').fetchall()
        attendance_records = conn.execute('SELECT * FROM attendance WHERE date = ?', (search_date,)).fetchall()
        attendance_dict = {str(record['worker_id']): record['status'] for record in attendance_records}

    total_present = sum(1 for status in attendance_dict.values() if status == 'Present')
    total_absent = len(workers_list) - total_present

    return render_template('workers.html', workers=workers_list, attendance=attendance_dict, display_date=display_date, search_date=search_date, is_today=is_today, day_name=day_name, total_present=total_present, total_absent=total_absent)

@app.route('/worker_detail/<int:id>', methods=['GET', 'POST'])
def worker_detail(id):
    with get_db() as conn:
        if request.method == 'POST':
            conn.execute('UPDATE workers SET name=?, work_id=?, contact=?, picture_url=? WHERE id=?', (request.form['name'], request.form['work_id'], request.form['contact'], request.form['picture_url'], id))
            return redirect(url_for('worker_detail', id=id))
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (id,)).fetchone()
        history = conn.execute('SELECT * FROM attendance WHERE worker_id=? ORDER BY date DESC', (id,)).fetchall()
    return render_template('worker_detail.html', worker=worker, history=history)

@app.route('/delete_worker/<int:id>')
def delete_worker(id):
    with get_db() as conn:
        conn.execute('DELETE FROM workers WHERE id=?', (id,))
        conn.execute('DELETE FROM attendance WHERE worker_id=?', (id,))
    return redirect(url_for('workers'))

@app.route('/fraud_prevention')
def fraud_prevention():
    with get_db() as conn: logs = conn.execute('SELECT * FROM fraud_logs ORDER BY id DESC').fetchall()
    return render_template('fraud.html', logs=logs)

@app.route('/delete_fraud_log/<int:id>')
def delete_fraud_log(id):
    with get_db() as conn: conn.execute('DELETE FROM fraud_logs WHERE id=?', (id,))
    return redirect(url_for('fraud_prevention'))

@app.route('/costs', methods=['GET', 'POST'])
def costs():
    if request.method == 'POST':
        date = request.form['date']
        item = request.form['item']
        amount = float(request.form['amount'])
        with get_db() as conn: conn.execute('INSERT INTO costs (date, item, amount) VALUES (?, ?, ?)', (date, item, amount))
        return redirect(url_for('costs'))

    search_query = request.args.get('search', '')
    today = datetime.now().strftime("%Y-%m-%d")
    start_of_week = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")

    with get_db() as conn:
        today_total = conn.execute('SELECT SUM(amount) FROM costs WHERE date = ?', (today,)).fetchone()[0] or 0.0
        week_total = conn.execute('SELECT SUM(amount) FROM costs WHERE date >= ?', (start_of_week,)).fetchone()[0] or 0.0
        if search_query: costs_list = conn.execute('SELECT * FROM costs WHERE item LIKE ? OR date LIKE ? ORDER BY date DESC', (f'%{search_query}%', f'%{search_query}%')).fetchall()
        else: costs_list = conn.execute('SELECT * FROM costs ORDER BY date DESC, id DESC LIMIT 20').fetchall()

    return render_template('costs.html', costs=costs_list, today_total=today_total, week_total=week_total, today_date=today, search_query=search_query)

@app.route('/edit_cost/<int:id>', methods=['GET', 'POST'])
def edit_cost(id):
    with get_db() as conn:
        if request.method == 'POST':
            conn.execute('UPDATE costs SET date=?, item=?, amount=? WHERE id=?', (request.form['date'], request.form['item'], request.form['amount'], id))
            return redirect(url_for('costs'))
        cost = conn.execute('SELECT * FROM costs WHERE id=?', (id,)).fetchone()
    return render_template('edit_cost.html', cost=cost)

@app.route('/delete_cost/<int:id>')
def delete_cost(id):
    with get_db() as conn: conn.execute('DELETE FROM costs WHERE id=?', (id,))
    return redirect(url_for('costs'))

@app.route('/earnings', methods=['GET', 'POST'])
def earnings():
    if request.method == 'POST':
        date = request.form['date']
        grams = float(request.form['grams'])
        amount = float(request.form['amount'])
        with get_db() as conn:
            existing = conn.execute('SELECT id FROM earnings WHERE date=?', (date,)).fetchone()
            if existing: conn.execute('UPDATE earnings SET grams=?, amount=? WHERE date=?', (grams, amount, date))
            else: conn.execute('INSERT INTO earnings (date, grams, amount) VALUES (?, ?, ?)', (date, grams, amount))
            if grams > 5.0:
                now = datetime.now()
                conn.execute('INSERT INTO fraud_logs (date, time, grams, amount) VALUES (?, ?, ?, ?)', (now.strftime("%d/%m/%Y"), now.strftime("%H:%M:%S"), grams, amount))
        return redirect(url_for('earnings'))

    today_raw = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%d/%m/%Y")
    today_day = datetime.now().strftime("%A")
    search_date = request.args.get('search', '')
    
    with get_db() as conn:
        today_record = conn.execute('SELECT * FROM earnings WHERE date=?', (today_raw,)).fetchone()
        if search_date: history = conn.execute('SELECT * FROM earnings WHERE date LIKE ? ORDER BY date DESC', (f'%{search_date}%',)).fetchall()
        else: history = conn.execute('SELECT * FROM earnings ORDER BY date DESC').fetchall()

    return render_template('earnings.html', today_record=today_record, today_display=today_display, today_day=today_day, today_date=today_raw, history=history, search_date=search_date)

@app.route('/report_detail/<date>')
def report_detail(date):
    with get_db() as conn: record = conn.execute('SELECT * FROM earnings WHERE date=?', (date,)).fetchone()
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    return render_template('report_detail.html', record=record, display_date=date_obj.strftime("%d/%m/%Y"), day_name=date_obj.strftime("%A"))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
