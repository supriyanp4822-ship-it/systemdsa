"""
MongoDB Atlas Models for Hospital Queue Management System.
Replaces Flask-SQLAlchemy with a native PyMongo model layer.
"""
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from database import db, MongoMeta, MongoQuery, FieldExpr


class MongoModelBase(metaclass=MongoMeta):
    __tablename__ = 'base'

    def __init__(self, **kwargs):
        self._initialized = False
        self.id = kwargs.get('id')
        for k, v in kwargs.items():
            setattr(self, k, v)
        self._initialized = True

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if hasattr(self, '_initialized') and self._initialized and not key.startswith('_'):
            db.session.add(self)

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, self.__class__):
            return False
        if self.id is None or other.id is None:
            return False
        return self.id == other.id

    def __hash__(self):
        if self.id is not None:
            return hash((self.__class__, self.id))
        return id(self)

    def _to_doc(self):
        doc = {}
        for k, v in self.__dict__.items():
            if not k.startswith('_'):
                if isinstance(v, date) and not isinstance(v, datetime):
                    doc[k] = v.strftime('%Y-%m-%d')
                else:
                    doc[k] = v
        return doc

    @classmethod
    def _from_doc(cls, doc):
        if doc is None:
            return None
        data = dict(doc)
        data.pop('_id', None)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data):
        if data is None:
            return None
        d = dict(data)
        datetime_fields = {'created_at', 'payment_date', 'check_in_time', 'started_at', 'completed_at', 'verified_at'}
        date_fields = {'date', 'follow_up_date'}
        for field in datetime_fields:
            if field in d and isinstance(d[field], str):
                try:
                    val_str = d[field].replace('T', ' ')
                    if '.' in val_str:
                        val_str = val_str.split('.')[0]
                    d[field] = datetime.strptime(val_str[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
        for field in date_fields:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = datetime.strptime(d[field][:10], '%Y-%m-%d').date()
                except Exception:
                    pass
        return cls(**d)

    def _save(self, engine):
        col_name = self.__tablename__
        if not self.id:
            self.id = engine.get_next_id(col_name)

        doc = self._to_doc()
        if engine.is_connected and engine.db is not None:
            engine.db[col_name].replace_one({'id': self.id}, doc, upsert=True)
        else:
            items = engine._memory_store.setdefault(col_name, [])
            for i, it in enumerate(items):
                if it.get('id') == self.id:
                    items[i] = doc
                    return
            items.append(doc)

    def _delete(self, engine):
        if not self.id:
            return
        col_name = self.__tablename__
        if engine.is_connected and engine.db is not None:
            engine.db[col_name].delete_one({'id': self.id})
        else:
            items = engine._memory_store.get(col_name, [])
            engine._memory_store[col_name] = [it for it in items if it.get('id') != self.id]


class User(UserMixin, MongoModelBase):
    __tablename__ = 'users'

    id = FieldExpr(None, 'id')
    username = FieldExpr(None, 'username')
    email = FieldExpr(None, 'email')
    password_hash = FieldExpr(None, 'password_hash')
    role = FieldExpr(None, 'role')
    name = FieldExpr(None, 'name')
    phone = FieldExpr(None, 'phone')
    is_active_user = FieldExpr(None, 'is_active_user')
    created_at = FieldExpr(None, 'created_at')

    def __init__(self, **kwargs):
        kwargs.setdefault('is_active_user', True)
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def is_active(self):
        return bool(getattr(self, 'is_active_user', True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def doctor_profile(self):
        return DoctorProfile.query.filter_by(user_id=self.id).first()

    @property
    def appointments_as_patient(self):
        return Appointment.query.filter_by(patient_id=self.id).all()

    @property
    def appointments_as_doctor(self):
        return Appointment.query.filter_by(doctor_id=self.id).all()

    @property
    def payments_as_patient(self):
        return Payment.query.filter_by(patient_id=self.id).all()

    @property
    def payments_as_doctor(self):
        return Payment.query.filter_by(doctor_id=self.id).all()

    @property
    def queue_entries_as_patient(self):
        return QueueEntry.query.filter_by(patient_id=self.id).all()

    @property
    def queue_entries_as_doctor(self):
        return QueueEntry.query.filter_by(doctor_id=self.id).all()

    @property
    def notifications(self):
        return Notification.query.filter_by(user_id=self.id).order_by(Notification.created_at.desc()).all()

    @property
    def consultations_as_doctor(self):
        return Consultation.query.filter_by(doctor_id=self.id).all()

    @property
    def consultations_as_patient(self):
        return Consultation.query.filter_by(patient_id=self.id).all()


class District(MongoModelBase):
    __tablename__ = 'districts'

    id = FieldExpr(None, 'id')
    name = FieldExpr(None, 'name')

    @property
    def hospitals(self):
        return Hospital.query.filter_by(district_id=self.id).all()


class Hospital(MongoModelBase):
    __tablename__ = 'hospitals'

    id = FieldExpr(None, 'id')
    name = FieldExpr(None, 'name')
    district_id = FieldExpr(None, 'district_id')
    address = FieldExpr(None, 'address')
    phone = FieldExpr(None, 'phone')
    latitude = FieldExpr(None, 'latitude')
    longitude = FieldExpr(None, 'longitude')
    opening_time = FieldExpr(None, 'opening_time')
    closing_time = FieldExpr(None, 'closing_time')
    is_active = FieldExpr(None, 'is_active')

    def __init__(self, **kwargs):
        kwargs.setdefault('opening_time', '09:00')
        kwargs.setdefault('closing_time', '21:00')
        kwargs.setdefault('is_active', True)
        super().__init__(**kwargs)

    @property
    def district(self):
        return District.query.get(self.district_id)

    @property
    def doctors(self):
        return DoctorProfile.query.filter_by(hospital_id=self.id).all()


class DoctorProfile(MongoModelBase):
    __tablename__ = 'doctor_profiles'

    id = FieldExpr(None, 'id')
    user_id = FieldExpr(None, 'user_id')
    hospital_id = FieldExpr(None, 'hospital_id')
    specialty = FieldExpr(None, 'specialty')
    experience = FieldExpr(None, 'experience')
    consultation_fee = FieldExpr(None, 'consultation_fee')
    rating = FieldExpr(None, 'rating')
    latitude = FieldExpr(None, 'latitude')
    longitude = FieldExpr(None, 'longitude')
    room_number = FieldExpr(None, 'room_number')
    available_from = FieldExpr(None, 'available_from')
    available_to = FieldExpr(None, 'available_to')

    def __init__(self, **kwargs):
        kwargs.setdefault('experience', 5)
        kwargs.setdefault('consultation_fee', 500.0)
        kwargs.setdefault('rating', 5.0)
        kwargs.setdefault('available_from', '09:00')
        kwargs.setdefault('available_to', '17:00')
        super().__init__(**kwargs)

    @property
    def user(self):
        return User.query.get(self.user_id)

    @property
    def hospital(self):
        return Hospital.query.get(self.hospital_id) if self.hospital_id else None

    @property
    def schedules(self):
        return DoctorSchedule.query.filter_by(doctor_profile_id=self.id).all()


class DoctorSchedule(MongoModelBase):
    __tablename__ = 'doctor_schedules'

    id = FieldExpr(None, 'id')
    doctor_profile_id = FieldExpr(None, 'doctor_profile_id')
    day_of_week = FieldExpr(None, 'day_of_week')
    start_time = FieldExpr(None, 'start_time')
    end_time = FieldExpr(None, 'end_time')

    def __init__(self, **kwargs):
        kwargs.setdefault('start_time', '09:00')
        kwargs.setdefault('end_time', '17:00')
        super().__init__(**kwargs)

    @property
    def profile(self):
        return DoctorProfile.query.get(self.doctor_profile_id)


class Appointment(MongoModelBase):
    __tablename__ = 'appointments'

    id = FieldExpr(None, 'id')
    patient_id = FieldExpr(None, 'patient_id')
    doctor_id = FieldExpr(None, 'doctor_id')
    date = FieldExpr(None, 'date')
    time_slot = FieldExpr(None, 'time_slot')
    status = FieldExpr(None, 'status')

    def __init__(self, **kwargs):
        kwargs.setdefault('status', 'scheduled')
        # Parse date if string
        d = kwargs.get('date')
        if isinstance(d, str):
            try:
                kwargs['date'] = datetime.strptime(d[:10], '%Y-%m-%d').date()
            except Exception:
                pass
        super().__init__(**kwargs)

    @property
    def patient(self):
        return User.query.get(self.patient_id)

    @property
    def doctor(self):
        return User.query.get(self.doctor_id)

    @property
    def payment(self):
        return Payment.query.filter_by(appointment_id=self.id).first()

    @property
    def queue_entry(self):
        return QueueEntry.query.filter_by(appointment_id=self.id).first()

    @property
    def consultation(self):
        return Consultation.query.filter_by(appointment_id=self.id).first()


class Department(MongoModelBase):
    __tablename__ = 'departments'

    id = FieldExpr(None, 'id')
    name = FieldExpr(None, 'name')
    description = FieldExpr(None, 'description')
    is_active = FieldExpr(None, 'is_active')

    def __init__(self, **kwargs):
        kwargs.setdefault('is_active', True)
        super().__init__(**kwargs)


class Payment(MongoModelBase):
    __tablename__ = 'payments'

    id = FieldExpr(None, 'id')
    receipt_no = FieldExpr(None, 'receipt_no')
    transaction_id = FieldExpr(None, 'transaction_id')
    patient_id = FieldExpr(None, 'patient_id')
    doctor_id = FieldExpr(None, 'doctor_id')
    appointment_id = FieldExpr(None, 'appointment_id')
    queue_entry_id = FieldExpr(None, 'queue_entry_id')
    amount = FieldExpr(None, 'amount')
    payment_method = FieldExpr(None, 'payment_method')
    upi_id = FieldExpr(None, 'upi_id')
    upi_ref_no = FieldExpr(None, 'upi_ref_no')
    payment_date = FieldExpr(None, 'payment_date')
    verified_at = FieldExpr(None, 'verified_at')
    status = FieldExpr(None, 'status')

    def __init__(self, **kwargs):
        kwargs.setdefault('payment_date', datetime.utcnow())
        kwargs.setdefault('status', 'paid')
        super().__init__(**kwargs)

    @property
    def patient(self):
        return User.query.get(self.patient_id)

    @property
    def doctor(self):
        return User.query.get(self.doctor_id)

    @property
    def appointment(self):
        return Appointment.query.get(self.appointment_id) if self.appointment_id else None


class QueueEntry(MongoModelBase):
    __tablename__ = 'queue_entries'

    id = FieldExpr(None, 'id')
    patient_id = FieldExpr(None, 'patient_id')
    doctor_id = FieldExpr(None, 'doctor_id')
    appointment_id = FieldExpr(None, 'appointment_id')
    position = FieldExpr(None, 'position')
    status = FieldExpr(None, 'status')
    check_in_time = FieldExpr(None, 'check_in_time')
    predicted_wait_time = FieldExpr(None, 'predicted_wait_time')

    def __init__(self, **kwargs):
        kwargs.setdefault('status', 'waiting')
        kwargs.setdefault('check_in_time', datetime.utcnow())
        kwargs.setdefault('predicted_wait_time', 0)
        super().__init__(**kwargs)

    @property
    def patient(self):
        return User.query.get(self.patient_id)

    @property
    def doctor(self):
        return User.query.get(self.doctor_id)

    @property
    def appointment(self):
        return Appointment.query.get(self.appointment_id) if self.appointment_id else None

    @property
    def consultation(self):
        return Consultation.query.filter_by(queue_entry_id=self.id).first()


class Notification(MongoModelBase):
    __tablename__ = 'notifications'

    id = FieldExpr(None, 'id')
    user_id = FieldExpr(None, 'user_id')
    title = FieldExpr(None, 'title')
    message = FieldExpr(None, 'message')
    event_type = FieldExpr(None, 'event_type')
    is_read = FieldExpr(None, 'is_read')
    created_at = FieldExpr(None, 'created_at')
    extra_info = FieldExpr(None, 'extra_info')

    def __init__(self, **kwargs):
        kwargs.setdefault('is_read', False)
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def user(self):
        return User.query.get(self.user_id)

    def to_dict(self):
        now = datetime.utcnow()
        created = self.created_at if isinstance(self.created_at, datetime) else datetime.utcnow()
        diff = (now - created).total_seconds()
        if diff < 60:
            time_ago = "Just now"
        elif diff < 3600:
            mins = max(1, int(diff // 60))
            time_ago = f"{mins} min{'s' if mins > 1 else ''} ago"
        elif diff < 86400:
            hours = int(diff // 3600)
            time_ago = f"{hours} hr{'s' if hours > 1 else ''} ago"
        else:
            time_ago = created.strftime('%d %b, %I:%M %p')

        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'event_type': self.event_type,
            'is_read': self.is_read,
            'created_at': created.strftime('%Y-%m-%d %H:%M:%S'),
            'time_ago': time_ago,
            'extra_info': self.extra_info
        }


class Consultation(MongoModelBase):
    __tablename__ = 'consultations'

    id = FieldExpr(None, 'id')
    doctor_id = FieldExpr(None, 'doctor_id')
    patient_id = FieldExpr(None, 'patient_id')
    appointment_id = FieldExpr(None, 'appointment_id')
    queue_entry_id = FieldExpr(None, 'queue_entry_id')
    symptoms = FieldExpr(None, 'symptoms')
    diagnosis = FieldExpr(None, 'diagnosis')
    prescription = FieldExpr(None, 'prescription')
    notes = FieldExpr(None, 'notes')
    follow_up_date = FieldExpr(None, 'follow_up_date')
    started_at = FieldExpr(None, 'started_at')
    completed_at = FieldExpr(None, 'completed_at')
    created_at = FieldExpr(None, 'created_at')

    def __init__(self, **kwargs):
        kwargs.setdefault('started_at', datetime.utcnow())
        kwargs.setdefault('created_at', datetime.utcnow())
        super().__init__(**kwargs)

    @property
    def doctor(self):
        return User.query.get(self.doctor_id)

    @property
    def patient(self):
        return User.query.get(self.patient_id)

    @property
    def appointment(self):
        return Appointment.query.get(self.appointment_id) if self.appointment_id else None

    @property
    def queue_entry(self):
        return QueueEntry.query.get(self.queue_entry_id) if self.queue_entry_id else None
