import os
import random
import psycopg2
import psycopg2.extras
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'pamoja_wealth_circle_secret_key'

WEEKLY_CONTRIBUTION = 510.00
TOTAL_MEMBERS = 10


class PostgresWrapper:
    """Wrapper to make psycopg2 connections behave similarly to sqlite3 connection objects"""
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Convert SQLite '?' placeholders to PostgreSQL '%s' placeholders
        query_pg = query.replace('?', '%s')
        if params:
            cur.execute(query_pg, params)
        else:
            cur.execute(query_pg)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set!")
    conn = psycopg2.connect(database_url)
    return PostgresWrapper(conn)


def init_db():
    with app.app_context():
        db = get_db()

        # 1. Ensure base tables exist (PostgreSQL syntax with SERIAL)
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                is_active INTEGER DEFAULT 1
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS contributions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                week_label TEXT NOT NULL,
                amount_paid REAL NOT NULL,
                date_paid TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS payout_schedule (
                id SERIAL PRIMARY KEY,
                rotation_order INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                payout_date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')

        # 2. Safe Column Migrations
        try:
            db.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1')
        except Exception:
            pass

        try:
            db.execute("ALTER TABLE payout_schedule ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
        except Exception:
            pass

        db.commit()

        # 3. Purge duplicates
        try:
            db.execute('''
                DELETE FROM users WHERE id NOT IN (
                    SELECT MIN(id) FROM users GROUP BY username
                )
            ''')
            db.commit()
        except Exception:
            pass

        # 4. Auto-seed official members with secure unique admin passwords
        flyer_members = [
            ('Vivian Nyaga', 'vivian', 'admin', 'vivianAdmin2026!'),
            ('Purity Murugi', 'purity', 'member', 'pamoja123'),
            ('Mukiti Ann', 'ann.mukiti', 'member', 'pamoja123'),
            ('Mercy Miraj', 'mercy.miraj', 'admin', 'mercyAdmin2026!'),
            ('Ann Murimi', 'ann.murimi', 'member', 'pamoja123'),
            ('Shirleen Wambui', 'shirleen', 'admin', 'shirleenAdmin2026!'),
            ('Simon Maina', 'simon', 'member', 'pamoja123'),
            ('Lydiah Muchira', 'lydiah', 'member', 'pamoja123'),
            ('Mercy Wanjiku', 'mercy.wanjiku', 'member', 'pamoja123'),
            ('Maureen Wambui', 'maureen', 'member', 'pamoja123'),
        ]

        valid_usernames = [m[1] for m in flyer_members]
        placeholders = ','.join(['?'] * len(valid_usernames))
        db.execute(
            f'UPDATE users SET is_active = 0 WHERE username NOT IN ({placeholders})',
            tuple(valid_usernames),
        )

        for full_name, username, role, default_pass in flyer_members:
            existing_user = db.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
            if not existing_user:
                db.execute(
                    'INSERT INTO users (full_name, username, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)',
                    (
                        full_name,
                        username,
                        generate_password_hash(default_pass),
                        role,
                    ),
                )
            else:
                db.execute(
                    'UPDATE users SET is_active = 1, full_name = ?, role = ? WHERE username = ?',
                    (full_name, role, username),
                )
        db.commit()

        # 5. Seed payout schedule
        seed_preplanned_schedule(db)


def seed_preplanned_schedule(db):
    db.execute('DELETE FROM payout_schedule')

    preplanned_schedule = [
        (1, 'Vivian Nyaga', 'Sunday, Nov 1, 2026', 'completed'),
        (2, 'Purity Murugi', 'Sunday, Nov 8, 2026', 'completed'),
        (3, 'Mukiti Ann', 'Sunday, Nov 15, 2026', 'pending'),
        (4, 'Mercy Miraj', 'Sunday, Nov 22, 2026', 'pending'),
        (5, 'Ann Murimi', 'Sunday, Nov 29, 2026', 'pending'),
        (6, 'Shirleen Wambui', 'Sunday, Dec 6, 2026', 'pending'),
        (7, 'Simon Maina', 'Sunday, Dec 13, 2026', 'pending'),
        (8, 'Lydiah Muchira', 'Sunday, Dec 20, 2026', 'pending'),
        (9, 'Mercy Wanjiku', 'Sunday, Dec 27, 2026', 'pending'),
        (10, 'Maureen Wambui', 'Sunday, Jan 3, 2027', 'pending'),
    ]

    for order, name, date_str, status in preplanned_schedule:
        user = db.execute(
            'SELECT id FROM users WHERE full_name LIKE ?', (f'%{name}%',)
        ).fetchone()
        if user:
            db.execute(
                'INSERT INTO payout_schedule (rotation_order, user_id, payout_date, status) VALUES (?, ?, ?, ?)',
                (order, user['id'], date_str, status),
            )
    db.commit()


@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE LOWER(username) = ? AND is_active = 1',
            (username,),
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f"Welcome back, {user['full_name']}!", 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/change-password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('dashboard'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters long.', 'warning')
        return redirect(url_for('dashboard'))

    db = get_db()
    user = db.execute(
        'SELECT password_hash FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()

    if user and check_password_hash(user['password_hash'], current_password):
        db.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), session['user_id']),
        )
        db.commit()
        flash('Password changed successfully!', 'success')
    else:
        flash('Incorrect current password.', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/admin/add-member', methods=['POST'])
def admin_add_member():
    if session.get('role') != 'admin':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('dashboard'))

    full_name = request.form['full_name']
    username = request.form['username'].strip().lower()
    password = request.form['password']
    role = request.form.get('role', 'member')

    db = get_db()
    active_count = db.execute(
        'SELECT COUNT(*) AS cnt FROM users WHERE is_active = 1'
    ).fetchone()['cnt']
    
    if active_count >= TOTAL_MEMBERS:
        flash(
            f'Pamoja Wealth Circle is capped at exactly {TOTAL_MEMBERS} active members.',
            'warning',
        )
        return redirect(url_for('dashboard'))

    try:
        db.execute(
            'INSERT INTO users (full_name, username, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)',
            (full_name, username, generate_password_hash(password), role),
        )
        db.commit()
        seed_preplanned_schedule(db)
        flash(f'Member {full_name} added successfully as {role.upper()}!', 'success')
    except Exception:
        flash('Username already exists.', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/admin/promote-admin/<int:user_id>', methods=['POST'])
def promote_admin(user_id):
    if session.get('role') != 'admin':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('dashboard'))

    db = get_db()
    db.execute(
        "UPDATE users SET role = 'admin' WHERE id = ? AND is_active = 1",
        (user_id,),
    )
    db.commit()
    flash('Member successfully promoted to Admin status!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/edit-member/<int:user_id>', methods=['POST'])
def edit_member(user_id):
    if session.get('role') != 'admin':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('dashboard'))

    full_name = request.form['full_name']
    username = request.form['username'].strip().lower()
    new_password = request.form['password']

    db = get_db()
    try:
        if new_password.strip():
            db.execute(
                'UPDATE users SET full_name = ?, username = ?, password_hash = ? WHERE id = ?',
                (full_name, username, generate_password_hash(new_password), user_id),
            )
        else:
            db.execute(
                'UPDATE users SET full_name = ?, username = ? WHERE id = ?',
                (full_name, username, user_id),
            )
        db.commit()
        flash('Member details updated successfully!', 'success')
    except Exception:
        flash('Username already taken by another user.', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/admin/remove-member/<int:user_id>', methods=['POST'])
def remove_member(user_id):
    if session.get('role') != 'admin':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('dashboard'))

    if user_id == session.get('user_id'):
        flash('You cannot remove yourself while logged in.', 'danger')
        return redirect(url_for('dashboard'))

    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.execute('DELETE FROM payout_schedule WHERE user_id = ?', (user_id,))
    db.commit()

    flash('Member has been permanently removed from the Chama roster.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/admin/mark-paid/<int:user_id>', methods=['POST'])
