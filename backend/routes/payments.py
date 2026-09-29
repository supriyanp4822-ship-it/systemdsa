from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from extensions import db
from models import User, DoctorProfile, Appointment, QueueEntry, Payment
from services.upi_service import sanitize_upi_merchant, generate_upi_payload, generate_qr_code_base64, verify_upi_payment
from datetime import datetime
import uuid

pay_bp = Blueprint('pay', __name__)

@pay_bp.route('/checkout/<int:entry_id>')
@login_required
def checkout(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)

    if current_user.role == 'patient' and entry.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    if entry.status != 'completed':
        flash("Consultation not yet completed.", "warning")
        return redirect(url_for('dash.index'))

    existing_pay = Payment.query.filter_by(queue_entry_id=entry.id, status='paid').first()
    if existing_pay:
        return redirect(url_for('pay.receipt', payment_id=existing_pay.id))

    doctor_profile = entry.doctor.doctor_profile if entry.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    
    amount = doctor_profile.consultation_fee if doctor_profile else 500.0
    hospital_name = hospital.name if hospital else "Hospital Care Center"
    
    # Generate unique transaction & receipt IDs
    now = datetime.now()
    txn_ref = f"TXN-UPI-{entry.id}-{uuid.uuid4().hex[:6].upper()}"
    merchant_name, merchant_upi = sanitize_upi_merchant(hospital_name)
    token_label = f"T{entry.id:03d}"
    doctor_name = entry.doctor.name if entry.doctor else "Doctor"
    note = f"Consultation Fee - Token {token_label} ({doctor_name})"
    
    # Standard UPI & Google Pay URI
    upi_url, gpay_url = generate_upi_payload(
        amount=amount,
        transaction_id=txn_ref,
        merchant_name=merchant_name,
        merchant_upi=merchant_upi,
        note=note
    )
    
    # Generate Base64 QR Code
    qr_code_data = generate_qr_code_base64(upi_url)

    return render_template(
        'payment/checkout.html',
        entry=entry,
        doctor_profile=doctor_profile,
        hospital=hospital,
        amount=amount,
        txn_ref=txn_ref,
        merchant_name=merchant_name,
        merchant_upi=merchant_upi,
        upi_url=upi_url,
        gpay_url=gpay_url,
        qr_code_data=qr_code_data,
        token_label=token_label
    )


@pay_bp.route('/api/initiate/<int:entry_id>', methods=['POST'])
@login_required
def initiate_payment(entry_id):
    """API endpoint to create an initiated payment record before user pays via UPI/Google Pay."""
    entry = QueueEntry.query.get_or_404(entry_id)
    if current_user.role == 'patient' and entry.patient_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    doctor_profile = entry.doctor.doctor_profile if entry.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    hospital_name = hospital.name if hospital else "Hospital Care Center"
    amount = doctor_profile.consultation_fee if doctor_profile else 500.0

    now = datetime.now()
    txn_ref = request.json.get('transaction_id') if request.is_json else request.form.get('transaction_id')
    if not txn_ref:
        txn_ref = f"TXN-UPI-{entry.id}-{uuid.uuid4().hex[:6].upper()}"
    
    receipt_no = f"REC-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    merchant_name, merchant_upi = sanitize_upi_merchant(hospital_name)
    token_label = f"T{entry.id:03d}"
    note = f"Consultation Fee - Token {token_label}"

    # Check for existing initiated payment
    payment = Payment.query.filter_by(queue_entry_id=entry.id).first()
    if not payment:
        payment = Payment(
            receipt_no=receipt_no,
            transaction_id=txn_ref,
            patient_id=entry.patient_id,
            doctor_id=entry.doctor_id,
            appointment_id=entry.appointment_id,
            queue_entry_id=entry.id,
            amount=amount,
            payment_method='UPI',
            upi_id=merchant_upi,
            status='initiated',
            payment_date=now
        )
        db.session.add(payment)
    else:
        if payment.status != 'paid':
            payment.transaction_id = txn_ref
            payment.status = 'initiated'
            payment.payment_date = now

    db.session.commit()

    upi_url, gpay_url = generate_upi_payload(amount, txn_ref, merchant_name, merchant_upi, note)
    qr_code_data = generate_qr_code_base64(upi_url)

    return jsonify({
        'status': 'initiated',
        'payment_id': payment.id,
        'transaction_id': txn_ref,
        'receipt_no': payment.receipt_no,
        'merchant_upi': merchant_upi,
        'merchant_name': merchant_name,
        'amount': amount,
        'upi_url': upi_url,
        'gpay_url': gpay_url,
        'qr_code': qr_code_data,
        'message': 'Payment initiated — awaiting verification'
    })


@pay_bp.route('/api/verify/<int:payment_id>', methods=['POST'])
@login_required
def verify_payment_api(payment_id):
    """API endpoint to verify UPI transaction status via UTR or gateway check."""
    payment = Payment.query.get_or_404(payment_id)
    if current_user.role == 'patient' and payment.patient_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or request.form
    utr_no = data.get('upi_ref_no', '').strip() if data else ''

    # If verification is requested
    verified, msg = verify_upi_payment(payment, entered_utr=utr_no if utr_no else None)
    
    if verified:
        db.session.commit()
        # Event 7: Payment successful notification
        from services.notification_service import notify_payment_successful
        notify_payment_successful(payment.patient_id, payment.amount, payment.receipt_no, payment.transaction_id)
        
        return jsonify({
            'success': True,
            'status': 'paid',
            'message': 'Payment Successful ✓',
            'receipt_url': url_for('pay.receipt', payment_id=payment.id)
        })
    else:
        # Awaiting verification
        payment.status = 'pending_verification'
        db.session.commit()
        return jsonify({
            'success': False,
            'status': 'pending_verification',
            'message': msg or 'Payment initiated — awaiting verification'
        }), 200


