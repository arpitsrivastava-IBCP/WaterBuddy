"""WaterBuddy: Your Daily Hydration Companion (Streamlit Web Edition)
FA-2 Formative Assessment 2 — Python Programming Project

Features:
- Age-based goal suggestion with manual adjustment (FA-1 Storyboard aligned).
- Quick '+250 ml (1 cup)' button and custom ml input with rigorous whole-number validation.
- Real-time calculations: total intake, remaining ml, percentage achieved (including >100%).
- Real-time animated vector bottle mascot with continuous liquid fill and neutral/smiling expressions.
- Milestone messages with factual hydration and health guidance.
- 'Clear today’s intake' action with confirmation and cancellation.
- 24-hour hourly intake chart (00:00 to 23:00) with Matplotlib.
- Session-isolated state (st.session_state) ensuring visitor privacy without cross-user data leakage.
- Explicit Asia/Kolkata timezone support for consistent daily calendar tracking.
"""

import sys
from datetime import datetime, date, timedelta, timezone
import random
import streamlit as st
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure

# ---------------------------------------------------------------------------
# 1. CONSTANTS, STANDARDS & FA-1 STORYBOARD GUIDANCE
# ---------------------------------------------------------------------------
CUP_ML = 250

# Technical limits to prevent integer overflow or visual distortion.
# Software safeguards, NOT medical recommendations.
MAX_SINGLE_INTAKE_ML = 10_000   # 10,000 ml (10 litres)
MAX_DAILY_GOAL_ML = 20_000      # 20,000 ml (20 litres)

DEFAULTS = {
    'Children (4–8 years)': 1200,
    'Teens (9–13 years)': 1700,
    'Adults (14–64 years)': 2000,
    'Seniors (65+ years)': 1700,
}

STANDARDS = {
    'Children (4–8 years)': '~1,200 ml (≈ 4–5 cups)',
    'Teens (9–13 years)': '~1,700 ml (≈ 6–7 cups)',
    'Adults (14–64 years)': '2,000–2,500 ml (≈ 8–10 cups); starting goal: 2,000 ml',
    'Seniors (65+ years)': '1,700–2,000 ml (≈ 6–8 cups); starting goal: 1,700 ml',
}

GUIDANCE = {
    'Children (4–8 years)': 'Assignment reference: ~1,200 ml (≈ 4–5 cups). A parent or caregiver should adjust the starting goal to suit.',
    'Teens (9–13 years)': 'Assignment reference: ~1,700 ml (≈ 6–7 cups). Needs vary with exact age, sex and activity; adjust as needed.',
    'Adults (14–64 years)': 'Assignment reference range: 2,000–2,500 ml (≈ 8–10 cups); 2,000 ml is an editable starting point.',
    'Seniors (65+ years)': 'Assignment reference range: 1,700–2,000 ml (≈ 6–8 cups); 1,700 ml is an editable starting point. Follow any clinician advice.',
}

TIPS = [
    'Keep your water nearby while studying.',
    'Spread your drinks across the day.',
    'Other drinks count toward fluid intake too.',
    'Log what you actually drink. There is no need to chase a score.',
]

# Calm aqua / blue color palette matching the original desktop design
THEME_COLORS = {
    'bg': '#f4f9fb',
    'card': '#ffffff',
    'text': '#15394c',
    'muted': '#567481',
    'soft': '#edf7fa',
    'accent': '#197f9b',
    'water': '#61c8d6',
    'line': '#c7e1e8',
    'warn': '#97501b',
}


# ---------------------------------------------------------------------------
# 2. TIMEZONE & DATE UTILITIES
# ---------------------------------------------------------------------------
def get_current_datetime():
    """
    Return the current local datetime using Asia/Kolkata timezone with robust fallback.
    Prevents hosting servers (which often run on UTC) from shifting the date prematurely.
    """
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        return datetime.now(tz)
    except Exception:
        # Fallback: IST is fixed at UTC+5:30
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(timezone.utc).astimezone(ist)


def get_today_str():
    """Return local calendar date formatted as YYYY-MM-DD."""
    return get_current_datetime().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# 3. REUSABLE CORE FUNCTIONS (Calculations & Validations)
