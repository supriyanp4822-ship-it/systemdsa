from extensions import db
from models import Notification, Appointment, QueueEntry, User
from datetime import datetime

def create_notification(user_id, title, message, event_type, extra_info=None):
    """
    Creates and persists a real event notification for a user.
    """
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            event_type=event_type,
            extra_info=extra_info,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {e}")
        return None

def notify_appointment_booked(appointment):
    """
    Event 1: Appointment booked
    - 'Your appointment has been booked successfully.'
    - Show: Hospital, Doctor, Date, Time, Appointment ID
    """
    doctor_name = appointment.doctor.name if appointment.doctor else "Assigned Doctor"
    hospital_name = "Hospital Care Center"
    if appointment.doctor and appointment.doctor.doctor_profile and appointment.doctor.doctor_profile.hospital:
        hospital_name = appointment.doctor.doctor_profile.hospital.name
        
    date_str = appointment.date.strftime('%d %b, %Y') if hasattr(appointment.date, 'strftime') else str(appointment.date)
    time_str = appointment.time_slot
    appt_id_str = f"#APT-{appointment.id}"
    
    title = "Appointment Booked"
    message = (
        f"Your appointment has been booked successfully. "
        f"Hospital: {hospital_name} | Doctor: {doctor_name} | Date: {date_str} | Time: {time_str} | Appointment ID: {appt_id_str}"
    )
    extra_info = f"{hospital_name} · {doctor_name} · {appt_id_str}"
    return create_notification(appointment.patient_id, title, message, 'appointment_booked', extra_info)

def notify_token_generated(queue_entry):
    """
    Event 2: Queue token generated
    - 'Your queue token is T005.'
    - Show: Token number, Doctor, Department, Queue position
    """
    token_str = f"T{queue_entry.id:03d}"
    position = queue_entry.position
    doctor_name = queue_entry.doctor.name if queue_entry.doctor else "Doctor"
    dept_name = queue_entry.doctor.doctor_profile.specialty if (queue_entry.doctor and queue_entry.doctor.doctor_profile) else "General"
    
    title = "Queue Token Generated"
    message = (
        f"Your queue token is {token_str}. "
        f"Doctor: {doctor_name} | Department: {dept_name} | Queue Position: #{position}."
    )
    extra_info = f"Token: {token_str} · Pos: #{position} · {dept_name}"
    return create_notification(queue_entry.patient_id, title, message, 'queue_token_generated', extra_info)

def notify_position_changed(queue_entry, new_position):
    """
    Event 3: Queue position changed
    - 'Your current queue position is #2.'
    """
    token_str = f"T{queue_entry.id:03d}"
    title = "Queue Position Updated"
    message = f"Your current queue position is #{new_position}."
    extra_info = f"Token {token_str} · Position #{new_position}"
    return create_notification(queue_entry.patient_id, title, message, 'queue_position_changed', extra_info)

def notify_wait_time_updated(queue_entry, wait_time):
    """
    Event 4: Waiting time updated
    - 'Your estimated waiting time is 20 minutes.'
    - Show the latest estimated waiting time.
    """
    token_str = f"T{queue_entry.id:03d}"
    title = "Waiting Time Updated"
    message = f"Your estimated waiting time is {wait_time} minutes."
    extra_info = f"Token {token_str} · ~{wait_time} mins"
    return create_notification(queue_entry.patient_id, title, message, 'waiting_time_updated', extra_info)

def notify_doctor_called(queue_entry):
    """
    Event 5: Doctor calls patient
    - 'Please proceed to the consultation room.'
    - Show: Doctor, Room number, Token number
    """
    doctor_name = queue_entry.doctor.name if queue_entry.doctor else "Doctor"
    room_number = "Cabin 1"
    if queue_entry.doctor and queue_entry.doctor.doctor_profile and queue_entry.doctor.doctor_profile.room_number:
        room_number = queue_entry.doctor.doctor_profile.room_number
    token_str = f"T{queue_entry.id:03d}"
        
    title = "Doctor Calling"
    message = f"Please proceed to the consultation room. Doctor: {doctor_name} | Room: {room_number} | Token: {token_str}."
    extra_info = f"Dr. {doctor_name} · Room {room_number} · {token_str}"
    return create_notification(queue_entry.patient_id, title, message, 'doctor_called', extra_info)

def notify_consultation_completed(queue_entry):
    """
    Event 6: Consultation completed
    - 'Your consultation has been completed.'
    """
    token_str = f"T{queue_entry.id:03d}"
    doctor_name = queue_entry.doctor.name if queue_entry.doctor else "Doctor"
    title = "Consultation Completed"
    message = f"Your consultation has been completed with {doctor_name}."
    extra_info = f"Token {token_str} · Completed"
    return create_notification(queue_entry.patient_id, title, message, 'consultation_completed', extra_info)

def notify_payment_successful(patient_id, amount, receipt_no, transaction_id):
    """
    Event 7: Payment successful
    - 'Payment successful.'
    - Show: Amount, Transaction ID, Receipt number
    """
    title = "Payment Successful"
    message = f"Payment successful. Amount: ₹{amount:.2f} | Transaction ID: {transaction_id} | Receipt Number: {receipt_no}."
    extra_info = f"₹{amount:.2f} · {receipt_no}"
    return create_notification(patient_id, title, message, 'payment_successful', extra_info)

def notify_appointment_cancelled(appointment):
    """
    Event 8: Appointment cancelled
    - 'Your appointment has been cancelled.'
    - Show: Hospital, Doctor, Appointment ID
    """
    doctor_name = appointment.doctor.name if appointment.doctor else "Assigned Doctor"
    hospital_name = "Hospital Care Center"
    if appointment.doctor and appointment.doctor.doctor_profile and appointment.doctor.doctor_profile.hospital:
        hospital_name = appointment.doctor.doctor_profile.hospital.name
        
    appt_id_str = f"#APT-{appointment.id}"
    title = "Appointment Cancelled"
    message = f"Your appointment has been cancelled. Hospital: {hospital_name} | Doctor: {doctor_name} | Appointment ID: {appt_id_str}."
    extra_info = f"Cancelled {appt_id_str} · {doctor_name}"
    return create_notification(appointment.patient_id, title, message, 'appointment_cancelled', extra_info)
