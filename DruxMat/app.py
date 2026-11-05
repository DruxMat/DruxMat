"""DruxMat Premium — Flask customer orders and separate administrator area."""
import os
import re
import io
import hmac
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse
import sqlite3
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DRUXMAT_DATA_DIR', str(ROOT / 'instance'))).resolve()
DB_PATH = Path(os.environ.get('DATABASE_PATH', str(DATA_DIR / 'druxmat.sqlite3'))).resolve()
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', str(DATA_DIR / 'uploads'))).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Railway and other production platforms require persistent signing keys.
IN_PRODUCTION = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('DRUXMAT_PRODUCTION') == '1')
configured_secret = os.environ.get('SECRET_KEY', '')
if IN_PRODUCTION and (len(configured_secret) < 32 or configured_secret.startswith('SET_A_')):
    raise RuntimeError('Brakuje silnego SECRET_KEY (min. 32 znaki) w konfiguracji serwera.')
if IN_PRODUCTION and os.environ.get('COOKIE_SECURE', '1') != '1':
    raise RuntimeError('Ustaw COOKIE_SECURE=1 w publicznym wdrożeniu HTTPS.')

app = Flask(__name__)
app.config.update(
    SECRET_KEY=configured_secret or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=24 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1' if IN_PRODUCTION else '0') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

CONTACT_EMAIL = 'druxmat@gmail.com'
PHONE_LABEL = '577 636 936'
SERVICES = [
    'Druk 3D na zamówienie', 'Prototypowanie', 'Małe serie produkcyjne',
    'Projektowanie modeli 3D', 'Konsultacja projektu'
]
MATERIALS = ['Nie wiem — proszę o poradę', 'PLA', 'PETG', 'ABS / ASA', 'TPU', 'Inny']
STATUSES = ['Nowe', 'W analizie', 'Wycenione', 'W realizacji', 'Gotowe', 'Zakończone', 'Anulowane']
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
FILE_EXTENSIONS = IMAGE_EXTENSIONS | {'stl', '3mf', 'obj', 'pdf'}
MAX_FILES = 4
MAX_FILE_BYTES = 12 * 1024 * 1024
EMAIL_RE = re.compile(r'^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$')
ADMIN_LOGIN_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{4,31}$')


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def connection():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=5000')
    return con


def init_db():
    with connection() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                service TEXT NOT NULL, material TEXT NOT NULL, quantity INTEGER NOT NULL,
                description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Nowe',
                admin_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_files (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                stored_name TEXT NOT NULL, original_name TEXT NOT NULL,
                kind TEXT NOT NULL, content_type TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                token TEXT PRIMARY KEY, count INTEGER NOT NULL, last_attempt TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, id DESC);
        ''')
        # Migrations for previously created DruxMat databases.
        user_cols = {row['name'] for row in con.execute('PRAGMA table_info(users)')}
        if 'login_name' not in user_cols:
            con.execute('ALTER TABLE users ADD COLUMN login_name TEXT')
        if 'session_version' not in user_cols:
            con.execute('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')
        con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_name ON users(login_name COLLATE NOCASE) WHERE login_name IS NOT NULL')
        # Keep compatibility with the first DruxMat project database.
        cols = {row['name'] for row in con.execute('PRAGMA table_info(orders)')}
        if {'image_filename', 'image_original'} <= cols:
            rows = con.execute('SELECT id, image_filename, image_original FROM orders WHERE image_filename IS NOT NULL').fetchall()
            for row in rows:
                exists = con.execute('SELECT 1 FROM order_files WHERE order_id=? AND stored_name=?', (row['id'], row['image_filename'])).fetchone()
                if not exists:
                    con.execute('INSERT INTO order_files(order_id, stored_name, original_name, kind, content_type) VALUES(?,?,?,?,?)',
                                (row['id'], row['image_filename'], row['image_original'] or 'zdjecie.jpg', 'image', 'image/jpeg'))
        con.commit()


def create_admin(email, password, login_name=None):
    email = email.strip().lower()
    login_name = login_name.strip() if login_name else None
    if not EMAIL_RE.fullmatch(email) or len(password) < 12 or len(password) > 256:
        raise ValueError('Administrator wymaga poprawnego adresu e-mail i hasła 12–256 znaków.')
    if login_name and not ADMIN_LOGIN_RE.fullmatch(login_name):
        raise ValueError('Login: 5–32 znaki, początek literą; dozwolone litery, cyfry, _ i -.')
    with connection() as con:
        existing = con.execute('SELECT id,role FROM users WHERE email=?', (email,)).fetchone()
        if existing and existing['role'] != 'admin':
            raise ValueError('Podany e-mail jest zajęty przez konto klienta. Użyj innego adresu.')
        try:
            if existing:
                con.execute('UPDATE users SET password_hash=?, login_name=COALESCE(?,login_name), session_version=session_version+1 WHERE id=?',
                            (generate_password_hash(password), login_name, existing['id']))
            else:
                con.execute('INSERT INTO users(name,email,password_hash,role,created_at,login_name) VALUES(?,?,?,?,?,?)',
                            ('Administrator', email, generate_password_hash(password), 'admin', now(), login_name))
            con.commit()
        except sqlite3.IntegrityError:
            raise ValueError('Wybrany login administratora jest już zajęty.') from None


def current_user():
    uid = session.get('uid')
    if not isinstance(uid, int):
        return None
    with connection() as con:
        user = con.execute('SELECT id,name,email,role,session_version FROM users WHERE id=?', (uid,)).fetchone()
    if not user or session.get('sv') != user['session_version']:
        session.clear()
        return None
    return user


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


@app.context_processor
def common_context():
    return dict(me=current_user(), csrf=csrf_token, services=SERVICES, materials=MATERIALS,
                statuses=STATUSES, contact_email=CONTACT_EMAIL, phone_label=PHONE_LABEL)


@app.before_request
def check_csrf():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        expected = csrf_token()
        actual = request.form.get('csrf', '')
        if not hmac.compare_digest(expected, actual):
            abort(400, 'Sesja formularza wygasła. Odśwież stronę i spróbuj ponownie.')


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; img-src 'self' data:; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    protected = ('/logowanie', '/rejestracja', '/odzyskaj-haslo', '/ustaw-nowe-haslo',
                 '/admin', '/moje-zamowienia', '/zamowienie', '/zalacznik')
    if request.path.startswith(protected):
        response.headers['Cache-Control'] = 'private, no-store, max-age=0'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    if request.path.startswith('/ustaw-nowe-haslo'):
        response.headers['Referrer-Policy'] = 'no-referrer'
    if IN_PRODUCTION:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def user_required(fn):
    @wraps(fn)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            flash('Zaloguj się, aby kontynuować.', 'error')
            return redirect(url_for('login'))
        if user['role'] == 'admin':
            return redirect(url_for('admin'))
        return fn(*args, **kwargs)
    return decorated


def admin_required(fn):
    @wraps(fn)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or user['role'] != 'admin':
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    return decorated


def limited(token):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    with connection() as con:
        row = con.execute('SELECT count,last_attempt FROM login_attempts WHERE token=?', (token,)).fetchone()
        if not row or row['last_attempt'] < cutoff:
            return False
        return row['count'] >= 8


def record_failure(token):
    stamp = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    with connection() as con:
        con.execute('DELETE FROM login_attempts WHERE last_attempt < ?', (cutoff,))
        row = con.execute('SELECT count FROM login_attempts WHERE token=?', (token,)).fetchone()
        if row:
            con.execute('UPDATE login_attempts SET count=count+1,last_attempt=? WHERE token=?', (stamp, token))
        else:
            con.execute('INSERT INTO login_attempts(token,count,last_attempt) VALUES(?,?,?)', (token, 1, stamp))
        con.commit()


def clear_failures(token):
    with connection() as con:
        con.execute('DELETE FROM login_attempts WHERE token=?', (token,))
        con.commit()


def attempt_token(email, scope):
    import hashlib
    # No unhashed addresses stored in the throttling table.
    return hashlib.sha256((scope + ':' + email.lower()).encode('utf-8')).hexdigest()


def sign_in(user):
    session.clear()
    session['uid'] = user['id']
    session['sv'] = user['session_version']
    session.permanent = True
    csrf_token()


@app.get('/health')
def health():
    return 'ok', 200, {'Cache-Control': 'no-store'}


@app.route('/')
def home():
    return render_template('home.html', title='Druk 3D, prototypowanie i projektowanie')


@app.route('/rejestracja', methods=['GET', 'POST'])
def register():
    if current_user():
        return redirect(url_for('admin') if current_user()['role'] == 'admin' else url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:100]
        email = request.form.get('email', '').strip().lower()[:200]
        password = request.form.get('password', '')
        if len(name) < 2 or not EMAIL_RE.fullmatch(email) or len(password) < 10 or len(password) > 256:
            flash('Podaj imię, prawidłowy e-mail i hasło (10–256 znaków).', 'error')
        else:
            try:
                with connection() as con:
                    cursor = con.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                                         (name, email, generate_password_hash(password), 'user', now()))
                    uid = cursor.lastrowid
                    con.commit()
                sign_in({'id': uid, 'session_version': 0})
                flash('Konto utworzone. Możesz przesłać swój pierwszy projekt.', 'success')
                return redirect(url_for('new_order'))
            except sqlite3.IntegrityError:
                flash('Ten adres e-mail ma już konto. Spróbuj się zalogować.', 'error')
    return render_template('auth.html', title='Załóż konto', register=True)


@app.route('/logowanie', methods=['GET', 'POST'])
def login():
    user = current_user()
    if user:
        return redirect(url_for('admin') if user['role'] == 'admin' else url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()[:200]
        password = request.form.get('password', '')
        token = attempt_token(email, 'client')
        if limited(token):
            flash('Zbyt wiele prób logowania. Spróbuj ponownie za około 15 minut.', 'error')
        else:
            with connection() as con:
                user = con.execute('SELECT * FROM users WHERE email=? AND role=?', (email, 'user')).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                clear_failures(token)
                sign_in(user)
                return redirect(url_for('dashboard'))
            record_failure(token)
            flash('Niepoprawny e-mail lub hasło.', 'error')
    return render_template('auth.html', title='Logowanie klienta', register=False)


@app.post('/wyloguj')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/moje-zamowienia')
@user_required
def dashboard():
    user = current_user()
    with connection() as con:
        orders = con.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC', (user['id'],)).fetchall()
        files = {o['id']: con.execute('SELECT * FROM order_files WHERE order_id=?', (o['id'],)).fetchall() for o in orders}
    return render_template('dashboard.html', title='Moje zamówienia', orders=orders, files=files)


def store_attachment(upload):
    original = secure_filename(upload.filename or '')[:150]
    if not original or '.' not in original:
        raise ValueError('Każdy załącznik musi mieć rozszerzenie pliku.')
    ext = original.rsplit('.', 1)[-1].lower()
    if ext not in FILE_EXTENSIONS:
        raise ValueError('Dozwolone formaty: JPG, PNG, WEBP, STL, 3MF, OBJ, PDF.')
    content = upload.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError('Jeden plik nie może przekraczać 12 MB.')
    if not content:
        raise ValueError('Nie można wysłać pustego pliku.')
    if ext in IMAGE_EXTENSIONS:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 25000000:
                    raise ValueError('Zdjęcie ma za duże wymiary.')
                image = image.convert('RGB')
                image.thumbnail((2600, 2600))
                stored = uuid.uuid4().hex + '.jpg'
                image.save(UPLOAD_DIR / stored, 'JPEG', quality=86, optimize=True)
            return stored, original, 'image', 'image/jpeg'
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise ValueError('Nie można odczytać zdjęcia. Wybierz poprawny obraz.') from None
    if ext == 'pdf' and not content.startswith(b'%PDF-'):
        raise ValueError('Plik PDF jest niepoprawny.')
    stored = uuid.uuid4().hex + '.' + ext
    (UPLOAD_DIR / stored).write_bytes(content)
    return stored, original, 'file', 'application/octet-stream'


@app.route('/zamowienie/nowe', methods=['GET', 'POST'])
@user_required
def new_order():
    if request.method == 'POST':
        service = request.form.get('service', '')
        material = request.form.get('material', '')
        description = request.form.get('description', '').strip()
        try:
            quantity = int(request.form.get('quantity', '0'))
        except ValueError:
            quantity = 0
        if service not in SERVICES or material not in MATERIALS or not 1 <= quantity <= 100000 or not 15 <= len(description) <= 4000:
            flash('Sprawdź usługę, materiał, liczbę sztuk i opis (min. 15 znaków).', 'error')
            return render_template('new_order.html', title='Nowe zamówienie', selected_service=service)
        uploads = [f for f in request.files.getlist('photos') if f and f.filename]
        if len(uploads) > MAX_FILES:
            flash('Możesz przesłać maksymalnie 4 załączniki.', 'error')
            return render_template('new_order.html', title='Nowe zamówienie', selected_service=service)
        created = []
        try:
            for upload in uploads:
                created.append(store_attachment(upload))
            with connection() as con:
                cursor = con.execute('INSERT INTO orders(user_id,service,material,quantity,description,created_at) VALUES(?,?,?,?,?,?)',
                                     (current_user()['id'], service, material, quantity, description, now()))
                for stored, original, kind, mimetype in created:
                    con.execute('INSERT INTO order_files(order_id,stored_name,original_name,kind,content_type) VALUES(?,?,?,?,?)',
                                (cursor.lastrowid, stored, original, kind, mimetype))
                con.commit()
            flash('Zamówienie zapisane! Możesz sprawdzać jego status w panelu klienta.', 'success')
            return redirect(url_for('dashboard'))
        except (ValueError, OSError, sqlite3.Error) as error:
            for stored, *_ in created:
                (UPLOAD_DIR / stored).unlink(missing_ok=True)
            flash(str(error) if isinstance(error, ValueError) else 'Nie udało się zapisać zamówienia. Spróbuj ponownie.', 'error')
    return render_template('new_order.html', title='Nowe zamówienie', selected_service=request.args.get('service', ''))


@app.route('/zalacznik/<int:file_id>')
def attachment(file_id):
    user = current_user()
    if not user:
        abort(403)
    with connection() as con:
        file = con.execute('SELECT f.*,o.user_id FROM order_files f JOIN orders o ON o.id=f.order_id WHERE f.id=?', (file_id,)).fetchone()
    if not file or (user['role'] != 'admin' and user['id'] != file['user_id']):
        abort(404)
    return send_from_directory(UPLOAD_DIR, file['stored_name'],
                               mimetype=file['content_type'],
                               as_attachment=file['kind'] != 'image',
                               download_name=file['original_name'],
                               max_age=0)


def recovery_configured():
    base = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    parsed = urlparse(base)
    allowed_local = parsed.hostname in ('localhost', '127.0.0.1') and parsed.scheme == 'http'
    return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM') and
                parsed.netloc and (parsed.scheme == 'https' or allowed_local))


def send_recovery_email(email, link):
    message = EmailMessage()
    message['Subject'] = 'DruxMat — ustaw nowe hasło'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = email
    message.set_content('Otrzymaliśmy prośbę o ustawienie nowego hasła.\n\n'
                        f'Aby ustawić nowe hasło, otwórz ten link (ważny 30 minut):\n{link}\n\n'
                        'Jeśli to nie Ty, zignoruj tę wiadomość.\n')
    host = os.environ['SMTP_HOST']
    port = int(os.environ.get('SMTP_PORT', '587'))
    with (smtplib.SMTP_SSL(host, port, timeout=12, context=ssl.create_default_context())
          if port == 465 else smtplib.SMTP(host, port, timeout=12)) as server:
        if port != 465:
            server.starttls(context=ssl.create_default_context())
        if os.environ.get('SMTP_USER'):
            server.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        server.send_message(message)


@app.route('/odzyskaj-haslo', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()[:200]
        if not EMAIL_RE.fullmatch(email):
            flash('Podaj poprawny adres e-mail.', 'error')
        elif not recovery_configured():
            flash('Odzyskiwanie przez e-mail nie jest jeszcze skonfigurowane na serwerze. Skontaktuj się z DruxMat.', 'error')
        else:
            # Rate limit by account and caller address; do not disclose whether an account exists.
            scope_email = attempt_token(email, 'reset')
            scope_ip = attempt_token(request.remote_addr or 'unknown', 'reset-ip')
            if limited(scope_email) or limited(scope_ip):
                flash('Zbyt wiele prób. Spróbuj ponownie za około 15 minut.', 'error')
            else:
                record_failure(scope_email)
                record_failure(scope_ip)
                with connection() as con:
                    account = con.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
                if account:
                    raw = secrets.token_urlsafe(40)
                    hashed = hashlib.sha256(raw.encode('ascii')).hexdigest()
                    expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
                    with connection() as con:
                        con.execute('DELETE FROM password_reset_tokens WHERE user_id=?', (account['id'],))
                        con.execute('INSERT INTO password_reset_tokens(token_hash,user_id,expires_at) VALUES(?,?,?)',
                                    (hashed, account['id'], expiry))
                        con.commit()
                    link = os.environ['PUBLIC_BASE_URL'].strip().rstrip('/') + url_for('reset_password', token=raw)
                    try:
                        send_recovery_email(email, link)
                    except (OSError, smtplib.SMTPException, KeyError, ValueError):
                        with connection() as con:
                            con.execute('DELETE FROM password_reset_tokens WHERE token_hash=?', (hashed,))
                            con.commit()
                        app.logger.exception('Nie udało się wysłać e-maila odzyskiwania hasła.')
                flash('Jeśli istnieje konto z tym adresem i poczta jest dostępna, otrzymasz wiadomość z linkiem do ustawienia hasła.', 'success')
    return render_template('forgot_password.html', title='Odzyskaj hasło')


@app.route('/ustaw-nowe-haslo/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if len(token) > 200:
        abort(404)
    hashed = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with connection() as con:
        token_data = con.execute('SELECT p.user_id,p.expires_at,u.role FROM password_reset_tokens p '
                                 'JOIN users u ON u.id=p.user_id WHERE token_hash=?', (hashed,)).fetchone()
    valid = bool(token_data and token_data['expires_at'] > datetime.now(timezone.utc).isoformat())
    if not valid:
        return render_template('reset_password.html', title='Link wygasł', valid=False), 400
    if request.method == 'POST':
        password = request.form.get('password', '')
        repeat = request.form.get('repeat_password', '')
        if not 12 <= len(password) <= 256:
            flash('Nowe hasło musi mieć od 12 do 256 znaków.', 'error')
        elif password != repeat:
            flash('Podane hasła różnią się.', 'error')
        else:
            with connection() as con:
                # Atomically consume single-use link and update password.
                deleted = con.execute('DELETE FROM password_reset_tokens WHERE token_hash=? AND expires_at>?',
                                      (hashed, datetime.now(timezone.utc).isoformat()))
                if not deleted.rowcount:
                    con.rollback()
                    return render_template('reset_password.html', title='Link wygasł', valid=False), 400
                con.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',
                            (generate_password_hash(password), token_data['user_id']))
                con.execute('DELETE FROM password_reset_tokens WHERE user_id=?', (token_data['user_id'],))
                con.commit()
            session.clear()
            flash('Hasło zmienione. Zaloguj się ponownie.', 'success')
            return redirect(url_for('admin_login' if token_data['role'] == 'admin' else 'login'))
    return render_template('reset_password.html', title='Ustaw nowe hasło', valid=True)


@app.route('/admin/logowanie', methods=['GET', 'POST'])
def admin_login():
    user = current_user()
    if user and user['role'] == 'admin':
        return redirect(url_for('admin'))
    if request.method == 'POST':
        login = request.form.get('login', '').strip().lower()[:200]
        password = request.form.get('password', '')
        token = attempt_token(login, 'admin')
        if limited(token):
            flash('Zbyt wiele prób. Spróbuj ponownie za około 15 minut.', 'error')
        else:
            with connection() as con:
                adm = con.execute('SELECT * FROM users WHERE role=? AND (email=? OR login_name=? COLLATE NOCASE)', ('admin', login, login)).fetchone()
            if adm and check_password_hash(adm['password_hash'], password):
                clear_failures(token)
                sign_in(adm)
                return redirect(url_for('admin'))
            record_failure(token)
            flash('Niepoprawne dane administratora.', 'error')
    return render_template('admin_login.html', title='Logowanie administratora')


@app.route('/admin')
@admin_required
def admin():
    selected = request.args.get('status', '')
    search = request.args.get('q', '').strip()[:100]
    conditions = []
    values = []
    if selected in STATUSES:
        conditions.append('o.status=?')
        values.append(selected)
    if search:
        conditions.append('(u.name LIKE ? OR u.email LIKE ? OR CAST(o.id AS TEXT) LIKE ? OR o.service LIKE ?)')
        pattern = '%' + search.replace('%', '\\%').replace('_', '\\_') + '%'
        values.extend([pattern] * 4)
    sql = 'SELECT o.*,u.name,u.email FROM orders o JOIN users u ON u.id=o.user_id'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    sql += ' ORDER BY o.id DESC LIMIT 150'
    with connection() as con:
        orders = con.execute(sql, values).fetchall()
        files = {o['id']: con.execute('SELECT * FROM order_files WHERE order_id=?', (o['id'],)).fetchall() for o in orders}
        stats = {s: 0 for s in STATUSES}
        stats.update({r['status']: r['n'] for r in con.execute('SELECT status, COUNT(*) n FROM orders GROUP BY status')})
        total_clients = con.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    return render_template('admin.html', title='Centrum zamówień', orders=orders,
                           files=files, stats=stats, selected=selected, search=search,
                           total_clients=total_clients)


@app.post('/admin/zamowienie/<int:order_id>')
@admin_required
def update_order(order_id):
    status = request.form.get('status', '')
    note = request.form.get('admin_note', '').strip()
    if status not in STATUSES or len(note) > 2000:
        abort(400)
    with connection() as con:
        cursor = con.execute('UPDATE orders SET status=?,admin_note=? WHERE id=?', (status, note, order_id))
        if not cursor.rowcount:
            abort(404)
        con.commit()
    flash(f'Zamówienie #{order_id} zostało zaktualizowane.', 'success')
    return redirect(url_for('admin'))


@app.errorhandler(413)
def too_big(error):
    flash('Załączniki są za duże. Maksymalnie 12 MB na plik i 24 MB łącznie.', 'error')
    return redirect(url_for('new_order') if current_user() and current_user()['role'] == 'user' else url_for('home'))


init_db()


def initial_admin_from_environment():
    # Initial provisioning only. Never resets an existing admin password at startup.
    initial_password = os.environ.get('DRUXMAT_ADMIN_INITIAL_PASSWORD', '')
    if not initial_password:
        return
    with connection() as con:
        count = con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    if count:
        return
    email = os.environ.get('DRUXMAT_ADMIN_EMAIL', CONTACT_EMAIL)
    login_name = os.environ.get('DRUXMAT_ADMIN_LOGIN', 'DruxMatAdmin')
    create_admin(email, initial_password, login_name)


initial_admin_from_environment()

if IN_PRODUCTION:
    with connection() as con:
        admin_count = con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    if not admin_count:
        raise RuntimeError('Brakuje administratora. Ustaw DRUXMAT_ADMIN_INITIAL_PASSWORD na pierwsze uruchomienie.')

if __name__ == '__main__':
    if not os.environ.get('SECRET_KEY'):
        print('UWAGA: Ustaw SECRET_KEY w środowisku przed publikacją aplikacji.')
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=False)
