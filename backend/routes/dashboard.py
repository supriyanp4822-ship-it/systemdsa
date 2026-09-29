from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry
from datetime import datetime, date

dash_bp = Blueprint('dash', __name__)

@dash_bp.route('/')
@login_required
def index():
    if current_user.role != 'patient':
        if current_user.role == 'doctor':
            return redirect(url_for('dash.doctor'))
        elif current_user.role == 'admin':
            return redirect(url_for('dash.admin'))
            
    appointments = Appointment.query.filter_by(patient_id=current_user.id).order_by(Appointment.date.desc()).all()
    
    # Active queue entry (only show waiting/in_consultation/completed_unpaid)
    active_queue = QueueEntry.query.filter(
        QueueEntry.patient_id == current_user.id,
        QueueEntry.status.in_(['waiting', 'in_consultation', 'completed'])
    ).order_by(QueueEntry.id.desc()).first()

    # Don't show completed if it's already paid and older than 1 hour (cleanup dashboard)
    if active_queue and active_queue.status == 'completed':
        from models import Payment
        qp = Payment.query.filter_by(queue_entry_id=active_queue.id, status='paid').first()
        if qp and qp.payment_date and (datetime.utcnow() - qp.payment_date).total_seconds() > 7200:
            active_queue = None
    
    # Calculate how many patients are ahead of the current user
    patients_ahead = 0
    if active_queue and active_queue.status == 'waiting':
        patients_ahead = QueueEntry.query.filter(
            QueueEntry.doctor_id == active_queue.doctor_id,
            QueueEntry.status == 'waiting',
            QueueEntry.position < active_queue.position
        ).count()
        # Add 1 if there's someone currently in consultation
        in_consult = QueueEntry.query.filter_by(doctor_id=active_queue.doctor_id, status='in_consultation').first()
        if in_consult:
            patients_ahead += 1

    from models import Notification
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(15).all()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            
    # Find the next upcoming appointment (scheduled or paid, from today onwards)
    upcoming_appt = Appointment.query.filter(
        Appointment.patient_id == current_user.id,
        Appointment.status.in_(['scheduled', 'paid']),
        Appointment.date >= date.today()
    ).order_by(Appointment.date.asc()).first()

    # Get hospital/dept info for upcoming appointment
    upcoming_hospital = None
    upcoming_dept = None
    upcoming_ai_wait = 0
    if upcoming_appt:
        doc_profile = upcoming_appt.doctor.doctor_profile if upcoming_appt.doctor else None
        upcoming_hospital = doc_profile.hospital if doc_profile else None
        upcoming_dept = doc_profile.specialty if doc_profile else 'General'
        from predictor import predict_wait_time as _pwt
        _qw = QueueEntry.query.filter_by(doctor_id=upcoming_appt.doctor_id, status='waiting').count()
        _qc = QueueEntry.query.filter_by(doctor_id=upcoming_appt.doctor_id, status='in_consultation').count()
        upcoming_ai_wait = _pwt(
            _qw + _qc,
            doc_profile.specialty if doc_profile else 'General',
            doc_profile.experience if doc_profile else 5,
            datetime.now().hour
        )

    return render_template('patient_dashboard.html', 
                           appointments=appointments, 
                           active_queue=active_queue,
                           patients_ahead=patients_ahead,
                           notifications=notifications,
                           unread_count=unread_count,
                           upcoming_appt=upcoming_appt,
                           upcoming_hospital=upcoming_hospital,
                           upcoming_dept=upcoming_dept,
                           upcoming_ai_wait=upcoming_ai_wait)


@dash_bp.route('/doctor')
@login_required
def doctor():
    if current_user.role != 'doctor':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
    return redirect(url_for('doctor.dashboard'))

def reorder_queue(doctor_id, skip_entry_id=None):
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
    from services.notification_service import notify_position_changed, notify_wait_time_updated
    
    for idx, entry in enumerate(waiting_entries, start=1):
        old_position = entry.position
        old_wait = entry.predicted_wait_time

        entry.position = idx
        queue_len_ahead = max(0, (idx - 1) + has_consult)
        new_wait = max(0, int(round(predict_wait_time(queue_len_ahead, specialty, experience, hour_of_day))))
        entry.predicted_wait_time = new_wait

        if skip_entry_id is not None and entry.id == skip_entry_id:
            continue

        # Event 3: Queue position changed
        if old_position != 0 and old_position != idx:
            notify_position_changed(entry, idx)

        # Event 4: Waiting time updated
        if old_wait != 0 and old_wait != new_wait:
            notify_wait_time_updated(entry, new_wait)

