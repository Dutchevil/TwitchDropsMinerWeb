/**
 * Advanced Mode Feature Enhancements
 * Extends functionality when advanced mode is active
 */

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Setup advanced mode features
    setupAdvancedModeFeatures();
    
    // Add a mutation observer to handle dynamic content
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                if (document.body.classList.contains('mode-advanced')) {
                    enhanceAdvancedMode();
                }
            }
        });
    });
    
    // Start observing the body element for class changes
    observer.observe(document.body, { attributes: true });
});

// Setup event listeners and initialize advanced mode features
function setupAdvancedModeFeatures() {
    // Listen for data updates to populate advanced fields
    document.addEventListener('data-refreshed', function(e) {
        if (document.body.classList.contains('mode-advanced')) {
            updateAdvancedFields(e.detail);
        }
    });
    
    // Set initial values for advanced mode fields
    enhanceAdvancedMode();
}

// Populate advanced mode fields with real diagnostics data only.
// Drop diagnostics are maintained by main.js/drop-progress.js because they
// receive the actual /api/status and /api/active_drop payloads. This file must
// not invent placeholder values such as "Fallback", random drop ids, or fake
// ping values — those make stale UI look trustworthy.
function updateAdvancedFields(data) {
    if (data && data.diagnostics) {
        const buildInfo = document.getElementById('build-info');
        if (buildInfo) buildInfo.textContent = data.diagnostics.buildInfo || '--';

        const platformInfo = document.getElementById('platform-info');
        if (platformInfo) platformInfo.textContent = data.diagnostics.platform || '--';
    }
}

// Apply enhancements when advanced mode is activated
function enhanceAdvancedMode() {
    // Keep system diagnostic placeholders harmless. Live drop diagnostics are
    // populated by the polling code and should remain untouched here.
    const buildInfo = document.getElementById('build-info');
    if (buildInfo && (buildInfo.textContent === '' || buildInfo.textContent === '--')) {
        const appVersion = document.getElementById('app-version')?.textContent;
        buildInfo.textContent = appVersion && appVersion !== 'Unknown' ? appVersion : '--';
    }

    const platformInfo = document.getElementById('platform-info');
    if (platformInfo && (platformInfo.textContent === '' || platformInfo.textContent === '--')) {
        platformInfo.textContent = navigator.platform || '--';
    }
}
