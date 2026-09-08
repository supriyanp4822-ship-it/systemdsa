from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry, Payment
from datetime import datetime
import uuid

pay_bp = Blueprint('pay', __name__, template_folder='../templates')

@pay_bp.route('/checkout/<int:entry_id>')
@login_required
def checkout(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)

    # Security: check if patient or admin
    if current_user.role == 'patient' and entry.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    if entry.status != 'completed':
        flash("Consultation not yet completed.", "warning")
        return redirect(url_for('dash.index'))

    # Check if already paid
    existing_pay = Payment.query.filter_by(queue_entry_id=entry.id).first()
    if existing_pay:
        return redirect(url_for('pay.receipt', payment_id=existing_pay.id))

    doctor_profile = entry.doctor.doctor_profile
    return render_template('payment/checkout.html', entry=entry, doctor_profile=doctor_profile)

@pay_bp.route('/process/<int:entry_id>', methods=['POST'])
@login_required
def process(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)
    method = request.form.get('payment_method')

    if not method:
        flash("Please select a payment method.", "danger")
        return redirect(url_for('pay.checkout', entry_id=entry.id))

    # Generate unique receipt number
    receipt_no = f"REC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    amount = entry.doctor.doctor_profile.consultation_fee if entry.doctor.doctor_profile else 500.0

    new_payment = Payment(
        receipt_no=receipt_no,
        patient_id=entry.patient_id,
        doctor_id=entry.doctor_id,
        appointment_id=entry.appointment_id,
        queue_entry_id=entry.id,
        amount=amount,
        payment_method=method,
        status='paid'
    )

    db.session.add(new_payment)
    db.session.commit()

    flash("Payment successful! Receipt generated.", "success")
    return redirect(url_for('pay.receipt', payment_id=new_payment.id))

@pay_bp.route('/receipt/<int:payment_id>')
@login_required
def receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if current_user.role == 'patient' and payment.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    return render_template('payment/receipt.html', payment=payment)

@pay_bp.route('/history')
@login_required
def history():
    if current_user.role != 'patient':
        return redirect(url_for('dash.index'))

    payments = Payment.query.filter_by(patient_id=current_user.id).order_by(Payment.payment_date.desc()).all()
    return render_template('payment/history.html', payments=payments)