# ---------------------------------------------------------------------------
def parse_positive_whole_number(raw_value, max_limit, field_name="Amount"):
    """
    Validate integer ml input.
    Rejects blank, fractional, non-numeric, zero, negative, and out-of-bounds inputs.
    Returns (int_val, None) or (None, error_message).
    """
    if raw_value is None:
        return None, "Enter a positive whole number of ml."
    val_str = str(raw_value).strip()
    if not val_str:
        return None, "Enter a positive whole number of ml."
    if '.' in val_str:
        return None, "Enter a whole number of ml (decimals and fractions are not allowed)."
    if not val_str.isdigit():
        return None, "Enter a positive whole number of ml (digits only)."
    try:
        val = int(val_str)
    except (ValueError, OverflowError):
        return None, f"{field_name} is too large. Maximum technical limit is {max_limit:,} ml."
    if val <= 0:
        return None, "Enter a positive whole number of ml (greater than 0)."
    if val > max_limit:
        return None, (
            f"{field_name} exceeds technical limit ({max_limit:,} ml). "
            "This limit is an application safeguard, not medical advice."
        )
    return val, None


def calculate(total, goal):
    """Return remaining ml, actual percentage, and a capped visual fraction (0.0 to 1.0)."""
    if goal <= 0:
        goal = 2000
    remaining = max(0, goal - total)
    actual_percent = (total / goal) * 100
    visual_fraction = min(total / goal, 1.0)
    return remaining, actual_percent, visual_fraction


def reaction(percent):
    """Return factual milestone messages consistent with health guidance."""
    if percent > 100:
        return (
            'Goal exceeded — no need to chase more.',
            'Do not force extra water. Too much, especially quickly, can cause water '
            'intoxication (low sodium). Being over this goal alone does not mean intoxication.'
        )
    elif percent >= 100:
        return 'Great job today! Goal reached.', 'You reached your chosen goal. Keep listening to your body.'
    elif percent >= 75:
        return 'Almost there!', 'You have reached 75% of your chosen goal.'
    elif percent >= 50:
        return 'Great! You reached 50%!', 'You are halfway to your chosen goal.'
    elif percent >= 25:
        return 'A lovely start!', 'You have reached 25% of your chosen goal.'
    return 'Every small habit starts somewhere.', 'Log your drinks as you go through the day.'


def render_bottle_svg(fraction, percent):
    """
    Render SVG water bottle mascot matching the Tkinter desktop design:
    - Continuous water level fill up to 100%.
    - Neutral straight-line mouth below 50%.
    - Smiling curve mouth from 50% onward.
    - Capped at 100% visual fill even when goal is exceeded.
    """
    capped_frac = max(0.0, min(1.0, fraction))
    water_h = capped_frac * 120
    water_y = 172 - water_h

    # Mouth expression
    if percent >= 50:
        mouth_path = '<path d="M 104 100 Q 120 118 136 100" stroke="#15394c" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
    else:
        mouth_path = '<line x1="110" y1="108" x2="130" y2="108" stroke="#15394c" stroke-width="2.5" stroke-linecap="round"/>'

    svg = f'''
    <div style="display:flex; justify-content:center; align-items:center; padding: 10px 0;">
      <svg width="220" height="190" viewBox="0 0 240 190" xmlns="http://www.w3.org/2000/svg">
        <!-- Bottle Cap -->
        <rect x="95" y="5" width="50" height="18" rx="3" fill="#197f9b"/>
        <!-- Bottle Outer Outline -->
        <path d="M 95 25 L 145 25 L 171 48 L 171 175 L 69 175 L 69 48 Z" fill="#edf7fa" stroke="#c7e1e8" stroke-width="3"/>
        <!-- Liquid Fill (clipped to bottle interior) -->
        <g clip-path="url(#bottleBodyClip)">
          <rect x="65" y="{water_y}" width="110" height="{water_h}" fill="#61c8d6"/>
        </g>
        <clipPath id="bottleBodyClip">
          <path d="M 96 26 L 144 26 L 170 49 L 170 174 L 70 174 L 70 49 Z"/>
        </clipPath>
        <!-- Mascot Eyes -->
        <circle cx="105" cy="88" r="3.5" fill="#15394c"/>
        <circle cx="135" cy="88" r="3.5" fill="#15394c"/>
        <!-- Mascot Mouth -->
        {mouth_path}
      </svg>
    </div>
    '''
    return svg


