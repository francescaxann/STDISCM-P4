CREATE TABLE IF NOT EXISTS users (
 id varchar(36) PRIMARY KEY, username varchar(64) UNIQUE NOT NULL,
 password_hash varchar(60) NOT NULL, role varchar(16) NOT NULL
);
CREATE TABLE IF NOT EXISTS revoked_tokens (jti varchar(64) PRIMARY KEY, expires_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS courses (
 id serial PRIMARY KEY, code varchar(16) UNIQUE NOT NULL, title varchar(128) NOT NULL,
 slots_available integer NOT NULL CHECK (slots_available >= 0)
);
CREATE TABLE IF NOT EXISTS enrollments (
 id serial PRIMARY KEY, student_id varchar(36) REFERENCES users(id), course_id integer REFERENCES courses(id),
 UNIQUE(student_id, course_id)
);
CREATE TABLE IF NOT EXISTS grades (
 id serial PRIMARY KEY, student_id varchar(36) REFERENCES users(id), course_id integer REFERENCES courses(id),
 grade varchar(3) NOT NULL, UNIQUE(student_id, course_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
 id serial PRIMARY KEY, event_type varchar(64), actor_id varchar(36), details text, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS receipts (
 id serial PRIMARY KEY,
 student_id varchar(36) REFERENCES users(id),
 course_id integer REFERENCES courses(id),
 status varchar(32) NOT NULL DEFAULT 'CREATED',
 details text,
 created_at timestamptz DEFAULT now(),
 updated_at timestamptz DEFAULT now()
);

INSERT INTO users(id,username,password_hash,role) VALUES
 ('11111111-1111-1111-1111-111111111111','student','$2b$12$UHfvJWHjtKywbt3qcqPoyOHM6elQrA3iBAt9h2hCEiKhelyuoa.Uq','STUDENT'),
 ('22222222-2222-2222-2222-222222222222','faculty','$2b$12$UHfvJWHjtKywbt3qcqPoyOHM6elQrA3iBAt9h2hCEiKhelyuoa.Uq','FACULTY')
ON CONFLICT (username) DO NOTHING;
INSERT INTO courses(code,title,slots_available) VALUES
 ('CS101','Introduction to Computing',3),('CS201','Data Structures',2),('NET301','Distributed Systems',1)
ON CONFLICT(code) DO NOTHING;
INSERT INTO grades(student_id,course_id,grade) VALUES
 ('11111111-1111-1111-1111-111111111111',1,'A'),
 ('11111111-1111-1111-1111-111111111111',2,'B+')
ON CONFLICT(student_id,course_id) DO UPDATE SET grade=EXCLUDED.grade;
