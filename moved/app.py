from flask import Flask, render_template, request, redirect, session
import sqlite3
import re
import ollama

app = Flask(__name__)
app.secret_key = 'your_secret_key'


@app.route('/review_answers/<int:exam_id>/<int:student_id>', methods=['GET', 'POST'])
def review_answers(exam_id, student_id):
    if 'teacher_id' not in session:
        return redirect('/login_teacher')

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        # Fetch exam title
        cursor.execute("SELECT title FROM Exam WHERE id = ?", (exam_id,))
        exam_title = cursor.fetchone()[0]

        # Fetch student name
        cursor.execute("SELECT username FROM Student WHERE id = ?", (student_id,))
        student_name = cursor.fetchone()[0]

        # Fetch student's answers with AI marks
        cursor.execute("""
            SELECT Question.question_text, Answer.answer_text, Answer.earned_marks, Question.total_marks, Answer.feedback, Answer.id
            FROM Answer
            JOIN Question ON Answer.question_id = Question.id
            WHERE Answer.student_id = ? AND Question.exam_id = ?
        """, (student_id, exam_id))
        answers = cursor.fetchall()  # (question_text, answer_text, earned_marks, total_marks, feedback, answer_id)

    if request.method == 'POST':
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            for answer in answers:
                answer_id = answer[5]
                new_marks = request.form.get(f'marks_{answer_id}', answer[2])
                cursor.execute("UPDATE Answer SET earned_marks = ? WHERE id = ?", (new_marks, answer_id))
            conn.commit()
        return redirect(f'/exam_details/{exam_id}')  # Redirect back to exam details after saving

    return render_template('review_answers.html', exam_id=exam_id, student_id=student_id, exam_title=exam_title, student_name=student_name, answers=answers)


def evaluate_answer(question, answer, answer_key, max_score):
    reasoning_prompt = (f"'{answer}' is an answer written by a student for the question '{question}'. "
                        f"The marking condition is '{answer_key}'. "
                        f"Carefully evaluate the answer and decide how many marks out of {max_score} should be given. "
                        f"Explain your reasoning in detail before stating the final score.")

    extract_prompt_template = ("Here is a detailed evaluation of a student's answer:\n\n"
                               "{deepseek_response}\n\n"
                               f"From the above evaluation, extract only the final marks (out of {max_score}). "
                               "Do not include any explanations, just return the number.")

    for _ in range(3):  # Try 3 times if AI doesn't return a valid number
        # Step 1: Get detailed reasoning from DeepSeek
        deepseek_response = ollama.chat(model="deepseek-r1:8b", messages=[{"role": "user", "content": reasoning_prompt}])
        deepseek_text = deepseek_response['message']['content'].strip()

        print(f"\n****************************************************************\nDeepSeek Response: {deepseek_text}")

        # Step 2: Extract marks using LLaMA
        extract_prompt = extract_prompt_template.format(deepseek_response=deepseek_text)
        extract_response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": extract_prompt}])
        extract_text = extract_response['message']['content'].strip()

        print(f"\n****************************************************************\nLLaMA Extraction: {extract_text}")

        # Extract numerical value from LLaMA response (handling decimals)
        match = re.search(r'\d+(\.\d+)?', extract_text)  # Matches integers and decimals
        if match:
            score = float(match.group())  # Convert to float for decimal support
            score = round(score, 2)  # Round to 2 decimal places for better accuracy

            if score <= max_score:
                print(f"Final Score: {score}")

                # Step 3: Get AI feedback from DeepSeek
                feedback_text = deepseek_text

                print(f"\n****************************************************************\nAI Reasoning: {feedback_text}")

                return score, feedback_text

    return -1, "AI could not generate feedback."  # Return -1 if AI fails after 3 attempts

import sqlite3

