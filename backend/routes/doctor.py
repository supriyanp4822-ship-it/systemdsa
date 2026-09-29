from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, DoctorSchedule, Appointment, QueueEntry, Consultation, Hospital, Department
from datetime import datetime, date
from services.notification_service import (
    notify_doctor_called, notify_consultation_completed, notify_position_changed, notify_wait_time_updated
)

doc_bp = Blueprint('doctor', __name__, url_prefix='/doctor')

def reorder_doctor_queue(doctor_id, skip_entry_id=None):
    """Reorders doctor queue positions and updates AI waiting times."""
    active_consult = QueueEntry.query.filter_by(doctor_id=doctor_id, status='in_consultation').first()
    has_consult = 1 if active_consult else 0
    
    waiting_entries = QueueEntry.query.filter_by(
        doctor_id=doctor_id,
        status='waiting'
    ).order_by(QueueEntry.position.asc(), QueueEntry.check_in_time.asc()).all()
    
    doctor_profile = DoctorProfile.query.filter_by(user_id=doctor_id).first()
    experience = doctor_profile.experience if doctor_profile else 5
    specialty = doctor_profile.specialty if doctor_profile else 'General'
    hour_of_day = datetime.now().hour
    
    from predictor import predict_wait_time
    
    for idx, entry in enumerate(waiting_entries, start=1):
        old_position = entry.position
        old_wait = entry.predicted_wait_time

        entry.position = idx
        queue_len_ahead = max(0, (idx - 1) + has_consult)
        new_wait = max(0, int(round(predict_wait_time(queue_len_ahead, specialty, experience, hour_of_day))))
        entry.predicted_wait_time = new_wait

        if skip_entry_id is not None and entry.id == skip_entry_id:
            continue

        if old_position != 0 and old_position != idx:
            notify_position_changed(entry, idx)

        if old_wait != 0 and old_wait != new_wait:
            notify_wait_time_updated(entry, new_wait)
            
    db.session.commit()


@doc_bp.route('/')
@doc_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'doctor':
        flash("Unauthorized access. Doctor credentials required.", "danger")
        return redirect(url_for('dash.index'))

    doctor_profile = current_user.doctor_profile
    today = date.today()
    
    # 1. Today's Appointments (strict isolation by doctor_id)
    today_appointments = Appointment.query.filter(
        Appointment.doctor_id == current_user.id,
        Appointment.date == today
    ).order_by(Appointment.time_slot.asc()).all()
    
    # 2. Active Queue Entries (Waiting or In Consultation)
    queue_entries = QueueEntry.query.filter(
        QueueEntry.doctor_id == current_user.id,
        QueueEntry.status.in_(['waiting', 'in_consultation'])
    ).order_by(QueueEntry.status.desc(), QueueEntry.position.asc()).all()

    # 3. Summary Statistics
    today_appts_count = len(today_appointments)
    waiting_count = sum(1 for q in queue_entries if q.status == 'waiting')
    current_patient = next((q for q in queue_entries if q.status == 'in_consultation'), None)
    
    completed_today = QueueEntry.query.filter(
        QueueEntry.doctor_id == current_user.id,
        QueueEntry.status == 'completed',
        db.func.date(QueueEntry.check_in_time) == today
    ).count()
    
    # If no completed today by date, fallback to overall completed count
    if completed_today == 0:
        completed_today = QueueEntry.query.filter_by(
            doctor_id=current_user.id, 
            status='completed'
        ).count()

    # Average waiting time calculation
    waiting_times = [q.predicted_wait_time for q in queue_entries if q.status == 'waiting' and q.predicted_wait_time > 0]
    avg_wait_time = int(sum(waiting_times) / len(waiting_times)) if waiting_times else 15

    # Get active consultation if any
    active_consultation = None
    if current_patient:
        active_consultation = Consultation.query.filter_by(queue_entry_id=current_patient.id).first()

    return render_template(
        'doctor_dashboard.html',
        doctor_profile=doctor_profile,
        today_appointments=today_appointments,
        queue_entries=queue_entries,
        today_appts_count=today_appts_count,
        waiting_count=waiting_count,
        completed_today=completed_today,
        current_patient=current_patient,
        avg_wait_time=avg_wait_time,
        active_consultation=active_consultation
    )


@doc_bp.route('/call_next', methods=['POST'])
@login_required
def call_next():
    """Selects the next waiting patient, sets to 'in_consultation', updates queue & notifies patient."""
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    # Get the waiting entry with position 1
    next_entry = QueueEntry.query.filter_by(
        doctor_id=current_user.id,
        status='waiting'
    ).order_by(QueueEntry.position.asc(), QueueEntry.check_in_time.asc()).first()

    if not next_entry:
        flash("No waiting patients in your queue line.", "info")
        return redirect(url_for('doctor.dashboard'))

    # If another patient is already in consultation, auto-complete
    active_consult = QueueEntry.query.filter_by(doctor_id=current_user.id, status='in_consultation').first()
    if active_consult:
        active_consult.status = 'completed'
        active_consult.position = 0
        if active_consult.appointment:
            active_consult.appointment.status = 'completed'
        
        # Mark consultation record completed
        consult_rec = Consultation.query.filter_by(queue_entry_id=active_consult.id).first()
        if consult_rec and not consult_rec.completed_at:
            consult_rec.completed_at = datetime.utcnow()
            
        notify_consultation_completed(active_consult)

    next_entry.status = 'in_consultation'
    next_entry.position = 0
    
    # Initialize Consultation record
    consult = Consultation.query.filter_by(queue_entry_id=next_entry.id).first()
    if not consult:
        consult = Consultation(
            doctor_id=current_user.id,
            patient_id=next_entry.patient_id,
            appointment_id=next_entry.appointment_id,
            queue_entry_id=next_entry.id,
            started_at=datetime.utcnow()
        )
        db.session.add(consult)

    db.session.commit()

    # Event 5: Doctor calls patient notification
    notify_doctor_called(next_entry)

    # Recalculate remaining queue
    reorder_doctor_queue(current_user.id)

    flash(f"Now Calling Token T{next_entry.id:03d} ({next_entry.patient.name}). Patient has been notified.", "success")
    return redirect(url_for('doctor.dashboard'))


