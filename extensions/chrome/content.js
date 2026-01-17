// ULTRA-ENHANCED content script - logs EVERYTHING for neural network training

let scrollDepth = 0;
let maxScroll = 0;
let keystrokeCount = 0;
let mouseClickCount = 0;
let mouseMoveCount = 0;
let formInteractions = [];
let buttonClicks = [];
let linkClicks = [];
let timeOnPage = Date.now();
let lastActivity = Date.now();
let isActive = true;
let mouseTrail = []; // Track mouse movement patterns
let keystrokePattern = []; // Track typing patterns
let elementInteractions = new Map(); // Track element-level interactions

// Track page visibility
document.addEventListener('visibilitychange', () => {
    isActive = !document.hidden;
    if (isActive) {
        lastActivity = Date.now();
        chrome.runtime.sendMessage({
            type: 'page_visibility',
            visible: isActive,
            timestamp: Date.now()
        });
    }
});

// Track window focus/blur
window.addEventListener('focus', () => {
    chrome.runtime.sendMessage({
        type: 'window_focus',
        timestamp: Date.now()
    });
});

window.addEventListener('blur', () => {
    chrome.runtime.sendMessage({
        type: 'window_blur',
        timestamp: Date.now()
    });
});

// Track window resize
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        chrome.runtime.sendMessage({
            type: 'window_resize',
            width: window.innerWidth,
            height: window.innerHeight,
            timestamp: Date.now()
        });
    }, 250);
});

// Track scroll depth with more detail
let scrollCheckpoints = [0, 10, 25, 50, 75, 90, 100];
let reachedCheckpoints = new Set();
let lastScrollTime = Date.now();

window.addEventListener('scroll', () => {
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = window.innerHeight;
    
    scrollDepth = Math.max(scrollDepth, (scrollTop + clientHeight) / scrollHeight * 100);
    
    // Track checkpoint milestones
    scrollCheckpoints.forEach(checkpoint => {
        if (scrollDepth >= checkpoint && !reachedCheckpoints.has(checkpoint)) {
            reachedCheckpoints.add(checkpoint);
            chrome.runtime.sendMessage({
                type: 'scroll_checkpoint',
                percentage: checkpoint,
                timestamp: Date.now()
            });
        }
    });
    
    // Log scroll velocity
    const now = Date.now();
    const scrollDelta = scrollTop - (window.lastScrollTop || 0);
    const timeDelta = now - lastScrollTime;
    window.lastScrollTop = scrollTop;
    lastScrollTime = now;
    
    if (timeDelta > 0) {
        chrome.runtime.sendMessage({
            type: 'scroll',
            scroll_percentage: Math.round(scrollDepth),
            scroll_velocity: Math.abs(scrollDelta / timeDelta),
            scroll_direction: scrollDelta > 0 ? 'down' : 'up',
            timestamp: now
        });
    }
});

// Track ALL keystrokes with detailed patterns
let keystrokeBuffer = [];
let lastKeystrokeTime = Date.now();
let typingSession = [];

document.addEventListener('keydown', (e) => {
    if (!isActive) return;
    
    keystrokeCount++;
    const now = Date.now();
    const timeSinceLastKey = now - lastKeystrokeTime;
    lastKeystrokeTime = now;
    
    // Build typing pattern
    const keyData = {
        key: e.key,
        code: e.code,
        keyCode: e.keyCode,
        timeSinceLastKey: timeSinceLastKey,
        isTyping: !e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1,
        target: e.target.tagName,
        targetType: e.target.type,
        targetId: e.target.id,
        targetClass: e.target.className,
        cursorPosition: e.target.selectionStart || 0,
        textLength: e.target.value?.length || 0,
        timestamp: now
    };
    
    typingSession.push(keyData);
    if (typingSession.length > 100) typingSession.shift();
    
    // Track typing speed
    if (timeSinceLastKey < 1000) {
        keystrokeBuffer.push(timeSinceLastKey);
        if (keystrokeBuffer.length > 20) keystrokeBuffer.shift();
    }
    
    chrome.runtime.sendMessage({
        type: 'keystroke',
        ...keyData,
        typingSpeed: calculateTypingSpeed()
    });
});

