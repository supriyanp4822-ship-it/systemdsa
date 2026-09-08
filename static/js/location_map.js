// static/js/location_map.js — Enhanced with Explorer Panel & Tamil Nadu flow

document.addEventListener('DOMContentLoaded', function () {
  /* ─────────────────────────────────────
     MAP SETUP (Tamil Nadu Focus)
  ───────────────────────────────────── */
  const tnCenter = [11.1271, 78.6569];
  const map = L.map('map').setView(tnCenter, 7); // Zoom 7 to see whole state

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map);

  map.on('mousemove', function (e) {
    document.getElementById('coordText').textContent =
      `Lat: ${e.latlng.lat.toFixed(4)}, Lng: ${e.latlng.lng.toFixed(4)}`;
  });

  /* ─────────────────────────────────────
     ICONS & STATE
  ───────────────────────────────────── */
  const hospitalIcon = L.divIcon({
    className: '',
    html: `<div class="map-marker hospital-marker"><i class="fa-solid fa-hospital"></i></div>`,
    iconSize: [40, 40], iconAnchor: [20, 40], popupAnchor: [0, -40]
  });

  const doctorIcon = L.divIcon({
    className: '',
    html: `<div class="map-marker doctor-marker"><i class="fa-solid fa-user-doctor"></i></div>`,
    iconSize: [36, 36], iconAnchor: [18, 36], popupAnchor: [0, -36]
  });

  let allMarkers = [];
  let traceLines = [];
  let locationData = [];
  let currentHospitalId = null;

  /* ─────────────────────────────────────
     TABS LOGIC
  ───────────────────────────────────── */
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  function switchTab(tabId) {
    tabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabId));
    tabContents.forEach(content => {
        if (content.id === `${tabId}Tab`) {
            content.classList.remove('hidden');
        } else if (tabId === 'doctors' && content.id === 'doctorsTab') {
             content.classList.remove('hidden');
        } else {
            content.classList.add('hidden');
        }
    });
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  /* ─────────────────────────────────────
     HOSPITAL & DISTRICT FLOW
  ───────────────────────────────────── */
  const districtFilter = document.getElementById('districtFilter');
  const hospitalList = document.getElementById('hospitalList');
  const hospitalSearch = document.getElementById('hospitalSearch');

  function loadExplorer() {
    const districtId = districtFilter.value;
    const url = districtId !== 'all' ? `/dashboard/api/locations?district_id=${districtId}` : '/dashboard/api/locations';

    fetch(url)
      .then(r => r.json())
      .then(data => {
        locationData = data.locations;
        renderHospitals();
        renderMarkers();

        // Debug message in dev mode
        const debugPanel = document.getElementById('debugPanel');
        if (data.debug && debugPanel) {
            debugPanel.classList.remove('hidden');
            debugPanel.innerHTML = `
                <span><strong>Selected:</strong> ${data.debug.selected_district_id || 'All'}</span>
                <span><strong>Found:</strong> ${data.debug.hospital_count} hospitals</span>
                <span><strong>Districts:</strong> ${data.debug.db_districts.slice(0, 5).join(", ")}...</span>
            `;
            console.log("Location Debug:", data.debug);
        } else if (debugPanel) {
            debugPanel.classList.add('hidden');
        }
      });
  }

  function renderHospitals() {
    const query = hospitalSearch.value.toLowerCase();
    const hospitals = locationData.filter(loc => loc.type === 'hospital');
    const filtered = hospitals.filter(h =>
        h.name.toLowerCase().includes(query) ||
        h.departments.some(d => d.toLowerCase().includes(query))
    );

    const countEl = document.getElementById('hospitalCount');
    if (countEl) countEl.textContent = `${filtered.length} Hospitals Found`;

    if (filtered.length === 0) {
        hospitalList.innerHTML = `<div class="token-empty"><p>No hospitals found matching your criteria.</p></div>`;
        return;
    }

    hospitalList.innerHTML = filtered.map(h => `
        <div class="hosp-card" data-id="${h.id}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <h4><i class="fa-solid fa-hospital"></i> ${h.name}</h4>
                <span class="hosp-status">🟢 OPEN NOW</span>
            </div>
            <div class="hosp-meta">
                <span><i class="fa-solid fa-location-dot"></i> ${h.address}</span>
                <span><i class="fa-solid fa-phone"></i> ${h.phone || 'N/A'}</span>
                <span style="color:var(--primary); font-weight:700;"><i class="fa-solid fa-user-md"></i> ${h.doctor_count} Doctors Available</span>
            </div>
            <div class="hosp-depts">
                ${h.departments.map(d => `<span class="dept-tag">${d}</span>`).join('')}
            </div>
            <div class="hosp-footer">
                <button class="btn btn-primary btn-block btn-sm btnViewDoctors" data-id="${h.id}">
                    View Available Doctors
                </button>
            </div>
        </div>
    `).join('');

    // Event listeners for cards
    document.querySelectorAll('.hosp-card').forEach(card => {
        card.addEventListener('click', function(e) {
            if (e.target.classList.contains('btnViewDoctors') || e.target.closest('.btnViewDoctors')) return;
            focusHospital(parseInt(this.dataset.id));
        });
    });

    document.querySelectorAll('.btnViewDoctors').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            showDoctorsForHospital(parseInt(this.dataset.id));
        });
    });
  }

  function renderMarkers() {
    allMarkers.forEach(m => map.removeLayer(m));
    allMarkers = [];

    locationData.forEach(loc => {
        const icon = loc.type === 'hospital' ? hospitalIcon : doctorIcon;
        const marker = L.marker([loc.lat, loc.lng], { icon }).addTo(map);

        let popupHtml = `<div class="map-popup"><div class="mp-title">${loc.name}</div>`;
        if (loc.type === 'hospital') {
            popupHtml += `<div class="mp-row">${loc.address}</div><button class="btn btn-primary btn-xs" onclick="window.focusHospital(${loc.id})">Details</button>`;
        } else {
            popupHtml += `<div class="mp-row">${loc.specialty}</div>`;
        }
        popupHtml += `</div>`;

        marker.bindPopup(popupHtml);
        marker.dataset = loc;
        allMarkers.push(marker);
    });

    if (allMarkers.length > 0 && districtFilter.value !== 'all') {
        const group = L.featureGroup(allMarkers);
        if (allMarkers.length === 1) {
            map.setView(allMarkers[0].getLatLng(), 14);
        } else {
            map.fitBounds(group.getBounds().pad(0.2));
        }
    } else if (districtFilter.value === 'all') {
        map.setView(tnCenter, 7);
    }
  }

  window.focusHospital = function(id) {
    const hosp = locationData.find(l => l.type === 'hospital' && l.id === id);
    if (!hosp) return;

    // Highlight card
    document.querySelectorAll('.hosp-card').forEach(c => c.classList.toggle('active', parseInt(c.dataset.id) === id));

    // Fly to map
    map.flyTo([hosp.lat, hosp.lng], 16);
    const marker = allMarkers.find(m => m.dataset.type === 'hospital' && m.dataset.id === id);
    if (marker) marker.openPopup();
  };

  /* ─────────────────────────────────────
     DOCTOR DRILL-DOWN
  ───────────────────────────────────── */
  const doctorsTab = document.getElementById('doctorsTab');
  const hospitalsTab = document.getElementById('hospitalsTab');
  const doctorList = document.getElementById('doctorList');
  const selectedHospitalName = document.getElementById('selectedHospitalName');
  const deptFilter = document.getElementById('deptFilter');

  function showDoctorsForHospital(id) {
    const hosp = locationData.find(l => l.type === 'hospital' && l.id === id);
    if (!hosp) return;

    currentHospitalId = id;
    selectedHospitalName.textContent = hosp.name;

    // Fill dept filter
    deptFilter.innerHTML = '<option value="all">All Departments</option>' +
        hosp.departments.map(d => `<option value="${d}">${d}</option>`).join('');

    // Fetch doctors from main data (in a real app, this might be a separate API call)
    // For now, we only show doctors that are associated with this hospital in the locationData
    renderDoctors();

    hospitalsTab.classList.add('hidden');
    doctorsTab.classList.remove('hidden');

    focusHospital(id);
  }

  function renderDoctors() {
    const dept = deptFilter.value;
    // Get doctors from global data that belong to this hospital
    const doctors = locationData.filter(loc => loc.type === 'doctor' && loc.hospital === selectedHospitalName.textContent);

    const filtered = dept === 'all' ? doctors : doctors.filter(d => d.specialty === dept);

    if (filtered.length === 0) {
        doctorList.innerHTML = `<div class="token-empty"><p>No doctors available for this selection.</p></div>`;
        return;
    }

    doctorList.innerHTML = filtered.map(d => `
        <div class="doc-item">
            <div class="doc-item-header">
                <div class="doc-item-name">${d.name}</div>
                <div class="doc-item-spec">${d.specialty}</div>
            </div>
            <div class="doc-item-meta">
                <span><i class="fa-solid fa-calendar-day"></i> Mon - Fri</span>
                <span><i class="fa-solid fa-clock"></i> 09:00 - 17:00</span>
                <span><i class="fa-solid fa-star"></i> ${d.rating} Rating</span>
                <span><i class="fa-solid fa-indian-rupee-sign"></i> ${d.fee} Fee</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="badge badge-success">Available</span>
                <a href="/appointments?doctor_id=${d.id}" class="btn btn-xs btn-primary">Book Now</a>
            </div>
        </div>
    `).join('');
  }

  document.getElementById('btnBackToHospitals').addEventListener('click', () => {
    doctorsTab.classList.add('hidden');
    hospitalsTab.classList.remove('hidden');
  });

  deptFilter.addEventListener('change', renderDoctors);
  districtFilter.addEventListener('change', loadExplorer);
  hospitalSearch.addEventListener('input', renderHospitals);

  const btnClearDistrict = document.getElementById('btnClearDistrict');
  if (btnClearDistrict) {
    btnClearDistrict.addEventListener('click', () => {
        districtFilter.value = 'all';
        loadExplorer();
    });
  }

  /* ─────────────────────────────────────
     TOKEN QUEUE LIST (Existing Logic)
  ───────────────────────────────────── */
  function loadTokenList() {
    fetch('/dashboard/api/queue-tokens')
      .then(r => r.json())
      .then(data => {
        renderTokenList(data.tokens);
        updateSummary(data.tokens);
      });
  }

  function renderTokenList(tokens) {
    const container = document.getElementById('tokenList');
    const search = document.getElementById('tokenSearch').value.toLowerCase();
    const filtered = tokens.filter(t => t.patient.toLowerCase().includes(search) || t.token.toLowerCase().includes(search));

    if (filtered.length === 0) {
      container.innerHTML = `<div class="token-empty"><p>No active tokens</p></div>`;
      return;
    }

    container.innerHTML = filtered.map(t => {
      const isConsulting = t.status === 'in_consultation';
      return `
        <div class="token-card ${isConsulting ? 'consulting' : 'waiting'}">
          <div class="token-number">${t.token}</div>
          <div class="token-info">
            <div class="token-patient">${t.patient}</div>
            <div class="token-doctor">${t.doctor}</div>
            <div class="token-meta">
                <span class="token-specialty">${t.specialty}</span>
                <span class="token-checkin"><i class="fa-regular fa-clock"></i> ${t.checkin_time}</span>
            </div>
          </div>
          <div class="token-right">
            <div class="token-pos">#${t.position}</div>
            <span class="token-badge ${isConsulting ? 'badge-consulting' : 'badge-waiting'}">
              ${isConsulting ? 'Consulting' : `${t.wait_time}m`}
            </span>
          </div>
        </div>`;
    }).join('');
  }

  function updateSummary(tokens) {
    const waiting = tokens.filter(t => t.status === 'waiting').length;
    const consulting = tokens.filter(t => t.status === 'in_consultation').length;
    const doctors = new Set(tokens.map(t => t.doctor)).size;
    document.getElementById('totalWaiting').textContent = waiting;
    document.getElementById('totalConsulting').textContent = consulting;
    document.getElementById('totalDoctors').textContent = doctors;
  }

  document.getElementById('tokenSearch').addEventListener('input', loadTokenList);

  /* ─────────────────────────────────────
     INIT
  ───────────────────────────────────── */
  loadExplorer();
  loadTokenList();
  setInterval(loadTokenList, 10000);

});
