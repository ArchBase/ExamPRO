document.addEventListener("DOMContentLoaded", function () {
    const loginBtns = document.querySelectorAll(".login-btn"); // Select all buttons with class 'login-btn'
    const modalContainer = document.getElementById("modal-container");

    // Load the modal content from `login-modal.html`
    fetch("login-modal.html")
        .then(response => response.text())
        .then(html => {
            modalContainer.innerHTML = html; // ✅ Insert modal content
            setTimeout(addModalEvents, 0); // ✅ Ensure DOM is updated before adding events
        });

    function addModalEvents() {
        const modal = document.getElementById("loginModal");
        const closeBtn = modal.querySelector(".close-btn"); // ✅ Ensure close button is selected

        // ✅ Ensure modal is hidden initially
        modal.style.display = "none";

        // Show modal when clicking "Login" or "Get Started"
        loginBtns.forEach(btn => {
            btn.addEventListener("click", function (event) {
                event.preventDefault();
                modal.style.display = "flex";
            });
        });

        // Hide modal when clicking close button
        closeBtn.addEventListener("click", function () {
            modal.style.display = "none";
        });

        // Hide modal when clicking outside modal content
        window.addEventListener("click", function (event) {
            if (event.target === modal) {
                modal.style.display = "none";
            }
        });
    }
});
