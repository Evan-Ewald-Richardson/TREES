export function createState() {
    return {
        // Map & layers
        map: null,
        trackLayers: [],   // holds polylines + start/end markers for tracks
        selectedTrackIds: [], // holds ids of selected tracks
        gateMarkers: [],   // holds gate markers (for all pairs)
        checkpointMarkers: [], // holds checkpoint markers (for all pairs)

        // UI state
        isDragOver: false,
        loading: false,
        error: null,
        ui: {
          activePanel: null,
        },
        coursesGrid: [], // from /courses_summary
        refreshingCourses: false, // guard to prevent overlapping refreshes
        newCourse: { name: "", description: "", imageFile: null, imagePreview: null },

        // Data
        tracks: [],        // [{id, name, points:[{lat, lon, ele?, time?}], color}]
        trackColors: ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#111827'],
        timeGates: [],      // flat list of gates: {id, pairId, name, type:'start'|'end', lat, lon, confirmed, editing}
        pairCheckpoints: new Map(), // Map of pairId -> array of checkpoints [{lat, lon}]
        pairNames: new Map(), // Map of pairId -> custom name string

        // Constants
        bufferMeters: 10,

        // Creation mode
        isCreatingCourse: false,

        // Leaderboard
        courses: [],
        selectedCourseId: null,
        leaderboard: [],

        // Submit selection for loaded course
        submitRouteId: null,
        selectedCourse: null,

        // User system
        user: {
            loggedIn: false,
            name: "",
            loginName: "",
            leaderboardPositions: [],
            createdCourses: []
        },
        config: { superUserName: null },

        // Strava
        strava: {
            connected: false,
            athlete: null,
            activities: [],
            error: null,
            open: false,
            page: 1,
            perPage: 5,
            hasMore: false,
            loading: false,
            preview: { activityId: null, layer: null }
        },
    };
}
