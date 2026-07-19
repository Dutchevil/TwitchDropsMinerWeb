// File: lazy-loader.js - Handles lazy loading of images and content
// This file contains utility functions for optimizing page performance

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function safeImageUrl(url) {
    const value = String(url || '').trim();
    if (!value) return '';
    if (/^(https?:|data:image\/)/i.test(value)) return value;
    return '';
}

function dropProgressMeta(drop) {
    const requiredMinutes = Number(drop?.required_minutes || 0);
    const currentMinutes = Number(drop?.current_minutes || 0);
    const percent = requiredMinutes > 0 ? Math.min(100, Math.max(0, Math.round((currentMinutes / requiredMinutes) * 100))) : 0;
    const isReady = requiredMinutes > 0 && currentMinutes >= requiredMinutes;
    return { requiredMinutes, currentMinutes, percent, isReady };
}

// Setup lazy loading for images
function setupLazyLoading() {
    // If Intersection Observer isn't supported, load all images immediately
    if (!('IntersectionObserver' in window)) {
        const lazyImages = document.querySelectorAll('.lazy-image');
        lazyImages.forEach(img => {
            if (img.dataset.src) {
                img.src = img.dataset.src;
            }
        });
        return;
    }

    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy-image');
                imageObserver.unobserve(img);
            }
        });
    });

    const lazyImages = document.querySelectorAll('.lazy-image');
    lazyImages.forEach(img => {
        imageObserver.observe(img);
    });
}

// Scroll position management is now handled by scroll-position.js

// These functions are provided for backwards compatibility
// They will be overridden by the scroll-position.js implementations
function saveScrollPosition(tabId) {
    // This is now handled by scroll-position.js
    // Empty implementation for backward compatibility
}

function restoreScrollPosition(tabId) {
    // This is now handled by scroll-position.js
    // Empty implementation for backward compatibility
}

// This will be replaced by the implementation in scroll-position.js
function setupScrollTracking() {
    // Empty implementation for backward compatibility
}

// Preload data in the background
// Make preloadedData available globally for other scripts
window.preloadedData = {
    campaigns: null,
    inventory: null,
    channels: null,
    lastPreloadTime: {
        campaigns: 0,
        inventory: 0,
        channels: 0
    }
};

// For backwards compatibility
let preloadedData = window.preloadedData;

// Preload data for a specific type with cache invalidation
function preloadData(dataType) {
    const now = Date.now();
    const cacheTime = 60000; // 1 minute cache
    
    // If we have recently preloaded this data, don't do it again
    if (now - preloadedData.lastPreloadTime[dataType] < cacheTime) {
        return Promise.resolve(preloadedData[dataType]);
    }
    
    // Set loading state
    // We don't show the progress bar for preloading to avoid distracting the user
    
    let fetchPromise;
    switch (dataType) {
        case 'campaigns':
            fetchPromise = fetch('/api/campaigns')
                .then(response => response.ok ? response.json() : Promise.reject('Error'))
                .then(data => {
                    if (!data.error) {
                        preloadedData.campaigns = data;
                        preloadedData.lastPreloadTime.campaigns = now;
                    }
                    return data;
                });
            break;
        case 'inventory':
            fetchPromise = fetch('/api/inventory')
                .then(response => response.ok ? response.json() : Promise.reject('Error'))
                .then(data => {
                    if (!data.error) {
                        preloadedData.inventory = data;
                        preloadedData.lastPreloadTime.inventory = now;
                    }
                    return data;
                });
            break;
        case 'channels':
            fetchPromise = fetch('/api/channels')
                .then(response => response.ok ? response.json() : Promise.reject('Error'))
                .then(data => {
                    if (!data.error) {
                        preloadedData.channels = data;
                        preloadedData.lastPreloadTime.channels = now;
                    }
                    return data;
                });
            break;
        default:
            return Promise.reject('Invalid data type');
    }
      return fetchPromise.catch(error => {
        // Failed to preload data, silently handle error
        return null;
    });
}

