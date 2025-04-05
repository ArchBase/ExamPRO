from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import sqlite3
import re
import ollama

app = Flask(__name__)
app.secret_key = 'your_secret_key'
import threading


def re_evaluate_single_answer(answer_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT Question.question_text, Answer.answer_text, Question.answer_key, Question.total_marks
            FROM Answer
            JOIN Question ON Answer.question_id = Question.id
            WHERE Answer.id = ?
        """, (answer_id,))
        data = cursor.fetchone()
        
        if data:
            question_text, answer_text, answer_key, max_marks = data
            new_marks, new_feedback = evaluate_answer(question_text, answer_text, answer_key, max_marks)

            cursor.execute("UPDATE Answer SET earned_marks = ?, feedback = ? WHERE id = ?", 
                           (new_marks, new_feedback, answer_id))
            conn.commit()



def evaluate_in_background(student_id, exam_id):
    total_earned = 0

    # Fetch all questions before processing to minimize DB time
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, question_text, total_marks, answer_key FROM Question WHERE exam_id = ?", (exam_id,))
        questions = cursor.fetchall()

    for question_id, question_text, max_marks, answer_key in questions:
        # Fetch answer text for the question
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT answer_text FROM Answer WHERE student_id = ? AND question_id = ?", (student_id, question_id))
            result = cursor.fetchone()

        if result:
            answer_text = result[0]

            # AI-based evaluation (outside DB operation)
            earned_marks, feedback = evaluate_answer(question_text, answer_text, answer_key, max_marks)
            total_earned += earned_marks if earned_marks != -1 else 0

            # Update the Answer row immediately after evaluation
            with sqlite3.connect('database.db') as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE Answer SET earned_marks = ?, feedback = ? WHERE student_id = ? AND question_id = ?",
                               (earned_marks, feedback, student_id, question_id))
                conn.commit()  # ✅ Commit after each update

    # Finally, update total earned marks in the Attended table
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Attended SET earned_total = ? WHERE student_id = ? AND exam_id = ?",
                       (total_earned, student_id, exam_id))
        conn.commit()


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
            SELECT Question.id, Question.question_text, Answer.answer_text, Answer.earned_marks, 
                   Question.total_marks, Answer.feedback, Answer.id
            FROM Answer
            JOIN Question ON Answer.question_id = Question.id
            WHERE Answer.student_id = ? AND Question.exam_id = ?
        """, (student_id, exam_id))
        answers = cursor.fetchall()  # (question_id, question_text, answer_text, earned_marks, total_marks, feedback, answer_id)

    if request.method == 'POST':
        action = request.form.get('action')

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()

            if action == 'update_marks':  # Manual mark editing & feedback update
                for answer in answers:
                    answer_id = answer[6]
                    new_marks = request.form.get(f'marks_{answer_id}', answer[3])  # Default to existing marks
                    new_feedback = request.form.get(f'feedback_{answer_id}', answer[5])  # Default to existing feedback
                    cursor.execute("UPDATE Answer SET earned_marks = ?, feedback = ? WHERE id = ?", 
                                   (new_marks, new_feedback, answer_id))

            elif request.form.get('retry_ai'):  # Retry AI button was pressed
                answer_id = int(request.form['retry_ai'])  # Get answer ID from button value
                print("\nRETRYING AI EVALUATION FOR ANSWER ID:", answer_id)
                threading.Thread(target=re_evaluate_single_answer, args=(answer_id,)).start()

                return render_template(
                    'message.html',
                    message="AI re-valuation for selected answer is under progress. Check back later for results.",
                    link_text="Continue reviewing...",
                    link_url=f"/review_answers/{exam_id}/{student_id}"
                )

            conn.commit()

        return redirect(request.url)  # Refresh the page to show updated data

    return render_template('review_answers.html', exam_id=exam_id, student_id=student_id, exam_title=exam_title, student_name=student_name, answers=answers)


