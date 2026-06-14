// StudyVerse AI - Main JavaScript Actions

document.addEventListener("DOMContentLoaded", () => {
    // 1. Auto-dismiss Flash Messages
    const flashMessages = document.querySelectorAll(".flash-msg");
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.transition = "opacity 0.6s ease, transform 0.6s ease";
            msg.style.opacity = "0";
            msg.style.transform = "translateY(-10px)";
            setTimeout(() => msg.remove(), 600);
        }, 4000);
    });

    // 2. Document Upload Logic (Drag-and-Drop + Processing Spinner)
    const uploadForm = document.getElementById("uploadForm");
    const fileInput = document.getElementById("pdfFileInput");
    const uploadZone = document.querySelector(".upload-zone");
    const fileIndicator = document.getElementById("fileIndicator");
    const processingOverlay = document.getElementById("processingOverlay");

    if (uploadForm && fileInput && uploadZone) {
        // Drag over effects
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                uploadZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                uploadZone.classList.remove('dragover');
            }, false);
        });

        // Drop file
        uploadZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length) {
                fileInput.files = files;
                updateFileIndicator(files[0].name);
            }
        });

        // Select file manually
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length) {
                updateFileIndicator(fileInput.files[0].name);
            }
        });

        function updateFileIndicator(name) {
            if (fileIndicator) {
                fileIndicator.textContent = `Selected file: ${name}`;
                fileIndicator.style.display = "inline-block";
            }
        }

        // Show processing loader on submit
        uploadForm.addEventListener("submit", () => {
            if (processingOverlay) {
                processingOverlay.classList.add("active");
            }
        });
    }

    // 3. Interactive Step-by-Step Quiz Controller
    const quizForm = document.getElementById("interactiveQuizForm");
    if (quizForm) {
        const questions = document.querySelectorAll(".quiz-card");
        const totalQuestions = questions.length;
        const progressInner = document.getElementById("quizProgressInner");
        const progressText = document.getElementById("quizProgressText");
        const prevBtn = document.getElementById("quizPrevBtn");
        const nextBtn = document.getElementById("quizNextBtn");
        const submitBtn = document.getElementById("quizSubmitBtn");
        
        let currentIndex = 0;

        function updateQuizUI() {
            // Toggle active card
            questions.forEach((card, idx) => {
                if (idx === currentIndex) {
                    card.classList.add("active");
                } else {
                    card.classList.remove("active");
                }
            });

            // Update Progress Bar
            const percent = ((currentIndex + 1) / totalQuestions) * 100;
            if (progressInner) progressInner.style.width = `${percent}%`;
            if (progressText) progressText.textContent = `Question ${currentIndex + 1} of ${totalQuestions}`;

            // Handle Buttons
            if (prevBtn) prevBtn.style.display = currentIndex === 0 ? "none" : "block";
            if (nextBtn) nextBtn.style.display = currentIndex === totalQuestions - 1 ? "none" : "block";
            if (submitBtn) submitBtn.style.display = currentIndex === totalQuestions - 1 ? "block" : "none";
        }

        // Initialize quiz view
        if (totalQuestions > 0) {
            updateQuizUI();
        }

        // Radio option highlighting
        const options = document.querySelectorAll(".quiz-option-label");
        options.forEach(label => {
            const radio = label.querySelector("input[type=radio]");
            if (radio) {
                radio.addEventListener("change", () => {
                    // Remove selected from siblings of this card
                    const card = label.closest(".quiz-card");
                    card.querySelectorAll(".quiz-option-label").forEach(l => l.classList.remove("selected"));
                    label.classList.add("selected");
                });
            }
        });

        // Navigation actions
        if (nextBtn) {
            nextBtn.addEventListener("click", () => {
                // Check if current question is answered
                const currentCard = questions[currentIndex];
                const answered = currentCard.querySelector("input[type=radio]:checked");
                if (!answered) {
                    alert("Please select an option before proceeding.");
                    return;
                }
                if (currentIndex < totalQuestions - 1) {
                    currentIndex++;
                    updateQuizUI();
                }
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener("click", () => {
                if (currentIndex > 0) {
                    currentIndex--;
                    updateQuizUI();
                }
            });
        }

        // Form submit using async Fetch
        quizForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            // Check if last question is answered
            const currentCard = questions[currentIndex];
            const answered = currentCard.querySelector("input[type=radio]:checked");
            if (!answered) {
                alert("Please select an option before submitting.");
                return;
            }

            let answers = {};
            document.querySelectorAll("input[type=radio]:checked").forEach(radio => {
                answers[radio.dataset.question] = radio.value;
            });

            try {
                // Show loader state inside form
                submitBtn.disabled = true;
                submitBtn.textContent = "Submitting...";

                const response = await fetch(window.location.pathname, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(answers)
                });

                if (!response.ok) {
                    throw new Error("Failed to submit quiz scores.");
                }

                const result = await response.json();
                renderQuizResults(result);
            } catch (err) {
                console.error("Quiz submission error:", err);
                alert("Something went wrong while submitting the quiz. Please try again.");
                submitBtn.disabled = false;
                submitBtn.textContent = "Submit Quiz";
            }
        });

        function renderQuizResults(result) {
            // Hide the active quiz wrapper
            const quizContainer = document.getElementById("quizActiveContainer");
            const resultContainer = document.getElementById("quizResultsContainer");
            if (quizContainer) quizContainer.style.display = "none";
            
            if (resultContainer) {
                resultContainer.style.display = "block";
                
                // Add animated results HTML
                let reviewHTML = "";
                result.results.forEach((q, idx) => {
                    const statusClass = q.is_correct ? "correct" : "incorrect";
                    const statusIcon = q.is_correct ? "✅" : "❌";
                    
                    let optionsHTML = "";
                    q.options.forEach(opt => {
                        let optClass = "";
                        if (opt === q.correct) {
                            optClass = "correct-option";
                        } else if (opt === q.user_answer && !q.is_correct) {
                            optClass = "user-option-incorrect";
                        }
                        optionsHTML += `<div class="review-option ${optClass}">${opt}</div>`;
                    });

                    reviewHTML += `
                        <div class="review-item ${statusClass}">
                            <div class="review-question">
                                ${idx + 1}. ${q.question} ${statusIcon}
                            </div>
                            <div class="review-options">
                                ${optionsHTML}
                            </div>
                            <div class="review-explanation">
                                <strong>Explanation:</strong> ${q.explanation || 'No explanation provided.'}
                            </div>
                        </div>
                    `;
                });

                resultContainer.innerHTML = `
                    <div class="quiz-results-card glass-card fade-in">
                        <h2 class="gradient-text mb-4">Quiz Completed! 🎉</h2>
                        
                        <div class="results-stats-row">
                            <div class="result-badge">
                                <div class="text-muted" style="font-size: 0.85rem;">Score</div>
                                <div class="result-badge-val success">${result.score} / ${result.total}</div>
                            </div>
                            <div class="result-badge">
                                <div class="text-muted" style="font-size: 0.85rem;">Accuracy</div>
                                <div class="result-badge-val info">${result.percentage}%</div>
                            </div>
                            <div class="result-badge">
                                <div class="text-muted" style="font-size: 0.85rem;">XP Gained</div>
                                <div class="result-badge-val xp">+${result.xp_earned} XP</div>
                            </div>
                        </div>

                        <div class="stats-summary-grid mb-8" style="max-width: 400px; margin: 2rem auto;">
                            <div class="stat-item">
                                <div class="text-muted" style="font-size: 0.85rem;">Total XP</div>
                                <div class="stat-value" style="font-size: 1.3rem; color: var(--primary-light);">${result.new_xp}</div>
                            </div>
                            <div class="stat-item">
                                <div class="text-muted" style="font-size: 0.85rem;">Level</div>
                                <div class="stat-value" style="font-size: 1.3rem; color: var(--secondary);">${result.new_level}</div>
                            </div>
                        </div>

                        <div style="display: flex; gap: 1rem; justify-content: center; margin-bottom: 2rem;">
                            <a href="${window.location.pathname}" class="btn btn-primary">Retake Quiz</a>
                            <a href="/dashboard" class="btn btn-secondary">Dashboard</a>
                        </div>

                        <div class="review-section">
                            <h3 class="mb-4">Question Review</h3>
                            <div class="review-list">
                                ${reviewHTML}
                            </div>
                        </div>
                    </div>
                `;
            }
        }
    }

    // 4. 3D Flashcards Deck Controller
    const cardContainer = document.getElementById("flashcardActiveContainer");
    if (cardContainer) {
        const cards = document.querySelectorAll(".flashcard-perspective");
        const totalCards = cards.length;
        const currentText = document.getElementById("cardIndexVal");
        const prevBtn = document.getElementById("cardPrevBtn");
        const nextBtn = document.getElementById("cardNextBtn");
        
        let cardIndex = 0;

        function updateFlashcardUI() {
            cards.forEach((card, idx) => {
                if (idx === cardIndex) {
                    card.style.display = "block";
                    // Reset flip state when navigating
                    const inner = card.querySelector(".flashcard-inner");
                    if (inner) inner.classList.remove("flipped");
                } else {
                    card.style.display = "none";
                }
            });

            if (currentText) currentText.textContent = `${cardIndex + 1} / ${totalCards}`;
            if (prevBtn) prevBtn.disabled = cardIndex === 0;
            if (nextBtn) nextBtn.disabled = cardIndex === totalCards - 1;
        }

        // Initialize view
        if (totalCards > 0) {
            updateFlashcardUI();
            
            // Set up flip trigger
            cards.forEach(card => {
                const inner = card.querySelector(".flashcard-inner");
                if (inner) {
                    inner.addEventListener("click", () => {
                        inner.classList.toggle("flipped");
                    });
                }
            });

            // Set up button navigation
            if (prevBtn) {
                prevBtn.addEventListener("click", () => {
                    if (cardIndex > 0) {
                        cardIndex--;
                        updateFlashcardUI();
                    }
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener("click", () => {
                    if (cardIndex < totalCards - 1) {
                        cardIndex++;
                        updateFlashcardUI();
                    }
                });
            }

            // Keyboard navigation listener
            document.addEventListener("keydown", (e) => {
                if (e.code === "Space") {
                    e.preventDefault(); // Prevent page scrolling
                    const activeCard = cards[cardIndex];
                    const inner = activeCard.querySelector(".flashcard-inner");
                    if (inner) inner.classList.toggle("flipped");
                } else if (e.code === "ArrowRight") {
                    if (cardIndex < totalCards - 1) {
                        cardIndex++;
                        updateFlashcardUI();
                    }
                } else if (e.code === "ArrowLeft") {
                    if (cardIndex > 0) {
                        cardIndex--;
                        updateFlashcardUI();
                    }
                }
            });
        }
    }
});
