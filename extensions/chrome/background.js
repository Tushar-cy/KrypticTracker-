// Enhanced Chrome extension background - tracks EVERYTHING including history

const API_URL = 'http://localhost:5000/api';
const API_KEY = 'local-dev-key-change-in-production';

let isLogging = true;
let currentTab = null;
let tabStartTime = Date.now();
let scrollDepth = 0;
let tabHistory = []; // Track tab navigation history

// Helper function to safely parse URLs
function safeParseURL(urlString) {
    if (!urlString || typeof urlString !== 'string') {
        return null;
    }

    // Only parse http/https URLs
    if (!urlString.startsWith('http://') && !urlString.startsWith('https://')) {
        return null;
    }

    try {
        return new URL(urlString);
    } catch (e) {
        return null;
    }
}

// Initialize
chrome.runtime.onInstalled.addListener(() => {
    chrome.storage.local.set({ isLogging: true });
    console.log('KrypticTrack: Extension installed');

    // Start tracking browser history
    startHistoryTracking();
});

// Track browser history
async function startHistoryTracking() {
    // Get recent history items
    chrome.history.search({
        text: '',
        maxResults: 100,
        startTime: Date.now() - 24 * 60 * 60 * 1000 // Last 24 hours
    }, (historyItems) => {
        historyItems.forEach(item => {
            logAction('history_item', {
                url: item.url,
                title: item.title,
                visit_count: item.visitCount,
                last_visit_time: item.lastVisitTime,
                typed_count: item.typedCount || 0,
                timestamp: Date.now()
            });
        });
    });

    // Listen for new history items
    chrome.history.onVisited.addListener((historyItem) => {
        logAction('history_visit', {
            url: historyItem.url,
            title: historyItem.title,
            visit_count: historyItem.visitCount,
            timestamp: Date.now()
        });
    });
}

// Track tab changes with full context
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    if (!isLogging) return;

    const tab = await chrome.tabs.get(activeInfo.tabId);
    const previousTab = currentTab;
    const previousDuration = previousTab ? (Date.now() - tabStartTime) : 0;

    // Log tab_switch with full context
    if (previousTab && previousTab.url) {
        const prevUrl = safeParseURL(previousTab.url);
        const currUrl = safeParseURL(tab.url);

        if (prevUrl || currUrl) {
            logAction('tab_switch', {
                from_url: previousTab.url,
                from_domain: prevUrl ? prevUrl.hostname : 'unknown',
                from_path: prevUrl ? prevUrl.pathname : 'unknown',
                from_protocol: prevUrl ? prevUrl.protocol : 'unknown',
                from_title: previousTab.title || '',
                to_url: tab.url || 'unknown',
                to_domain: currUrl ? currUrl.hostname : 'unknown',
                to_path: currUrl ? currUrl.pathname : 'unknown',
                to_protocol: currUrl ? currUrl.protocol : 'unknown',
                to_title: tab.title || '',
                duration_on_previous: previousDuration,
                timestamp: Date.now()
            });
        } else {
            // Fallback for non-http URLs
            logAction('tab_switch', {
                from_url: previousTab.url || 'unknown',
                to_url: tab.url || 'unknown',
                from_title: previousTab.title || '',
                to_title: tab.title || '',
                duration_on_previous: previousDuration,
                timestamp: Date.now()
            });
        }

        // Add to tab history (only for http/https URLs)
        if (prevUrl) {
            tabHistory.push({
                url: previousTab.url,
                title: previousTab.title,
                duration: previousDuration,
                timestamp: Date.now() - previousDuration
            });
            if (tabHistory.length > 100) tabHistory.shift();
        }
    }

    currentTab = tab;
    tabStartTime = Date.now();
    scrollDepth = 0;

    // Always log tab_visit with full context
    if (tab.url) {
        const url = safeParseURL(tab.url);
        if (url) {
            logAction('tab_visit', {
                url: tab.url,
                domain: url.hostname,
                path: url.pathname,
                protocol: url.protocol,
                search_params: url.search,
                hash: url.hash,
                title: tab.title || '',
                timestamp: Date.now()
            });
        } else {
            // Fallback for non-http URLs (chrome://, about:, etc.)
            logAction('tab_visit', {
                url: tab.url,
                title: tab.title || '',
                timestamp: Date.now()
            });
        }
    }
});

