# 💧 WaterBuddy
### Your Daily Hydration Companion

WaterBuddy is a Python web application that helps users record their daily water intake and track progress towards an editable, age-based goal.

Developed for the **Python Programming FA‑2 project** at **Viraj International School**, it turns the FA‑1 storyboard into an interactive Streamlit application.

## 🔗 Project Links

- **Live application:** https://waterbuddy--vis.streamlit.app/
- **GitHub repository:** https://github.com/arpitsrivastava-IBCP/WaterBuddy

## Features

- Age-group selection with a suggested daily goal.
- Manual adjustment of the daily goal.
- A **+250 ml** button for quick logging.
- Custom water-intake entry in millilitres.
- Live totals, remaining water and progress percentage.
- A bottle mascot that fills as intake increases.
- Motivational messages at progress milestones.
- Confirmation before clearing today’s intake.
- Daily hydration tips.
- Daily reports with an hourly intake chart.

## How It Works

1. Select your age group.
2. Review or adjust your daily goal.
3. Log a drink using **+250 ml** or a custom amount.
4. View your updated total, progress and bottle mascot.
5. Open the report to review your intake during the day.

The bottle has a neutral face below 50% and smiles from 50% onward. At 100%, it appears full. If intake exceeds the chosen goal, the percentage can exceed 100%, while the visual stays full.

## Calculations

- **Total intake:** Sum of the amounts logged during the day.
- **Remaining water:** `max(0, goal - total)`
- **Progress:** `(total / goal) × 100`

One app cup represents **250 ml**.

## Technologies

- **Python** for application logic.
- **Streamlit** for the web interface and session state.
- **Matplotlib** for the hourly intake chart.
- **GitHub** for source-code management.
- **Streamlit Community Cloud** for hosting.

## Run Locally

Install Python, download or clone this repository, and open a terminal in the project folder.

Install the dependencies:

    pip install -r requirements.txt

Start the application:

    streamlit run app.py

Open the local URL displayed in the terminal.

## Privacy and Storage

WaterBuddy uses `st.session_state` to keep each visitor’s intake and settings separate during their session.

Session data is temporary. Refreshing the page, losing the session or restarting the application can reset the records. The app does not provide permanent account-based storage.

The application uses the **Asia/Kolkata** timezone for daily tracking.

## Team

| Member | Registration Number |
|---|---|
| Nived Chandrasudan | 1000521 |
| Arpit Brijesh Srivastava | 1000626 |
| Kanishk Juvan | 1000522 |

**School:** Viraj International School  
**CRS:** Artificial Intelligence  
**Course:** Python Programming  
**Assessment:** Formative Assessment 2

## Health Context

WaterBuddy is an educational project. Suggested goals are assignment reference values, not personalised medical advice. Fluid needs vary, and other drinks also contribute to intake.

The app records what users log; it does not measure hydration. Follow individual medical guidance and do not force extra water to increase the progress score.
