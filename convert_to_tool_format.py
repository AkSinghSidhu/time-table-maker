"""
Convert the hand-made 'Time Table (Aug-Dec) 2026(2).xlsx' workbook into the
structured input format required by the Time Table Maker tool.

Input workbook layout (surveyed):
  - "Final Load" / "Copy of Final Load"  : teacher -> (Branch, Sem, Sec, Subject,
        Theory, Pratical, Credit, Hours, TOTAL)  -> authoritative teaching load.
  - "class wise" / "Copy of class wise"  : per-section weekly grids
        (days x 8 periods, with a 9:00-9:10 slot in col B, Lunch in col H),
        used to (a) enumerate the sections and (b) add department courses that
        are NOT in "Final Load" (B.Tech-1 & B.Tech-3 extras).
  - "Facultywise" / "Lab Wise" / "Mdc Vac" / "Computer Science" : teacher/lab
        views and other-department grids (not needed for conversion).

Conversion rules (documented in the ConversionNotes sheet):
  * "Final Load" is authoritative for subject/teacher/class assignments and
    per-week session counts (Theory -> theory sessions, Pratical -> lab blocks
    of 2 periods; Hours = Theory + 2*Pratical confirms the mapping).
  * Sections with no Sec letter on a BCA-something row apply to BOTH sections.
  * Special combined rows are remapped:
      CAPSTONE ("5 AND 7")           -> 1 lab for B.Tech 5 and B.Tech 7 each
      Training & Placement ("7,5,MCA")-> 1 theory session for BCA-5 A and B each
      UGC Net Coaching ("1+3")       -> 2 theory sessions for MCA-I and MCA-III
                                        each (10 sessions are joint in the real
                                        file; tools cannot model joint slots)
  * Grid-only department courses added from the "class wise" grids:
      Engineering Mathematics (JPS), Engineering Chemistry (Dr. Ajay Khajuria),
      English Reading and Writing (Dr. Kuldeep Singh), PYTHON B.Tech-3 (NM).
  * Excluded (other department / non-faculty-run / study slots):
      MDC, AECC English, EMC-Online, Minor (Mgmt) courses, Foundation of
      Computer Science, DBMS-MINOR / R Programming (other-dept minors),
      Office Automation labs & LA practice sessions, Typing/Practice/Remedial
      sessions, Library, NCC*, SIMRAN (9:00-9:10 slot), Lunch, Project work.
"""

import re
import shutil
from pathlib import Path

import openpyxl
import pandas as pd

SRC = Path("Time Table (Aug-Dec) 2026(2).xlsx")
COPY = Path("Time Table (Aug-Dec) 2026 (original copy).xlsx")
OUT = Path("Time Table (Aug-Dec) 2026 - TOOL FORMAT.xlsx")

CLASS_WISE_SHEETS = ["class wise", "Copy of class wise"]
LOAD_SHEET = "Final Load"

# ---------------------------------------------------------------- classes ---
CLASSES = {
    "BCA1A": "BCA 1st Sem Section A (AB301)",
    "BCA1B": "BCA 1st Sem Section B (AB301)",
    "BCA3A": "BCA 3rd Sem Section A (H301)",
    "BCA3B": "BCA 3rd Sem Section B (H303)",
    "BCA5A": "BCA 5th Sem Section A (G405)",
    "BCA5B": "BCA 5th Sem Section B (B201)",
    "BT1":   "B.Tech 1st Sem (B303)",
    "BT3":   "B.Tech 3rd Sem (G402)",
    "BT5":   "B.Tech 5th Sem (G403)",
    "BT7":   "B.Tech 7th Sem (G404)",
    "MCA1":  "MCA Sem I (F405)",
    "MCA3":  "MCA Sem III (B304)",
}