@dash_bp.route('/doctor/start/<int:entry_id>', methods=['POST'])
@login_required
def start_consultation(entry_id):
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))
        
    entry = QueueEntry.query.get_or_404(entry_id)
    
    if entry.doctor_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.doctor'))
        
    # Check if there is another patient already in consultation
    active_consult = QueueEntry.query.filter_by(doctor_id=current_user.id, status='in_consultation').first()
    if active_consult:
        # Automatically mark them completed
        active_consult.status = 'completed'
        active_consult.position = 0
        if active_consult.appointment:
            active_consult.appointment.status = 'completed'
        # Event 6: Consultation completed for previous active patient
        from services.notification_service import notify_consultation_completed
        notify_consultation_completed(active_consult)
            
    entry.status = 'in_consultation'
    entry.position = 0
    db.session.commit()

    # Event 5: Doctor calls patient
    from services.notification_service import notify_doctor_called
    notify_doctor_called(entry)
    
    # Recalculate remaining waiting entries
    reorder_queue(current_user.id)
    db.session.commit()
    
    flash(f"Consultation started with {entry.patient.name}.", "success")
    return redirect(url_for('dash.doctor'))

@dash_bp.route('/doctor/complete/<int:entry_id>', methods=['POST'])
@login_required
def complete_consultation(entry_id):
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))
        
    entry = QueueEntry.query.get_or_404(entry_id)
    
    if entry.doctor_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.doctor'))
        
    entry.status = 'completed'
    entry.position = 0
    if entry.appointment:
        entry.appointment.status = 'completed'
        
    db.session.commit()

    # Event 6: Consultation completed
    from services.notification_service import notify_consultation_completed
    notify_consultation_completed(entry)
    
    # Recalculate remaining waiting entries
    reorder_queue(current_user.id)
    db.session.commit()
    
    flash(f"Consultation with {entry.patient.name} completed successfully.", "success")
    return redirect(url_for('dash.doctor'))

@dash_bp.route('/doctor/skip/<int:entry_id>', methods=['POST'])
@login_required
def skip_patient(entry_id):
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))
        
    entry = QueueEntry.query.get_or_404(entry_id)
    
    if entry.doctor_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.doctor'))
        
    entry.status = 'skipped'
    entry.position = 0
    db.session.commit()
    
    # Recalculate remaining waiting entries
    reorder_queue(current_user.id)
    db.session.commit()
    
    flash(f"Patient {entry.patient.name} marked as skipped.", "warning")
    return redirect(url_for('dash.doctor'))

@dash_bp.route('/doctor/call_next', methods=['POST'])
@login_required
def call_next():
    if current_user.role != 'doctor':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))
        
    # Get the waiting entry with position 1
    next_entry = QueueEntry.query.filter_by(
        doctor_id=current_user.id,
        status='waiting'
    ).order_by(QueueEntry.position.asc()).first()
    
    if not next_entry:
        flash("No waiting patients in your line.", "info")
        return redirect(url_for('dash.doctor'))
        
    # Check if there is another patient already in consultation
    active_consult = QueueEntry.query.filter_by(doctor_id=current_user.id, status='in_consultation').first()
    if active_consult:
        active_consult.status = 'completed'
        active_consult.position = 0
        if active_consult.appointment:
            active_consult.appointment.status = 'completed'
        # Event 6: Consultation completed for previous active patient
        from services.notification_service import notify_consultation_completed
        notify_consultation_completed(active_consult)
            
    next_entry.status = 'in_consultation'
    next_entry.position = 0
    db.session.commit()

    # Event 5: Doctor calls patient
    from services.notification_service import notify_doctor_called
    notify_doctor_called(next_entry)
    
    # Recalculate remaining waiting entries
    reorder_queue(current_user.id)
    db.session.commit()
    
    flash(f"Called next patient: {next_entry.patient.name}.", "success")
    return redirect(url_for('dash.doctor'))



