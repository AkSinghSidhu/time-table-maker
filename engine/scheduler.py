import tempfile
import os
import pandas as pd

from engine.data_loader import load_timetable_data, generate_dummy_template, TimetableData
from engine.validator import PreSolverValidator, IndependentValidator
from engine.cpsat_solver import TimetableCPSATSolver
from engine.exporter import TimetableExporter

class SchedulerError(Exception):
    pass

class TimetableScheduler:
    """Main facade for the University Timetable Generator using CP-SAT."""

    def __init__(self, data_or_filepath):
        if isinstance(data_or_filepath, TimetableData):
            self.data = data_or_filepath
        else:
            self.data = load_timetable_data(data_or_filepath)

    def solve(self, time_limit_seconds=30):
        # 1. Pre-solver Validation
        errors = PreSolverValidator.validate(self.data)
        if errors:
            raise SchedulerError("Pre-solver Validation Failed:\n" + "\n".join(f"• {e}" for e in errors))

        # 2. Run CP-SAT Solver
        try:
            solver = TimetableCPSATSolver(self.data)
            master_schedule = solver.solve(time_limit_seconds=time_limit_seconds)
        except Exception as e:
            raise SchedulerError(f"Solver Failure: {str(e)}")

        # 3. Post-solver Independent Validation
        violations = IndependentValidator.validate_schedule(master_schedule, self.data)
        if violations:
            raise SchedulerError("Post-solver Constraint Violations Detected:\n" + "\n".join(f"• {v}" for v in violations))

        # 4. Generate Projections
        class_grids, teacher_grids = TimetableExporter.generate_projections(master_schedule, self.data)
        return master_schedule, class_grids, teacher_grids

    def export_excel(self, class_grids, teacher_grids, output_path):
        return TimetableExporter.export_excel(class_grids, teacher_grids, output_path)
