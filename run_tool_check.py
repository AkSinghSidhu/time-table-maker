"""Headless acceptance test: run the tool's pipeline on the converted workbook."""

import sys
import time

from engine.data_loader import load_timetable_data
from engine.validator import PreSolverValidator, IndependentValidator
from engine.cpsat_solver import TimetableCPSATSolver


def main(path="Time Table (Aug-Dec) 2026 - TOOL FORMAT.xlsx", time_limit=60):
    time_limit = float(time_limit)
    t0 = time.time()
    print(f"=== Running tool pipeline on: {path} (solver limit {time_limit}s) ===")
    data = load_timetable_data(path)

    errors = PreSolverValidator.validate(data)
    if errors:
        print("\n*** VALIDATION FAILED ***")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    solver = TimetableCPSATSolver(data)
    schedule = solver.solve(time_limit_seconds=time_limit)

    IndependentValidator.validate_schedule(schedule, data)

    # quick summary
    from collections import Counter
    per_class = Counter(e["class_id"] for e in schedule)
    per_teacher = Counter(e["teacher_id"] for e in schedule)
    print("\nPeriods scheduled per class:")
    for c, n in sorted(per_class.items()):
        print(f"  {c:6} {n:3}")
    print("Periods per teacher:")
    for t, n in sorted(per_teacher.items()):
        print(f"  {t:6} {n:3}")
    print(f"\nTotal schedule entries: {len(schedule)} "
          f"(elapsed pipeline time {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main(*sys.argv[1:])