def generate_plagiarism_report(exam_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        # Get all questions of the exam
        cursor.execute("SELECT id, question_text, answer_key FROM Question WHERE exam_id=?", (exam_id,))
        questions = cursor.fetchall()

        for qid, qtext, answer_key in questions:
            # Get all answers to this question
            cursor.execute("SELECT student_id, answer_text FROM Answer WHERE question_id=?", (qid,))
            answers = cursor.fetchall()

            for i in range(len(answers)):
                sid1, ans1 = answers[i]
                for j in range(i + 1, len(answers)):
                    sid2, ans2 = answers[j]
                    if sid1 == sid2:
                        continue

                    # Prompt for reasoning
                    reasoning_prompt = (
                        f"Compare the following two answers to the question:\n\n"
                        f"Q: {qtext}\n\n"
                        f"Answer 1: {ans1}\n"
                        f"Answer 2: {ans2}\n\n"
                        f"Based on the question and expected answer '{answer_key}', "
                        f"how similar are these two answers? Give a similarity score out of 100 "
                        f"(100 meaning identical answers, 0 meaning completely different). "
                        f"Then explain your reasoning."
                    )

                    extract_prompt_template = (
                        "Here is a detailed analysis of plagiarism between two answers:\n\n"
                        "{deepseek_response}\n\n"
                        "From the above reasoning, extract only the final similarity score (out of 100). "
                        "Do not include any explanations, just return the number."
                    )

                    for _ in range(3):  # Retry if needed
                        # Step 1: Get reasoning
                        reasoning_response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": reasoning_prompt}])
                        reasoning_text = reasoning_response['message']['content'].strip()

                        print(f"\n****************************************************************\nPlagiarism Reasoning:\n{reasoning_text}")

                        reasoning_text = re.sub(r'<think>.*?</think>', '', reasoning_text, flags=re.DOTALL).strip()

                        # Step 2: Extract score
                        extract_prompt = extract_prompt_template.format(deepseek_response=reasoning_text)
                        extract_response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": extract_prompt}])
                        extract_text = extract_response['message']['content'].strip()

                        print(f"\n****************************************************************\nExtracted Similarity Score:\n{extract_text}")

                        match = re.search(r'\d+(\.\d+)?', extract_text)
                        if match:
                            score = float(match.group())
                            score = round(score, 2)

                            if 0 <= score <= 100:
                                #score = 100
                                # Save to DB
                                cursor.execute('''INSERT INTO PlagiarismReport 
                                                (exam_id, question_id, student1_id, student2_id, similarity_score, reasoning) 
                                                VALUES (?, ?, ?, ?, ?, ?)''',
                                               (exam_id, qid, sid1, sid2, score, reasoning_text))
                                break  # break retry loop if successful

        conn.commit()



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
        deepseek_response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": reasoning_prompt}])
        deepseek_text = deepseek_response['message']['content'].strip()

        print(f"\n****************************************************************\nDeepSeek Response: {deepseek_text}")

        deepseek_text = re.sub(r'<think>.*?</think>', '', deepseek_text, flags=re.DOTALL).strip()

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
                                    total_marks INTEGER,
                                    is_started INTEGER DEFAULT 0,
                                    duration INTEGER  -- in minutes maybe
                                )''')


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
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS PlagiarismReport (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            exam_id INTEGER,
                            question_id INTEGER,
                            student1_id INTEGER,
                            student2_id INTEGER,
                            similarity_score REAL,
                            reasoning TEXT);''')
        
        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS WaitingRoom (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                exam_id INTEGER,
                                student_id INTEGER
                            )
                        ''')


        # In init_db()
        #cursor.execute('''ALTER TABLE Exam ADD COLUMN duration INTEGER''')  # Duration in minutes
        #cursor.execute('''ALTER TABLE Exam ADD COLUMN is_started INTEGER DEFAULT 0''')  # 0: Not started, 1: Started

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
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_started FROM Exam WHERE id = ?", (exam_code,))
            result = cursor.fetchone()
            if result:
                is_started = result[0]
                if is_started == 1:
                    return redirect(f'/write_exam/{exam_code}')
                else:
                    # Add to WaitingRoom if not already waiting
                    student_id = session['student_id']
                    cursor.execute("SELECT id FROM WaitingRoom WHERE exam_id = ? AND student_id = ?", (exam_code, student_id))
                    already_waiting = cursor.fetchone()
                    if not already_waiting:
                        cursor.execute("INSERT INTO WaitingRoom (exam_id, student_id) VALUES (?, ?)", (exam_code, student_id))
                        conn.commit()
                    return render_template('waiting_room.html', exam_id=exam_code)


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

        # Check if already attended
        cursor.execute("SELECT id FROM Attended WHERE student_id = ? AND exam_id = ?", (student_id, exam_id))
        attempted = cursor.fetchone()
        if attempted:
            return render_template(
                'message.html',
                message="You have already attempted this exam.",
                link_text="Back to dashboard",
                link_url=f"/dashboard_student"
            )

        # ✅ Get exam duration
        cursor.execute("SELECT duration FROM Exam WHERE id = ?", (exam_id,))
        result = cursor.fetchone()
        duration = result[0] if result else 0  # in minutes

        # On submit
        if request.method == 'POST':
            cursor.execute("SELECT id FROM Question WHERE exam_id = ?", (exam_id,))
            questions = cursor.fetchall()

            for (question_id,) in questions:
                answer_text = request.form.get(f'answer_{question_id}', '').strip()
                cursor.execute("INSERT INTO Answer (question_id, student_id, answer_text, earned_marks, feedback) VALUES (?, ?, ?, NULL, NULL)",
                               (question_id, student_id, answer_text))

            cursor.execute("INSERT INTO Attended (student_id, exam_id, earned_total) VALUES (?, ?, NULL)",
                           (student_id, exam_id))
            conn.commit()

            # Evaluate in background
            threading.Thread(target=evaluate_in_background, args=(student_id, exam_id)).start()

            return render_template(
                'message.html',
                message="Exam submitted! Evaluation is in progress. Check back later for results.",
                link_text="Back to dashboard",
                link_url=f"/dashboard_student"
            )

        # Fetch exam questions
        cursor.execute("SELECT * FROM Question WHERE exam_id = ?", (exam_id,))
        questions = cursor.fetchall()
        return render_template('write_exam.html', questions=questions, duration=duration)



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
        duration = int(request.form['duration'])
        # Calculate total marks dynamically
        total_marks = sum(map(int, question_marks))

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Exam (teacher_id, title, total_marks, duration) VALUES (?, ?, ?, ?)",
               (session['teacher_id'], title, total_marks, duration))
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
            SELECT Student.username, Student.reg_no, Attended.earned_total, Student.id
            FROM Attended
            JOIN Student ON Attended.student_id = Student.id
            WHERE Attended.exam_id = ?
        """, (exam_id,))
        students = cursor.fetchall()  # (username, earned_total, student_id)
    
    # Fetch high plagiarism cases
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                PlagiarismReport.id,
                PlagiarismReport.similarity_score,

                s1.id, s1.username, s1.reg_no,
                s2.id, s2.username, s2.reg_no

            FROM PlagiarismReport
            JOIN Student s1 ON PlagiarismReport.student1_id = s1.id
            JOIN Student s2 ON PlagiarismReport.student2_id = s2.id
            WHERE PlagiarismReport.exam_id = ? AND PlagiarismReport.similarity_score >= 75
        ''', (exam_id,))
        rows = cursor.fetchall()


        fatal_cases = [{
            'id': row[0],
            'similarity_score': row[1],
            'student1': {
                'id': row[2],
                'username': row[3],
                'reg_no': row[4],
            },
            'student2': {
                'id': row[5],
                'username': row[6],
                'reg_no': row[7],
            }
        } for row in rows]


    return render_template("exam_details.html", exam=exam, students=students, fatal_cases=fatal_cases)


