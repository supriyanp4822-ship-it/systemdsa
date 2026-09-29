from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'patient', 'doctor', 'admin'
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class District(db.Model):
    __tablename__ = 'districts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    hospitals = db.relationship('Hospital', backref='district', lazy=True)

class Hospital(db.Model):
    __tablename__ = 'hospitals'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    district_id = db.Column(db.Integer, db.ForeignKey('districts.id', ondelete='CASCADE'), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    opening_time = db.Column(db.String(5), default="09:00")
    closing_time = db.Column(db.String(5), default="21:00")
    is_active = db.Column(db.Boolean, default=True)

    doctors = db.relationship('DoctorProfile', backref='hospital', lazy=True)

class DoctorProfile(db.Model):
    __tablename__ = 'doctor_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)
    specialty = db.Column(db.String(100), nullable=False)
    experience = db.Column(db.Integer, default=5)
    consultation_fee = db.Column(db.Float, default=500.0)
    rating = db.Column(db.Float, default=5.0)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    room_number = db.Column(db.String(20), nullable=True)
    available_from = db.Column(db.String(5), default="09:00")
    available_to = db.Column(db.String(5), default="17:00")
    
    # Relationship to user
    user = db.relationship('User', backref=db.backref('doctor_profile', uselist=False, cascade='all, delete-orphan'))

class DoctorSchedule(db.Model):
    __tablename__ = 'doctor_schedules'
    id = db.Column(db.Integer, primary_key=True)
    doctor_profile_id = db.Column(db.Integer, db.ForeignKey('doctor_profiles.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False) # e.g., "Monday"
    start_time = db.Column(db.String(5), default="09:00")
    end_time = db.Column(db.String(5), default="17:00")

    profile = db.relationship('DoctorProfile', backref=db.backref('schedules', cascade='all, delete-orphan'))

class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(10), nullable=False)  # e.g., "10:30 AM"
    status = db.Column(db.String(20), default="scheduled")  # 'scheduled', 'paid', 'completed', 'cancelled'
    
    patient = db.relationship('User', foreign_keys=[patient_id], backref=db.backref('appointments_as_patient', cascade='all, delete'))
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref=db.backref('appointments_as_doctor', cascade='all, delete'))

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(30), unique=True, nullable=False)
    transaction_id = db.Column(db.String(40), unique=True, nullable=True)  # unique txn ID / gateway ref
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True)
    queue_entry_id = db.Column(db.Integer, db.ForeignKey('queue_entries.id', ondelete='SET NULL'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False) # Cash, UPI, Card
    upi_id = db.Column(db.String(100), nullable=True)  # Merchant UPI or reference (no PIN/password stored)
    upi_ref_no = db.Column(db.String(60), nullable=True)  # Bank UTR / Payment gateway reference
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), default='paid')  # 'paid', 'initiated', 'pending_verification', 'failed'

    patient = db.relationship('User', foreign_keys=[patient_id], backref=db.backref('payments_as_patient', cascade='all, delete'))
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref=db.backref('payments_as_doctor', cascade='all, delete'))
    appointment = db.relationship('Appointment', backref=db.backref('payment', uselist=False))


class QueueEntry(db.Model):
    __tablename__ = 'queue_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True)
    position = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="waiting")  # 'waiting', 'in_consultation', 'completed', 'skipped'
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)
    predicted_wait_time = db.Column(db.Integer, default=0)  # in minutes
    
    patient = db.relationship('User', foreign_keys=[patient_id], backref=db.backref('queue_entries_as_patient', cascade='all, delete'))
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref=db.backref('queue_entries_as_doctor', cascade='all, delete'))
    appointment = db.relationship('Appointment', backref=db.backref('queue_entry', uselist=False))


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    extra_info = db.Column(db.String(255), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('notifications', cascade='all, delete-orphan', order_by='desc(Notification.created_at)'))

    def to_dict(self):
        now = datetime.utcnow()
        diff = (now - self.created_at).total_seconds()
        if diff < 60:
            time_ago = "Just now"
        elif diff < 3600:
            mins = max(1, int(diff // 60))
            time_ago = f"{mins} min{'s' if mins > 1 else ''} ago"
        elif diff < 86400:
            hours = int(diff // 3600)
            time_ago = f"{hours} hr{'s' if hours > 1 else ''} ago"
        else:
            time_ago = self.created_at.strftime('%d %b, %I:%M %p')

        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'event_type': self.event_type,
            'is_read': self.is_read,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'time_ago': time_ago,
            'extra_info': self.extra_info
        }


class Consultation(db.Model):
    __tablename__ = 'consultations'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True)
    queue_entry_id = db.Column(db.Integer, db.ForeignKey('queue_entries.id', ondelete='SET NULL'), nullable=True)

    # Clinical Consultation Fields
    symptoms = db.Column(db.Text, nullable=True)
    diagnosis = db.Column(db.Text, nullable=True)
    prescription = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    follow_up_date = db.Column(db.Date, nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    doctor = db.relationship('User', foreign_keys=[doctor_id], backref=db.backref('consultations_as_doctor', cascade='all, delete'))
    patient = db.relationship('User', foreign_keys=[patient_id], backref=db.backref('consultations_as_patient', cascade='all, delete'))
    appointment = db.relationship('Appointment', backref=db.backref('consultation', uselist=False))
    queue_entry = db.relationship('QueueEntry', backref=db.backref('consultation', uselist=False))


