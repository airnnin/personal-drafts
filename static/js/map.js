let map;
let floodLayer, landslideLayer, liquefactionLayer;
let currentMarker;
let facilityMarkers = L.layerGroup();

const COLORS = {
    'LS': '#10b981',   // Green - Low
    'MS': '#f59e0b',   // Yellow - Moderate
    'HS': '#f97316',   // Orange - High
    'VHS': '#ef4444',  // Red - Very High
    'DF': '#8b1a1a'    // Dark Red - DEBRIS FLOW (CRITICAL)
};

function initMap() {
    map = L.map('map', {
        zoomControl: false
    }).setView([9.3, 123.3], 9);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    // Create layer groups - only flood visible by default
    floodLayer = L.layerGroup().addTo(map);
    landslideLayer = L.layerGroup();
    liquefactionLayer = L.layerGroup();
    facilityMarkers.addTo(map);

    // Load all data upfront for instant toggling
    loadHazardData();
    
    map.on('click', function (e) {
        if (!e.originalEvent.defaultPrevented) {
            onMapClick(e);
        }
    });
}

async function loadHazardData() {
    try {
        const floodResponse = await fetch('/api/flood-data/');
        if (floodResponse.ok) {
            const floodData = await floodResponse.json();
            addGeoJSONLayer(floodData, floodLayer, 'flood');
        }

        const landslideResponse = await fetch('/api/landslide-data/');
        if (landslideResponse.ok) {
            const landslideData = await landslideResponse.json();
            addGeoJSONLayer(landslideData, landslideLayer, 'landslide');
        }

        const liquefactionResponse = await fetch('/api/liquefaction-data/');
        if (liquefactionResponse.ok) {
            const liquefactionData = await liquefactionResponse.json();
            addGeoJSONLayer(liquefactionData, liquefactionLayer, 'liquefaction');
        }
    } catch (error) {
        console.error('Error loading hazard data:', error);
    }
}

function addGeoJSONLayer(geojsonData, layerGroup, hazardType) {
    L.geoJSON(geojsonData, {
        style: function(feature) {
            const susceptibility = feature.properties.susceptibility;
            let fillColor = COLORS[susceptibility] || '#9ca3af';
            
            // Special styling for Debris Flow - make it highly visible
            let fillOpacity = 0.6;
            let weight = 0.5;
            if (susceptibility === 'DF') {
                fillOpacity = 0.8;  // More opaque for critical debris flow
                weight = 1;  // Thicker border
            }
            
            return {
                fillColor: fillColor,
                weight: weight,
                opacity: 1,
                color: susceptibility === 'DF' ? '#450a0a' : 'rgba(255,255,255,0.4)',
                fillOpacity: fillOpacity
            };
        },
        onEachFeature: function(feature, layer) {
            layer.on('click', function(e) {
                onMapClick(e);
            });
            
            layer.addTo(layerGroup);
        }
    });
}

function onMapClick(e) {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;

    if (currentMarker) {
        map.removeLayer(currentMarker);
    }

    currentMarker = L.marker([lat, lng]).addTo(map);
    showLocationInfo(lat, lng);
}

