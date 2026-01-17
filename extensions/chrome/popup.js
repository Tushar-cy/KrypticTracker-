const API_URL = 'http://localhost:5000/api';
const API_KEY = 'local-dev-key-change-in-production';

let isLogging = true;
let currentTab = null;
let updateInterval = null;

// DOM Elements
const elements = {
    loading: document.getElementById('loading'),
    content: document.getElementById('content'),
    error: document.getElementById('error'),
    productivityScore: document.getElementById('productivityScore'),
    progressRing: document.getElementById('progressRing'),
    focusTime: document.getElementById('focusTime'),
    contextSwitches: document.getElementById('contextSwitches'),
    activeGoals: document.getElementById('activeGoals'),
    peakHour: document.getElementById('peakHour'),
    siteName: document.getElementById('siteName'),
    siteTime: document.getElementById('siteTime'),
    siteBadge: document.getElementById('siteBadge'),
    statusText: document.getElementById('statusText'),
    indicatorDot: document.getElementById('indicatorDot'),
    toggleTracking: document.getElementById('toggleTracking'),
    toggleIcon: document.getElementById('toggleIcon'),
    toggleText: document.getElementById('toggleText'),
    viewDashboard: document.getElementById('viewDashboard'),
    viewGoals: document.getElementById('viewGoals'),
    retryBtn: document.getElementById('retryBtn')
};

// Initialize
async function init() {
    // Load tracking status
    const result = await chrome.storage.local.get(['isLogging']);
    isLogging = result.isLogging !== false;
    updateTrackingUI();

    // Get current tab
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tabs[0];

    // Load stats immediately (no delay)
    loadStats();

    // Start auto-refresh every 10 seconds (reduced from 5s)
    updateInterval = setInterval(loadStats, 10000);

    // Setup event listeners
    setupEventListeners();
}

// Load stats from backend
async function loadStats() {
    try {
        showLoading();

        // Fetch quick stats with 3-second timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);

        const response = await fetch(`${API_URL}/stats/quick`, {
            headers: { 'X-API-Key': API_KEY },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const stats = await response.json();
        displayStats(stats);
        showContent();

    } catch (error) {
        console.error('Failed to load stats:', error);
        showError();
    }
}

// Display stats in UI
function displayStats(stats) {
    // Productivity score (calculate from focus percentage)
    const score = Math.round(stats.focusPercentage || 0);
    elements.productivityScore.textContent = score;
    updateProgressRing(score);

    // Quick stats
    elements.focusTime.textContent = stats.focusedTime || '0m';
    elements.contextSwitches.textContent = stats.contextSwitches || 0;
    elements.activeGoals.textContent = stats.activeGoals || 0;
    elements.peakHour.textContent = stats.peakHour || 'N/A';

    // Current site info
    if (currentTab) {
        const url = new URL(currentTab.url || 'about:blank');
        const domain = url.hostname || 'New Tab';

        elements.siteName.textContent = domain;
        elements.siteTime.textContent = 'Just now'; // TODO: Track time on current site

        // Classify site (simple heuristic for now)
        const classification = classifySite(domain);
        elements.siteBadge.textContent = classification.label;
        elements.siteBadge.className = `site-badge ${classification.type}`;
    }
}

// Classify site as productive/neutral/distracting
function classifySite(domain) {
    const productive = ['github.com', 'stackoverflow.com', 'docs.', 'developer.', 'localhost'];
    const distracting = ['youtube.com', 'facebook.com', 'twitter.com', 'reddit.com', 'instagram.com'];

    if (productive.some(site => domain.includes(site))) {
        return { type: 'productive', label: 'Productive ✅' };
    } else if (distracting.some(site => domain.includes(site))) {
        return { type: 'distracting', label: 'Distracting ⚠️' };
    } else {
        return { type: 'neutral', label: 'Neutral' };
    }
}

// Update circular progress ring
function updateProgressRing(percentage) {
    const circumference = 2 * Math.PI * 52; // radius = 52
    const offset = circumference - (percentage / 100) * circumference;
    elements.progressRing.style.strokeDashoffset = offset;
}

// UI State Management
function showLoading() {
    elements.loading.style.display = 'flex';
    elements.content.style.display = 'none';
    elements.error.style.display = 'none';
}

function showContent() {
    elements.loading.style.display = 'none';
    elements.content.style.display = 'block';
    elements.error.style.display = 'none';
}

function showError() {
    elements.loading.style.display = 'none';
    elements.content.style.display = 'none';
    elements.error.style.display = 'block';
}

// Update tracking status UI
function updateTrackingUI() {
    if (isLogging) {
        elements.indicatorDot.classList.add('active');
        elements.statusText.textContent = 'Neural Active';
        elements.toggleIcon.className = 'ph-bold ph-pause';
        elements.toggleText.textContent = 'Pause Neural Tracking';
        elements.toggleTracking.classList.remove('paused');
    } else {
        elements.indicatorDot.classList.remove('active');
        elements.statusText.textContent = 'Neural Paused';
        elements.toggleIcon.className = 'ph-bold ph-play';
        elements.toggleText.textContent = 'Resume Neural Tracking';
        elements.toggleTracking.classList.add('paused');
    }
}

// Event Listeners
function setupEventListeners() {
    // Toggle tracking
    elements.toggleTracking.addEventListener('click', async () => {
        isLogging = !isLogging;
        await chrome.storage.local.set({ isLogging });
        chrome.runtime.sendMessage({ action: 'toggle_logging' });
        updateTrackingUI();
    });

    // View dashboard
    elements.viewDashboard.addEventListener('click', () => {
        chrome.tabs.create({ url: 'http://localhost:3000' });
    });

    // View goals
    elements.viewGoals.addEventListener('click', () => {
        chrome.tabs.create({ url: 'http://localhost:3000/goals' });
    });

    // Retry button
    elements.retryBtn.addEventListener('click', () => {
        loadStats();
    });
}

// Cleanup on popup close
window.addEventListener('unload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
});

// Start the app
init();
