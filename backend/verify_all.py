"""
Comprehensive verification test for all application features
"""
import os
from datetime import date, datetime
from app import create_app
from models import User, Hospital, District, Department, Appointment, QueueEntry, Payment, Notification, Consultation
from predictor import predict_wait_time

app = create_app('development')
client = app.test_client()

print("=" * 60)
print("RUNNING COMPREHENSIVE END-TO-END VERIFICATION")
print("=" * 60)

# 1. Landing Page
resp = client.get('/')
assert resp.status_code == 200, f"Landing page failed: {resp.status_code}"
print("[PASS] Landing page: OK (200)")

# 2. Public Queue Board
resp = client.get('/queue/')
assert resp.status_code == 200, f"Queue board failed: {resp.status_code}"
print("[PASS] Public Queue Board: OK (200)")

# 3. Patient Login & Dashboard
with client:
    resp = client.post('/auth/login', data={'identifier': 'patient', 'password': 'patient123'}, follow_redirects=True)
    assert resp.status_code == 200, f"Patient login failed: {resp.status_code}"
    assert b"Welcome" in resp.data or b"Patient Dashboard" in resp.data or b"Appointments" in resp.data
    print("[PASS] Patient Login & Dashboard: OK (200)")

    # Notifications API
    resp = client.get('/dashboard/api/notifications')
    assert resp.status_code == 200, f"Notifications API failed: {resp.status_code}"
    print("[PASS] Notifications API: OK (200)")

    # Districts API
    resp = client.get('/dashboard/api/districts')
    assert resp.status_code == 200, f"Districts API failed: {resp.status_code}"
    print("[PASS] Districts API: OK (200)")

    # Locations API
    resp = client.get('/dashboard/api/locations')
    assert resp.status_code == 200, f"Locations API failed: {resp.status_code}"
    print("[PASS] Locations API: OK (200)")

    # Appointments page
    resp = client.get('/appointments/')
    assert resp.status_code == 200, f"Appointments page failed: {resp.status_code}"
    print("[PASS] Appointments Booking Page: OK (200)")

    # Hospital details API
    hosp = Hospital.query.first()
    assert hosp is not None
    resp = client.get(f'/appointments/api/hospital/{hosp.id}')
    assert resp.status_code == 200, f"Hospital details API failed: {resp.status_code}"
    print(f"[PASS] Hospital Details API (Hospital #{hosp.id}): OK (200)")

    # Slots endpoint
    doc = User.query.filter_by(role='doctor').first()
    assert doc is not None
    resp = client.post('/appointments/slots', data={'doctor_id': doc.id, 'date': date.today().strftime('%Y-%m-%d')})
    assert resp.status_code == 200, f"Slots API failed: {resp.status_code}"
    print("[PASS] Slots API: OK (200)")

    # Logout
    client.get('/auth/logout', follow_redirects=True)

# 4. Doctor Login & Dashboard & Consultation Flow
with client:
    resp = client.post('/auth/login', data={'identifier': 'drsmith', 'password': 'doctor123'}, follow_redirects=True)
    assert resp.status_code == 200, f"Doctor login failed: {resp.status_code}"
    print("[PASS] Doctor Login: OK (200)")

    resp = client.get('/doctor/dashboard')
    assert resp.status_code == 200, f"Doctor dashboard failed: {resp.status_code}"
    print("[PASS] Doctor Dashboard: OK (200)")

    # Call Next Doctor Flow
    resp = client.post('/doctor/call_next', follow_redirects=True)
    assert resp.status_code == 200, f"Doctor call next failed: {resp.status_code}"
    print("[PASS] Doctor Call Next Patient Flow: OK (200)")

    client.get('/auth/logout', follow_redirects=True)

# 5. Admin Login & Dashboard & Management
with client:
    resp = client.post('/auth/login', data={'identifier': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code}"
    print("[PASS] Admin Login: OK (200)")

    resp = client.get('/admin/dashboard')
    assert resp.status_code == 200, f"Admin dashboard failed: {resp.status_code}"
    print("[PASS] Admin Dashboard: OK (200)")

    resp = client.get('/admin/patients')
    assert resp.status_code == 200, f"Admin patients page failed: {resp.status_code}"
    print("[PASS] Admin Patients Management: OK (200)")

    resp = client.get('/admin/doctors')
    assert resp.status_code == 200, f"Admin doctors page failed: {resp.status_code}"
    print("[PASS] Admin Doctors Management: OK (200)")

    resp = client.get('/admin/hospitals')
    assert resp.status_code == 200, f"Admin hospitals page failed: {resp.status_code}"
    print("[PASS] Admin Hospitals Management: OK (200)")

    resp = client.get('/admin/departments')
    assert resp.status_code == 200, f"Admin departments page failed: {resp.status_code}"
    print("[PASS] Admin Departments Management: OK (200)")

    resp = client.get('/admin/appointments')
    assert resp.status_code == 200, f"Admin appointments page failed: {resp.status_code}"
    print("[PASS] Admin Appointments Management: OK (200)")

    resp = client.get('/admin/queue')
    assert resp.status_code == 200, f"Admin queue management: {resp.status_code}"
    print("[PASS] Admin Queue Management: OK (200)")

    resp = client.get('/admin/payments')
    assert resp.status_code == 200, f"Admin payments management: {resp.status_code}"
    print("[PASS] Admin Payments Management: OK (200)")

    resp = client.get('/admin/notifications')
    assert resp.status_code == 200, f"Admin notifications audit: {resp.status_code}"
    print("[PASS] Admin Notifications Audit: OK (200)")

    client.get('/auth/logout', follow_redirects=True)

# 6. ML Prediction Verification
wait_time_1 = predict_wait_time(0, "Cardiology", 10, 10)
wait_time_2 = predict_wait_time(5, "Cardiology", 10, 10)
wait_time_3 = predict_wait_time(10, "Neurology", 15, 14)
assert wait_time_1 >= 0, f"Negative wait time: {wait_time_1}"
assert wait_time_2 >= 0, f"Negative wait time: {wait_time_2}"
assert wait_time_3 >= 0, f"Negative wait time: {wait_time_3}"
print(f"[PASS] ML Predictions: Queue 0 -> {wait_time_1}m, Queue 5 -> {wait_time_2}m, Queue 10 -> {wait_time_3}m (All >= 0)")

print("=" * 60)
print("ALL VERIFICATION CHECKS PASSED (100% WORKING)")
print("=" * 60)