// Track navigation - LOG EVERYTHING
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (!isLogging) return;

    // Log page load when status is complete
    if (changeInfo.status === 'complete' && tab.url) {
        const url = safeParseURL(tab.url);
        if (url) {
            logAction('page_load', {
                url: tab.url,
                domain: url.hostname,
                path: url.pathname,
                protocol: url.protocol,
                search_params: url.search,
                hash: url.hash,
                title: tab.title || '',
                is_active_tab: currentTab && currentTab.id === tabId,
                timestamp: Date.now()
            });
        } else {
            // Fallback for non-http URLs
            logAction('page_load', {
                url: tab.url,
                title: tab.title || '',
                timestamp: Date.now()
            });
        }

        // Update current tab if it's the active one
        if (currentTab && currentTab.id === tabId) {
            currentTab = tab;
            tabStartTime = Date.now();
            scrollDepth = 0;
        }
    }

    // Track URL changes
    if (changeInfo.url && tab.url) {
        const url = safeParseURL(tab.url);
        if (url) {
            logAction('url_change', {
                url: tab.url,
                domain: url.hostname,
                path: url.pathname,
                title: tab.title || '',
                timestamp: Date.now()
            });
        } else {
            // Fallback for non-http URLs
            logAction('url_change', {
                url: tab.url,
                timestamp: Date.now()
            });
        }
    }
});

// Track tab closing
chrome.tabs.onRemoved.addListener((tabId) => {
    if (!isLogging || !currentTab || currentTab.id !== tabId) return;

    const duration = (Date.now() - tabStartTime) / 1000;
    logAction('tab_close', {
        url: currentTab.url || 'unknown',
        duration: duration,
        timestamp: Date.now()
    });
});

// Track new tab creation
chrome.tabs.onCreated.addListener((tab) => {
    if (!isLogging) return;
    logAction('tab_new', {
        url: tab.url || 'new_tab',
        timestamp: Date.now()
    });
});

