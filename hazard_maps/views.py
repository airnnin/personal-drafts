from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.gis.geos import Point
from .models import HazardDataset, FloodSusceptibility, LandslideSusceptibility, LiquefactionSusceptibility
from .utils import ShapefileProcessor
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
        
        valid_types = ['flood', 'landslide', 'liquefaction']
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
        
        return Response({
            'overall_risk': risk_assessment,
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

def get_user_friendly_label(level, hazard_type):
    """Convert technical labels to user-friendly descriptions"""
    if not level:
        return 'Not at risk - No hazard data for this area (safe zone)'
    
    DESCRIPTIONS = {
        'flood': {
            'LS': 'Low risk - Flooding unlikely',
            'MS': 'Moderate risk - Occasional flooding possible',
            'HS': 'High risk - Frequent flooding expected',
            'VHS': 'Very high risk - Severe flooding likely'
        },
        'landslide': {
            'LS': 'Low risk - Stable terrain',
            'MS': 'Moderate risk - Some slope instability',
            'HS': 'High risk - Landslide-prone area',
            'VHS': 'Very high risk - Critical landslide zone',
            'DF': 'CRITICAL RISK - Debris Flow zone: Catastrophic rapid movement of rocks, soil and water. Immediate evacuation required during heavy rain.'
        },
        'liquefaction': {
            'LS': 'Low risk - Soil unlikely to liquefy during earthquakes',
            'MS': 'Moderate risk - Soil may weaken during strong earthquakes',
            'HS': 'High risk - Soil highly prone to liquefaction during earthquakes'
        }
    }
    
    return DESCRIPTIONS.get(hazard_type, {}).get(level, 'Risk level unknown')

def calculate_risk_score(flood_level, landslide_level, liquefaction_level):
    """
    Calculate overall risk score based on hazard levels
    FIXED: Debris Flow (DF) now rated as HIGHEST risk (110/100)
    NO DATA = LOW RISK (area is safe from that hazard)
    Returns: dict with score (0-100), category, and color
    """
    # Risk weights based on Philippine disaster frequency
    WEIGHTS = {
        'flood': 0.5,      # 50% - most frequent disaster
        'landslide': 0.3,  # 30% - common in mountainous areas
        'liquefaction': 0.2 # 20% - only during earthquakes
    }
    
    # FIXED: Debris Flow (DF) is now rated HIGHEST at 110
    LEVEL_SCORES = {
        'LS': 25,   # Low = 25/100
        'MS': 50,   # Moderate = 50/100
        'HS': 75,   # High = 75/100
        'VHS': 100, # Very High = 100/100
        'DF': 110,  # DEBRIS FLOW = 110/100 (CRITICAL - exceeds VHS)
        None: 10    # NO DATA = 10/100 (assume safe - no hazard present)
    }
    
    # Calculate weighted score
    flood_score = LEVEL_SCORES.get(flood_level, 10) * WEIGHTS['flood']
    landslide_score = LEVEL_SCORES.get(landslide_level, 10) * WEIGHTS['landslide']
    liquefaction_score = LEVEL_SCORES.get(liquefaction_level, 10) * WEIGHTS['liquefaction']
    
    total_score = flood_score + landslide_score + liquefaction_score
    
    # Special case: Debris Flow automatically triggers VERY HIGH RISK
    if landslide_level == 'DF':
        total_score = max(total_score, 85)  # Ensure at least Very High Risk
    
    # Categorize overall risk
    if total_score < 25:
        category = 'LOW RISK'
        message = 'Generally safe for development'
        color = '#10b981'  # Green
        icon = '✅'
        recommendation = 'This location has low disaster risk. Suitable for most types of construction.'
        safety_level = 'SAFE'
    elif total_score < 50:
        category = 'MODERATE RISK'
        message = 'Acceptable with precautions'
        color = '#f59e0b'  # Yellow
        icon = '⚠️'
        recommendation = 'This location has moderate risk. Construction requires standard disaster mitigation measures (elevated foundations, drainage systems).'
        safety_level = 'CAUTION'
    elif total_score < 75:
        category = 'HIGH RISK'
        message = 'Significant hazards present'
        color = '#f97316'  # Orange
        icon = '⚠️'
        recommendation = 'This location has high disaster risk. Consult structural engineers and implement comprehensive mitigation measures. Consider alternative sites.'
        safety_level = 'WARNING'
    else:
        category = 'VERY HIGH RISK'
        message = 'Not recommended for development'
        color = '#ef4444'  # Red
        icon = '🚫'
        recommendation = 'This location has very high disaster risk. Development is strongly discouraged. Relocate to safer areas.'
        safety_level = 'DANGER'
    
    # Special messaging for Debris Flow
    if landslide_level == 'DF':
        category = 'CRITICAL RISK - DEBRIS FLOW ZONE'
        message = 'EXTREME DANGER - Evacuation zone'
        icon = '🚨'
        recommendation = 'This is a DEBRIS FLOW zone with catastrophic risk. Construction is PROHIBITED. Immediate evacuation required during heavy rainfall. Consult PHIVOLCS and local DRRMO.'
        safety_level = 'CRITICAL'
    
    return {
        'score': round(min(total_score, 100), 1),  # Cap display at 100
        'raw_score': round(total_score, 1),  # Actual score (can exceed 100 for DF)
        'category': category,
        'message': message,
        'color': color,
        'icon': icon,
        'recommendation': recommendation,
        'safety_level': safety_level
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
    
@api_view(['GET'])
def get_nearby_facilities(request):
    """Get facilities within specified radius with disaster-priority grouping"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = int(request.GET.get('radius', 3000))
        
        facilities = OverpassClient.query_facilities(lat, lng, radius)
        
        # Calculate distances
        for facility in facilities:
            distance = calculate_distance(lat, lng, facility['lat'], facility['lng'])
            facility['distance_meters'] = distance
            facility['distance_km'] = round(distance / 1000, 2)
            facility['distance_display'] = format_distance(distance)
            
            # Add walkability flag (critical for disasters)
            facility['is_walkable'] = distance <= 500  # Within 500m
        
        facilities.sort(key=lambda x: x['distance_meters'])
        
        # Reorganize by disaster priority
        evacuation_centers = []
        medical = []
        emergency_services = []
        essential_services = []
        other_facilities = []
        
        for f in facilities:
            ftype = f['facility_type']
            
            # Priority 1: Evacuation (schools, gyms, community centers as shelters)
            if ftype in ['school', 'community_centre', 'kindergarten', 'college', 'university']:
                f['subcategory'] = 'evacuation'
                f['priority'] = 1
                evacuation_centers.append(f)
            
            # Priority 2: Medical
            elif ftype in ['hospital', 'clinic', 'doctors', 'pharmacy']:
                f['subcategory'] = 'medical'
                f['priority'] = 2
                medical.append(f)
            
            # Priority 3: Emergency Services
            elif ftype in ['fire_station', 'police']:
                f['subcategory'] = 'emergency_services'
                f['priority'] = 3
                emergency_services.append(f)
            
            # Priority 4: Essential Services (food, water)
            elif ftype in ['marketplace', 'supermarket', 'convenience']:
                f['subcategory'] = 'essential'
                f['priority'] = 4
                essential_services.append(f)
            
            # Priority 5: Everything else
            else:
                f['subcategory'] = 'other'
                f['priority'] = 5
                other_facilities.append(f)
        
        # Find nearest of each critical type
        nearest_evacuation = evacuation_centers[0] if evacuation_centers else None
        nearest_hospital = next((f for f in medical if f['facility_type'] in ['hospital', 'clinic']), None)
        nearest_fire = next((f for f in emergency_services if f['facility_type'] == 'fire_station'), None)
        
        result = {
            'summary': {
                'nearest_evacuation': {
                    'name': nearest_evacuation['name'] if nearest_evacuation else 'None within 3km',
                    'distance': nearest_evacuation['distance_display'] if nearest_evacuation else 'N/A',
                    'is_walkable': nearest_evacuation['is_walkable'] if nearest_evacuation else False,
                } if nearest_evacuation else None,
                'nearest_hospital': {
                    'name': nearest_hospital['name'] if nearest_hospital else 'None within 3km',
                    'distance': nearest_hospital['distance_display'] if nearest_hospital else 'N/A',
                    'is_walkable': nearest_hospital['is_walkable'] if nearest_hospital else False,
                } if nearest_hospital else None,
                'nearest_fire_station': {
                    'name': nearest_fire['name'] if nearest_fire else 'None within 3km',
                    'distance': nearest_fire['distance_display'] if nearest_fire else 'N/A',
                    'is_walkable': nearest_fire['is_walkable'] if nearest_fire else False,
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