async function showLocationInfo(lat, lng) {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const locationInfo = document.getElementById('location-info');
    const hazardDetails = document.getElementById('hazard-details');

    sidebar.classList.remove('hidden');
    sidebarToggle.classList.add('sidebar-open');

    locationInfo.innerHTML = `
        <div style="text-align: center; padding: 1rem;">
            <div class="loading-spinner"></div>
            <p style="color: #6b7280; font-size: 0.875rem; margin-top: 0.5rem;">Loading location information...</p>
        </div>
    `;

    try {
        const response = await fetch(`/api/location-info/?lat=${lat}&lng=${lng}`);
        const locationData = await response.json();
        
        if (response.ok && locationData.success) {
            locationInfo.innerHTML = `
                <div class="location-header">
                    <div class="location-icon">📍</div>
                    <div class="location-details">
                        <div class="location-barangay">${locationData.barangay}</div>
                        <div class="location-municipality">${locationData.municipality}, ${locationData.province}</div>
                        <div class="location-coordinates">
                            <span>${lat.toFixed(6)}°N, ${lng.toFixed(6)}°E</span>
                        </div>
                    </div>
                </div>
            `;
        } else {
            locationInfo.innerHTML = `
                <div class="location-header">
                    <div class="location-icon">📍</div>
                    <div class="location-details">
                        <div class="location-barangay">Selected Location</div>
                        <div class="location-coordinates">
                            <span>${lat.toFixed(6)}°N, ${lng.toFixed(6)}°E</span>
                        </div>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error fetching location info:', error);
        locationInfo.innerHTML = `
            <div class="location-header">
                <div class="location-icon">📍</div>
                <div class="location-details">
                    <div class="location-barangay">Selected Location</div>
                    <div class="location-coordinates">
                        <span>${lat.toFixed(6)}°N, ${lng.toFixed(6)}°E</span>
                    </div>
                </div>
            </div>
        `;
    }

    getHazardInfoForLocation(lat, lng, hazardDetails);
    
    const facilitiesContainer = document.getElementById('facilities-section');
    if (facilitiesContainer) {
        loadNearbyFacilities(lat, lng);
    }
}

async function getHazardInfoForLocation(lat, lng, container) {
    container.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="loading-spinner"></div>
            <p style="color: #6b7280; font-size: 0.875rem; margin-top: 0.5rem;">Analyzing disaster risks...</p>
        </div>
    `;

    try {
        const response = await fetch(`/api/location-hazards/?lat=${lat}&lng=${lng}`);
        const data = await response.json();

        if (response.ok) {
            const overall = data.overall_risk;
            
            // IMPROVED: Better visual hierarchy and clearer information
            let html = `
                <!-- OVERALL RISK SCORE CARD - Enhanced Design -->
                <div class="risk-score-card" style="background: linear-gradient(135deg, ${overall.color}15 0%, ${overall.color}25 100%); border: 2px solid ${overall.color}; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
                    <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
                        <div class="risk-icon-large" style="font-size: 3rem; line-height: 1;">${overall.icon}</div>
                        <div style="flex: 1;">
                            <div class="risk-category" style="font-size: 1.4rem; font-weight: 800; color: ${overall.color}; line-height: 1.2; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.5px;">
                                ${overall.category}
                            </div>
                            <div style="font-size: 0.95rem; color: #4b5563; font-weight: 500;">
                                ${overall.message}
                            </div>
                        </div>
                    </div>
                    
                    <!-- Risk Score Bar -->
                    <div class="score-container" style="background: white; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.75rem;">
                            <span style="font-size: 0.8rem; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">RISK SCORE</span>
                            <div>
                                <span style="font-size: 2rem; font-weight: 800; color: ${overall.color};">${overall.score}</span>
                                <span style="font-size: 1.2rem; color: #9ca3af; font-weight: 600;">/100</span>
                            </div>
                        </div>
                        <div style="width: 100%; height: 12px; background: #e5e7eb; border-radius: 9999px; overflow: hidden; position: relative;">
                            <div style="width: ${overall.score}%; height: 100%; background: linear-gradient(90deg, ${overall.color} 0%, ${adjustColorBrightness(overall.color, -20)} 100%); transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 0 8px ${overall.color}50;"></div>
                        </div>
                    </div>
                    
                    <!-- Safety Level Badge -->
                    <div style="display: inline-block; background: ${overall.color}; color: white; padding: 0.5rem 1rem; border-radius: 6px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 1rem;">
                        ${overall.safety_level}
                    </div>
                    
                    <!-- Recommendation Box -->
                    <div class="recommendation-box" style="background: white; border-left: 4px solid ${overall.color}; border-radius: 6px; padding: 1rem; font-size: 0.875rem; line-height: 1.6; color: #374151;">
                        <div style="font-weight: 700; color: ${overall.color}; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem;">
                            <span>💡</span>
                            <span>Recommendation</span>
                        </div>
                        ${overall.recommendation}
                    </div>
                </div>

                <!-- INDIVIDUAL HAZARD BREAKDOWN - Always Visible -->
                <div class="hazard-breakdown-section">
                    <h5 style="font-size: 1rem; font-weight: 700; color: #1f2937; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; padding-bottom: 0.75rem; border-bottom: 2px solid #e5e7eb;">
                        <span>⚠️</span>
                        <span>Hazard Analysis</span>
                    </h5>
                    
                    <div class="hazard-cards">
            `;

            // FLOOD HAZARD CARD
            const floodColor = getColorForLevel(data.flood.level);
            const floodSeverity = getSeverityLevel(data.flood.level);
            html += createHazardCard(
                '🌊',
                'Flood Risk',
                data.flood.risk_label,
                floodColor,
                floodSeverity,
                data.flood.level
            );

            // LANDSLIDE HAZARD CARD
            const landslideColor = getColorForLevel(data.landslide.level);
            const landslideSeverity = getSeverityLevel(data.landslide.level);
            const landslideIcon = data.landslide.level === 'DF' ? '🌋' : '⛰️';
            const landslideTitle = data.landslide.level === 'DF' ? 'DEBRIS FLOW RISK' : 'Landslide Risk';
            html += createHazardCard(
                landslideIcon,
                landslideTitle,
                data.landslide.risk_label,
                landslideColor,
                landslideSeverity,
                data.landslide.level
            );

            // LIQUEFACTION HAZARD CARD (FIXED LABEL)
            const liquefactionColor = getColorForLevel(data.liquefaction.level);
            const liquefactionSeverity = getSeverityLevel(data.liquefaction.level);
            html += createHazardCard(
                '〰️',
                'Liquefaction Risk',
                data.liquefaction.risk_label,
                liquefactionColor,
                liquefactionSeverity,
                data.liquefaction.level
            );

            html += `
                    </div>
                </div>
            `;

            container.innerHTML = html;
        } else {
            container.innerHTML = `
                <div class="error-card">
                    <div style="font-size: 3rem; margin-bottom: 0.5rem;">❌</div>
                    <p style="color: #ef4444; font-weight: 600;">Error loading hazard data</p>
                    <p style="color: #6b7280; font-size: 0.875rem;">${data.error || 'Unable to retrieve information'}</p>
                </div>
            `;
        }
    } catch (error) {
        container.innerHTML = `
            <div class="error-card">
                <div style="font-size: 3rem; margin-bottom: 0.5rem;">❌</div>
                <p style="color: #ef4444; font-weight: 600;">Error retrieving hazard information</p>
                <p style="color: #6b7280; font-size: 0.875rem;">Please try again later</p>
            </div>
        `;
        console.error('Error getting hazard info:', error);
    }
}

function createHazardCard(icon, title, description, color, severity, level) {
    // Special styling for Debris Flow
    const isDebrisFlow = level === 'DF';
    const cardStyle = isDebrisFlow 
        ? `background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 2px solid ${color}; box-shadow: 0 4px 8px rgba(139, 26, 26, 0.2);`
        : `background: ${color}08; border: 1px solid ${color}40;`;
    
    return `
        <div class="hazard-card" style="${cardStyle} border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; transition: all 0.2s;">
            <div style="display: flex; align-items: start; gap: 0.75rem;">
                <div style="font-size: 1.75rem; line-height: 1; flex-shrink: 0;">${icon}</div>
                <div style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <h6 style="font-size: ${isDebrisFlow ? '1rem' : '0.95rem'}; font-weight: 700; color: ${color}; margin: 0; ${isDebrisFlow ? 'text-transform: uppercase; letter-spacing: 0.5px;' : ''}">${title}</h6>
                        ${severity !== 'NONE' ? `<span class="severity-badge" style="background: ${color}; color: white; padding: 0.25rem 0.625rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;">${severity}</span>` : ''}
                    </div>
                    <p style="font-size: 0.875rem; color: #4b5563; line-height: 1.5; margin: 0;">
                        ${description}
                    </p>
                    ${isDebrisFlow ? '<div style="margin-top: 0.5rem; padding: 0.5rem; background: white; border-radius: 4px; font-size: 0.75rem; color: #991b1b; font-weight: 600;">⚡ IMMEDIATE EVACUATION REQUIRED DURING HEAVY RAIN</div>' : ''}
                </div>
            </div>
        </div>
    `;
}

function getSeverityLevel(level) {
    const severityMap = {
        'LS': 'LOW',
        'MS': 'MODERATE',
        'HS': 'HIGH',
        'VHS': 'VERY HIGH',
        'DF': 'CRITICAL',
        null: 'NONE'
    };
    return severityMap[level] || 'UNKNOWN';
}

function getColorForLevel(level) {
    if (!level) return '#10b981';  // No data = GREEN (safe zone)
    return COLORS[level] || '#9ca3af';
}

function adjustColorBrightness(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.max(Math.min(255, (num >> 16) + amt), 0);
    const G = Math.max(Math.min(255, (num >> 8 & 0x00FF) + amt), 0);
    const B = Math.max(Math.min(255, (num & 0x0000FF) + amt), 0);
    return '#' + (0x1000000 + (R << 16) + (G << 8) + B).toString(16).slice(1);
}

// Custom Zoom Controls
function setupCustomZoomControls() {
    const zoomInBtn = document.getElementById('zoom-in-btn');
    const zoomOutBtn = document.getElementById('zoom-out-btn');

    zoomInBtn.addEventListener('click', function() {
        map.zoomIn();
    });

    zoomOutBtn.addEventListener('click', function() {
        map.zoomOut();
    });
}

// Layer Control Panel
function setupLayerControl() {
    const layerControlBtn = document.getElementById('layer-control-btn');
    const layerPanel = document.getElementById('layer-panel');
    const closeLayerPanel = document.getElementById('close-layer-panel');

    layerControlBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        layerPanel.classList.toggle('hidden');
    });

    closeLayerPanel.addEventListener('click', function() {
        layerPanel.classList.add('hidden');
    });

    // Close panel when clicking outside
    document.addEventListener('click', function(e) {
        if (!layerPanel.contains(e.target) && !layerControlBtn.contains(e.target)) {
            layerPanel.classList.add('hidden');
        }
    });
}

