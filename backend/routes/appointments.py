# New imports
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry, Department, Hospital, DoctorSchedule
from datetime import datetime, timedelta

# Blueprint definition
appt_bp = Blueprint('appointments', __name__)

# Index route – provides doctors, hospitals, departments
@appt_bp.route('/')
@login_required
def index():
    if current_user.role != 'patient':
        flash("Only patients can book appointments.", "warning")
        return redirect(url_for('dash.index'))
    doctors = User.query.filter_by(role='doctor').all()
    hospitals = Hospital.query.all()
    departments = Department.query.all()
    return render_template('appointment.html', doctors=doctors, hospitals=hospitals, departments=departments)

# AJAX endpoint to get available slots for a doctor on a given date
@appt_bp.route('/slots', methods=['POST'])
@login_required
def get_slots():
    doctor_id = request.form.get('doctor_id')
    date_str = request.form.get('date')
    if not doctor_id or not date_str:
        return jsonify({'error': 'Missing parameters'}), 400
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date'}), 400
    doctor_profile = DoctorProfile.query.filter_by(user_id=doctor_id).first()
    if not doctor_profile:
        return jsonify({'error': 'Doctor profile not found'}), 404
    day_name = appt_date.strftime('%A')
    schedule = DoctorSchedule.query.filter_by(doctor_profile_id=doctor_profile.id, day_of_week=day_name).first()
    if not schedule:
        return jsonify({'slots': []})
    start = datetime.strptime(schedule.start_time, '%H:%M').time()
    end = datetime.strptime(schedule.end_time, '%H:%M').time()
    slots = []
    cur = datetime.combine(appt_date, start)
    end_dt = datetime.combine(appt_date, end)
    while cur + timedelta(minutes=30) <= end_dt:
        slot_str = cur.strftime('%I:%M %p')
        existing = Appointment.query.filter_by(
            doctor_id=doctor_id, date=appt_date, time_slot=slot_str, status='paid'
        ).first()
        if not existing:
            slots.append(slot_str)
        cur += timedelta(minutes=30)
    return jsonify({'slots': slots})

# Create a new appointment (pending payment) - original book route kept for backward compat
@appt_bp.route('/book', methods=['POST'])
@login_required
def book():
    if current_user.role != 'patient':
        flash("Only patients can book appointments.", "warning")
        return redirect(url_for('dash.index'))
    doctor_id = request.form.get('doctor_id')
    date_str = request.form.get('date')
    time_slot = request.form.get('time_slot')
    if not doctor_id or not date_str or not time_slot:
        flash("Please fill in all fields.", "danger")
        return redirect(url_for('appointments.index'))
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for('appointments.index'))
    existing = Appointment.query.filter_by(
        doctor_id=doctor_id, date=appt_date, time_slot=time_slot, status='paid'
    ).first()
    if existing:
        flash("This time slot is already booked for this doctor. Please choose another.", "danger")
        return redirect(url_for('appointments.index'))
    appointment = Appointment(
        patient_id=current_user.id,
        doctor_id=doctor_id,
        date=appt_date,
        time_slot=time_slot,
        status='scheduled'
    )
    db.session.add(appointment)
    db.session.commit()

    from services.notification_service import notify_appointment_booked
    notify_appointment_booked(appointment)

    flash("Appointment registered! Please complete payment to confirm your booking.", "info")
    return redirect(url_for('appointments.payment', appt_id=appointment.id))

