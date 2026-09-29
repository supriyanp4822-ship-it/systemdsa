from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, DoctorSchedule, Appointment, QueueEntry, Department, Hospital, District, Payment, Notification, Consultation
from datetime import date, datetime
from database import func, or_
from functools import wraps

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Unauthorized access. Admin credentials required.", "danger")
            return redirect(url_for('dash.index'))
        return f(*args, **kwargs)
    return decorated_function


# ── 1. Admin Dashboard Summary ──
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    today = date.today()
    
    # Real database statistics
    total_patients = User.query.filter_by(role='patient').count()
    total_doctors = User.query.filter_by(role='doctor').count()
    total_hospitals = Hospital.query.count()
    today_appts = Appointment.query.filter_by(date=today).count()
    waiting_patients = QueueEntry.query.filter_by(status='waiting').count()
    
    completed_today = QueueEntry.query.filter(
        QueueEntry.status == 'completed'
    ).count()

    today_payments_records = Payment.query.filter(
        func.date(Payment.payment_date) == today,
        Payment.status == 'paid'
    ).all()
    today_payments_amount = sum(p.amount for p in today_payments_records)
    total_revenue = sum(p.amount for p in Payment.query.filter_by(status='paid').all())

    # Recent Activity
    recent_appts = Appointment.query.order_by(Appointment.id.desc()).limit(6).all()
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(5).all()

    # Department Queue Stats
    dept_stats = []
    departments = Department.query.all()
    for dept in departments:
        doc_count = DoctorProfile.query.filter_by(specialty=dept.name).count()
        waiting = QueueEntry.query.join(User, QueueEntry.doctor_id == User.id)\
            .join(DoctorProfile, User.id == DoctorProfile.user_id)\
            .filter(DoctorProfile.specialty == dept.name, QueueEntry.status == 'waiting').count()
        dept_stats.append({'name': dept.name, 'doc_count': doc_count, 'waiting': waiting})

    return render_template('admin/dashboard.html',
                           total_patients=total_patients,
                           total_doctors=total_doctors,
                           total_hospitals=total_hospitals,
                           today_appts=today_appts,
                           waiting_patients=waiting_patients,
                           completed_today=completed_today,
                           today_payments_amount=today_payments_amount,
                           total_revenue=total_revenue,
                           recent_appts=recent_appts,
                           recent_payments=recent_payments,
                           dept_stats=dept_stats)


# ── 2. Patient Management ──
@admin_bp.route('/patients')
@login_required
@admin_required
def patients():
    search = request.args.get('search', '').strip()
    query = User.query.filter_by(role='patient')
    
    if search:
        query = query.filter(
            or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.username.ilike(f'%{search}%')
            )
        )
    
    patients_list = query.order_by(User.id.desc()).all()
    
    # Calculate appointment counts
    patient_data = []
    for p in patients_list:
        appt_count = Appointment.query.filter_by(patient_id=p.id).count()
        patient_data.append({
            'user': p,
            'appt_count': appt_count
        })
        
    return render_template('admin/patients.html', patients=patient_data, search=search)