// Sidebar controls
function setupSidebarControls() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebarClose = document.getElementById('sidebar-close');

    sidebarToggle.addEventListener('click', function () {
        sidebar.classList.toggle('hidden');
        sidebarToggle.classList.toggle('sidebar-open');
    });

    sidebarClose.addEventListener('click', function () {
        sidebar.classList.add('hidden');
        sidebarToggle.classList.remove('sidebar-open');
    });
}

// Legend Controls
function setupLegendControls() {
    const legend = document.getElementById('legend');
    const legendToggle = document.getElementById('legend-toggle');
    const closeLegend = document.getElementById('close-legend');

    closeLegend.addEventListener('click', function() {
        legend.classList.add('hidden');
        legendToggle.classList.remove('hidden');
    });

    legendToggle.addEventListener('click', function() {
        legend.classList.remove('hidden');
        legendToggle.classList.add('hidden');
    });
}

function setupLayerToggles() {
    document.getElementById('flood-toggle').addEventListener('change', function (e) {
        if (e.target.checked) {
            map.addLayer(floodLayer);
        } else {
            map.removeLayer(floodLayer);
        }
    });

    document.getElementById('landslide-toggle').addEventListener('change', function (e) {
        if (e.target.checked) {
            map.addLayer(landslideLayer);
        } else {
            map.removeLayer(landslideLayer);
        }
    });

    document.getElementById('liquefaction-toggle').addEventListener('change', function (e) {
        if (e.target.checked) {
            map.addLayer(liquefactionLayer);
        } else {
            map.removeLayer(liquefactionLayer);
        }
    });
}

