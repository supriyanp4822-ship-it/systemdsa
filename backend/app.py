import os
from flask import Flask, render_template
from extensions import db, login_manager
from models import User, DoctorProfile, Appointment, QueueEntry, Department, Hospital, DoctorSchedule, District, Notification
from datetime import datetime, date
from pathlib import Path
from flask_cors import CORS

from config import config

BASE_DIR = Path(__file__).resolve().parent

def get_template_folder():
    candidates = [
        BASE_DIR.parent / 'frontend' / 'templates',
        BASE_DIR / 'frontend' / 'templates',
        BASE_DIR / 'templates',
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(BASE_DIR / 'templates')

def get_static_folder():
    candidates = [
        BASE_DIR.parent / 'frontend' / 'static',
        BASE_DIR / 'frontend' / 'static',
        BASE_DIR / 'static',
        BASE_DIR.parent / 'static'
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(BASE_DIR / 'static')

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    template_dir = get_template_folder()
    static_dir = get_static_folder()

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    CORS(app)

    app_config = config.get(config_name, config['default'])
    app.config.from_object(app_config)

    if hasattr(app_config, 'init_app'):
        app_config.init_app(app)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from routes.auth import auth_bp
    from routes.appointments import appt_bp
    from routes.dashboard import dash_bp
    from routes.queue import queue_bp
    from routes.admin import admin_bp
    from routes.payments import pay_bp
    from routes.doctor import doc_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(appt_bp, url_prefix='/appointments')
    app.register_blueprint(dash_bp, url_prefix='/dashboard')
    app.register_blueprint(doc_bp, url_prefix='/doctor')
    app.register_blueprint(queue_bp, url_prefix='/queue')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(pay_bp, url_prefix='/payment')

    @app.route("/")
    def home():
        # Get all doctors to show on landing page
        doctors = User.query.filter_by(role='doctor').all()
        return render_template("index.html", doctors=doctors)

    # Seed Database function
    with app.app_context():
        db.create_all()
        
        # Seed Departments
        if not Department.query.first():
            print("Seeding departments...")
            dept_names = ["Cardiology", "Neurology", "Orthopedics", "Pediatrics", "Emergency", "General Surgery", "Internal Medicine", "Radiology", "Obstetrics", "Oncology"]
            for name in dept_names:
                db.session.add(Department(name=name, description=f"{name} Department"))
            db.session.commit()

        # Seed Districts
        if not District.query.first():
            print("Seeding districts...")
            district_names = [
                "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore",
                "Dharmapuri", "Dindigul", "Erode", "Kallakurichi", "Kancheepuram",
                "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam",
                "Kanyakumari", "Namakkal", "Perambalur", "Pudukkottai",
                "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi",
                "Thanjavur", "Theni", "Tiruvallur", "Tiruvarur", "Thoothukudi",
                "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur",
                "Tiruvannamalai", "The Nilgiris", "Vellore", "Viluppuram",
                "Virudhunagar"
            ]
            for name in district_names:
                db.session.add(District(name=name))
            db.session.commit()

        # Seed Hospitals
        hospitals_to_seed = [
            ("PSG Hospitals", "Coimbatore", "Peelamedu, Coimbatore, Tamil Nadu 641004", "0422-2570170", 11.0228, 76.9681),
            ("Kovai Medical Center (KMCH)", "Coimbatore", "Avanashi Road, Coimbatore, Tamil Nadu 641014", "0422-4323800", 11.0300, 77.0020),
            ("Sri Ramakrishna Hospital", "Coimbatore", "395, Sarojini Naidu Rd, Coimbatore 641044", "0422-4500000", 11.0043, 76.9616),
            ("G. Kuppuswamy Naidu Memorial Hospital (GKNM)", "Coimbatore", "Pappanaickenpalayam, Coimbatore 641037", "0422-2213501", 11.0050, 76.9550),
            ("Royal Care Super Speciality Hospital", "Coimbatore", "Neelambur, Coimbatore 641062", "0422-2227000", 11.0225, 77.0024),
            ("Apollo Children's Hospital", "Chennai", "15, Shafee Mohammed Rd, Thousand Lights West, Chennai 600006", "044-28296666", 13.0640, 80.2520),
            ("Madras Medical Mission", "Chennai", "4-A, Dr. J. J. Nagar, Mogappair, Chennai 600037", "044-26565961", 13.0850, 80.1850),
            ("Meenakshi Mission Hospital", "Madurai", "Lake Area, Melur Road, Madurai 625107", "0452-2588741", 9.9530, 78.1480),
            ("Manipal Hospital", "Salem", "Dalmia Board, Salem 636012", "0427-2346600", 11.6643, 78.1460),
            ("Government Dharmapuri Medical College Hospital", "Dharmapuri", "Near Netaji Bye Pass Road, Dharmapuri 636701", "04342-233033", 12.1332, 78.1587),
            ("Dharmapuri District Head Quarters Hospital", "Dharmapuri", "Collectorate Road, Dharmapuri 636701", "04342-233011", 12.1250, 78.1550),
            ("Kauvery Hospital", "Tiruchirappalli", "Tennur, Tiruchirappalli 620017", "0431-4077777", 10.8220, 78.6850),
            ("Galaxy Hospital", "Tirunelveli", "Palayamkottai, Tirunelveli 627002", "0462-2502255", 8.7130, 77.7280),
            ("Christian Medical College (CMC)", "Vellore", "Ida Scudder Road, Vellore 632004", "0416-2281000", 12.9230, 79.1350)
        ]

        for name, dist_name, addr, phone, lat, lng in hospitals_to_seed:
            if not Hospital.query.filter_by(name=name).first():
                dist = District.query.filter_by(name=dist_name).first()
                if dist:
                    db.session.add(Hospital(name=name, district_id=dist.id, address=addr, phone=phone, latitude=lat, longitude=lng))
        db.session.commit()

        # Check if database is already seeded
        if not User.query.filter_by(role='admin').first():
            print("Seeding database...")
            
            # 1. Seed Admin
            admin = User(username='admin', email='admin@hospital.com', role='admin', name='System Administrator')
            admin.set_password('admin123')
            db.session.add(admin)
            
            # 2. Seed Patient
            patient = User(username='patient', email='patient@example.com', role='patient', name='John Doe')
            patient.set_password('patient123')
            db.session.add(patient)
            
            # Doctors placed at real Coimbatore hospital locations
            doctor_data = [
                # Coimbatore
                ('drsmith', 'smith@hospital.com', 'Dr. John Smith', 'Cardiology', 15, 600.0, 4.8, 11.0228, 76.9681, "PSG Hospitals", "A-101"),
                ('drwilson', 'wilson@hospital.com', 'Dr. Sarah Wilson', 'Neurology', 10, 550.0, 4.9, 11.0300, 77.0020, "Kovai Medical Center (KMCH)", "B-202"),
                ('drlee', 'lee@hospital.com', 'Dr. David Lee', 'Orthopedics', 12, 500.0, 4.7, 11.0043, 76.9616, "Sri Ramakrishna Hospital", "C-303"),
                ('drdavis', 'davis@hospital.com', 'Dr. Emily Davis', 'Pediatrics', 8, 450.0, 4.9, 11.0050, 76.9550, "G. Kuppuswamy Naidu Memorial Hospital (GKNM)", "D-404"),
                ('drarun', 'arun@hospital.com', 'Dr. Arun Prasad', 'General Surgery', 11, 500.0, 4.8, 11.0225, 77.0024, "Royal Care Super Speciality Hospital", "R-105"),
                
                # Dharmapuri
                ('drrajesh', 'rajesh@hospital.com', 'Dr. Rajesh Kumar', 'Internal Medicine', 12, 400.0, 4.8, 12.1250, 78.1550, "Dharmapuri District Head Quarters Hospital", "Cabin 101"),
                ('drmeena', 'meena@hospital.com', 'Dr. Meena Selvam', 'Cardiology', 9, 500.0, 4.9, 12.1250, 78.1550, "Dharmapuri District Head Quarters Hospital", "Cabin 102"),
                ('drsuresh', 'suresh@hospital.com', 'Dr. Suresh Babu', 'Pediatrics', 7, 350.0, 4.7, 12.1250, 78.1550, "Dharmapuri District Head Quarters Hospital", "Cabin 103"),
                ('drsenthil', 'senthil@hospital.com', 'Dr. K. Senthil', 'Orthopedics', 14, 400.0, 4.8, 12.1332, 78.1587, "Government Dharmapuri Medical College Hospital", "OPD-2"),
                
                # Chennai
                ('drlakshmi', 'lakshmi@hospital.com', 'Dr. Lakshmi Narayanan', 'Pediatrics', 15, 650.0, 4.9, 13.0640, 80.2520, "Apollo Children's Hospital", "Room 201"),
                ('drbalaji', 'balaji@hospital.com', 'Dr. V. Balaji', 'Cardiology', 16, 700.0, 4.9, 13.0850, 80.1850, "Madras Medical Mission", "Room 305"),
                
                # Madurai
                ('drramanathan', 'ramanathan@hospital.com', 'Dr. R. Ramanathan', 'Neurology', 13, 500.0, 4.8, 9.9530, 78.1480, "Meenakshi Mission Hospital", "Room N-12"),
                
                # Salem
                ('drkavitha', 'kavitha@hospital.com', 'Dr. S. Kavitha', 'Internal Medicine', 10, 450.0, 4.7, 11.6643, 78.1460, "Manipal Hospital", "Room 108"),
                
                # Tiruchirappalli
                ('drkarthik', 'karthik@hospital.com', 'Dr. M. Karthik', 'Orthopedics', 8, 500.0, 4.8, 10.8220, 78.6850, "Kauvery Hospital", "Room O-4"),
                
                # Tirunelveli
                ('drvignesh', 'vignesh@hospital.com', 'Dr. N. Vignesh', 'General Surgery', 9, 450.0, 4.7, 8.7130, 77.7280, "Galaxy Hospital", "Room G-2"),
                
                # Vellore
                ('drgrace', 'grace@hospital.com', 'Dr. Grace Thomas', 'Cardiology', 18, 600.0, 5.0, 12.9230, 79.1350, "Christian Medical College (CMC)", "CMC-101")
            ]
            
            for username, email, name, specialty, experience, fee, rating, lat, lng, hosp_name, room in doctor_data:
                doc_user = User(username=username, email=email, role='doctor', name=name)
                doc_user.set_password('doctor123')
                db.session.add(doc_user)
                db.session.flush() # Populate doc_user.id

                hosp = Hospital.query.filter_by(name=hosp_name).first()

                profile = DoctorProfile(
                    user_id=doc_user.id,
                    hospital_id=hosp.id if hosp else None,
                    specialty=specialty,
                    experience=experience,
                    consultation_fee=fee,
                    rating=rating,
                    latitude=lat,
                    longitude=lng,
                    room_number=room
                )
                db.session.add(profile)
                db.session.flush()

                # Add default schedule
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                for day in days:
                    db.session.add(DoctorSchedule(doctor_profile_id=profile.id, day_of_week=day))


            # 4. Seed Extra Patients
            patients_data = [
                ('alice', 'alice@example.com', 'Alice Smith'),
                ('bob', 'bob@example.com', 'Bob Johnson'),
                ('charlie', 'charlie@example.com', 'Charlie Brown'),
                ('diana', 'diana@example.com', 'Diana Prince'),
                ('siva', 'siva@example.com', 'Siva')
            ]
            patients = {}
            for username, email, name in patients_data:
                p_user = User(username=username, email=email, role='patient', name=name)
                p_user.set_password('patient123')
                db.session.add(p_user)
                db.session.flush()
                patients[username] = p_user
            
            # Fetch drsmith and drwilson for setting up queues
            dr_smith = User.query.filter_by(username='drsmith').first()
            dr_wilson = User.query.filter_by(username='drwilson').first()
            
            if dr_smith and dr_wilson:
                # Alice - in consultation with Dr. Smith
                appt_alice = Appointment(patient_id=patients['alice'].id, doctor_id=dr_smith.id, date=date.today(), time_slot='09:30 AM', status='paid')
                db.session.add(appt_alice)
                db.session.flush()
                q_alice = QueueEntry(patient_id=patients['alice'].id, doctor_id=dr_smith.id, appointment_id=appt_alice.id, position=1, status='in_consultation')
                db.session.add(q_alice)
                
                # Bob - waiting for Dr. Smith
                appt_bob = Appointment(patient_id=patients['bob'].id, doctor_id=dr_smith.id, date=date.today(), time_slot='10:00 AM', status='paid')
                db.session.add(appt_bob)
                db.session.flush()
                q_bob = QueueEntry(patient_id=patients['bob'].id, doctor_id=dr_smith.id, appointment_id=appt_bob.id, position=1, status='waiting', predicted_wait_time=15)
                db.session.add(q_bob)
                
                # Charlie - waiting for Dr. Smith
                appt_charlie = Appointment(patient_id=patients['charlie'].id, doctor_id=dr_smith.id, date=date.today(), time_slot='10:30 AM', status='paid')
                db.session.add(appt_charlie)
                db.session.flush()
                q_charlie = QueueEntry(patient_id=patients['charlie'].id, doctor_id=dr_smith.id, appointment_id=appt_charlie.id, position=2, status='waiting', predicted_wait_time=30)
                db.session.add(q_charlie)
                
                # Diana - in consultation with Dr. Wilson
                appt_diana = Appointment(patient_id=patients['diana'].id, doctor_id=dr_wilson.id, date=date.today(), time_slot='09:45 AM', status='paid')
                db.session.add(appt_diana)
                db.session.flush()
                q_diana = QueueEntry(patient_id=patients['diana'].id, doctor_id=dr_wilson.id, appointment_id=appt_diana.id, position=1, status='in_consultation')
                db.session.add(q_diana)
                
                # John Doe (default patient) - waiting for Dr. Wilson
                patient_john = User.query.filter_by(username='patient').first()
                if patient_john:
                    appt_john = Appointment(patient_id=patient_john.id, doctor_id=dr_wilson.id, date=date.today(), time_slot='10:15 AM', status='paid')
                    db.session.add(appt_john)
                    db.session.flush()
                    q_john = QueueEntry(patient_id=patient_john.id, doctor_id=dr_wilson.id, appointment_id=appt_john.id, position=1, status='waiting', predicted_wait_time=20)
                    db.session.add(q_john)
                
            db.session.commit()
            print("Database seeded successfully.")
            
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)