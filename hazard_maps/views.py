from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.gis.geos import Point
from django.core.cache import cache
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility, BarangayBoundaryNew
from .utils import ShapefileProcessor
from .utils import calculate_haversine_distance
from .overpass_client import OverpassClient
from math import radians, cos, sin, asin, sqrt
import json

def index(request):
    """Main map view"""
    return render(request, 'index.html')

@csrf_exempt
@api_view(['POST'])
def upload_shapefile(request):
    """Handle shapefile/CSV upload and processing"""
    if request.method == 'POST':
        if 'shapefile' not in request.FILES:
            return JsonResponse({'error': 'No file provided'}, status=400)
        
        if 'dataset_type' not in request.POST:
            return JsonResponse({'error': 'Dataset type not specified'}, status=400)
        
        uploaded_file = request.FILES['shapefile']
        dataset_type = request.POST['dataset_type']
        
        # Valid types
        valid_types = [
            'flood', 'landslide', 'liquefaction', 'barangay', 'barangay_new', 
            'municipality_characteristics', 'barangay_characteristics', 'zonal_values'
        ]
        if dataset_type not in valid_types:
            return JsonResponse({
                'error': f'Invalid dataset type. Must be one of: {valid_types}'
            }, status=400)
        
        # NEW: Check file type based on dataset type
        file_name = uploaded_file.name.lower()
        
        # CSV datasets - accept .csv files directly
        if dataset_type in ['municipality_characteristics', 'barangay_characteristics','zonal_values']:
            if not file_name.endswith('.csv'):
                return JsonResponse({
                    'error': 'Please upload a .csv file for this dataset type'
                }, status=400)
            
            # Use CSV processor
            from .utils import CSVProcessor
            processor = CSVProcessor(uploaded_file, dataset_type)
        
        # Shapefile datasets - require .zip files
        else:
            if not file_name.endswith('.zip'):
                return JsonResponse({
                    'error': 'Please upload a .zip file containing shapefile data'
                }, status=400)
            
            # Use Shapefile processor
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
        
        # OPTIMIZED: Cache facility data to avoid duplicate API calls
        try:
            # Try to get from cache first (stored by get_nearby_facilities)
            cache_key = f"facilities_{round(lat, 4)}_{round(lng, 4)}"
            from django.core.cache import cache
            
            nearby_facilities = cache.get(cache_key)
            
            if nearby_facilities is None:
                # If not cached, fetch and cache for 5 minutes
                nearby_facilities = get_nearby_facilities_for_suitability(lat, lng)
                cache.set(cache_key, nearby_facilities, 300)  # 5 minutes
                print(f"✅ Cached facility data for suitability calculation")
            else:
                print(f"✅ Using cached facility data")
                
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
    """Get facilities within specified radius with disaster-priority grouping - FIXED VERSION"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = int(request.GET.get('radius', 3000))
        
        # CACHE CHECK - Avoid duplicate Overpass API calls
        cache_key = f"facilities_{round(lat, 4)}_{round(lng, 4)}"
        from django.core.cache import cache
        
        cached_result = cache.get(cache_key + "_full")
        if cached_result:
            print(f"✅ Returning cached facility data (avoiding Overpass API call)")
            return Response(cached_result)
        
        # Get facilities from Overpass
        facilities = OverpassClient.query_facilities(lat, lng, radius)
        
        # VALIDATION: Check if we got any facilities
        if not facilities or len(facilities) == 0:
            return Response({
                'error': 'No facilities found in this area',
                'summary': {
                    'nearest_evacuation': None,
                    'nearest_hospital': None,
                    'nearest_fire_station': None,
                },
                'evacuation_centers': [],
                'medical': [],
                'emergency_services': [],
                'essential_services': [],
                'other': [],
                'counts': {
                    'evacuation': 0,
                    'medical': 0,
                    'emergency_services': 0,
                    'essential': 0,
                    'other': 0,
                    'total': 0
                }
            })
        
        # Calculate straight-line distances (fast and reliable)
        from .utils import calculate_haversine_distance
        for facility in facilities:
            distance_meters = calculate_haversine_distance(
                lat, lng,
                facility['lat'], facility['lng']
            )
            
            facility['distance_meters'] = distance_meters
            facility['distance_km'] = round(distance_meters / 1000, 2)
            facility['distance_display'] = format_distance(distance_meters)
            facility['is_walkable'] = distance_meters <= 500
            
            # Estimate travel time (assuming 40 km/h average speed)
            duration_minutes = (distance_meters / 1000) / 40 * 60
            facility['duration_minutes'] = round(duration_minutes, 1)
            facility['duration_display'] = format_duration(duration_minutes * 60)
            facility['method'] = 'straight_line'
        
        # CRITICAL: Ensure all required fields exist
        for f in facilities:
            # Add missing fields with defaults if not present
            if 'distance_display' not in f:
                f['distance_display'] = format_distance(f.get('distance_meters', 0))
            if 'duration_display' not in f:
                duration_min = f.get('duration_minutes', 0)
                f['duration_display'] = f"{int(duration_min)} min" if duration_min >= 1 else "< 1 min"
            if 'is_walkable' not in f:
                f['is_walkable'] = f.get('distance_meters', 9999) <= 500
        
        # Sort by distance
        facilities.sort(key=lambda x: x.get('distance_meters', 999999))
        
        # Reorganize by disaster priority - IMPROVED CATEGORIZATION
        evacuation_centers = []
        medical = []
        emergency_services = []
        essential_services = []
        other_facilities = []
        
        for f in facilities:
            # Get subcategory (pre-assigned by Overpass)
            subcat = f.get('subcategory', '')
            ftype = f.get('facility_type', '')
            
            # Categorize facilities
            if subcat == 'evacuation' or ftype in ['school', 'community_centre', 'kindergarten', 'college', 'university']:
                f['subcategory'] = 'evacuation'
                evacuation_centers.append(f)
            elif subcat == 'medical' or ftype in ['hospital', 'clinic', 'doctors', 'pharmacy']:
                f['subcategory'] = 'medical'
                medical.append(f)
            elif subcat == 'emergency_services' or ftype in ['fire_station', 'police']:
                f['subcategory'] = 'emergency_services'
                emergency_services.append(f)
            elif subcat == 'essential' or ftype in ['marketplace', 'supermarket', 'convenience', 'bank', 'fuel', 
                          'restaurant', 'fast_food', 'cafe', 'mall', 'atm', 'department_store']:
                f['subcategory'] = 'essential'
                essential_services.append(f)
            else:
                f['subcategory'] = 'other'
                other_facilities.append(f)

        # DEBUG LOGGING
        print(f"📊 Categorization Results:")
        print(f"   - Evacuation: {len(evacuation_centers)}")
        print(f"   - Medical: {len(medical)}")
        print(f"   - Emergency Services: {len(emergency_services)}")
        print(f"   - Essential Services: {len(essential_services)}")
        print(f"   - Other: {len(other_facilities)}")
        
        # FIXED: Find nearest of each critical type (NO DUPLICATES)
        nearest_evacuation = evacuation_centers[0] if evacuation_centers else None
        nearest_hospital = medical[0] if medical else None  # FIXED: Take first medical facility
        nearest_fire = next((f for f in emergency_services if f.get('facility_type') == 'fire_station'), None)
        
        # CRITICAL FIX: Build summary with proper null handling
        def build_facility_summary(facility):
            """Helper to build facility summary with all required fields"""
            if not facility:
                return None
            
            return {
                'name': facility.get('name', 'Unknown'),
                'distance': facility.get('distance_display', 'N/A'),
                'distance_meters': facility.get('distance_meters', 999999),
                'duration': facility.get('duration_display', 'N/A'),
                'is_walkable': facility.get('is_walkable', False),
            }
        
        result = {
            'summary': {
                'nearest_evacuation': build_facility_summary(nearest_evacuation),
                'nearest_hospital': build_facility_summary(nearest_hospital),
                'nearest_fire_station': build_facility_summary(nearest_fire),
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

        # ... all the categorization code ...
    
        result = {
            'summary': { ... },
            'evacuation_centers': evacuation_centers[:10],
            'medical': medical[:10],
            'emergency_services': emergency_services[:10],
            'essential_services': essential_services[:10],
            'other': other_facilities[:10],
            'counts': { ... }
        }
        
        # ✅ CACHE THE RESULT for 5 minutes
        cache.set(cache_key + "_full", result, 300)
        
        # Also cache simplified version for suitability
        simplified_result = {
            'summary': result['summary'],
            'counts': result['counts']
        }
        cache.set(cache_key, simplified_result, 300)
        
        return Response(result)
        
    except ValueError:
        return Response({'error': 'Invalid coordinates or radius'}, status=400)
    except Exception as e:
        print(f"❌ Error in get_nearby_facilities: {e}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)

def get_nearby_facilities_for_suitability(lat, lng):
    """Helper function for suitability calculation"""
    from .overpass_client import OverpassClient
    from .utils import calculate_haversine_distance  # ✅ FIXED
    
    try:
        facilities = OverpassClient.query_facilities(lat, lng, 3000)
        
        if not facilities:
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
        
        # ✅ Calculate straight-line distances (FAST & RELIABLE)
        for facility in facilities:
            distance_meters = calculate_haversine_distance(
                lat, lng,
                facility['lat'], facility['lng']
            )
            
            facility['distance_meters'] = distance_meters
            facility['distance_km'] = round(distance_meters / 1000, 2)
            facility['distance_display'] = format_distance(distance_meters)
            facility['is_walkable'] = distance_meters <= 500
            
            # Estimate travel time
            duration_minutes = (distance_meters / 1000) / 40 * 60
            facility['duration_minutes'] = round(duration_minutes, 1)
            facility['duration_display'] = format_duration(duration_minutes * 60)
            facility['method'] = 'straight_line'
        
        facilities.sort(key=lambda x: x.get('distance_meters', 999999))
        
        # IMPROVED CATEGORIZATION (same as main function)
        evacuation_centers = []
        medical = []
        emergency_services = []
        essential_services = []
        other_facilities = []
        
        for f in facilities:
            subcat = f.get('subcategory', '')
            ftype = f.get('facility_type', '')
            
            if subcat == 'evacuation' or ftype in ['school', 'community_centre', 'kindergarten', 'college', 'university']:
                f['subcategory'] = 'evacuation'
                evacuation_centers.append(f)
            elif subcat == 'medical' or ftype in ['hospital', 'clinic', 'doctors', 'pharmacy']:
                f['subcategory'] = 'medical'
                medical.append(f)
            elif subcat == 'emergency_services' or ftype in ['fire_station', 'police']:
                f['subcategory'] = 'emergency_services'
                emergency_services.append(f)
            elif subcat == 'essential' or ftype in ['marketplace', 'supermarket', 'convenience', 'bank', 'fuel', 
                          'restaurant', 'fast_food', 'cafe', 'mall', 'atm', 'department_store']:
                f['subcategory'] = 'essential'
                essential_services.append(f)
            else:
                f['subcategory'] = 'other'
                other_facilities.append(f)
        
        nearest_evacuation = evacuation_centers[0] if evacuation_centers else None
        nearest_hospital = medical[0] if medical else None
        nearest_fire = next((f for f in emergency_services if f.get('facility_type') == 'fire_station'), None)
        
        def build_facility_summary(facility):
            if not facility:
                return None
            return {
                'name': facility.get('name', 'Unknown'),
                'distance': facility.get('distance_display', 'N/A'),
                'distance_meters': facility.get('distance_meters', 999999),
                'duration': facility.get('duration_display', 'N/A'),
                'is_walkable': facility.get('is_walkable', False),
            }
        
        return {
            'summary': {
                'nearest_evacuation': build_facility_summary(nearest_evacuation),
                'nearest_hospital': build_facility_summary(nearest_hospital),
                'nearest_fire_station': build_facility_summary(nearest_fire),
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
        print(f"❌ ERROR in get_nearby_facilities_for_suitability: {e}")
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

def format_duration(seconds):
    """Format duration for display"""
    minutes = seconds / 60
    if minutes < 1:
        return "< 1 min"
    elif minutes < 60:
        return f"{int(minutes)} min"
    else:
        hours = int(minutes / 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}min"

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
    """Get barangay boundary data as GeoJSON - NEW VERSION"""
    try:
        barangay_features = []
        
        # Use the NEW barangay model
        barangay_records = BarangayBoundaryNew.objects.all()
        
        for record in barangay_records:
            feature = {
                'type': 'Feature',
                'properties': {
                    'barangay_name': record.adm4_en,
                    'barangay_code': record.adm4_pcode,
                    'municipality': record.adm3_en,
                    'province': record.adm2_en,
                    'region': record.adm1_en,
                    'area_sqkm': record.area_sqkm,
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


# REPLACE the old get_barangay_from_point function
@api_view(['GET'])
def get_barangay_from_point(request):
    """
    Get barangay information for a specific point location - NEW VERSION
    Uses accurate PSA-NAMRIA boundaries
    """
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        
        point = Point(lng, lat, srid=4326)
        
        # Find which barangay boundary contains this point
        barangay = BarangayBoundaryNew.objects.filter(
            geometry__contains=point
        ).first()
        
        if barangay:
            return Response({
                'success': True,
                'barangay': barangay.adm4_en,
                'municipality': barangay.adm3_en,
                'province': barangay.adm2_en,
                'region': barangay.adm1_en,
                'area_sqkm': barangay.area_sqkm,
                'barangay_code': barangay.adm4_pcode,
                'municipality_code': barangay.adm3_pcode,
                'full_address': f"{barangay.adm4_en}, {barangay.adm3_en}, {barangay.adm2_en}"
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
    

@api_view(['GET'])
def get_municipality_info(request):
    """
    Get municipality characteristics by municipality code
    Used when clicking on a barangay to show municipality summary
    """
    try:
        municipality_code = request.GET.get('code')
        
        if not municipality_code:
            return Response({'error': 'Municipality code not provided'}, status=400)
        
        from .models import MunicipalityCharacteristic
        
        # Find municipality by correspondence code
        municipality = MunicipalityCharacteristic.objects.filter(
            correspondence_code=municipality_code
        ).first()
        
        if not municipality:
            return Response({
                'found': False,
                'message': 'No data available for this municipality'
            })
        
        return Response({
            'found': True,
            'municipality': {
                'name': municipality.lgu_name,
                'code': municipality.correspondence_code,
                'category': municipality.category,
                'population': municipality.population,
                'population_display': municipality.get_population_display(),
                'revenue': float(municipality.revenue),
                'revenue_display': municipality.get_revenue_display(),
                'provincial_score': municipality.provincial_score,
                'poverty_incidence_rate': municipality.poverty_incidence_rate,
                
                # Additional data for potential use
                'score': municipality.score,
                'population_weight': municipality.population_weight,
                'revenue_weight': municipality.revenue_weight,
                'total_percentage': municipality.total_percentage,
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    


@api_view(['GET'])
def get_barangay_characteristics(request):
    """
    Get barangay characteristics by barangay code with nearby facilities
    Used when clicking on a barangay to show detailed info
    """
    try:
        barangay_code = request.GET.get('code')
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        
        if not barangay_code:
            return Response({'error': 'Barangay code not provided'}, status=400)
        
        from .models import BarangayCharacteristic
        
        # Find barangay by code
        barangay = BarangayCharacteristic.objects.filter(
            barangay_code=barangay_code
        ).first()
        
        if not barangay:
            return Response({
                'found': False,
                'message': 'No characteristics data available for this barangay'
            })
        
        # Get nearby facilities if coordinates provided
        nearby_facilities_by_category = {}
        if lat and lng:
            try:
                lat = float(lat)
                lng = float(lng)
                nearby_facilities_by_category = get_categorized_facilities(lat, lng, radius=3000)
            except Exception as e:
                print(f"Error getting facilities: {e}")
        
        return Response({
            'found': True,
            'barangay': {
                'name': barangay.barangay_name,
                'code': barangay.barangay_code,
                'population': barangay.population,
                'population_display': barangay.get_population_display(),
                'ecological_landscape': barangay.ecological_landscape,
                'landscape_icon': barangay.get_landscape_icon(),
                'urbanization': barangay.urbanization,
                'urbanization_icon': barangay.get_urbanization_icon(),
                'cellular_signal': barangay.cellular_signal,
                'public_street_sweeper': barangay.public_street_sweeper,
                'facilities': nearby_facilities_by_category,  
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

def get_categorized_facilities(lat, lng, radius=3000):
    """
    Get facilities categorized by type for barangay characteristics
    
    Categories:
    - Education (Elementary/High School/College)
    - Hospital
    - Health Center/Clinic
    - Fire Station
    - Seaport
    - Post Office
    """
    from .overpass_client import OverpassClient    
    # Query facilities
    facilities = OverpassClient.query_facilities(lat, lng, radius)
    
    if not facilities:
        return {}
    
    # Calculate straight-line distances (fast and reliable)
    from .utils import calculate_haversine_distance
    for facility in facilities:
        distance_meters = calculate_haversine_distance(
            lat, lng,
            facility['lat'], facility['lng']
        )
        
        facility['distance_meters'] = distance_meters
        facility['distance_km'] = round(distance_meters / 1000, 2)
        facility['distance_display'] = format_distance(distance_meters)
        facility['is_walkable'] = distance_meters <= 500
        
        # Estimate travel time (assuming 40 km/h average speed)
        duration_minutes = (distance_meters / 1000) / 40 * 60
        facility['duration_minutes'] = round(duration_minutes, 1)
        facility['duration_display'] = format_duration(duration_minutes * 60)
        facility['method'] = 'straight_line'

    # Categorize facilities
    categorized = {
        'education_elementary': [],
        'education_highschool': [],
        'education_college': [],
        'hospital': [],
        'health_center': [],
        'fire_station': [],
        'seaport': [],
        'post_office': [],
    }
    
    for facility in facilities:
        ftype = facility.get('facility_type', '')
        name = facility.get('name', 'Unnamed')
        distance = facility.get('distance_meters', 999999)
        distance_display = facility.get('distance_display', 'N/A')
        
        # Only include facilities within 3km
        if distance > 3000:
            continue
        
        facility_info = {
            'name': name,
            'distance': distance_display,
            'distance_meters': distance,
        }
        
        # Education - Elementary
        if ftype in ['school', 'kindergarten']:
            # Check if it's specifically elementary or assume elementary for generic "school"
            if 'elementary' in name.lower() or 'elem' in name.lower() or ftype == 'kindergarten':
                categorized['education_elementary'].append(facility_info)
            elif 'high' in name.lower() or 'secondary' in name.lower():
                categorized['education_highschool'].append(facility_info)
            elif 'college' in name.lower() or 'university' in name.lower():
                categorized['education_college'].append(facility_info)
            else:
                # Default to elementary for generic schools
                categorized['education_elementary'].append(facility_info)
        
        # Education - High School
        elif ftype == 'school' and ('high' in name.lower() or 'secondary' in name.lower()):
            categorized['education_highschool'].append(facility_info)
        
        # Education - College/University
        elif ftype in ['college', 'university']:
            categorized['education_college'].append(facility_info)
        
        # Hospital
        elif ftype == 'hospital':
            categorized['hospital'].append(facility_info)
        
        # Health Center/Clinic
        elif ftype in ['clinic', 'doctors']:
            categorized['health_center'].append(facility_info)
        
        # Fire Station
        elif ftype == 'fire_station':
            categorized['fire_station'].append(facility_info)
        
        # Seaport (we need to query this separately via Overpass)
        elif ftype in ['ferry_terminal', 'port']:
            categorized['seaport'].append(facility_info)
        
        # Post Office
        elif ftype == 'post_office':
            categorized['post_office'].append(facility_info)
    
    # Sort each category by distance
    for category in categorized:
        categorized[category].sort(key=lambda x: x['distance_meters'])
    
    # Count facilities in each category
    counts = {
        'education_elementary': len(categorized['education_elementary']),
        'education_highschool': len(categorized['education_highschool']),
        'education_college': len(categorized['education_college']),
        'hospital': len(categorized['hospital']),
        'health_center': len(categorized['health_center']),
        'fire_station': len(categorized['fire_station']),
        'seaport': len(categorized['seaport']),
        'post_office': len(categorized['post_office']),
    }
    
    return {
        'facilities': categorized,
        'counts': counts
    }


@api_view(['GET'])
def get_zonal_values(request):
    """
    Get zonal values for a specific barangay by code
    Used to show land prices when clicking on a barangay
    """
    try:
        barangay_code = request.GET.get('code')
        
        if not barangay_code:
            return Response({'error': 'Barangay code not provided'}, status=400)
        
        from .models import ZonalValue
        
        # Find all zonal values for this barangay
        zonal_values = ZonalValue.objects.filter(
            barangay_code=barangay_code
        ).order_by('street', 'vicinity')
        
        if not zonal_values.exists():
            return Response({
                'found': False,
                'message': 'No zonal value data available for this barangay'
            })
        
        # Calculate statistics
        prices = [float(zv.price_per_sqm) for zv in zonal_values]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        # Build zonal value list
        values_list = []
        for zv in zonal_values:
            values_list.append({
                'street': zv.street or 'General',
                'vicinity': zv.vicinity or '',
                'land_class': zv.land_class or 'N/A',
                'price_per_sqm': float(zv.price_per_sqm),
                'price_display': zv.get_price_display(),
                'price_formatted': zv.get_price_per_sqm_formatted(),
            })
        
        return Response({
            'found': True,
            'barangay_name': zonal_values.first().barangay_name,
            'municipality': zonal_values.first().municipality,
            'zonal_values': values_list,
            'statistics': {
                'count': len(values_list),
                'average_price': round(avg_price, 2),
                'average_price_display': f"₱{avg_price:,.2f}",
                'min_price': round(min_price, 2),
                'min_price_display': f"₱{min_price:,.2f}",
                'max_price': round(max_price, 2),
                'max_price_display': f"₱{max_price:,.2f}",
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)