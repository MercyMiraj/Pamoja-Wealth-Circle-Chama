DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS contributions;
DROP TABLE IF EXISTS payout_schedule;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    is_active INTEGER DEFAULT 1
);

CREATE TABLE contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    week_label TEXT NOT NULL,
    amount_paid REAL NOT NULL,
    date_paid TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE payout_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rotation_order INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    payout_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending' -- 'completed' or 'pending'
);