// Track keyup for key hold duration
let keyPressTimes = new Map();
document.addEventListener('keyup', (e) => {
    const pressTime = keyPressTimes.get(e.code);
    if (pressTime) {
        const holdDuration = Date.now() - pressTime;
        chrome.runtime.sendMessage({
            type: 'keyup',
            key: e.key,
            code: e.code,
            holdDuration: holdDuration,
            timestamp: Date.now()
        });
        keyPressTimes.delete(e.code);
    }
});

document.addEventListener('keydown', (e) => {
    keyPressTimes.set(e.code, Date.now());
});

function calculateTypingSpeed() {
    if (keystrokeBuffer.length < 5) return 0;
    const avgTime = keystrokeBuffer.reduce((a, b) => a + b, 0) / keystrokeBuffer.length;
    if (avgTime === 0) return 0;
    return Math.round((1000 / avgTime) * 60 / 5); // WPM
}

// Track mouse events with patterns
let mouseMoveThrottle = Date.now();
const MOUSE_MOVE_THROTTLE_MS = 100; // More frequent logging

document.addEventListener('mousemove', (e) => {
    if (!isActive) return;
    
    mouseMoveCount++;
    const now = Date.now();
    
    // Track mouse trail
    mouseTrail.push({ x: e.clientX, y: e.clientY, t: now });
    if (mouseTrail.length > 50) mouseTrail.shift();
    
    // Throttle mouse move logging
    if (now - mouseMoveThrottle > MOUSE_MOVE_THROTTLE_MS) {
        mouseMoveThrottle = now;
        
        // Calculate velocity
        const lastMove = mouseTrail[mouseTrail.length - 2];
        let velocity = 0;
        if (lastMove) {
            const dx = e.clientX - lastMove.x;
            const dy = e.clientY - lastMove.y;
            const dt = now - lastMove.t;
            velocity = Math.sqrt(dx * dx + dy * dy) / dt;
        }
        
        // Get element under cursor
        const element = document.elementFromPoint(e.clientX, e.clientY);
        
        chrome.runtime.sendMessage({
            type: 'mouse_move',
            x: e.clientX,
            y: e.clientY,
            velocity: velocity,
            elementTag: element?.tagName || '',
            elementId: element?.id || '',
            elementClass: element?.className || '',
            timestamp: now
        });
    }
});

// Track mouse clicks with more detail
document.addEventListener('click', (e) => {
    if (!isActive) return;
    
    mouseClickCount++;
    const target = e.target;
    
    // Determine what was clicked
    let clickType = 'unknown';
    let clickValue = '';
    
    if (target.tagName === 'A') {
        clickType = 'link';
        clickValue = target.href || target.textContent?.substring(0, 100);
        linkClicks.push({
            href: target.href,
            text: target.textContent?.substring(0, 50),
            timestamp: Date.now()
        });
    } else if (target.tagName === 'BUTTON' || target.type === 'button' || target.type === 'submit') {
        clickType = 'button';
        clickValue = target.textContent?.substring(0, 100) || target.value || target.id || target.className;
        buttonClicks.push({
            text: target.textContent?.substring(0, 50),
            id: target.id,
            className: target.className,
            timestamp: Date.now()
        });
    } else if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        clickType = 'input';
        clickValue = target.type || target.name || target.id;
    } else if (target.tagName === 'IMG') {
        clickType = 'image';
        clickValue = target.src || target.alt || '';
    }
    
    // Track element interaction
    const elementKey = `${target.tagName}-${target.id || target.className}`;
    const interactionCount = elementInteractions.get(elementKey) || 0;
    elementInteractions.set(elementKey, interactionCount + 1);
    
    chrome.runtime.sendMessage({
        type: 'mouse_click',
        x: e.clientX,
        y: e.clientY,
        clickType: clickType,
        clickValue: clickValue?.substring(0, 100),
        targetTag: target.tagName,
        targetId: target.id,
        targetClass: target.className,
        button: e.button,
        ctrlKey: e.ctrlKey,
        shiftKey: e.shiftKey,
        altKey: e.altKey,
        metaKey: e.metaKey,
        interactionCount: interactionCount + 1,
        timestamp: Date.now()
    });
});

// Track mouse hover (enter/leave)
let hoveredElements = new Set();
document.addEventListener('mouseenter', (e) => {
    if (!hoveredElements.has(e.target)) {
        hoveredElements.add(e.target);
        chrome.runtime.sendMessage({
            type: 'mouse_enter',
            elementTag: e.target.tagName,
            elementId: e.target.id,
            elementClass: e.target.className,
            timestamp: Date.now()
        });
    }
}, true);

