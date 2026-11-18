"""WATERBUDDY — beginner-friendly Python desktop app with SQLite storage & daily reports.
Run: python waterbuddy.py
Requires: Python 3 with Tkinter, sqlite3, and matplotlib.

LEARN THE CODE
1. DATABASE ARCHITECTURE:
   - Uses Python's built-in sqlite3 module for local, single-user desktop storage.
   - Data is stored in a permanent, writable user directory (%APPDATA%/WaterBuddy on Windows)
     so launching the app from any folder uses the exact same records.
   - Three tables:
     * 'preferences': stores user settings (age_group, default_goal, theme).
     * 'daily_goals': records the specific chosen goal for each date (YYYY-MM-DD).
     * 'water_entries': logs each drink with unique ID, timestamp, date, and integer ml.
   - Totals are always calculated dynamically from stored entries (SUM) to avoid drift.
   - Safe transactions with parameterized SQL prevent corruption and injection.

2. AUTOMATIC END-OF-DAY ROLLOVER:
   - A day concludes at midnight local time.
   - The app checks for date changes seamlessly using Tkinter's after() loop (non-blocking)
     and verifies the date before every intake or goal change.
   - When midnight crosses:
     * Previous day's entries and goal are archived in history.
     * New day begins at 0 ml.
     * The default goal carries forward automatically.
     * The previous day's graph report is displayed once.
     * If Reports / History is already open, it immediately updates its date choices,
       marks yesterday as completed, and marks today as in progress.
   - If the app was closed at midnight, the most recent completed day report opens
     automatically upon next launch without repetitive pop-ups.

3. DAILY GRAPH REPORT & HISTORY:
   - Separate Tkinter window accessible via "Reports / History".
   - Select any recorded calendar date from the dropdown.
   - Shows intake in ml and cups (1 cup = 250 ml), goal, percentage (including >100%),
     remaining or exceeded amounts, and entry count.
   - Embeds a Matplotlib 24-hour bar chart (00:00 to 23:00) styled to match the active theme.
   - Clearly marks today as "In progress" and distinguishes recorded zero-intake days
     from dates with no tracking data.

4. HEALTH CONTEXT & FA-1 STORYBOARD GUIDANCE:
   Defaults are demonstration starting points from the FA-1 storyboard, NOT mandatory
   prescriptions. Fluid guidance includes milk and other drinks. The app only counts what
   you log; it cannot measure hydration, drinking speed, sodium, or water intoxication.
   Needs vary with age, sex, activity, weather, health, and clinician instructions.
"""

import os
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date, timedelta
import random
import tkinter as tk
from tkinter import ttk, messagebox

# Matplotlib configuration for Tkinter embedding
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---------------------------------------------------------------------------
# 1. CONSTANTS, GUIDANCE & THEMES (FA-1 Storyboard Aligned)
# ---------------------------------------------------------------------------
CUP_ML = 250

# Documented technical limits (to prevent integer overflow, GUI distortion, or SQLite crashes).
# NOTE: These are application software constraints, NOT medical recommendations.
MAX_SINGLE_INTAKE_ML = 10_000   # 10 litres per single log entry
MAX_DAILY_GOAL_ML = 20_000      # 20 litres for a daily goal

# FA-1 Storyboard Starting Goals
DEFAULTS = {
    'Children (4–8 years)': 1200,
    'Teens (9–13 years)': 1700,
    'Adults (14–64 years)': 2000,
    'Seniors (65+ years)': 1700,
}

# FA-1 Storyboard Standard Reference Ranges
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

LEGACY_AGE_MAP = {
    'Child (1–8)': 'Children (4–8 years)',
    'Teen (9–17)': 'Teens (9–13 years)',
    'Adult (18–64)': 'Adults (14–64 years)',
    'Senior citizen (65+)': 'Seniors (65+ years)',
}

TIPS = [
    'Keep your water nearby while studying.',
    'Spread your drinks across the day.',
    'Other drinks count toward fluid intake too.',
    'Log what you actually drink. There is no need to chase a score.',
]

THEMES = {
    'light': {
        'bg': '#e9f3f6',
        'card': '#ffffff',
        'text': '#15394c',
        'muted': '#567481',
        'soft': '#edf7fa',
        'accent': '#197f9b',
        'water': '#61c8d6',
        'line': '#c7e1e8',
        'warn': '#97501b',
    },
    'dark': {
        'bg': '#10232f',
        'card': '#193441',
        'text': '#edfaff',
        'muted': '#aec6d0',
        'soft': '#234653',
        'accent': '#64cbdc',
        'water': '#3ba9c2',
        'line': '#365b6b',
        'warn': '#ffcd93',
    },
}