function setupUploadModal() {
    const uploadBtn = document.getElementById('upload-btn');
    const modal = document.getElementById('upload-modal');
    const closeBtn = document.getElementById('close-modal');
    const cancelBtn = document.getElementById('cancel-upload');
    const uploadForm = document.getElementById('upload-form');

    uploadBtn.addEventListener('click', () => {
        modal.classList.remove('hidden');
    });

    closeBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
        resetUploadForm();
    });

    cancelBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
        resetUploadForm();
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
            resetUploadForm();
        }
    });

    uploadForm.addEventListener('submit', handleFileUpload);
}

async function handleFileUpload(e) {
    e.preventDefault();

    const formData = new FormData();
    const fileInput = document.getElementById('shapefile-input');
    const datasetType = document.getElementById('dataset-type').value;

    if (!fileInput.files[0]) {
        alert('Please select a shapefile to upload');
        return;
    }

    if (!datasetType) {
        alert('Please select a dataset type');
        return;
    }

    formData.append('shapefile', fileInput.files[0]);
    formData.append('dataset_type', datasetType);

    showUploadProgress();

    try {
        const response = await fetch('/api/upload-shapefile/', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            showUploadResult(true, `Successfully processed ${result.records_created} records`);
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            showUploadResult(false, result.error || 'Upload failed');
        }
    } catch (error) {
        showUploadResult(false, 'Network error occurred');
        console.error('Upload error:', error);
    }
}

