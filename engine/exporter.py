import pandas as pd
from engine.logger import log_step, log_info, log_success

class TimetableExporter:
    """Generates Class views, Teacher views, and exports formatted Excel workbooks."""

    @staticmethod
    def generate_projections(master_schedule, data):
        days = data.working_days
        periods_per_day = data.periods_per_day
        break_after_period = getattr(data, "break_after_period", 0)

        # Build column list: Period 1..N with separate BREAK column inserted after break_after_period
        periods_cols = []
        for p in range(1, periods_per_day + 1):
            periods_cols.append(f"Period {p}")
            if break_after_period > 0 and p == break_after_period:
                periods_cols.append("BREAK")

        subj_name = {str(row["subject_id"]): str(row["name"]) for _, row in data.subjects.iterrows()}
        teacher_name = {str(row["teacher_id"]): str(row["name"]) for _, row in data.teachers.iterrows()}
        class_name = {str(row["class_id"]): str(row["name"]) for _, row in data.classes.iterrows()}

        class_ids = list(data.classes["class_id"].astype(str).unique())
        teacher_ids = list(data.teachers["teacher_id"].astype(str).unique())

        log_step("📊 Step 6: Generating Schedule Projections", f"Class Views: {len(class_ids)}, Teacher Views: {len(teacher_ids)}")

        class_grids = {}
        teacher_grids = {}

        for c_id in class_ids:
            df = pd.DataFrame(index=days, columns=periods_cols)
            df.fillna("Free", inplace=True)
            if "BREAK" in df.columns:
                df["BREAK"] = "LUNCH BREAK"
            class_grids[c_id] = df

        for t_id in teacher_ids:
            df = pd.DataFrame(index=days, columns=periods_cols)
            df.fillna("Free", inplace=True)
            if "BREAK" in df.columns:
                df["BREAK"] = "LUNCH BREAK"
            teacher_grids[t_id] = df

        for entry in master_schedule:
            c_id = entry["class_id"]
            s_id = entry["subject_id"]
            t_id = entry["teacher_id"]
            r_id = entry.get("room_id")
            day = entry["day"]
            p = entry["period"]
            stype = entry["type"]

            p_col = f"Period {p}"
            s_display = subj_name.get(s_id, s_id)
            t_display = teacher_name.get(t_id, t_id)
            c_display = class_name.get(c_id, c_id)

            lab_tag = " [LAB]" if stype == "lab" else ""
            room_tag = f" ({r_id})" if r_id and str(r_id) != "None" else ""

            cell_class = f"{s_display} ({t_display}){lab_tag}{room_tag}"
            if c_id in class_grids and day in class_grids[c_id].index and p_col in class_grids[c_id].columns:
                class_grids[c_id].at[day, p_col] = cell_class

            cell_teacher = f"{c_display} - {s_display}{lab_tag}"
            if t_id in teacher_grids and day in teacher_grids[t_id].index and p_col in teacher_grids[t_id].columns:
                teacher_grids[t_id].at[day, p_col] = cell_teacher

        log_info(f"Generated grids for Class Sections: {', '.join(class_ids)}")
        log_info(f"Generated grids for Teachers: {', '.join(teacher_ids)}")

        return class_grids, teacher_grids

    @staticmethod
    def export_excel(class_grids, teacher_grids, output_path):
        log_step("💾 Step 7: Exporting Schedule to Excel Workbook", output_path)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for c_id, df in class_grids.items():
                sheet_name = f"Class_{c_id}"[:31]
                df.to_excel(writer, sheet_name=sheet_name)

            for t_id, df in teacher_grids.items():
                sheet_name = f"Tr_{t_id}"[:31]
                df.to_excel(writer, sheet_name=sheet_name)

        log_success(f"Workbook successfully exported to {output_path}")
        return output_path
