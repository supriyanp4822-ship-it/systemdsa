from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry
from predictor import predict_wait_time
from datetime import datetime

queue_bp = Blueprint('queue', __name__)

@queue_bp.route('/')
def index():
    # Public board showing active queues for all doctors
    doctors = User.query.filter_by(role='doctor').all()
    queue_data = {}
    
    for doc in doctors:
        # Active entries: waiting or in consultation
        active_entries = QueueEntry.query.filter(
            QueueEntry.doctor_id == doc.id,
            QueueEntry.status.in_(['waiting', 'in_consultation'])
        ).order_by(QueueEntry.position.asc()).all()

        # Recent completed entries (last 5)
        completed_entries = QueueEntry.query.filter_by(
            doctor_id=doc.id,
            status='completed'
        ).order_by(QueueEntry.id.desc()).limit(5).all()

        current_consulting = next((q for q in active_entries if q.status == 'in_consultation'), None)
        waiting_list = [q for q in active_entries if q.status == 'waiting']
        
        # Calculate total wait time for a new patient joining now
        experience = doc.doctor_profile.experience if doc.doctor_profile else 5
        specialty = doc.doctor_profile.specialty if doc.doctor_profile else 'General'
        hour_of_day = datetime.now().hour
        total_wait = predict_wait_time(len(active_entries), specialty, experience, hour_of_day)

        queue_data[doc.id] = {
            'doctor_name': doc.name,
            'specialty': specialty,
            'current': current_consulting.patient.name if current_consulting else 'None',
            'token_current': f"T{current_consulting.id:03d}" if current_consulting else None,
            'waiting': [
                {
                    'id': q.id,
                    'name': q.patient.name,
                    'position': q.position,
                    'wait_time': max(0, q.predicted_wait_time or 0)
                }
                for q in waiting_list
            ],
            'completed': [
                {
                    'id': q.id,
                    'name': q.patient.name
                }
                for q in completed_entries
            ],
            'wait_count': len(waiting_list),
            'total_wait_time': total_wait
        }
        
    return render_template('queue.html', queue_data=queue_data)

@queue_bp.route('/checkin/<int:appt_id>', methods=['POST'])
@login_required
def checkin(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    
    if appt.patient_id != current_user.id:
        flash("Unauthorized check-in.", "danger")
        return redirect(url_for('dash.index'))
        
    if appt.status != 'paid':
        flash("Please complete payment before checking in.", "warning")
        return redirect(url_for('appointments.payment', appt_id=appt.id))
        
    # Check if already checked in
    existing_entry = QueueEntry.query.filter_by(appointment_id=appt.id).first()
    if existing_entry:
        flash("You are already checked in for this appointment.", "warning")
        return redirect(url_for('dash.index'))
        
    # Get active queue length for this doctor
    active_queue = QueueEntry.query.filter(
        QueueEntry.doctor_id == appt.doctor_id,
        QueueEntry.status.in_(['waiting', 'in_consultation'])
    ).all()
    
    queue_len = len(active_queue)
    
    # Calculate position (next integer in waiting line)
    waiting_entries = [q for q in active_queue if q.status == 'waiting']
    next_position = max([q.position for q in waiting_entries]) + 1 if waiting_entries else 1

    # Create queue entry with dummy position/wait time, reorder_queue will fix it
    entry = QueueEntry(
        patient_id=current_user.id,
        doctor_id=appt.doctor_id,
        appointment_id=appt.id,
        position=next_position,
        status='waiting',
        predicted_wait_time=0
    )
    
    db.session.add(entry)
    db.session.commit()
    
    # Use reorder_queue to calculate proper position and ML wait time
    from routes.dashboard import reorder_queue
    reorder_queue(appt.doctor_id, skip_entry_id=entry.id)
    db.session.commit()

    # Refetch entry to get predicted time
    db.session.refresh(entry)

    # Event 2: Queue token generated
    # Event 4: Waiting time updated
    from services.notification_service import notify_token_generated, notify_wait_time_updated
    notify_token_generated(entry)
    if entry.predicted_wait_time > 0:
        notify_wait_time_updated(entry, entry.predicted_wait_time)

    flash(f"Check-in successful! Your queue position is #{entry.position}. Estimated waiting time: {entry.predicted_wait_time} mins.", "success")
    return redirect(url_for('dash.index'))

