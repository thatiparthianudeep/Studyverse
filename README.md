# 🌌 StudyVerse AI - Smart Study Assistant

StudyVerse AI is a premium, gamified web application designed to help students, scholars, and lifelong learners master any subject. By uploading textbook chapters, lecture notes, or articles in PDF format, the app leverages Google Gemini AI models to generate structured study materials, 3D interactive flashcards, and step-by-step quizzes.

The application is gamified, allowing users to earn XP, level up their ranks, and compete on a public leaderboard. It features a sleek glassmorphic dark-theme design with clean layouts and smooth micro-animations.

---

## ✨ Core Features

* **📝 AI Document Summaries**: Instantly extracts PDF content and structures it into core topics, detailed explanations, and critical exam tips. Rendered dynamically via Markdown.
* **🎴 3D Interactive Flashcards**: Review terms and formulas using double-sided 3D card flipping transitions. Supports navigation buttons and keyboard shortcuts (Space to flip, Left/Right arrow keys to browse).
* **❓ Practice Quizzes**: Card-based step-by-step multiple choice quizzes. Submitting grades answers asynchronously (AJAX) to instantly award XP, calculate accuracy percentages, and display a review deck with correct answers and explanations.
* **🏆 Gamified Ranks & Leaderboard**: Users earn +50 XP for uploading materials, and +20 XP for every correct quiz answer. Ranks advance from Novice up to Legend, with rankings highlighted on a Gold/Silver/Bronze global podium leaderboard.
* **🛡️ Resilient Failover & Multi-Model Engine**: Automatically cycles through available API models (`gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-flash-latest`) to avoid quota limits. If all API requests fail, a local Python NLP parser analyzes the PDF text to generate custom summaries, flashcards, and quizzes so the app never crashes.
* **💾 Database Agnostic**: Seamlessly switches between a local SQLite database for development and a PostgreSQL database in production.

---

## 🛠️ Technology Stack

* **Frontend**: HTML5, Vanilla CSS3 (Glassmorphism, custom CSS properties, keyframe animations, 3D perspectives), Vanilla Javascript, marked.js (Markdown parsing), Google Fonts (Plus Jakarta Sans).
* **Backend**: Python 3, Flask (Web framework), Flask-SQLAlchemy (Optional/DB bindings), Werkzeug (Security, hashing), PyMuPDF (PDF text extraction), google-generativeai, python-dotenv.
* **Database**: SQLite (Local development), PostgreSQL (Production/Render environment).
* **Server**: gunicorn (WSGI server for Linux production).

---

## 🚀 Local Installation & Setup

1. **Clone or download the project** and open a terminal in the folder directory.
2. **Create a virtual environment (optional but recommended)**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment Variables**:
   Create a `.env` file in the root directory and add your secret credentials:
   ```env
   SECRET_KEY=your_secret_session_key_here
   GEMINI_API_KEY=your_google_gemini_api_key
   # DATABASE_URL= (Leave empty for SQLite local development; will auto-generate database.db)
   ```
5. **Run the application**:
   ```bash
   python app.py
   ```
   Open your browser and navigate to **`http://127.0.0.1:5001`**.

---

## ☁️ Production Deployment (Render)

Render free tier files are ephemeral. Since SQLite database updates reset when the server restarts, this app automatically integrates with **PostgreSQL** in production.

### Step-by-Step Render Deployment:

1. **Push your workspace code to GitHub**.
2. **Create a PostgreSQL Database on Render**:
   * Navigate to the Render Dashboard, click **New +**, and select **PostgreSQL**.
   * Fill out the database details and click create.
   * Once status changes to **Available**, copy the **Internal Database URL** (begins with `postgres://` or `postgresql://`).
3. **Create a Web Service**:
   * Click **New +** and select **Web Service**.
   * Link your GitHub repository.
   * Configure the service options:
     * **Runtime**: `Python`
     * **Build Command**: `pip install -r requirements.txt`
     * **Start Command**: `gunicorn app:app`
4. **Add Environment Variables**:
   Click **Advanced / Environment Variables** and configure:
   * `DATABASE_URL` = (Insert the **Internal Database URL** copied in step 2)
   * `GEMINI_API_KEY` = (Insert your Google Gemini API key)
   * `SECRET_KEY` = (Insert a secure secret string)
5. **Deploy**:
   Click **Create Web Service**. Render will install the environment packages, initialize database tables via the Postgres adapter, and set your app live!
