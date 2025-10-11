from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.gis.geos import Point
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility
from .utils import ShapefileProcessor
from .utils import RoadDistanceCalculator
from .overpass_client import OverpassClient
from math import radians, cos, sin, asin, sqrt
import json

def index(request):
    """Main map view"""
    return render(request, 'index.html')

@csrf_exempt
@api_view(['POST'])
def upload_shapefile(request):
    """Handle shapefile upload and processing"""
    if request.method == 'POST':
        if 'shapefile' not in request.FILES:
            return JsonResponse({'error': 'No shapefile provided'}, status=400)
        
        if 'dataset_type' not in request.POST:
            return JsonResponse({'error': 'Dataset type not specified'}, status=400)
        
        uploaded_file = request.FILES['shapefile']
        dataset_type = request.POST['dataset_type']
        
        valid_types = ['flood', 'landslide', 'liquefaction', 'barangay']
        if dataset_type not in valid_types:
            return JsonResponse({'error': f'Invalid dataset type. Must be one of: {valid_types}'}, status=400)
        
        processor = ShapefileProcessor(uploaded_file, dataset_type)
        result = processor.process()
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse({'error': result['error']}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@api_view(['GET'])
def get_flood_data(request):
    """Get flood susceptibility data as GeoJSON"""
    try:
        flood_features = []
        flood_records = FloodSusceptibility.objects.all()
        
        for record in flood_records:
            feature = {
                'type': 'Feature',
                'properties': {
                    'susceptibility': record.flood_susc,
                    'original_code': record.original_code,
                    'shape_area': record.shape_area,
                    'dataset_id': record.dataset.id
                },
                'geometry': json.loads(record.geometry.geojson)
            }
            flood_features.append(feature)
        
        geojson_data = {
            'type': 'FeatureCollection',
            'features': flood_features
        }
        
        return Response(geojson_data)
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_landslide_data(request):
    """Get landslide susceptibility data as GeoJSON"""
    try:
        landslide_features = []
        landslide_records = LandslideSusceptibility.objects.all()
        
        for record in landslide_records:
            feature = {
                'type': 'Feature',
                'properties': {
                    'susceptibility': record.landslide_susc,
                    'original_code': record.original_code,
                    'shape_area': record.shape_area,
                    'dataset_id': record.dataset.id
                },
                'geometry': json.loads(record.geometry.geojson)
            }
            landslide_features.append(feature)
        
        geojson_data = {
            'type': 'FeatureCollection',
            'features': landslide_features
        }
        
        return Response(geojson_data)
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_liquefaction_data(request):
    """Get liquefaction susceptibility data as GeoJSON"""
    try:
        liquefaction_features = []
        liquefaction_records = LiquefactionSusceptibility.objects.all()
        
        for record in liquefaction_records:
            feature = {
                'type': 'Feature',
                'properties': {
                    'susceptibility': record.liquefaction_susc,
                    'original_code': record.original_code,
                    'dataset_id': record.dataset.id
                },
                'geometry': json.loads(record.geometry.geojson)
            }
            liquefaction_features.append(feature)
        
        geojson_data = {
            'type': 'FeatureCollection',
            'features': liquefaction_features
        }
        
        return Response(geojson_data)
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_location_hazards(request):
    """Get hazard levels for a specific point location"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        
        point = Point(lng, lat, srid=4326)
        
        flood_result = FloodSusceptibility.objects.filter(
            geometry__contains=point
        ).first()
        
        landslide_result = LandslideSusceptibility.objects.filter(
            geometry__contains=point
        ).first()
        
        liquefaction_result = LiquefactionSusceptibility.objects.filter(
            geometry__contains=point
        ).first()
        
        # Extract levels
        flood_level = flood_result.flood_susc if flood_result else None
        landslide_level = landslide_result.landslide_susc if landslide_result else None
        liquefaction_level = liquefaction_result.liquefaction_susc if liquefaction_result else None
        
        # Calculate overall risk
        risk_assessment = calculate_risk_score(flood_level, landslide_level, liquefaction_level)
        
        # NEW: Get nearby facilities for suitability calculation
        try:
            nearby_facilities = get_nearby_facilities_for_suitability(lat, lng)
        except Exception as e:
            print(f"Error getting facilities for suitability: {e}")
            nearby_facilities = {'counts': {}, 'summary': {}}
        
        # NEW: Calculate suitability score
        suitability = calculate_suitability_score(
            lat, lng,
            {'overall_risk': risk_assessment},
            nearby_facilities
        )
        
        return Response({
            'overall_risk': risk_assessment,
            'suitability': suitability,  # NEW: Added suitability score
            'flood': {
                'level': flood_level,
                'label': flood_result.get_flood_susc_display() if flood_result else 'No Data Available',
                'risk_label': get_user_friendly_label(flood_level, 'flood')
            },
            'landslide': {
                'level': landslide_level,
                'label': landslide_result.get_landslide_susc_display() if landslide_result else 'No Data Available',
                'risk_label': get_user_friendly_label(landslide_level, 'landslide')
            },
            'liquefaction': {
                'level': liquefaction_level,
                'label': liquefaction_result.get_liquefaction_susc_display() if liquefaction_result else 'No Data Available',
                'risk_label': get_user_friendly_label(liquefaction_level, 'liquefaction')
            }
        })
        
    except ValueError:
        return Response({'error': 'Invalid coordinates'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    
@api_view(['GET'])
def get_nearby_facilities(request):
    """Get facilities within specified radius with disaster-priority grouping"""
    from .utils import RoadDistanceCalculator
    
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = int(request.GET.get('radius', 3000))
        
        # Get facilities from Overpass
        facilities = OverpassClient.query_facilities(lat, lng, radius)
        
        # Calculate ROAD distances for all facilities
        print(f"🚗 Calculating road distances for {len(facilities)} facilities...")
        facilities = RoadDistanceCalculator.batch_calculate_distances(lat, lng, facilities)
        
        # Update display format and add metadata
        for facility in facilities:
            facility['distance_display'] = format_distance(facility['distance_meters'])
            facility['is_walkable'] = facility['distance_meters'] <= 500
            
            # Add travel time display
            if facility.get('duration_minutes'):
                if facility['duration_minutes'] < 1:
                    facility['duration_display'] = "< 1 min"
                else:
                    facility['duration_display'] = f"{int(facility['duration_minutes'])} min"
            else:
                facility['duration_display'] = "N/A"
        
        # Sort by actual road distance
        facilities.sort(key=lambda x: x['distance_meters'])
        
        # Log road vs straight-line comparison
        road_count = sum(1 for f in facilities if f.get('method') == 'road')
        print(f"✅ Road distances: {road_count}/{len(facilities)}, Fallback: {len(facilities) - road_count}")
        
        # Reorganize by disaster priority
        evacuation_centers = []
        medical = []
        emergency_services = []
        essential_services = []
        other_facilities = []
        
        for f in facilities:
            ftype = f.get('facility_type', '')
            
            # Priority 1: Evacuation Centers
            if ftype in ['school', 'community_centre', 'kindergarten', 'college', 'university']:
                f['subcategory'] = 'evacuation'
                f['priority'] = 1
                evacuation_centers.append(f)
            
            # Priority 2: Medical Facilities
            elif ftype in ['hospital', 'clinic', 'doctors', 'pharmacy']:
                f['subcategory'] = 'medical'
                f['priority'] = 2
                medical.append(f)
            
            # Priority 3: Emergency Services
            elif ftype in ['fire_station', 'police']:
                f['subcategory'] = 'emergency_services'
                f['priority'] = 3
                emergency_services.append(f)
            
            # Priority 4: Essential Services
            elif ftype in ['marketplace', 'supermarket', 'convenience']:
                f['subcategory'] = 'essential'
                f['priority'] = 4
                essential_services.append(f)
            
            # Priority 5: Other
            else:
                f['subcategory'] = 'other'
                f['priority'] = 5
                other_facilities.append(f)
        
        # Find nearest of each critical type
        nearest_evacuation = evacuation_centers[0] if evacuation_centers else None
        nearest_hospital = next((f for f in medical if f.get('facility_type') in ['hospital', 'clinic']), None)
        nearest_fire = next((f for f in emergency_services if f.get('facility_type') == 'fire_station'), None)
        
        result = {
            'summary': {
                'nearest_evacuation': {
                    'name': nearest_evacuation.get('name', 'Unknown'),
                    'distance': nearest_evacuation.get('distance_display', 'N/A'),
                    'distance_meters': nearest_evacuation.get('distance_meters', 999999),
                    'duration': nearest_evacuation.get('duration_display', 'N/A'),
                    'is_walkable': nearest_evacuation.get('is_walkable', False),
                } if nearest_evacuation else None,
                'nearest_hospital': {
                    'name': nearest_hospital.get('name', 'Unknown'),
                    'distance': nearest_hospital.get('distance_display', 'N/A'),
                    'distance_meters': nearest_hospital.get('distance_meters', 999999),
                    'duration': nearest_hospital.get('duration_display', 'N/A'),
                    'is_walkable': nearest_hospital.get('is_walkable', False),
                } if nearest_hospital else None,
                'nearest_fire_station': {
                    'name': nearest_fire.get('name', 'Unknown'),
                    'distance': nearest_fire.get('distance_display', 'N/A'),
                    'distance_meters': nearest_fire.get('distance_meters', 999999),
                    'duration': nearest_fire.get('duration_display', 'N/A'),
                    'is_walkable': nearest_fire.get('is_walkable', False),
                } if nearest_fire else None,
            },
            'evacuation_centers': evacuation_centers[:10],
            'medical': medical[:10],
            'emergency_services': emergency_services[:10],
            'essential_services': essential_services[:10],
            'other': other_facilities[:10],
            'counts': {
                'evacuation': len(evacuation_centers),
                'medical': len(medical),
                'emergency_services': len(emergency_services),
                'essential': len(essential_services),
                'other': len(other_facilities),
                'total': len(facilities)
            }
        }
        
        return Response(result)
        
    except ValueError:
        return Response({'error': 'Invalid coordinates or radius'}, status=400)
    except Exception as e:
        print(f"Error in get_nearby_facilities: {e}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


def get_nearby_facilities_for_suitability(lat, lng):
    """
    Helper function to get nearby facilities data for suitability calculation
    Uses REAL ROAD DISTANCES via OSRM
    """
    from .overpass_client import OverpassClient
    from .utils import RoadDistanceCalculator
    
    try:
        # Get facilities from Overpass API
        facilities = OverpassClient.query_facilities(lat, lng, 3000)
        
        # Calculate ROAD distances
        print(f"🚗 Calculating road distances for {len(facilities)} facilities...")
        facilities = RoadDistanceCalculator.batch_calculate_distances(lat, lng, facilities)
        
        # Update display format
        for facility in facilities:
            facility['distance_display'] = format_distance(facility['distance_meters'])
            facility['is_walkable'] = facility['distance_meters'] <= 500
            
            # Add travel time info
            if facility.get('duration_minutes'):
                if facility['duration_minutes'] < 1:
                    facility['duration_display'] = "< 1 min"
                else:
                    facility['duration_display'] = f"{int(facility['duration_minutes'])} min"
            else:
                facility['duration_display'] = "N/A"
        
        # Sort by road distance
        facilities.sort(key=lambda x: x['distance_meters'])
        
        # Log road vs straight-line comparison
        road_count = sum(1 for f in facilities if f.get('method') == 'road')
        print(f"✅ Road distances: {road_count}/{len(facilities)}, Fallback: {len(facilities) - road_count}")
        
        # Categorize facilities
        evacuation_centers = []
        medical = []
        emergency_services = []
        essential_services = []
        other_facilities = []
        
        for f in facilities:
            ftype = f.get('facility_type', '')
            
            if ftype in ['school', 'community_centre', 'kindergarten', 'college', 'university']:
                f['subcategory'] = 'evacuation'
                f['priority'] = 1
                evacuation_centers.append(f)
            elif ftype in ['hospital', 'clinic', 'doctors', 'pharmacy']:
                f['subcategory'] = 'medical'
                f['priority'] = 2
                medical.append(f)
            elif ftype in ['fire_station', 'police']:
                f['subcategory'] = 'emergency_services'
                f['priority'] = 3
                emergency_services.append(f)
            elif ftype in ['marketplace', 'supermarket', 'convenience']:
                f['subcategory'] = 'essential'
                f['priority'] = 4
                essential_services.append(f)
            else:
                f['subcategory'] = 'other'
                f['priority'] = 5
                other_facilities.append(f)
        
        # Find nearest critical facilities
        nearest_evacuation = evacuation_centers[0] if evacuation_centers else None
        nearest_hospital = next((f for f in medical if f.get('facility_type') in ['hospital', 'clinic']), None)
        nearest_fire = next((f for f in emergency_services if f.get('facility_type') == 'fire_station'), None)
        
        return {
            'summary': {
                'nearest_evacuation': {
                    'name': nearest_evacuation.get('name', 'Unknown') if nearest_evacuation else None,
                    'distance': nearest_evacuation.get('distance_display', 'N/A') if nearest_evacuation else None,
                    'distance_meters': nearest_evacuation.get('distance_meters', 999999) if nearest_evacuation else 999999,
                    'duration': nearest_evacuation.get('duration_display', 'N/A') if nearest_evacuation else None,
                    'is_walkable': nearest_evacuation.get('is_walkable', False) if nearest_evacuation else False,
                } if nearest_evacuation else None,
                'nearest_hospital': {
                    'name': nearest_hospital.get('name', 'Unknown') if nearest_hospital else None,
                    'distance': nearest_hospital.get('distance_display', 'N/A') if nearest_hospital else None,
                    'distance_meters': nearest_hospital.get('distance_meters', 999999) if nearest_hospital else 999999,
                    'duration': nearest_hospital.get('duration_display', 'N/A') if nearest_hospital else None,
                    'is_walkable': nearest_hospital.get('is_walkable', False) if nearest_hospital else False,
                } if nearest_hospital else None,
                'nearest_fire_station': {
                    'name': nearest_fire.get('name', 'Unknown') if nearest_fire else None,
                    'distance': nearest_fire.get('distance_display', 'N/A') if nearest_fire else None,
                    'distance_meters': nearest_fire.get('distance_meters', 999999) if nearest_fire else 999999,
                    'duration': nearest_fire.get('duration_display', 'N/A') if nearest_fire else None,
                    'is_walkable': nearest_fire.get('is_walkable', False) if nearest_fire else False,
                } if nearest_fire else None,
            },
            'counts': {
                'evacuation': len(evacuation_centers),
                'medical': len(medical),
                'emergency_services': len(emergency_services),
                'essential': len(essential_services),
                'other': len(other_facilities),
                'total': len(facilities)
            }
        }
    except Exception as e:
        print(f"ERROR in get_nearby_facilities_for_suitability: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'summary': {
                'nearest_evacuation': None,
                'nearest_hospital': None,
                'nearest_fire_station': None,
            },
            'counts': {
                'evacuation': 0,
                'medical': 0,
                'emergency_services': 0,
                'essential': 0,
                'other': 0,
                'total': 0
            }
        }

def get_user_friendly_label(level, hazard_type):
    """Convert technical labels to citizen-friendly descriptions"""
    if not level:
        return 'Not at risk - No hazard data for this area (safe zone)'
    
    DESCRIPTIONS = {
        'flood': {
            'LS': 'Low risk - Flooding unlikely in this area',
            'MS': 'Moderate risk - Minor flooding possible during heavy rain',
            'HS': 'High risk - Frequent flooding expected during typhoons',
            'VHS': 'Very high risk - Severe flooding likely, area may become submerged'
        },
        'landslide': {
            'LS': 'Low risk - Stable ground, slopes are secure',
            'MS': 'Moderate risk - Some slope movement possible during heavy rain',
            'HS': 'High risk - Slopes may collapse during typhoons or earthquakes',
            'VHS': 'Very high risk - Steep unstable slopes, landslides expected during storms',
            'DF': 'CRITICAL RISK - Debris Flow Zone: Massive fast-moving landslides carrying rocks, mud, and debris. Extremely dangerous during heavy rain. EVACUATION REQUIRED.'
        },
        'liquefaction': {
            'LS': 'Low risk - Soil remains stable during earthquakes',
            'MS': 'Moderate risk - During strong earthquakes, ground may shift slightly',
            'HS': 'High risk - During earthquakes, ground may turn soft like quicksand, causing buildings to sink or tilt'
        }
    }
    
    return DESCRIPTIONS.get(hazard_type, {}).get(level, 'Risk level unknown')


def calculate_risk_score(flood_level, landslide_level, liquefaction_level):
    """
    IMPROVED ALGORITHM based on Philippine disaster frequency and severity
    
    Methodology:
    - Based on NDRRMC disaster statistics (2010-2024)
    - Follows PHIVOLCS hazard assessment guidelines
    - Debris Flow = automatic critical risk (no-build zone)
    - Combined hazards receive exponential penalty
    
    Weights:
    - Flood: 60% (most frequent disaster in Philippines)
    - Landslide: 25% (severe but less frequent)
    - Liquefaction: 15% (only during earthquakes)
    """
    
    # PRIORITY 1: Debris Flow = Automatic CRITICAL RISK (overrides everything)
    if landslide_level == 'DF':
        rec_data = generate_debris_flow_critical_warning()
        return {
            'score': 100,
            'raw_score': 100,
            'category': 'CRITICAL - DEBRIS FLOW ZONE',
            'message': '⛔ NO-BUILD ZONE - Construction prohibited by PHIVOLCS',
            'color': '#7f1d1d',
            'icon': '🚫',
            'safety_level': 'EVACUATION REQUIRED',
            'recommendation_summary': rec_data['summary'],
            'recommendation_details': rec_data['details']
        }
    
    # Base hazard severity scores (0-100 scale)
    SEVERITY_SCORES = {
        None: 0,   # No data = assume safe (no hazard present)
        'LS': 20,  # Low susceptibility
        'MS': 40,  # Moderate susceptibility
        'HS': 70,  # High susceptibility
        'VHS': 100 # Very high susceptibility
    }
    
    # Get base scores
    flood_score = SEVERITY_SCORES.get(flood_level, 0)
    landslide_score = SEVERITY_SCORES.get(landslide_level, 0)
    liquefaction_score = SEVERITY_SCORES.get(liquefaction_level, 0)
    
    # IMPROVED WEIGHTING based on Philippine disaster statistics
    # Dynamic weighting - only count hazards that are present
    total_weight = 0
    weighted_score = 0
    
    if flood_level:
        flood_weight = 0.6  # 60% - Floods are most frequent (typhoons, monsoon)
        weighted_score += flood_score * flood_weight
        total_weight += flood_weight
    
    if landslide_level:
        landslide_weight = 0.25  # 25% - Severe but less frequent than floods
        weighted_score += landslide_score * landslide_weight
        total_weight += landslide_weight
    
    if liquefaction_level:
        liquefaction_weight = 0.15  # 15% - Only during earthquakes (rare)
        weighted_score += liquefaction_score * liquefaction_weight
        total_weight += liquefaction_weight
    
    # Normalize score based on present hazards
    if total_weight > 0:
        final_score = weighted_score / total_weight
    else:
        final_score = 0  # No hazards present = completely safe
    
    # COMBINED HAZARD PENALTY
    # Multiple high-level hazards increase risk exponentially
    high_hazards_count = sum([
        1 if flood_level in ['HS', 'VHS'] else 0,
        1 if landslide_level in ['HS', 'VHS'] else 0,
        1 if liquefaction_level == 'HS' else 0
    ])
    
    # Apply 25% penalty for each additional high-risk hazard
    if high_hazards_count >= 2:
        final_score = min(100, final_score * 1.25)  # Cap at 100
    
    # Categorize overall risk
    if final_score < 25:
        category = 'LOW RISK'
        message = 'Suitable for development with standard precautions'
        color = '#10b981'  # Green
        icon = '✅'
        safety_level = 'SAFE'
    elif final_score < 50:
        category = 'MODERATE RISK'
        message = 'Development acceptable with engineering controls'
        color = '#f59e0b'  # Yellow
        icon = '⚠️'
        safety_level = 'CAUTION'
    elif final_score < 75:
        category = 'HIGH RISK'
        message = 'Significant mitigation required - consult engineers'
        color = '#f97316'  # Orange
        icon = '⚠️'
        safety_level = 'WARNING'
    else:
        category = 'VERY HIGH RISK'
        message = 'Development strongly discouraged - relocation recommended'
        color = '#ef4444'  # Red
        icon = '🚫'
        safety_level = 'DANGER'
    
    # Generate specific recommendations
    rec_data = generate_smart_recommendations(flood_level, landslide_level, liquefaction_level)
    
    return {
        'score': round(min(final_score, 100), 1),  # Display score (capped at 100)
        'raw_score': round(final_score, 1),        # Actual calculated score
        'category': category,
        'message': message,
        'color': color,
        'icon': icon,
        'safety_level': safety_level,
        'recommendation_summary': rec_data['summary'],
        'recommendation_details': rec_data['details']
    }

def generate_debris_flow_critical_warning():
    """
    Special critical warning for Debris Flow zones
    These are NO-BUILD zones per PHIVOLCS directive
    """
    return {
        'summary': 'DEBRIS FLOW ZONE - No Construction Allowed',
        'details': '''
            <div style="padding: 1rem; line-height: 1.8;">
                <div style="background: #7f1d1d; color: white; padding: 1.25rem; border-radius: 8px; margin-bottom: 1rem;">
                    <h6 style="margin: 0 0 0.75rem 0; font-size: 1.2rem; font-weight: 800;">
                        🚨 CRITICAL HAZARD ZONE
                    </h6>
                    <p style="margin: 0; font-size: 0.95rem; line-height: 1.6;">
                        This area is designated as a <strong>DEBRIS FLOW SUSCEPTIBILITY ZONE</strong> 
                        by the Philippine Institute of Volcanology and Seismology (PHIVOLCS).
                    </p>
                </div>
                
                <div style="background: #fef2f2; padding: 1rem; border-radius: 6px; border: 2px solid #dc2626; margin-bottom: 1rem;">
                    <h6 style="color: #991b1b; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">
                        What is a Debris Flow?
                    </h6>
                    <p style="margin: 0 0 0.75rem 0; color: #7f1d1d; font-size: 0.9rem;">
                        Debris flows are <strong>catastrophic landslides</strong> that move at high speeds 
                        (up to 50 km/h), carrying massive amounts of rocks, soil, trees, and water. 
                        They can:
                    </p>
                    <ul style="margin: 0 0 0 1.5rem; color: #7f1d1d; font-size: 0.9rem;">
                        <li>Bury structures within minutes</li>
                        <li>Destroy buildings completely</li>
                        <li>Cause massive casualties</li>
                        <li>Travel several kilometers from source</li>
                    </ul>
                </div>
                
                <div style="background: #450a0a; color: white; padding: 1rem; border-radius: 6px; margin-bottom: 1rem;">
                    <h6 style="font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">
                        ⛔ PHIVOLCS DIRECTIVE
                    </h6>
                    <p style="margin: 0; font-size: 0.9rem; font-weight: 600;">
                        CONSTRUCTION IS STRICTLY PROHIBITED IN THIS ZONE
                    </p>
                </div>
                
                <div style="background: white; padding: 1rem; border-radius: 6px; border: 1px solid #e5e7eb;">
                    <h6 style="color: #1f2937; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 0.95rem;">
                        Required Actions:
                    </h6>
                    <ul style="margin: 0 0 0 1.5rem; line-height: 1.8; font-size: 0.875rem; color: #4b5563;">
                        <li><strong>Do NOT purchase or develop land in this area</strong></li>
                        <li><strong>If currently inhabited:</strong> Coordinate with Local Government Unit (LGU) and DSWD for relocation assistance</li>
                        <li><strong>Evacuation Protocol:</strong> Mandatory evacuation during heavy rainfall (&gt;100mm/24hrs)</li>
                        <li><strong>Land Use:</strong> Area suitable only for reforestation, watershed protection, or buffer zone</li>
                        <li><strong>Early Warning:</strong> Install community rain gauges and establish evacuation routes</li>
                    </ul>
                </div>
                
                <div style="background: #eff6ff; padding: 1rem; border-radius: 6px; border-left: 4px solid #3b82f6; margin-top: 1rem;">
                    <strong style="color: #1e40af; font-size: 0.9rem;">📞 Contact for Assistance:</strong><br>
                    <span style="font-size: 0.85rem; color: #1e40af;">
                        • PHIVOLCS Regional Office<br>
                        • Local Disaster Risk Reduction and Management Office (LDRRMO)<br>
                        • Department of Social Welfare and Development (DSWD) for relocation programs
                    </span>
                </div>
            </div>
        '''
    }

def calculate_suitability_score(lat, lng, hazard_data, nearby_facilities):
    """
    Calculate infrastructure development suitability score (0-100)
    
    IMPROVED FORMULA - Disaster Safety is now the DOMINANT factor
    
    Factors considered:
    1. Disaster Safety (60% weight) - PRIMARY CONSIDERATION
    2. Access to Critical Facilities (20% weight) - SECONDARY
    3. Community Infrastructure (20% weight) - SECONDARY
    """
    
    # 1. DISASTER SAFETY COMPONENT (60% weight)
    hazard_score = hazard_data['overall_risk']['score']
    
    # Special case: Debris Flow = 0 suitability
    if hazard_data['overall_risk']['safety_level'] == 'EVACUATION REQUIRED':
        return {
            'score': 0,
            'category': 'NOT SUITABLE',
            'color': '#7f1d1d',
            'recommendation': '⛔ Debris Flow Zone - Construction Prohibited by PHIVOLCS',
            'breakdown': {
                'safety': 0,
                'safety_description': 'Critical hazard zone - no construction allowed',
                'accessibility': 0,
                'accessibility_description': 'Not applicable - area is prohibited for development',
                'infrastructure': 0,
                'infrastructure_description': 'Not applicable - area is prohibited for development'
            }
        }
    
    # Calculate safety score (inverse of hazard)
    safety_score = (100 - hazard_score) * 0.6
    
    # Generate safety description
    if hazard_score >= 75:
        safety_desc = 'Very high disaster risk - extensive mitigation required'
    elif hazard_score >= 50:
        safety_desc = 'High disaster risk - significant engineering controls needed'
    elif hazard_score >= 25:
        safety_desc = 'Moderate disaster risk - standard precautions sufficient'
    else:
        safety_desc = 'Low disaster risk - safe for development'
    
    # 2. ACCESSIBILITY COMPONENT (20% weight)
    accessibility_score = 0
    
    # Check nearest evacuation center - USE distance_meters directly
    if nearby_facilities.get('summary', {}).get('nearest_evacuation'):
        evac_data = nearby_facilities['summary']['nearest_evacuation']
        evac_distance_m = evac_data.get('distance_meters', 999999)
        evac_distance_km = evac_distance_m / 1000
        
        # Scoring: 100 if within 500m, decreasing to 0 at 5km
        evac_score = max(0, min(100, 100 - ((evac_distance_km - 0.5) / 4.5) * 100))
        accessibility_score += evac_score * 0.5
    
    # Check nearest hospital - USE distance_meters directly
    if nearby_facilities.get('summary', {}).get('nearest_hospital'):
        hosp_data = nearby_facilities['summary']['nearest_hospital']
        hosp_distance_m = hosp_data.get('distance_meters', 999999)
        hosp_distance_km = hosp_distance_m / 1000
        
        # Scoring: 100 if within 1km, decreasing to 0 at 10km
        hosp_score = max(0, min(100, 100 - ((hosp_distance_km - 1) / 9) * 100))
        accessibility_score += hosp_score * 0.5
    
    accessibility_component = accessibility_score * 0.2
    
    # Generate accessibility description
    if accessibility_score >= 75:
        access_desc = 'Excellent access - hospitals and evacuation centers within walking distance or very close by for emergency response'
    elif accessibility_score >= 50:
        access_desc = 'Good access - hospitals and evacuation centers reachable within 10-15 minutes by vehicle'
    elif accessibility_score >= 25:
        access_desc = 'Moderate access - hospitals and evacuation centers 15-30 minutes away by vehicle'
    else:
        access_desc = 'Poor access - hospitals and evacuation centers far away (30+ minutes), emergency response difficult'
    
    # 3. COMMUNITY INFRASTRUCTURE COMPONENT (20% weight)
    infrastructure_score = 0
    
    # Count facilities in each category
    evac_count = nearby_facilities.get('counts', {}).get('evacuation', 0)
    medical_count = nearby_facilities.get('counts', {}).get('medical', 0)
    emergency_count = nearby_facilities.get('counts', {}).get('emergency_services', 0)
    essential_count = nearby_facilities.get('counts', {}).get('essential', 0)
    
    # Scoring based on facility diversity
    if evac_count >= 3:
        infrastructure_score += 25
    elif evac_count >= 1:
        infrastructure_score += 15
    
    if medical_count >= 2:
        infrastructure_score += 25
    elif medical_count >= 1:
        infrastructure_score += 15
    
    if emergency_count >= 2:
        infrastructure_score += 25
    elif emergency_count >= 1:
        infrastructure_score += 15
    
    if essential_count >= 5:
        infrastructure_score += 25
    elif essential_count >= 2:
        infrastructure_score += 15
    
    infrastructure_component = min(100, infrastructure_score) * 0.2
    
    # Generate infrastructure description
    total_facilities = nearby_facilities.get('counts', {}).get('total', 0)
    
    if total_facilities >= 15:
        infra_desc = f'Well-developed area with {medical_count} medical facilities, {evac_count} evacuation centers, and {essential_count} essential services nearby'
    elif total_facilities >= 8:
        infra_desc = f'Adequate development with {medical_count} medical facilities, {evac_count} evacuation centers, and {essential_count} essential services within 3km'
    elif total_facilities >= 3:
        infra_desc = f'Basic development - {total_facilities} facilities nearby including {medical_count} medical and {evac_count} evacuation centers'
    else:
        infra_desc = f'Underdeveloped area - very limited facilities ({total_facilities} total) within 3km'
    
    # TOTAL SUITABILITY SCORE
    total_suitability = safety_score + accessibility_component + infrastructure_component
    
    # Apply additional penalty for very high risk areas
    if hazard_score >= 75:
        total_suitability = total_suitability * 0.8
    
    # Categorize suitability
    if total_suitability >= 70:
        category = 'HIGHLY SUITABLE'
        color = '#10b981'
        recommendation = 'Excellent location for development. Low disaster risk with good infrastructure and accessibility.'
    elif total_suitability >= 50:
        category = 'MODERATELY SUITABLE'
        color = '#f59e0b'
        recommendation = 'Acceptable for development with proper planning and standard precautions. Some disaster risk present.'
    elif total_suitability >= 30:
        category = 'MARGINALLY SUITABLE'
        color = '#f97316'
        recommendation = 'Development possible but challenging. High disaster risk requires extensive mitigation.'
    else:
        category = 'NOT SUITABLE'
        color = '#ef4444'
        recommendation = 'Not recommended for development. Very high disaster risk and/or inadequate infrastructure.'
    
    return {
        'score': round(total_suitability, 1),
        'category': category,
        'color': color,
        'recommendation': recommendation,
        'breakdown': {
            'safety': round(safety_score, 1),
            'safety_description': safety_desc,
            'accessibility': round(accessibility_component, 1),
            'accessibility_description': access_desc,
            'infrastructure': round(infrastructure_component, 1),
            'infrastructure_description': infra_desc
        }
    }


def generate_smart_recommendations(flood_level, landslide_level, liquefaction_level):
    """
    Generate recommendations based on Philippine government guidelines:
    - PHIVOLCS (Philippine Institute of Volcanology and Seismology)
    - PAGASA (Philippine Atmospheric, Geophysical and Astronomical Services Administration)
    - DPWH (Department of Public Works and Highways)
    - National Building Code (PD 1096)
    - National Structural Code of the Philippines (NSCP)
    """
    high_risks = []
    
    # Identify high risks
    if flood_level in ['HS', 'VHS']:
        high_risks.append('flood')
    if landslide_level in ['HS', 'VHS', 'DF']:
        high_risks.append('landslide')
    if liquefaction_level in ['HS']:
        high_risks.append('liquefaction')
    
    # LOW/MODERATE RISK - Return simple recommendations
    if not high_risks:
        if flood_level == 'MS' or landslide_level == 'MS' or liquefaction_level == 'MS':
            return {
                'summary': 'Standard building codes with enhanced precautions',
                'details': '''
                    <div style="padding: 1rem; line-height: 1.8;">
                        <p style="margin-bottom: 1rem;"><strong>This location is suitable for development with standard precautions:</strong></p>
                        <ul style="margin: 0 0 1rem 1.5rem;">
                            <li><strong>Building Code Compliance:</strong> Follow National Building Code of the Philippines (PD 1096)</li>
                            <li><strong>Site Assessment:</strong> Conduct geotechnical investigation before construction</li>
                            <li><strong>Drainage Systems:</strong> Install proper surface water drainage</li>
                            <li><strong>Slope Protection:</strong> Maintain vegetation on slopes</li>
                        </ul>
                        <div style="background: #dbeafe; padding: 0.75rem; border-radius: 6px; border-left: 3px solid #3b82f6; margin-top: 1rem;">
                            <strong style="color: #1e40af;">📋 Required Permits:</strong><br>
                            Secure Building Permit from Local Government Unit and consult licensed civil/structural engineer.
                        </div>
                    </div>
                '''
            }
        else:
            return {
                'summary': 'Low risk - Standard construction practices',
                'details': '''
                    <div style="padding: 1rem; line-height: 1.8;">
                        <p style="margin-bottom: 1rem;"><strong>This location has minimal disaster exposure:</strong></p>
                        <ul style="margin: 0 0 1rem 1.5rem;">
                            <li><strong>Standard Building Code:</strong> Comply with National Building Code (PD 1096)</li>
                            <li><strong>Regular Maintenance:</strong> Maintain drainage and building integrity</li>
                            <li><strong>Emergency Preparedness:</strong> Prepare basic evacuation plan</li>
                        </ul>
                        <div style="background: #d1fae5; padding: 0.75rem; border-radius: 6px; border-left: 3px solid #10b981; margin-top: 1rem;">
                            <strong style="color: #065f46;">✅ Development Status:</strong><br>
                            Safe for residential, commercial, and institutional use.
                        </div>
                    </div>
                '''
            }
    
    # HIGH RISK - Build detailed recommendations
    rec_summary_parts = []
    rec_html = '<div style="padding: 1rem;">'
    
    # FLOOD RECOMMENDATIONS
    if 'flood' in high_risks:
        if flood_level == 'VHS':
            rec_summary_parts.append('VERY HIGH FLOOD RISK')
            rec_html += '''
                <div style="margin-bottom: 1.5rem; padding: 1rem; background: #fee2e2; border-left: 4px solid #dc2626; border-radius: 6px;">
                    <h6 style="color: #991b1b; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">🌊 VERY HIGH FLOOD RISK</h6>
                    <div style="background: #fef2f2; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; border: 1px solid #fca5a5;">
                        <strong style="color: #dc2626;">⚠️ DPWH/PAGASA ADVISORY:</strong><br>
                        <span style="font-size: 0.9rem;">Area is subject to severe flooding. Development is STRONGLY DISCOURAGED.</span>
                    </div>
                    
                    <p style="margin: 0 0 0.75rem 0; font-weight: 600; color: #7f1d1d;">If development must proceed (not recommended):</p>
                    <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; font-size: 0.9rem;">
                        <li><strong>Minimum Elevation:</strong> Raise finished floor at least 2.0 meters above ground (DPWH standard for flood-prone areas)</li>
                        <li><strong>Foundation:</strong> Use elevated post/pile foundations designed by licensed engineer</li>
                        <li><strong>Materials:</strong> Use flood-resistant materials (concrete, stone) for lower floors</li>
                        <li><strong>Drainage:</strong> Install comprehensive flood control with retention basins</li>
                        <li><strong>Emergency Access:</strong> Provide elevated exits and refuge areas on upper floors</li>
                        <li><strong>Utilities:</strong> Locate electrical panels and equipment above flood level</li>
                    </ul>
                    
                    <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                        <strong style="color: #dc2626;">🏛️ Required:</strong><br>
                        <span style="font-size: 0.875rem;">Consult Local DRRMO and DPWH District Office. Flood hazard disclosure required in property documents.</span>
                    </div>
                </div>
            '''
        else:  # HIGH flood
            rec_summary_parts.append('HIGH FLOOD RISK')
            rec_html += '''
                <div style="margin-bottom: 1.5rem; padding: 1rem; background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 6px;">
                    <h6 style="color: #92400e; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">🌊 HIGH FLOOD RISK</h6>
                    <div style="background: #fffbeb; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; border: 1px solid #fcd34d;">
                        <strong style="color: #b45309;">⚠️ DPWH/PAGASA ADVISORY:</strong><br>
                        <span style="font-size: 0.9rem;">Area is prone to flooding during heavy rainfall and typhoons.</span>
                    </div>
                    
                    <p style="margin: 0 0 0.75rem 0; font-weight: 600;">Required Flood Mitigation:</p>
                    <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; font-size: 0.9rem;">
                        <li><strong>Floor Elevation:</strong> Raise floor at least 1.5 meters above ground (DPWH recommendation)</li>
                        <li><strong>Foundation:</strong> Use elevated foundations or flood-resistant materials</li>
                        <li><strong>Drainage:</strong> Install perimeter drains and surface water diversion</li>
                        <li><strong>Flood Barriers:</strong> Use removable barriers for doorways and openings</li>
                        <li><strong>Utilities:</strong> Elevate HVAC, water heaters, and electrical systems</li>
                        <li><strong>Grading:</strong> Slope property away from structure</li>
                    </ul>
                    
                    <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                        <strong style="color: #92400e;">📋 Required:</strong><br>
                        <span style="font-size: 0.875rem;">Coordinate with Local DRRMO. Hydraulic plans must be approved by DPWH.</span>
                    </div>
                </div>
            '''
    
    # LANDSLIDE RECOMMENDATIONS
    if 'landslide' in high_risks:
        if landslide_level == 'DF':
            rec_summary_parts.append('DEBRIS FLOW ZONE')
            rec_html += '''
                <div style="margin-bottom: 1.5rem; padding: 1rem; background: #fee2e2; border-left: 4px solid #7f1d1d; border-radius: 6px;">
                    <h6 style="color: #7f1d1d; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1.1rem;">🌋 DEBRIS FLOW HAZARD ZONE</h6>
                    <div style="background: #fef2f2; padding: 1rem; border-radius: 4px; margin-bottom: 1rem; border: 2px solid #dc2626;">
                        <strong style="color: #991b1b; font-size: 1rem;">🚨 PHIVOLCS CRITICAL ADVISORY:</strong><br>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.95rem;">
                            This is a <strong>DEBRIS FLOW SUSCEPTIBILITY ZONE</strong>. Debris flows are catastrophic landslides 
                            with rocks, soil, and mud moving at high speeds. Can bury structures within minutes.
                        </p>
                    </div>
                    
                    <div style="background: #7f1d1d; color: white; padding: 1rem; border-radius: 6px; margin-bottom: 1rem;">
                        <p style="margin: 0; font-weight: 700; font-size: 1.05rem;">⛔ CONSTRUCTION PROHIBITED</p>
                        <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">No structural mitigation can protect against debris flows. Area must remain unpopulated.</p>
                    </div>
                    
                    <p style="margin: 0 0 0.75rem 0; font-weight: 700; color: #7f1d1d;">PHIVOLCS-Mandated Actions:</p>
                    <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.9; font-size: 0.9rem;">
                        <li><strong>No-Build Zone:</strong> Area designated as restricted per PHIVOLCS hazard mapping</li>
                        <li><strong>Evacuation Protocol:</strong> Mandatory evacuation during heavy rainfall (>100mm/24hrs)</li>
                        <li><strong>Early Warning:</strong> Install community rain gauges and monitoring system</li>
                        <li><strong>Land Use:</strong> Reforestation, watershed protection, or buffer zone only</li>
                        <li><strong>Relocation:</strong> If inhabited, coordinate with LGU and DSWD for relocation</li>
                    </ul>
                    
                    <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                        <strong style="color: #991b1b;">📞 Mandatory:</strong><br>
                        <span style="font-size: 0.875rem;">Contact PHIVOLCS Regional Office and Local DRRMO. Secure Geohazard Assessment.</span>
                    </div>
                </div>
            '''
        elif landslide_level == 'VHS':
            rec_summary_parts.append('VERY HIGH LANDSLIDE RISK')
            rec_html += '''
                <div style="margin-bottom: 1.5rem; padding: 1rem; background: #fef3c7; border-left: 4px solid #dc2626; border-radius: 6px;">
                    <h6 style="color: #92400e; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">⛰️ VERY HIGH LANDSLIDE RISK</h6>
                    <div style="background: #fffbeb; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; border: 1px solid #fcd34d;">
                        <strong style="color: #b45309;">⚠️ PHIVOLCS ADVISORY:</strong><br>
                        <span style="font-size: 0.9rem;">Very high landslide susceptibility. Development STRONGLY DISCOURAGED.</span>
                    </div>
                    
                    <p style="margin: 0 0 0.75rem 0; font-weight: 600;">If development cannot be avoided (extensive mitigation required):</p>
                    <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; font-size: 0.9rem;">
                        <li><strong>Slope Stabilization:</strong> Engineered retaining walls, soil nailing, rock bolting by geotechnical engineer</li>
                        <li><strong>Subsurface Drainage:</strong> Horizontal drains or deep wells to reduce water pressure</li>
                        <li><strong>Bioengineering:</strong> Plant deep-rooted native species (bamboo, agoho trees)</li>
                        <li><strong>Slope Angle:</strong> Maintain natural slopes below 30° where possible</li>
                        <li><strong>Monitoring:</strong> Install inclinometers, rain gauges, and early warning systems</li>
                        <li><strong>Setback:</strong> Minimum 10-meter buffer from slope crest or base</li>
                    </ul>
                    
                    <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                        <strong style="color: #dc2626;">🏛️ Required:</strong><br>
                        <span style="font-size: 0.875rem;">Geohazard Assessment by PHIVOLCS-accredited geologist. Clearance from Local DRRMO and Mines and Geosciences Bureau (MGB).</span>
                    </div>
                </div>
            '''
        else:  # HIGH landslide
            rec_summary_parts.append('HIGH LANDSLIDE RISK')
            rec_html += '''
                <div style="margin-bottom: 1.5rem; padding: 1rem; background: #fef9c3; border-left: 4px solid #f59e0b; border-radius: 6px;">
                    <h6 style="color: #78350f; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">⛰️ HIGH LANDSLIDE RISK</h6>
                    <div style="background: #fffbeb; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; border: 1px solid #fde047;">
                        <strong style="color: #a16207;">⚠️ PHIVOLCS ADVISORY:</strong><br>
                        <span style="font-size: 0.9rem;">Prone to landslides during heavy rain and earthquakes. Engineering required.</span>
                    </div>
                    
                    <p style="margin: 0 0 0.75rem 0; font-weight: 600;">Required Landslide Mitigation:</p>
                    <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; font-size: 0.9rem;">
                        <li><strong>Geotechnical Study:</strong> Site investigation with soil boring and stability analysis</li>
                        <li><strong>Retaining Walls:</strong> Gravity walls, gabions, or reinforced earth structures</li>
                        <li><strong>Surface Drainage:</strong> Lined channels to divert runoff away from slopes</li>
                        <li><strong>Terracing:</strong> Benched slopes with vegetation cover</li>
                        <li><strong>Foundation:</strong> Deep piles or piers anchored to stable bedrock</li>
                        <li><strong>Monitoring:</strong> Regular inspection for cracks, tilting, or ground movement</li>
                    </ul>
                    
                    <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                        <strong style="color: #92400e;">📋 Required:</strong><br>
                        <span style="font-size: 0.875rem;">Consult geotechnical engineer. Geohazard Clearance from PHIVOLCS/MGB and Local DRRMO.</span>
                    </div>
                </div>
            '''
    
    # LIQUEFACTION RECOMMENDATIONS
    if 'liquefaction' in high_risks:
        rec_summary_parts.append('HIGH LIQUEFACTION RISK')
        rec_html += '''
            <div style="margin-bottom: 1.5rem; padding: 1rem; background: #f3e8ff; border-left: 4px solid #9333ea; border-radius: 6px;">
                <h6 style="color: #6b21a8; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1rem;">〰️ HIGH LIQUEFACTION RISK</h6>
                <div style="background: #faf5ff; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; border: 1px solid #d8b4fe;">
                    <strong style="color: #7e22ce;">⚠️ PHIVOLCS/NBC ADVISORY:</strong><br>
                    <span style="font-size: 0.9rem;">During earthquakes, water-saturated soil may lose strength and behave like liquid, causing buildings to sink or tilt.</span>
                </div>
                
                <p style="margin: 0 0 0.75rem 0; font-weight: 600;">Required Liquefaction Mitigation (National Building Code):</p>
                <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; font-size: 0.9rem;">
                    <li><strong>Deep Foundations:</strong> Driven piles, bored piles, or caissons through liquefiable layers to stable soil (10-20m depth)</li>
                    <li><strong>Ground Improvement:</strong> Soil densification via vibro-compaction, dynamic compaction, or stone columns</li>
                    <li><strong>Testing:</strong> Standard Penetration Test (SPT) and Cone Penetration Test (CPT) to map liquefaction zones</li>
                    <li><strong>Structural Design:</strong> Moment-resisting frames or shear walls per National Structural Code of the Philippines (NSCP)</li>
                    <li><strong>Mat Foundation:</strong> Alternative: thick reinforced concrete mat to "float" on soil</li>
                    <li><strong>Dewatering:</strong> Install gravel drains or wells to lower groundwater table</li>
                </ul>
                
                <div style="background: white; padding: 0.75rem; border-radius: 4px;">
                    <strong style="color: #6b21a8;">🏛️ Required:</strong><br>
                    <span style="font-size: 0.875rem;">Foundation design sealed by licensed Civil Engineer. Must comply with NSCP Seismic Zone 4 provisions. Coordinate with Local Building Official.</span>
                </div>
            </div>
        '''
    
    # MULTIPLE HAZARDS WARNING
    if len(high_risks) >= 2:
        rec_html += '''
            <div style="padding: 1rem; background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 2px solid #dc2626; border-radius: 8px;">
                <h6 style="color: #991b1b; font-weight: 700; margin: 0 0 0.75rem 0; font-size: 1.05rem;">⚠️ MULTIPLE HAZARD EXPOSURE</h6>
                <p style="margin: 0 0 0.75rem 0; line-height: 1.7; font-size: 0.95rem; color: #7f1d1d;">
                    This location faces <strong>multiple high-severity hazards</strong>. Combined risks increase vulnerability significantly:
                </p>
                <ul style="margin: 0 0 1rem 1.5rem; line-height: 1.8; color: #7f1d1d; font-size: 0.9rem;">
                    <li>Mitigation may cost 30-50% of construction budget</li>
                    <li>Substantial long-term maintenance required</li>
                    <li>Property insurance may be unavailable or expensive</li>
                    <li>Resale value significantly reduced</li>
                </ul>
                <div style="background: #7f1d1d; color: white; padding: 0.875rem; border-radius: 6px;">
                    <strong style="font-size: 1rem;">🏛️ OFFICIAL RECOMMENDATION:</strong><br>
                    <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem;">
                        <strong>Relocate to safer site.</strong> If proceeding, conduct Multi-Hazard Risk Assessment and secure clearances from PHIVOLCS, PAGASA, Local DRRMO, MGB, and DPWH.
                    </p>
                </div>
            </div>
        '''
    
    rec_html += '</div>'
    
    summary = ' + '.join(rec_summary_parts) if rec_summary_parts else 'Low Risk'
    
    return {
        'summary': summary,
        'details': rec_html
    }

@api_view(['GET'])
def get_datasets(request):
    """Get list of uploaded datasets"""
    try:
        datasets = HazardDataset.objects.all().values(
            'id', 'name', 'dataset_type', 'upload_date', 'file_name'
        )
        return Response(list(datasets))
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two points using Haversine formula
    Returns distance in meters
    """
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Radius of earth in meters
    r = 6371000
    
    return c * r


def format_distance(meters):
    """Format distance for display"""
    if meters < 1000:
        return f"{int(meters)} m"
    else:
        km = meters / 1000
        return f"{km:.1f} km"

@api_view(['GET'])
def get_location_info(request):
    """Get administrative boundary info for a location"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        
        location_info = OverpassClient.get_location_info(lat, lng)
        
        return Response(location_info)
        
    except ValueError:
        return Response({'error': 'Invalid coordinates'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_barangay_data(request):
    """Get barangay boundary data as GeoJSON"""
    from .models import BarangayBoundary
    
    try:
        barangay_features = []
        barangay_records = BarangayBoundary.objects.all()
        
        for record in barangay_records:
            feature = {
                'type': 'Feature',
                'properties': {
                    'brgy_id': record.brgy_id,
                    'barangay_name': record.b_name,
                    'municipality': record.lgu_name,
                    'population_2020': record.pop_2020,
                    'area_hectares': record.hectares,
                    'district': record.district,
                    'dataset_id': record.dataset.id
                },
                'geometry': json.loads(record.geometry.geojson)
            }
            barangay_features.append(feature)
        
        geojson_data = {
            'type': 'FeatureCollection',
            'features': barangay_features
        }
        
        return Response(geojson_data)
    
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def get_barangay_from_point(request):
    """
    Get barangay information for a specific point location
    This replaces Nominatim for accurate barangay identification
    """
    from .models import BarangayBoundary
    from django.contrib.gis.geos import Point
    
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        
        point = Point(lng, lat, srid=4326)
        
        # Find which barangay boundary contains this point
        barangay = BarangayBoundary.objects.filter(
            geometry__contains=point
        ).first()
        
        if barangay:
            # Calculate population density
            population_density = None
            if barangay.pop_2020 and barangay.hectares and barangay.hectares > 0:
                population_density = round(barangay.pop_2020 / barangay.hectares, 2)
            
            return Response({
                'success': True,
                'barangay': barangay.b_name,
                'municipality': barangay.lgu_name,
                'province': 'Negros Oriental',
                'population_2020': barangay.pop_2020,
                'area_hectares': barangay.hectares,
                'district': barangay.district,
                'brgy_code': barangay.brgycode,
                'population_density': population_density,  # NEW: Population per hectare
                'full_address': f"{barangay.b_name}, {barangay.lgu_name}, Negros Oriental"
            })
        else:
            # Point is outside all barangay boundaries
            return Response({
                'success': False,
                'barangay': 'Unknown',
                'municipality': 'Unknown',
                'province': 'Negros Oriental',
                'full_address': f"Lat: {lat:.6f}, Lng: {lng:.6f}",
                'message': 'Location is outside mapped barangay boundaries'
            })
        
    except ValueError:
        return Response({'error': 'Invalid coordinates'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)