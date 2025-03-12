document.addEventListener("DOMContentLoaded", function () {
    // Dummy data for subject, questions, student responses, and marks
    const examData = {
        subject: "Computer Science",
        totalMarks: 100,
        obtainedMarks: 85,
        questions: [
            { question: "Define polymorphism.", response: "Polymorphism means multiple forms. In OOP, it allows methods to have different implementations.", marks: 5 },
            { question: "Explain recursion with an example.", response: "Recursion is a function calling itself. Example: Factorial function using recursion.", marks: 4 },
            { question: "Compare Stack vs Queue.", response: "Stack follows LIFO, Queue follows FIFO.", marks: 3 },
            { question: "Write binary search algorithm.", response: "Binary search divides the array and checks the middle element.", marks: 5 },
            { question: "Discuss OOP principles.", response: "OOP includes Encapsulation, Inheritance, Polymorphism, and Abstraction.", marks: 4 },
        ]
    };

    // Update Subject, Total & Obtained Marks
    document.getElementById("subject-name").textContent = examData.subject;
    document.getElementById("total-marks").textContent = examData.totalMarks;
    document.getElementById("marks-obtained").textContent = examData.obtainedMarks;

    // Populate Form with Questions
    const container = document.getElementById("questions-container");
    examData.questions.forEach((q, index) => {
        const questionBox = document.createElement("div");
        questionBox.classList.add("question-box");

        questionBox.innerHTML = `
            <label>Q${index + 1}: ${q.question}</label>
            <textarea readonly>${q.response}</textarea>
            <br>
            <label>Marks Obtained: </label>
            <input type="number" value="${q.marks}" readonly>
        `;

        container.appendChild(questionBox);
    });

    // Close Button Functionality
    document.getElementById("close-btn").addEventListener("click", function () {
        window.history.back(); // Go back to the previous page
    });
});