@app.route('/check_exam_started/<int:exam_id>')
def check_exam_started(exam_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_started FROM Exam WHERE id = ?", (exam_id,))
        result = cursor.fetchone()
        if result and result[0] == 1:
            return jsonify({"started": True})
    return jsonify({"started": False})



@app.route('/manage_exam/<int:exam_id>', methods=['GET', 'POST'])
def manage_exam(exam_id):
    if 'teacher_id' not in session:
        return redirect('/login_teacher')

    def reset_exam_flag_later(exam_id):
        # This function runs in a separate thread after 10 seconds
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Exam SET is_started = 0 WHERE id = ?", (exam_id,))
            conn.commit()

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()

        if request.method == 'POST':
            # Start exam temporarily
            cursor.execute("UPDATE Exam SET is_started = 1 WHERE id = ?", (exam_id,))
            cursor.execute("DELETE FROM WaitingRoom WHERE exam_id = ?", (exam_id,))
            conn.commit()

            # Start a background thread to reset is_started after 10 seconds
            threading.Timer(10.0, reset_exam_flag_later, args=(exam_id,)).start()

            return redirect('/dashboard_teacher')

        # Show students who joined
        cursor.execute("""
            SELECT Student.username 
            FROM Attended 
            JOIN Student ON Attended.student_id = Student.id 
            WHERE Attended.exam_id = ?
        """, (exam_id,))
        students = cursor.fetchall()
        
        # Show students in waiting room
        cursor.execute("""
            SELECT Student.username 
            FROM WaitingRoom 
            JOIN Student ON WaitingRoom.student_id = Student.id 
            WHERE WaitingRoom.exam_id = ?
        """, (exam_id,))
        waiting_students = cursor.fetchall()

    return render_template('manage_exam.html', exam_id=exam_id, students=students, waiting_students=waiting_students)

import threading

@app.route('/generate_plagiarism/<int:exam_id>', methods=['POST'])
def generate_plagiarism(exam_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        # Delete previous plagiarism data for this exam
        cursor.execute("DELETE FROM PlagiarismReport WHERE exam_id = ?", (exam_id,))

    # Run the report generation in a background thread
    threading.Thread(target=generate_plagiarism_report, args=(exam_id,)).start()

    # Immediately show message to user
    return render_template(
        'message.html',
        message="Our AI is working on your exam. Plagiarism report will be available soon. Please check back later.",
        link_text="Back to Exam Details",
        link_url=f"/exam_details/{exam_id}"
    )


@app.route('/plagiarism_detail/<int:report_id>')
def view_plagiarism_detail(report_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        
        # Get plagiarism report row
        cursor.execute("SELECT * FROM PlagiarismReport WHERE id=?", (report_id,))
        row = cursor.fetchone()
        exam_id, question_id, student1_id, student2_id = row[1], row[2], row[3], row[4]

        # Get question and answer key
        cursor.execute("SELECT question_text, answer_key FROM Question WHERE id=?", (question_id,))
        question_row = cursor.fetchone()

        # Get student 1 details
        cursor.execute("SELECT username, reg_no FROM Student WHERE id=?", (student1_id,))
        s1 = cursor.fetchone()

        # Get student 2 details
        cursor.execute("SELECT username, reg_no FROM Student WHERE id=?", (student2_id,))
        s2 = cursor.fetchone()

        # Get both answers
        cursor.execute("SELECT answer_text FROM Answer WHERE question_id=? AND student_id=?", (question_id, student1_id))
        answer1 = cursor.fetchone()
        cursor.execute("SELECT answer_text FROM Answer WHERE question_id=? AND student_id=?", (question_id, student2_id))
        answer2 = cursor.fetchone()

        detail = {
            'student1': {
                'username': s1[0],
                'reg_no': s1[1],
                'answer': answer1[0] if answer1 else "No answer found"
            },
            'student2': {
                'username': s2[0],
                'reg_no': s2[1],
                'answer': answer2[0] if answer2 else "No answer found"
            },
            'similarity_score': row[5],
            'reasoning': row[6],
            'question': question_row[0],
            'answer_key': question_row[1]
        }

    return render_template("plagiarism_detail.html", detail=detail)



@app.route('/get_exam_status/<int:exam_id>')
def get_exam_status(exam_id):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT Student.username 
            FROM Attended 
            JOIN Student ON Attended.student_id = Student.id 
            WHERE Attended.exam_id = ?
        """, (exam_id,))
        students = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT Student.username 
            FROM WaitingRoom 
            JOIN Student ON WaitingRoom.student_id = Student.id 
            WHERE WaitingRoom.exam_id = ?
        """, (exam_id,))
        waiting_students = [row[0] for row in cursor.fetchall()]
    
    return jsonify({"students": students, "waiting_students": waiting_students})



if __name__ == '__main__':
    init_db()
    app.run(debug=True)