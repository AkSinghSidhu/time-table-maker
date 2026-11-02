import pandas as pd
import os
from engine.logger import log_step, log_info

class TimetableData:
    """Container holding all parsed input tables for the timetable generator."""

    def __init__(self, df_subjects, df_teachers, df_unavail, df_classes, df_assignments, df_rooms, df_config):
        self.subjects = df_subjects.fillna("")
        self.teachers = df_teachers.fillna("")
        self.unavailability = df_unavail.fillna("")
        self.classes = df_classes.fillna("")
        self.assignments = df_assignments.fillna("")
        self.rooms = df_rooms.fillna("")
        self.config_df = df_config.fillna("")

        self.parse_config()

    def parse_config(self):
        """Parse configuration parameters from Config sheet or defaults."""
        config_dict = {}
        if not self.config_df.empty and "field" in self.config_df.columns and "value" in self.config_df.columns:
            for _, row in self.config_df.iterrows():
                field = str(row["field"]).strip()
                val = str(row["value"]).strip()
                config_dict[field] = val

        self.periods_per_day = int(config_dict.get("periods_per_day", 8))
        break_val = config_dict.get("break_after_period", config_dict.get("lunch_period_index", "4"))
        self.break_after_period = int(break_val) if str(break_val).strip() and str(break_val).strip() != "0" else 0

        days_str = config_dict.get("working_days", "Monday, Tuesday, Wednesday, Thursday, Friday")
        self.working_days = [d.strip() for d in days_str.split(",") if d.strip()]


def load_timetable_data(filepath_or_excel):
    """Loads timetable datasets from an Excel file path or pd.ExcelFile."""
    if isinstance(filepath_or_excel, str):
        log_step("📂 Step 1: Loading Timetable Input Data", filepath_or_excel)
        xls = pd.ExcelFile(filepath_or_excel)
    else:
        log_step("📂 Step 1: Parsing Timetable Input Workbook")
        xls = filepath_or_excel

    sheet_names = xls.sheet_names

    required_sheets = ["Subjects", "Teachers", "Classes", "TeacherAssignment", "Rooms"]
    for req in required_sheets:
        if req not in sheet_names:
            raise ValueError(f"Input workbook is missing required sheet: '{req}'")

    df_subjects = pd.read_excel(xls, sheet_name="Subjects")
    df_teachers = pd.read_excel(xls, sheet_name="Teachers")
    df_unavail = pd.read_excel(xls, sheet_name="TeacherUnavailability") if "TeacherUnavailability" in sheet_names else pd.DataFrame(columns=["teacher_id", "day", "period"])
    df_classes = pd.read_excel(xls, sheet_name="Classes")
    df_assignments = pd.read_excel(xls, sheet_name="TeacherAssignment")
    df_rooms = pd.read_excel(xls, sheet_name="Rooms")
    df_config = pd.read_excel(xls, sheet_name="Config") if "Config" in sheet_names else pd.DataFrame(columns=["field", "value"])

    data = TimetableData(df_subjects, df_teachers, df_unavail, df_classes, df_assignments, df_rooms, df_config)

    log_info(f"Loaded {len(data.subjects)} Subjects, {len(data.teachers)} Teachers, {len(data.classes)} Classes, {len(data.assignments)} Assignments, {len(data.rooms)} Rooms.")
    break_msg = f"Separate Lunch Break after Period {data.break_after_period}" if data.break_after_period else "No Lunch Break"
    log_info(f"Configuration: {data.periods_per_day} teaching lectures/day, {break_msg}, Days: {', '.join(data.working_days)}")

    return data


def generate_dummy_template(filepath):
    """Generates a complete template Excel file populated with sample university data."""
    from create_test_data import create_sample_dataset
    log_step("📥 Generating Template File", filepath)
    return create_sample_dataset(filepath)