@admin_bp.route('/patients/toggle/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_patient(user_id):
    patient = User.query.get_or_404(user_id)
    if patient.role != 'patient':
        flash("Unauthorized action.", "danger")
        return redirect(url_for('admin.patients'))
        
    patient.is_active_user = not getattr(patient, 'is_active_user', True)
    db.session.commit()
    status_str = "activated" if patient.is_active_user else "deactivated"
    flash(f"Patient {patient.name} has been {status_str}.", "success")
    return redirect(url_for('admin.patients'))


@admin_bp.route('/patients/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_patient(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'patient':
        flash("Cannot delete non-patient user from here.", "danger")
    else:
        # Check if patient has active appointments
        active_appts = Appointment.query.filter(
            Appointment.patient_id == user.id,
            Appointment.status.in_(['scheduled', 'paid'])
        ).count()
        
        if active_appts > 0:
            user.is_active_user = False
            db.session.commit()
            flash(f"Patient has active appointments. Patient account has been deactivated instead of permanent deletion.", "warning")
        else:
            db.session.delete(user)
            db.session.commit()
            flash(f"Patient {user.name} removed successfully.", "success")
            
    return redirect(url_for('admin.patients'))


# ── 3. Doctor Management ──
@admin_bp.route('/doctors')
@login_required
@admin_required
def doctors():
    doctors_list = User.query.filter_by(role='doctor').order_by(User.id.desc()).all()
    departments = Department.query.all()
    hospitals = Hospital.query.all()
    
    doctor_data = []
    today = date.today()
    for doc in doctors_list:
        dp = doc.doctor_profile
        today_appts = Appointment.query.filter_by(doctor_id=doc.id, date=today).count()
        waiting_count = QueueEntry.query.filter_by(doctor_id=doc.id, status='waiting').count()
        doctor_data.append({
            'user': doc,
            'profile': dp,
            'today_appts': today_appts,
            'waiting_count': waiting_count
        })
        
    return render_template('admin/doctors.html', doctors=doctor_data, departments=departments, hospitals=hospitals)


@admin_bp.route('/doctors/add', methods=['POST'])
@login_required
@admin_required
def add_doctor():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '').strip()
    specialty = request.form.get('specialty', 'General Practitioner')
    hospital_id = request.form.get('hospital_id')
    experience = int(request.form.get('experience', 5))
    fee = float(request.form.get('consultation_fee', 500.0))
    room = request.form.get('room_number', 'OPD-1')
    available_from = request.form.get('available_from', '09:00')
    available_to = request.form.get('available_to', '17:00')

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("Username or email already exists.", "danger")
        return redirect(url_for('admin.doctors'))

    doc_user = User(username=username, email=email, role='doctor', name=name)
    doc_user.set_password(password or 'doctor123')
    db.session.add(doc_user)
    db.session.flush()

    profile = DoctorProfile(
        user_id=doc_user.id,
        hospital_id=int(hospital_id) if hospital_id else None,
        specialty=specialty,
        experience=experience,
        consultation_fee=fee,
        room_number=room,
        available_from=available_from,
        available_to=available_to
    )
    db.session.add(profile)
    db.session.commit()
    
    flash(f"Dr. {name} has been added successfully.", "success")
    return redirect(url_for('admin.doctors'))


@admin_bp.route('/doctors/edit/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_doctor(user_id):
    user = User.query.get_or_404(user_id)
    profile = user.doctor_profile
    
    user.name = request.form.get('name', user.name)
    user.email = request.form.get('email', user.email)
    
    if profile:
        profile.specialty = request.form.get('specialty', profile.specialty)
        h_id = request.form.get('hospital_id')
        profile.hospital_id = int(h_id) if h_id else profile.hospital_id
        profile.experience = int(request.form.get('experience', profile.experience))
        profile.consultation_fee = float(request.form.get('consultation_fee', profile.consultation_fee))
        profile.room_number = request.form.get('room_number', profile.room_number)
        profile.available_from = request.form.get('available_from', profile.available_from)
        profile.available_to = request.form.get('available_to', profile.available_to)

    db.session.commit()
    flash(f"Dr. {user.name}'s profile has been updated.", "success")
    return redirect(url_for('admin.doctors'))


@admin_bp.route('/doctors/toggle/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_doctor(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active_user = not getattr(user, 'is_active_user', True)
    db.session.commit()
    status_str = "activated" if user.is_active_user else "deactivated"
    flash(f"Dr. {user.name} has been {status_str}.", "success")
    return redirect(url_for('admin.doctors'))


# ── 4. Hospital Management ──
@admin_bp.route('/hospitals')
@login_required
@admin_required
def hospitals():
    hospitals_list = Hospital.query.order_by(Hospital.id.asc()).all()
    districts = District.query.order_by(District.name.asc()).all()
    
    hospital_data = []
    for h in hospitals_list:
        doc_count = DoctorProfile.query.filter_by(hospital_id=h.id).count()
        depts = db.session.query(DoctorProfile.specialty).filter_by(hospital_id=h.id).distinct().all()
        dept_names = [d[0] for d in depts]
        hospital_data.append({
            'hospital': h,
            'doc_count': doc_count,
            'departments': dept_names
        })
        
    return render_template('admin/hospitals.html', hospitals=hospital_data, districts=districts)


@admin_bp.route('/hospitals/add', methods=['POST'])
@login_required
@admin_required
def add_hospital():
    name = request.form.get('name', '').strip()
    district_id = request.form.get('district_id')
    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()
    lat = float(request.form.get('latitude', 11.0168))
    lng = float(request.form.get('longitude', 76.9558))
    open_t = request.form.get('opening_time', '09:00')
    close_t = request.form.get('closing_time', '21:00')

    if not district_id:
        flash("Please select a valid district.", "danger")
        return redirect(url_for('admin.hospitals'))

    new_h = Hospital(
        name=name,
        district_id=int(district_id),
        address=address,
        phone=phone,
        latitude=lat,
        longitude=lng,
        opening_time=open_t,
        closing_time=close_t,
        is_active=True
    )
    db.session.add(new_h)
    db.session.commit()
    flash(f"Hospital '{name}' added successfully.", "success")
    return redirect(url_for('admin.hospitals'))


@admin_bp.route('/hospitals/edit/<int:h_id>', methods=['POST'])
@login_required
@admin_required
def edit_hospital(h_id):
    h = Hospital.query.get_or_404(h_id)
    h.name = request.form.get('name', h.name)
    h.district_id = int(request.form.get('district_id', h.district_id))
    h.address = request.form.get('address', h.address)
    h.phone = request.form.get('phone', h.phone)
    h.latitude = float(request.form.get('latitude', h.latitude))
    h.longitude = float(request.form.get('longitude', h.longitude))
    h.opening_time = request.form.get('opening_time', h.opening_time)
    h.closing_time = request.form.get('closing_time', h.closing_time)
    
    db.session.commit()
    flash(f"Hospital '{h.name}' updated successfully.", "success")
    return redirect(url_for('admin.hospitals'))


@admin_bp.route('/hospitals/toggle/<int:h_id>', methods=['POST'])
@login_required
@admin_required
def toggle_hospital(h_id):
    h = Hospital.query.get_or_404(h_id)
    h.is_active = not getattr(h, 'is_active', True)
    db.session.commit()
    status_str = "activated" if h.is_active else "deactivated"
    flash(f"Hospital '{h.name}' {status_str}.", "success")
    return redirect(url_for('admin.hospitals'))


# ── 5. Department Management ──
@admin_bp.route('/departments')
@login_required
@admin_required
def departments():
    depts = Department.query.order_by(Department.name.asc()).all()
    dept_data = []
    for d in depts:
        doc_count = DoctorProfile.query.filter_by(specialty=d.name).count()
        waiting = QueueEntry.query.join(User, QueueEntry.doctor_id == User.id)\
            .join(DoctorProfile, User.id == DoctorProfile.user_id)\
            .filter(DoctorProfile.specialty == d.name, QueueEntry.status == 'waiting').count()
        dept_data.append({
            'id': d.id,
            'name': d.name,
            'description': d.description,
            'is_active': getattr(d, 'is_active', True),
            'doc_count': doc_count,
            'waiting': waiting
        })
    return render_template('admin/departments.html', departments=dept_data)


@admin_bp.route('/departments/add', methods=['POST'])
@login_required
@admin_required
def add_department():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if Department.query.filter_by(name=name).first():
        flash("Department already exists.", "danger")
    else:
        new_dept = Department(name=name, description=desc, is_active=True)
        db.session.add(new_dept)
        db.session.commit()
        flash(f"Department '{name}' added successfully.", "success")
    return redirect(url_for('admin.departments'))


@admin_bp.route('/departments/edit/<int:dept_id>', methods=['POST'])
@login_required
@admin_required
def edit_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    dept.name = request.form.get('name', dept.name).strip()
    dept.description = request.form.get('description', dept.description).strip()
    db.session.commit()
    flash(f"Department '{dept.name}' updated.", "success")
    return redirect(url_for('admin.departments'))


@admin_bp.route('/departments/toggle/<int:dept_id>', methods=['POST'])
@login_required
@admin_required
def toggle_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    dept.is_active = not getattr(dept, 'is_active', True)
    db.session.commit()
    status_str = "activated" if dept.is_active else "deactivated"
    flash(f"Department '{dept.name}' {status_str}.", "success")
    return redirect(url_for('admin.departments'))


# ── 6. Appointment Management ──
@admin_bp.route('/appointments')
@login_required
@admin_required
def appointments():
    status_filter = request.args.get('status', 'all')
    date_filter = request.args.get('date', '')
    doc_filter = request.args.get('doctor_id', '')
    hosp_filter = request.args.get('hospital_id', '')

    query = Appointment.query

    if status_filter != 'all':
        query = query.filter(Appointment.status == status_filter)
    if date_filter:
        try:
            d = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(Appointment.date == d)
        except ValueError:
            pass
    if doc_filter:
        query = query.filter(Appointment.doctor_id == int(doc_filter))
    if hosp_filter:
        query = query.join(User, Appointment.doctor_id == User.id)\
            .join(DoctorProfile, User.id == DoctorProfile.user_id)\
            .filter(DoctorProfile.hospital_id == int(hosp_filter))

    appts = query.order_by(Appointment.date.desc(), Appointment.id.desc()).all()
    doctors = User.query.filter_by(role='doctor').all()
    hospitals = Hospital.query.all()

    return render_template(
        'admin/appointments.html',
        appointments=appts,
        doctors=doctors,
        hospitals=hospitals,
        current_status=status_filter,
        current_date=date_filter,
        current_doc=doc_filter,
        current_hosp=hosp_filter
    )


@admin_bp.route('/appointments/update/<int:appt_id>/<string:status>', methods=['POST'])
@login_required
@admin_required
def update_appointment(appt_id, status):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = status
    if status == 'cancelled':
        from services.notification_service import notify_appointment_cancelled
        notify_appointment_cancelled(appt)
        if appt.queue_entry and appt.queue_entry.status == 'waiting':
            appt.queue_entry.status = 'skipped'
            from routes.dashboard import reorder_queue
            reorder_queue(appt.doctor_id)
            
    db.session.commit()
    flash(f"Appointment #APT-{appt.id} marked as {status}.", "success")
    return redirect(url_for('admin.appointments'))


# ── 7. Queue Management ──
@admin_bp.route('/queue')
@login_required
@admin_required
def queue():
    doctors = User.query.filter_by(role='doctor').all()
    queue_data = []

    for doc in doctors:
        dp = doc.doctor_profile
        hospital_name = dp.hospital.name if dp and dp.hospital else "Main Hospital"
        specialty = dp.specialty if dp else "General"
        
        active_entries = QueueEntry.query.filter(
            QueueEntry.doctor_id == doc.id,
            QueueEntry.status.in_(['waiting', 'in_consultation'])
        ).order_by(QueueEntry.position.asc()).all()

        current_consulting = next((q for q in active_entries if q.status == 'in_consultation'), None)
        waiting_entries = [q for q in active_entries if q.status == 'waiting']
        
        completed_count = QueueEntry.query.filter_by(
            doctor_id=doc.id,
            status='completed'
        ).count()

        est_wait = waiting_entries[0].predicted_wait_time if waiting_entries else 0

        queue_data.append({
            'doctor': doc,
            'hospital_name': hospital_name,
            'specialty': specialty,
            'current_token': f"T{current_consulting.id:03d}" if current_consulting else 'None',
            'current_patient': current_consulting.patient.name if current_consulting else None,
            'waiting_count': len(waiting_entries),
            'completed_count': completed_count,
            'est_wait': est_wait,
            'active_entries': active_entries
        })

    return render_template('admin/queue.html', queue_data=queue_data)


@admin_bp.route('/queue/reset/<int:doctor_id>', methods=['POST'])
@login_required
@admin_required
def reset_doctor_queue(doctor_id):
    """Safely completes / closes active entries without destroying historical data."""
    active_entries = QueueEntry.query.filter(
        QueueEntry.doctor_id == doctor_id,
        QueueEntry.status.in_(['waiting', 'in_consultation'])
    ).all()

    for q in active_entries:
        q.status = 'completed'
        q.position = 0
        if q.appointment:
            q.appointment.status = 'completed'
            
    db.session.commit()
    flash("Doctor's active queue has been safely closed.", "info")
    return redirect(url_for('admin.queue'))


# ── 8. Payment Management ──
@admin_bp.route('/payments')
@login_required
@admin_required
def payments_list():
    search = request.args.get('search', '').strip()
    method_filter = request.args.get('method', '')

    query = Payment.query
    if search:
        query = query.join(User, Payment.patient_id == User.id).filter(
            or_(
                Payment.receipt_no.ilike(f'%{search}%'),
                Payment.transaction_id.ilike(f'%{search}%'),
                User.name.ilike(f'%{search}%')
            )
        )
    if method_filter:
        query = query.filter(Payment.payment_method == method_filter)

    payments = query.order_by(Payment.payment_date.desc()).all()
    total_revenue = sum(p.amount for p in payments if p.status == 'paid')

    return render_template(
        'admin/payments.html',
        payments=payments,
        total_revenue=total_revenue,
        search=search,
        method_filter=method_filter
    )


# ── 9. System Notification Audit ──
@admin_bp.route('/notifications')
@login_required
@admin_required
def notifications():
    event_filter = request.args.get('type', request.args.get('event', 'all'))
    query = Notification.query

    if event_filter != 'all' and event_filter:
        if event_filter in ['appointment', 'appointments']:
            query = query.filter((Notification.event_type.in_(['appointment_booked', 'appointment_cancelled', 'appointment'])) | (Notification.title.ilike('%appointment%')))
        elif event_filter == 'queue':
            query = query.filter((Notification.event_type.in_(['queue_token_generated', 'queue_position_changed', 'waiting_time_updated', 'doctor_called', 'consultation_completed', 'queue'])) | (Notification.title.ilike('%queue%')) | (Notification.title.ilike('%token%')))
        elif event_filter in ['payment', 'payments']:
            query = query.filter((Notification.event_type.in_(['payment_successful', 'payment'])) | (Notification.title.ilike('%payment%')) | (Notification.title.ilike('%receipt%')))
        elif event_filter == 'system':
            query = query.filter(Notification.event_type.in_(['system', None]))

    notifications = query.order_by(Notification.created_at.desc()).limit(100).all()
    
    return render_template(
        'admin/notifications.html',
        notifications=notifications,
        filter_type=event_filter if event_filter != 'all' else None
    )