document.addEventListener('mouseleave', (e) => {
    if (hoveredElements.has(e.target)) {
        hoveredElements.delete(e.target);
        chrome.runtime.sendMessage({
            type: 'mouse_leave',
            elementTag: e.target.tagName,
            elementId: e.target.id,
            elementClass: e.target.className,
            timestamp: Date.now()
        });
    }
}, true);

// Track form interactions with more detail
document.addEventListener('input', (e) => {
    if (!isActive) return;
    
    const target = e.target;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        formInteractions.push({
            type: target.type,
            name: target.name,
            id: target.id,
            valueLength: target.value?.length || 0,
            timestamp: Date.now()
        });
        
        chrome.runtime.sendMessage({
            type: 'form_input',
            inputType: target.type,
            name: target.name,
            id: target.id,
            valueLength: target.value?.length || 0,
            cursorPosition: target.selectionStart || 0,
            hasValue: !!target.value,
            timestamp: Date.now()
        });
    }
});

// Track focus/blur on inputs
document.addEventListener('focus', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        chrome.runtime.sendMessage({
            type: 'input_focus',
            inputType: e.target.type,
            name: e.target.name,
            id: e.target.id,
            timestamp: Date.now()
        });
    }
}, true);

document.addEventListener('blur', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        chrome.runtime.sendMessage({
            type: 'input_blur',
            inputType: e.target.type,
            name: e.target.name,
            id: e.target.id,
            valueLength: e.target.value?.length || 0,
            timestamp: Date.now()
        });
    }
}, true);

// Track text selection
document.addEventListener('selectionchange', () => {
    const selection = window.getSelection();
    if (selection.toString().length > 0) {
        chrome.runtime.sendMessage({
            type: 'text_select',
            selectedText: selection.toString().substring(0, 200),
            selectionLength: selection.toString().length,
            timestamp: Date.now()
        });
    }
});

// Track copy/paste
document.addEventListener('copy', (e) => {
    chrome.runtime.sendMessage({
        type: 'copy',
        timestamp: Date.now()
    });
});

document.addEventListener('paste', (e) => {
    chrome.runtime.sendMessage({
        type: 'paste',
        timestamp: Date.now()
    });
});

// Track form submissions
document.addEventListener('submit', (e) => {
    if (!isActive) return;
    
    const form = e.target;
    const formData = {};
    
    // Collect form data (sanitized)
    Array.from(form.elements).forEach(element => {
        if (element.name && element.value) {
            if (element.type !== 'password') {
                formData[element.name] = element.value.substring(0, 200);
            }
        }
    });
    
    chrome.runtime.sendMessage({
        type: 'form_submit',
        formId: form.id,
        formAction: form.action,
        formMethod: form.method,
        fieldCount: form.elements.length,
        formData: formData,
        timestamp: Date.now()
    });
});

// Track search queries
const searchForms = document.querySelectorAll('form[action*="search"], form[action*="query"], form[role="search"]');
searchForms.forEach(form => {
    form.addEventListener('submit', (e) => {
        const input = form.querySelector('input[type="text"], input[name*="q"], input[name*="query"], input[name*="search"]');
        if (input && input.value) {
            chrome.runtime.sendMessage({
                type: 'search',
                query: input.value,
                searchEngine: window.location.hostname,
                timestamp: Date.now()
            });
        }
    });
});

// DOM change tracking removed - too basic, not useful for IRL training
// Focus on meaningful user interactions instead

// Track image loads
document.querySelectorAll('img').forEach(img => {
    img.addEventListener('load', () => {
        chrome.runtime.sendMessage({
            type: 'image_load',
            src: img.src.substring(0, 200),
            alt: img.alt || '',
            width: img.width,
            height: img.height,
            timestamp: Date.now()
        });
    });
});

