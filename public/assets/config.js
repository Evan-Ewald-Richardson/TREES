
    // Backend API configuration
    // Auto-detect local vs production
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      window.API_BASE = "http://127.0.0.1:3000";  // Local development
      window.STRAVA_BASE = "https://trees-race-app-aqd6bva2etcfaaeb.canadacentral-01.azurewebsites.net";  // Strava auth stays on hosted
    } else {
      window.API_BASE = "https://trees-race-app-aqd6bva2etcfaaeb.canadacentral-01.azurewebsites.net";  // Production
      window.STRAVA_BASE = window.API_BASE;  // Same as API in production
    }
  
    function API(path) {
      // Route Strava endpoints to hosted server even in local dev
      if (path.startsWith('/api/strava/')) {
        return (window.STRAVA_BASE || window.API_BASE) + path;
      }
      return (window.API_BASE || "") + path;
    }

    // OAuth functionality
    async function fetchMe() {
      try {
        const r = await fetch(`${window.API_BASE}/me`, { credentials: 'include' });
        if (!r.ok) return { user: null };
        return await r.json();
      } catch { return { user: null }; }
    }

    function loginGoogle() {
      const next = encodeURIComponent(location.href);
      location.href = `${window.API_BASE}/auth/google/start?next=${next}`;
    }

    async function logout() {
      await fetch(`${window.API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
      // Clear localStorage for legacy system compatibility
      localStorage.removeItem("ever_user");
      await hydrateAuth();
    }

    async function hydrateAuth() {
      const { user } = await fetchMe();
      const $avatar = document.getElementById('auth-avatar');
      const $name = document.getElementById('auth-name');
      const $login = document.getElementById('btn-login');
      const $logout = document.getElementById('btn-logout');

      if (user) {
        $name.textContent = user.name || user.email;
        if (user.avatar_url) { $avatar.src = user.avatar_url; $avatar.style.display = 'block'; }
        else { $avatar.style.display = 'none'; }
        $login.style.display = 'none';
        $logout.style.display = 'inline-flex';
        document.body.classList.add('is-authed');
        // Store minimal display info in memory for other components
        window.__AUTH_USER__ = user;
        
        // Also update Vue user state for compatibility with existing profile system
        if (window.app && window.app.user) {
          window.app.user.loggedIn = true;
          window.app.user.name = user.name || user.email;
          // Fetch the profile data for the Vue system
          await window.app.fetchProfile?.();
        }
      } else {
        $name.textContent = '';
        $avatar.style.display = 'none';
        $login.style.display = 'inline-flex';
        $logout.style.display = 'none';
        document.body.classList.remove('is-authed');
        window.__AUTH_USER__ = null;
        
        // Also clear Vue user state
        if (window.app && window.app.user) {
          window.app.user.loggedIn = false;
          window.app.user.name = '';
          window.app.closePanels?.();
          window.app.user.createdCourses = [];
          window.app.user.leaderboardPositions = [];
        }
      }
    }

