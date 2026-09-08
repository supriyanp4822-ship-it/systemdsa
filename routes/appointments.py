# New imports
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry, Department, Hospital, DoctorSchedule
from datetime import datetime, timedelta

# Blueprint definition
appt_bp = Blueprint('appointments', __name__, template_folder='../templates')

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
    # Find the DoctorProfile id for the given doctor (User) ID
    doctor_profile = DoctorProfile.query.filter_by(user_id=doctor_id).first()
    if not doctor_profile:
        return jsonify({'error': 'Doctor profile not found'}), 404
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
            doctor_id=doctor_id,
            date=appt_date,
            time_slot=slot_str,
            status='paid'
        ).first()
        if not existing:
            slots.append(slot_str)
        cur += timedelta(minutes=30)
    return jsonify({'slots': slots})

# Create a new appointment (pending payment)
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
        doctor_id=doctor_id,
        date=appt_date,
        time_slot=time_slot,
        status='paid'
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
    flash("Appointment registered! Please complete payment to confirm your booking.", "info")
    return redirect(url_for('appointments.payment', appt_id=appointment.id))

# Payment handling – after successful payment redirect to confirmation
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
    if request.method == 'POST':
        card_number = request.form.get('card_number')
        if not card_number or len(card_number.replace(' ', '')) < 16:
            flash("Invalid card information.", "danger")
            return render_template('payment.html', appt=appt)
        appt.status = 'paid'
        db.session.commit()
        flash("Payment successful! Your appointment has been secured.", "success")
        return redirect(url_for('appointments.confirm', appt_id=appt.id))
    return render_template('payment.html', appt=appt)

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
