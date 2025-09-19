export const computedConfig = {
    isProfileOpen() {
      return this.ui.activePanel === 'profile';
    },
    isCoursesOpen() {
      return this.ui.activePanel === 'courses';
    },
    isSaveOpen() {
      return this.ui.activePanel === 'save';
    },
    canEditGates() { return !!this.isCreatingCourse; },
    activeRoutes() {
      const ids = new Set(this.selectedTrackIds || []);
      return (this.tracks || []).filter(t => ids.has(t.id));
    },
    isAnyPanelOpen() {
      return this.ui.activePanel !== null;
    },
    isSuperUser() {
      if (!this.user.loggedIn) return false;
      const authUser = (typeof window !== 'undefined' && window.__AUTH_USER__) || null;
      const emailList = Array.isArray(this.config.superUserEmails) ? this.config.superUserEmails : [];
      const authEmail = authUser && authUser.email ? authUser.email.trim().toLowerCase() : '';
      if (authUser && authUser.role === 'admin') return true;
      if (authEmail && emailList.some(email => (email || '').trim().toLowerCase() === authEmail)) return true;
      const configured = (this.config.superUserName || '').trim().toLowerCase();
      if (!configured) return false;
      return (this.user.name || '').trim().toLowerCase() === configured;
    },
    
    // Get a consistent username for backend operations
    backendUsername() {
      if (!this.user.loggedIn) return null;
      
      // For OAuth users, use the first name or email prefix
      if (window.__AUTH_USER__) {
        const oauthUser = window.__AUTH_USER__;
        // Use first name if available, otherwise email prefix
        if (oauthUser.name && oauthUser.name.includes(' ')) {
          return oauthUser.name.split(' ')[0]; // "Evan Richardson" -> "Evan"
        }
        return oauthUser.name || oauthUser.email.split('@')[0];
      }
      
      // For legacy users, use the name as-is
      return this.user.name;
    },
    // build pairs from flat gates robustly
    gatePairs() {
      const groups = new Map();
      for (const g of this.timeGates) {
        if (!groups.has(g.pairId)) {
          const customName = this.pairNames.get(g.pairId);
          groups.set(g.pairId, {
            pairId: g.pairId,
            name: customName || g.name || `Gate Pair ${g.pairId}`,
            start: null,
            end: null,
            checkpoints: this.pairCheckpoints.get(g.pairId) || [],
            confirmed: false,
            editing: false
          });
        }
        const entry = groups.get(g.pairId);
        entry[g.type] = g;                             // start or end
        // Use custom name if available, otherwise fallback to gate name
        const customName = this.pairNames.get(g.pairId);
        entry.name = customName || g.name || entry.name;
        entry.confirmed = !!(entry.start?.confirmed && entry.end?.confirmed);
        entry.editing = !!(entry.start?.editing || entry.end?.editing);
        // Keep checkpoints in sync
        entry.checkpoints = this.pairCheckpoints.get(g.pairId) || [];
      }
      return Array.from(groups.values()).filter(p => p.start && p.end);
    }
};
