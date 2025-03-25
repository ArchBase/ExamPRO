from flask import Flask, render_template, request, redirect, session
import sqlite3
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def init_db():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS Student (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT,
                            reg_no TEXT,
                            email TEXT,
                            password TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Teacher (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT,
                            email TEXT,
                            password TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Exam (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            teacher_id INTEGER,
                            title TEXT,
                            total_marks INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Question (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            exam_id INTEGER,
                            question_text TEXT,
                            total_marks INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Answer (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question_id INTEGER,
                            student_id INTEGER,
                            answer_text TEXT,
                            earned_marks INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS Attended (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_id INTEGER,
                            exam_id INTEGER,
                            earned_total INTEGER)''')
        conn.commit()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/signup_student', methods=['GET', 'POST'])
def signup_student():
    if request.method == 'POST':
        username = request.form['username']
        reg_no = request.form['reg_no']
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Student (username, reg_no, email, password) VALUES (?, ?, ?, ?)",
                           (username, reg_no, email, password))
            conn.commit()
        return redirect('/login_student')
    return render_template('signup_student.html')

@app.route('/login_student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Student WHERE email = ? AND password = ?", (email, password))
            student = cursor.fetchone()
            if student:
                session['student_id'] = student[0]
                return redirect('/dashboard_student')
    return render_template('login_student.html')

@app.route('/signup_teacher', methods=['GET', 'POST'])
def signup_teacher():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Teacher (username, email, password) VALUES (?, ?, ?)",
                           (username, email, password))
            conn.commit()
        return redirect('/login_teacher')
    return render_template('signup_teacher.html')

@app.route('/login_teacher', methods=['GET', 'POST'])
def login_teacher():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM Teacher WHERE email = ? AND password = ?", (email, password))
            teacher = cursor.fetchone()
            if teacher:
                session['teacher_id'] = teacher[0]
                return redirect('/dashboard_teacher')
    return render_template('login_teacher.html')

@app.route('/dashboard_student', methods=['GET', 'POST'])
def dashboard_student():
    if 'student_id' not in session:
        return redirect('/login_student')
    if request.method == 'POST':
        exam_code = request.form['exam_code']
        return redirect(f'/write_exam/{exam_code}')
    student_id = session['student_id']
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT Exam.id, Exam.title, Attended.earned_total FROM Exam JOIN Attended ON Exam.id = Attended.exam_id WHERE Attended.student_id = ?", (student_id,))
        exams = cursor.fetchall()
    return render_template('dashboard_student.html', exams=exams)

@app.route('/dashboard_teacher')
def dashboard_teacher():
    if 'teacher_id' not in session:
        return redirect('/login_teacher')
    teacher_id = session['teacher_id']
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Exam WHERE teacher_id = ?", (teacher_id,))
        exams = cursor.fetchall()
    return render_template('dashboard_teacher.html', exams=exams)

@app.route('/write_exam/<int:exam_id>', methods=['GET', 'POST'])
def write_exam(exam_id):
    if 'student_id' not in session:
        return redirect('/login_student')
    student_id = session['student_id']
    if request.method == 'POST':
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Question WHERE exam_id = ?", (exam_id,))
            questions = cursor.fetchall()
            total_earned = 0
            for question in questions:
                question_id = question[0]
                answer_text = request.form[f'answer_{question_id}']
                earned_marks = random.randint(0, 10)  # Random marks for simplicity
                total_earned += earned_marks
                cursor.execute("INSERT INTO Answer (question_id, student_id, answer_text, earned_marks) VALUES (?, ?, ?, ?)",
                               (question_id, student_id, answer_text, earned_marks))
            cursor.execute("INSERT INTO Attended (student_id, exam_id, earned_total) VALUES (?, ?, ?)",
                           (student_id, exam_id, total_earned))
            conn.commit()
        return redirect('/dashboard_student')
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Question WHERE exam_id = ?", (exam_id,))
        questions = cursor.fetchall()
    return render_template('write_exam.html', questions=questions)

@app.route('/view_result/<int:exam_id>')
def view_result(exam_id):
    if 'student_id' not in session:
        return redirect('/login_student')
    student_id = session['student_id']
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT earned_total FROM Attended WHERE student_id = ? AND exam_id = ?", (student_id, exam_id))
        result = cursor.fetchone()
    return render_template('view_result.html', result=result)


@app.route('/create_exam', methods=['GET', 'POST'])
def create_exam():
    if 'teacher_id' not in session:
        return redirect('/login_teacher')
    
    if request.method == 'POST':
        title = request.form['title']
        questions = request.form.getlist('question_text[]')
        question_marks = request.form.getlist('question_marks[]')

        # Calculate total marks dynamically
        total_marks = sum(map(int, question_marks))

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Exam (teacher_id, title, total_marks) VALUES (?, ?, ?)",
                           (session['teacher_id'], title, total_marks))
            exam_id = cursor.lastrowid

            for question_text, marks in zip(questions, question_marks):
                cursor.execute("INSERT INTO Question (exam_id, question_text, total_marks) VALUES (?, ?, ?)",
                               (exam_id, question_text, marks))

            conn.commit()

        return redirect('/dashboard_teacher')
    
    return render_template('create_exam.html')


@app.route('/exam_details/<int:exam_id>')
def exam_details(exam_id):
    if 'teacher_id' not in session:
        return redirect('/login_teacher')
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Exam WHERE id = ?", (exam_id,))
        exam = cursor.fetchone()
        cursor.execute("SELECT Student.username, Attended.earned_total FROM Attended JOIN Student ON Attended.student_id = Student.id WHERE Attended.exam_id = ?", (exam_id,))
        students = cursor.fetchall()
    return render_template('exam_details.html', exam=exam, students=students)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)