function showUploadProgress() {
    document.getElementById('upload-form').classList.add('hidden');
    document.getElementById('upload-progress').classList.remove('hidden');
}

function showUploadResult(success, message) {
    document.getElementById('upload-progress').classList.add('hidden');
    const resultDiv = document.getElementById('upload-result');
    const messageDiv = document.getElementById('result-message');

    resultDiv.classList.remove('hidden');
    messageDiv.innerHTML = `
        <div style="padding: 1rem; border-radius: 0.5rem; ${success
            ? 'background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7;'
            : 'background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;'}">
            ${message}
        </div>
    `;
}

function resetUploadForm() {
    document.getElementById('upload-form').classList.remove('hidden');
    document.getElementById('upload-progress').classList.add('hidden');
    document.getElementById('upload-result').classList.add('hidden');
    document.getElementById('upload-form').reset();
}

function setupSearch() {
    const searchBtn = document.getElementById('search-btn');
    const searchInput = document.getElementById('location-search');

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
}

async function performSearch() {
    const searchTerm = document.getElementById('location-search').value.trim();
    
    if (!searchTerm) {
        alert('Please enter a location to search');
        return;
    }
    
    try {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/search?` +
            `format=json&q=${encodeURIComponent(searchTerm + ', Negros Oriental, Philippines')}&limit=5`
        );
        
        const results = await response.json();
        
        if (results.length > 0) {
            const lat = parseFloat(results[0].lat);
            const lng = parseFloat(results[0].lon);
            
            map.setView([lat, lng], 15);
            
            if (currentMarker) {
                map.removeLayer(currentMarker);
            }
            
            currentMarker = L.marker([lat, lng]).addTo(map);
            showLocationInfo(lat, lng);
        } else {
            alert('Location not found. Try: "Dumaguete", "Bais", or a barangay name');
        }
        
    } catch (error) {
        console.error('Search error:', error);
        alert('Error searching for location');
    }
}

async function loadNearbyFacilities(lat, lng) {
    const container = document.getElementById('facilities-section');
    container.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="loading-spinner"></div>
            <p style="color: #6b7280; font-size: 0.875rem; margin-top: 0.5rem;">Loading nearby facilities...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/nearby-facilities/?lat=${lat}&lng=${lng}&radius=3000`);
        
        if (!response.ok) {
            throw new Error('Failed to fetch facilities');
        }
        
        const data = await response.json();
        displayFacilities(data);
        
    } catch (error) {
        console.error('Error loading facilities:', error);
        container.innerHTML = `
            <div class="error-card">
                <p style="color: #ef4444; font-weight: 600;">Error loading facilities</p>
                <p style="color: #6b7280; font-size: 0.875rem;">Please try again later</p>
            </div>
        `;
    }
}

