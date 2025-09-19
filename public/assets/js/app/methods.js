export const methods = {
    startNewCourse() {
      this.selectedCourseId = null;
      this.selectedCourse = null;
      this.timeGates = [];
      this.pairCheckpoints.clear();
      this.pairNames.clear();
      this.leaderboard = [];
      this.bufferMeters = 10;
      this.isCreatingCourse = true; this.redrawGates();},
    deselectCourse() { this.selectedCourseId = null; this.selectedCourse = null; this.isCreatingCourse = false; this.timeGates = []; this.pairCheckpoints.clear(); this.pairNames.clear(); this.leaderboard = []; this.bufferMeters = 10; this.redrawGates(); },
    // Expose API helper for templates and methods
    API(path) {
      try { return (window.API ? window.API(path) : (window.API_BASE || '') + path); }
      catch { return path; }
    },
    /* -------------------- PANEL MANAGEMENT -------------------- */
    invalidateMap() {
      if (!this.map) return;
      requestAnimationFrame(() => {
        if (this.map && this.map.invalidateSize) {
          this.map.invalidateSize();
        }
      });
    },
    setActivePanel(panel) {
      const nextPanel = panel || null;
      if (this.ui.activePanel === nextPanel) {
        this.invalidateMap();
        return;
      }
      this.ui.activePanel = nextPanel;
      this.$nextTick(() => this.invalidateMap());
      if (nextPanel === 'courses') {
        this.refreshCoursesGrid();
      }
      if (nextPanel === 'profile' && this.user.loggedIn) {
        this.fetchProfile();
      }
    },
    openPanel(panel) {
      this.setActivePanel(panel);
    },
    togglePanel(panel) {
      const next = this.ui.activePanel === panel ? null : panel;
      this.setActivePanel(next);
    },
    openCoursesModal() {
      if (this.ui.activePanel === 'courses') {
        this.refreshCoursesGrid();
      } else {
        this.setActivePanel('courses');
      }
    },
    closePanels() {
      this.setActivePanel(null);
    },

    /* -------------------- SIDEBAR RESIZER -------------------- */
    setupSidebarResizer() {
      const left = document.querySelector('.left');
      const resizer = left?.querySelector('.resizer');
      if (!left || !resizer) return;

      const MIN = 320;                 // matches CSS min-width
      const MAX = Math.floor(window.innerWidth * 0.75);

      let startX = 0, startW = 0, dragging = false;

      const onMove = (e) => {
        if (!dragging) return;
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const dx = clientX - startX;
        const newW = Math.max(MIN, Math.min(MAX, startW + dx));
        left.style.width = newW + 'px';
        left.style.flex = '0 0 auto';   // keep fixed width during drag
        if (this.map) this.map.invalidateSize(); // keep Leaflet happy
        e.preventDefault?.();
      };

      const stop = () => {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove('resizing');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', stop);
        window.removeEventListener('touchmove', onMove);
        window.removeEventListener('touchend', stop);
      };

      const start = (e) => {
        dragging = true;
        startX = e.touches ? e.touches[0].clientX : e.clientX;
        startW = left.getBoundingClientRect().width;
        document.body.classList.add('resizing');
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', stop);
        window.addEventListener('touchmove', onMove, { passive: false });
        window.addEventListener('touchend', stop);
        e.preventDefault?.();
      };

      resizer.addEventListener('mousedown', start);
      resizer.addEventListener('touchstart', start, { passive: false });
    },

    /* -------------------- USER SYSTEM -------------------- */
    async login() {
      const name = (this.user.loginName || "").trim();
      if (!name) return;
      
      const loginUrl = API("/users/login");
      console.log("Attempting login to:", loginUrl, "with name:", name);
      
      try {
        const res = await fetch(loginUrl, {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ name })
        });
        
        console.log("Login response status:", res.status);
        
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          const errorMsg = errorData.detail || `Login failed (${res.status})`;
          console.error("Login error details:", errorData);
          alert(`Login failed: ${errorMsg}

Trying to connect to: ${loginUrl}

Check browser console for details.`);
          return;
        }
        
        const u = await res.json();
        console.log("Login successful:", u);
        this.user.name = u.name;
        this.user.loggedIn = true;
        this.user.isAdmin = this.isSuperUser;
        this.user.loginName = "";
        localStorage.setItem("ever_user", JSON.stringify(u.name));
        await this.fetchProfile();
      } catch (error) {
        console.error("Login network error:", error);
        alert(`Login failed: Network error - ${error.message}

Trying to connect to: ${loginUrl}

This might be a CORS issue or the server might be unreachable.`);
      }
    },
    
    logout() {
      this.user.loggedIn = false;
      this.user.name = "";
      this.closePanels();
      this.user.createdCourses = [];
      this.user.leaderboardPositions = [];
      this.user.isAdmin = false;
      localStorage.removeItem("ever_user");
    },
    
    async fetchProfile() {
      if (!this.user.loggedIn) return;
      
      // Try OAuth profile endpoint first
      if (window.__AUTH_USER__) {
        try {
          const r = await fetch(API('/me/profile'), { credentials: 'include' });
          if (r.ok) {
            const p = await r.json();
            this.user.createdCourses = p.createdCourses || [];
            this.user.leaderboardPositions = p.leaderboardPositions || [];
            const authUser = (typeof window !== 'undefined' && window.__AUTH_USER__) || null;
            const computedAdmin = typeof p.isAdmin === 'boolean' ? p.isAdmin : !!(authUser && authUser.role === 'admin');
            this.user.isAdmin = computedAdmin;
            return;
          }
        } catch (e) {
          console.log('OAuth profile fetch failed, trying legacy:', e);
        }
      }
      
      // Fallback to legacy profile endpoint using consistent username
      try {
        const username = this.backendUsername;
        if (username) {
          const r = await fetch(API(`/users/${encodeURIComponent(username)}/profile`));
          if (r.ok) {
            const p = await r.json();
            this.user.createdCourses = p.createdCourses || [];
            this.user.leaderboardPositions = p.leaderboardPositions || [];
            this.user.isAdmin = this.isSuperUser;
            return;
          }
        }
      } catch (e) {
        console.log('Legacy profile fetch failed:', e);
      }
      
      // Clear profile data if all methods fail
      this.user.createdCourses = [];
      this.user.leaderboardPositions = [];
      this.user.isAdmin = false;
    },
    
    // UI hooks for the existing right-side profile panel
    closeProfileModal() {
      this.closePanels();
    },

    async loadCourseFromProfile(courseId) {
        // Close the profile modal
        this.closePanels();

        // Load the selected course
        this.selectedCourseId = courseId;
        await this.loadSelectedCourse();
        
        // Scroll to courses section
        const coursesSection = document.getElementById('courses');
        if (coursesSection) {
            coursesSection.scrollIntoView({ behavior: 'smooth' });
        }
    },
    
    async deleteLeaderboardEntry(entryId) {
      if (!confirm("Delete this leaderboard entry?")) return;
      const url = API(`/users/${encodeURIComponent(this.backendUsername)}/leaderboard/${entryId}`);
      const r = await fetch(url, { method: "DELETE", credentials: "include" });
      if (!r.ok) { alert("Delete failed"); return; }
      await this.fetchProfile();
    },
    
    async deleteCourse(courseId) {
      if (!confirm("Delete this course? This also deletes its leaderboard entries.")) return;
      const url = API(`/users/${encodeURIComponent(this.backendUsername)}/courses/${courseId}`);
      const r = await fetch(url, { method: "DELETE", credentials: "include" });
      if (!r.ok) { alert("Delete failed"); return; }
      await this.fetchProfile();
    },
    

    /* -------------------- COURSES -------------------- */
    async apiGet(path) {
        const res = await fetch(API(path), { credentials: 'include' });
        if (!res.ok) {
            let msg; try { msg = (await res.json()).detail || await res.text(); } catch { msg = await res.text(); }
            throw new Error(msg);
        }
        return res.json();
     },

    async refreshCoursesGrid() {
      if (this.refreshingCourses) return;
      this.refreshingCourses = true;
      try {
        await this.loadCourses();
      } finally {
        this.refreshingCourses = false;
      }
    },
    formatDate(iso) {
      if (!iso) return 'ΓÇö';
      const date = new Date(iso);
      if (Number.isNaN(date.getTime())) return 'ΓÇö';
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    },
    formatSeconds(total) {
      const n = Number(total);
      if (!Number.isFinite(n) || n < 0) return 'ΓÇö';
      if (n < 60) {
        return `${Math.round(n)}s`;
      }
      const hours = Math.floor(n / 3600);
      const minutes = Math.floor((n % 3600) / 60);
      const seconds = Math.round(n % 60);
      const mm = hours ? String(minutes).padStart(2, '0') : String(minutes);
      const ss = String(seconds).padStart(2, '0');
      return hours ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
    },
    courseGateCount(course) {
      if (!course) return 0;
      if (typeof course.gate_count === 'number') return course.gate_count;
      if (Array.isArray(course.gates)) return course.gates.length;
      return 0;
    },
    courseLeaderboardCount(course) {
      if (!course) return 0;
      if (typeof course.leaderboard_count === 'number') return course.leaderboard_count;
      if (Array.isArray(course.leaderboard)) return course.leaderboard.length;
      return course.first_place ? 1 : 0;
    },
    loadCourseCard(id) {
      this.closePanels();
      this.selectedCourseId = id;
      this.$nextTick(async () => {
        await this.loadSelectedCourse(); // already implemented
      });
    },

    onCourseImageSelect(e) {
      const f = e.target.files && e.target.files[0];
      if (!f) { 
        this.newCourse.imageFile = null; 
        this.newCourse.imagePreview = null; 
        return; 
      }
      this.newCourse.imageFile = f;
      if (this.newCourse.imagePreview) URL.revokeObjectURL(this.newCourse.imagePreview);
      this.newCourse.imagePreview = URL.createObjectURL(f);
    },

    async saveAdvancedCourse() {
      // Use your existing gate payload helper
      const gates = this.gatePairsToApiPayload();
      if (!gates.length) { alert("Confirm at least one gate pair before saving."); return; }
      if (!this.newCourse.name) { alert("Enter a course name."); return; }

      try {
        // Step 1: create
        const created = await this.apiPost("/courses", {
          name: this.newCourse.name,
          buffer_m: this.bufferMeters || 10,
          gates,
          created_by: this.backendUsername,
          description: this.newCourse.description || null,
          image_url: null
        });

        // Step 2: optional image upload
        if (this.newCourse.imageFile) {
          const fd = new FormData();
          fd.append("file", this.newCourse.imageFile);
          const r = await fetch(API(`/courses/${created.id}/image`), {
            method: "POST",
            body: fd,
            credentials: "include"
          });
          if (!r.ok) { console.warn("Image upload failed"); }
        }

        // Reset & load
        if (this.newCourse.imagePreview) URL.revokeObjectURL(this.newCourse.imagePreview);
        this.newCourse = { name: "", description: "", imageFile: null, imagePreview: null };
        this.closePanels();
        await this.loadCourses();           // refresh select list + cards
        this.selectedCourseId = created.id;
        await this.loadSelectedCourse();
      } catch (e) {
        alert(`Save failed: ${e.message || e}`);
      }
    },

        // [ADD] Courses: list
    async loadCourses() {
        try {
            const data = await this.apiGet("/courses_summary");
            const normalized = (Array.isArray(data) ? data : [])
                .map(c => ({
                    ...c,
                    gates: Array.isArray(c.gates) ? c.gates : [],
                }));
            this.courses = normalized;
            this.coursesGrid = normalized
                .slice()
                .sort((a, b) => {
                    const aTime = a.created_at ? Date.parse(a.created_at) : 0;
                    const bTime = b.created_at ? Date.parse(b.created_at) : 0;
                    return bTime - aTime;
                });
        } catch (e) {
            console.error(e);
            this.courses = [];
            this.coursesGrid = [];
        }
    },

    // [ADD] Courses: load selected course into the map + state
    async loadSelectedCourse() {
        if (!this.selectedCourseId) return;
        try {
            const c = await this.apiGet(`/courses/${this.selectedCourseId}`);
            this.selectedCourse = c;
            this.isCreatingCourse = false;

            // Replace local gates with course gates (confirmed, non-editing)
            this.timeGates = [];
            this.pairCheckpoints.clear();
            this.pairNames.clear();
            for (const g of c.gates) {
                this.timeGates.push({
                    id: `${g.pairId}_S`, pairId: g.pairId, name: g.name,
                    type: "start", lat: g.start.lat, lon: g.start.lon,
                    confirmed: true, editing: false
                });
                this.timeGates.push({
                    id: `${g.pairId}_E`, pairId: g.pairId, name: g.name,
                    type: "end", lat: g.end.lat, lon: g.end.lon,
                    confirmed: true, editing: false
                });
                if (Array.isArray(g.checkpoints)) {
                    this.pairCheckpoints.set(g.pairId, g.checkpoints.map(cp => ({ lat: cp.lat, lon: cp.lon })));
                }
                // Store the custom name
                this.pairNames.set(g.pairId, g.name);
            }
            this.bufferMeters = c.buffer_m;
            this.redrawGates();
            await this.fetchLeaderboard();
            await this.recalcAllSegmentTimes();
        } catch (e) {
            alert(`Load failed: ${e.message || e}`);
        }
        },

        // [ADD] Leaderboard: fetch
        async fetchLeaderboard() {
        if (!this.selectedCourseId) { this.leaderboard = []; return; }
        try {
            const data = await this.apiGet(`/leaderboard/${this.selectedCourseId}`);
            this.leaderboard = data.entries || [];
        } catch (e) {
            console.error(e);
            this.leaderboard = [];
        }
        },

        // [ADD] Leaderboard: submit a track (arcade-style name only)
    async submitTrackToLeaderboard(trackId) {
      if (!this.user.loggedIn) { alert("Please login first."); return; }
      const t = this.tracks.find(x => x.id === trackId);
      if (!t) return;
      const payload = { username: this.backendUsername, points: t.points };
      const r = await fetch(API(`/leaderboard/${this.selectedCourseId}/submit`), {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(payload)
      });
      if (!r.ok) {
        const err = await r.json().catch(()=>({detail:"Submit failed"}));
        alert(err.detail || "Submit failed");
        return;
      }
      await this.fetchLeaderboard?.();
      await this.fetchProfile();
    },
    /* -------------------- API -------------------- */
    async apiPost(path, body) {
        const res = await fetch(API(path), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: 'include',         // <-- important
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            let msg; try { msg = (await res.json()).detail || await res.text(); } catch { msg = await res.text(); }
            throw new Error(msg);
        }
        return res.json();
    },

    async apiDelete(path) {
        const res = await fetch(API(path), {
            method: "DELETE",
            credentials: 'include'
        });
        if (!res.ok) {
            let msg; try { msg = (await res.json()).detail || await res.text(); } catch { msg = await res.text(); }
            throw new Error(msg);
        }
        return res.json();
    },

    gatePairsToApiPayload() {
    return this.gatePairs
        .filter(p => p.start && p.end && p.confirmed)
        .map(p => ({
            pairId: p.pairId,
            name: p.name || `Gate Pair ${p.pairId}`,
            start: { lat: p.start.lat, lon: p.start.lon },
            end:   { lat: p.end.lat,   lon: p.end.lon },
            checkpoints: p.checkpoints.map(c => ({ lat: c.lat, lon: c.lon }))
        }));
    },
    /* -------------------- MAP INIT -------------------- */
    initMap() {
      this.map = L.map('map', { worldCopyJump: true }).setView([49.35, -123.10], 11);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '┬⌐ OpenStreetMap contributors'
      }).addTo(this.map);

      const bcBounds = L.latLngBounds([48.0, -125.5], [50.5, -122.0]);
      this.map.setMaxBounds(bcBounds);
      this.map.setMinZoom(4);
      this.map.setMaxZoom(20);
    },

    /* -------------------- UPLOAD -------------------- */
    handleDrop(e) {
      this.isDragOver = false;
      const files = Array.from(e.dataTransfer.files || []).filter(f => f.name.toLowerCase().endsWith('.gpx'));
      files.forEach(this.processFile);
    },
    handleFileSelect(e) {
      const files = Array.from(e.target.files || []).filter(f => f.name.toLowerCase().endsWith('.gpx'));
      files.forEach(this.processFile);
    },

    async processFile(file) {
      // quick validation
      if (!file.name.toLowerCase().endsWith('.gpx')) { this.error = 'Please select a .gpx file.'; return; }
      if (file.size > 10 * 1024 * 1024) { this.error = 'Max file size is 10MB.'; return; }

      this.loading = true; this.error = null;
      const formData = new FormData();
      formData.append('gpxfile', file);

      try {
        const resp = await fetch(API('/upload-gpx'), {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ error: 'Upload failed' }));
          throw new Error(err.error || 'Upload failed');
        }
        const data = await resp.json();
        if (!data.tracks?.length) throw new Error('No tracks found in GPX');

        const base = this.tracks.length;
        const newTracks = data.tracks.map((t, i) => ({
          ...t,
          id: `${Date.now()}_${i}`,
          color: this.trackColors[(base + i) % this.trackColors.length]
        }));

        this.tracks.push(...newTracks);
        this.selectedTrackIds.push(...newTracks.map(t => t.id));
        this.redrawTracks();

        if (this.gatePairs.some(p => p.confirmed)) {
            this.recalcAllSegmentTimes();
        }

      } catch (e) {
        this.error = e.message || 'Unknown error';
      } finally {
        this.loading = false;
        if (this.$refs.fileInput) this.$refs.fileInput.value = '';
      }
    },

    clearTracks() {
      this.tracks = [];
      this.clearLayerArray(this.trackLayers);
    },

    /* -------------------- GATES -------------------- */
    addGatePair() {
      const c = this.map.getCenter();
      const offset = 0.001; // ~100m-ish latitude/longitude-ish (varies by lat)
      const nextPairId = this.nextPairId();

      const start = {
        id: `${Date.now()}_S`,
        pairId: nextPairId,
        name: `Gate Pair ${nextPairId}`,
        type: 'start',
        lat: c.lat + offset,
        lon: c.lng + offset,
        confirmed: false,
        editing: true
      };
      const end = {
        id: `${Date.now()}_E`,
        pairId: nextPairId,
        name: `Gate Pair ${nextPairId}`,
        type: 'end',
        lat: c.lat - offset,
        lon: c.lng - offset,
        confirmed: false,
        editing: true
      };
      this.timeGates.push(start, end);
      this.redrawGates();
    },

    startEditing(pairId) {
      // exactly one pair editable at once
      this.timeGates.forEach(g => { g.editing = (g.pairId === pairId); if (g.pairId !== pairId && !g.confirmed) g.confirmed = false; });
      this.redrawGates();
    },

    updatePairName(pairId, newName) {
      // Update the persistent name storage
      this.pairNames.set(pairId, newName);
    },

    saveAndConfirmGate(pairId) {
      // Get the current name from the gatePairs (which includes any UI edits)
      const pair = this.gatePairs.find(p => p.pairId === pairId);
      const newName = pair?.name || `Gate Pair ${pairId}`;
      
      // Store the name persistently
      this.pairNames.set(pairId, newName);

      // Mark gates as confirmed and stop editing
      this.timeGates = this.timeGates.map(g => {
        if (g.pairId !== pairId) return g;
        return { ...g, name: newName, confirmed: true, editing: false };
      });
      this.redrawGates();
      this.recalcAllSegmentTimes();
      this.fetchLeaderboard();
    },

    removeGatePair(pairId) {
      this.timeGates = this.timeGates.filter(g => g.pairId !== pairId);
      this.pairCheckpoints.delete(pairId);
      this.pairNames.delete(pairId);
      this.redrawGates();
      this.recalcAllSegmentTimes();
    },

    clearAllGates() {
      this.timeGates = [];
      this.pairCheckpoints.clear();
      this.pairNames.clear();
      this.redrawGates();
      this.recalcAllSegmentTimes();
    },

    nextPairId() {
      // choose the smallest positive integer not used yet
      const used = new Set(this.timeGates.map(g => g.pairId));
      let i = 1; while (used.has(i)) i += 1; return i;
    },

    addCheckpoint(pairId) {
      const pair = this.gatePairs.find(p => p.pairId === pairId);
      if (pair) {
        const newCheckpoint = { lat: pair.start.lat, lon: pair.start.lon };
        if (!this.pairCheckpoints.has(pairId)) {
          this.pairCheckpoints.set(pairId, []);
        }
        this.pairCheckpoints.get(pairId).push(newCheckpoint);
        this.redrawGates();
      }
    },

    removeLastCheckpoint(pairId) {
      if (this.pairCheckpoints.has(pairId)) {
        const checkpoints = this.pairCheckpoints.get(pairId);
        if (checkpoints.length > 0) {
          checkpoints.pop();
          this.redrawGates();
        }
      }
    },

    /* -------------------- TRACKS -------------------- */
    isSelected(trackId) {
        return this.selectedTrackIds.includes(trackId);
    },

    toggleTrack(trackId) {
        const i = this.selectedTrackIds.indexOf(trackId);
        if (i >= 0) this.selectedTrackIds.splice(i, 1);
        else this.selectedTrackIds.push(trackId);
        this.redrawTracks();
    },

    removeTrack(trackId) {
        this.tracks = this.tracks.filter(t => t.id !== trackId);
        const i = this.selectedTrackIds.indexOf(trackId);
        if (i >= 0) this.selectedTrackIds.splice(i, 1);
        this.redrawTracks();
    },

    /* -------------------- DRAWING / LAYERS -------------------- */
    clearLayerArray(arr) {
      arr.forEach(l => { try { this.map.removeLayer(l); } catch(_) {} });
      arr.splice(0, arr.length);
    },

    redrawTracks() {
        this.clearLayerArray(this.trackLayers);

        if (!this.tracks.length) return;

        // Only draw tracks that are both selected and have points
        const selected = new Set(this.selectedTrackIds);
        const toDraw = this.tracks.filter(t => selected.has(t.id) && t.points?.length > 0);

        if (!toDraw.length) return;

        let bounds = null;
        toDraw.forEach(t => {
            const latlngs = t.points.map(p => [p.lat, p.lon]);
            const line = L.polyline(latlngs, { color: t.color, weight: 3, opacity: 0.9 }).addTo(this.map);
            this.trackLayers.push(line);

            const start = L.marker(latlngs[0]).addTo(this.map).bindPopup(`${t.name} - Start`);
            const end = L.marker(latlngs[latlngs.length - 1]).addTo(this.map).bindPopup(`${t.name} - End`);
            this.trackLayers.push(start, end);

            bounds = bounds ? bounds.extend(line.getBounds()) : line.getBounds();
        });

        if (bounds) this.map.fitBounds(bounds);
    },

    redrawGates() {
    this.clearLayerArray(this.gateMarkers);
    this.clearLayerArray(this.checkpointMarkers);

    // Draw Start/End markers as before
    for (const gate of this.timeGates) {
        const isStart = gate.type === 'start';
        const isEditing = gate.editing;
        const isConfirmed = gate.confirmed;

        const bg = isStart ? (isConfirmed ? '#10b981' : '#f59e0b') : (isConfirmed ? '#111827' : '#f59e0b');
        const border = isStart ? (isConfirmed ? '#047857' : '#ea580c') : (isConfirmed ? '#ffffff' : '#ea580c');
        const label = isStart ? 'S' : 'E';

        const icon = L.divIcon({
        className: 'gate-icon',
        html: `<div style="background:${bg}; color:white; border-radius:50%; width:34px; height:34px; display:flex; align-items:center; justify-content:center; font-weight:700; border:3px solid ${border}; box-shadow:0 2px 6px rgba(0,0,0,.3);">${label}</div>`,
        iconSize: [34,34], iconAnchor: [17,17]
        });

        const marker = L.marker([gate.lat, gate.lon], {
        icon, draggable: isEditing || !isConfirmed
        }).addTo(this.map);

        marker.on('dragend', (e) => {
        const ll = e.target.getLatLng();
        gate.lat = ll.lat; gate.lon = ll.lng;
        });

        this.gateMarkers.push(marker);
    }

    // Draw checkpoints for pairs that are currently in memory (use computed pairs)
    const pairs = this.gatePairs;
    for (const pair of pairs) {
        if (!Array.isArray(pair.checkpoints) || !pair.checkpoints.length) continue;

        // color-tie to gate: use the start confirmed color hue (#10b981 green) but lighter bubble
        const cpBorder = pair.confirmed ? '#10b981' : '#f59e0b';
        pair.checkpoints.forEach((cp, idx) => {
        const icon = L.divIcon({
            className: 'cp-icon',
            html: `<div style="background:white; color:${cpBorder}; border-radius:999px; border:2px solid ${cpBorder}; padding:2px 6px; font-size:12px; font-weight:700; box-shadow:0 1px 4px rgba(0,0,0,.25);">${idx+1}</div>`,
            iconSize: [24, 22],
            iconAnchor: [12, 11]
        });
        const m = L.marker([cp.lat, cp.lon], {
            icon,
            draggable: !!pair.editing  // only draggable in edit mode
        }).addTo(this.map);

        m.on('dragend', (e) => {
            const ll = e.target.getLatLng();
            cp.lat = ll.lat; cp.lon = ll.lng;
        });

        this.checkpointMarkers.push(m);
        });
    }
    },

    /* -------------------- SEGMENT TIMES -------------------- */
    async recalcAllSegmentTimes() {
        if (!this.tracks.length) return;

        const gates = this.gatePairsToApiPayload();
        // If no confirmed gates, clear any old results
        if (!gates.length) {
            this.tracks.forEach(t => t.segmentTimes = []);
            return;
        }

        const buffer_m = this.bufferMeters || 10;

        // Compute per track (simple + readable; can batch later if needed)
        for (const t of this.tracks) {
            if (!t.points?.length) { 
                t.segmentTimes = []; 
                continue; 
            }
            try {
                const data = await this.apiPost("/segment-times", {
                    points: t.points.map(p => ({ lat: p.lat, lon: p.lon, ele: p.ele ?? null, time: p.time ?? null })),
                    gates,
                    buffer_m
                });
                t.segmentTimes = data.segments || [];
            } catch (e) {
                console.error("Segment calc failed", e);
                t.segmentTimes = [];
            }
        }
    },

    /* -------------------- STRAVA -------------------- */
    async checkStravaConnected() {
        try {
            const res = await fetch(API('/api/strava/me'), { credentials: 'include' });
            if (!res.ok) throw new Error(await res.text());
            this.strava.athlete = await res.json();
            this.strava.connected = true;
            this.strava.error = null;
        } catch (e) {
            this.strava.connected = false;
            this.strava.athlete = null;
            // do not show error on page load
        }
    },

    stravaLogin() {
        window.location.href = API('/api/strava/login');
    },
    
    async fetchStravaActivities(page = this.strava.page) {
        if (!this.strava.connected) return;
        this.strava.loading = true;
        this.strava.error = null;
        try {
            const url = API(`/api/strava/activities?per_page=${this.strava.perPage}&page=${page}`);
            const res = await fetch(url, { credentials: 'include' });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            // backend may return an array or {activities:[...]}
            const list = Array.isArray(data) ? data : (data.activities || data.data || []);
            this.strava.activities = list;
            this.strava.page = page;
            this.strava.hasMore = (list.length === this.strava.perPage);
        } catch (e) {
            this.strava.error = e?.message || 'Failed to load activities';
        } finally {
            this.strava.loading = false;
        }
    },

    async nextStravaPage() {
        if (!this.strava.hasMore) return;
        await this.fetchStravaActivities(this.strava.page + 1);
        this.clearStravaPreview();
    },

    async prevStravaPage() {
        if (this.strava.page <= 1) return;
        await this.fetchStravaActivities(this.strava.page - 1);
        this.clearStravaPreview();
    },

    async refreshStrava() {
        this.strava.page = 1;
        await this.fetchStravaActivities(1);
    },

    clearStravaPreview() {
        if (this.strava.preview.layer) {
            try { this.map.removeLayer(this.strava.preview.layer); } catch {}
        }
        this.strava.preview.layer = null;
        this.strava.preview.activityId = null;
    },

    async previewStravaActivity(activityId) {
        // toggle off
        if (this.strava.preview.activityId === activityId) {
            this.clearStravaPreview();
            return;
        }
        try {
            // reuse your import endpoint for points
            const res = await fetch(API(`/api/strava/activities/${activityId}/points`), { credentials: 'include' });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            const latlngs = (data.points || []).map(p => [p.lat, p.lon]);
            if (!latlngs.length) throw new Error('No points');

            this.clearStravaPreview();
            const layer = L.polyline(latlngs, { weight: 4, opacity: 0.9, dashArray: '6,6' }).addTo(this.map);
            this.strava.preview.layer = layer;
            this.strava.preview.activityId = activityId;
            this.map.fitBounds(layer.getBounds());
        } catch (e) {
            this.strava.error = e.message || 'Preview failed';
        }
    },

    async importStravaActivity(activityId) {
        try {
            const res = await fetch(API(`/api/strava/activities/${activityId}/points`), { credentials: 'include' });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            const pts = data.points || [];
            if (!pts.length) throw new Error('No timed points found for this activity');

            const base = this.tracks.length;
            const t = {
            id: `${Date.now()}_${activityId}`,
            name: data.name || `Activity ${activityId}`,
            points: pts,
            color: this.trackColors[(base) % this.trackColors.length]
            };
            this.tracks.push(t);
            this.selectedTrackIds.push(t.id);
            this.redrawTracks();

            // recompute segment times if gates exist
            if (this.gatePairs.some(p => p.confirmed)) {
            this.recalcAllSegmentTimes();
            }

            // clear preview if it was this activity
            if (this.strava.preview.activityId === activityId) {
            this.clearStravaPreview();
            }
        } catch (e) {
            alert(e.message || 'Import failed');
        }
    },
};
