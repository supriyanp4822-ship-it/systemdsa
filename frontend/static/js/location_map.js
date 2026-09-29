// static/js/location_map.js — High Performance Map & Route System (Optimized Initialization & Debouncing)

document.addEventListener('DOMContentLoaded', function () {

  /* ─────────────────────────────────────
     1. MAP INITIALIZATION (EXACTLY ONCE)
  ───────────────────────────────────── */
  const tnCenter = [11.1271, 78.6569];
  const mapContainer = document.getElementById('map');
  if (!mapContainer) return;

  // Initialize Leaflet map ONLY ONCE
  const map = L.map('map', {
    zoomControl: true,
    attributionControl: true
  }).setView(tnCenter, 7);

  // Add tile layer ONLY ONCE
  const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map);

  map.on('mousemove', function (e) {
    const coordEl = document.getElementById('coordText');
    if (coordEl) {
      coordEl.textContent = `Lat: ${e.latlng.lat.toFixed(4)}, Lng: ${e.latlng.lng.toFixed(4)}`;
    }
  });

  /* ─────────────────────────────────────
     2. ICONS & STATE MANAGEMENT
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

  const originIcon = L.divIcon({
    className: '',
    html: `<div class="map-marker origin-marker"><i class="fa-solid fa-location-crosshairs"></i></div>`,
    iconSize: [42, 42], iconAnchor: [21, 42], popupAnchor: [0, -42]
  });

  const destIcon = L.divIcon({
    className: '',
    html: `<div class="map-marker dest-marker"><i class="fa-solid fa-hospital-user"></i></div>`,
    iconSize: [42, 42], iconAnchor: [21, 42], popupAnchor: [0, -42]
  });

  // Reuse markers to prevent duplication & map DOM lag
  const markerMap = new Map(); // key -> L.Marker
  let traceLines = [];
  let locationData = [];
  let currentHospitalId = null;

  // Route state
  let routingControl = null;
  let originMarker = null;
  let originLatLng = null;  // { lat, lng, label }
  let destLatLng = null;    // { lat, lng, label }

  /* ─────────────────────────────────────
     3. DEBOUNCE UTILITY
  ───────────────────────────────────── */
  function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  /* ─────────────────────────────────────
     4. TABS LOGIC
  ───────────────────────────────────── */
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  function switchTab(tabId) {
    tabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabId));
    const tabMap = {
      hospitals: 'hospitalsTab',
      route: 'routeTab',
      queue: 'queueTab',
      doctors: 'doctorsTab'
    };
    tabContents.forEach(content => {
      content.classList.toggle('hidden', content.id !== tabMap[tabId]);
    });
    if (tabId === 'route' || tabId === 'hospitals') {
      setTimeout(() => map.invalidateSize(), 50);
    }
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  /* ─────────────────────────────────────
     5. EFFICIENT MARKER REUSE & RENDERING
  ───────────────────────────────────── */
  function renderMarkers() {
    const newKeys = new Set();

    locationData.forEach(loc => {
      const key = `${loc.type}_${loc.id}`;
      newKeys.add(key);

      let marker = markerMap.get(key);
      const icon = loc.type === 'hospital' ? hospitalIcon : doctorIcon;

      if (!marker) {
        // Create new marker ONLY if it does not already exist
        marker = L.marker([loc.lat, loc.lng], { icon }).addTo(map);
        marker._locData = loc;

        let popupHtml = `<div class="map-popup"><div class="mp-title">${loc.name}</div>`;
        if (loc.type === 'hospital') {
          popupHtml += `
            <div class="mp-row">${loc.address}</div>
            <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
              <button class="btn btn-primary btn-xs" onclick="window.focusHospital(${loc.id})">Details</button>
              <button class="btn btn-outline btn-xs" onclick="window.launchRouteToHospital(${loc.lat},${loc.lng},'${loc.name.replace(/'/g,"\\'")}')">
                <i class="fa-solid fa-route"></i> Directions
              </button>
            </div>`;
        } else {
          popupHtml += `<div class="mp-row">${loc.specialty}</div>`;
        }
        popupHtml += `</div>`;
        marker.bindPopup(popupHtml);
        markerMap.set(key, marker);
      } else {
        // Reuse existing marker and update position if needed
        marker.setLatLng([loc.lat, loc.lng]);
        marker._locData = loc;
      }
    });

    // Remove markers that are no longer present in locationData
    for (let [key, marker] of markerMap.entries()) {
      if (!newKeys.has(key)) {
        map.removeLayer(marker);
        markerMap.delete(key);
      }
    }

    // Adjust view smoothly
    const activeMarkers = Array.from(markerMap.values());
    if (activeMarkers.length > 0 && districtFilter.value !== 'all') {
      const group = L.featureGroup(activeMarkers);
      if (activeMarkers.length === 1) {
        map.setView(activeMarkers[0].getLatLng(), 14);
      } else {
        map.fitBounds(group.getBounds().pad(0.2));
      }
    } else if (districtFilter.value === 'all') {
      map.setView(tnCenter, 7);
    }
  }

  /* ─────────────────────────────────────
     6. EXPLORER & HOSPITAL DATA FETCHING
  ───────────────────────────────────── */
  const districtFilter = document.getElementById('districtFilter');
  const hospitalList = document.getElementById('hospitalList');
  const hospitalSearch = document.getElementById('hospitalSearch');

  function loadExplorer() {
    const districtId = districtFilter.value;
    const url = districtId !== 'all'
      ? `/dashboard/api/locations?district_id=${districtId}`
      : '/dashboard/api/locations';

    fetch(url)
      .then(r => r.json())
      .then(data => {
        locationData = data.locations || [];
        renderHospitals();
        renderMarkers();

        const debugPanel = document.getElementById('debugPanel');
        if (data.debug && debugPanel) {
          debugPanel.classList.remove('hidden');
          debugPanel.innerHTML = `
            <span><strong>Selected:</strong> ${data.debug.selected_district_id || 'All'}</span>
            <span><strong>Found:</strong> ${data.debug.hospital_count} hospitals</span>
          `;
        } else if (debugPanel) {
          debugPanel.classList.add('hidden');
        }
      })
      .catch(err => console.error("Error loading location data:", err));
  }

  function renderHospitals() {
    const query = hospitalSearch.value.trim().toLowerCase();
    const hospitals = locationData.filter(loc => loc.type === 'hospital');
    const filtered = hospitals.filter(h =>
      h.name.toLowerCase().includes(query) ||
      (h.departments && h.departments.some(d => d.toLowerCase().includes(query)))
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
          <span style="color:var(--primary); font-weight:700;">
            <i class="fa-solid fa-user-md"></i> ${h.doctor_count} Doctors Available
          </span>
        </div>
        <div class="hosp-depts">
          ${(h.departments || []).map(d => `<span class="dept-tag">${d}</span>`).join('')}
        </div>
        <div class="hosp-footer" style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-primary btn-block btn-sm btnViewDoctors" data-id="${h.id}">
            View Doctors
          </button>
          <button class="btn btn-outline btn-sm btnGetRoute"
            data-id="${h.id}"
            data-lat="${h.lat}"
            data-lng="${h.lng}"
            data-name="${h.name}">
            <i class="fa-solid fa-route"></i> Directions
          </button>
        </div>
      </div>
    `).join('');

    // Attach click events
    document.querySelectorAll('.hosp-card').forEach(card => {
      card.addEventListener('click', function (e) {
        if (e.target.closest('.btnViewDoctors') || e.target.closest('.btnGetRoute')) return;
        focusHospital(parseInt(this.dataset.id));
      });
    });

    document.querySelectorAll('.btnViewDoctors').forEach(btn => {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        showDoctorsForHospital(parseInt(this.dataset.id));
      });
    });

    document.querySelectorAll('.btnGetRoute').forEach(btn => {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        const lat = parseFloat(this.dataset.lat);
        const lng = parseFloat(this.dataset.lng);
        const name = this.dataset.name;
        prefillRouteDestination(lat, lng, name);
        switchTab('route');
      });
    });
  }

  window.focusHospital = function (id) {
    const hosp = locationData.find(l => l.type === 'hospital' && l.id === id);
    if (!hosp) return;
    document.querySelectorAll('.hosp-card').forEach(c =>
      c.classList.toggle('active', parseInt(c.dataset.id) === id)
    );
    map.flyTo([hosp.lat, hosp.lng], 16);
    const key = `hospital_${id}`;
    const marker = markerMap.get(key);
    if (marker) marker.openPopup();
  };

  window.launchRouteToHospital = function (lat, lng, name) {
    prefillRouteDestination(lat, lng, name);
    switchTab('route');
  };

  /* ─────────────────────────────────────
     7. DEBOUNCED SEARCH EVENT LISTENERS
  ───────────────────────────────────── */
  const debouncedRenderHospitals = debounce(renderHospitals, 250);
  hospitalSearch.addEventListener('input', debouncedRenderHospitals);
  districtFilter.addEventListener('change', loadExplorer);

  const btnClearDistrict = document.getElementById('btnClearDistrict');
  if (btnClearDistrict) {
    btnClearDistrict.addEventListener('click', () => {
      districtFilter.value = 'all';
      loadExplorer();
    });
  }

  /* ─────────────────────────────────────
     8. DOCTOR DRILL-DOWN
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
    deptFilter.innerHTML = '<option value="all">All Departments</option>' +
      (hosp.departments || []).map(d => `<option value="${d}">${d}</option>`).join('');
    renderDoctors();
    hospitalsTab.classList.add('hidden');
    doctorsTab.classList.remove('hidden');
    focusHospital(id);
  }

  function renderDoctors() {
    const dept = deptFilter.value;
    const hospName = selectedHospitalName.textContent;
    const doctors = locationData.filter(loc => loc.type === 'doctor' && loc.hospital === hospName);
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
          <span><i class="fa-solid fa-star"></i> ${d.rating} Rating</span>
          <span><i class="fa-solid fa-indian-rupee-sign"></i> ${d.fee} Fee</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
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

  /* ─────────────────────────────────────
     9. TOKEN QUEUE LIST (LIGHTWEIGHT DATA REFRESH)
  ───────────────────────────────────── */
  function loadTokenList() {
    fetch('/dashboard/api/queue-tokens')
      .then(r => r.json())
      .then(data => {
        renderTokenList(data.tokens || []);
        updateSummary(data.tokens || []);
      })
      .catch(err => console.error("Token list refresh error:", err));
  }

  function renderTokenList(tokens) {
    const container = document.getElementById('tokenList');
    if (!container) return;

    const searchInput = document.getElementById('tokenSearch');
    const search = searchInput ? searchInput.value.toLowerCase() : '';
    const filtered = tokens.filter(t =>
      t.patient.toLowerCase().includes(search) || t.token.toLowerCase().includes(search)
    );

    if (filtered.length === 0) {
      container.innerHTML = `<div class="token-empty"><p>No active tokens</p></div>`;
      return;
    }

    container.innerHTML = filtered.map(t => {
      const isConsulting = t.status === 'in_consultation';
      const cleanWait = Math.max(0, parseInt(t.wait_time) || 0);
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
              ${isConsulting ? 'Consulting' : `${cleanWait}m`}
            </span>
          </div>
        </div>`;
    }).join('');
  }

  function updateSummary(tokens) {
    const waiting = tokens.filter(t => t.status === 'waiting').length;
    const consulting = tokens.filter(t => t.status === 'in_consultation').length;
    const doctors = new Set(tokens.map(t => t.doctor)).size;

    const wEl = document.getElementById('totalWaiting');
    const cEl = document.getElementById('totalConsulting');
    const dEl = document.getElementById('totalDoctors');
    if (wEl) wEl.textContent = waiting;
    if (cEl) cEl.textContent = consulting;
    if (dEl) dEl.textContent = doctors;
  }

  const tokenSearchEl = document.getElementById('tokenSearch');
  if (tokenSearchEl) {
    tokenSearchEl.addEventListener('input', debounce(loadTokenList, 250));
  }

  /* ═══════════════════════════════════════════════
     10. ROUTE PLANNER MODULE (SINGLE-CALCULATION & CLEANUP)
  ═══════════════════════════════════════════════ */
  const rpOriginInput = document.getElementById('rpOrigin');
  const rpOriginSuggestions = document.getElementById('rpOriginSuggestions');
  const rpOriginStatus = document.getElementById('rpOriginStatus');
  const rpDistrictFilter = document.getElementById('rpDistrictFilter');
  const rpHospitalSelect = document.getElementById('rpHospital');
  const btnShowRoute = document.getElementById('btnShowRoute');
  const btnClearRoute = document.getElementById('btnClearRoute');
  const routeInfoPanel = document.getElementById('routeInfoPanel');

  let geocodeTimer = null;

  if (rpOriginInput) {
    rpOriginInput.addEventListener('input', function () {
      const val = this.value.trim();
      clearTimeout(geocodeTimer);
      if (val.length < 3) {
        if (rpOriginSuggestions) rpOriginSuggestions.classList.add('hidden');
        return;
      }
      geocodeTimer = setTimeout(() => geocodeOrigin(val), 400);
    });
  }

  function geocodeOrigin(query) {
    if (rpOriginStatus) rpOriginStatus.textContent = 'Searching…';
    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query + ', Tamil Nadu, India')}&limit=5&countrycodes=in`, {
      headers: { 'Accept-Language': 'en' }
    })
      .then(r => r.json())
      .then(results => {
        if (rpOriginStatus) rpOriginStatus.textContent = '';
        if (!results || results.length === 0) {
          if (rpOriginSuggestions) {
            rpOriginSuggestions.innerHTML = `<div class="rp-sug-item no-result">No results found</div>`;
            rpOriginSuggestions.classList.remove('hidden');
          }
          return;
        }
        if (rpOriginSuggestions) {
          rpOriginSuggestions.innerHTML = results.map(r => `
            <div class="rp-sug-item" data-lat="${r.lat}" data-lng="${r.lon}" data-label="${r.display_name}">
              <i class="fa-solid fa-location-dot" style="color:#6366f1;"></i>
              <span>${r.display_name}</span>
            </div>
          `).join('');
          rpOriginSuggestions.classList.remove('hidden');

          rpOriginSuggestions.querySelectorAll('.rp-sug-item').forEach(item => {
            item.addEventListener('click', function () {
              const lat = parseFloat(this.dataset.lat);
              const lng = parseFloat(this.dataset.lng);
              const label = this.dataset.label;
              setOriginLocation(lat, lng, label, rpOriginInput.value);
            });
          });
        }
      })
      .catch(() => { if (rpOriginStatus) rpOriginStatus.textContent = ''; });
  }

  function setOriginLocation(lat, lng, fullLabel, shortLabel) {
    originLatLng = { lat, lng, label: shortLabel || fullLabel };
    if (rpOriginInput) rpOriginInput.value = shortLabel || fullLabel.split(',')[0];
    if (rpOriginSuggestions) rpOriginSuggestions.classList.add('hidden');
    if (rpOriginStatus) {
      rpOriginStatus.textContent = '✓ Location set';
      rpOriginStatus.style.color = '#10b981';
    }

    // Place origin marker on map
    if (originMarker) map.removeLayer(originMarker);
    originMarker = L.marker([lat, lng], { icon: originIcon }).addTo(map);
    originMarker.bindPopup(`<div class="map-popup"><div class="mp-title">📍 Your Start</div><div class="mp-row">${shortLabel || fullLabel}</div></div>`).openPopup();
    map.flyTo([lat, lng], 12);

    // Remove old route layer when origin changes
    clearRoute(true);
    updateShowRouteBtn();
  }

  const btnUseMyLocation = document.getElementById('rpUseMyLocation');
  if (btnUseMyLocation) {
    btnUseMyLocation.addEventListener('click', function () {
      if (!navigator.geolocation) {
        if (rpOriginStatus) {
          rpOriginStatus.textContent = 'GPS not supported by your browser.';
          rpOriginStatus.style.color = '#ef4444';
        }
        return;
      }
      if (rpOriginStatus) {
        rpOriginStatus.textContent = 'Getting your location…';
        rpOriginStatus.style.color = '#6366f1';
      }
      navigator.geolocation.getCurrentPosition(pos => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        setOriginLocation(lat, lng, 'My Current Location', 'My Current Location');
      }, err => {
        if (rpOriginStatus) {
          rpOriginStatus.textContent = 'Could not get location. Please type it manually.';
          rpOriginStatus.style.color = '#ef4444';
        }
      });
    });
  }

  if (rpDistrictFilter) {
    rpDistrictFilter.addEventListener('change', function () {
      const distId = this.value;
      if (!rpHospitalSelect) return;

      rpHospitalSelect.innerHTML = '<option value="">Loading hospitals…</option>';
      rpHospitalSelect.disabled = true;
      if (btnShowRoute) btnShowRoute.disabled = true;

      // Clear existing route when destination district changes
      clearRoute(true);

      if (!distId) {
        rpHospitalSelect.innerHTML = '<option value="">— Select a district first —</option>';
        return;
      }

      fetch(`/dashboard/api/locations?district_id=${distId}`)
        .then(r => r.json())
        .then(data => {
          const hospitals = (data.locations || []).filter(l => l.type === 'hospital');
          if (hospitals.length === 0) {
            rpHospitalSelect.innerHTML = '<option value="">No hospitals in this district</option>';
            return;
          }
          rpHospitalSelect.innerHTML = '<option value="">— Select Hospital —</option>' +
            hospitals.map(h => `<option value="${h.id}" data-lat="${h.lat}" data-lng="${h.lng}" data-name="${h.name}">${h.name}</option>`).join('');
          rpHospitalSelect.disabled = false;
        });
    });
  }

  if (rpHospitalSelect) {
    rpHospitalSelect.addEventListener('change', function () {
      const opt = this.options[this.selectedIndex];

      // Remove existing route when hospital selection changes
      clearRoute(true);

      if (!opt.value) {
        destLatLng = null;
      } else {
        destLatLng = {
          lat: parseFloat(opt.dataset.lat),
          lng: parseFloat(opt.dataset.lng),
          label: opt.dataset.name
        };
        // Auto draw route ONCE when hospital is selected explicitly
        if (originLatLng && destLatLng) {
          drawRoute(originLatLng, destLatLng);
        }
      }
      updateShowRouteBtn();
    });
  }

  function updateShowRouteBtn() {
    if (btnShowRoute) {
      btnShowRoute.disabled = !(originLatLng && destLatLng);
    }
  }

  function prefillRouteDestination(lat, lng, name) {
    destLatLng = { lat, lng, label: name };
    if (rpHospitalSelect) {
      for (let opt of rpHospitalSelect.options) {
        if (opt.dataset.name === name) {
          rpHospitalSelect.value = opt.value;
          break;
        }
      }
    }
    clearRoute(true);
    updateShowRouteBtn();

    // Auto draw route if starting location is already selected
    if (originLatLng && destLatLng) {
      drawRoute(originLatLng, destLatLng);
    }
  }

  if (btnShowRoute) {
    btnShowRoute.addEventListener('click', function () {
      if (!originLatLng || !destLatLng) return;
      drawRoute(originLatLng, destLatLng);
    });
  }

  if (btnClearRoute) {
    btnClearRoute.addEventListener('click', function () {
      clearRoute(true);
    });
  }

  function drawRoute(origin, dest) {
    // Remove previous routing control layers cleanly before calculating new route
    clearRoute(false);

    map.invalidateSize();

    // OSRM routing calculated ONCE upon selection
    routingControl = L.Routing.control({
      waypoints: [
        L.latLng(origin.lat, origin.lng),
        L.latLng(dest.lat, dest.lng)
      ],
      routeWhileDragging: false,
      addWaypoints: false,
      draggableWaypoints: false,
      fitSelectedRoutes: true,
      show: false,
      lineOptions: {
        styles: [
          { color: '#6366f1', weight: 5, opacity: 0.85 },
          { color: '#ffffff', weight: 2, opacity: 0.4, dashArray: '6 10' }
        ]
      },
      createMarker: function (i, wp) {
        const icon = i === 0 ? originIcon : destIcon;
        const label = i === 0 ? origin.label : dest.label;
        const marker = L.marker(wp.latLng, { icon });
        marker.bindPopup(`<div class="map-popup"><div class="mp-title">${i === 0 ? '📍 Start' : '🏥 Destination'}</div><div class="mp-row">${label}</div></div>`).openPopup();
        return marker;
      },
      router: L.Routing.osrmv1({
        serviceUrl: 'https://router.project-osrm.org/route/v1',
        profile: 'driving'
      })
    }).addTo(map);

    routingControl.on('routesfound', function (e) {
      const route = e.routes[0];
      const distKm = (route.summary.totalDistance / 1000).toFixed(1);
      const timeMin = Math.max(0, Math.round(route.summary.totalTime / 60));
      const timeStr = timeMin >= 60
        ? `${Math.floor(timeMin / 60)}h ${timeMin % 60}m`
        : `${timeMin} min`;

      const distEl = document.getElementById('riDistance');
      const durEl = document.getElementById('riDuration');
      const fromEl = document.getElementById('riFrom');
      const toEl = document.getElementById('riTo');

      if (distEl) distEl.textContent = `${distKm} km`;
      if (durEl) durEl.textContent = timeStr;
      if (fromEl) fromEl.textContent = origin.label;
      if (toEl) toEl.textContent = dest.label;

      if (routeInfoPanel) routeInfoPanel.classList.remove('hidden');
      if (btnClearRoute) btnClearRoute.style.display = 'block';
      if (btnShowRoute) btnShowRoute.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Recalculate';
    });

    routingControl.on('routingerror', function (e) {
      if (rpOriginStatus) {
        rpOriginStatus.textContent = 'Route calculation failed. Check internet connection.';
        rpOriginStatus.style.color = '#ef4444';
      }
    });
  }

  function clearRoute(resetButtons = true) {
    if (routingControl) {
      try {
        map.removeControl(routingControl);
      } catch (err) { }
      routingControl = null;
    }
    if (resetButtons) {
      if (routeInfoPanel) routeInfoPanel.classList.add('hidden');
      if (btnClearRoute) btnClearRoute.style.display = 'none';
      if (btnShowRoute) btnShowRoute.innerHTML = '<i class="fa-solid fa-route"></i> Show Route';
    }
  }

  /* ─────────────────────────────────────
     11. MAP SEARCH & DEBOUNCE
  ───────────────────────────────────── */
  const mapSearch = document.getElementById('mapSearch');
  const mapSearchClear = document.getElementById('mapSearchClear');
  const mapSearchResults = document.getElementById('mapSearchResults');

  if (mapSearch) {
    mapSearch.addEventListener('input', debounce(function () {
      const q = this.value.trim().toLowerCase();
      if (!q) {
        if (mapSearchResults) mapSearchResults.classList.add('hidden');
        return;
      }
      const results = locationData.filter(l =>
        l.name.toLowerCase().includes(q) ||
        (l.specialty && l.specialty.toLowerCase().includes(q)) ||
        (l.departments && l.departments.some(d => d.toLowerCase().includes(q)))
      );
      if (results.length === 0) {
        if (mapSearchResults) mapSearchResults.innerHTML = `<div class="msr-no-results"><i class="fa-solid fa-magnifying-glass"></i>No results</div>`;
      } else {
        if (mapSearchResults) {
          mapSearchResults.innerHTML = results.slice(0, 8).map(r => `
            <div class="msr-item" data-lat="${r.lat}" data-lng="${r.lng}" data-name="${r.name}">
              <div class="msr-icon ${r.type}">
                <i class="fa-solid fa-${r.type === 'hospital' ? 'hospital' : 'user-doctor'}"></i>
              </div>
              <div class="msr-text">
                <span class="msr-name">${r.name}</span>
                <span class="msr-sub">${r.type === 'hospital' ? r.address : r.specialty}</span>
              </div>
              <i class="fa-solid fa-arrow-right msr-arrow"></i>
            </div>
          `).join('');
        }
      }
      if (mapSearchResults) mapSearchResults.classList.remove('hidden');

      if (mapSearchResults) {
        mapSearchResults.querySelectorAll('.msr-item').forEach(item => {
          item.addEventListener('click', function () {
            const lat = parseFloat(this.dataset.lat);
            const lng = parseFloat(this.dataset.lng);
            map.flyTo([lat, lng], 16);
            mapSearch.value = this.dataset.name;
            mapSearchResults.classList.add('hidden');
          });
        });
      }
    }, 250));
  }

  if (mapSearchClear) {
    mapSearchClear.addEventListener('click', () => {
      if (mapSearch) mapSearch.value = '';
      if (mapSearchResults) mapSearchResults.classList.add('hidden');
    });
  }

  /* ─────────────────────────────────────
     12. INITIALIZATION & REFRESH TIMERS
  ───────────────────────────────────── */
  loadExplorer();
  loadTokenList();

  // Poll lightweight token data every 15s without re-rendering map or reloading tiles
  setInterval(loadTokenList, 15000);
});
