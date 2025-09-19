const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1']);
const LOCAL_API_BASE = 'http://127.0.0.1:3000';
const PROD_API_BASE = 'https://trees-race-app-aqd6bva2etcfaaeb.canadacentral-01.azurewebsites.net';
const PROD_STRAVA_BASE = PROD_API_BASE;
const LOCAL_STRAVA_BASE = PROD_API_BASE; // Keep Strava hosted even in dev

const hostname = typeof window !== 'undefined' ? window.location.hostname : '';
const isLocal = LOCAL_HOSTS.has(hostname);

if (typeof window !== 'undefined') {
  if (!window.API_BASE) {
    window.API_BASE = isLocal ? LOCAL_API_BASE : PROD_API_BASE;
  }
  if (!window.STRAVA_BASE) {
    window.STRAVA_BASE = isLocal ? LOCAL_STRAVA_BASE : PROD_STRAVA_BASE;
  }
}

export function apiPath(path) {
  if (path.startsWith('/api/strava/')) {
    const base = (typeof window !== 'undefined' ? window.STRAVA_BASE : PROD_STRAVA_BASE) || '';
    return `${base}${path}`;
  }
  const base = (typeof window !== 'undefined' ? window.API_BASE : PROD_API_BASE) || '';
  return `${base}${path}`;
}

export async function fetchMe() {
  try {
    const response = await fetch(`${(typeof window !== 'undefined' ? window.API_BASE : PROD_API_BASE) || ''}/me`, {
      credentials: 'include',
    });
    if (!response.ok) return { user: null };
    return await response.json();
  } catch {
    return { user: null };
  }
}

export function loginGoogle() {
  const next = encodeURIComponent(typeof location !== 'undefined' ? location.href : '/');
  const base = (typeof window !== 'undefined' ? window.API_BASE : PROD_API_BASE) || '';
  if (typeof location !== 'undefined') {
    location.href = `${base}/auth/google/start?next=${next}`;
  }
}

export async function logout(appInstance) {
  const base = (typeof window !== 'undefined' ? window.API_BASE : PROD_API_BASE) || '';
  await fetch(`${base}/auth/logout`, { method: 'POST', credentials: 'include' });
  if (typeof window !== 'undefined') {
    localStorage.removeItem('ever_user');
  }
  await hydrateAuth(appInstance);
}

export async function hydrateAuth(appInstance = typeof window !== 'undefined' ? window.app : undefined) {
  const { user } = await fetchMe();
  const avatar = typeof document !== 'undefined' ? document.getElementById('auth-avatar') : null;
  const nameEl = typeof document !== 'undefined' ? document.getElementById('auth-name') : null;
  const loginBtn = typeof document !== 'undefined' ? document.getElementById('btn-login') : null;
  const logoutBtn = typeof document !== 'undefined' ? document.getElementById('btn-logout') : null;

  if (user) {
    if (nameEl) nameEl.textContent = user.name || user.email;
    if (avatar) {
      if (user.avatar_url) {
        avatar.src = user.avatar_url;
        avatar.style.display = 'block';
      } else {
        avatar.style.display = 'none';
      }
    }
    if (loginBtn) loginBtn.style.display = 'none';
    if (logoutBtn) logoutBtn.style.display = 'inline-flex';
    if (typeof document !== 'undefined') document.body.classList.add('is-authed');
    if (typeof window !== 'undefined') window.__AUTH_USER__ = user;

    const app = appInstance;
    if (app && app.user) {
      app.user.loggedIn = true;
      app.user.name = user.name || user.email;
      if (typeof app.fetchProfile === 'function') {
        await app.fetchProfile();
      }
    }
  } else {
    if (nameEl) nameEl.textContent = '';
    if (avatar) avatar.style.display = 'none';
    if (loginBtn) loginBtn.style.display = 'inline-flex';
    if (logoutBtn) logoutBtn.style.display = 'none';
    if (typeof document !== 'undefined') document.body.classList.remove('is-authed');
    if (typeof window !== 'undefined') window.__AUTH_USER__ = null;

    const app = appInstance;
    if (app && app.user) {
      app.user.loggedIn = false;
      app.user.name = '';
      if (typeof app.closePanels === 'function') app.closePanels();
      app.user.createdCourses = [];
      app.user.leaderboardPositions = [];
    }
  }
}

export function setupAuthUi(appInstance) {
  if (typeof document === 'undefined') return;
  const loginBtn = document.getElementById('btn-login');
  const logoutBtn = document.getElementById('btn-logout');
  if (loginBtn) loginBtn.addEventListener('click', () => loginGoogle());
  if (logoutBtn) logoutBtn.addEventListener('click', () => logout(appInstance));
}

if (typeof window !== 'undefined') {
  window.API = apiPath;
  window.loginGoogle = loginGoogle;
  window.logout = () => logout(window.app);
  window.hydrateAuth = () => hydrateAuth(window.app);
}