// Listen for messages from content script - LOG EVERYTHING
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const tabUrl = sender.tab ? sender.tab.url : '';

    if (message.type === 'scroll') {
        scrollDepth = Math.max(scrollDepth, message.scrollPercentage);
        logAction('scroll', {
            scroll_percentage: message.scrollPercentage,
            scroll_velocity: message.scroll_velocity,
            scroll_direction: message.scroll_direction,
            url: tabUrl,
            timestamp: message.timestamp || Date.now()
        });
    } else if (message.type === 'scroll_checkpoint') {
        logAction('scroll_checkpoint', {
            checkpoint: message.percentage,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'keystroke') {
        logAction('keystroke', {
            key: message.key,
            code: message.code,
            timeSinceLastKey: message.timeSinceLastKey,
            isTyping: message.isTyping,
            target: message.target,
            targetType: message.targetType,
            targetId: message.targetId,
            targetClass: message.targetClass,
            cursorPosition: message.cursorPosition,
            textLength: message.textLength,
            typingSpeed: message.typingSpeed,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'keyup') {
        logAction('keyup', {
            key: message.key,
            code: message.code,
            holdDuration: message.holdDuration,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'mouse_move') {
        // Filtered - too high frequency, creates bloat
        return;
    } else if (false && message.type === 'mouse_move') {
        logAction('mouse_move', {
            x: message.x,
            y: message.y,
            velocity: message.velocity,
            elementTag: message.elementTag,
            elementId: message.elementId,
            elementClass: message.elementClass,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'mouse_click') {
        logAction('mouse_click', {
            x: message.x,
            y: message.y,
            clickType: message.clickType,
            clickValue: message.clickValue?.substring(0, 100),
            targetTag: message.targetTag,
            targetId: message.targetId,
            targetClass: message.targetClass,
            button: message.button,
            ctrlKey: message.ctrlKey,
            shiftKey: message.shiftKey,
            altKey: message.altKey,
            metaKey: message.metaKey,
            interactionCount: message.interactionCount,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'mouse_enter' || message.type === 'mouse_leave') {
        // Filtered - too high frequency, creates bloat
        return;
        logAction(message.type, {
            elementTag: message.elementTag,
            elementId: message.elementId,
            elementClass: message.elementClass,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'input_focus' || message.type === 'input_blur') {
        logAction(message.type, {
            inputType: message.inputType,
            name: message.name,
            id: message.id,
            valueLength: message.valueLength || 0,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'text_select') {
        logAction('text_select', {
            selectedText: message.selectedText,
            selectionLength: message.selectionLength,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'copy' || message.type === 'paste') {
        logAction(message.type, {
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'dom_change') {
        // Ignore dom_change - removed from content.js, too basic
        return; // Don't log it
        logAction('dom_change', {
            changeType: message.changeType,
            nodeCount: message.nodeCount,
            targetTag: message.targetTag,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'image_load') {
        logAction('image_load', {
            src: message.src,
            alt: message.alt,
            width: message.width,
            height: message.height,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'window_resize') {
        logAction('window_resize', {
            width: message.width,
            height: message.height,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'window_focus' || message.type === 'window_blur' || message.type === 'page_visibility') {
        logAction(message.type, {
            visible: message.visible,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'video_seek') {
        logAction('video_seek', {
            currentTime: message.currentTime,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'form_input') {
        logAction('form_input', {
            inputType: message.inputType,
            name: message.name,
            id: message.id,
            valueLength: message.valueLength,
            cursorPosition: message.cursorPosition,
            hasValue: message.hasValue,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'form_submit') {
        logAction('form_submit', {
            formId: message.formId,
            formAction: message.formAction,
            fieldCount: message.fieldCount,
            formData: message.formData,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'activity_summary') {
        logAction('activity_summary', {
            timeOnPage: message.timeOnPage,
            keystrokeCount: message.keystrokeCount,
            mouseClickCount: message.mouseClickCount,
            mouseMoveCount: message.mouseMoveCount,
            scrollDepth: message.scrollDepth,
            typingSpeed: message.typingSpeed,
            formInteractions: message.formInteractions,
            buttonClicks: message.buttonClicks,
            linkClicks: message.linkClicks,
            mouseDistance: message.mouseDistance,
            uniqueElementsInteracted: message.uniqueElementsInteracted,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'page_exit') {
        logAction('page_exit', {
            timeOnPage: message.timeOnPage,
            scrollDepth: message.scrollDepth,
            totalKeystrokes: message.totalKeystrokes,
            totalClicks: message.mouseClickCount,
            formInteractions: message.formInteractions,
            buttonClicks: message.buttonClicks,
            linkClicks: message.linkClicks,
            uniqueElementsInteracted: message.uniqueElementsInteracted,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'video_play') {
        logAction('video_play', {
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'video_pause') {
        logAction('video_pause', {
            duration: message.duration,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'video_progress') {
        logAction('video_progress', {
            percentage: message.percentage,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'github_repo_view') {
        logAction('github_repo_view', {
            repo: message.repo,
            path: message.path,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'github_file_view') {
        logAction('github_file_view', {
            file: message.file,
            repo: message.repo,
            url: tabUrl,
            timestamp: message.timestamp
        });
    } else if (message.type === 'search') {
        const tabUrl = sender.tab ? sender.tab.url : '';
        const url = safeParseURL(tabUrl);
        logAction('search', {
            query: message.query,
            searchEngine: message.searchEngine || (url ? url.hostname : 'unknown'),
            domain: url ? url.hostname : 'unknown',
            url: tabUrl,
            timestamp: message.timestamp || Date.now()
        });
    } else if (message.type === 'video_watch') {
        const tabUrl = sender.tab ? sender.tab.url : '';
        const url = safeParseURL(tabUrl);
        logAction('video_watch', {
            url: tabUrl,
            domain: url ? url.hostname : 'unknown',
            duration: message.duration,
            timestamp: Date.now()
        });
    }

    sendResponse({ success: true });
});

// Periodic history sync (every 5 minutes)
setInterval(() => {
    if (!isLogging) return;

    chrome.history.search({
        text: '',
        maxResults: 50,
        startTime: Date.now() - 5 * 60 * 1000 // Last 5 minutes
    }, (historyItems) => {
        historyItems.forEach(item => {
            logAction('history_sync', {
                url: item.url,
                title: item.title,
                visit_count: item.visitCount,
                last_visit_time: item.lastVisitTime,
                timestamp: Date.now()
            });
        });
    });
}, 5 * 60 * 1000);

// Log action to backend - LOG EVERYTHING
async function logAction(actionType, context) {
    if (!isLogging) return;

    try {
        const response = await fetch(`${API_URL}/log-action`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': API_KEY
            },
            body: JSON.stringify({
                source: 'chrome',
                action_type: actionType,
                context: context
            })
        });

        if (!response.ok) {
            console.warn('KrypticTrack: Backend returned error', response.status);
        }
    } catch (error) {
        console.error('KrypticTrack: Failed to log action', error);
    }
}

// Toggle logging
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'toggle_logging') {
        isLogging = !isLogging;
        chrome.storage.local.set({ isLogging: isLogging });
        sendResponse({ isLogging: isLogging });
    }
    return true;
});

// Get current logging status
chrome.storage.local.get(['isLogging'], (result) => {
    isLogging = result.isLogging !== false;
});

// ============================================
// PHASE 2: SMART NOTIFICATIONS SYSTEM
// ============================================

// Notification state tracking
let focusStartTime = null;
let lastBreakNotification = null;
let distractingSiteStartTime = null;
let currentSiteCategory = 'neutral';
let totalFocusTime = 0;

// Site categorization
const PRODUCTIVE_SITES = [
    'github.com', 'stackoverflow.com', 'docs.', 'developer.', 'localhost',
    'learn.', 'tutorial', 'documentation', 'api.', 'dev.'
];

const DISTRACTING_SITES = [
    'youtube.com', 'facebook.com', 'twitter.com', 'reddit.com',
    'instagram.com', 'tiktok.com', 'netflix.com', 'twitch.tv'
];

// Classify site
function classifySite(url) {
    if (!url) return 'neutral';
    const urlLower = url.toLowerCase();

    if (PRODUCTIVE_SITES.some(site => urlLower.includes(site))) {
        return 'productive';
    } else if (DISTRACTING_SITES.some(site => urlLower.includes(site))) {
        return 'distracting';
    }
    return 'neutral';
}

// 1. BREAK REMINDERS (Pomodoro-style)
// Check every minute if user needs a break
chrome.alarms.create('checkBreakTime', { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'checkBreakTime') {
        checkIfBreakNeeded();
    }
});

async function checkIfBreakNeeded() {
    if (!isLogging) return;

    const now = Date.now();

    // Track focus time
    if (currentSiteCategory === 'productive') {
        if (!focusStartTime) {
            focusStartTime = now;
        }

        const focusDuration = (now - focusStartTime) / 1000 / 60; // minutes

        // Notify after 50 minutes of continuous focus
        if (focusDuration >= 50 && (!lastBreakNotification || (now - lastBreakNotification) > 60 * 60 * 1000)) {
            showBreakReminder();
            lastBreakNotification = now;
            focusStartTime = null; // Reset
        }
    } else {
        focusStartTime = null; // Reset if not on productive site
    }
}

function showBreakReminder() {
    chrome.notifications.create('break-reminder', {
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: '🧠 Time for a break!',
        message: 'You\'ve been focused for 50 minutes. Take a 5-minute break to recharge.',
        buttons: [
            { title: 'Start Break (5min)' },
            { title: 'Snooze 10min' }
        ],
        priority: 1
    });
}

// Handle break reminder button clicks
chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
    if (notificationId === 'break-reminder') {
        if (buttonIndex === 0) {
            // Start break - create 5-minute alarm
            chrome.alarms.create('breakEnd', { delayInMinutes: 5 });
            chrome.notifications.clear('break-reminder');

            chrome.notifications.create('break-started', {
                type: 'basic',
                iconUrl: 'icons/icon128.png',
                title: '☕ Break started',
                message: 'Enjoy your 5-minute break. I\'ll remind you when it\'s over.',
                priority: 0
            });
        } else if (buttonIndex === 1) {
            // Snooze - remind again in 10 minutes
            lastBreakNotification = Date.now() - (40 * 60 * 1000); // Will trigger again in 10 min
            chrome.notifications.clear('break-reminder');
        }
    }
});

// Break end notification
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'breakEnd') {
        chrome.notifications.create('break-end', {
            type: 'basic',
            iconUrl: 'icons/icon128.png',
            title: '🚀 Break over!',
            message: 'Ready to get back to work? Let\'s make it productive!',
            priority: 1
        });
    }
});

// 2. DISTRACTION WARNINGS
// Track time on distracting sites
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    const category = classifySite(tab.url);

    // Site changed
    if (category !== currentSiteCategory) {
        // Check if leaving distracting site
        if (currentSiteCategory === 'distracting' && distractingSiteStartTime) {
            const timeSpent = (Date.now() - distractingSiteStartTime) / 1000 / 60;
            if (timeSpent >= 15) {
                // User spent 15+ minutes on distracting site
                logAction('distraction_session', {
                    duration_minutes: timeSpent,
                    timestamp: Date.now()
                });
            }
            distractingSiteStartTime = null;
        }

        // Entering distracting site
        if (category === 'distracting') {
            distractingSiteStartTime = Date.now();

            // Check after 15 minutes
            setTimeout(() => {
                if (currentSiteCategory === 'distracting') {
                    showDistractionWarning();
                }
            }, 15 * 60 * 1000);
        }

        currentSiteCategory = category;
    }
});

function showDistractionWarning() {
    chrome.notifications.create('distraction-warning', {
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: '⚠️ Distraction Alert',
        message: 'You\'ve been on this site for 15 minutes. Time to refocus on your goals?',
        buttons: [
            { title: 'Back to Work' },
            { title: 'Just 5 more min' }
        ],
        priority: 1
    });
}

// Handle distraction warning clicks
chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
    if (notificationId === 'distraction-warning') {
        if (buttonIndex === 0) {
            // Back to work - open dashboard
            chrome.tabs.create({ url: 'http://localhost:3000' });
            chrome.notifications.clear('distraction-warning');
        } else {
            // Snooze
            chrome.notifications.clear('distraction-warning');
        }
    }
});

// 3. GOAL MISALIGNMENT ALERTS
// Check every 30 minutes if user is aligned with goals
chrome.alarms.create('checkGoalAlignment', { periodInMinutes: 30 });

chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'checkGoalAlignment') {
        checkGoalAlignment();
    }
});

async function checkGoalAlignment() {
    if (!isLogging) return;

    try {
        // Fetch active goals from backend
        const response = await fetch(`${API_URL}/goals`, {
            headers: { 'X-API-Key': API_KEY }
        });

        if (!response.ok) return;

        const goals = await response.json();
        const activeGoals = goals.filter(g => g.status === 'active' || !g.status);

        if (activeGoals.length === 0) return;

        // Check if current activity aligns with any goal
        if (currentTab && currentTab.url) {
            const url = currentTab.url.toLowerCase();
            const title = (currentTab.title || '').toLowerCase();

            let aligned = false;
            for (const goal of activeGoals) {
                const keywords = goal.keywords || [];
                const goalText = (goal.goal_text || '').toLowerCase();

                // Check if URL or title contains goal keywords
                if (keywords.some(kw => url.includes(kw.toLowerCase()) || title.includes(kw.toLowerCase()))) {
                    aligned = true;
                    break;
                }

                // Check if goal text is in URL/title
                const goalWords = goalText.split(' ').filter(w => w.length > 3);
                if (goalWords.some(word => url.includes(word) || title.includes(word))) {
                    aligned = true;
                    break;
                }
            }

            // If not aligned and on neutral/distracting site, show alert
            if (!aligned && (currentSiteCategory === 'neutral' || currentSiteCategory === 'distracting')) {
                showGoalMisalignmentAlert(activeGoals[0]);
            }
        }
    } catch (error) {
        console.error('Failed to check goal alignment:', error);
    }
}

function showGoalMisalignmentAlert(goal) {
    chrome.notifications.create('goal-misalignment', {
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: '🎯 Goal Reminder',
        message: `Remember your goal: "${goal.goal_text}". Is this helping you get there?`,
        buttons: [
            { title: 'View Goals' },
            { title: 'Dismiss' }
        ],
        priority: 1
    });
}

// Handle goal misalignment clicks
chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
    if (notificationId === 'goal-misalignment') {
        if (buttonIndex === 0) {
            // View goals
            chrome.tabs.create({ url: 'http://localhost:3000/goals' });
            chrome.notifications.clear('goal-misalignment');
        } else {
            // Dismiss
            chrome.notifications.clear('goal-misalignment');
        }
    }
});

// 4. DAILY SUMMARY NOTIFICATION
// Schedule daily summary at 6 PM
chrome.alarms.create('dailySummary', {
    when: getNextDailySummaryTime(),
    periodInMinutes: 24 * 60
});

function getNextDailySummaryTime() {
    const now = new Date();
    const summary = new Date();
    summary.setHours(18, 0, 0, 0); // 6 PM

    if (now > summary) {
        // If past 6 PM, schedule for tomorrow
        summary.setDate(summary.getDate() + 1);
    }

    return summary.getTime();
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name === 'dailySummary') {
        await showDailySummary();
    }
});

async function showDailySummary() {
    try {
        const response = await fetch(`${API_URL}/stats/quick`, {
            headers: { 'X-API-Key': API_KEY }
        });

        if (!response.ok) return;

        const stats = await response.json();

        chrome.notifications.create('daily-summary', {
            type: 'basic',
            iconUrl: 'icons/icon128.png',
            title: '📊 Daily Productivity Summary',
            message: `Today's score: ${Math.round(stats.focusPercentage || 0)}/100\nFocus time: ${stats.focusedTime || '0m'}\nContext switches: ${stats.contextSwitches || 0}`,
            buttons: [
                { title: 'View Dashboard' }
            ],
            priority: 2
        });
    } catch (error) {
        console.error('Failed to show daily summary:', error);
    }
}

// Handle daily summary click
chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
    if (notificationId === 'daily-summary') {
        if (buttonIndex === 0) {
            chrome.tabs.create({ url: 'http://localhost:3000' });
            chrome.notifications.clear('daily-summary');
        }
    }
});

// Clear notifications when clicked
chrome.notifications.onClicked.addListener((notificationId) => {
    chrome.notifications.clear(notificationId);
});

console.log('KrypticTrack: Smart notifications system initialized');
