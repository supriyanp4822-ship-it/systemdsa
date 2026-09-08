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

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(20), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id', ondelete='SET NULL'), nullable=True)
    queue_entry_id = db.Column(db.Integer, db.ForeignKey('queue_entries.id', ondelete='SET NULL'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False) # Cash, UPI, Card
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='paid')

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
