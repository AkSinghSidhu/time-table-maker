import pandas as pd

def create_sample_dataset(output_path="test_data.xlsx"):
    # 1. Subjects
    df_subjects = pd.DataFrame([
        {"subject_id": "SUB101", "name": "Mathematics", "priority": 1, "theory_sessions_per_week": 4, "lab_sessions_per_week": 0, "lab_room_category": None},
        {"subject_id": "SUB102", "name": "Physics", "priority": 2, "theory_sessions_per_week": 3, "lab_sessions_per_week": 1, "lab_room_category": "Physics Lab"},
        {"subject_id": "SUB103", "name": "Chemistry", "priority": 2, "theory_sessions_per_week": 3, "lab_sessions_per_week": 1, "lab_room_category": "Chemistry Lab"},
        {"subject_id": "SUB104", "name": "Computer Science", "priority": 1, "theory_sessions_per_week": 3, "lab_sessions_per_week": 1, "lab_room_category": "CS Lab"},
        {"subject_id": "SUB105", "name": "English", "priority": 3, "theory_sessions_per_week": 3, "lab_sessions_per_week": 0, "lab_room_category": None},
    ])

    # 2. Teachers
    df_teachers = pd.DataFrame([
        {"teacher_id": "T101", "name": "Dr. Smith (Math)", "max_periods_week": 20, "max_periods_day": 5},
        {"teacher_id": "T102", "name": "Prof. Johnson (Physics)", "max_periods_week": 18, "max_periods_day": 5},
        {"teacher_id": "T103", "name": "Dr. Brown (Chemistry)", "max_periods_week": 18, "max_periods_day": 5},
        {"teacher_id": "T104", "name": "Prof. Alan (CS)", "max_periods_week": 18, "max_periods_day": 5},
        {"teacher_id": "T105", "name": "Ms. Clark (English)", "max_periods_week": 18, "max_periods_day": 5},
    ])

    # 3. TeacherUnavailability
    df_unavail = pd.DataFrame([
        {"teacher_id": "T101", "day": "Friday", "period": 7},
        {"teacher_id": "T102", "day": "Monday", "period": 1},
    ])

    # 4. Classes
    df_classes = pd.DataFrame([
        {"class_id": "SEC_A", "name": "Section 10A", "strength": 40},
        {"class_id": "SEC_B", "name": "Section 10B", "strength": 40},
    ])

    # 5. TeacherAssignment
    df_assignments = pd.DataFrame([
        # SEC_A
        {"class_id": "SEC_A", "subject_id": "SUB101", "teacher_id": "T101"},
        {"class_id": "SEC_A", "subject_id": "SUB102", "teacher_id": "T102"},
        {"class_id": "SEC_A", "subject_id": "SUB103", "teacher_id": "T103"},
        {"class_id": "SEC_A", "subject_id": "SUB104", "teacher_id": "T104"},
        {"class_id": "SEC_A", "subject_id": "SUB105", "teacher_id": "T105"},
        # SEC_B
        {"class_id": "SEC_B", "subject_id": "SUB101", "teacher_id": "T101"},
        {"class_id": "SEC_B", "subject_id": "SUB102", "teacher_id": "T102"},
        {"class_id": "SEC_B", "subject_id": "SUB103", "teacher_id": "T103"},
        {"class_id": "SEC_B", "subject_id": "SUB104", "teacher_id": "T104"},
        {"class_id": "SEC_B", "subject_id": "SUB105", "teacher_id": "T105"},
    ])

    # 6. Rooms
    df_rooms = pd.DataFrame([
        {"room_id": "R_PHY", "type": "lab", "lab_category": "Physics Lab", "capacity": 45},
        {"room_id": "R_CHEM", "type": "lab", "lab_category": "Chemistry Lab", "capacity": 45},
        {"room_id": "R_CS", "type": "lab", "lab_category": "CS Lab", "capacity": 45},
    ])

    # 7. Config
    df_config = pd.DataFrame([
        {"field": "periods_per_day", "value": "8"},
        {"field": "break_after_period", "value": "4"},
        {"field": "working_days", "value": "Monday, Tuesday, Wednesday, Thursday, Friday"},
    ])

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_subjects.to_excel(writer, sheet_name="Subjects", index=False)
        df_teachers.to_excel(writer, sheet_name="Teachers", index=False)
        df_unavail.to_excel(writer, sheet_name="TeacherUnavailability", index=False)
        df_classes.to_excel(writer, sheet_name="Classes", index=False)
        df_assignments.to_excel(writer, sheet_name="TeacherAssignment", index=False)
        df_rooms.to_excel(writer, sheet_name="Rooms", index=False)
        df_config.to_excel(writer, sheet_name="Config", index=False)

    print(f"Sample dataset saved to {output_path}")
    return output_path

if __name__ == "__main__":
    create_sample_dataset()
