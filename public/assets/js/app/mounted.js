export async function mountedHook() {
    this.initMap();
    this.loadCourses();
    this.checkStravaConnected();
    this.setupSidebarResizer();
    
    // Fetch config and restore saved user
    try {
      const cfg = await fetch(this.API("/config")).then(r => r.json());
      if (!window.API_BASE && cfg.backend_url) window.API_BASE = cfg.backend_url;
      this.config.superUserName = cfg.super_user_name || null;
    } catch(e) {}
    
    const saved = localStorage.getItem("ever_user");
    if (saved) {
      this.user.name = JSON.parse(saved);
      this.user.loggedIn = true;
      await this.fetchProfile();
    }
}