# ---------------------------------------------------------------------------
# 4. SESSION STATE MANAGEMENT (Isolated Client Memory)
# ---------------------------------------------------------------------------
def init_session_state():
    """Initialize isolated session data for the current browser visitor."""
    today = get_today_str()

    if 'session_initialized' not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.current_date = today
        st.session_state.age_group = 'Adults (14–64 years)'
        st.session_state.default_goal = 2000
        # Daily goals map: {date_str: int}
        st.session_state.daily_goals = {today: 2000}
        # Logged entries list: [{'timestamp': str, 'date': str, 'amount': int}]
        st.session_state.water_entries = []
        st.session_state.feedback_msg = 'Ready when you are.'
        st.session_state.feedback_type = 'info'
        st.session_state.show_reset_confirm = False
        st.session_state.selected_tip = random.choice(TIPS)

    # Check for midnight date rollover in session
    if st.session_state.current_date != today:
        prev_date = st.session_state.current_date
        st.session_state.current_date = today
        # Carry forward user's default goal to the new day
        new_day_goal = st.session_state.daily_goals.get(
            today, st.session_state.default_goal
        )
        st.session_state.daily_goals[today] = new_day_goal
        st.session_state.feedback_msg = f'A new day has started ({today}). Intake reset to 0 ml.'
        st.session_state.feedback_type = 'info'
        st.session_state.show_reset_confirm = False


def get_day_total(date_str):
    """Compute total intake for a given date from session entries."""
    return sum(
        e['amount'] for e in st.session_state.water_entries
        if e['date'] == date_str
    )


def get_day_entry_count(date_str):
    """Return count of logged entries for a given date."""
    return sum(
        1 for e in st.session_state.water_entries
        if e['date'] == date_str
    )


def get_hourly_totals(date_str):
    """Return a dict of hours 0..23 mapped to total intake in that hour."""
    hourly = {h: 0 for h in range(24)}
    for e in st.session_state.water_entries:
        if e['date'] == date_str:
            try:
                dt = datetime.fromisoformat(e['timestamp'])
                hourly[dt.hour] += e['amount']
            except Exception:
                pass
    return hourly


def log_water_intake(amount):
    """Record an intake entry in session state."""
    today = st.session_state.current_date
    now_iso = get_current_datetime().isoformat()
    st.session_state.water_entries.append({
        'timestamp': now_iso,
        'date': today,
        'amount': amount,
    })
    cups = amount / CUP_ML
    st.session_state.feedback_msg = f'Added {amount:,} ml ({cups:g} cups).'
    st.session_state.feedback_type = 'success'