def init_db():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        
        # Create tables
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
                            total_marks INTEGER,
                            answer_key TEXT)''')  # ✅ Includes answer key for auto-grading

        cursor.execute('''CREATE TABLE IF NOT EXISTS Answer (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question_id INTEGER,
                            student_id INTEGER,
                            answer_text TEXT,
                            earned_marks REAL,  -- ✅ Changed from INTEGER to REAL
                            feedback TEXT)''')  # ✅ Feedback column included

        cursor.execute('''CREATE TABLE IF NOT EXISTS Attended (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            student_id INTEGER,
                            exam_id INTEGER,
                            earned_total REAL)''')  # ✅ Changed from INTEGER to REAL

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

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        # Check if student has already attempted the exam
        cursor.execute("SELECT id FROM Attended WHERE student_id = ? AND exam_id = ?", (student_id, exam_id))
        attempted = cursor.fetchone()

        if attempted:
            return render_template('message.html', message="You have already attempted this exam.")

        if request.method == 'POST':
            cursor.execute("SELECT id, question_text, total_marks, answer_key FROM Question WHERE exam_id = ?", (exam_id,))
            questions = cursor.fetchall()
            
            total_earned = 0
            for question_id, question_text, max_marks, answer_key in questions:
                answer_text = request.form.get(f'answer_{question_id}', '').strip()
                
                # AI-based evaluation with the answer key
                earned_marks, feedback = evaluate_answer(question_text, answer_text, answer_key, max_marks)
                total_earned += earned_marks if earned_marks != -1 else 0  # Ignore if AI fails
                
                cursor.execute("INSERT INTO Answer (question_id, student_id, answer_text, earned_marks, feedback) VALUES (?, ?, ?, ?, ?)",
                               (question_id, student_id, answer_text, earned_marks, feedback))
            
            cursor.execute("INSERT INTO Attended (student_id, exam_id, earned_total) VALUES (?, ?, ?)",
                           (student_id, exam_id, total_earned))
            conn.commit()
        
            return render_template('message.html', message="Exam submitted successfully!")
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
        
        # Fetch total earned marks
        cursor.execute("SELECT earned_total FROM Attended WHERE student_id = ? AND exam_id = ?", (student_id, exam_id))
        result = cursor.fetchone()
        
        # Fetch each question, student's answer, earned marks, max marks, and feedback
        cursor.execute("""
            SELECT Question.question_text, Answer.answer_text, Answer.earned_marks, Question.total_marks, Answer.feedback
            FROM Answer
            JOIN Question ON Answer.question_id = Question.id
            WHERE Answer.student_id = ? AND Question.exam_id = ?
        """, (student_id, exam_id))
        
        answers = cursor.fetchall()  # List of (question_text, answer_text, earned_marks, max_marks, feedback)

    return render_template('view_result.html', result=result, answers=answers)

@app.route('/create_exam', methods=['GET', 'POST'])
def create_exam():
    if 'teacher_id' not in session:
        return redirect('/login_teacher')
    
    if request.method == 'POST':
        title = request.form['title']
        questions = request.form.getlist('question_text[]')
        question_marks = request.form.getlist('question_marks[]')
        answer_keys = request.form.getlist('answer_key[]')  # ✅ Capture answer keys

        # Calculate total marks dynamically
        total_marks = sum(map(int, question_marks))

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Exam (teacher_id, title, total_marks) VALUES (?, ?, ?)",
                           (session['teacher_id'], title, total_marks))
            exam_id = cursor.lastrowid

            for question_text, marks, answer_key in zip(questions, question_marks, answer_keys):
                cursor.execute("INSERT INTO Question (exam_id, question_text, total_marks, answer_key) VALUES (?, ?, ?, ?)",
                               (exam_id, question_text, marks, answer_key))

            conn.commit()

        return redirect('/dashboard_teacher')
    
    return render_template('create_exam.html')



@app.route('/exam_details/<int:exam_id>')
def exam_details(exam_id):
    if 'teacher_id' not in session:
        return redirect('/login_teacher')

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        # Fetch exam details
        cursor.execute("SELECT * FROM Exam WHERE id = ?", (exam_id,))
        exam = cursor.fetchone()

        # Fetch students who attended
        cursor.execute("""
            SELECT Student.username, Attended.earned_total, Student.id
            FROM Attended
            JOIN Student ON Attended.student_id = Student.id
            WHERE Attended.exam_id = ?
        """, (exam_id,))
        students = cursor.fetchall()  # (username, earned_total, student_id)

    return render_template('exam_details.html', exam=exam, students=students)
if __name__ == '__main__':
    init_db()
    app.run(debug=True)