import pandas as pd
import os
import calendar
from engine.logger import log_step, log_info
from engine.input_utils import integer

class TimetableData:
    """Container holding all parsed input tables for the timetable generator."""

    def __init__(self, df_subjects, df_teachers, df_unavail, df_classes, df_assignments, df_rooms, df_config):
        def clean(frame):
            result = frame.astype(object).where(frame.notna(), "")
            result.columns = [str(column).strip() for column in result.columns]
            for column in result.columns:
                if column in {"subject_id", "teacher_id", "class_id", "room_id", "lab_category", "lab_room_category", "day", "type"}:
                    result[column] = result[column].astype(str).str.strip()
                if column == "type":
                    result[column] = result[column].str.lower()
                elif column == "day":
                    result[column] = result[column].str.title()
            return result
        self.subjects = clean(df_subjects)
        self.teachers = clean(df_teachers)
        self.unavailability = clean(df_unavail)
        self.classes = clean(df_classes)
        self.assignments = clean(df_assignments)
        self.rooms = clean(df_rooms)
        self.config_df = clean(df_config)

        self.parse_config()

    def parse_config(self, overrides=None):
        """Parse configuration parameters from Config sheet or defaults."""
        config_dict = {}
        if not self.config_df.empty:
            if not {"field", "value"}.issubset(self.config_df.columns):
                raise ValueError("Config sheet must contain 'field' and 'value' columns.")
            for index, row in self.config_df.iterrows():
                field = str(row["field"]).strip()
                val = str(row["value"]).strip()
                if field not in {"periods_per_day", "break_after_period", "lunch_period_index", "working_days"}:
                    raise ValueError(f"Config row {index + 2}: unknown field '{field}'.")
                if field in config_dict:
                    raise ValueError(f"Config row {index + 2}: duplicate field '{field}'.")
                config_dict[field] = val
        config_dict.update(overrides or {})
        periods = integer(config_dict.get("periods_per_day", 8), "Config periods_per_day", 1, 24)
        break_val = config_dict.get("break_after_period", config_dict.get("lunch_period_index", min(4, periods)))
        break_period = integer(break_val, "Config break_after_period", 0, periods)
        days_str = config_dict.get("working_days", "Monday, Tuesday, Wednesday, Thursday, Friday")
        names = {day.lower(): day for day in calendar.day_name}
        raw_days = [d.strip().lower() for d in str(days_str).split(",") if d.strip()]
        if not raw_days or any(day not in names for day in raw_days):
            raise ValueError("Config working_days must list full weekday names, separated by commas.")
        if len(set(raw_days)) != len(raw_days):
            raise ValueError("Config working_days contains duplicate days.")
        self.periods_per_day = periods
        self.break_after_period = break_period
        self.working_days = [names[day] for day in raw_days]


def load_timetable_data(filepath_or_excel):
    """Loads timetable datasets from an Excel file path or pd.ExcelFile."""
    owned = isinstance(filepath_or_excel, (str, os.PathLike))
    log_step("📂 Step 1: Loading Timetable Input Data", str(filepath_or_excel) if owned else "Workbook")
    xls = pd.ExcelFile(filepath_or_excel) if owned else filepath_or_excel
    try:
        required = ["Subjects", "Teachers", "Classes", "TeacherAssignment", "Rooms"]
        optional = {
            "TeacherUnavailability": ["teacher_id", "day", "period"],
            "Config": ["field", "value"],
        }
        for sheet in required:
            if sheet not in xls.sheet_names:
                raise ValueError(f"Input workbook is missing required sheet: '{sheet}'")
        tables = {}
        id_types = {name: str for name in ("subject_id", "teacher_id", "class_id", "room_id")}
        for sheet in required + list(optional):
            df = (pd.read_excel(xls, sheet_name=sheet, dtype=id_types)
                  if sheet in xls.sheet_names else pd.DataFrame(columns=optional[sheet]))
            tables[sheet] = df
        data = TimetableData(tables["Subjects"], tables["Teachers"], tables["TeacherUnavailability"],
                             tables["Classes"], tables["TeacherAssignment"], tables["Rooms"], tables["Config"])
    finally:
        if owned:
            xls.close()

    log_info(f"Loaded {len(data.subjects)} Subjects, {len(data.teachers)} Teachers, {len(data.classes)} Classes, {len(data.assignments)} Assignments, {len(data.rooms)} Rooms.")
    break_msg = f"Separate Lunch Break after Period {data.break_after_period}" if data.break_after_period else "No Lunch Break"
    log_info(f"Configuration: {data.periods_per_day} teaching lectures/day, {break_msg}, Days: {', '.join(data.working_days)}")

    return data


def generate_dummy_template(filepath):
    """Generates a complete template Excel file populated with sample university data."""
    from create_test_data import create_sample_dataset
    log_step("📥 Generating Template File", filepath)
    return create_sample_dataset(filepath)