# ---------------------------------------------------------------------------
# 5. STREAMLIT USER INTERFACE
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title='WaterBuddy — Your Daily Hydration Companion',
        page_icon='💧',
        layout='wide',
        initial_sidebar_state='expanded',
    )

    init_session_state()
    today = st.session_state.current_date

    # Custom CSS for calm aqua styling matching the desktop app
    st.markdown('''
    <style>
    .main {
        background-color: #f4f9fb;
    }
    .stApp {
        background-color: #f4f9fb;
        color: #15394c;
    }
    .card-box {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 24px;
        border: 1px solid #c7e1e8;
        box-shadow: 0 2px 8px rgba(25, 127, 155, 0.05);
        margin-bottom: 20px;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #15394c;
        line-height: 1.2;
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #567481;
        text-transform: uppercase;
    }
    .stat-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 700;
        background-color: #edf7fa;
        color: #197f9b;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    </style>
    ''', unsafe_allow_html=True)

    # Sidebar: About, Privacy Notice & FA-1 Reference
    with st.sidebar:
        st.markdown('### 💧 WaterBuddy')
        st.markdown(
            '**Your Daily Hydration Companion**  \n'
            '*FA-2: Developing and Deploying App Using Python*'
        )
        st.divider()

        st.markdown('#### 🔒 Session Privacy & Storage')
        st.info(
            '**Client-Isolated Session:**  \n'
            'This web application uses `st.session_state` to keep your intake completely private. '
            'Your logs are never shared across public visitors.  \n\n'
            '*Note:* On cloud hosting (Streamlit Cloud), closing or refreshing your browser tab '
            'starts a fresh session.'
        )

        st.divider()
        st.markdown('#### 💡 Daily Hydration Tip')
        st.markdown(f'*{st.session_state.selected_tip}*')

        st.divider()
        st.markdown(
            '<div style="font-size:0.8rem; color:#567481;">'
            'WaterBuddy is designed for educational demonstration. '
            'Starting goals are reference benchmarks from the FA-1 storyboard. '
            'Fluid intake includes other drinks; always listen to your body and clinician advice.'
            '</div>',
            unsafe_allow_html=True
        )

    # Header Bar
    st.markdown('''
    <div style="display:flex; justify-content:space-between; align-items:baseline; padding: 10px 0 20px 0;">
      <div>
        <h1 style="color:#15394c; margin:0; font-size:2.2rem; font-weight:800;">WaterBuddy</h1>
        <div style="color:#567481; font-size:0.85rem; font-weight:700; letter-spacing:0.1em;">
          YOUR DAILY HYDRATION COMPANION · STREAMLIT WEB APP
        </div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    # Main Grid: Two columns
    col_left, col_right = st.columns([3, 2], gap='large')

    # Fetch today's current totals and goal
    today_goal = st.session_state.daily_goals.get(today, st.session_state.default_goal)
    today_total = get_day_total(today)
    remaining_ml, percent, visual_frac = calculate(today_total, today_goal)
    today_cups = today_total / CUP_ML
    remaining_cups = remaining_ml / CUP_ML
    goal_cups = today_goal / CUP_ML

    # -----------------------------------------------------------------------
    # LEFT COLUMN: TODAY'S INTAKE & LOGGING
    # -----------------------------------------------------------------------
    with col_left:
        st.markdown('<div class="card-box">', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">TODAY’S INTAKE</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="metric-value">{today_total:,} ml  <span style="font-size:1.3rem; font-weight:500; color:#567481;">·  {today_cups:g} cups</span></div>',
            unsafe_allow_html=True
        )

        if today_total >= today_goal:
            diff = today_total - today_goal
            status_text = 'Goal reached!' if diff == 0 else f'+{diff:,} ml above goal'
            st.markdown(f'<div style="color:#197f9b; font-weight:600; margin: 4px 0 14px 0;">{status_text}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="color:#567481; margin: 4px 0 14px 0;">{remaining_ml:,} ml remaining  ·  {remaining_cups:g} cups</div>', unsafe_allow_html=True)

        # Progress bar (Streamlit st.progress expects 0.0 to 1.0)
        capped_progress = min(1.0, max(0.0, today_total / today_goal if today_goal > 0 else 0.0))
        st.progress(capped_progress)
        st.markdown(f'<div style="color:#567481; font-size:0.9rem; margin-top:4px;">{percent:.1f}% of your chosen goal</div>', unsafe_allow_html=True)

        st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)

        # Quick Log Button (+250 ml)
        if st.button('💧 +250 ml  ·  1 cup', key='quick_add_btn', use_container_width=True, type='primary'):
            log_water_intake(250)
            st.rerun()

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Custom ml entry form
        st.markdown('<div style="font-size:0.9rem; color:#567481; font-weight:600; margin-bottom:4px;">Or enter an amount (ml)</div>', unsafe_allow_html=True)
        custom_cols = st.columns([3, 1])
        with custom_cols[0]:
            custom_input = st.text_input(
                'Custom ml amount',
                value='250',
                key='custom_ml_field',
                label_visibility='collapsed',
                placeholder='e.g. 250'
            )
        with custom_cols[1]:
            if st.button('Add water', key='custom_add_btn', use_container_width=True):
                parsed_val, err = parse_positive_whole_number(
                    custom_input, MAX_SINGLE_INTAKE_ML, 'Amount'
                )
                if err:
                    st.session_state.feedback_msg = err
                    st.session_state.feedback_type = 'error'
                else:
                    log_water_intake(parsed_val)
                st.rerun()

        # Feedback Message Box
        if st.session_state.feedback_type == 'error':
            st.error(st.session_state.feedback_msg)
        elif st.session_state.feedback_type == 'success':
            st.success(st.session_state.feedback_msg)
        else:
            st.info(st.session_state.feedback_msg)

        # Milestone Guidance Text
        heading, detail = reaction(percent)
        st.markdown(f'### {heading}')
        warn_style = 'color:#97501b;' if percent > 100 else 'color:#567481;'
        st.markdown(f'<div style="{warn_style} font-size:0.95rem; line-height:1.4;">{detail}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # RIGHT COLUMN: GOALS & ANIMATED MASCOT BOTTLE
    # -----------------------------------------------------------------------
    with col_right:
        st.markdown('<div class="card-box">', unsafe_allow_html=True)
        st.markdown('### Daily goal')

        # Age Group Selector
        current_age = st.session_state.age_group
        age_options = list(DEFAULTS.keys())
        selected_age = st.selectbox(
            'Choose your age group:',
            options=age_options,
            index=age_options.index(current_age) if current_age in age_options else 2,
            key='age_group_selector'
        )

        # Handle age change
        if selected_age != st.session_state.age_group:
            st.session_state.age_group = selected_age
            new_default = DEFAULTS[selected_age]
            st.session_state.default_goal = new_default
            st.session_state.daily_goals[today] = new_default
            st.session_state.feedback_msg = 'Age starting goal applied and saved for today.'
            st.session_state.feedback_type = 'info'
            st.rerun()

        # Side-by-side display of Standard Reference vs User-Set Goal
        st.markdown(f'''
        <div style="background-color:#edf7fa; border-radius:8px; padding:12px; margin: 10px 0 16px 0; border:1px solid #c7e1e8;">
          <div style="font-size:0.8rem; font-weight:700; color:#567481; text-transform:uppercase;">FA-1 Standard Reference</div>
          <div style="font-size:1.05rem; font-weight:700; color:#15394c; margin:2px 0;">{STANDARDS[selected_age]}</div>
          <div style="font-size:0.8rem; color:#567481; margin-top:2px;">{GUIDANCE[selected_age]}</div>
        </div>
        ''', unsafe_allow_html=True)

        st.markdown(f'<div class="metric-value" style="font-size:1.8rem;">{today_goal:,} ml <span style="font-size:1.1rem; color:#567481;">/ {goal_cups:g} cups</span></div>', unsafe_allow_html=True)

        # Adjust Goal Form
        st.markdown('<div style="font-size:0.9rem; color:#567481; font-weight:600; margin:10px 0 4px 0;">Adjust your goal (ml)</div>', unsafe_allow_html=True)
        goal_cols = st.columns([3, 1])
        with goal_cols[0]:
            goal_input_val = st.text_input(
                'Adjust goal',
                value=str(today_goal),
                key='goal_adjust_field',
                label_visibility='collapsed'
            )
        with goal_cols[1]:
            if st.button('Apply', key='apply_goal_btn', use_container_width=True):
                parsed_goal, goal_err = parse_positive_whole_number(
                    goal_input_val, MAX_DAILY_GOAL_ML, 'Daily goal'
                )
                if goal_err:
                    st.session_state.feedback_msg = goal_err
                    st.session_state.feedback_type = 'error'
                else:
                    st.session_state.daily_goals[today] = parsed_goal
                    st.session_state.default_goal = parsed_goal
                    st.session_state.feedback_msg = 'Daily goal updated and saved for today and future days.'
                    st.session_state.feedback_type = 'success'
                st.rerun()

        # Bottle Mascot Rendering
        st.markdown(render_bottle_svg(visual_frac, percent), unsafe_allow_html=True)
        st.markdown('<div style="text-align:center; font-size:0.8rem; color:#567481;">1 app cup = 250 ml</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # BOTTOM ACTION BAR & RESET CONFIRMATION
    # -----------------------------------------------------------------------
    st.divider()
    action_cols = st.columns([2, 1, 1])

    with action_cols[0]:
        st.markdown(
            '<div style="font-size:0.85rem; color:#567481; padding-top:6px;">'
            'Editable starting goals · Fluid guidance includes other drinks  \n'
            'Client session memory · Follow any clinician-set fluid limits'
            '</div>',
            unsafe_allow_html=True
        )

    with action_cols[2]:
        if st.button('Clear today’s intake', key='clear_intake_btn', use_container_width=True):
            st.session_state.show_reset_confirm = True
            st.rerun()

    # Reset Confirmation / Cancellation Dialog
    if st.session_state.show_reset_confirm:
        st.warning('⚠️ Are you sure you want to clear today’s intake? Your age group, goal, and previous days’ history will be kept.')
        confirm_cols = st.columns([1, 1, 3])
        with confirm_cols[0]:
            if st.button('Yes, clear intake', type='primary', use_container_width=True):
                st.session_state.water_entries = [
                    e for e in st.session_state.water_entries
                    if e['date'] != today
                ]
                st.session_state.feedback_msg = 'Today’s intake was cleared. History and preferences preserved.'
                st.session_state.feedback_type = 'info'
                st.session_state.show_reset_confirm = False
                st.rerun()
        with confirm_cols[1]:
            if st.button('Cancel', use_container_width=True):
                st.session_state.show_reset_confirm = False
                st.rerun()

    # -----------------------------------------------------------------------
    # TAB: REPORTS / HISTORY & 24-HOUR MATPLOTLIB BAR CHART
    # -----------------------------------------------------------------------
    with st.expander('📊 Daily Graph Report & History', expanded=False):
        # Collect recorded dates from session
        entry_dates = {e['date'] for e in st.session_state.water_entries}
        goal_dates = set(st.session_state.daily_goals.keys())
        recorded_dates = sorted(list(entry_dates.union(goal_dates)), reverse=True)
        if today not in recorded_dates:
            recorded_dates.insert(0, today)

        rep_date = st.selectbox(
            'Select Report Date:',
            options=recorded_dates,
            key='history_date_select'
        )

        is_rep_today = (rep_date == today)
        rep_goal = st.session_state.daily_goals.get(rep_date, st.session_state.default_goal)
        rep_total = get_day_total(rep_date)
        rep_entries = get_day_entry_count(rep_date)
        rep_hourly = get_hourly_totals(rep_date)
        rep_percent = (rep_total / rep_goal * 100) if rep_goal > 0 else 0.0

        badge_text = '● IN PROGRESS (TODAY)' if is_rep_today else '✓ COMPLETED DAY'
        st.markdown(f'<span class="stat-badge">{badge_text}</span>', unsafe_allow_html=True)

        # Summary Metric Cards
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric('Total Intake', f'{rep_total:,} ml', f'{rep_total/CUP_ML:g} cups')
        sc2.metric('Day Goal', f'{rep_goal:,} ml', f'{rep_goal/CUP_ML:g} cups')
        sc3.metric('Achieved', f'{rep_percent:.1f}%')
        if rep_total >= rep_goal:
            sc4.metric('Outcome', 'Goal Reached', f'+{rep_total-rep_goal:,} ml above goal')
        else:
            sc4.metric('Remaining', f'{rep_goal-rep_total:,} ml', f'{(rep_goal-rep_total)/CUP_ML:g} cups left')

        st.markdown(f'**Log Summary:** {rep_entries} {"drink" if rep_entries==1 else "drinks"} logged for {rep_date}.')

        # Matplotlib 24-Hour Bar Chart
        fig = Figure(figsize=(9, 3.6), dpi=100)
        fig.patch.set_facecolor('#ffffff')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#edf7fa')

        hours = list(range(24))
        amounts = [rep_hourly.get(h, 0) for h in hours]

        ax.bar(hours, amounts, color='#197f9b', edgecolor='#c7e1e8', width=0.65, zorder=3)
        ax.set_xlabel('Hour of day', color='#15394c', fontsize=10, labelpad=6)
        ax.set_ylabel('Water logged (ml)', color='#15394c', fontsize=10, labelpad=6)

        title_suffix = ' (In progress)' if is_rep_today else ' (Completed)'
        ax.set_title(f'Hourly Water Intake — {rep_date}{title_suffix}', color='#15394c', fontsize=11, fontweight='bold', pad=10)

        tick_hours = list(range(0, 24, 2))
        ax.set_xticks(tick_hours)
        ax.set_xticklabels([f'{h:02d}:00' for h in tick_hours], color='#567481', fontsize=8)
        ax.tick_params(axis='y', colors='#567481', labelsize=8)

        for spine in ax.spines.values():
            spine.set_color('#c7e1e8')
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, color='#c7e1e8', zorder=0)
        ax.set_axisbelow(True)

        fig.tight_layout()
        st.pyplot(fig)


if __name__ == '__main__':
    main()