function displayFacilities(data) {
    const container = document.getElementById('facilities-section');
    
    facilityMarkers.clearLayers();
    
    if (data.counts.total === 0) {
        container.innerHTML = `
            <div style="padding: 1.5rem; background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📍</div>
                <p style="margin: 0; color: #92400e; font-weight: 600;">No facilities found within 3km radius</p>
            </div>
        `;
        return;
    }
    
    let html = `
        <!-- EMERGENCY READINESS SUMMARY - Enhanced Design -->
        <div class="emergency-summary" style="background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); border: 2px solid #3b82f6; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; box-shadow: 0 2px 6px rgba(59, 130, 246, 0.15);">
            <h5 style="margin: 0 0 1rem 0; color: #1e40af; font-size: 1.05rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.5rem;">🚨</span>
                <span>Emergency Preparedness</span>
            </h5>
    `;
    
    // Nearest Evacuation
    if (data.summary.nearest_evacuation) {
        const evac = data.summary.nearest_evacuation;
        const walkIcon = evac.is_walkable ? '✅' : '⚠️';
        const walkStatus = evac.is_walkable ? 'Walking distance' : 'Requires transport';
        html += `
            <div class="facility-summary-card" style="margin-bottom: 0.75rem; padding: 0.875rem; background: white; border-radius: 6px; border-left: 4px solid #10b981;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.375rem; letter-spacing: 0.5px;">Nearest Evacuation Center</div>
                <div style="font-weight: 700; color: #1f2937; font-size: 0.95rem; margin-bottom: 0.25rem;">${walkIcon} ${evac.name}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.875rem; color: #059669; font-weight: 600;">${evac.distance} away</span>
                    <span style="font-size: 0.75rem; color: #6b7280; font-style: italic;">${walkStatus}</span>
                </div>
            </div>
        `;
    } else {
        html += `
            <div style="padding: 0.875rem; background: #fee2e2; border-radius: 6px; margin-bottom: 0.75rem; border-left: 4px solid #ef4444;">
                <div style="color: #991b1b; font-size: 0.875rem; font-weight: 600;">⚠️ No evacuation center within 3km</div>
                <div style="color: #7f1d1d; font-size: 0.75rem; margin-top: 0.25rem;">Consider identifying alternative safe areas</div>
            </div>
        `;
    }
    
    // Nearest Hospital
    if (data.summary.nearest_hospital) {
        const hosp = data.summary.nearest_hospital;
        const walkIcon = hosp.is_walkable ? '✅' : '⚠️';
        const walkStatus = hosp.is_walkable ? 'Walking distance' : 'Requires transport';
        html += `
            <div class="facility-summary-card" style="margin-bottom: 0.75rem; padding: 0.875rem; background: white; border-radius: 6px; border-left: 4px solid #ef4444;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.375rem; letter-spacing: 0.5px;">Nearest Medical Facility</div>
                <div style="font-weight: 700; color: #1f2937; font-size: 0.95rem; margin-bottom: 0.25rem;">${walkIcon} ${hosp.name}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.875rem; color: #059669; font-weight: 600;">${hosp.distance} away</span>
                    <span style="font-size: 0.75rem; color: #6b7280; font-style: italic;">${walkStatus}</span>
                </div>
            </div>
        `;
    }
    
    html += `
            <div style="font-size: 0.75rem; color: #6b7280; margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid #bfdbfe; text-align: center;">
                ✅ Within 500m walking distance | ⚠️ Requires vehicle
            </div>
        </div>
    `;
    
    // Detailed Facility Lists (Collapsible with better styling)
    if (data.evacuation_centers.length > 0) {
        html += `
            <details class="facility-details" style="margin-bottom: 0.75rem;">
                <summary style="cursor: pointer; font-weight: 700; color: #dc2626; padding: 0.875rem; background: #fee2e2; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #fecaca;">
                    <span>🏠 Evacuation Centers (${data.counts.evacuation})</span>
                    <span style="font-size: 0.875rem;">▼</span>
                </summary>
                <div style="margin-top: 0.5rem; padding: 0.5rem;">
        `;
        data.evacuation_centers.forEach((f, index) => {
            html += createFacilityCard(f, '#dc2626', '#fef2f2', `evac-${index}`);
            addFacilityMarker(f, '#dc2626');
        });
        html += `</div></details>`;
    }
    
    if (data.medical.length > 0) {
        html += `
            <details class="facility-details" style="margin-bottom: 0.75rem;">
                <summary style="cursor: pointer; font-weight: 700; color: #dc2626; padding: 0.875rem; background: #fee2e2; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #fecaca;">
                    <span>🏥 Medical Facilities (${data.counts.medical})</span>
                    <span style="font-size: 0.875rem;">▼</span>
                </summary>
                <div style="margin-top: 0.5rem; padding: 0.5rem;">
        `;
        data.medical.forEach((f, index) => {
            html += createFacilityCard(f, '#dc2626', '#fef2f2', `medical-${index}`);
            addFacilityMarker(f, '#dc2626');
        });
        html += `</div></details>`;
    }
    
    if (data.emergency_services.length > 0) {
        html += `
            <details class="facility-details" style="margin-bottom: 0.75rem;">
                <summary style="cursor: pointer; font-weight: 700; color: #dc2626; padding: 0.875rem; background: #fee2e2; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #fecaca;">
                    <span>🚒 Emergency Services (${data.counts.emergency_services})</span>
                    <span style="font-size: 0.875rem;">▼</span>
                </summary>
                <div style="margin-top: 0.5rem; padding: 0.5rem;">
        `;
        data.emergency_services.forEach((f, index) => {
            html += createFacilityCard(f, '#dc2626', '#fef2f2', `emergency-${index}`);
            addFacilityMarker(f, '#dc2626');
        });
        html += `</div></details>`;
    }
    
    if (data.essential_services.length > 0) {
        html += `
            <details class="facility-details" style="margin-bottom: 0.75rem;">
                <summary style="cursor: pointer; font-weight: 700; color: #2563eb; padding: 0.875rem; background: #dbeafe; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #93c5fd;">
                    <span>🛒 Essential Services (${data.counts.essential})</span>
                    <span style="font-size: 0.875rem;">▼</span>
                </summary>
                <div style="margin-top: 0.5rem; padding: 0.5rem;">
        `;
        data.essential_services.forEach((f, index) => {
            html += createFacilityCard(f, '#2563eb', '#eff6ff', `essential-${index}`);
            addFacilityMarker(f, '#2563eb');
        });
        html += `</div></details>`;
    }
    
    html += `
        <div style="margin-top: 1.5rem; padding: 0.875rem; background: #f9fafb; border-radius: 6px; text-align: center; border: 1px solid #e5e7eb;">
            <p style="margin: 0; font-size: 0.75rem; color: #6b7280;">
                📍 Data from OpenStreetMap contributors
            </p>
        </div>
    `;
    
    container.innerHTML = html;
    attachFacilityClickListeners();
}