// Preload all data types in the background
function preloadAllData() {
    // Stagger the preloads to avoid overloading the server
    setTimeout(() => preloadData('campaigns'), 500);
    setTimeout(() => preloadData('inventory'), 1000);
    setTimeout(() => preloadData('channels'), 1500);
}

// Check if we have valid preloaded data - make it globally available
function hasValidPreloadedData(dataType) {
    const now = Date.now();
    const cacheTime = 60000; // 1 minute cache
    return preloadedData[dataType] && (now - preloadedData.lastPreloadTime[dataType] < cacheTime);
}

// Make this function available globally for other scripts
window.hasValidPreloadedData = hasValidPreloadedData;

// Get preloaded data if available, otherwise fetch it
function getDataWithPreload(dataType, fetchFunction) {
    if (hasValidPreloadedData(dataType)) {
        // Using preloaded data
        return Promise.resolve(preloadedData[dataType]);
    } else {
        return fetchFunction().then(data => {
            preloadedData[dataType] = data;
            preloadedData.lastPreloadTime[dataType] = Date.now();
            return data;
        });
    }
}

// Set up virtual rendering for campaigns list
// Helper function to create a campaign card - moved from main.js
function createCampaignCard(campaign) {
    const imageUrl = safeImageUrl(campaign.image_url);
    const campaignName = escapeHtml(campaign.name || 'Unknown Campaign');
    const gameName = escapeHtml(campaign.game || 'Unknown Game');
    const status = campaign.status || 'UNKNOWN';
    const isActive = status === 'ACTIVE';
    const isUpcoming = status === 'UPCOMING';
    const isExpired = status === 'EXPIRED';
    const statusClass = isActive ? 'bg-green-100 border-green-500' : (isUpcoming ? 'bg-yellow-100 border-yellow-500' : 'bg-gray-100 border-gray-400');
    const statusTextColor = isActive ? 'text-green-800' : (isUpcoming ? 'text-yellow-800' : 'text-gray-600');
    const statusLabels = [];
    statusLabels.push(isActive ? 'Active' : (isUpcoming ? 'Upcoming' : (isExpired ? 'Expired' : 'Inactive')));
    if (campaign.excluded) statusLabels.push('Excluded');
    if (campaign.linked === false) statusLabels.push('Not Linked');
    else if (campaign.linked === true) statusLabels.push('Linked');
    if (campaign.finished) statusLabels.push('Finished');
    const statusText = statusLabels.join(' · ');

    const campaignCard = document.createElement('div');
    campaignCard.className = 'w-full p-4 bg-blue-50 rounded shadow';

    const dropsHtml = campaign.drops && campaign.drops.length > 0 ?
        `<div class="flex flex-wrap overflow-x-auto pb-2">
            ${campaign.drops.map(drop => {
                const dropImageUrl = safeImageUrl(drop.image_url);
                const dropName = escapeHtml(drop.name || 'Unknown Drop');
                const { requiredMinutes, percent } = dropProgressMeta(drop);
                const progressHtml = drop.claimed ?
                    `<p class="text-xs text-green-600 font-semibold">Claimed</p>` :
                    (requiredMinutes > 0 ?
                        `<p class="text-xs text-gray-600">${percent}% of ${requiredMinutes} min</p>
                        <div class="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                            <div class="bg-green-600 h-1.5 rounded-full" style="width: ${percent}%"></div>
                        </div>` :
                        `<p class="text-xs text-gray-600">No watch time required</p>`);
                return `
                    <div class="mr-4 mb-2 flex flex-col items-center" style="min-width: 100px">
                        ${dropImageUrl ?
                            `<img data-src="${dropImageUrl}" alt="${dropName}" class="w-16 h-16 object-cover rounded lazy-image" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E">` :
                            `<div class="w-16 h-16 bg-gray-200 rounded flex items-center justify-center">
                                <i class="fas fa-gift text-gray-400"></i>
                            </div>`}
                        <div class="mt-1 text-xs text-center">
                            <p class="font-semibold">${dropName}</p>
                            ${progressHtml}
                        </div>
                    </div>
                `;
            }).join('')}
        </div>` :
        `<p class="text-gray-500 text-sm">No drops available</p>`;

    campaignCard.innerHTML = `
        <div class="flex flex-col w-full">
            <div class="flex">
                <div class="w-1/4 flex flex-col items-center pr-3">
                    ${imageUrl ?
                        `<div class="mb-2">
                            <img data-src="${imageUrl}" alt="${campaignName}" class="w-24 h-24 object-cover rounded lazy-image" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E">
                        </div>` :
                        `<div class="mb-2 w-24 h-24 bg-gray-200 rounded flex items-center justify-center">
                            <i class="fas fa-gamepad text-gray-400 text-2xl"></i>
                        </div>`}
                    <h3 class="font-bold text-sm text-center text-gray-800 mb-2">${gameName}</h3>
                    <div class="text-xs text-center">
                        ${campaign.start_time ? `<p class="text-gray-600">Starts: ${new Date(campaign.start_time).toLocaleDateString()}</p>` : ''}
                        ${campaign.end_time ? `<p class="text-gray-600">Ends: ${new Date(campaign.end_time).toLocaleDateString()}</p>` : ''}
                    </div>
                    <div class="mt-2">
                        <span class="px-2 py-1 rounded text-xs font-semibold ${statusTextColor} bg-opacity-70 ${statusClass}">${escapeHtml(statusText)}</span>
                    </div>
                </div>
                <div class="w-3/4 pl-3 border-l">
                    <h3 class="font-bold text-base text-gray-800 mb-3">${campaignName}</h3>
                    ${dropsHtml}
                </div>
            </div>
        </div>
    `;

    return campaignCard;
}

