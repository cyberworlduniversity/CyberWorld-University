CREATE DATABASE IF NOT EXISTS cwu CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cwu;

CREATE TABLE IF NOT EXISTS users (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 name VARCHAR(120) NOT NULL,
 email VARCHAR(190) NOT NULL UNIQUE,
 password_hash VARCHAR(255) NOT NULL,
 role ENUM('student','admin') NOT NULL DEFAULT 'student',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_categories (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 name VARCHAR(120) NOT NULL UNIQUE,
 slug VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS courses (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 category_id INT UNSIGNED NULL,
 title VARCHAR(200) NOT NULL,
 slug VARCHAR(220) NOT NULL UNIQUE,
 description TEXT NOT NULL,
 thumbnail VARCHAR(500),
 instructor VARCHAR(150),
 level VARCHAR(50),
 duration_minutes INT UNSIGNED DEFAULT 0,
 price DECIMAL(10,2) DEFAULT 0,
 is_free BOOLEAN DEFAULT TRUE,
 objectives TEXT,
 requirements TEXT,
 syllabus TEXT,
 status ENUM('draft','published','archived') DEFAULT 'draft',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 FOREIGN KEY(category_id) REFERENCES course_categories(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS course_phases (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 course_id INT UNSIGNED NOT NULL,
 title VARCHAR(200) NOT NULL,
 description TEXT,
 sort_order INT UNSIGNED DEFAULT 0,
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lessons (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 phase_id INT UNSIGNED NOT NULL,
 title VARCHAR(200) NOT NULL,
 description TEXT,
 content LONGTEXT,
 sort_order INT UNSIGNED DEFAULT 0,
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(phase_id) REFERENCES course_phases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS videos (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 lesson_id INT UNSIGNED NOT NULL,
 title VARCHAR(200) NOT NULL,
 description TEXT,
 video_url VARCHAR(1000) NOT NULL,
 thumbnail_url VARCHAR(1000),
 duration_seconds INT UNSIGNED DEFAULT 0,
 sort_order INT UNSIGNED DEFAULT 0,
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS materials (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 lesson_id INT UNSIGNED NULL,
 title VARCHAR(200) NOT NULL,
 description TEXT,
 file_url VARCHAR(1000) NOT NULL,
 file_type VARCHAR(100),
 file_size BIGINT UNSIGNED DEFAULT 0,
 status ENUM('draft','published') DEFAULT 'draft',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS questions (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 course_id INT UNSIGNED NOT NULL,
 phase_id INT UNSIGNED NULL,
 topic VARCHAR(150),
 question_type ENUM('mcq','true_false') DEFAULT 'mcq',
 question TEXT NOT NULL,
 explanation TEXT,
 correct_answer VARCHAR(20) NOT NULL,
 marks INT UNSIGNED DEFAULT 1,
 difficulty ENUM('easy','medium','hard') DEFAULT 'medium',
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
 FOREIGN KEY(phase_id) REFERENCES course_phases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS question_options (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 question_id INT UNSIGNED NOT NULL,
 option_key CHAR(1) NOT NULL,
 option_text TEXT NOT NULL,
 UNIQUE KEY uq_question_option(question_id,option_key),
 FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quizzes (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 course_id INT UNSIGNED NOT NULL,
 phase_id INT UNSIGNED NULL,
 title VARCHAR(200) NOT NULL,
 question_count INT UNSIGNED DEFAULT 10,
 duration_seconds INT UNSIGNED DEFAULT 600,
 passing_percent DECIMAL(5,2) DEFAULT 60,
 max_attempts INT UNSIGNED DEFAULT 1,
 randomize_questions BOOLEAN DEFAULT TRUE,
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
 FOREIGN KEY(phase_id) REFERENCES course_phases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS quiz_questions (
 quiz_id INT UNSIGNED NOT NULL,
 question_id INT UNSIGNED NOT NULL,
 sort_order INT UNSIGNED DEFAULT 0,
 PRIMARY KEY(quiz_id,question_id),
 FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
 FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exams (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 course_id INT UNSIGNED NOT NULL,
 title VARCHAR(200) NOT NULL,
 question_count INT UNSIGNED DEFAULT 50,
 duration_seconds INT UNSIGNED DEFAULT 3600,
 passing_percent DECIMAL(5,2) DEFAULT 60,
 max_attempts INT UNSIGNED DEFAULT 1,
 randomize_questions BOOLEAN DEFAULT TRUE,
 certificate_required BOOLEAN DEFAULT TRUE,
 status ENUM('draft','published') DEFAULT 'draft',
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_questions (
 exam_id INT UNSIGNED NOT NULL,
 question_id INT UNSIGNED NOT NULL,
 sort_order INT UNSIGNED DEFAULT 0,
 PRIMARY KEY(exam_id,question_id),
 FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE,
 FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enrollments (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NOT NULL,
 course_id INT UNSIGNED NOT NULL,
 enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_enrollment(user_id,course_id),
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_progress (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NOT NULL,
 lesson_id INT UNSIGNED NOT NULL,
 completed BOOLEAN DEFAULT FALSE,
 completed_at TIMESTAMP NULL,
 UNIQUE KEY uq_progress(user_id,lesson_id),
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NOT NULL,
 quiz_id INT UNSIGNED NOT NULL,
 score DECIMAL(7,2) DEFAULT 0,
 passed BOOLEAN DEFAULT FALSE,
 started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 submitted_at TIMESTAMP NULL,
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_attempts (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NOT NULL,
 exam_id INT UNSIGNED NOT NULL,
 score DECIMAL(7,2) DEFAULT 0,
 passed BOOLEAN DEFAULT FALSE,
 started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 submitted_at TIMESTAMP NULL,
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS certificates (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NOT NULL,
 course_id INT UNSIGNED NOT NULL,
 certificate_number VARCHAR(100) NOT NULL UNIQUE,
 completion_date DATE NOT NULL,
 verification_code VARCHAR(120) NOT NULL UNIQUE,
 file_url VARCHAR(1000),
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
 FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS advertisements (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 title VARCHAR(200) NOT NULL,
 description TEXT,
 image_url VARCHAR(1000),
 button_text VARCHAR(80),
 target_url VARCHAR(1000),
 starts_at DATETIME,
 ends_at DATETIME,
 enabled BOOLEAN DEFAULT TRUE,
 sort_order INT UNSIGNED DEFAULT 0,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 user_id INT UNSIGNED NULL,
 rating TINYINT UNSIGNED NOT NULL,
 review_text TEXT NOT NULL,
 status ENUM('pending','published','rejected') DEFAULT 'pending',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS website_content (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 content_key VARCHAR(150) NOT NULL UNIQUE,
 content_value LONGTEXT,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 setting_key VARCHAR(150) NOT NULL UNIQUE,
 setting_value LONGTEXT,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO course_categories(name,slug) VALUES
('Cyber Security Fundamentals','cyber-security-fundamentals'),
('Ethical Hacking','ethical-hacking'),
('Network Security','network-security'),
('Web Security','web-security'),
('Digital Forensics','digital-forensics'),
('Python for Cybersecurity','python-for-cybersecurity');