# Payment handling for appointment booking
@appt_bp.route('/payment/<int:appt_id>', methods=['GET', 'POST'])
@login_required
def payment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    if appt.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
    if appt.status != 'scheduled':
        flash("Appointment already paid or processed.", "warning")
        return redirect(url_for('dash.index'))
    
    doctor_profile = appt.doctor.doctor_profile if appt.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    hospital_name = hospital.name if hospital else "Hospital Care Center"
    amount = doctor_profile.consultation_fee if doctor_profile else 500.0
    
    from services.upi_service import sanitize_upi_merchant, generate_upi_payload, generate_qr_code_base64
    import uuid
    merchant_name, merchant_upi = sanitize_upi_merchant(hospital_name)
    txn_ref = f"TXN-APT-{appt.id}-{uuid.uuid4().hex[:6].upper()}"
    note = f"Appointment Fee - Dr. {appt.doctor.name if appt.doctor else 'Doctor'}"
    
    upi_url, gpay_url = generate_upi_payload(amount, txn_ref, merchant_name, merchant_upi, note)
    qr_code_data = generate_qr_code_base64(upi_url)

    if request.method == 'POST':
        method = request.form.get('payment_method', 'UPI')
        custom_txn = request.form.get('transaction_id')
        transaction_id = custom_txn if custom_txn else txn_ref
        upi_ref_no = request.form.get('upi_ref_no', '').strip() or None
        
        from models import Payment
        from services.notification_service import notify_payment_successful
        
        appt.status = 'paid'
        now = datetime.now()
        receipt_no = f"REC-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        new_pay = Payment(
            receipt_no=receipt_no,
            transaction_id=transaction_id,
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            appointment_id=appt.id,
            amount=amount,
            payment_method=method,
            upi_id=merchant_upi if method == 'UPI' else None,
            upi_ref_no=upi_ref_no,
            status='paid',
            payment_date=now,
            verified_at=now
        )
        db.session.add(new_pay)
        db.session.commit()
        
        notify_payment_successful(appt.patient_id, amount, receipt_no, transaction_id)
        flash("Payment successful! Your appointment has been secured.", "success")
        return redirect(url_for('appointments.confirm', appt_id=appt.id))

    return render_template(
        'payment.html',
        appt=appt,
        hospital=hospital,
        doctor_profile=doctor_profile,
        amount=amount,
        txn_ref=txn_ref,
        merchant_name=merchant_name,
        merchant_upi=merchant_upi,
        upi_url=upi_url,
        gpay_url=gpay_url,
        qr_code_data=qr_code_data
    )

# Confirmation page after payment
@appt_bp.route('/confirm/<int:appt_id>')
@login_required
def confirm(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    doctor_user = User.query.get(appt.doctor_id)
    doctor_profile = doctor_user.doctor_profile if doctor_user else None
    hospital = doctor_profile.hospital if doctor_profile else None
    department_name = doctor_profile.specialty if doctor_profile else None
    return render_template('appointment_success.html', appt=appt, doctor=doctor_user, hospital=hospital, department=department_name)

# Patient cancels appointment
@appt_bp.route('/cancel/<int:appt_id>', methods=['POST'])
@login_required
def cancel(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    if appt.patient_id != current_user.id and current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))
    if appt.status in ('completed', 'cancelled'):
        flash(f"Appointment already {appt.status}.", "warning")
        return redirect(url_for('dash.index'))
    appt.status = 'cancelled'
    if appt.queue_entry and appt.queue_entry.status == 'waiting':
        appt.queue_entry.status = 'skipped'
        from routes.dashboard import reorder_queue
        reorder_queue(appt.doctor_id)
    db.session.commit()
    from services.notification_service import notify_appointment_cancelled
    notify_appointment_cancelled(appt)
    flash("Your appointment has been cancelled.", "info")
    return redirect(url_for('dash.index'))