function setupVirtualRendering(container, data, startIndex) {
    // Create a sentinel element that will trigger loading more campaigns when it becomes visible
    const sentinel = document.createElement('div');
    sentinel.className = 'virtual-sentinel';
    sentinel.style.height = '1px';
    sentinel.style.width = '100%';
    container.appendChild(sentinel);
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Load more items
                const fragment = document.createDocumentFragment();
                const batchSize = 20; // Number of items to load at once
                const endIndex = Math.min(startIndex + batchSize, data.length);
                
                for (let i = startIndex; i < endIndex; i++) {
                    const campaign = data[i];
                    const card = createCampaignCard(campaign);
                    fragment.appendChild(card);
                }
                
                // Remove sentinel before appending
                sentinel.remove();
                
                // Append new campaigns before the sentinel
                container.appendChild(fragment);
                
                // If there are more campaigns, add sentinel again and update startIndex
                if (endIndex < data.length) {
                    container.appendChild(sentinel);
                    setupLazyLoading(); // Setup lazy loading for newly added images
                    startIndex = endIndex;
                } else {
                    // Disconnect the observer when all campaigns are loaded
                    observer.disconnect();
                }
            }
        });
    }, { rootMargin: '200px' }); // Start loading more content when sentinel is 200px away from viewport
    
    observer.observe(sentinel);
}