def admin_mark_paid(user_id):
    if session.get('role') != 'admin':
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('dashboard'))

    current_week = 'Week of Nov 9 - Nov 15, 2026'
    db = get_db()

    existing = db.execute(
        'SELECT id FROM contributions WHERE user_id = ? AND week_label = ?',
        (user_id, current_week),
    ).fetchone()

    if not existing:
        db.execute(
            'INSERT INTO contributions (user_id, week_label, amount_paid) VALUES (?, ?, ?)',
            (user_id, current_week, WEEKLY_CONTRIBUTION),
        )
        db.commit()
        flash('Member contribution verified and marked as PAID!', 'success')
    else:
        flash('This member is already marked as paid for this week.', 'info')

    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    seed_preplanned_schedule(db)

    current_user = db.execute(
        'SELECT role FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    if current_user:
        session['role'] = current_user['role']
        session.modified = True

    current_week = 'Week of Nov 9 - Nov 15, 2026'

    members = db.execute(
        '''
            SELECT u.id, u.full_name, u.username, u.role,
                   COALESCE(SUM(c.amount_paid), 0) AS total_contributed,
                   MAX(CASE WHEN c.week_label = ? THEN 1 ELSE 0 END) AS paid_current_week
            FROM users u
            LEFT JOIN contributions c ON u.id = c.user_id
            WHERE u.is_active = 1
            GROUP BY u.id, u.full_name, u.username, u.role
            ORDER BY CASE WHEN u.role = 'admin' THEN 0 ELSE 1 END, u.full_name ASC
        ''',
        (current_week,),
    ).fetchall()

    total_pool = sum(m['total_contributed'] for m in members)
    weekly_target_pool = TOTAL_MEMBERS * WEEKLY_CONTRIBUTION

    schedule = db.execute('''
        SELECT ps.rotation_order, ps.payout_date, ps.status, u.full_name
        FROM payout_schedule ps
        JOIN users u ON ps.user_id = u.id
        ORDER BY ps.rotation_order ASC
    ''').fetchall()

    pending_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM payout_schedule WHERE status != 'completed'"
    ).fetchone()['cnt']
    shuffle_unlocked = pending_count == 0

    chart_labels = [m['full_name'] for m in members]
    chart_data = [m['total_contributed'] for m in members]

    return render_template(
        'dashboard.html',
        members=members,
        total_pool=total_pool,
        weekly_target=weekly_target_pool,
        current_week=current_week,
        schedule=schedule,
        shuffle_unlocked=shuffle_unlocked,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )


@app.route('/shuffle', methods=['POST'])
def shuffle():
    if session.get('role') != 'admin':
        flash('Only the Admin can trigger the Sunday rotation shuffle.', 'danger')
        return redirect(url_for('dashboard'))

    db = get_db()
    pending_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM payout_schedule WHERE status != 'completed'"
    ).fetchone()['cnt']
    
    if pending_count > 0:
        flash(
            'Shuffle is locked! All members must complete their pre-planned first round of payouts before reshuffling.',
            'warning',
        )
        return redirect(url_for('dashboard'))

    members = db.execute('SELECT id FROM users WHERE is_active = 1').fetchall()
    member_ids = [m['id'] for m in members]
    random.shuffle(member_ids)

    db.execute('DELETE FROM payout_schedule')

    sundays = [
        'Sunday, Jan 10, 2027',
        'Sunday, Jan 17, 2027',
        'Sunday, Jan 24, 2027',
        'Sunday, Jan 31, 2027',
        'Sunday, Feb 7, 2027',
        'Sunday, Feb 14, 2027',
        'Sunday, Feb 21, 2027',
        'Sunday, Feb 28, 2027',
        'Sunday, Mar 7, 2027',
        'Sunday, Mar 14, 2027',
    ]

    for order, u_id in enumerate(member_ids, start=1):
        sunday_date = (
            sundays[order - 1]
            if order <= len(sundays)
            else f'Week {order} Sunday'
        )
        db.execute(
            'INSERT INTO payout_schedule (rotation_order, user_id, payout_date, status) VALUES (?, ?, ?, ?)',
            (order, u_id, sunday_date, 'pending'),
        )

    db.commit()
    flash(
        'First round completed! New random Sunday payout cycle successfully locked.',
        'success',
    )
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)