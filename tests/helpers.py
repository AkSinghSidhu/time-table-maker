import pandas as pd

from engine.data_loader import TimetableData


def fixture():
    data = TimetableData(
        pd.DataFrame([
            dict(subject_id="S1", name="Mathematics", priority=1, theory_sessions_per_week=1, lab_sessions_per_week=0, lab_room_category=""),
            dict(subject_id="S2", name="Physics", priority=2, theory_sessions_per_week=0, lab_sessions_per_week=1, lab_room_category="Physics"),
        ], dtype=object),
        pd.DataFrame([
            dict(teacher_id="T1", name="Teacher One", max_periods_week=8, max_periods_day=4),
            dict(teacher_id="T2", name="Teacher Two", max_periods_week=8, max_periods_day=4),
        ], dtype=object),
        pd.DataFrame(columns=["teacher_id", "day", "period"]),
        pd.DataFrame([dict(class_id="C1", name="Class One", strength=20), dict(class_id="C2", name="Class Two", strength=20)]),
        pd.DataFrame([
            dict(class_id="C1", subject_id="S1", teacher_id="T1"),
            dict(class_id="C1", subject_id="S2", teacher_id="T2"),
            dict(class_id="C2", subject_id="S1", teacher_id="T2"),
        ]),
        pd.DataFrame([
            dict(room_id="L1", type="lab", lab_category="Physics", capacity=30),
            dict(room_id="SMALL", type="lab", lab_category="Physics", capacity=5),
        ]),
        pd.DataFrame([dict(field="working_days", value="Monday, Tuesday"),
                      dict(field="periods_per_day", value="6"), dict(field="break_after_period", value="3")]),
    )
    schedule = [
        dict(session_id=1, class_id="C1", subject_id="S1", teacher_id="T1", room_id=None, day="Monday", period=1, type="theory"),
        dict(session_id=2, class_id="C1", subject_id="S2", teacher_id="T2", room_id="L1", day="Monday", period=4, type="lab"),
        dict(session_id=2, class_id="C1", subject_id="S2", teacher_id="T2", room_id="L1", day="Monday", period=5, type="lab"),
        dict(session_id=3, class_id="C2", subject_id="S1", teacher_id="T2", room_id=None, day="Monday", period=1, type="theory"),
    ]
    return data, schedule


def write_workbook(data, path):
    sheets = {"Subjects": data.subjects, "Teachers": data.teachers, "Classes": data.classes,
              "TeacherAssignment": data.assignments, "Rooms": data.rooms,
              "TeacherUnavailability": data.unavailability, "Config": data.config_df}
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