@dash_bp.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
    return redirect(url_for('admin.dashboard'))

@dash_bp.route('/admin/bump/<int:entry_id>', methods=['POST'])
@login_required
def bump_priority(entry_id):
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
        
    entry = QueueEntry.query.get_or_404(entry_id)
    
    if entry.status != 'waiting':
        flash("Can only bump patients waiting in line.", "warning")
        return redirect(url_for('dash.admin'))
        
    # Bump to position 1
    old_position = entry.position
    if old_position == 1:
        flash(f"{entry.patient.name} is already at the front of the queue.", "info")
        return redirect(url_for('dash.admin'))
        
    # Shift other waiting patients for this doctor who are ahead of him down by 1
    other_entries = QueueEntry.query.filter(
        QueueEntry.doctor_id == entry.doctor_id,
        QueueEntry.status == 'waiting',
        QueueEntry.position < old_position
    ).all()
    
    for item in other_entries:
        item.position += 1
        
    entry.position = 1
    db.session.commit()

    reorder_queue(entry.doctor_id)
    db.session.commit()

    flash(f"Emergency bump successful! {entry.patient.name} is now next in line.", "success")
    return redirect(url_for('dash.admin'))

# Location Dashboard
@dash_bp.route('/location-dashboard')
@login_required
def location_dashboard():
    from models import District
    districts = District.query.order_by(District.name).all()
    return render_template('location_dashboard.html', districts=districts)

# API endpoint for districts
@dash_bp.route('/api/districts')
@login_required
def api_districts():
    from flask import jsonify
    from models import District
    districts = District.query.order_by(District.name).all()
    return jsonify({"districts": [{"id": d.id, "name": d.name} for d in districts]})

# API endpoint for map data
@dash_bp.route('/api/locations')
@login_required
def api_locations():
    from flask import jsonify, request, current_app
    from models import Hospital, District
    import traceback

    district_id = request.args.get('district_id')
    district_name = request.args.get('district') # optional string filter

    locations = []
    debug_info = {
        "selected_district_id": district_id,
        "selected_district_name": district_name,
        "hospital_count": 0,
        "db_districts": []
    }

    try:
        # Get all hospitals from DB
        query = Hospital.query

        if district_id and district_id != 'all':
            query = query.filter_by(district_id=district_id)
        elif district_name and district_name != 'all':
            # Normalized search by name
            norm_name = district_name.strip().lower()
            query = query.join(District).filter(db.func.lower(District.name) == norm_name)

        hospitals = query.all()
        debug_info["hospital_count"] = len(hospitals)

        # Log all districts for debugging
        all_districts = District.query.all()
        debug_info["db_districts"] = [d.name for d in all_districts]

        for hosp in hospitals:
            # Get count of available doctors
            doc_count = DoctorProfile.query.filter_by(hospital_id=hosp.id).count()
            # Available departments
            depts = db.session.query(DoctorProfile.specialty).filter_by(hospital_id=hosp.id).distinct().all()
            dept_names = [d[0] for d in depts]

            locations.append({
                "type": "hospital",
                "id": hosp.id,
                "name": hosp.name,
                "lat": hosp.latitude,
                "lng": hosp.longitude,
                "address": hosp.address,
                "phone": hosp.phone,
                "district": hosp.district.name,
                "doctor_count": doc_count,
                "departments": dept_names
            })

        # Doctor locations with live queue counts
        if district_id and district_id != 'all':
            doctors = DoctorProfile.query.join(User).filter(User.role == 'doctor').filter(DoctorProfile.hospital_id.in_([h.id for h in hospitals])).all()
        else:
            doctors = DoctorProfile.query.join(User).filter(User.role == 'doctor').all()

        for doc in doctors:
            if doc.latitude is not None and doc.longitude is not None:
                waiting = QueueEntry.query.filter_by(doctor_id=doc.user_id, status='waiting').count()
                consulting = QueueEntry.query.filter_by(doctor_id=doc.user_id, status='in_consultation').count()
                locations.append({
                    "type": "doctor",
                    "id": doc.id,
                    "name": doc.user.name,
                    "lat": doc.latitude,
                    "lng": doc.longitude,
                    "specialty": doc.specialty,
                    "waiting": waiting,
                    "consulting": consulting,
                    "fee": doc.consultation_fee,
                    "rating": doc.rating,
                    "hospital": doc.hospital.name if doc.hospital else "Private Clinic"
                })

        # Append debug info if in debug mode
        response_data = {"locations": locations}
        if current_app.debug:
            response_data["debug"] = debug_info

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in api_locations: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e), "locations": []}), 500

