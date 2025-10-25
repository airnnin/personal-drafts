let map;
let floodLayer, landslideLayer, liquefactionLayer, barangayLayer;
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

    // Create layer groups - barangay and flood visible by default
    barangayLayer = L.layerGroup().addTo(map);  // NEW: Barangay boundaries
    floodLayer = L.layerGroup().addTo(map);
    landslideLayer = L.layerGroup();
    liquefactionLayer = L.layerGroup();
    facilityMarkers.addTo(map);

    // Load all data upfront for instant toggling
    loadHazardData();
    loadBarangayBoundaries();
    
    map.on('click', function (e) {
        if (!e.originalEvent.defaultPrevented) {
            onMapClick(e);
        }
    });
}

// NEW: Load barangay boundaries
async function loadBarangayBoundaries() {
    try {
        const response = await fetch('/api/barangay-data/');
        if (response.ok) {
            const barangayData = await response.json();
            addBarangayLayer(barangayData);
        }
    } catch (error) {
        console.error('Error loading barangay boundaries:', error);
    }
}

// NEW: Add barangay boundary layer
function addBarangayLayer(geojsonData) {
    L.geoJSON(geojsonData, {
        style: function(feature) {
            return {
                fillColor: 'transparent',
                weight: 2,
                opacity: 0.8,
                color: '#3b82f6',
                fillOpacity: 0.05,
                dashArray: '5, 5'
            };
        },
        onEachFeature: function(feature, layer) {
            // REMOVED: layer.bindPopup() - No more popup clutter!
            
            // Hover effect
            layer.on('mouseover', function() {
                layer.setStyle({
                    fillOpacity: 0.2,
                    weight: 3,
                    color: '#2563eb'
                });
            });
            
            layer.on('mouseout', function() {
                layer.setStyle({
                    fillOpacity: 0.05,
                    weight: 2,
                    color: '#3b82f6'
                });
            });
            
            // Click handler - still works but no popup
            layer.on('click', function(e) {
                onMapClick(e);
            });
            
            layer.addTo(barangayLayer);
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
        const response = await fetch(`/api/barangay-from-point/?lat=${lat}&lng=${lng}`);
        const locationData = await response.json();
        
        if (response.ok && locationData.success) {
            const area = locationData.area_sqkm 
                ? locationData.area_sqkm.toFixed(2) 
                : 'N/A';
            
            // Build base location info
            let locationHTML = `
                <div class="location-header">
                    <div class="location-icon">📍</div>
                    <div class="location-details">
                        <div class="location-barangay">${locationData.barangay}</div>
                        <div class="location-municipality">${locationData.municipality}, ${locationData.province}</div>
            `;
            
            // Load barangay characteristics if available
            const barangayCode = locationData.barangay_code;
            if (barangayCode) {
                try {
                    const charResponse = await fetch(`/api/barangay-characteristics/?code=${barangayCode}&lat=${lat}&lng=${lng}`);
                    const charData = await charResponse.json();
                    
                    if (charData.found && charData.barangay) {
                        const brgy = charData.barangay;
                        
                        // Add barangay characteristics
                        locationHTML += `
                            <!-- Barangay Characteristics Section -->
                            <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e5e7eb;">
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.85rem; margin-bottom: 0.75rem;">
                                    <!-- Population -->
                                    <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                        <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">👥 Population</div>
                                        <div style="color: #1f2937; font-weight: 700; font-size: 1rem;">${brgy.population_display}</div>
                                    </div>
                                    
                                    <!-- Landscape -->
                                    <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                        <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">🌍 Landscape</div>
                                        <div style="color: #1f2937; font-weight: 700; font-size: 0.85rem;">${brgy.landscape_icon} ${brgy.ecological_landscape || 'N/A'}</div>
                                    </div>
                                </div>
                                
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.85rem;">
                                    <!-- Urbanization -->
                                    <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                        <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">🏘️ Type</div>
                                        <div style="color: #1f2937; font-weight: 700; font-size: 0.85rem;">${brgy.urbanization_icon} ${brgy.urbanization || 'N/A'}</div>
                                    </div>
                                    
                                    <!-- Cellular Signal -->
                                    <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                        <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">📶 Signal</div>
                                        <div style="color: #1f2937; font-weight: 700; font-size: 0.85rem;">${brgy.cellular_signal === 'Yes' ? '✅ Yes' : brgy.cellular_signal === 'No' ? '❌ No' : 'N/A'}</div>
                                    </div>
                                </div>
                                
                                <!-- Street Sweeper -->
                                <div style="margin-top: 0.75rem; background: ${brgy.public_street_sweeper === 'Yes' ? '#d1fae5' : '#fee2e2'}; padding: 0.625rem; border-radius: 6px; text-align: center;">
                                    <div style="font-weight: 600; color: #4b5563; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">🧹 Street Sweeper</div>
                                    <div style="color: #1f2937; font-weight: 700; font-size: 0.95rem;">${brgy.public_street_sweeper === 'Yes' ? '✅ Available' : brgy.public_street_sweeper === 'No' ? '❌ Not Available' : 'N/A'}</div>
                                </div>
                            </div>
                        `;
                        
                        // NEW: Add Facilities Section
                        if (brgy.facilities && brgy.facilities.facilities) {
                            locationHTML += buildFacilitiesSection(brgy.facilities);
                        }
                    }
                } catch (charError) {
                    console.log('No barangay characteristics data available');
                }
            }
            
            // Complete the location info HTML
            locationHTML += `
                        <!-- Area and Region (Original) -->
                        <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e5e7eb;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.85rem;">
                                <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                    <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">Area</div>
                                    <div style="color: #1f2937; font-weight: 700; font-size: 1rem;">${area} km²</div>
                                </div>
                                <div style="background: #f9fafb; padding: 0.625rem; border-radius: 6px;">
                                    <div style="font-weight: 600; color: #4b5563; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem;">Region</div>
                                    <div style="color: #1f2937; font-weight: 700; font-size: 0.8rem;">${locationData.region || 'Central Visayas'}</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="location-coordinates" style="margin-top: 0.75rem;">
                            <span>${lat.toFixed(6)}°N, ${lng.toFixed(6)}°E</span>
                        </div>
                        
                        <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #e5e7eb; font-size: 0.7rem; color: #9ca3af; text-align: center;">
                            📊 Boundary data: PSA-NAMRIA via HumData
                        </div>
                    </div>
                </div>
            `;
            
            locationInfo.innerHTML = locationHTML;
            
            // Load municipality summary on the right side
            if (locationData.municipality_code) {
                loadMunicipalitySummary(locationData.municipality_code);
            }
        } else {
            // Fallback
            locationInfo.innerHTML = `
                <div class="location-header">
                    <div class="location-icon">📍</div>
                    <div class="location-details">
                        <div class="location-barangay">Selected Location</div>
                        <div style="font-size: 0.85rem; color: #f59e0b; margin: 0.5rem 0;">
                            ⚠️ Outside mapped barangay boundaries
                        </div>
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
            const suitability = data.suitability;
            
            let html = `
                <!-- SUITABILITY SCORE CARD - NEW PRIMARY INDICATOR -->
                <div class="suitability-card" style="background: linear-gradient(135deg, ${suitability.color}15 0%, ${suitability.color}25 100%); border: 2px solid ${suitability.color}; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
                    <div style="text-align: center; margin-bottom: 1rem;">
                        <div style="font-size: 0.75rem; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">
                            Development Suitability
                        </div>
                        <div style="font-size: 2.5rem; font-weight: 800; color: ${suitability.color}; line-height: 1; margin-bottom: 0.25rem;">
                            ${suitability.score}
                        </div>
                        <div style="font-size: 0.9rem; color: #9ca3af; font-weight: 600;">/100</div>
                    </div>
                    
                    <div style="width: 100%; height: 14px; background: #e5e7eb; border-radius: 9999px; overflow: hidden; margin-bottom: 1rem; position: relative;">
                        <div style="width: ${suitability.score}%; height: 100%; background: linear-gradient(90deg, ${suitability.color} 0%, ${adjustColorBrightness(suitability.color, -20)} 100%); transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 0 8px ${suitability.color}50;"></div>
                    </div>
                    
                    <div style="background: white; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-size: 1.1rem; font-weight: 700; color: ${suitability.color}; margin-bottom: 0.5rem; text-align: center;">
                            ${suitability.category}
                        </div>
                        <div style="font-size: 0.875rem; color: #4b5563; text-align: center; line-height: 1.6;">
                            ${suitability.recommendation}
                        </div>
                    </div>
                
                    
                    <!-- Suitability Breakdown -->
                    <details style="cursor: pointer;">
                        <summary style="font-size: 0.85rem; color: #6b7280; font-weight: 600; padding: 0.75rem; background: white; border-radius: 6px; margin-bottom: 0.5rem;">
                            📊 View Score Breakdown
                        </summary>
                        <div style="background: white; padding: 1rem; border-radius: 6px; margin-top: 0.5rem;">
                            <!-- DISASTER SAFETY -->
                            <div style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid #e5e7eb;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                    <span style="font-size: 0.85rem; color: #1f2937; font-weight: 700;">🛡️ Disaster Safety (60%)</span>
                                    <span style="font-size: 0.9rem; color: ${suitability.color}; font-weight: 700;">${suitability.breakdown.safety}</span>
                                </div>
                                <div style="width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-bottom: 0.5rem;">
                                    <div style="width: ${(suitability.breakdown.safety / 60) * 100}%; height: 100%; background: ${suitability.color}; transition: width 0.5s;"></div>
                                </div>
                                <p style="margin: 0; font-size: 0.75rem; color: #6b7280; line-height: 1.5;">
                                    ${suitability.breakdown.safety_description}
                                </p>
                            </div>
                            
                            <!-- ACCESSIBILITY -->
                            <div style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid #e5e7eb;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                    <span style="font-size: 0.85rem; color: #1f2937; font-weight: 700;">🏥 Accessibility (20%)</span>
                                    <span style="font-size: 0.9rem; color: ${suitability.color}; font-weight: 700;">${suitability.breakdown.accessibility}</span>
                                </div>
                                <div style="width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-bottom: 0.5rem;">
                                    <div style="width: ${(suitability.breakdown.accessibility / 20) * 100}%; height: 100%; background: ${suitability.color}; transition: width 0.5s;"></div>
                                </div>
                                <p style="margin: 0; font-size: 0.75rem; color: #6b7280; line-height: 1.5;">
                                    ${suitability.breakdown.accessibility_description}
                                </p>
                            </div>
                            
                            <!-- INFRASTRUCTURE -->
                            <div style="margin-bottom: 0;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                    <span style="font-size: 0.85rem; color: #1f2937; font-weight: 700;">🏘️ Infrastructure (20%)</span>
                                    <span style="font-size: 0.9rem; color: ${suitability.color}; font-weight: 700;">${suitability.breakdown.infrastructure}</span>
                                </div>
                                <div style="width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-bottom: 0.5rem;">
                                    <div style="width: ${(suitability.breakdown.infrastructure / 20) * 100}%; height: 100%; background: ${suitability.color}; transition: width 0.5s;"></div>
                                </div>
                                <p style="margin: 0; font-size: 0.75rem; color: #6b7280; line-height: 1.5;">
                                    ${suitability.breakdown.infrastructure_description}
                                </p>
                            </div>
                            
                            <!-- EXPLANATION -->
                            <div style="margin-top: 1rem; padding: 0.75rem; background: #f9fafb; border-radius: 6px; border-left: 3px solid ${suitability.color};">
                                <p style="margin: 0; font-size: 0.7rem; color: #4b5563; line-height: 1.6;">
                                    <em>Disaster safety is weighted at 60% to prioritize life safety over convenience.</em>
                                </p>
                            </div>
                        </div>
                    </details>
                </div>
            `;
            
            // ==========================================
            // 🆕 NEW: ADD ZONAL VALUES HERE
            // ==========================================
            try {
                const barangayResponse = await fetch(`/api/barangay-from-point/?lat=${lat}&lng=${lng}`);
                const barangayData = await barangayResponse.json();
                
                if (barangayData.success && barangayData.barangay_code) {
                    const zonalResponse = await fetch(`/api/zonal-values/?code=${barangayData.barangay_code}`);
                    const zonalData = await zonalResponse.json();
                    
                    if (zonalData.found) {
                        html += buildZonalValuesCard(zonalData);
                    }
                }
            } catch (zonalError) {
                console.log('No zonal value data available:', zonalError);
            }
            // ==========================================
            // END OF ZONAL VALUES SECTION
            // ==========================================
            
            html += `
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
                            <span style="font-size: 0.8rem; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">DISASTER RISK SCORE</span>
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
                    
                    <!-- Collapsible Recommendation Button -->
                    <div class="recommendation-box" style="background: white; border-left: 4px solid ${overall.color}; border-radius: 6px; padding: 0; overflow: hidden; margin-top: 1rem;">
                        <button 
                            onclick="toggleRecommendations()" 
                            id="rec-toggle-btn"
                            style="width: 100%; padding: 1rem; background: ${overall.color}10; border: none; cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s;"
                            onmouseover="this.style.background='${overall.color}20'"
                            onmouseout="this.style.background='${overall.color}10'">
                            <div style="display: flex; align-items: center; gap: 0.75rem;">
                                <span style="font-size: 1.5rem;">💡</span>
                                <div style="text-align: left;">
                                    <div style="font-weight: 700; color: ${overall.color}; font-size: 0.95rem;">View Mitigation Recommendations</div>
                                    <div style="font-size: 0.8rem; color: #6b7280; margin-top: 0.25rem;">${overall.recommendation_summary}</div>
                                </div>
                            </div>
                            <span id="rec-arrow" style="font-size: 1.25rem; color: ${overall.color}; transition: transform 0.3s;">▼</span>
                        </button>
                        <div id="rec-content" style="max-height: 0; overflow: hidden; transition: max-height 0.5s ease-out;">
                            <div style="background: #fafbfc; border-top: 1px solid #e5e7eb;">
                                ${overall.recommendation_details}
                            </div>
                        </div>
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

            // LIQUEFACTION HAZARD CARD
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

// 🆕 NEW FUNCTION: Build Zonal Values Card
function buildZonalValuesCard(zonalData) {
    const stats = zonalData.statistics;
    const values = zonalData.zonal_values;
    
    let html = `
        <!-- ZONAL VALUES CARD -->
        <div class="zonal-values-card" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 2px solid #f59e0b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
            <div style="text-align: center; margin-bottom: 1rem;">
                <div style="font-size: 0.75rem; color: #92400e; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem;">
                    💰 Land Zonal Value
                </div>
                <div style="font-size: 2rem; font-weight: 800; color: #b45309; line-height: 1; margin-bottom: 0.25rem;">
                    ${stats.average_price_display}
                </div>
                <div style="font-size: 0.85rem; color: #78350f; font-weight: 600;">Average Price per m²</div>
            </div>
            
            <!-- Price Range -->
            <div style="background: white; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;">
                    <div>
                        <div style="font-size: 0.7rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;">Lowest</div>
                        <div style="font-size: 1.1rem; font-weight: 700; color: #10b981;">${stats.min_price_display}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.7rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.25rem;">Highest</div>
                        <div style="font-size: 1.1rem; font-weight: 700; color: #ef4444;">${stats.max_price_display}</div>
                    </div>
                </div>
                
                <!-- Price Range Bar -->
                <div style="width: 100%; height: 8px; background: linear-gradient(90deg, #10b981 0%, #f59e0b 50%, #ef4444 100%); border-radius: 4px;"></div>
            </div>
            
            <!-- Zonal Value Details (Collapsible) -->
            <details style="cursor: pointer;">
                <summary style="font-size: 0.85rem; color: #78350f; font-weight: 600; padding: 0.75rem; background: white; border-radius: 6px; margin-bottom: 0.5rem;">
                    📊 View ${stats.count} Zonal Value${stats.count > 1 ? 's' : ''} by Location
                </summary>
                <div style="background: white; padding: 0.75rem; border-radius: 6px; margin-top: 0.5rem; max-height: 300px; overflow-y: auto;">
    `;
    
    // List each zonal value
    values.forEach((value, index) => {
        html += `
            <div style="padding: 0.75rem; background: #fef3c7; border-radius: 6px; margin-bottom: 0.5rem; ${index === values.length - 1 ? 'margin-bottom: 0;' : ''}">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.375rem;">
                    <div style="flex: 1;">
                        <div style="font-weight: 700; font-size: 0.875rem; color: #92400e; margin-bottom: 0.25rem;">
                            ${value.street}
                        </div>
                        ${value.vicinity ? `<div style="font-size: 0.75rem; color: #78350f;">${value.vicinity}</div>` : ''}
                    </div>
                    <div style="text-align: right; margin-left: 0.5rem;">
                        <div style="font-size: 0.95rem; font-weight: 800; color: #b45309;">
                            ${value.price_formatted}
                        </div>
                    </div>
                </div>
                ${value.land_class && value.land_class !== 'N/A' ? `
                    <div style="display: inline-block; background: #fbbf24; color: #78350f; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">
                        ${value.land_class}
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    html += `
                </div>
            </details>
            
            <!-- Data Source -->
            <div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid #fbbf24; font-size: 0.7rem; color: #92400e; text-align: center;">
                📊 Zonal values from BIR/Local Assessor's Office
            </div>
        </div>
    `;
    
    return html;
}

function createHazardCard(icon, title, description, color, severity, level) {
    // Special styling for Debris Flow
    const isDebrisFlow = level === 'DF';
    const cardStyle = isDebrisFlow 
        ? `background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 2px solid ${color}; box-shadow: 0 4px 8px rgba(139, 26, 26, 0.2);`
        : `background: ${color}08; border: 1px solid ${color}40;`;
    
    // ADD THIS WARNING BOX for debris flow
    const debrisFlowWarning = isDebrisFlow 
        ? '<div style="margin-top: 0.5rem; padding: 0.5rem; background: white; border-radius: 4px; font-size: 0.75rem; color: #991b1b; font-weight: 600;">⚡ CONSTRUCTION PROHIBITED - EVACUATION ZONE</div>' 
        : '';
    
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
                    ${debrisFlowWarning}
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
    // NEW: Barangay boundary toggle
    document.getElementById('barangay-toggle').addEventListener('change', function (e) {
        if (e.target.checked) {
            map.addLayer(barangayLayer);
        } else {
            map.removeLayer(barangayLayer);
        }
    });

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
    
    // Show loading with estimated time
    container.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="loading-spinner"></div>
            <p style="color: #6b7280; font-size: 0.875rem; margin-top: 0.5rem;">
                Finding nearby facilities...
            </p>
            <p style="color: #9ca3af; font-size: 0.75rem; margin-top: 0.25rem;">
                📍 Calculating distances to nearby facilities...
            </p>
        </div>
    `;
    
    const startTime = Date.now();
    
    try {
        const response = await fetch(`/api/nearby-facilities/?lat=${lat}&lng=${lng}&radius=3000`);
        
        if (!response.ok) {
            throw new Error('Failed to fetch facilities');
        }
        
        const data = await response.json();
        const loadTime = ((Date.now() - startTime) / 1000).toFixed(1);
        
        console.log(`✅ ${data.counts.total} facilities loaded in ${loadTime} seconds (straight-line distance)`);
        
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
        <!-- EMERGENCY PREPAREDNESS SUMMARY - FIXED VERSION -->
        <div class="emergency-summary" style="background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); border: 2px solid #3b82f6; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; box-shadow: 0 2px 6px rgba(59, 130, 246, 0.15);">
            <h5 style="margin: 0 0 1rem 0; color: #1e40af; font-size: 1.05rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.5rem;">🚨</span>
                <span>Emergency Preparedness</span>
            </h5>
    `;
    
    // FIXED: Nearest Evacuation Center
    if (data.summary.nearest_evacuation) {
        const evac = data.summary.nearest_evacuation;
        const walkIcon = evac.is_walkable ? '✅' : '⚠️';
        const walkStatus = evac.is_walkable ? 'Walking distance' : 'Requires transport';
        const travelTime = evac.duration ? `🚗 ${evac.duration} drive` : '';
        
        html += `
            <div class="facility-summary-card" style="margin-bottom: 0.75rem; padding: 0.875rem; background: white; border-radius: 6px; border-left: 4px solid #10b981;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.375rem; letter-spacing: 0.5px;">Nearest Evacuation Center</div>
                <div style="font-weight: 700; color: #1f2937; font-size: 0.95rem; margin-bottom: 0.25rem;">${walkIcon} ${evac.name}</div>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                    <span style="font-size: 0.875rem; color: #059669; font-weight: 600;">${evac.distance} away</span>
                    <span style="font-size: 0.75rem; color: #6b7280;">${travelTime || walkStatus}</span>
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
    
    // FIXED: Nearest Hospital/Medical Facility (NO DUPLICATES)
    if (data.summary.nearest_hospital) {
        const hosp = data.summary.nearest_hospital;
        const walkIcon = hosp.is_walkable ? '✅' : '⚠️';
        const walkStatus = hosp.is_walkable ? 'Walking distance' : 'Requires transport';
        const travelTime = hosp.duration ? `🚗 ${hosp.duration} drive` : '';
        
        html += `
            <div class="facility-summary-card" style="margin-bottom: 0.75rem; padding: 0.875rem; background: white; border-radius: 6px; border-left: 4px solid #ef4444;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.375rem; letter-spacing: 0.5px;">Nearest Medical Facility</div>
                <div style="font-weight: 700; color: #1f2937; font-size: 0.95rem; margin-bottom: 0.25rem;">${walkIcon} ${hosp.name}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.875rem; color: #059669; font-weight: 600;">${hosp.distance} away</span>
                    <span style="font-size: 0.75rem; color: #6b7280;">${travelTime || walkStatus}</span>
                </div>
            </div>
        `;
    } else {
        html += `
            <div style="padding: 0.875rem; background: #fee2e2; border-radius: 6px; margin-bottom: 0.75rem; border-left: 4px solid #ef4444;">
                <div style="color: #991b1b; font-size: 0.875rem; font-weight: 600;">⚠️ No medical facility within 3km</div>
            </div>
        `;
    }
    
    // FIXED: Nearest Fire Station
    if (data.summary.nearest_fire_station) {
        const fire = data.summary.nearest_fire_station;
        const walkIcon = fire.is_walkable ? '✅' : '⚠️';
        const walkStatus = fire.is_walkable ? 'Walking distance' : 'Requires transport';
        const travelTime = fire.duration ? `🚗 ${fire.duration} drive` : '';
        
        html += `
            <div class="facility-summary-card" style="margin-bottom: 0.75rem; padding: 0.875rem; background: white; border-radius: 6px; border-left: 4px solid #f97316;">
                <div style="font-size: 0.75rem; color: #6b7280; font-weight: 600; text-transform: uppercase; margin-bottom: 0.375rem; letter-spacing: 0.5px;">Nearest Fire Station</div>
                <div style="font-weight: 700; color: #1f2937; font-size: 0.95rem; margin-bottom: 0.25rem;">${walkIcon} ${fire.name}</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.875rem; color: #059669; font-weight: 600;">${fire.distance} away</span>
                    <span style="font-size: 0.75rem; color: #6b7280;">${travelTime || walkStatus}</span>
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
                📍 Data from OpenStreetMap contributors<br>
                <span style="color: #9ca3af; font-size: 0.7rem;">Distances shown are straight-line approximations</span>
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
    // NEW: Add travel time display
    const travelTime = facility.duration_display 
        ? `<span style="font-size: 0.75rem; color: #6b7280;">🚗 ${facility.duration_display} drive</span>` 
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

function toggleRecommendations() {
    const content = document.getElementById('rec-content');
    const arrow = document.getElementById('rec-arrow');
    const button = document.getElementById('rec-toggle-btn');
    
    if (content.style.maxHeight && content.style.maxHeight !== '0px') {
        // Collapse
        content.style.maxHeight = '0px';
        arrow.style.transform = 'rotate(0deg)';
        arrow.textContent = '▼';
    } else {
        // Expand
        content.style.maxHeight = content.scrollHeight + 'px';
        arrow.style.transform = 'rotate(180deg)';
        arrow.textContent = '▲';
    }
}

async function loadMunicipalitySummary(municipalityCode) {
    const panel = document.getElementById('municipality-summary-panel');
    const content = document.getElementById('municipality-summary-content');
    
    // Show panel with loading state
    panel.classList.remove('hidden');
    content.innerHTML = `
        <div style="text-align: center; padding: 1.5rem 0.5rem;">
            <div class="loading-spinner" style="width: 30px; height: 30px; border-width: 3px;"></div>
            <p style="color: #6b7280; font-size: 0.75rem; margin-top: 0.5rem;">Loading...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/municipality-info/?code=${municipalityCode}`);
        const data = await response.json();
        
        if (data.found && data.municipality) {
            const muni = data.municipality;
            
            // Determine poverty color
            let povertyColor = '#10b981';  // Green
            if (muni.poverty_incidence_rate > 30) povertyColor = '#ef4444';  // Red
            else if (muni.poverty_incidence_rate > 20) povertyColor = '#f59e0b';  // Yellow
            
            // Format revenue more compactly
            const revenueShort = muni.revenue >= 1000000 
                ? `₱${(muni.revenue / 1000000).toFixed(1)}M`
                : `₱${(muni.revenue / 1000).toFixed(0)}K`;
            
            // Build COMPACT municipality summary HTML
            content.innerHTML = `
                <!-- Municipality Header -->
                <div class="muni-header">
                    <div class="muni-name">${muni.name}</div>
                    <div class="muni-category">${muni.category}</div>
                </div>
                
                <!-- Population -->
                <div class="muni-stat-card" style="border-left-color: #3b82f6;">
                    <div class="muni-stat-label">👥 POPULATION</div>
                    <div class="muni-stat-value">${muni.population_display}</div>
                </div>
                
                <!-- Revenue - COMPACT -->
                <div class="muni-stat-card" style="border-left-color: #10b981;">
                    <div class="muni-stat-label">💰 REVENUE</div>
                    <div class="muni-stat-value" style="font-size: 0.85rem;">${revenueShort}</div>
                    <div style="font-size: 0.65rem; color: #6b7280; margin-top: 0.125rem;">${muni.revenue_display}</div>
                </div>
                
                <!-- Provincial Score -->
                <div class="muni-stat-card" style="border-left-color: #8b5cf6;">
                    <div class="muni-stat-label">📊 PROVINCIAL SCORE</div>
                    <div class="muni-stat-value">
                        ${muni.provincial_score !== null ? muni.provincial_score.toFixed(2) : 'N/A'}
                    </div>
                </div>
                
                <!-- Poverty Incidence - COMPACT -->
                <div class="muni-stat-card" style="background: linear-gradient(135deg, ${povertyColor}10 0%, ${povertyColor}20 100%); border: 2px solid ${povertyColor}; border-left: 3px solid ${povertyColor};">
                    <div class="muni-stat-label">📉 POVERTY RATE</div>
                    <div class="muni-stat-value" style="color: ${povertyColor};">
                        ${muni.poverty_incidence_rate !== null ? muni.poverty_incidence_rate.toFixed(1) : 'N/A'}%
                    </div>
                    <div style="width: 100%; height: 6px; background: #e5e7eb; border-radius: 3px; overflow: hidden; margin-top: 0.375rem;">
                        <div style="width: ${muni.poverty_incidence_rate}%; height: 100%; background: ${povertyColor}; transition: width 0.8s;"></div>
                    </div>
                </div>
                
                <!-- Data Source - COMPACT -->
                <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #e5e7eb; font-size: 0.6rem; color: #9ca3af; text-align: center; line-height: 1.3;">
                    📊 DTI 2024 Data
                </div>
            `;
        } else {
            content.innerHTML = `
                <div style="text-align: center; padding: 1rem 0.5rem; color: #6b7280;">
                    <div style="font-size: 1.5rem; margin-bottom: 0.375rem;">📭</div>
                    <p style="margin: 0; font-size: 0.75rem;">No data available</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading municipality summary:', error);
        content.innerHTML = `
            <div style="text-align: center; padding: 1rem 0.5rem; color: #ef4444;">
                <div style="font-size: 1.5rem; margin-bottom: 0.375rem;">❌</div>
                <p style="margin: 0; font-size: 0.75rem;">Error loading</p>
            </div>
        `;
    }
}

function setupMunicipalityPanel() {
    const closeBtn = document.getElementById('close-municipality-panel');
    const panel = document.getElementById('municipality-summary-panel');
    
    if (closeBtn && panel) {
        closeBtn.addEventListener('click', function() {
            panel.classList.add('hidden');
        });
    }
}


function buildFacilitiesSection(facilitiesData) {
    const facilities = facilitiesData.facilities;
    const counts = facilitiesData.counts;
    
    let html = `
        <!-- Nearby Facilities Section -->
        <div style="margin-top: 1rem; padding-top: 1rem; border-top: 2px solid #3b82f6;">
            <h5 style="font-size: 0.95rem; font-weight: 700; color: #1f2937; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem;">
                <span>🏢</span>
                <span>Nearby Facilities (within 3km)</span>
            </h5>
    `;
    
    // Education - Elementary
    html += buildFacilityCategory('🎓 Elementary Schools', facilities.education_elementary, counts.education_elementary);
    
    // Education - High School
    html += buildFacilityCategory('🏫 High Schools', facilities.education_highschool, counts.education_highschool);
    
    // Education - College/University
    html += buildFacilityCategory('🎓 Colleges/Universities', facilities.education_college, counts.education_college);
    
    // Hospital
    html += buildFacilityCategory('🏥 Hospitals', facilities.hospital, counts.hospital);
    
    // Health Center/Clinic
    html += buildFacilityCategory('💊 Health Centers/Clinics', facilities.health_center, counts.health_center);
    
    // Fire Station
    html += buildFacilityCategory('🚒 Fire Stations', facilities.fire_station, counts.fire_station);
    
    // Seaport
    html += buildFacilityCategory('⚓ Seaports', facilities.seaport, counts.seaport);
    
    // Post Office
    html += buildFacilityCategory('📮 Post Offices', facilities.post_office, counts.post_office);
    
    html += `</div>`;
    
    return html;
}

// NEW FUNCTION: Build Individual Category
function buildFacilityCategory(title, facilityList, count) {
    if (count === 0) {
        return `
            <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: #fef2f2; border-radius: 6px; border-left: 3px solid #ef4444;">
                <div style="font-weight: 700; font-size: 0.8rem; color: #991b1b; margin-bottom: 0.25rem;">${title}</div>
                <div style="font-size: 0.75rem; color: #7f1d1d;">❌ None within 3km</div>
            </div>
        `;
    }
    
    let html = `
        <details style="margin-bottom: 0.75rem; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb;">
            <summary style="padding: 0.75rem; cursor: pointer; font-weight: 700; font-size: 0.8rem; color: #1f2937; display: flex; justify-content: space-between; align-items: center;">
                <span>${title}</span>
                <span style="background: #3b82f6; color: white; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.7rem;">${count}</span>
            </summary>
            <div style="padding: 0 0.75rem 0.75rem 0.75rem;">
    `;
    
    facilityList.forEach((facility, index) => {
        html += `
            <div style="padding: 0.5rem; background: white; border-radius: 4px; margin-bottom: 0.375rem; display: flex; justify-content: space-between; align-items: center; ${index === facilityList.length - 1 ? 'margin-bottom: 0;' : ''}">
                <div style="font-size: 0.75rem; color: #1f2937; font-weight: 600; flex: 1;">${facility.name}</div>
                <div style="font-size: 0.7rem; color: #059669; font-weight: 700; white-space: nowrap; margin-left: 0.5rem;">📍 ${facility.distance}</div>
            </div>
        `;
    });
    
    html += `
            </div>
        </details>
    `;
    
    return html;
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
    setupMunicipalityPanel();
});