// Set up virtual rendering for drops lists
// Helper function to create a drop card
function createDropCard(drop, type) {
    const dropCard = document.createElement('div');
    
    if (type === 'pending') {
        dropCard.className = 'bg-white rounded shadow mb-4 overflow-hidden';
        
        // Calculate progress. Some Twitch rewards (chat badges, one-off rewards)
        // report required_minutes=0; those are not watch-progress claimable and
        // must not render as NaN% or show a claim button.
        const { requiredMinutes, currentMinutes, percent, isReady } = dropProgressMeta(drop);
        const statusClass = isReady ? 'bg-green-100 border-green-500' : 'bg-blue-100 border-blue-500';
        const safeDropId = escapeHtml(drop.id || '');
        const dropName = escapeHtml(drop.name || 'Unknown Drop');
        const gameName = escapeHtml(drop.game || 'Unknown Game');
        const imageUrl = safeImageUrl(drop.image_url);
        const actionButton = isReady ? 
            `<button class="claim-drop-btn bg-green-500 hover:bg-green-600 text-white py-1 px-3 rounded text-sm" data-drop-id="${safeDropId}">
                <i class="fas fa-gift mr-1"></i> Claim
            </button>` : 
            '';
        
        const imageHtml = imageUrl ? 
            `<div class="mr-3 flex-shrink-0">
                <img data-src="${imageUrl}" alt="${dropName}" class="w-16 h-16 object-cover rounded lazy-image" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E">
            </div>` : 
            '';
        
        dropCard.innerHTML = `
            <div class="border-l-4 ${statusClass} p-4">
                <div class="flex items-center mb-2">
                    ${imageHtml}
                    <div class="flex-grow">
                        <div class="flex justify-between items-start w-full">
                            <div>
                                <h3 class="font-bold text-lg text-gray-800">${dropName}</h3>
                                <p class="text-gray-600">${gameName}</p>
                            </div>
                            <div>
                                ${actionButton}
                            </div>
                        </div>
                        <div class="mt-3">
                            <div class="shadow w-full bg-gray-200 rounded">
                                <div class="bg-purple-600 text-xs leading-none py-1 text-center text-white rounded" style="width: ${percent}%">${percent}%</div>
                            </div>
                            <p class="mt-1 text-sm text-gray-500">${currentMinutes}/${requiredMinutes} minutes watched</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } else {
        dropCard.className = 'bg-green-50 rounded shadow mb-4 border-l-4 border-green-500 p-4';
        
        // Use the same claimed status badge for all drops in this section
        const statusBadge = '<span class="px-2 py-1 rounded text-xs font-semibold bg-green-100 text-green-800">Claimed</span>';
        
        // For auto-moved drops, show completion status; for actually claimed drops, show claim time
        const timeInfo = drop.autoMoved ?
            `<p class="mt-2 text-sm text-gray-500">100% Complete</p>` :
            (drop.claim_time ? `<p class="mt-2 text-sm text-gray-500">Claimed on ${new Date(drop.claim_time).toLocaleString()}</p>` : '');
        
        const imageUrl = safeImageUrl(drop.image_url);
        const dropName = escapeHtml(drop.name || 'Unknown Drop');
        const gameName = escapeHtml(drop.game || 'Unknown Game');
        const imageHtml = imageUrl ? 
            `<div class="mr-3 flex-shrink-0">
                <img data-src="${imageUrl}" alt="${dropName}" class="w-16 h-16 object-cover rounded lazy-image" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E">
            </div>` : 
            '';
        
        dropCard.innerHTML = `
            <div class="flex items-center">
                ${imageHtml}
                <div class="flex-grow">
                    <div class="flex justify-between items-start w-full">
                        <div>
                            <h3 class="font-bold text-lg text-gray-800">${dropName}</h3>
                            <p class="text-gray-600">${gameName}</p>
                        </div>
                        ${statusBadge}
                    </div>
                    ${timeInfo}
                </div>
            </div>
        `;
    }
    
    return dropCard;
}

function setupDropsVirtualRendering(container, items, startIndex, type) {
    // Create a sentinel element that will trigger loading more items when it becomes visible
    const sentinel = document.createElement('div');
    sentinel.className = 'virtual-sentinel';
    sentinel.style.height = '1px';
    sentinel.style.width = '100%';
    container.appendChild(sentinel);
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Load more items
                const fragment = document.createDocumentFragment();
                const batchSize = 10; // Number of items to load at once
                const endIndex = Math.min(startIndex + batchSize, items.length);
                
                for (let i = startIndex; i < endIndex; i++) {
                    const drop = items[i];
                    const dropCard = createDropCard(drop, type);
                    fragment.appendChild(dropCard);
                }
                
                // Remove sentinel before appending
                sentinel.remove();
                
                // Append new items before the sentinel
                container.appendChild(fragment);
                
                // If there are more items, add sentinel again and update startIndex
                if (endIndex < items.length) {
                    container.appendChild(sentinel);
                    setupLazyLoading(); // Setup lazy loading for newly added images
                    startIndex = endIndex;
                } else {
                    // Disconnect the observer when all items are loaded
                    observer.disconnect();
                }
            }
        });
    }, { rootMargin: '200px' }); // Start loading more content when sentinel is 200px away from viewport
    
    observer.observe(sentinel);
}
