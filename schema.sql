DROP TABLE IF EXISTS payout_schedule CASCADE;
DROP TABLE IF EXISTS contributions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    is_active INTEGER DEFAULT 1
);

CREATE TABLE contributions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    week_label TEXT NOT NULL,
    amount_paid REAL NOT NULL,
    date_paid TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE payout_schedule (
    id SERIAL PRIMARY KEY,
    rotation_order INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    payout_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- 'completed' or 'pending'
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);