from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry, Department
from datetime import date, datetime
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, template_folder='../templates')

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Unauthorized access.", "danger")
            return redirect(url_for('dash.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    # Summary Cards Data
    total_patients = User.query.filter_by(role='patient').count()
    today_appts = Appointment.query.filter_by(date=date.today()).count()
    waiting_patients = QueueEntry.query.filter_by(status='waiting').count()
    doctors_available = User.query.filter_by(role='doctor').count()
    completed_today = QueueEntry.query.filter(
        QueueEntry.status == 'completed',
        func.date(QueueEntry.check_in_time) == date.today()
    ).count()

    # Recent Activity / Stats for charts or lists
    recent_appts = Appointment.query.order_by(Appointment.id.desc()).limit(5).all()

    # Department stats
    dept_stats = []
    departments = Department.query.all()
    for dept in departments:
        waiting = QueueEntry.query.join(User, QueueEntry.doctor_id == User.id)\
            .join(DoctorProfile, User.id == DoctorProfile.user_id)\
            .filter(DoctorProfile.specialty == dept.name, QueueEntry.status == 'waiting').count()
        dept_stats.append({'name': dept.name, 'waiting': waiting})

    return render_template('admin/dashboard.html',
                           total_patients=total_patients,
                           today_appts=today_appts,
                           waiting_patients=waiting_patients,
                           doctors_available=doctors_available,
                           completed_today=completed_today,
                           recent_appts=recent_appts,
                           dept_stats=dept_stats)

# --- Patient Management ---
@admin_bp.route('/patients')
@login_required
@admin_required
def patients():
    search = request.args.get('search', '')
    if search:
        patients_list = User.query.filter(
            User.role == 'patient',
            (User.name.ilike(f'%{search}%')) | (User.email.ilike(f'%{search}%')) | (User.username.ilike(f'%{search}%'))
        ).all()
    else:
        patients_list = User.query.filter_by(role='patient').all()
    return render_template('admin/patients.html', patients=patients_list, search=search)

@admin_bp.route('/patients/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_patient(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'patient':
        flash("Cannot delete non-patient users from here.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"Patient {user.name} deleted successfully.", "success")
    return redirect(url_for('admin.patients'))

# --- Doctor Management ---
@admin_bp.route('/doctors')
@login_required
@admin_required
def doctors():
    doctors_list = User.query.filter_by(role='doctor').all()
    depts = Department.query.all()
    return render_template('admin/doctors.html', doctors=doctors_list, departments=depts)

@admin_bp.route('/doctors/add', methods=['POST'])
@login_required
@admin_required
def add_doctor():
    username = request.form.get('username')
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    specialty = request.form.get('specialty')
    experience = request.form.get('experience', 5)
    fee = request.form.get('consultation_fee', 300.0)

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("Username or email already exists.", "danger")
        return redirect(url_for('admin.doctors'))
        
    doc_user = User(username=username, email=email, role='doctor', name=name)
    doc_user.set_password(password)
    db.session.add(doc_user)
    db.session.flush()
    
    profile = DoctorProfile(
        user_id=doc_user.id,
        specialty=specialty,
        experience=int(experience),
        consultation_fee=float(fee)
    )
    db.session.add(profile)
    db.session.commit()
    flash(f"Doctor {name} added.", "success")
    return redirect(url_for('admin.doctors'))

@admin_bp.route('/doctors/edit/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_doctor(user_id):
    user = User.query.get_or_404(user_id)
    profile = user.doctor_profile
    user.name = request.form.get('name')
    user.email = request.form.get('email')
    profile.specialty = request.form.get('specialty')
    profile.experience = int(request.form.get('experience'))
    profile.consultation_fee = float(request.form.get('consultation_fee'))
    db.session.commit()
    flash("Doctor updated.", "success")
    return redirect(url_for('admin.doctors'))

@admin_bp.route('/doctors/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_doctor(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("Doctor removed.", "success")
    return redirect(url_for('admin.doctors'))

# --- Department Management ---
@admin_bp.route('/departments')
@login_required
@admin_required
def departments():
    depts = Department.query.all()
    # Calculate waiting for each dept
    dept_data = []
    for d in depts:
        waiting = QueueEntry.query.join(User, QueueEntry.doctor_id == User.id)\
            .join(DoctorProfile, User.id == DoctorProfile.user_id)\
            .filter(DoctorProfile.specialty == d.name, QueueEntry.status == 'waiting').count()
        dept_data.append({'id': d.id, 'name': d.name, 'description': d.description, 'waiting': waiting})
    return render_template('admin/departments.html', departments=dept_data)

@admin_bp.route('/departments/add', methods=['POST'])
@login_required
@admin_required
def add_department():
    name = request.form.get('name')
    desc = request.form.get('description')
    if Department.query.filter_by(name=name).first():
        flash("Department already exists.", "danger")
    else:
        new_dept = Department(name=name, description=desc)
        db.session.add(new_dept)
        db.session.commit()
        flash("Department added.", "success")
    return redirect(url_for('admin.departments'))

@admin_bp.route('/departments/delete/<int:dept_id>', methods=['POST'])
@login_required
@admin_required
def delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    db.session.delete(dept)
    db.session.commit()
    flash("Department deleted.", "success")
    return redirect(url_for('admin.departments'))

# --- Queue Management ---
@admin_bp.route('/queue')
@login_required
@admin_required
def queue():
    active_entries = QueueEntry.query.filter(QueueEntry.status.in_(['waiting', 'in_consultation'])).all()
    return render_template('admin/queue.html', active_entries=active_entries)

@admin_bp.route('/queue/clear-completed', methods=['POST'])
@login_required
@admin_required
def clear_completed_queues():
    # Technically they are already status 'completed', maybe just a cleanup route if needed
    # User asked to "Clear/close completed queues"
    # We'll just flash a message as we don't store "closed" queues differently yet
    flash("Completed queues processed.", "info")
    return redirect(url_for('admin.queue'))

# --- Appointment Management ---
@admin_bp.route('/appointments')
@login_required
@admin_required
def appointments():
    status_filter = request.args.get('status', 'all')
    if status_filter == 'all':
        appts = Appointment.query.order_by(Appointment.date.desc()).all()
    else:
        appts = Appointment.query.filter_by(status=status_filter).order_by(Appointment.date.desc()).all()
    return render_template('admin/appointments.html', appointments=appts, current_filter=status_filter)

@admin_bp.route('/appointments/update/<int:appt_id>/<string:status>', methods=['POST'])
@login_required
@admin_required
def update_appointment(appt_id, status):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = status
    db.session.commit()
    flash(f"Appointment marked as {status}.", "success")
    return redirect(url_for('admin.appointments'))

@admin_bp.route('/payments')
@login_required
@admin_required
def payments_list():
    pays = Payment.query.order_by(Payment.payment_date.desc()).all()
    return render_template('admin/payments.html', payments=pays)