function createFacilityCard(facility, borderColor, bgColor, facilityId) {
    const walkBadge = facility.is_walkable 
        ? '<span style="background: #10b981; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">WALKABLE</span>'
        : '';
    
    return `
        <div class="facility-card" data-facility-id="${facilityId}" data-lat="${facility.lat}" data-lng="${facility.lng}" 
             style="padding: 0.75rem; border-left: 3px solid ${borderColor}; margin-bottom: 0.5rem; background: ${bgColor}; 
                    border-radius: 0 6px 6px 0; cursor: pointer; transition: all 0.2s; border: 1px solid ${borderColor}30;"
             onmouseover="this.style.backgroundColor='${adjustColorBrightness(bgColor, -5)}'; this.style.transform='translateX(4px)'; this.style.boxShadow='0 2px 6px rgba(0,0,0,0.1)';"
             onmouseout="this.style.backgroundColor='${bgColor}'; this.style.transform='translateX(0)'; this.style.boxShadow='none';">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.375rem;">
                <div style="font-weight: 700; font-size: 0.875rem; color: #1f2937;">
                    ${facility.name}
                </div>
                ${walkBadge}
            </div>
            <div style="font-size: 0.8rem; color: #6b7280; margin-bottom: 0.375rem;">
                ${facility.type_display}
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.8rem; color: #059669; font-weight: 600;">
                    📍 ${facility.distance_display} away
                </span>
                <span style="font-size: 0.7rem; color: #3b82f6; font-style: italic;">
                    Click to view
                </span>
            </div>
        </div>
    `;
}

function addFacilityMarker(facility, color) {
    const icon = L.divIcon({
        className: 'custom-facility-marker',
        html: `<div style="background-color: ${color}; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });
    
    const marker = L.marker([facility.lat, facility.lng], { icon: icon })
        .bindPopup(`
            <div style="min-width: 150px;">
                <strong style="display: block; margin-bottom: 0.5rem;">${facility.name}</strong>
                <div style="font-size: 0.85rem; color: #6b7280;">${facility.type_display}</div>
                <div style="font-size: 0.85rem; color: #059669; font-weight: 600; margin-top: 0.25rem;">
                    ${facility.distance_display} away
                </div>
            </div>
        `);
    
    facilityMarkers.addLayer(marker);
}

function attachFacilityClickListeners() {
    const facilityCards = document.querySelectorAll('.facility-card');
    
    facilityCards.forEach(card => {
        card.addEventListener('click', function() {
            const lat = parseFloat(this.dataset.lat);
            const lng = parseFloat(this.dataset.lng);
            
            map.setView([lat, lng], 17, {
                animate: true,
                duration: 0.5
            });
            
            facilityMarkers.eachLayer(layer => {
                if (layer instanceof L.Marker) {
                    const markerLatLng = layer.getLatLng();
                    if (Math.abs(markerLatLng.lat - lat) < 0.00001 && 
                        Math.abs(markerLatLng.lng - lng) < 0.00001) {
                        layer.openPopup();
                    }
                }
            });
        });
    });
}

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    initMap();
    setupCustomZoomControls();
    setupLayerControl();
    setupSidebarControls();
    setupLegendControls();
    setupLayerToggles();
    setupUploadModal();
    setupSearch();
});