# Hospital Details Route
@dash_bp.route('/hospital/<int:hospital_id>')
@login_required
def hospital_details(hospital_id):
    from models import Hospital, Department
    hospital = Hospital.query.get_or_404(hospital_id)

    # Get distinct specialties (departments) available in this hospital
    depts = db.session.query(DoctorProfile.specialty).filter_by(hospital_id=hospital_id).distinct().all()
    dept_names = [d[0] for d in depts]

    doctor_count = DoctorProfile.query.filter_by(hospital_id=hospital_id).count()

    # Determine status (simple open/closed based on current time)
    now = datetime.now().strftime("%H:%M")
    is_open = hospital.opening_time <= now <= hospital.closing_time

    return render_template('hospital_details.html',
                           hospital=hospital,
                           departments=dept_names,
                           doctor_count=doctor_count,
                           is_open=is_open)

# Hospital Doctors Route
@dash_bp.route('/hospital/<int:hospital_id>/doctors')
@login_required
def hospital_doctors(hospital_id):
    from models import Hospital, DoctorProfile, Department
    hospital = Hospital.query.get_or_404(hospital_id)

    dept_filter = request.args.get('department')

    query = DoctorProfile.query.filter_by(hospital_id=hospital_id)
    if dept_filter:
        query = query.filter_by(specialty=dept_filter)

    doctors = query.all()

    # Get all available departments for filter
    depts = db.session.query(DoctorProfile.specialty).filter_by(hospital_id=hospital_id).distinct().all()
    dept_names = [d[0] for d in depts]

    return render_template('hospital_doctors.html',
                           hospital=hospital,
                           doctors=doctors,
                           departments=dept_names,
                           current_dept=dept_filter)

# Doctor Profile Route
@dash_bp.route('/doctor-profile/<int:user_id>')
@login_required
def doctor_profile(user_id):
    from models import User
    doctor = User.query.get_or_404(user_id)
    if doctor.role != 'doctor':
        flash("User is not a doctor.", "danger")
        return redirect(url_for('dash.index'))

    return render_template('doctor_profile_public.html', doctor=doctor)

# API endpoint for queue token list
@dash_bp.route('/api/queue-tokens')
@login_required
def api_queue_tokens():
    from flask import jsonify
    active_entries = QueueEntry.query.filter(
        QueueEntry.status.in_(['waiting', 'in_consultation'])
    ).order_by(QueueEntry.doctor_id, QueueEntry.position).all()

    tokens = []
    for entry in active_entries:
        tokens.append({
            "token": f"T{entry.id:03d}",
            "patient": entry.patient.name,
            "doctor": entry.doctor.name,
            "specialty": entry.doctor.doctor_profile.specialty if entry.doctor.doctor_profile else "General",
            "position": entry.position,
            "status": entry.status,
            "wait_time": max(0, entry.predicted_wait_time or 0),
            "checkin_time": entry.check_in_time.strftime('%H:%M') if entry.check_in_time else '—'
        })
    return jsonify({"tokens": tokens})

# --- Notification Routes ---
@dash_bp.route('/notifications')
@login_required
def all_notifications():
    from models import Notification
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('notifications.html', notifications=notifications, unread_count=unread_count)

@dash_bp.route('/api/notifications')
@login_required
def api_notifications():
    from flask import jsonify
    from models import Notification
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(30).all()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({
        'success': True,
        'unread_count': unread_count,
        'notifications': [n.to_dict() for n in notifications]
    })

@dash_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def api_mark_notification_read(notif_id):
    from flask import jsonify
    from models import Notification
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'success': True, 'unread_count': unread_count})

@dash_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def api_mark_all_read():
    from flask import jsonify
    from models import Notification
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True, 'unread_count': 0})