# ── API: Hospital departments + doctors with live queue + AI wait time ──
@appt_bp.route('/api/hospital/<int:hospital_id>')
@login_required
def api_hospital_details(hospital_id):
    hospital = Hospital.query.get_or_404(hospital_id)
    from predictor import predict_wait_time
    dept_rows = db.session.query(DoctorProfile.specialty).filter_by(hospital_id=hospital_id).distinct().all()
    departments = [r[0] for r in dept_rows]
    doctors_raw = DoctorProfile.query.filter_by(hospital_id=hospital_id).all()
    doctors_out = []
    hour = datetime.now().hour
    for dp in doctors_raw:
        doc_user = dp.user
        if not doc_user or doc_user.role != 'doctor':
            continue
        waiting_count = QueueEntry.query.filter_by(doctor_id=doc_user.id, status='waiting').count()
        in_consult = QueueEntry.query.filter_by(doctor_id=doc_user.id, status='in_consultation').count()
        total_queue = waiting_count + in_consult
        ai_wait = predict_wait_time(total_queue, dp.specialty, dp.experience, hour)
        schedule_days = [s.day_of_week for s in dp.schedules] if dp.schedules else []
        today_name = datetime.now().strftime('%A')
        is_today = today_name in schedule_days
        doctors_out.append({
            'id': doc_user.id,
            'name': doc_user.name,
            'specialty': dp.specialty,
            'experience': dp.experience,
            'fee': dp.consultation_fee,
            'rating': dp.rating,
            'room': dp.room_number or 'N/A',
            'available_from': dp.available_from,
            'available_to': dp.available_to,
            'schedule_days': schedule_days,
            'is_available_today': is_today,
            'waiting_count': waiting_count,
            'in_consult': in_consult,
            'total_queue': total_queue,
            'ai_wait_time': ai_wait,
        })
    return jsonify({
        'hospital': {
            'id': hospital.id,
            'name': hospital.name,
            'address': hospital.address,
            'phone': hospital.phone,
            'opening_time': hospital.opening_time,
            'closing_time': hospital.closing_time,
        },
        'departments': departments,
        'doctors': doctors_out,
        'hospital_queue_total': sum(d['total_queue'] for d in doctors_out),
    })


# ── Confirmation Preview page before booking ──
@appt_bp.route('/preview', methods=['POST'])
@login_required
def preview():
    if current_user.role != 'patient':
        flash("Only patients can book appointments.", "warning")
        return redirect(url_for('dash.index'))
    doctor_id = request.form.get('doctor_id')
    date_str  = request.form.get('date')
    time_slot = request.form.get('time_slot')
    dept_name = request.form.get('department', '')
    if not doctor_id or not date_str or not time_slot:
        flash("Please complete all required fields.", "danger")
        return redirect(url_for('appointments.index'))
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date.", "danger")
        return redirect(url_for('appointments.index'))
    doctor_user = User.query.get_or_404(doctor_id)
    dp = doctor_user.doctor_profile
    hospital = dp.hospital if dp else None
    from predictor import predict_wait_time
    waiting_count = QueueEntry.query.filter_by(doctor_id=doctor_user.id, status='waiting').count()
    in_consult    = QueueEntry.query.filter_by(doctor_id=doctor_user.id, status='in_consultation').count()
    ai_wait = predict_wait_time(
        waiting_count + in_consult,
        dp.specialty if dp else 'General',
        dp.experience if dp else 5,
        datetime.now().hour
    )
    return render_template('appointment_preview.html',
        doctor=doctor_user,
        dp=dp,
        hospital=hospital,
        dept_name=dept_name or (dp.specialty if dp else 'General'),
        appt_date=appt_date,
        time_slot=time_slot,
        ai_wait=ai_wait,
    )


# ── Final booking from confirmation page ──
@appt_bp.route('/book-confirmed', methods=['POST'])
@login_required
def book_confirmed():
    if current_user.role != 'patient':
        flash("Only patients can book appointments.", "warning")
        return redirect(url_for('dash.index'))
    doctor_id = request.form.get('doctor_id')
    date_str  = request.form.get('date')
    time_slot = request.form.get('time_slot')
    if not doctor_id or not date_str or not time_slot:
        flash("Missing booking details.", "danger")
        return redirect(url_for('appointments.index'))
    try:
        appt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date.", "danger")
        return redirect(url_for('appointments.index'))
    existing = Appointment.query.filter_by(
        doctor_id=doctor_id, date=appt_date, time_slot=time_slot, status='paid'
    ).first()
    if existing:
        flash("This slot was just taken. Please choose another.", "danger")
        return redirect(url_for('appointments.index'))
    appointment = Appointment(
        patient_id=current_user.id,
        doctor_id=doctor_id,
        date=appt_date,
        time_slot=time_slot,
        status='scheduled'
    )
    db.session.add(appointment)
    db.session.commit()
    from services.notification_service import notify_appointment_booked
    notify_appointment_booked(appointment)
    flash("Appointment registered! Please complete payment to confirm.", "info")
    return redirect(url_for('appointments.payment', appt_id=appointment.id))