def parse_positive_whole_number(raw_value, max_limit, field_name="Amount"):
    """
    Validate and parse integer ml input.
    Rejects:
      - None, empty, whitespace strings
      - Fractional / decimal numbers (e.g. '250.5')
      - Non-numeric strings
      - Zero or negative values
      - Numbers exceeding technical limits (prevents SQLite OverflowError)
    Returns (int_value, None) on success or (None, error_message) on failure.
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
            "This limit is a software safeguard, not medical advice."
        )
    return val, None


def calculate(total, goal):
    """Return remaining ml, actual percentage, and a capped visual fraction (0.0 to 1.0)."""
    if goal <= 0:
        goal = 2000
    return max(0, goal - total), (total / goal) * 100, min(total / goal, 1.0)


def reaction(percent):
    """Return factual guidance headings and details based on percentage achieved."""
    if percent > 100:
        return (
            'Goal exceeded — no need to chase more.',
            'Do not force extra water. Too much, especially quickly, can cause water '
            'intoxication (low sodium). Being over this goal alone does not mean intoxication.',
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


# ---------------------------------------------------------------------------
# 2. SYSTEM CLOCK ABSTRACTION (Injectable for Date Testing)
# ---------------------------------------------------------------------------
class SystemClock:
    """Provides the current date and time. Can be swapped with a simulated clock in tests."""
    def now(self):
        return datetime.now()

    def today_str(self):
        return self.now().strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# 3. DATABASE STORAGE (SQLite via Built-in sqlite3)
# ---------------------------------------------------------------------------
def get_default_db_path():
    """Return a stable, writable user-data folder path across working directories."""
    base_dir = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = os.path.join(base_dir, 'WaterBuddy')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'waterbuddy.db')


class WaterBuddyDB:
    """Manages SQLite storage for preferences, daily goals, and water entries."""
    def __init__(self, db_path=None):
        self.db_path = db_path if db_path is not None else get_default_db_path()
        self.init_db()

    @contextmanager
    def _connection(self):
        """Context manager that handles connection lifecycle and automatic closing."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Create database tables and indices if they do not exist."""
        with self._connection() as conn:
            cursor = conn.cursor()
            # User preferences: theme, age group, current default goal
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            # Daily chosen goals and report auto-display status
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_goals (
                    date TEXT PRIMARY KEY,
                    goal INTEGER NOT NULL,
                    report_shown INTEGER DEFAULT 0
                )
            ''')
            # Individual water intake entries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS water_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    amount INTEGER NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_entries_date ON water_entries(date)
            ''')
            conn.commit()

    def get_preference(self, key, default=None):
        """Retrieve a stored user preference."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM preferences WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    def set_preference(self, key, value):
        """Save a user preference immediately."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO preferences (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ''', (key, str(value)))
            conn.commit()

    def get_or_create_daily_goal(self, date_str, default_goal):
        """Fetch the day's recorded goal, or initialize it with default_goal if new."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT goal FROM daily_goals WHERE date = ?', (date_str,))
            row = cursor.fetchone()
            if row:
                return int(row['goal'])
            cursor.execute('''
                INSERT INTO daily_goals (date, goal, report_shown)
                VALUES (?, ?, 0)
            ''', (date_str, int(default_goal)))
            conn.commit()
            return int(default_goal)

    def set_daily_goal(self, date_str, goal):
        """Set or update the goal specifically for date_str with bounds check."""
        if not isinstance(goal, int) or goal <= 0 or goal > MAX_DAILY_GOAL_ML:
            raise ValueError(f'Daily goal must be a positive integer up to {MAX_DAILY_GOAL_ML:,} ml.')
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO daily_goals (date, goal, report_shown)
                    VALUES (?, ?, 0)
                    ON CONFLICT(date) DO UPDATE SET goal = excluded.goal
                ''', (date_str, int(goal)))
                conn.commit()
        except (sqlite3.Error, OverflowError) as e:
            raise sqlite3.Error(f'Database write error: {e}')

    def add_water_entry(self, timestamp_iso, date_str, amount):
        """Log a water intake entry in integer ml with technical bounds check."""
        if not isinstance(amount, int) or amount <= 0 or amount > MAX_SINGLE_INTAKE_ML:
            raise ValueError(f'Amount must be a positive integer up to {MAX_SINGLE_INTAKE_ML:,} ml.')
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO water_entries (timestamp, date, amount)
                    VALUES (?, ?, ?)
                ''', (timestamp_iso, date_str, amount))
                conn.commit()
        except (sqlite3.Error, OverflowError) as e:
            raise sqlite3.Error(f'Database write error: {e}')

    def get_day_total(self, date_str):
        """Dynamically calculate total intake for date_str from stored entries."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM water_entries
                WHERE date = ?
            ''', (date_str,))
            row = cursor.fetchone()
            return int(row['total']) if row else 0

    def get_day_entry_count(self, date_str):
        """Return the number of entries logged for a date."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) AS cnt FROM water_entries WHERE date = ?', (date_str,))
            row = cursor.fetchone()
            return int(row['cnt']) if row else 0

    def get_hourly_totals(self, date_str):
        """Return a dict of hours 0..23 mapped to total ml logged in that hour."""
        hourly = {h: 0 for h in range(24)}
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, amount FROM water_entries WHERE date = ?
            ''', (date_str,))
            rows = cursor.fetchall()
            for row in rows:
                ts = row['timestamp']
                try:
                    dt = datetime.fromisoformat(ts)
                    h = dt.hour
                    hourly[h] += int(row['amount'])
                except Exception:
                    pass
        return hourly

    def clear_day_entries(self, date_str):
        """Delete only entries logged for date_str. Keeps all goals and past days."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM water_entries WHERE date = ?', (date_str,))
            conn.commit()

    def is_date_recorded(self, date_str):
        """Return True if date_str has a tracked daily goal or at least one water entry."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM daily_goals WHERE date = ? LIMIT 1', (date_str,))
            if cursor.fetchone():
                return True
            cursor.execute('SELECT 1 FROM water_entries WHERE date = ? LIMIT 1', (date_str,))
            return cursor.fetchone() is not None

    def get_all_recorded_dates(self):
        """Return a sorted descending list of all calendar dates recorded."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT date FROM daily_goals
                UNION
                SELECT date FROM water_entries
                ORDER BY date DESC
            ''')
            return [row['date'] for row in cursor.fetchall()]

    def get_unviewed_completed_dates(self, current_date_str):
        """Return dates prior to current_date_str that haven't been shown in an auto-report."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT date FROM daily_goals
                WHERE date < ? AND report_shown = 0
                ORDER BY date DESC
            ''', (current_date_str,))
            return [row['date'] for row in cursor.fetchall()]

    def mark_report_shown(self, date_str):
        """Mark a completed day's report as viewed so it does not pop up repeatedly."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE daily_goals SET report_shown = 1 WHERE date = ?', (date_str,))
            conn.commit()

    def mark_all_completed_reports_shown(self, current_date_str):
        """Mark all past unviewed days as acknowledged to avoid cascading pop-ups."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE daily_goals SET report_shown = 1 WHERE date < ?', (current_date_str,))
            conn.commit()


# ---------------------------------------------------------------------------
# 4. HOVER BUTTON ANIMATION
# ---------------------------------------------------------------------------
class HoverButton(tk.Canvas):
    """A keyboard-accessible button that smoothly scales up on hover or focus."""
    def __init__(self, parent, colors, command):
        super().__init__(parent, height=92, bg=colors['card'], highlightthickness=0,
                         takefocus=True, cursor='hand2')
        self.colors, self.command = colors, command
        self.scale = self.target = 1.0
        self.timer = None
        self.bind('<Configure>', lambda e: self.paint())
        self.bind('<Enter>', lambda e: self.grow(1.06))
        self.bind('<Leave>', lambda e: self.grow(1.0))
        self.bind('<FocusIn>', lambda e: self.grow(1.06))
        self.bind('<FocusOut>', lambda e: self.grow(1.0))
        self.bind('<Button-1>', lambda e: self.command())
        self.bind('<Return>', lambda e: self.command())
        self.bind('<space>', lambda e: self.command())

    def grow(self, target):
        self.target = target
        if self.timer is None:
            self.animate()

    def animate(self):
        self.scale += (self.target - self.scale) * 0.30
        if abs(self.target - self.scale) < 0.002:
            self.scale = self.target
            self.timer = None
        else:
            self.timer = self.after(16, self.animate)
        self.paint()

    def paint(self):
        self.delete('all')
        width = min(300, max(130, self.winfo_width() - 30)) * self.scale
        height = 55 * self.scale
        x, y = self.winfo_width() / 2, 46
        self.create_oval(x - width / 2, y - height / 2, x - width / 2 + height, y + height / 2,
                         fill=self.colors['accent'], outline='')
        self.create_oval(x + width / 2 - height, y - height / 2, x + width / 2, y + height / 2,
                         fill=self.colors['accent'], outline='')
        self.create_rectangle(x - width / 2 + height / 2, y - height / 2,
                              x + width / 2 - height / 2, y + height / 2,
                              fill=self.colors['accent'], outline='')
        self.create_text(x, y, text='+250 ml  ·  1 cup',
                         font=('Arial', int(16 * self.scale), 'bold'),
                         fill='#10232f' if self.colors['accent'] == '#64cbdc' else 'white')

    def destroy(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
        super().destroy()


# ---------------------------------------------------------------------------
# 5. DAILY GRAPH REPORT & HISTORY WINDOW
# ---------------------------------------------------------------------------
class ReportWindow(tk.Toplevel):
    """Separate window displaying daily statistics and hourly Matplotlib bar chart."""
    def __init__(self, parent, db, clock, current_date, selected_date=None, auto_popup=False):
        super().__init__(parent)
        self.app = parent
        self.db = db
        self.clock = clock
        self.current_date = current_date
        self.auto_popup = auto_popup

        self.title('WaterBuddy — Daily Report & History')
        self.geometry('860x780')
        self.minsize(760, 680)

        # Ensure window appears on top when auto-popping up
        if auto_popup:
            self.lift()
            self.attributes('-topmost', True)
            self.after_idle(lambda: self.attributes('-topmost', False))

        self.theme = self.db.get_preference('theme', 'light')
        self.colors = THEMES[self.theme]
        self.configure(bg=self.colors['bg'])

        # Selected date tracking
        if selected_date is None:
            selected_date = self.current_date
        self.selected_date = tk.StringVar(value=selected_date)

        self.fig = None
        self.canvas = None
        self.date_combo = None
        self.build_ui()
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def on_close(self):
        """Clean up Matplotlib canvas and resources on close."""
        if self.fig:
            self.fig.clear()
        self.destroy()

    def update_theme(self, new_theme):
        """Update window theme dynamically if changed while window is open."""
        self.theme = new_theme
        self.colors = THEMES[self.theme]
        self.configure(bg=self.colors['bg'])
        self.build_ui()

    def on_date_rollover(self, new_current_date):
        """
        Called when a calendar date rollover occurs while the report window is open.
        Refreshes current date, date choices combobox, status badge, and chart.
        """
        self.current_date = new_current_date
        recorded_dates = self.db.get_all_recorded_dates()
        if self.current_date not in recorded_dates:
            recorded_dates.insert(0, self.current_date)
        if hasattr(self, 'date_combo') and self.date_combo is not None and self.date_combo.winfo_exists():
            self.date_combo.configure(values=recorded_dates)
        self.load_report()

    def build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()

        c = self.colors

        # Header bar
        header = tk.Frame(self, bg=c['bg'])
        header.pack(fill='x', padx=28, pady=(20, 12))

        title_text = 'End-of-Day Report' if self.auto_popup else 'Daily Hydration Report'
        tk.Label(header, text=title_text, font=('Arial', 20, 'bold'),
                 bg=c['bg'], fg=c['text']).pack(side='left')

        # Close button
        tk.Button(header, text='Close', command=self.on_close, font=('Arial', 11, 'bold'),
                  bg=c['soft'], fg=c['text'], activebackground=c['line'],
                  activeforeground=c['text'], relief='flat', padx=16, pady=6,
                  cursor='hand2').pack(side='right')

        # Date selector row
        sel_row = tk.Frame(self, bg=c['card'], padx=20, pady=12)
        sel_row.pack(fill='x', padx=28, pady=(0, 16))

        tk.Label(sel_row, text='Select Date:', font=('Arial', 12, 'bold'),
                 bg=c['card'], fg=c['text']).pack(side='left', padx=(0, 10))

        recorded_dates = self.db.get_all_recorded_dates()
        if self.current_date not in recorded_dates:
            recorded_dates.insert(0, self.current_date)

        # Style Combobox
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Report.TCombobox', fieldbackground=c['soft'],
                        background=c['soft'], foreground=c['text'], padding=6)

        self.date_combo = ttk.Combobox(sel_row, textvariable=self.selected_date,
                                       values=recorded_dates, state='readonly',
                                       font=('Arial', 11), style='Report.TCombobox', width=16)
        self.date_combo.pack(side='left')
        self.date_combo.bind('<<ComboboxSelected>>', lambda e: self.load_report())

        self.status_badge = tk.Label(sel_row, font=('Arial', 10, 'bold'),
                                     bg=c['soft'], fg=c['accent'], padx=10, pady=4)
        self.status_badge.pack(side='left', padx=(14, 0))

        # Main Report Content Area
        self.content_frame = tk.Frame(self, bg=c['card'], padx=24, pady=20)
        self.content_frame.pack(fill='both', expand=True, padx=28, pady=(0, 20))

        self.load_report()

    def load_report(self):
        """Fetch and render statistics and Matplotlib chart for the selected date."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        c = self.colors
        target_date = self.selected_date.get().strip()

        # Update status badge
        is_today = (target_date == self.current_date)
        if is_today:
            self.status_badge.configure(text='● IN PROGRESS (TODAY)',
                                        fg=c['accent'], bg=c['soft'])
        else:
            self.status_badge.configure(text='✓ COMPLETED DAY',
                                        fg=c['muted'], bg=c['soft'])

        # Check if date has tracking data
        if not self.db.is_date_recorded(target_date):
            no_data_frame = tk.Frame(self.content_frame, bg=c['card'])
            no_data_frame.pack(fill='both', expand=True, pady=40)
            tk.Label(no_data_frame, text='No Tracking Data Recorded',
                     font=('Arial', 16, 'bold'), bg=c['card'], fg=c['warn']).pack(pady=(20, 8))
            tk.Label(no_data_frame,
                     text=f'There are no logged drinks or goal records for {target_date}.\n'
                          'Choose a recorded date from the list above.',
                     font=('Arial', 11), bg=c['card'], fg=c['muted'], justify='center').pack()
            return

        # Fetch recorded goal, intake, and hourly logs
        default_goal = int(self.db.get_preference('default_goal', '2000'))
        day_goal = self.db.get_or_create_daily_goal(target_date, default_goal)
        total_ml = self.db.get_day_total(target_date)
        entry_count = self.db.get_day_entry_count(target_date)
        hourly_data = self.db.get_hourly_totals(target_date)

        total_cups = total_ml / CUP_ML
        goal_cups = day_goal / CUP_ML
        percent = (total_ml / day_goal * 100) if day_goal > 0 else 0.0

        # Stats Grid Summary
        stats_frame = tk.Frame(self.content_frame, bg=c['card'])
        stats_frame.pack(fill='x', pady=(0, 16))

        for i in range(4):
            stats_frame.columnconfigure(i, weight=1, uniform='stats')

        def stat_box(col, label_text, val_text, sub_text=''):
            f = tk.Frame(stats_frame, bg=c['soft'], padx=12, pady=10)
            f.grid(row=0, column=col, sticky='nsew', padx=4)
            tk.Label(f, text=label_text, font=('Arial', 9, 'bold'),
                     bg=c['soft'], fg=c['muted']).pack(anchor='w')
            tk.Label(f, text=val_text, font=('Arial', 15, 'bold'),
                     bg=c['soft'], fg=c['text']).pack(anchor='w', pady=(3, 1))
            if sub_text:
                tk.Label(f, text=sub_text, font=('Arial', 9),
                         bg=c['soft'], fg=c['muted']).pack(anchor='w')

        stat_box(0, 'TOTAL INTAKE', f'{total_ml:,} ml', f'{total_cups:g} cups (250 ml/cup)')
        stat_box(1, 'DAY GOAL', f'{day_goal:,} ml', f'{goal_cups:g} cups')
        stat_box(2, 'ACHIEVED', f'{percent:.1f}%', 'of daily target')

        if total_ml >= day_goal:
            diff = total_ml - day_goal
            sub = 'Goal met' if diff == 0 else f'+{diff:,} ml above goal'
            stat_box(3, 'OUTCOME', 'Goal Reached', sub)
        else:
            remaining = day_goal - total_ml
            stat_box(3, 'REMAINING', f'{remaining:,} ml', f'{remaining/CUP_ML:g} cups left')

        # Entry Count & Health Context Note
        info_row = tk.Frame(self.content_frame, bg=c['card'])
        info_row.pack(fill='x', pady=(0, 12))

        if total_ml == 0:
            intake_status_msg = f'Recorded day with 0 ml logged ({entry_count} entries).'
        else:
            intake_status_msg = f'{entry_count} water {"entry" if entry_count == 1 else "entries"} logged.'

        tk.Label(info_row, text=f'Log Summary: {intake_status_msg}',
                 font=('Arial', 10, 'bold'), bg=c['card'], fg=c['muted']).pack(side='left')

        heading, detail = reaction(percent)
        note_color = c['warn'] if percent > 100 else c['muted']
        tk.Label(self.content_frame, text=f'{heading} {detail}',
                 font=('Arial', 10), bg=c['card'], fg=note_color,
                 wraplength=780, justify='left').pack(anchor='w', pady=(0, 14))

        # Embed Matplotlib Bar Chart
        self.embed_chart(target_date, hourly_data, is_today)

    def embed_chart(self, target_date, hourly_data, is_today):
        """Draw 24-hour water logging chart in Matplotlib and embed it in Tkinter."""
        c = self.colors

        # Create Figure
        fig = Figure(figsize=(7.5, 3.4), dpi=100)
        fig.patch.set_facecolor(c['card'])

        ax = fig.add_subplot(111)
        ax.set_facecolor(c['soft'])

        hours = list(range(24))
        amounts = [hourly_data.get(h, 0) for h in hours]

        bars = ax.bar(hours, amounts, color=c['accent'], edgecolor=c['line'],
                      width=0.65, zorder=3)

        # Labeling and Axis Formatting
        ax.set_xlabel('Hour of day', color=c['text'], fontsize=10, labelpad=6)
        ax.set_ylabel('Water logged (ml)', color=c['text'], fontsize=10, labelpad=6)

        status_suffix = ' (In progress)' if is_today else ' (Completed)'
        ax.set_title(f'Hourly Water Intake — {target_date}{status_suffix}',
                     color=c['text'], fontsize=11, fontweight='bold', pad=10)

        # 24-hour labels (ticks every 2 hours: 00:00, 02:00, ..., 22:00)
        tick_hours = list(range(0, 24, 2))
        ax.set_xticks(tick_hours)
        ax.set_xticklabels([f'{h:02d}:00' for h in tick_hours],
                           color=c['muted'], fontsize=8)
        ax.tick_params(axis='y', colors=c['muted'], labelsize=8)

        # Spines and Grid
        for spine in ax.spines.values():
            spine.set_color(c['line'])
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, color=c['line'], zorder=0)
        ax.set_axisbelow(True)

        fig.tight_layout()

        # Canvas embedding
        self.canvas = FigureCanvasTkAgg(fig, master=self.content_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.fig = fig

    def refresh_if_viewing(self, date_str):
        """Refresh content dynamically if currently viewing date_str."""
        if self.selected_date.get().strip() == date_str:
            self.load_report()


# ---------------------------------------------------------------------------
# 6. MAIN APPLICATION CONTROLLER
# ---------------------------------------------------------------------------
class WaterBuddyApp:
    """Main application controller managing Tkinter UI, SQLite DB, and date rollover."""
    def __init__(self, root, db=None, clock=None):
        self.root = root
        self.clock = clock if clock is not None else SystemClock()
        self.db = db if db is not None else WaterBuddyDB()

        self.root.title('WaterBuddy')
        self.root.geometry('1080x820')
        self.root.minsize(1020, 780)

        # Load persisted preferences or sensible defaults
        self.theme = self.db.get_preference('theme', 'light')
        stored_age = self.db.get_preference('age_group', 'Adults (14–64 years)')
        # Handle legacy age keys gracefully if upgrading
        stored_age = LEGACY_AGE_MAP.get(stored_age, stored_age)
        if stored_age not in DEFAULTS:
            stored_age = 'Adults (14–64 years)'
        self.age = tk.StringVar(value=stored_age)

        default_goal_for_age = DEFAULTS.get(stored_age, 2000)
        stored_default_goal = int(self.db.get_preference('default_goal', str(default_goal_for_age)))

        # Track current local date and restore today's goal and total
        self.current_date = self.clock.today_str()
        self.goal = self.db.get_or_create_daily_goal(self.current_date, stored_default_goal)
        self.total = self.db.get_day_total(self.current_date)

        # Tkinter UI variables
        self.goal_input = tk.StringVar(value=str(self.goal))
        self.custom = tk.StringVar(value='250')
        self.feedback = tk.StringVar(value='Ready when you are.')

        # Animation states
        self.visual_fraction = 0.0
        self.bottle_timer = None
        self.rollover_job = None
        self.tip = random.choice(TIPS)

        self.report_window = None

        # Build UI and start date rollover listener
        self.build_ui()
        self.schedule_rollover_check()

        # Check for unviewed completed day reports on startup
        self.root.after(350, self.check_startup_missed_reports)

    # -----------------------------------------------------------------------
    # Date Rollover & Automatic Daily Reports
    # -----------------------------------------------------------------------
    def schedule_rollover_check(self):
        """Non-blocking periodic check for date changes using Tkinter's after()."""
        self.check_date_rollover()
        self.rollover_job = self.root.after(1000, self.schedule_rollover_check)

    def check_date_rollover(self):
        """Detect midnight crossing, archive previous day, reset today, and show report."""
        now_today = self.clock.today_str()
        if now_today != self.current_date:
            previous_date = self.current_date
            self.current_date = now_today

            # Carry forward user's current default goal
            stored_default_goal = int(self.db.get_preference(
                'default_goal', str(DEFAULTS.get(self.age.get(), 2000))))
            self.goal = self.db.get_or_create_daily_goal(self.current_date, stored_default_goal)
            self.goal_input.set(str(self.goal))

            # Start new day's intake at zero
            self.total = self.db.get_day_total(self.current_date)
            self.feedback.set(f'New day started ({self.current_date}). Intake reset to 0 ml.')
            self.refresh()

            # Mark previous day as auto-shown
            self.db.mark_report_shown(previous_date)

            # If report window is already open, refresh it with new date context
            if self.report_window is not None and self.report_window.winfo_exists():
                self.report_window.on_date_rollover(self.current_date)
                self.report_window.selected_date.set(previous_date)
                self.report_window.load_report()
                self.report_window.lift()
            else:
                self.open_reports_window(selected_date=previous_date, auto_popup=True)

    def check_startup_missed_reports(self):
        """If closed across midnight, prepare & show the most recent completed day report."""
        unviewed = self.db.get_unviewed_completed_dates(self.current_date)
        if unviewed:
            # The list is sorted descending, so unviewed[0] is the most recent completed day
            most_recent_unviewed = unviewed[0]
            # Acknowledge all older unviewed days so we avoid repeated pop-ups
            self.db.mark_all_completed_reports_shown(self.current_date)
            self.open_reports_window(selected_date=most_recent_unviewed, auto_popup=True)

    # -----------------------------------------------------------------------
    # Callbacks for Existing Controls
    # -----------------------------------------------------------------------
    def add_water(self, amount=None):
        """Validate input and save water intake entry immediately to SQLite."""
        self.check_date_rollover()
        if amount is None:
            amount, err_msg = parse_positive_whole_number(
                self.custom.get(), MAX_SINGLE_INTAKE_ML, "Amount"
            )
            if err_msg:
                self.feedback.set(err_msg)
                return
        else:
            if not isinstance(amount, int) or amount <= 0 or amount > MAX_SINGLE_INTAKE_ML:
                self.feedback.set(f"Enter an amount up to {MAX_SINGLE_INTAKE_ML:,} ml.")
                return

        timestamp_iso = self.clock.now().isoformat()
        try:
            self.db.add_water_entry(timestamp_iso, self.current_date, amount)
        except (sqlite3.Error, OverflowError, ValueError) as e:
            messagebox.showerror('Database Error', f'Failed to save intake to database:\n{e}')
            self.feedback.set('Save failed. Water intake was not recorded.')
            return

        # Dynamically calculate total from database
        self.total = self.db.get_day_total(self.current_date)
        self.feedback.set(f'Added {amount:,} ml ({amount/CUP_ML:g} cups).')
        self.refresh()

        if self.report_window and self.report_window.winfo_exists():
            self.report_window.refresh_if_viewing(self.current_date)

    def change_age(self, event=None):
        """Update age group preference, apply starting goal, and update database."""
        self.check_date_rollover()
        selected_age = self.age.get()
        new_goal = DEFAULTS.get(selected_age, 2000)

        try:
            self.db.set_preference('age_group', selected_age)
            self.db.set_preference('default_goal', str(new_goal))
            self.db.set_daily_goal(self.current_date, new_goal)
        except (sqlite3.Error, OverflowError, ValueError) as e:
            messagebox.showerror('Database Error', f'Failed to save age preference:\n{e}')
            self.feedback.set('Failed to save age setting to database.')
            return

        self.goal = new_goal
        self.goal_input.set(str(self.goal))
        self.feedback.set('Age starting goal applied and saved. Intake kept.')
        self.refresh()

        if self.report_window and self.report_window.winfo_exists():
            self.report_window.refresh_if_viewing(self.current_date)

    def save_goal(self):
        """Update today's goal and the default for future days without altering past days."""
        self.check_date_rollover()
        new_goal, err_msg = parse_positive_whole_number(
            self.goal_input.get(), MAX_DAILY_GOAL_ML, "Daily goal"
        )
        if err_msg:
            self.feedback.set(err_msg)
            return

        try:
            self.db.set_daily_goal(self.current_date, new_goal)
            self.db.set_preference('default_goal', str(new_goal))
        except (sqlite3.Error, OverflowError, ValueError) as e:
            messagebox.showerror('Database Error', f'Failed to update goal:\n{e}')
            self.feedback.set('Failed to save goal to database.')
            return

        self.goal = new_goal
        self.feedback.set('Daily goal updated and saved for today and future days.')
        self.refresh()

        if self.report_window and self.report_window.winfo_exists():
            self.report_window.refresh_if_viewing(self.current_date)

    def clear_today_intake(self):
        """Require confirmation, clear only today's entries, and preserve history."""
        self.check_date_rollover()
        confirmed = messagebox.askyesno(
            'Clear today’s intake?',
            'Are you sure you want to clear today’s logged water entries?\n\n'
            'Your age group, daily goal, preferences, and previous days’ history will be kept.',
        )
        if confirmed:
            try:
                self.db.clear_day_entries(self.current_date)
            except sqlite3.Error as e:
                messagebox.showerror('Database Error', f'Failed to clear intake:\n{e}')
                self.feedback.set('Database error: Unable to clear today’s intake.')
                return

            self.total = self.db.get_day_total(self.current_date)
            self.tip = random.choice(TIPS)
            self.feedback.set('Today’s intake was cleared. History and settings preserved.')
            self.refresh()

            if self.report_window and self.report_window.winfo_exists():
                self.report_window.refresh_if_viewing(self.current_date)

    def toggle_theme(self):
        """Toggle between light and dark themes and persist preference."""
        self.theme = 'dark' if self.theme == 'light' else 'light'
        try:
            self.db.set_preference('theme', self.theme)
        except sqlite3.Error:
            pass

        self.build_ui()
        if self.report_window and self.report_window.winfo_exists():
            self.report_window.update_theme(self.theme)

    def open_reports_window(self, selected_date=None, auto_popup=False):
        """Open or refocus the Daily Graph Report & History window."""
        if selected_date is None:
            selected_date = self.current_date

        if self.report_window is not None and self.report_window.winfo_exists():
            self.report_window.selected_date.set(selected_date)
            self.report_window.load_report()
            self.report_window.lift()
        else:
            self.report_window = ReportWindow(
                self.root, self.db, self.clock, self.current_date,
                selected_date=selected_date, auto_popup=auto_popup,
            )

    # -----------------------------------------------------------------------
    # Main UI Building & Drawing
    # -----------------------------------------------------------------------
    def build_ui(self):
        if self.bottle_timer is not None:
            self.root.after_cancel(self.bottle_timer)
            self.bottle_timer = None

        for widget in self.root.winfo_children():
            widget.destroy()

        c = THEMES[self.theme]
        self.root.configure(bg=c['bg'])

        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TCombobox', fieldbackground=c['soft'],
                        background=c['soft'], foreground=c['text'], padding=8)
        style.map('TCombobox',
                  fieldbackground=[('readonly', c['soft'])],
                  foreground=[('readonly', c['text'])])

        def text(parent, content='', size=12, bold=False, muted=False, **options):
            return tk.Label(parent, text=content,
                            font=('Arial', size, 'bold' if bold else 'normal'),
                            bg=parent.cget('bg'),
                            fg=c['muted'] if muted else c['text'], **options)

        def small_button(parent, title, action):
            return tk.Button(parent, text=title, command=action, font=('Arial', 11, 'bold'),
                             bg=c['soft'], fg=c['text'], activebackground=c['line'],
                             activeforeground=c['text'], relief='flat', padx=16, pady=10,
                             cursor='hand2')

        def entry(parent, variable):
            return tk.Entry(parent, textvariable=variable, font=('Arial', 16), width=10,
                            bg=c['soft'], fg=c['text'], insertbackground=c['text'],
                            relief='flat')

        # Header
        header = tk.Frame(self.root, bg=c['bg'])
        header.pack(fill='x', padx=32, pady=(24, 18))
        text(header, 'WaterBuddy', 26, True).pack(side='left')
        small_button(header, 'Light mode' if self.theme == 'dark' else 'Dark mode',
                     self.toggle_theme).pack(side='right')
        text(header, '  YOUR DAILY HYDRATION COMPANION', 10, muted=True).pack(side='left', padx=12)

        # Body Layout: Two columns
        body = tk.Frame(self.root, bg=c['bg'])
        body.pack(fill='both', expand=True, padx=32, pady=(0, 12))
        body.columnconfigure(0, weight=3, uniform='panels')
        body.columnconfigure(1, weight=2, uniform='panels')
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=c['card'], padx=26, pady=24)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        right = tk.Frame(body, bg=c['card'], padx=26, pady=24)
        right.grid(row=0, column=1, sticky='nsew')

        # Left Column: Intake Logging & Progress
        text(left, 'TODAY’S INTAKE', 11, True, True).pack(anchor='w')
        self.total_label = text(left, size=34, bold=True)
        self.total_label.pack(anchor='w', pady=(12, 0))

        self.remaining_label = text(left, muted=True)
        self.remaining_label.pack(anchor='w', pady=(3, 14))

        self.bar = tk.Canvas(left, height=12, bg=c['soft'], highlightthickness=0)
        self.bar.pack(fill='x')
        self.bar.bind('<Configure>', lambda e: self.draw_progress())

        self.percent_label = text(left, size=11, muted=True)
        self.percent_label.pack(anchor='w', pady=(8, 6))

        HoverButton(left, c, lambda: self.add_water(250)).pack(fill='x')

        text(left, 'Or enter an amount (ml)', 11, muted=True).pack(anchor='w')
        inputs = tk.Frame(left, bg=c['card'])
        inputs.pack(fill='x', pady=(8, 0))

        field = entry(inputs, self.custom)
        field.pack(side='left', fill='x', expand=True, ipady=8)
        field.bind('<Return>', lambda e: self.add_water())
        small_button(inputs, 'Add water', self.add_water).pack(side='left', padx=(10, 0))

        text(left, size=10, muted=True, textvariable=self.feedback,
             anchor='w', height=2).pack(fill='x', pady=(6, 0))

        self.message_label = text(left, size=17, bold=True, wraplength=470, justify='left')
        self.message_label.pack(anchor='w', pady=(14, 7))

        self.detail_label = text(left, size=12, muted=True, wraplength=470, justify='left')
        self.detail_label.pack(anchor='w')

        self.tip_label = text(left, size=11, muted=True, wraplength=470, justify='left')
        self.tip_label.pack(anchor='w', pady=(18, 0))

        # Right Column: Goal Settings & Animated Bottle
        text(right, 'Daily goal', 21, True).pack(anchor='w')
        text(right, 'Choose your age group', 11, muted=True).pack(anchor='w', pady=(15, 6))

        selector = ttk.Combobox(right, textvariable=self.age,
                                values=list(DEFAULTS.keys()), state='readonly', font=('Arial', 12))
        selector.pack(fill='x')
        selector.bind('<<ComboboxSelected>>', self.change_age)

        # Standard Reference vs User-set Goal (FA-1 requirement)
        self.standard_ref_label = text(right, size=10, muted=True, wraplength=320, justify='left')
        self.standard_ref_label.pack(anchor='w', pady=(6, 2))

        self.goal_label = text(right, size=20, bold=True)
        self.goal_label.pack(anchor='w', pady=(8, 4))

        text(right, 'Adjust your goal (ml)', 11, muted=True).pack(anchor='w')
        goal_row = tk.Frame(right, bg=c['card'])
        goal_row.pack(fill='x', pady=(6, 8))

        entry(goal_row, self.goal_input).pack(side='left', fill='x', expand=True, ipady=8)
        small_button(goal_row, 'Apply', self.save_goal).pack(side='left', padx=(8, 0))

        self.note_label = text(right, size=10, muted=True, wraplength=320, justify='left')
        self.note_label.pack(anchor='w')

        self.bottle = tk.Canvas(right, height=195, bg=c['card'], highlightthickness=0)
        self.bottle.pack(fill='x', pady=(12, 0))
        self.bottle.bind('<Configure>', lambda e: self.draw_bottle())

        text(right, '1 app cup = 250 ml', 10, muted=True).pack()

        # Footer Bar: Action Buttons & Accurate SQLite Information
        footer = tk.Frame(self.root, bg=c['bg'])
        footer.pack(fill='x', padx=32, pady=(0, 20))

        small_button(footer, 'Clear today’s intake', self.clear_today_intake).pack(side='right')
        small_button(footer, 'Reports / History',
                     lambda: self.open_reports_window(self.current_date)).pack(side='right', padx=(0, 10))

        text(
            footer,
            'Editable starting goals • Fluid guidance includes other drinks.\n'
            'Saved locally with SQLite • Automatic daily rollover • Follow any clinician-set fluid limit.',
            10, muted=True, justify='left',
        ).pack(side='left')

        self.refresh()

    def refresh(self):
        """Update text counters, feedback, and trigger canvas redraws."""
        remaining, percent, fraction = calculate(self.total, self.goal)
        self.total_label.configure(text=f'{self.total:,} ml  ·  {self.total/CUP_ML:g} cups')
        self.remaining_label.configure(
            text=f'{remaining:,} ml remaining  ·  {remaining/CUP_ML:g} cups'
        )
        self.percent_label.configure(text=f'{percent:.1f}% of your chosen goal')
        self.goal_label.configure(text=f'Chosen Goal: {self.goal:,} ml ({self.goal/CUP_ML:g} cups)')

        current_age = self.age.get()
        std_text = STANDARDS.get(current_age, '')
        self.standard_ref_label.configure(text=f'FA-1 Standard reference: {std_text}')

        guidance_text = GUIDANCE.get(current_age, '')
        self.note_label.configure(text=guidance_text)

        heading, detail = reaction(percent)
        self.message_label.configure(text=heading)
        self.detail_label.configure(
            text=detail, fg=THEMES[self.theme]['warn' if percent > 100 else 'muted']
        )
        self.tip_label.configure(text='TIP  ' + self.tip)

        self.draw_progress()
        self.animate_bottle()

    def draw_progress(self):
        if not hasattr(self, 'bar') or not self.bar.winfo_exists():
            return
        self.bar.delete('all')
        fraction = calculate(self.total, self.goal)[2]
        self.bar.create_rectangle(
            0, 0, self.bar.winfo_width() * fraction, 12,
            fill=THEMES[self.theme]['accent'], outline='',
        )

    def draw_bottle(self):
        if not hasattr(self, 'bottle') or not self.bottle.winfo_exists():
            return
        c = THEMES[self.theme]
        self.bottle.delete('all')
        x = self.bottle.winfo_width() / 2

        # Bottle neck and body
        self.bottle.create_rectangle(x - 25, 5, x + 25, 23, fill=c['accent'], outline='')
        self.bottle.create_polygon(
            x - 25, 25, x + 25, 25, x + 51, 48, x + 51, 175, x - 51, 175, x - 51, 48,
            fill=c['soft'], outline=c['line'], width=3,
        )

        # Water filling
        if self.visual_fraction > 0:
            self.bottle.create_rectangle(
                x - 47, 172 - self.visual_fraction * 120, x + 47, 172,
                fill=c['water'], outline='',
            )

        # Eyes and smiling / neutral face
        for eye in [x - 15, x + 15]:
            self.bottle.create_oval(eye - 3, 91, eye + 3, 97, fill=c['text'], outline='')

        if self.goal > 0 and (self.total / self.goal) >= 0.5:
            self.bottle.create_arc(
                x - 16, 98, x + 16, 120, start=180, extent=180,
                style='arc', outline=c['text'], width=2,
            )
        else:
            self.bottle.create_line(x - 10, 110, x + 10, 110, fill=c['text'], width=2)

    def animate_bottle(self):
        if self.bottle_timer is not None:
            self.root.after_cancel(self.bottle_timer)
            self.bottle_timer = None

        target = calculate(self.total, self.goal)[2]
        self.visual_fraction += (target - self.visual_fraction) * 0.18

        if abs(target - self.visual_fraction) < 0.003:
            self.visual_fraction = target
        else:
            self.bottle_timer = self.root.after(16, self.animate_bottle)

        self.draw_bottle()


# ---------------------------------------------------------------------------
# 7. APPLICATION ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    root = tk.Tk()
    app = WaterBuddyApp(root)
    root.mainloop()
