from datetime import date, timedelta
from typing import Tuple, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from app.models.models import (
    AttendanceAnomaly, AttendanceRecord, AttendanceBreak, Employee,
    Shift, EmployeeShiftAssignment
)
from .recommendation_schemas import AttendanceComparison, HistoricalContext

class AnomalyAnalyzer:
    """
    Executes deep historical feature extraction and scheduled vs actual variance analysis.
    Grounds all metrics in actual PostgreSQL/SQLite attendance records.
    Never invents baseline values or reasons.
    """

    @classmethod
    async def analyze_anomaly(
        cls,
        db: AsyncSession,
        anomaly: AttendanceAnomaly
    ) -> Tuple[AttendanceComparison, HistoricalContext]:
        # 1. Fetch related attendance record
        att_record: Optional[AttendanceRecord] = None
        if anomaly.attendance_record_id:
            stmt = select(AttendanceRecord).where(AttendanceRecord.id == anomaly.attendance_record_id)
            att_record = (await db.execute(stmt)).scalars().first()

        # If not linked directly by ID, locate by employee_id + date
        if not att_record:
            stmt = select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.employee_id == anomaly.employee_id,
                    AttendanceRecord.date == anomaly.date
                )
            )
            att_record = (await db.execute(stmt)).scalars().first()

        # 2. Fetch assigned shift information
        shift: Optional[Shift] = None
        shift_assign_stmt = (
            select(Shift)
            .join(EmployeeShiftAssignment, EmployeeShiftAssignment.shift_id == Shift.id)
            .where(
                and_(
                    EmployeeShiftAssignment.employee_id == anomaly.employee_id,
                    EmployeeShiftAssignment.effective_from <= anomaly.date
                )
            )
            .order_by(desc(EmployeeShiftAssignment.effective_from))
        )
        shift = (await db.execute(shift_assign_stmt)).scalars().first()

        # If no explicit assignment, default to General Shift (8h required, 15m grace)
        shift_name = shift.name if shift else "Standard General Shift"
        shift_code = shift.code if shift else "GEN"
        shift_req_hours = shift.required_hours if shift else 8.0
        grace_period = shift.grace_period_minutes if shift else 15
        expected_worked_minutes = int(shift_req_hours * 60)

        # 3. Fetch breaks for current record
        breaks: List[AttendanceBreak] = []
        if att_record:
            break_stmt = select(AttendanceBreak).where(AttendanceBreak.attendance_record_id == att_record.id)
            breaks = (await db.execute(break_stmt)).scalars().all()
        actual_break_minutes = sum(b.duration_minutes for b in breaks) if breaks else 0

        # 4. Actual attendance values
        actual_worked_minutes = att_record.worked_minutes if att_record else 0
        actual_overtime_minutes = att_record.overtime_minutes if att_record else 0
        actual_late_minutes = att_record.late_minutes if att_record else 0

        clock_in_str = att_record.clock_in.strftime("%H:%M") if (att_record and att_record.clock_in) else None
        clock_out_str = att_record.clock_out.strftime("%H:%M") if (att_record and att_record.clock_out) else None
        sched_start_str = shift.start_time.strftime("%H:%M") if (shift and shift.start_time) else "09:00"
        sched_end_str = shift.end_time.strftime("%H:%M") if (shift and shift.end_time) else "17:30"

        # 5. Build Variance Summary
        variances = []
        if actual_worked_minutes and actual_worked_minutes != expected_worked_minutes:
            diff = actual_worked_minutes - expected_worked_minutes
            sign = "+" if diff > 0 else ""
            variances.append(f"Worked duration {actual_worked_minutes}m ({sign}{diff}m vs scheduled {expected_worked_minutes}m)")
        if actual_overtime_minutes and actual_overtime_minutes > 0:
            variances.append(f"Overtime {actual_overtime_minutes}m exceeding zero baseline")
        if actual_late_minutes and actual_late_minutes > 0:
            variances.append(f"Late clock-in by {actual_late_minutes}m past {grace_period}m grace period")
        if actual_break_minutes and actual_break_minutes > 60:
            variances.append(f"Break duration {actual_break_minutes}m vs 60m typical allowance")
        if clock_in_str and not clock_out_str:
            variances.append("Clock-in recorded without matching clock-out punch")

        variance_summary = "; ".join(variances) if variances else "Standard attendance parameters within tolerance."

        comparison = AttendanceComparison(
            actual_worked_minutes=actual_worked_minutes,
            expected_worked_minutes=expected_worked_minutes,
            actual_overtime_minutes=actual_overtime_minutes,
            expected_overtime_minutes=0,
            actual_late_minutes=actual_late_minutes,
            expected_late_minutes=0,
            actual_break_minutes=actual_break_minutes,
            expected_break_minutes=60,
            clock_in_time=clock_in_str,
            clock_out_time=clock_out_str,
            scheduled_start=sched_start_str,
            scheduled_end=sched_end_str,
            variance_summary=variance_summary
        )

        # 6. Retrieve historical records (past 30 days prior to anomaly date)
        window_start = anomaly.date - timedelta(days=30)
        hist_stmt = select(AttendanceRecord).where(
            and_(
                AttendanceRecord.employee_id == anomaly.employee_id,
                AttendanceRecord.date >= window_start,
                AttendanceRecord.date <= anomaly.date
            )
        )
        hist_records = (await db.execute(hist_stmt)).scalars().all()

        total_pts = len(hist_records)
        if total_pts > 0:
            worked_mins_list = [r.worked_minutes for r in hist_records if r.worked_minutes and r.worked_minutes > 0]
            avg_worked_m = sum(worked_mins_list) / len(worked_mins_list) if worked_mins_list else float(expected_worked_minutes)
            avg_worked_h = round(avg_worked_m / 60.0, 1)

            ot_days = sum(1 for r in hist_records if r.overtime_minutes and r.overtime_minutes > 0)
            total_ot_mins = sum(r.overtime_minutes for r in hist_records if r.overtime_minutes)
            total_ot_h = round(total_ot_mins / 60.0, 1)

            late_days = sum(1 for r in hist_records if (r.late_minutes and r.late_minutes > 0) or r.status == "late")
        else:
            avg_worked_m = float(expected_worked_minutes)
            avg_worked_h = round(expected_worked_minutes / 60.0, 1)
            ot_days = 0
            total_ot_h = 0.0
            late_days = 0

        # 7. Check count of previous anomalies of same type in past 60 days
        prev_anom_stmt = select(func.count(AttendanceAnomaly.id)).where(
            and_(
                AttendanceAnomaly.employee_id == anomaly.employee_id,
                AttendanceAnomaly.anomaly_type == anomaly.anomaly_type,
                AttendanceAnomaly.date >= anomaly.date - timedelta(days=60),
                AttendanceAnomaly.id != anomaly.id
            )
        )
        similar_count = (await db.execute(prev_anom_stmt)).scalar() or 0

        history = HistoricalContext(
            average_worked_minutes_30d=round(avg_worked_m, 1),
            average_worked_hours_30d=avg_worked_h,
            overtime_frequency_30d=ot_days,
            total_overtime_hours_30d=total_ot_h,
            late_arrival_frequency_30d=late_days,
            previous_similar_anomalies_count=similar_count,
            assigned_shift_name=shift_name,
            assigned_shift_code=shift_code,
            assigned_shift_hours=shift_req_hours,
            grace_period_minutes=grace_period,
            data_points_analyzed=total_pts
        )

        return comparison, history