@pay_bp.route('/process/<int:entry_id>', methods=['POST'])
@login_required
def process(entry_id):
    entry = QueueEntry.query.get_or_404(entry_id)

    if current_user.role == 'patient' and entry.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    method = request.form.get('payment_method')
    if not method or method not in ('UPI', 'Card', 'Cash'):
        flash("Please select a valid payment method.", "danger")
        return redirect(url_for('pay.checkout', entry_id=entry_id))

    doctor_profile = entry.doctor.doctor_profile if entry.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    hospital_name = hospital.name if hospital else "Hospital Care Center"
    merchant_name, merchant_upi = sanitize_upi_merchant(hospital_name)

    now = datetime.now()
    receipt_no = f"REC-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    
    # Custom or submitted transaction reference
    custom_txn = request.form.get('transaction_id')
    transaction_id = custom_txn if custom_txn else f"TXN-{method.upper()}-{uuid.uuid4().hex[:8].upper()}"
    
    amount = doctor_profile.consultation_fee if doctor_profile else 500.0
    upi_ref_no = request.form.get('upi_ref_no', '').strip() or None

    # Check if a payment record already exists for this entry
    payment = Payment.query.filter_by(queue_entry_id=entry.id).first()
    if not payment:
        payment = Payment(
            receipt_no=receipt_no,
            transaction_id=transaction_id,
            patient_id=entry.patient_id,
            doctor_id=entry.doctor_id,
            appointment_id=entry.appointment_id,
            queue_entry_id=entry.id,
            amount=amount,
            payment_method=method,
            upi_id=merchant_upi if method == 'UPI' else None,
            upi_ref_no=upi_ref_no,
            status='paid',
            payment_date=now,
            verified_at=now
        )
        db.session.add(payment)
    else:
        payment.receipt_no = receipt_no
        payment.transaction_id = transaction_id
        payment.payment_method = method
        payment.amount = amount
        payment.upi_id = merchant_upi if method == 'UPI' else None
        payment.upi_ref_no = upi_ref_no
        payment.status = 'paid'
        payment.payment_date = now
        payment.verified_at = now

    db.session.commit()

    # Event 7: Payment successful
    from services.notification_service import notify_payment_successful
    notify_payment_successful(entry.patient_id, amount, receipt_no, transaction_id)

    flash("Payment successful! Your official consultation receipt has been generated.", "success")
    return redirect(url_for('pay.receipt', payment_id=payment.id))


@pay_bp.route('/receipt/<int:payment_id>')
@login_required
def receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if current_user.role == 'patient' and payment.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    doctor_profile = payment.doctor.doctor_profile if payment.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    return render_template('payment/receipt.html', payment=payment, doctor_profile=doctor_profile, hospital=hospital)


@pay_bp.route('/download/<int:payment_id>')
@login_required
def download_receipt(payment_id):
    """Download receipt as printable standalone document."""
    payment = Payment.query.get_or_404(payment_id)
    if current_user.role == 'patient' and payment.patient_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dash.index'))

    doctor_profile = payment.doctor.doctor_profile if payment.doctor else None
    hospital = doctor_profile.hospital if doctor_profile else None
    
    rendered = render_template('payment/receipt.html', payment=payment, doctor_profile=doctor_profile, hospital=hospital, is_download=True)
    
    response = Response(rendered, mimetype='text/html')
    response.headers['Content-Disposition'] = f'inline; filename="Receipt_{payment.receipt_no}.html"'
    return response


@pay_bp.route('/history')
@login_required
def history():
    if current_user.role != 'patient':
        flash("Access restricted.", "warning")
        return redirect(url_for('dash.index'))

    payments = Payment.query.filter_by(patient_id=current_user.id).order_by(Payment.payment_date.desc()).all()
    total_spent = sum(p.amount for p in payments if p.status == 'paid')
    return render_template('payment/history.html', payments=payments, total_spent=total_spent)


@pay_bp.route('/admin/payments')
@login_required
def admin_payments():
    if current_user.role != 'admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('dash.index'))

    search = request.args.get('search', '').strip()
    method_filter = request.args.get('method', '')

    query = Payment.query
    if search:
        query = query.join(User, Payment.patient_id == User.id).filter(
            db.or_(
                Payment.receipt_no.ilike(f'%{search}%'),
                Payment.transaction_id.ilike(f'%{search}%'),
                User.name.ilike(f'%{search}%'),
            )
        )
    if method_filter:
        query = query.filter(Payment.payment_method == method_filter)

    payments = query.order_by(Payment.payment_date.desc()).all()
    total_revenue = sum(p.amount for p in payments if p.status == 'paid')
    return render_template(
        'payment/admin_payments.html',
        payments=payments,
        total_revenue=total_revenue,
        search=search,
        method_filter=method_filter,
    )