@doc_bp.route('/start/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def start_consultation(entry_id):
    """Starts consultation with a specific patient and opens consultation editor."""
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    entry = QueueEntry.query.get_or_404(entry_id)
    if entry.doctor_id != current_user.id:
        flash("Unauthorized access to this patient record.", "danger")
        return redirect(url_for('doctor.dashboard'))

    # If another patient is active, complete them
    active_consult = QueueEntry.query.filter_by(doctor_id=current_user.id, status='in_consultation').first()
    if active_consult and active_consult.id != entry.id:
        active_consult.status = 'completed'
        active_consult.position = 0
        if active_consult.appointment:
            active_consult.appointment.status = 'completed'
        notify_consultation_completed(active_consult)

    entry.status = 'in_consultation'
    entry.position = 0
    
    # Ensure Consultation record exists
    consult = Consultation.query.filter_by(queue_entry_id=entry.id).first()
    if not consult:
        consult = Consultation(
            doctor_id=current_user.id,
            patient_id=entry.patient_id,
            appointment_id=entry.appointment_id,
            queue_entry_id=entry.id,
            started_at=datetime.utcnow()
        )
        db.session.add(consult)

    db.session.commit()

    notify_doctor_called(entry)
    reorder_doctor_queue(current_user.id)

    return redirect(url_for('doctor.consultation_page', entry_id=entry.id))


@doc_bp.route('/consultation/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def consultation_page(entry_id):
    """Clinical consultation page for recording symptoms, diagnosis, prescription, and follow-up."""
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    entry = QueueEntry.query.get_or_404(entry_id)
    if entry.doctor_id != current_user.id:
        flash("Unauthorized access to this patient record.", "danger")
        return redirect(url_for('doctor.dashboard'))

    consult = Consultation.query.filter_by(queue_entry_id=entry.id).first()
    if not consult:
        consult = Consultation(
            doctor_id=current_user.id,
            patient_id=entry.patient_id,
            appointment_id=entry.appointment_id,
            queue_entry_id=entry.id,
            started_at=datetime.utcnow()
        )
        db.session.add(consult)
        db.session.commit()

    if request.method == 'POST':
        consult.symptoms = request.form.get('symptoms', '').strip()
        consult.diagnosis = request.form.get('diagnosis', '').strip()
        consult.prescription = request.form.get('prescription', '').strip()
        consult.notes = request.form.get('notes', '').strip()
        
        follow_up_str = request.form.get('follow_up_date')
        if follow_up_str:
            try:
                consult.follow_up_date = datetime.strptime(follow_up_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        db.session.commit()
        
        if 'complete_and_save' in request.form:
            return redirect(url_for('doctor.complete_consultation', entry_id=entry.id))
        
        flash("Consultation clinical notes saved successfully.", "success")
        return redirect(url_for('doctor.consultation_page', entry_id=entry.id))

    doctor_profile = current_user.doctor_profile
    return render_template(
        'consultation.html',
        entry=entry,
        consult=consult,
        doctor_profile=doctor_profile
    )


@doc_bp.route('/complete/<int:entry_id>', methods=['POST', 'GET'])
@login_required
def complete_consultation(entry_id):
    """Completes consultation, updates queue and appointment status, and notifies patient."""
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    entry = QueueEntry.query.get_or_404(entry_id)
    if entry.doctor_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('doctor.dashboard'))

    entry.status = 'completed'
    entry.position = 0
    if entry.appointment:
        entry.appointment.status = 'completed'

    consult = Consultation.query.filter_by(queue_entry_id=entry.id).first()
    if consult:
        consult.completed_at = datetime.utcnow()

    db.session.commit()

    # Event 6: Consultation completed notification
    notify_consultation_completed(entry)

    # Recalculate remaining waiting entries
    reorder_doctor_queue(current_user.id)

    flash(f"Consultation with {entry.patient.name} (Token T{entry.id:03d}) completed successfully.", "success")
    return redirect(url_for('doctor.dashboard'))


@doc_bp.route('/skip/<int:entry_id>', methods=['POST'])
@login_required
def skip_patient(entry_id):
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    entry = QueueEntry.query.get_or_404(entry_id)
    if entry.doctor_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('doctor.dashboard'))

    entry.status = 'skipped'
    entry.position = 0
    db.session.commit()

    reorder_doctor_queue(current_user.id)
    flash(f"Patient {entry.patient.name} (Token T{entry.id:03d}) marked as skipped.", "warning")
    return redirect(url_for('doctor.dashboard'))


@doc_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    dp = current_user.doctor_profile
    if dp:
        dp.room_number = request.form.get('room_number', dp.room_number)
        dp.available_from = request.form.get('available_from', dp.available_from)
        dp.available_to = request.form.get('available_to', dp.available_to)
        dp.consultation_fee = float(request.form.get('consultation_fee', dp.consultation_fee))
        db.session.commit()
        flash("Doctor profile & consultation room updated successfully.", "success")
    
    return redirect(url_for('doctor.dashboard'))
