from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry
from datetime import datetime, date

dash_bp = Blueprint('dash', __name__, template_folder='../templates')

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
    if active_queue and active_queue.status == 'completed' and active_queue.payment:
        # Check if payment is older than 2 hours to hide from main dashboard
        if (datetime.utcnow() - active_queue.payment.payment_date).total_seconds() > 7200:
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
            
    return render_template('patient_dashboard.html', 
                           appointments=appointments, 
                           active_queue=active_queue,
                           patients_ahead=patients_ahead)

@dash_bp.route('/doctor')
@login_required
def doctor():
    if current_user.role != 'doctor':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
        
    # Active queue entries for this doctor
    queue_entries = QueueEntry.query.filter(
        QueueEntry.doctor_id == current_user.id,
        QueueEntry.status.in_(['waiting', 'in_consultation'])
    ).order_by(QueueEntry.status.desc(), QueueEntry.position.asc()).all()
    
    # Historical stats
    completed_today = QueueEntry.query.filter_by(
        doctor_id=current_user.id, 
        status='completed'
    ).count()
    
    waiting_count = sum(1 for q in queue_entries if q.status == 'waiting')
    current_patient = next((q for q in queue_entries if q.status == 'in_consultation'), None)
    
    return render_template('doctor_dashboard.html', 
                           queue_entries=queue_entries,
                           completed_today=completed_today,
                           waiting_count=waiting_count,
                           current_patient=current_patient)

def reorder_queue(doctor_id):
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
        entry.position = idx
        queue_len_ahead = (idx - 1) + has_consult
        entry.predicted_wait_time = predict_wait_time(queue_len_ahead, specialty, experience, hour_of_day)

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
            
    entry.status = 'in_consultation'
    entry.position = 0
    db.session.commit()
    
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
            
    next_entry.status = 'in_consultation'
    next_entry.position = 0
    db.session.commit()
    
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
            query = query.join(District).filter(func.lower(District.name) == norm_name)

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
            "wait_time": entry.predicted_wait_time,
            "checkin_time": entry.check_in_time.strftime('%H:%M') if entry.check_in_time else '—'
        })
    return jsonify({"tokens": tokens})