// Track YouTube video watch time and interactions
if (window.location.hostname.includes('youtube.com')) {
    const video = document.querySelector('video');
    if (video) {
        let watchTime = 0;
        let lastPlayTime = Date.now();
        let isPlaying = false;
        
        video.addEventListener('play', () => {
            isPlaying = true;
            lastPlayTime = Date.now();
            chrome.runtime.sendMessage({
                type: 'video_play',
                timestamp: Date.now()
            });
        });
        
        video.addEventListener('pause', () => {
            if (isPlaying) {
                watchTime += (Date.now() - lastPlayTime) / 1000;
                chrome.runtime.sendMessage({
                    type: 'video_pause',
                    duration: watchTime,
                    timestamp: Date.now()
                });
            }
            isPlaying = false;
        });
        
        video.addEventListener('ended', () => {
            watchTime += (Date.now() - lastPlayTime) / 1000;
            chrome.runtime.sendMessage({
                type: 'video_end',
                duration: watchTime,
                timestamp: Date.now()
            });
        });
        
        // Track video progress milestones
        const progressCheckpoints = [0.1, 0.25, 0.5, 0.75, 0.9, 1.0];
        const reachedVideoCheckpoints = new Set();
        
        video.addEventListener('timeupdate', () => {
            const progress = video.currentTime / video.duration;
            progressCheckpoints.forEach(checkpoint => {
                if (progress >= checkpoint && !reachedVideoCheckpoints.has(checkpoint)) {
                    reachedVideoCheckpoints.add(checkpoint);
                    chrome.runtime.sendMessage({
                        type: 'video_progress',
                        percentage: checkpoint * 100,
                        timestamp: Date.now()
                    });
                }
            });
        });
        
        // Track video seeking
        video.addEventListener('seeking', () => {
            chrome.runtime.sendMessage({
                type: 'video_seek',
                currentTime: video.currentTime,
                timestamp: Date.now()
            });
        });
        
        window.addEventListener('beforeunload', () => {
            if (isPlaying) {
                watchTime += (Date.now() - lastPlayTime) / 1000;
                chrome.runtime.sendMessage({
                    type: 'video_watch',
                    duration: watchTime,
                    timestamp: Date.now()
                });
            }
        });
    }
}

// Track GitHub activity
if (window.location.hostname.includes('github.com')) {
    const repoName = window.location.pathname.split('/').slice(1, 3).join('/');
    if (repoName && repoName.split('/').length === 2) {
        chrome.runtime.sendMessage({
            type: 'github_repo_view',
            repo: repoName,
            path: window.location.pathname,
            timestamp: Date.now()
        });
    }
    
    if (window.location.pathname.includes('/blob/')) {
        chrome.runtime.sendMessage({
            type: 'github_file_view',
            file: window.location.pathname.split('/').pop(),
            repo: repoName,
            timestamp: Date.now()
        });
    }
}

// Periodic activity summary (every 10 seconds for more data)
setInterval(() => {
    if (!isActive) return;
    
    const timeOnPageNow = (Date.now() - timeOnPage) / 1000;
    const typingSpeed = calculateTypingSpeed();
    
    // Calculate mouse movement patterns
    const mouseDistance = calculateMouseDistance();
    
    chrome.runtime.sendMessage({
        type: 'activity_summary',
        timeOnPage: timeOnPageNow,
        keystrokeCount: keystrokeCount,
        mouseClickCount: mouseClickCount,
        mouseMoveCount: mouseMoveCount,
        scrollDepth: Math.round(scrollDepth),
        typingSpeed: typingSpeed,
        formInteractions: formInteractions.length,
        buttonClicks: buttonClicks.length,
        linkClicks: linkClicks.length,
        mouseDistance: mouseDistance,
        uniqueElementsInteracted: elementInteractions.size,
        timestamp: Date.now()
    });
    
    // Reset counters for next period
    keystrokeCount = 0;
    mouseClickCount = 0;
    mouseMoveCount = 0;
}, 10000); // Every 10 seconds instead of 30

function calculateMouseDistance() {
    if (mouseTrail.length < 2) return 0;
    let distance = 0;
    for (let i = 1; i < mouseTrail.length; i++) {
        const dx = mouseTrail[i].x - mouseTrail[i-1].x;
        const dy = mouseTrail[i].y - mouseTrail[i-1].y;
        distance += Math.sqrt(dx * dx + dy * dy);
    }
    return Math.round(distance);
}

// Final summary when leaving page
window.addEventListener('beforeunload', () => {
    const timeOnPageNow = (Date.now() - timeOnPage) / 1000;
    
    chrome.runtime.sendMessage({
        type: 'page_exit',
        timeOnPage: timeOnPageNow,
        scrollDepth: Math.round(scrollDepth),
        totalKeystrokes: keystrokeCount,
        totalClicks: mouseClickCount,
        formInteractions: formInteractions.length,
        buttonClicks: buttonClicks.length,
        linkClicks: linkClicks.length,
        uniqueElementsInteracted: elementInteractions.size,
        timestamp: Date.now()
    });
});