# ---------------------------------------------------------------- teachers ---
# teacher_key (lowercased, simplified) -> (teacher_id, display name, initials)
TEACHERS = {
    "dr. upinder kaur":   ("T_UK",  "Dr. Upinder Kaur",        "UK"),
    "dr. harpal singh":   ("T_HS",  "Dr. Harpal Singh",        "HS"),
    "malik":              ("T_MM",  "Malik Muzamil",           "MM"),
    "ms. sukhdeep kaur":  ("T_SK",  "Sukhdeep Kaur",           "SK"),
    "ms. nancy":          ("T_NM",  "Nancy Mittal",            "NM"),
    "mr. sahezpreet singh":("T_SPS","Sahezpreet Singh",        "SPS"),
    "jyotishana":         ("T_JG",  "JyotiShana Goyal",        "JG"),
    "makinder":           ("T_MK",  "Makinder Kaur",           "MK"),
    "aijaz":              ("T_AA",  "Aijaz Ahmad",             "AA"),
    "kauser":             ("T_KA",  "Kounser Ali",             "KA"),
    "rashid":             ("T_RR",  "Rashid Rafiq Shah",       "RR"),
    "malik haider":       ("T_MH",  "Malik Haider Ali",        "MH"),
    "annu":               ("T_AM",  "Annu",                    "AM"),
    "dr. neha soni":      ("T_NS",  "Dr. Neha Soni",           "NS"),
    "dr. manpreet kaur":  ("T_MPK", "Dr. Manpreet Kaur",       "MPK"),
    # grid-only teachers (never in "Final Load")
    "dr. ankur":          ("T_AK",  "Ankita Krishnia",         "AK"),  # placeholder, overridden below
}
TEACHERS.pop("dr. ankur", None)
TEACHERS["ankita krishnia"] = ("T_AK", "Ankita Krishnia", "AK")
# initials -> teacher key fallbacks
INITIALS_TO_ID = {
    "UK": "T_UK", "HS": "T_HS", "MM": "T_MM", "MHA": "T_MM",
    "SK": "T_SK", "NM": "T_NM", "SPS": "T_SPS", "JG": "T_JG",
    "MK": "T_MK", "AA": "T_AA", "KA": "T_KA", "RR": "T_RR", "RRS": "T_RR",
    "MH": "T_MH", "AM": "T_AM", "NS": "T_NS", "MPK": "T_MPK", "AK": "T_AK",
    # grid-extra teachers (B.Tech 1st sem + B.Tech 3rd sem)
    "JPS": "T_JPS", "AKJ": "T_AKJ", "KS": "T_KS",
}
EXTRA_TEACHERS = {
    "T_JPS": "Dr. Jaskirat Pal Singh",
    "T_AKJ": "Dr. Ajay Khajuria",
    "T_KS":  "Dr. Kuldeep Singh",
}

# ------------------------------------------------------- naming fixes ------
SUBJECT_NAME_FIX = {
    "Programming In C": "Programming in C",
    "Daa": "DAA", "Cn": "CN", "Os": "OS", "Iot": "IoT", "Ai": "AI",
    "Nlp": "NLP", "Rag": "RAG", "Mad": "MAD", "Dbms": "DBMS",
    "Ugc Net Coaching": "UGC Net Coaching",
    "Big Data Analytics": "Big Data Analytics",
    "Mongo Db": "MongoDB", "Power Bi": "POWER BI",
    "Advanced Web Using Php": "Advanced Web Using PHP",
    "Fundamentals Of Web": "Fundamentals of Web",
    "Theory Of Computation": "Theory of Computation",
    "Introduction To Blockchain": "Introduction to Blockchain",
    "Training And Placement": "Training and Placement",
}


def pretty_subject(title_text: str) -> str:
    s = re.sub(r"\s+", " ", title_text).strip()
    return SUBJECT_NAME_FIX.get(s, s)


