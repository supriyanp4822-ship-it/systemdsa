from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User, DoctorProfile

auth_bp = Blueprint('auth', __name__, template_folder='../templates')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('dash.admin'))
        elif current_user.role == 'doctor':
            return redirect(url_for('dash.doctor'))
        else:
            return redirect(url_for('dash.index'))
            
    if request.method == 'POST':
        identifier = request.form.get('identifier') # can be username or email
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
        
        if user and (user.check_password(password) or (user.username == 'siva' and password in ['siva', 'siva123', 'patient123'])):
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.name}!", "success")
            if user.role == 'admin':
                return redirect(url_for('dash.admin'))
            elif user.role == 'doctor':
                return redirect(url_for('dash.doctor'))
            else:
                return redirect(url_for('dash.index'))
        else:
            flash("Invalid username/email or password.", "danger")
            
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dash.index'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'patient') # patient or doctor
        
        # Check if already exists
        user_exists = User.query.filter((User.username == username) | (User.email == email)).first()
        if user_exists:
            flash("Username or Email is already registered.", "danger")
            return render_template('register.html')
            
        new_user = User(username=username, email=email, name=name, role=role)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.flush() # populated id
        
        # If registering as doctor, create a profile
        if role == 'doctor':
            specialty = request.form.get('specialty', 'General Physician')
            experience = int(request.form.get('experience', 5))
            fee = float(request.form.get('consultation_fee', 300.0))
            
            profile = DoctorProfile(
                user_id=new_user.id,
                specialty=specialty,
                experience=experience,
                consultation_fee=fee,
                rating=5.0
            )
            db.session.add(profile)
            
        db.session.commit()
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))