def build_output():
    wb = openpyxl.load_workbook(SRC, data_only=True)

    # ------------------------------------------------------------ copy ------
    if COPY.exists():
        COPY.unlink()
    shutil.copyfile(SRC, COPY)
    print(f"[copy] Original saved as: {COPY}")

    # ---------------------------------------- 1. authoritative Final Load ---
    ws = wb[LOAD_SHEET]
    rows = []
    teacher = None
    loads = {}
    for r in range(2, ws.max_row + 1):
        a = ws.cell(row=r, column=1).value
        if isinstance(a, str) and a.strip():
            teacher = a.strip()
        branch = ws.cell(row=r, column=2).value
        sem = ws.cell(row=r, column=3).value
        sec = ws.cell(row=r, column=4).value
        subject = ws.cell(row=r, column=5).value
        th = ws.cell(row=r, column=6).value
        pra = ws.cell(row=r, column=7).value
        total = ws.cell(row=r, column=10).value
        # capture the stated weekly TOTAL even on name-only summary rows
        if total not in (None, "") and teacher is not None:
            try:
                cur_key = " ".join(str(teacher).split()).lower().rstrip(".")
                if cur_key in TEACHERS:
                    loads.setdefault(TEACHERS[cur_key][2], []).append(round(float(total)))
            except (TypeError, ValueError):
                pass
        if not isinstance(subject, str) or not subject.strip():
            continue
        subject = subject.strip()
        assignments = []          # list of (class_id, th, pra)
        if "capstone" in subject.lower():
            subject = "Capstone Project"
            assignments = [("BT5", 0, 1), ("BT7", 0, 1)]
        elif "training and placement" in (branch or "").lower() and "malik" in (teacher or "").lower():
            subject = "Training and Placement"
            assignments = [("BCA5A", 1, 0), ("BCA5B", 1, 0)]
        elif "ugc" in subject.lower():
            assignments = [("MCA1", 2, 0), ("MCA3", 2, 0)]
        else:
            br = str(branch or "").strip().lower().replace(".", "")
            if br in ("btech", "b tech"):
                cl = f"BT{int(float(sem))}"
                assignments = [(cl, th, pra)]
            elif br == "bca":
                s1 = int(float(sem))
                s = str(sec or "").strip().upper()
                cls = {1: "BCA1", 3: "BCA3", 5: "BCA5"}.get(s1)
                if cls:
                    assignments = (
                        [(f"{cls}A", th, pra), (f"{cls}B", th, pra)] if not s else
                        [(f"{cls}{s}", th, pra)])
            elif br == "mca":
                cl = f"MCA{int(float(sem))}"
                assignments = [(cl, th, pra)]
            else:
                continue          # 'other department' / unknown -> skipped
        if teacher is None:
            continue
        tkey = " ".join(str(teacher).split()).lower().rstrip(".")
        tid = TEACHERS.get(tkey, (None,))[0]
        if tid is None:
            print(f"[warn] unknown teacher '{teacher}' on row {r} ({subject}) -> skipped")
            continue
        for cls, th_n, pra_n in assignments:
            rows.append({"class_id": cls, "subject": pretty_subject(subject.title()),
                         "theory": int(th_n or 0), "lab": int(pra_n or 0),
                         "teacher_id": tid})

    load_df = pd.DataFrame(rows)
    print(f"[final-load] parsed {len(load_df)} class-subject assignments")

    # ------------------------------------ 2. grid corrections & extras ---------
    # a) the grids show 'Digital Electronics' for BCA-1B too (Final Load lists it
    #    only as section A) -> added for BCA-1B from the grid evidence
    # b) harvested from 'class wise' grids; counts derived from the grids.
    extras = pd.DataFrame([
        {"class_id": "BCA1B", "subject": "Digital Electronics",    "theory": 4, "lab": 0, "teacher_id": "T_JG"},
        {"class_id": "BT1",   "subject": "Engineering Mathematics","theory": 5, "lab": 0, "teacher_id": "T_JPS"},
        {"class_id": "BT1",   "subject": "Engineering Chemistry",  "theory": 4, "lab": 1, "teacher_id": "T_AKJ"},
        {"class_id": "BT1",   "subject": "English Reading and Writing", "theory": 4, "lab": 0, "teacher_id": "T_KS"},
        {"class_id": "BT3",   "subject": "Python",                 "theory": 3, "lab": 1, "teacher_id": "T_NM"},
    ])
    load_df = pd.concat([load_df, extras], ignore_index=True)

    # dedupe (same class+subject+teacher appearing twice)
    load_df = load_df.groupby(["class_id", "subject", "teacher_id"], as_index=False).agg(
        {"theory": "max", "lab": "max"})

    # ------------------------------------------------ 3. build the sheets ---
    subj_specs = []       # (subject_id, name, priority, th, lab, cat)
    assignments = []      # rows
    subject_ids = {}
    for _, r in load_df.iterrows():
        class_id, base, tid = r["class_id"], r["subject"], r["teacher_id"]
        if class_id not in CLASSES:
            print(f"[warn] unknown class '{class_id}' for '{base}' -> skipped")
            continue
        slug = re.sub(r"[^A-Z0-9]", "", base.upper())[:12] or "SUBJ"
        short = {"BCA1A": "BCA-1A", "BCA1B": "BCA-1B", "BCA3A": "BCA-3A", "BCA3B": "BCA-3B",
                 "BCA5A": "BCA-5A", "BCA5B": "BCA-5B", "BT1": "B.Tech-1", "BT3": "B.Tech-3",
                 "BT5": "B.Tech-5", "BT7": "B.Tech-7", "MCA1": "MCA-I", "MCA3": "MCA-III"}[class_id]
        sid = f"{slug}-{class_id}"
        if sid in subject_ids:
            existing = subject_ids[sid]
            if existing[3] != (r["theory"], r["lab"], tid):
                print(f"[warn] conflicting spec for {sid}: {existing[3]} vs "
                      f"{(r['theory'], r['lab'], tid)}")
            continue
        lab = int(r["lab"] or 0)
        th = int(r["theory"] or 0)
        cat = "CS Lab" if lab > 0 else ""
        subj_specs.append((sid, f"{base} ({short})", 2, th, lab, cat))
        subject_ids[sid] = (base, short, tid, (th, lab))
        assignments.append({"class_id": class_id, "subject_id": sid, "teacher_id": tid})

    # teacher loads -> caps
    assigned = {}
    for a in assignments:
        th, lab = next(((s[3], s[4]) for s in subj_specs if s[0] == a["subject_id"]), (0, 0))
        assigned[a["teacher_id"]] = assigned.get(a["teacher_id"], 0) + th + 2 * lab

    teachers = {}
    for tid, name in EXTRA_TEACHERS.items():
        teachers[tid] = name
    for (tid, name, ini) in TEACHERS.values():
        teachers[tid] = name
    INITIAL_OF = {}
    for (tid, name, ini) in TEACHERS.values():
        INITIAL_OF[tid] = ini
    INITIAL_OF.update({"T_JPS": "JPS", "T_AKJ": "AKJ", "T_KS": "KS"})
    teacher_rows = []
    for tid, name in sorted(teachers.items()):
        stated_vals = loads.get(INITIAL_OF[tid], [])
        stated = max(stated_vals) if stated_vals else 0
        calc = assigned.get(tid, 0)
        max_week = int(max(stated, calc, 1))
        teacher_rows.append({"teacher_id": tid, "name": name,
                             "max_periods_week": max_week, "max_periods_day": 5})

    subj_ids = {s[0] for s in subj_specs}
    assignments = [a for a in assignments if a["subject_id"] in subj_ids]

    df_subjects = pd.DataFrame([{
        "subject_id": s[0], "name": s[1], "priority": s[2],
        "theory_sessions_per_week": s[3], "lab_sessions_per_week": s[4],
        "lab_room_category": s[5]} for s in subj_specs])
    df_teachers = pd.DataFrame(teacher_rows)
    df_unavail = pd.DataFrame(columns=["teacher_id", "day", "period"])
    df_classes = pd.DataFrame([{"class_id": k, "name": v, "strength": 40}
                               for k, v in CLASSES.items()])
    df_assign = pd.DataFrame(assignments).drop_duplicates()
    df_teachers = df_teachers.sort_values("teacher_id").reset_index(drop=True)
    df_assign = df_assign.sort_values(["class_id", "subject_id"]).reset_index(drop=True)

    labs = ["D-301", "D-302", "C-302", "C-303", "C-304", "E-302"]
    classrooms = ["AB301", "H301", "H303", "G405", "B201", "B303",
                  "G402", "G403", "G404", "F405", "B304"]
    df_rooms = pd.DataFrame(
        [{"room_id": r, "type": "lab", "lab_category": "CS Lab", "capacity": 40} for r in labs] +
        [{"room_id": r, "type": "classroom", "lab_category": "", "capacity": 40}
         for r in classrooms])

    df_config = pd.DataFrame([
        {"field": "periods_per_day", "value": "8"},
        {"field": "break_after_period", "value": "5"},
        {"field": "working_days", "value": "Monday, Tuesday, Wednesday, Thursday, Friday"},
    ])

    notes = pd.DataFrame({"ConversionNotes": [
        "Source workbook: Time Table (Aug-Dec) 2026(2).xlsx (original copied as "
        "'Time Table (Aug-Dec) 2026 (original copy).xlsx').",
        "Authoritative data source: 'Final Load' sheet (teacher -> Branch/Sem/Sec/Subject "
        "+ Theory/Practical per-week counts). Theory -> theory sessions/week, "
        "Pratical -> lab blocks/week (each lab = 2 periods, Hours = Theory + 2 x Pratical).",
        "Classes: all 12 sections found in the 'class wise' / 'Copy of class wise' grids "
        "(BCA 1A/1B/3A/3B/5A/5B, B.Tech 1/3/5/7, MCA I & III). Teacher strength not stated "
        "anywhere in the file; defaulted to 40 (edit if known).",
        "Special rows from 'Final Load' remapped: CAPSTONE PROJECT (B.Tech 5 AND 7) -> one "
        "lab each for B.Tech 5 and 7; Training & Placement (combined 7,5,MCA) -> one theory "
        "session each for BCA-5 A and B; UGC Net Coaching (MCA 1+3 combined, plus BCA-5 "
        "sections in the real grids) -> 2 theory sessions each for MCA-I and MCA-III "
        "(joint/combined classes cannot be represented by the tool).",
        "Grid-only department courses added from 'class wise': Engineering Mathematics "
        "(Dr. Jaskirat Pal Singh), Engineering Chemistry (Dr. Ajay Khajuria), English Reading "
        "and Writing (Dr. Kuldeep Singh) for B.Tech 1; PYTHON for B.Tech 3 (Nancy Mittal). "
        "'Digital Electronics' was also added for BCA-1B (the grid schedules it there, but "
        "'Final Load' lists it only for BCA-1A).",
        "Excluded on purpose (other departments / non-faculty-run / study slots): MDC, AECC "
        "English (B-I & II), EMC- Marketing Basics (online), Minor (Management) courses, "
        "Foundation of Computer Science, DBMS(MINOR)/R Programming (Rajwinder Kaur, other "
        "dept), Office Automation labs and Lab-Assistant practice sessions, Typing practice, "
        "Remedial sessions, C-Programming Practice, Project work, Library, NCC*, SIMRAN "
        "(9:00-9:10), Lunch.",
        "Config: 8 teaching periods/day (I-VIII), lunch break after period 5 "
        "(12:20-1:10 period V ends, 1:10-1:50 is lunch), Monday-Friday.",
        "Rooms: the 6 real computer labs (D-301, D-302, C-302, C-303, C-304, E-302) all "
        "labeled lab category 'CS Lab' (subjects do not name individual lab categories), "
        "plus the section classrooms kept for reference.",
        "Teacher max_periods_week = max(weekly TOTAL in 'Final Load', computed assigned "
        "load); max_periods_day = 5.",
    ]})

    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        df_subjects.to_excel(writer, sheet_name="Subjects", index=False)
        df_teachers.to_excel(writer, sheet_name="Teachers", index=False)
        df_unavail.to_excel(writer, sheet_name="TeacherUnavailability", index=False)
        df_classes.to_excel(writer, sheet_name="Classes", index=False)
        df_assign.to_excel(writer, sheet_name="TeacherAssignment", index=False)
        df_rooms.to_excel(writer, sheet_name="Rooms", index=False)
        df_config.to_excel(writer, sheet_name="Config", index=False)
        notes.to_excel(writer, sheet_name="ConversionNotes", index=False)

    print(f"[out ] Converted workbook written to: {OUT}")
    print(f"       Subjects={len(df_subjects)}  Teachers={len(df_teachers)}  "
          f"Classes={len(df_classes)}  Assignments={len(df_assign)}  Rooms={len(df_rooms)}")
    return df_subjects, df_teachers, df_unavail, df_classes, df_assign, df_rooms, df_config


if __name__ == "__main__":
    build_output()
